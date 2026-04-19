# ==============================================================================
# SCRIPT: 02_exploratory_analysis_v3_final.R
#
# PURPOSE: Implements a hierarchical, context-aware exploratory analysis. It
#          first clusters datasets into families, then analyzes variable
#          relationships within each family to find meaningful semantic groups.
#
# FINAL FRAMEWORK:
# 1. Dataset Clustering: Identifies families of datasets with similar schemas.
# 2. Context-Aware Variable Clustering: Iterates through each dataset family
#    to find high-confidence variable clusters using multiple signals.
# 3. Integrated Reporting: Generates a report structured around this
#    hierarchical analysis, presenting dataset families first, then the
#    specific variable clusters found within them.
# ==============================================================================


# ==============================================================================
# PHASE 0: SETUP & CONFIGURATION
# ==============================================================================

# --- Install and load all necessary packages quietly ---
packages <- c("jsonlite", "dplyr", "igraph", "knitr", "stringdist", "pheatmap")
install_if_missing <- function(p) {
  if (!require(p, character.only = TRUE)) {
    install.packages(p, dependencies = TRUE)
  }
}
invisible(sapply(packages, install_if_missing))

suppressPackageStartupMessages({
  library(jsonlite); library(dplyr); library(igraph);
  library(knitr); library(stringdist); library(pheatmap)
})
cat("✅ All required packages are loaded.\n")


# --- Configuration ---
INPUT_JSON_PATH <- "datasus_analysis.json"
REPORT_PATH <- "exploratory_analysis_final_report.md"
DATASET_SIMILARITY_PLOT_PATH <- "dataset_similarity_heatmap.png"

# Analysis Parameters
# Threshold for cutting the dataset dendrogram into distinct clusters
DATASET_CLUSTER_CUTOFF <- 0.8 # (1 - similarity threshold)
# Thresholds for the multi-signal variable clustering
CLUSTER_NAME_SIM_THRESHOLD <- 0.85
CLUSTER_VALUE_SIM_THRESHOLD <- 0.60


# --- Helper Functions ---
start_timer <- function(phase_name) { cat(paste0("\nPHASE ", phase_name, ": Starting...\n")); proc.time() }
end_timer <- function(start_time, phase_name) {
  elapsed <- proc.time() - start_time
  cat(paste0("✅ PHASE ", phase_name, ": Complete. (", format(round(elapsed[3], 2), nsmall = 2), " seconds)\n"))
}


# ==============================================================================
# PHASE 1: LOAD JSON AND CREATE MASTER VARIABLE PROFILES
# ==============================================================================
pt <- start_timer("1: Data Loading & Master Profile Generation")

if (!file.exists(INPUT_JSON_PATH)) stop("❌ CRITICAL ERROR: 'datasus_analysis.json' not found.")
analysis_data <- fromJSON(INPUT_JSON_PATH, simplifyVector = FALSE)

master_profiles <- list()
for (series_name in names(analysis_data)) {
  series <- analysis_data[[series_name]]
  if (series$series_metadata$status == "Success" && length(series$variable_analysis) > 0) {
    for (var_instance in series$variable_analysis) {
      var_name <- var_instance$variable_name
      if (is.null(master_profiles[[var_name]])) {
        master_profiles[[var_name]] <- list(
          name = var_name, appears_in_series = c(), value_space = c()
        )
      }
      master_profiles[[var_name]]$appears_in_series <- union(master_profiles[[var_name]]$appears_in_series, series_name)
      if (!is.null(var_instance$analysis$frequencies)) {
        master_profiles[[var_name]]$value_space <- union(master_profiles[[var_name]]$value_space, names(var_instance$analysis$frequencies))
      }
    }
  }
}
end_timer(pt, "1: Data Loading & Master Profile Generation")


# ==============================================================================
# PHASE 2: DATASET SCHEMA CLUSTERING
# ==============================================================================
pt <- start_timer("2: Dataset Schema Similarity Analysis & Clustering")

dataset_names <- names(analysis_data)
n_datasets <- length(dataset_names)

