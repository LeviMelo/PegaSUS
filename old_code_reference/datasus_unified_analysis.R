# ==============================================================================
# SCRIPT: DATASUS UNIFIED ANALYSIS & REPORTING PIPELINE
#
# ARCHITECTURE: A single, idempotent script that performs discovery, download,
#               analysis, and reporting with self-healing checkpoints.
#
# WORKFLOW:
# 1. SETUP: Loads libraries and defines all paths and constants.
# 2. CHECKPOINT & TARGETING: Checks for existing results. If found, it
#    identifies only the failed or missing data series to process.
# 3. ANALYSIS PIPELINE (Conditional): If there are series to process, it runs:
#    - Download: Fetches a curated set of candidate files with caching.
#    - Parallel Analysis: Processes the files, handling errors and sampling.
#    - Merge & Save: Merges new results with any old ones and saves
#      checkpoints (`.RData` and `.json`).
# 4. REPORTING: Generates a comprehensive Markdown report that includes:
#    - An aggregate summary table of all series.
#    - A detailed variable-by-variable breakdown for each successful series.
# 5. SUMMARY: Logs the final execution status.
# ==============================================================================

# ==============================================================================
# PHASE 1: SCRIPT SETUP
# ==============================================================================

# --- Install and Load Libraries ---
packages <- c("curl", "jsonlite", "dplyr", "parallel", "foreach", "doParallel", "read.dbc", "foreign", "knitr")
install_if_missing <- function(p) { if (!require(p, character.only = TRUE)) install.packages(p, dependencies = TRUE) }
invisible(sapply(packages, install_if_missing))

suppressPackageStartupMessages({
  library(curl)
  library(jsonlite)
  library(dplyr)
  library(parallel)
  library(foreach)
  library(doParallel)
  library(read.dbc)
  library(foreign)
  library(knitr)
})
cat("✅ All required packages are loaded.\n")


# --- Define Global Constants, File Paths, and Logging ---
# Input files
json_catalog_path <- 'datasus_discovery_catalog.json'
ftp_links_path <- 'link_ftp.txt'

# Output & Cache files
json_checkpoint_path <- "datasus_analysis.json"
rdata_checkpoint_path <- "analysis_results.RData"
md_report_path <- "datasus_report.md"
cache_dir <- file.path(getwd(), "datasus_file_cache")
log_file_path <- "pipeline.log"

# Analysis parameters
MAX_ROWS_FOR_ANALYSIS <- 50000
MAX_CATEGORICAL_VALUES <- 25