# Correctly extract variable names for each dataset
dataset_vars <- sapply(analysis_data, function(d) {
  if (!is.null(d$variable_analysis) && length(d$variable_analysis) > 0) {
    sapply(d$variable_analysis, function(v) v$variable_name)
  } else {
    character(0) # Handle failed datasets
  }
}, simplify = FALSE)

dataset_sim_matrix <- matrix(0, nrow = n_datasets, ncol = n_datasets, dimnames = list(dataset_names, dataset_names))
jaccard_index_sets <- function(s1, s2) {
  union_size <- length(union(s1, s2))
  if (union_size == 0) return(0) else return(length(intersect(s1, s2)) / union_size)
}

for (i in 1:n_datasets) {
  for (j in i:n_datasets) {
    sim <- jaccard_index_sets(dataset_vars[[i]], dataset_vars[[j]])
    dataset_sim_matrix[i, j] <- dataset_sim_matrix[j, i] <- sim
  }
}

# --- Formal Clustering and Heatmap Generation ---
if(n_datasets > 1) {
  dist_matrix <- as.dist(1 - dataset_sim_matrix)
  hclust_result <- hclust(dist_matrix, method = "complete")
  
  # Formally define clusters by cutting the dendrogram
  dataset_clusters_id <- cutree(hclust_result, h = DATASET_CLUSTER_CUTOFF)
  
  # Create a summary table of the dataset clusters
  dataset_cluster_summary <- tibble(
    Dataset = names(dataset_clusters_id),
    Cluster_ID = dataset_clusters_id
  ) %>%
    group_by(Cluster_ID) %>%
    summarise(
      Cluster_Size = n(),
      Member_Datasets = paste(Dataset, collapse = ", ")
    ) %>%
    arrange(desc(Cluster_Size), Cluster_ID)
  
  png(DATASET_SIMILARITY_PLOT_PATH, width = 2400, height = 2400, res = 200)
  pheatmap(dataset_sim_matrix,
           main = "Heatmap of Dataset Schema Similarity (Jaccard Index of Variable Sets)",
           clustering_distance_rows = dist_matrix,
           clustering_distance_cols = dist_matrix,
           border_color = "grey60",
           fontsize_row = 5, fontsize_col = 5)
  dev.off()
}
end_timer(pt, "2: Dataset Schema Similarity Analysis & Clustering")


# ==============================================================================
# PHASE 3: CONTEXT-AWARE VARIABLE CLUSTERING
# ==============================================================================
pt <- start_timer("3: Context-Aware Variable Clustering")

# Create a list of dataset families from the clustering result
dataset_families <- split(names(dataset_clusters_id), dataset_clusters_id)
final_semantic_clusters <- list()