# --- Setup Logging and Directories ---
if (file.exists(log_file_path)) file.remove(log_file_path)
log_message <- function(message, level = "INFO") {
  log_entry <- sprintf("%s [%s]: %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), level, message)
  cat(log_entry, "\n")
  write(log_entry, file = log_file_path, append = TRUE)
}
if (!dir.exists(cache_dir)) dir.create(cache_dir)

log_message("Starting DATASUS Unified Analysis Pipeline.")

# --- Critical Input File Check ---
if (!file.exists(json_catalog_path)) stop("❌ CRITICAL ERROR: 'datasus_discovery_catalog.json' not found.")
if (!file.exists(ftp_links_path)) stop("❌ CRITICAL ERROR: 'link_ftp.txt' not found.")


# ==============================================================================
# PHASE 2: SELF-HEALING CHECKPOINT & TARGET IDENTIFICATION
# ==============================================================================
full_analysis_list <- NULL
tryCatch({
  if (file.exists(json_checkpoint_path)) {
    full_analysis_list <- fromJSON(json_checkpoint_path, simplifyVector = FALSE)
    log_message("Found and successfully loaded existing analysis checkpoint.")
  }
}, error = function(e) {
  log_message(paste("Checkpoint file is corrupt. Deleting it and starting fresh. Error:", e$message), level = "WARN")
  if (file.exists(json_checkpoint_path)) file.remove(json_checkpoint_path)
  if (file.exists(rdata_checkpoint_path)) file.remove(rdata_checkpoint_path)
  full_analysis_list <- NULL
})

catalog_text <- readLines(json_catalog_path, warn = FALSE)
catalog <- fromJSON(paste(catalog_text, collapse = ""), flatten = TRUE)
all_series_names <- names(catalog)

series_to_process <- if (is.null(full_analysis_list)) {
  log_message("No valid checkpoint found. All series will be analyzed.")
  all_series_names
} else {
  successful_series <- names(full_analysis_list)[sapply(full_analysis_list, function(x) x$series_metadata$status == "Success")]
  failed_series <- setdiff(all_series_names, successful_series)
  if (length(failed_series) == 0) {
    log_message("All series have been successfully analyzed previously. Skipping directly to reporting.")
  } else {
    log_message(paste("Targeting the remaining", length(failed_series), "failed/missing series for analysis."))
  }
  failed_series
}


# ==============================================================================
# PHASE 3: ANALYSIS PIPELINE (RUNS ONLY IF NEEDED)
# ==============================================================================
if (length(series_to_process) > 0) {
  # --- Helper Functions for Analysis ---
  parse_date_from_filename <- function(filename, format, prefix) {
    tryCatch({
      core_name <- sub(paste0("^", prefix), "", tools::file_path_sans_ext(filename), ignore.case = TRUE)
      date_part <- sub("^[A-Z]{2}", "", core_name)
      year <- NA; month <- "01"
      if (format == "YYMM") {
        year_str <- substr(date_part, 1, 2); month <- substr(date_part, 3, 4)
      } else if (format == "YYYY") {
        year_str <- substr(date_part, 1, 4)
      } else if (format == "YY") {
        year_str <- substr(date_part, 1, 2)
      } else { return(NA) }
      year_num <- suppressWarnings(as.numeric(year_str))
      year <- if (nchar(year_str) == 2) { if (year_num > 50) 1900 + year_num else 2000 + year_num } else { year_num }
      return(as.numeric(paste0(year, month)))
    }, error = function(e) { return(NA) })
  }
  sanitize_text <- function(x) { iconv(x, from = "latin1", to = "UTF-8", sub = "") }
  
  # --- Sub-Phase 3.1: Create Analysis Tasks and Download Initial Files ---
  all_ftp_links <- readLines(ftp_links_path)
  analysis_tasks <- bind_rows(lapply(series_to_process, function(s_name) {
    series_info <- catalog[[s_name]]
    relevant_links <- all_ftp_links[grepl(paste0("/", s_name), all_ftp_links, ignore.case = TRUE)]
    if (length(relevant_links) == 0) return(NULL)
    data.frame(series_name = s_name, url = relevant_links, filename = basename(relevant_links), stringsAsFactors = FALSE) %>%
      mutate(parsed_date = sapply(filename, parse_date_from_filename, series_info$date_format, s_name)) %>%
      filter(!is.na(parsed_date) & !grepl("\\.(zip|pdf|doc|xls)$", filename, ignore.case = TRUE))
  })) %>%
    group_by(series_name) %>%
    arrange(desc(parsed_date)) %>%
    summarise(candidates = list(pick(everything())), .groups = 'drop')
  
  # Download a small, curated set of initial candidates to speed up the process
  initial_download_plan_df <- bind_rows(lapply(series_to_process, function(s_name) {
    task <- analysis_tasks %>% filter(series_name == s_name)
    if(nrow(task) == 0) return(NULL)
    latest_files <- task$candidates[[1]]
    state_files <- latest_files %>% filter(!grepl(paste0(s_name, "BR"), filename, ignore.case = TRUE)) %>% head(3)
    candidate_files <- if (nrow(state_files) > 0) state_files else latest_files %>% head(1)
    if (nrow(candidate_files) == 0) return(NULL)
    data.frame(url = candidate_files$url, local_path = file.path(cache_dir, candidate_files$filename))
  }))
  
  if (nrow(initial_download_plan_df) > 0) {
    existing_files_mask <- file.exists(initial_download_plan_df$local_path)
    files_to_download_df <- initial_download_plan_df[!existing_files_mask, ]
    if (nrow(files_to_download_df) > 0) {
      log_message(paste("Downloading", nrow(files_to_download_df), "initial candidate files..."))
      multi_download(urls = files_to_download_df$url, destfiles = files_to_download_df$local_path, resume = TRUE)
    } else {
      log_message("All initial candidate files are already cached.")
    }
  }
  
  # --- Sub-Phase 3.2: Robust Parallel Analysis ---
  num_cores <- detectCores() - 1; if (num_cores < 1) num_cores <- 1
  cl <- makeCluster(num_cores); registerDoParallel(cl)
  log_message(paste("Analyzing", nrow(analysis_tasks), "series using", num_cores, "CPU cores..."))
  
  newly_analyzed_list <- foreach(i = 1:nrow(analysis_tasks), .packages = c("dplyr", "read.dbc", "foreign", "curl")) %dopar% {
    task <- analysis_tasks[i, ]
    series_name <- task$series_name
    tryCatch({
      candidates <- task$candidates[[1]]
      df <- NULL; file_analyzed <- NULL; rows_original <- 0
      
      # Fallback Loop: Try candidates until a readable one is found
      for (j in 1:nrow(candidates)) {
        candidate_row <- candidates[j, ]
        local_path <- file.path(cache_dir, candidate_row$filename)
        try({
          if (!file.exists(local_path)) { curl_download(candidate_row$url, destfile = local_path, quiet = TRUE) }
          temp_df <- NULL
          if (tolower(tools::file_ext(local_path)) == "dbc") {
            temp_df_raw <- suppressWarnings(read.dbc(local_path))
            temp_df <- as.data.frame(lapply(temp_df_raw, function(x) if(is.character(x)) iconv(x, from="latin1", to="UTF-8", sub="") else x), stringsAsFactors = FALSE)
          } else if (tolower(tools::file_ext(local_path)) == "dbf") {
            temp_df <- read.dbf(local_path, as.is = TRUE)
          }
          if (!is.null(temp_df) && nrow(temp_df) > 0) {
            df <- temp_df; file_analyzed <- basename(local_path); rows_original <- nrow(df); break
          }
        }, silent = TRUE)
      }
      
      if (is.null(df)) { return(list(series_metadata = list(series_name = series_name, status = "Failed", message = "All candidates were empty, unreadable, or failed to download."))) }
      
      rows_sampled <- nrow(df)
      if(nrow(df) > MAX_ROWS_FOR_ANALYSIS) {
        df <- df[sample(nrow(df), MAX_ROWS_FOR_ANALYSIS), ]
        rows_sampled <- MAX_ROWS_FOR_ANALYSIS
      }
      
      # Sanitize column names and character data
      colnames(df) <- sanitize_text(colnames(df))
      df <- as.data.frame(lapply(df, function(x) if(is.character(x) || is.factor(x)) sanitize_text(as.character(x)) else x), stringsAsFactors = FALSE)
      
      variable_analysis <- list()
      for (col_name in colnames(df)) {
        col_data <- df[[col_name]]; na_rate <- paste0(format(round(mean(is.na(col_data)) * 100, 2), nsmall = 2), "%")
        analysis <- list(); unique_vals <- unique(na.omit(col_data))
        
        if (is.numeric(col_data) || inherits(col_data, 'Date')) {
          analysis$type <- if(is.numeric(col_data)) "continuous_numeric" else "date"
          s <- summary(col_data)
          analysis$summary_stats <- list(min = s[[1]], q1 = s[[2]], median = s[[3]], mean = s[[4]], q3 = s[[5]], max = s[[6]])
        } else {
          freq_table <- table(col_data)
          if (length(freq_table) <= MAX_CATEGORICAL_VALUES) {
            analysis$type <- "categorical"; analysis$unique_values <- length(freq_table); names(freq_table) <- sanitize_text(names(freq_table)); analysis$frequencies <- as.list(freq_table)
          } else { analysis$type <- "high_cardinality_text" }
        }
        analysis$sample_values <- as.character(head(unique_vals, 5))
        variable_analysis[[col_name]] <- list(variable_name = col_name, data_type = class(col_data)[1], na_rate = na_rate, analysis = analysis)
      }
      list(series_metadata = list(series_name = series_name, status = "Success", file_analyzed = file_analyzed, rows_in_original_file = rows_original, rows_sampled_for_analysis = rows_sampled, columns = ncol(df)), variable_analysis = unname(variable_analysis))
    }, error = function(e) {
      list(series_metadata = list(series_name = series_name, status = "Worker Error", message = gsub("\n", " ", e$message)))
    })
  }
  stopCluster(cl); log_message("Parallel analysis complete.")
  
  # --- Sub-Phase 3.3: Merge New Results and Save Checkpoints ---
  log_message("Merging new results and saving checkpoints...")
  if (is.null(full_analysis_list)) { full_analysis_list <- list() }
  for (result in newly_analyzed_list) {
    if (!is.null(result$series_metadata$series_name)) {
      full_analysis_list[[result$series_metadata$series_name]] <- result
    }
  }
  
  saveRDS(full_analysis_list, file = rdata_checkpoint_path)
  names(full_analysis_list) <- sapply(full_analysis_list, function(x) x$series_metadata$series_name)
  write(toJSON(full_analysis_list, pretty = TRUE, auto_unbox = TRUE, na = "string"), json_checkpoint_path)
  log_message("Checkpoints saved successfully.")
}
analysis_results_list <- full_analysis_list

# ==============================================================================
# PHASE 4: FINAL REPORT GENERATION
# ==============================================================================
log_message("Assembling final Markdown report.")

# --- Sub-Phase 4.1: Generate Aggregate Summary Table ---
log_message("Generating high-level aggregate summary data...")
aggregate_summary_df <- bind_rows(lapply(analysis_results_list, function(result) {
  series_name <- result$series_metadata$series_name
  catalog_info <- catalog[[series_name]]
  
  status <- result$series_metadata$status
  variables <- NA; original_rows <- NA; global_na_rate <- "N/A"
  
  if (status == "Success") {
    variables <- result$series_metadata$columns
    original_rows <- result$series_metadata$rows_in_original_file
    if (length(result$variable_analysis) > 0) {
      na_percents <- as.numeric(sub("%", "", sapply(result$variable_analysis, function(v) v$na_rate)))
      total_na <- sum(na_percents / 100 * original_rows, na.rm = TRUE)
      total_cells <- variables * original_rows
      global_na_rate <- if (total_cells > 0) paste0(format(round((total_na / total_cells) * 100, 2), nsmall = 2), "%") else "N/A"
    }
  }
  
  tibble(
    `Series` = series_name,
    `Time Range` = catalog_info$time_range_str,
    `Partition` = catalog_info$partition_type,
    `File Count` = catalog_info$file_count,
    `Variables` = variables,
    `Original Rows` = original_rows,
    `Global NA%` = global_na_rate,
    `Status` = status
  )
}))

# --- Sub-Phase 4.2: Assemble Full Markdown Report ---
report_header <- paste(
  "# DATASUS Data Series Analysis Report\n\n",
  "## Aggregate Summary\n\n",
  "This table provides a high-level overview of all discovered data series, combining file discovery metadata with results from the direct data analysis.\n\n",
  paste(capture.output(print(kable(aggregate_summary_df, format = "pipe"))), collapse = "\n"),
  "\n\n## Detailed Variable Analysis\n\n",
  "The following sections provide a variable-by-variable breakdown for each successfully analyzed data series.\n"
)

detailed_blocks <- lapply(analysis_results_list, function(result) {
  tryCatch({
    if (is.null(result$series_metadata) || is.null(result$series_metadata$series_name)) return(NULL)
    series_name <- result$series_metadata$series_name
    header <- paste0("\n\n--------------------------------------------------\n",
                     "### Data Series: ", series_name, "\n",
                     "--------------------------------------------------\n")
    
    if (result$series_metadata$status != "Success") {
      body <- paste0("**Status:** ❌ `", result$series_metadata$status, "`\n\n> **Message:** ", result$series_metadata$message, "\n")
      return(paste0(header, body))
    }
    
    body <- paste0("**Status:** ✅ `Success`\n\n",
                   "- **Analyzed File:** '", result$series_metadata$file_analyzed, "'\n",
                   "- **File Dimensions:** ", result$series_metadata$rows_in_original_file, " rows x ", result$series_metadata$columns, " columns\n",
                   "- **Rows Sampled for Analysis:** ", result$series_metadata$rows_sampled_for_analysis, "\n\n")
    
    if (is.null(result$variable_analysis) || length(result$variable_analysis) == 0) return(paste0(header, body, "*No variables were found to report.*"))
    
    summary_df <- bind_rows(lapply(result$variable_analysis, function(v) {
      analysis_str <- ""
      if (v$analysis$type == "categorical") { freqs <- paste0(names(v$analysis$frequencies), ":", v$analysis$frequencies, collapse = "; "); analysis_str <- paste("Categorical (", v$analysis$unique_values, " unique): ", freqs) } 
      else if (v$analysis$type %in% c("continuous_numeric", "date")) { stats <- paste0("Min:", v$analysis$summary_stats$min, ", Med:", v$analysis$summary_stats$median, ", Max:", v$analysis$summary_stats$max); analysis_str <- paste("Continuous. ", stats) } 
      else { samples <- paste(v$analysis$sample_values, collapse = ", "); analysis_str <- paste("High Cardinality. Samples: ", samples) }
      tibble(`Variable Name` = v$variable_name, `NA %` = v$na_rate, `Type` = v$data_type, `Analysis / Samples` = analysis_str)
    }))
    
    table_text <- capture.output(print(kable(summary_df, format = "pipe")))
    return(paste(header, body, paste(table_text, collapse = "\n"), sep = "\n"))
  }, error = function(e) {
    series_name <- if (!is.null(result$series_metadata$series_name)) result$series_metadata$series_name else "Unknown"
    header <- paste0("\n\n--------------------------------------------------\n", "### Data Series: ", series_name, "\n", "--------------------------------------------------\n")
    return(paste0(header, "❌ **Error generating report table for this series:** ", e$message))
  })
})

# Combine and write the final report to a file
final_report_content <- c(report_header, unlist(detailed_blocks))
writeLines(final_report_content, md_report_path)
log_message(paste("Markdown report successfully saved to", md_report_path))


# ==============================================================================
# PHASE 5: FINAL EXECUTION SUMMARY
# ==============================================================================
success_count <- sum(sapply(analysis_results_list, function(x) x$series_metadata$status == "Success"))
fail_count <- length(analysis_results_list) - success_count
log_message("---------- EXECUTION SUMMARY ----------", level = "INFO")
log_message(paste("Total Series in Catalog:", length(all_series_names)), level = "INFO")
log_message(paste("Total Series with Analysis Results:", length(analysis_results_list)), level = "INFO")
log_message(paste("✅ Successful:", success_count), level = "INFO")
log_message(paste("❌ Failed/Errored:", fail_count), level = "INFO")
if (fail_count > 0) {
  failed_names <- names(analysis_results_list)[sapply(analysis_results_list, function(x) x$series_metadata$status != "Success")]
  log_message(paste("Failed Series:", paste(failed_names, collapse = ", ")), level = "WARN")
}
log_message("---------------------------------------", level = "INFO")
log_message("END OF SCRIPT", level = "INFO")

cat("\n\n==========================================================================")
cat("\n                             END OF SCRIPT")
cat("\n==========================================================================\n")