cat(" -> Analyzing variables within each dataset family...\n")
for (family_id in names(dataset_families)) {
  family_datasets <- dataset_families[[family_id]]
  
  # Skip families with only one dataset
  if (length(family_datasets) < 2) next
  
  # Isolate variables that appear only within this family
  family_vars_names <- names(which(sapply(master_profiles, function(p) {
    any(p$appears_in_series %in% family_datasets)
  })))
  
  if (length(family_vars_names) < 2) next
  
  local_profiles <- master_profiles[family_vars_names]
  n_local <- length(local_profiles)
  
  # --- Build Local Similarity Matrices ---
  name_sim <- matrix(0, n_local, n_local)
  value_sim <- matrix(0, n_local, n_local)
  
  for (i in 1:n_local) {
    for (j in (i+1):n_local) {
      if (j > n_local) next
      
      p1 <- local_profiles[[i]]
      p2 <- local_profiles[[j]]
      
      # Enforce the core rule: no common datasets
      if (length(intersect(p1$appears_in_series, p2$appears_in_series)) == 0) {
        name_sim[i, j] <- stringsim(p1$name, p2$name, method = "jw")
        value_sim[i, j] <- jaccard_index_sets(p1$value_space, p2$value_space)
      }
    }
  }
  
  # --- Fuse Signals and Build High-Confidence Graph ---
  fused_sim <- name_sim * value_sim # Element-wise product
  
  # Create a graph where an edge exists only if it meets both thresholds
  high_confidence_matrix <- (name_sim > CLUSTER_NAME_SIM_THRESHOLD) & (value_sim > CLUSTER_VALUE_SIM_THRESHOLD)
  
  g_local <- graph_from_adjacency_matrix(high_confidence_matrix, mode = "undirected", diag = FALSE)
  V(g_local)$name <- names(local_profiles)
  g_local <- delete_vertices(g_local, which(degree(g_local) == 0))
  
  if (vcount(g_local) == 0) next
  
  # --- Detect Communities in the High-Confidence Graph ---
  local_clusters <- cluster_walktrap(g_local)
  
  # --- Format results for this family ---
  family_cluster_summary <- tibble(
    Local_Cluster_ID = membership(local_clusters),
    Variable = names(membership(local_clusters))
  ) %>%
    group_by(Local_Cluster_ID) %>%
    summarise(
      Cluster_Size = n(),
      Members = paste(Variable, collapse = ", ")
    ) %>%
    filter(Cluster_Size > 1) %>%
    arrange(desc(Cluster_Size)) %>%
    mutate(
      Family_ID = family_id,
      Family_Datasets = paste(family_datasets, collapse = ", ")
    )
  
  if(nrow(family_cluster_summary) > 0) {
    final_semantic_clusters[[family_id]] <- family_cluster_summary
  }
}

end_timer(pt, "3: Context-Aware Variable Clustering")


# ==============================================================================
# PHASE 4: ASSEMBLE FINAL OVERHAULED REPORT
# ==============================================================================
pt <- start_timer("4: Final Report Assembly")

report_content <- c(
  "# Hierarchical Exploratory Analysis Report\n\n",
  "## 1. Introduction\n\n",
  "This report presents a hierarchical analysis of the DATASUS corpus. It first identifies 'families' of datasets with similar schemas and then explores the semantic relationships between variables *within* each of these contexts. This context-aware approach avoids the noise of global comparisons and reveals more meaningful structural and semantic patterns.\n\n",
  "---\n\n",
  "## 2. Dataset Family Analysis\n\n",
  "Datasets were clustered based on the Jaccard similarity of their variable sets. The heatmap visualizes these relationships, while the table below lists the formal clusters or 'families' that were identified.\n\n",
  "### Dataset Schema Similarity Heatmap\n\n",
  paste0("![Dataset Similarity Heatmap](", basename(DATASET_SIMILARITY_PLOT_PATH), ")\n\n"),
  "### Identified Dataset Families\n\n",
  paste(kable(dataset_cluster_summary, format = "pipe"), collapse = "\n"),
  "\n\n---\n\n",
  "## 3. Context-Aware Semantic Variable Clusters\n\n",
  "The following sections detail the semantic variable clusters found within each major dataset family. A cluster is only formed if member variables have **both high name similarity and high value-set similarity**, ensuring the groups are conceptually coherent.\n\n"
)

# Append the results for each dataset family
if (length(final_semantic_clusters) > 0) {
  for (family_id in names(final_semantic_clusters)) {
    family_summary <- final_semantic_clusters[[family_id]]
    family_name_str <- family_summary$Family_Datasets[1]
    
    report_content <- c(report_content,
                        paste0("\n### Family ID: ", family_id, " (`", family_name_str, "`)\n"),
                        paste(kable(family_summary %>% select(-Family_ID, -Family_Datasets), format = "pipe"), collapse = "\n")
    )
  }
} else {
  report_content <- c(report_content, "*No significant semantic variable clusters were found using the multi-signal criteria.*")
}

writeLines(report_content, REPORT_PATH)
end_timer(pt, "4: Final Report Assembly")

cat("\n\n==========================================================================")
cat("\n                    ✅ DEFINITIVE ANALYSIS COMPLETE")
cat("\n==========================================================================\n")