# PegaSUS Data Module Plan

Version: 2026-04-03  
Status: Working implementation plan  
Primary scope: DATASUS + SIDRA data substrate for PegaSUS

---

## 1. Purpose of this document

This document formalizes the implementation plan for the **data module** that will serve the PegaSUS project.

It is meant to be a durable engineering reference for:

- how source discovery should work,
- how raw assets should be fetched and versioned,
- how DATASUS and SIDRA should be normalized into one shared substrate,
- what logic from earlier projects should be preserved,
- how to structure the implementation order,
- and what proof-of-concepts must be built before any higher-order graph/scanner layer is attempted.

This document does **not** specify the final statistical graph engine. It specifies the layer that must exist before that engine is even worth implementing.

---

## 2. Project objective in operational terms

PegaSUS is not supposed to begin as a giant municipality-year warehouse and it should not begin as a graph engine.

The first implementation goal is a **lawful source and compilation substrate** that can:

1. discover and catalog DATASUS and SIDRA source assets,
2. fetch raw source material reproducibly,
3. parse source-specific raw assets,
4. normalize them into canonical records or canonical aggregate observables,
5. register support roles and code roles explicitly,
6. compile lawful epidemiological observables,
7. align them on a common support lattice,
8. preserve provenance and uncertainty information.

The data module therefore has to support two source regimes:

- **DATASUS**: raw files, source-specific registries, weak formal API surface, FTP/transfer-based distribution, heterogeneous schemas.
- **SIDRA**: native aggregate source with explicit metadata structure and formal API endpoints.

---

## 3. Why the old Python FTP crawler was much slower than FileZilla

### 3.1 The main reason is not “Python is slow”

The dominant issue is almost certainly **protocol shape and round-trip count**, not raw language speed.

FTP is unusual because directory listings and file transfers do not happen on the main control connection alone. A separate **data connection** is used for listings and transfers. In passive mode, the client requests an address via `PASV`, then opens a secondary connection for the listing or transfer. This means directory discovery is much more expensive than a simple HTTP metadata request. Every listing operation is comparatively heavyweight. FileZilla documents this explicitly: FTP uses a control connection plus a separate data connection for each listing or file transfer. Python’s `ftplib` documentation also distinguishes `NLST`, `LIST`, and `MLSD`, with `MLSD` being the better structured API when supported. [References: Python `ftplib` docs; FileZilla network documentation]

### 3.2 What the old crawler actually did

The earlier crawler, as recovered from the notebook export, had the following shape:

1. one FTP login per worker,
2. a recursive scan rooted at `/dissemin/publicos/`,
3. `ftp.nlst(path)` for each directory,
4. then, for **every returned item**, an attempted `ftp.cwd(item_name)` just to test whether that item is a directory,
5. recursion into directories, followed by `ftp.cwd(path)` to backtrack,
6. and repeated this process for many top-level systems using a `ThreadPoolExecutor(max_workers=200)`.

That is a very expensive traversal pattern.

### 3.3 The specific performance pathologies in the old crawler

#### 3.3.1 `NLST` gives names only, so you compensated by probing every entry with `CWD`

Your crawler calls `ftp.nlst(path)` and gets only file names. It does not get reliable structured entry type metadata.

Because of that, it then tries:

- `ftp.cwd(item_name)` to see whether the item is a directory,
- and catches `ftplib.error_perm` to decide it is actually a file.

That means **every entry** potentially costs at least one extra FTP command, often more once recursion and backtracking are counted.

This is the single biggest design flaw in the crawler.

At scale, this produces a brutal multiplication of round-trips:

- one listing request for the directory,
- plus one `CWD` probe for each child entry,
- plus one “go back” `CWD` after each recursive descent.

On a huge tree, that becomes catastrophic.

#### 3.3.2 Recursive `cwd` backtracking adds more control-plane chatter

The function does:

- `ftp.cwd(item_name)` to enter,
- recurse,
- then `ftp.cwd(path)` to go back.

That is another round-trip on every recursive branch. It also makes the crawler sensitive to path handling inconsistencies.

#### 3.3.3 You opened too many sessions at once

The crawler used `MAX_WORKERS = 200`, with one FTP connection per worker.

That sounds aggressive, but for FTP it is often self-defeating. Too many simultaneous connections can trigger:

- server-side throttling,
- connection limits,
- passive port exhaustion,
- connection churn,
- socket setup overhead,
- increased timeout/retry behavior,
- and general loss of efficiency.

FileZilla’s documentation and wiki both emphasize simultaneous transfer/connection limits, and explicitly note that some servers restrict connection counts and may require connection limiting. In other words, “more workers” is not automatically “faster FTP” and may become slower. [References: FileZilla simultaneous transfer and connection-limit documentation]

#### 3.3.4 Thread scheduling was not aligned with the real bottleneck

Your bottleneck was mostly I/O latency and FTP command churn, not CPU. A huge Python thread pool does not remove protocol round-trips. It mainly adds:

- more socket churn,
- more login churn,
- more context switching,
- more contention,
- and more server stress.

So the worker count was large, but the traversal strategy remained intrinsically expensive.

#### 3.3.5 One worker per top-level system creates load imbalance

The code assigns one entire top-level system to each thread. Some trees are shallow and small; others are deep and large. That creates work imbalance:

- some threads finish quickly,
- some threads become long-lived stragglers,
- and overall completion time is dragged by a few heavy system trees.

#### 3.3.6 Logging and notebook-style execution add friction

The recovered notebook code prints a lot and was clearly exploratory. Logging is not the core issue, but in notebook execution it still adds noise and overhead, especially with many workers.

### 3.4 Why FileZilla was probably much faster

FileZilla likely outperformed the Python crawler for a combination of reasons:

#### 3.4.1 It is likely using a better listing primitive and/or better parsing strategy

If the server supports `MLSD`, that is preferable because it returns structured facts such as entry type. Python’s `ftplib` docs explicitly say `mlsd()` offers a better API than `nlst()` or `dir()` when supported. If a client can determine type from the listing itself, it avoids your `cwd()`-per-entry probe pattern. [Reference: Python `ftplib` docs]

#### 3.4.2 It likely uses optimized connection management

FileZilla is a mature native client. Even without assuming any hidden magic, it is reasonable to expect:

- better session reuse,
- tighter event-loop behavior,
- lower per-operation overhead,
- less wasteful probing,
- and more disciplined concurrency.

#### 3.4.3 It is not structured like your crawler

Your crawler was built to answer a specific research question: “find PDFs and a representative DBC per system/state while traversing everything.” That imposed a recursive path-testing approach.

FileZilla’s goal is general-purpose remote browsing and transfer. A mature browser can optimize listing, caching, and interaction differently.

#### 3.4.4 Native code is not the main reason, but it still helps

The gap is mostly from traversal strategy, not just C++ versus Python. But once protocol design is fixed, native implementation does still help with:

- lower memory overhead,
- tighter socket/event handling,
- and lower overhead per command.

### 3.5 Could we build an internal scanner that approaches FileZilla speed?

**Yes, probably.**

**Exact parity is not guaranteed**, because we do not know the exact listing behavior that FileZilla used against DATASUS at the time you scanned it. But we can very likely get **close enough** for engineering purposes if we stop doing the pathological parts of the old crawler.

### 3.6 What would be required to approach FileZilla speed

#### 3.6.1 Use `MLSD` if the server supports it

This is the first thing to test.

If `ftp.datasus.gov.br` supports `MLSD`, use it. It returns structured facts and, critically, can identify entry type without probing each child via `cwd()`.

That removes the worst part of the old design.

#### 3.6.2 Never detect directories by attempting `cwd()` on every child

This should be treated as forbidden except as a rare fallback.

If `MLSD` is not available, parse `LIST` output instead and only fall back to active probing when parsing is ambiguous.

#### 3.6.3 Use bounded concurrency, not 200 connections

Start with a small tested range such as:

- 4,
- 8,
- 12,
- 16,

and benchmark.

FTP often degrades once you exceed the server’s comfort zone.

#### 3.6.4 Use a queue-based breadth-first scheduler, not one thread per top-level system

Maintain a queue of directories to scan and let a small connection pool consume from that queue.

Advantages:

- better work balancing,
- easier checkpointing,
- easier backoff handling,
- easier resumability.

#### 3.6.5 Separate “enumeration” from “analysis”

Do not do PDF scoring, series validation, or semantic grouping while walking the FTP tree.

Fast scanning should do only one job:

- emit a manifest of discovered paths and basic facts.

All higher-order logic should happen offline against the manifest.

#### 3.6.6 Stream output incrementally

Write discovered entries to:

- JSONL,
- CSV,
- or Parquet,

as they are found.

Do not hold the entire crawl in memory before saving.

#### 3.6.7 Make the scanner resumable

Checkpoint:

- scanned directories,
- pending directories,
- failures,
- retry counts,
- and final entry rows.

This matters more than shaving a few seconds.

### 3.7 The realistic recommendation

There are two different needs here:

1. **One-time or occasional full-server discovery**
2. **Stable, reproducible data engineering**

For (1), an optimized scanner is useful.
For (2), the right artifact is still the **manifest**.

So the engineering recommendation is:

- keep a high-performance scanner as an optional utility,
- but make the **manifest** the canonical input for catalog building,
- because the manifest is reproducible, diffable, inspectable, and much cheaper to reuse.

In other words: even if we build a faster scanner, the output that enters the PegaSUS data module should still be the manifest.

---

## 4. Formal decision on DATASUS discovery strategy

### 4.1 Canonical discovery artifact

The canonical discovery artifact for DATASUS will be a **manifest file** containing the discovered FTP path scaffold.

Accepted input forms:

- FileZilla export text file,
- internal optimized crawler output,
- concatenated FTP URL lists,
- or normalized JSONL produced by our own discovery utility.

### 4.2 Why the manifest must be canonical

Because it is:

- reproducible,
- diffable across scans,
- versionable in git/LFS/object storage,
- much faster to re-analyze than rescanning FTP,
- independent of transient connection problems,
- and suitable for downstream catalog inference.

### 4.3 What the scanner becomes

The scanner becomes a **manifest producer**, not the thing downstream code depends on.

That distinction is important.

---

## 5. Summary of logic to preserve from the earlier projects

### 5.1 DATASUS logic worth preserving

The following logic from the notebook export should be preserved and rewritten cleanly:

1. **Manifest parsing** from the endpoint text dump.
2. **Filename pattern parsing** into `series_prefix`, `geo_code`, `date_code`.
3. **Primary vs auxiliary path detection**.
4. **Exclusion rules** such as `/IBGE/`.
5. **Relational validation by directory cardinality**.
6. **Series consolidation** by prefix after validation.
7. **Partition typing**:
   - `Nation-Wide`
   - `State-Partitioned`
   - `Mixed-Partition`
8. **Date-format inference** (`YY`, `YYMM`, possible `YYYY` fallback).
9. **Path semantics inference**:
   - primary,
   - staging,
   - legacy archive.
10. **PDF association scoring** using:
    - tree distance,
    - fuzzy filename/path similarity,
    - keyword bonuses.
11. **System grouping** by path context.
12. **JSON catalog output**.

### 5.2 DATASUS logic not worth preserving as the main path

The following should **not** remain the main operational method:

1. live recursive FTP traversal as the default discovery source,
2. `cwd()`-per-entry probing,
3. one giant thread pool with 200 connections,
4. notebook-oriented execution flow.

### 5.3 SIDRA logic worth preserving

The SIDRA project contains strong reusable logic in these areas:

1. local metadata warehouse schema,
2. metadata ingestion for tables, variables, classifications, categories, periods, and localities,
3. territorial coverage probing and indexing,
4. normalized search keys,
5. search link tables,
6. FTS title indexing,
7. optional title embeddings via LM Studio-compatible endpoints,
8. unified boolean search grammar.

### 5.4 SIDRA logic that still needs new work

The major missing piece is a **value retrieval and normalization layer** for actual aggregate values.

The existing project is much stronger at:

- finding tables,
- cataloging metadata,
- and indexing them,

than at producing PegaSUS-ready numerical observables.

---

## 6. Target architecture of the PegaSUS data module

The data module will be divided into the following top-level subsystems.

### 6.1 `discovery`

Purpose:

- discover and catalog source assets before parsing them.

Submodules:

- `datasus.discovery.manifest`
- `datasus.discovery.scanner`
- `datasus.discovery.catalog`
- `datasus.discovery.docs`
- `sidra.catalog.ingest`
- `sidra.catalog.search`

### 6.2 `acquisition`

Purpose:

- fetch and version raw artifacts.

Submodules:

- `datasus.fetch`
- `sidra.fetch`
- `common.provenance`
- `common.storage`

### 6.3 `parsing`

Purpose:

- parse source-specific raw material into source-normalized rows.

Submodules:

- `datasus.parsers.sinasc`
- `datasus.parsers.sim`
- `datasus.parsers.sinan`
- `datasus.parsers.sih`
- `sidra.values`

### 6.4 `canonicalization`

Purpose:

- map source-normalized records into the canonical PegaSUS record model.

Submodules:

- `pegasus.canonical.schema`
- `pegasus.canonical.mapper`
- `pegasus.canonical.validators`

### 6.5 `registries`

Purpose:

- define reusable semantic infrastructure.

Submodules:

- `pegasus.registry.codes`
- `pegasus.registry.support`
- `pegasus.registry.sources`
- `pegasus.registry.fields`

### 6.6 `compiler`

Purpose:

- compile canonical records and native aggregates into typed observables.

Submodules:

- `pegasus.compiler.counts`
- `pegasus.compiler.thresholds`
- `pegasus.compiler.rates`
- `pegasus.compiler.annotations`
- `pegasus.compiler.lineage`
- `pegasus.compiler.uncertainty`

### 6.7 `llm_assist`

Purpose:

- use local LLM inference to accelerate manual semantic work, without making it authoritative.

Submodules:

- `assist.field_role_suggester`
- `assist.pdf_summarizer`
- `assist.sidra_table_ranker`
- `assist.mapping_draft_generator`

---

## 7. Repository layout

The recommended repository layout is:

```text
pegasus_data/
  pyproject.toml
  README.md
  src/
    pegasus_data/
      config/
      common/
        io.py
        hashing.py
        provenance.py
        logging.py
        storage.py
        retry.py
      datasus/
        discovery/
          manifest.py
          scanner.py
          catalog.py
          docs.py
          heuristics.py
        fetch/
          downloader.py
          planner.py
        parsers/
          sinasc.py
          sim.py
          sinan.py
          sih.py
        mappings/
          source_registry.py
          field_registry.py
      sidra/
        catalog/
          ingest.py
          search.py
          links.py
          coverage.py
        fetch/
          api.py
          cache.py
        values/
          loader.py
          normalize.py
        mappings/
          table_registry.py
      pegasus/
        canonical/
          schema.py
          mapper.py
          validators.py
        registry/
          codes.py
          support.py
          sources.py
          fields.py
        compiler/
          counts.py
          thresholds.py
          annotations.py
          rates.py
          lineage.py
          uncertainty.py
      assist/
        lmstudio.py
        prompts.py
        ranking.py
  tests/
  docs/
```

---

## 8. Core data contracts

### 8.1 Contract A: DATASUS manifest row

Every line discovered in DATASUS discovery must normalize to a row like:

```json
{
  "path": "/dissemin/publicos/SINASC/.../DNAL2023.dbc",
  "url": "ftp://ftp.datasus.gov.br/dissemin/publicos/...",
  "directory": "/dissemin/publicos/SINASC/...",
  "filename": "DNAL2023.dbc",
  "extension": ".dbc",
  "path_components": ["dissemin", "publicos", "SINASC", "..."],
  "source": "datasus_ftp",
  "scan_id": "2026-04-03T...",
  "path_type": "Primary",
  "pattern_name": "PREFIX_GEO_YYMM",
  "series_prefix": "DN",
  "geo_code": "AL",
  "date_code": "2023",
  "raw_listing_facts": null
}
```

### 8.2 Contract B: DATASUS series catalog row

```json
{
  "series_id": "SINASC:DN",
  "series_prefix": "DN",
  "system_guess": "SINASC",
  "partition_type": "State-Partitioned",
  "date_format": "YYMM",
  "time_range_raw": ["9801", "2412"],
  "time_range_display": "Jan 1998 to Dec 2024",
  "geo_coverage": ["AC", "AL", "AM", "..."],
  "file_count": 1234,
  "source_paths": ["/dissemin/publicos/SINASC/..."],
  "path_semantics": {
    "/dissemin/publicos/SINASC/...": "[Primary]"
  },
  "associated_pdfs": [
    {"url": "ftp://.../layout.pdf", "score": 88}
  ],
  "validated_pattern": "PREFIX_GEO_YYMM"
}
```

### 8.3 Contract C: source-normalized raw record

This is not yet canonical. It is source-specific but standardized enough for mapping.

```json
{
  "source": "SINASC",
  "dataset": "DN",
  "raw_file": ".../DNAL2412.dbc",
  "row_number": 12345,
  "fields": {
    "CODMUNNASC": "2704302",
    "DTNASC": "2024-12-03",
    "SEXO": "1",
    "PESO": "3120",
    "APGAR1": "8",
    "APGAR5": "9",
    "CODANOMAL1": "Q039",
    "CODANOMAL2": null
  },
  "parse_warnings": [],
  "encoding": "latin1",
  "schema_version": "sinasc_v1"
}
```

### 8.4 Contract D: canonical PegaSUS record

```json
{
  "support": {
    "municipality": "2704302",
    "year": 2024,
    "month": 12,
    "date": "2024-12-03"
  },
  "support_role": "birth_occurrence",
  "source": {
    "system": "SINASC",
    "dataset": "DN",
    "file": "DNAL2412.dbc"
  },
  "event_type": "birth",
  "code_roles": {
    "anomaly": ["Q039"]
  },
  "subgroups": {
    "sex": "male"
  },
  "continuous": {
    "birth_weight_g": 3120,
    "apgar_1m": 8,
    "apgar_5m": 9
  },
  "annotations": {
    "anomaly_slots": ["Q039"]
  },
  "weight": 1.0,
  "quality": {
    "included": true,
    "flags": []
  },
  "provenance": {
    "row_number": 12345,
    "schema_version": "sinasc_v1"
  }
}
```

### 8.5 Contract E: compiled observable instance

```json
{
  "family": "birth_anomaly_count",
  "support_role": "birth_occurrence",
  "support_grain": ["municipality", "year"],
  "code_query": {
    "role": "anomaly",
    "system": "ICD10",
    "node": "Q00-Q07",
    "descendants": true
  },
  "partition": {
    "sex": ["male", "female"]
  },
  "measure": "count",
  "representation": "extensive",
  "values": [
    {"municipality": "2704302", "year": 2024, "sex": "male", "value": 12}
  ],
  "uncertainty": {
    "count_model": "poisson",
    "notes": []
  },
  "lineage": {
    "sources": ["SINASC:DN"],
    "compiler_version": "0.1.0"
  }
}
```

---

## 9. DATASUS discovery subsystem specification

### 9.1 Objectives

The DATASUS discovery subsystem must:

1. ingest a manifest or produce one,
2. identify likely data-bearing files,
3. recover latent series structure from file naming conventions,
4. classify territorial partitioning,
5. infer temporal coding style,
6. identify candidate documentation PDFs,
7. group series into likely source systems,
8. output a machine-readable catalog.

### 9.2 Input types

Supported inputs:

- plain text file with one FTP URL/path per line,
- JSONL manifest from internal scanner,
- CSV export with path column,
- future: direct crawl output stream.

### 9.3 Mandatory heuristics to preserve

#### 9.3.1 Filename pattern extraction

Required regex families:

- `PREFIX_GEO_YYMM`
- `PREFIX_GEO_YY`
- optional fallback `PREFIX_GEO_DATE`

#### 9.3.2 Exclusion filters

Must exclude known noise domains or irrelevant path families such as:

- `/IBGE/`

#### 9.3.3 Auxiliary-path labeling

Must label non-primary documentation/support directories using path keywords such as:

- `TABELAS`
- `DOCS`
- `DOCUMENTOS`
- `TABWIN`
- `DOC`

#### 9.3.4 Directory-level relational validation

A pattern match is not enough.

A directory should only be promoted into high-confidence series validation if it contains at least a minimum number of matching files.

Initial threshold:

- `MIN_FILES_FOR_PATTERN_VALIDATION = 5`

#### 9.3.5 Territorial partition validation

Initial state-partition validation threshold:

- `MIN_UF_COUNT_FOR_STATE_VALIDATION = 20`

Partition labels:

- `Nation-Wide`
- `State-Partitioned`
- `Mixed-Partition`
- `Unknown`

#### 9.3.6 Date-format inference

Must infer at least:

- `YY`
- `YYMM`
- fallback `Unknown`

Later enhancement:

- `YYYY`
- `YYYYMM`

#### 9.3.7 Path semantics inference

Must label:

- `[Primary]`
- `[Staging]`
- `[Legacy Archive]`

Initial heuristics:

- path keywords `PRELIM`, `HOMOL` => staging,
- paths lagging far behind series-global max date => legacy archive.

#### 9.3.8 PDF association scorer

The scorer must combine:

- tree-distance proximity,
- fuzzy similarity between series name and PDF filename,
- fuzzy similarity between series path context and PDF path context,
- keyword bonus for likely documentation names.

### 9.4 Outputs

The discovery subsystem must emit:

1. `manifest.parquet` or `manifest.jsonl`
2. `series_catalog.json`
3. `series_catalog.parquet`
4. `pdf_catalog.json`
5. `discovery_log.txt`

---

## 10. DATASUS fast scanner specification

### 10.1 Goal

Produce a server manifest fast enough that FileZilla is no longer the only practical option.

### 10.2 Non-goals

The scanner must **not**:

- do semantic series classification during traversal,
- do PDF scoring during traversal,
- download data files during traversal,
- infer final source semantics during traversal.

### 10.3 Required behavior

#### 10.3.1 Preferred listing order

1. Try `MLSD`
2. Fall back to `LIST`
3. Fall back to `NLST` only if necessary
4. Avoid `CWD`-per-entry probing except as last-resort disambiguation

#### 10.3.2 Concurrency model

Use:

- bounded connection pool,
- shared queue of directories,
- work stealing,
- checkpointing.

#### 10.3.3 Recommended initial tuning

- connections: 8
- retry count: 3
- exponential backoff: 1s, 2s, 4s
- timeout: 30s control / 60s data
- checkpoint interval: every 5,000 entries or 60 seconds

#### 10.3.4 Output row shape

Each discovered entry should record:

- parent directory,
- child name,
- full path,
- entry type if known,
- size if known,
- modified time if known,
- listing method (`MLSD`, `LIST`, `NLST`),
- scan timestamp,
- scan worker id,
- error flags if any.

### 10.4 Benchmark protocol

To determine whether the internal scanner is good enough:

1. pick a fixed subtree,
2. benchmark:
   - FileZilla export time,
   - internal scanner time with 4 connections,
   - internal scanner time with 8 connections,
   - internal scanner time with 12 connections,
3. compare:
   - total entries discovered,
   - elapsed time,
   - failures,
   - retries,
   - duplicate entries,
   - missing directories.

### 10.5 Acceptance threshold

The internal scanner is acceptable if:

- completeness >= FileZilla snapshot completeness,
- no unrecoverable structural errors,
- and wall-clock time is within an acceptable engineering factor.

A reasonable first target is:

- within **1.5x to 2.5x** of FileZilla on the same subtree.

If it achieves that, it is good enough for internal use.

---

## 11. DATASUS acquisition subsystem

### 11.1 Goals

- fetch raw files deterministically,
- version fetches,
- verify integrity,
- separate planning from execution.

### 11.2 Download planning

The downloader should consume catalog rows and allow filters such as:

- system = `SINASC`
- prefix in [`DN`]
- geo in [`AL`, `BA`, `MG`]
- year range
- file extension in `.dbc`, `.dbf`, `.csv`, `.zip`

### 11.3 Download storage layout

Recommended raw layout:

```text
raw/
  datasus/
    ftp/
      scan_id=2026-04-03/
        system=SINASC/
          prefix=DN/
            geo=AL/
              year=2024/
                DNAL2412.dbc
```

### 11.4 Provenance metadata

Each downloaded asset must have sidecar metadata:

```json
{
  "source": "datasus_ftp",
  "scan_id": "2026-04-03T...",
  "discovered_path": "/dissemin/publicos/.../DNAL2412.dbc",
  "downloaded_at": "2026-04-03T...",
  "size_bytes": 1234567,
  "sha256": "...",
  "transport": "ftp",
  "listing_method": "manifest",
  "etag": null,
  "notes": []
}
```

### 11.5 Downloader behavior

Must support:

- resume on partial failure,
- skip-if-hash-known,
- overwrite-on-hash-mismatch only with explicit flag,
- optional mirror mode,
- dry-run planning mode.

---

## 12. DATASUS parser subsystem

### 12.1 Principles

Each source system gets its own parser module. Do **not** attempt a universal parser.

### 12.2 Initial parser priority

1. `SINASC`
2. `SIM`
3. `SINAN`
4. `SIH`

### 12.3 Parser contract

Each parser must expose:

- `detect(files) -> bool`
- `load_metadata(files) -> SourceMetadata`
- `iter_rows(files) -> Iterator[SourceRow]`
- `normalize_row(raw) -> SourceNormalizedRow`
- `quality_checks(row) -> list[flag]`

### 12.4 Initial proof-of-concept parser target

Start with **SINASC** because it stress-tests:

- support-role explicitness,
- continuous variables,
- repeated anomaly slots,
- municipality/time normalization,
- and lawful threshold compilation.

---

## 13. SIDRA subsystem plan

### 13.1 Preserve existing strengths

The current SIDRA work already provides strong logic for:

- metadata ingestion,
- local warehousing,
- territorial coverage probing,
- normalized lexical search,
- embeddings-backed title ranking,
- and boolean retrieval over table metadata.

This should be preserved as the SIDRA catalog/search layer.

### 13.2 Add the missing value layer

The missing implementation is a dedicated value-fetch and normalization path.

Required functions:

- fetch table values by aggregate/period/variable/locality/classification,
- normalize value payloads,
- persist raw responses,
- emit typed aggregate rows,
- map those rows to canonical aggregate observables.

### 13.3 SIDRA storage layers

#### Layer A: catalog warehouse

Already mostly present.

Stores:

- aggregates,
- variables,
- classifications,
- categories,
- periods,
- localities,
- search links,
- FTS,
- embeddings.

#### Layer B: raw value cache

New.

Stores raw API response payloads keyed by request signature.

#### Layer C: normalized aggregate rows

New.

Stores value rows with standardized:

- table id,
- variable id,
- locality id,
- period id,
- classification/category selections,
- value,
- status flags.

#### Layer D: canonical aggregate observables

New.

Stores aggregate data ready for PegaSUS compilation/alignment.

---

## 14. Canonical schema plan

### 14.1 Required dimensions

The canonical schema must support the dimensions defined by the PegaSUS blueprint:

- support,
- support role,
- source identity,
- event/carrier type,
- code-role map,
- categorical subgroup attributes,
- continuous attributes,
- repeated annotations,
- quality state,
- weight,
- provenance.

### 14.2 Support roles

Initial controlled vocabulary:

- `residence`
- `occurrence`
- `notification_residence`
- `notification_occurrence`
- `hospitalization_occurrence`
- `death_occurrence`
- `birth_occurrence`
- `facility_location`

### 14.3 Event/carrier types

Initial controlled vocabulary:

- `notification`
- `hospitalization`
- `death`
- `birth`
- `facility`
- `procedure`
- `aggregate_context`

### 14.4 Code-role vocabulary

Initial controlled vocabulary:

- `condition`
- `diagnosis`
- `cause_of_death`
- `anomaly`
- `procedure`
- `secondary_diagnosis`
- `associated_cause`

### 14.5 Quality model

Each record must support:

- `included: bool`
- `flags: list[str]`
- `missingness_summary`
- `raw_parse_issues`

---

## 15. Registry plan

### 15.1 Source registry

Maps source systems to:

- source family,
- parser,
- support-role defaults,
- known code-bearing fields,
- known subgroup fields,
- known continuous fields,
- known annotation fields.

### 15.2 Code registry

Must support:

- code systems,
- code roles,
- code hierarchy edges,
- ancestor/descendant closure,
- source-role compatibility.

### 15.3 Support registry

Must support:

- municipality normalization,
- state derivation,
- date-to-month/year rollups,
- support-role compatibility,
- lawful alignment operators.

### 15.4 Field registry

Must support source-specific field semantics, for example:

- `SINASC.PESO -> continuous.birth_weight_g`
- `SIM.CAUSABAS -> code_roles.cause_of_death`
- `SINAN.AGRAVO -> code_roles.condition`

---

## 16. Observable compiler plan

### 16.1 Why this matters first

The compiler is the first true PegaSUS engine. It turns canonical data into lawful numerical objects.

### 16.2 Initial observable families to implement

#### 16.2.1 Count observables

Examples:

- births by municipality-year,
- deaths by municipality-year,
- notifications by municipality-year,
- hospitalizations by municipality-year.

#### 16.2.2 Code-query count observables

Examples:

- births with anomaly code under `Q00-Q07`,
- deaths with cause under `A50-A53`,
- notifications with condition under a disease family.

#### 16.2.3 Subgroup count observables

Examples:

- births by sex,
- notifications by age band,
- deaths by race/color.

#### 16.2.4 Threshold observables for continuous variables

Examples:

- birth weight < 2500g,
- Apgar at 5 minutes < 7,
- gestational age < 37 weeks.

#### 16.2.5 Simple rate observables

Examples:

- event count / population,
- birth outcome rate / live births,
- disease burden / denominator population.

### 16.3 Annotation-aware compilation

Repeated code slots must support existential semantics:

- “any descendant of node X appears in any anomaly slot”

They must **not** be compiled as if repeated slots were mutually exclusive categories.

### 16.4 Lineage and uncertainty

Each compiled observable must carry:

- compiler version,
- source set,
- query definition,
- uncertainty notes,
- shrinkage or smoothing metadata if applied.

---

## 17. LM Studio role

### 17.1 Allowed use

LLM use is allowed for:

- drafting source field-role mappings,
- ranking probable documentation PDFs,
- summarizing source documentation,
- ranking SIDRA tables against semantic queries,
- generating YAML/JSON mapping drafts.

### 17.2 Forbidden use

LLM use is not allowed to silently become source truth for:

- numeric value interpretation,
- support-role assignment,
- final code-role mapping,
- final parsing decisions,
- final denominator logic.

### 17.3 Required operating mode

Every LLM output must be:

- structured,
- logged,
- reviewable,
- confidence-scored,
- and accepted explicitly before becoming registry truth.

---

## 18. Development phases

### Phase 0 — Salvage and stabilization

Deliverables:

- refactored DATASUS manifest parser,
- refactored DATASUS series catalog builder,
- refactored PDF association utility,
- isolated SIDRA catalog/search package,
- shared config/logging/provenance utilities.

Exit criteria:

- can ingest an existing DATASUS manifest and produce a clean series catalog,
- can ingest SIDRA metadata and search local catalog.

### Phase 1 — DATASUS discovery and acquisition

Deliverables:

- optional fast scanner,
- manifest schema,
- deterministic downloader,
- asset metadata sidecars,
- raw storage layout.

Exit criteria:

- can reproducibly locate and fetch a chosen DATASUS slice from catalog rules.

### Phase 2 — First parser vertical slice

Deliverables:

- SINASC parser,
- source-normalized row schema,
- first canonical mapper,
- quality flags,
- municipality/date normalization.

Exit criteria:

- can parse SINASC raw files into canonical records.

### Phase 3 — SIDRA values layer

Deliverables:

- value endpoint client,
- raw value cache,
- normalized aggregate rows,
- first canonical aggregate mapper.

Exit criteria:

- can fetch population/context values and align them to municipality-year.

### Phase 4 — First observable compiler

Deliverables:

- count compiler,
- code-query compiler,
- threshold compiler,
- rate compiler,
- lineage/uncertainty metadata.

Exit criteria:

- can compile a first family of municipality-year observables from SINASC + SIDRA.

### Phase 5 — Second DATASUS source

Deliverables:

- SIM or SINAN parser,
- second canonical mapper,
- second set of code-role rules,
- cross-source alignment checks.

Exit criteria:

- can compile cross-source observables on one shared support.

### Phase 6 — Frontier definitions

Deliverables:

- observable family descriptors,
- refinement grammar skeleton,
- controlled materialization hooks.

Exit criteria:

- data substrate is ready for a baseline scanner.

---

## 19. Recommended proof-of-concepts

### POC 1 — SINASC + SIDRA

Goal:

- validate the whole path from DATASUS file discovery to canonical records to thresholded outcomes and denominator alignment.

Suggested outputs:

- live births count by municipality-year,
- low birth weight count/rate,
- congenital anomaly family count/rate,
- Apgar threshold count/rate,
- linked population denominator from SIDRA.

### POC 2 — SIM + SIDRA or SINAN + SIDRA

Goal:

- validate code-role handling and support-role semantics beyond birth data.

Suggested outputs:

- mortality counts by cause family,
- notification counts by condition family,
- subgroup rates,
- alignment checks between source roles.

### POC 3 — Documentation-assisted mapping

Goal:

- validate that local LLM assistance can accelerate source mapping without becoming authoritative.

Suggested outputs:

- machine-generated draft field registry,
- manual review diff,
- final accepted mapping.

---

## 20. Testing strategy

### 20.1 Discovery tests

- manifest parse correctness,
- regex extraction correctness,
- path exclusion correctness,
- path semantics tagging correctness,
- PDF association score regression tests.

### 20.2 Acquisition tests

- resumable download,
- hash stability,
- sidecar metadata completeness,
- duplicate suppression.

### 20.3 Parser tests

- encoding handling,
- date normalization,
- municipality normalization,
- missing-value handling,
- code-slot extraction.

### 20.4 Canonicalization tests

- support-role assignment,
- code-role mapping,
- subgroup normalization,
- annotation semantics.

### 20.5 Compiler tests

- count totals,
- code-query descendant semantics,
- threshold correctness,
- rate denominator correctness,
- lineage propagation.

---

## 21. Immediate implementation checklist

### 21.1 First week

- [ ] create repo skeleton
- [ ] move SIDRA code into isolated package boundary
- [ ] implement DATASUS manifest row schema
- [ ] implement DATASUS manifest parser from FileZilla export
- [ ] implement DATASUS series consolidation
- [ ] implement DATASUS PDF association scorer
- [ ] write series catalog to JSON and Parquet

### 21.2 Second week

- [ ] implement optional fast FTP scanner prototype
- [ ] benchmark `MLSD`/`LIST`/`NLST` behavior against DATASUS
- [ ] add downloader with provenance sidecars
- [ ] define canonical schema classes
- [ ] define source and field registry schema

### 21.3 Third week

- [ ] implement SINASC parser
- [ ] implement canonical mapper for SINASC
- [ ] implement municipality/date normalization helpers
- [ ] implement first compiler: simple counts + thresholds
- [ ] add SIDRA value fetch layer for denominator/context tables

### 21.4 Fourth week

- [ ] complete POC 1
- [ ] validate outputs on sample municipalities/years
- [ ] document edge cases
- [ ] decide whether SIM or SINAN becomes parser #2

---

## 22. Final implementation stance

The data module should be built under the following fixed principles:

1. **Manifest-first for DATASUS discovery**
2. **Metadata-warehouse-first for SIDRA**
3. **Source-specific parsers, not one universal parser**
4. **Canonical record mapping before scanning**
5. **Registries before downstream analytics**
6. **Observable compiler before graph engine**
7. **LLM assistance only as reviewed semantic acceleration**
8. **Provenance and uncertainty are first-class from day one**

The final graph/scanner layer is downstream of this work, not a substitute for it.

---

## 23. Appendix: direct engineering conclusions on the old FTP code

### 23.1 What was wrong with the old crawler

- It used `NLST` where a structured listing method was needed.
- It classified child entries by attempting `CWD` on each one.
- It backtracked with `CWD` recursively.
- It opened too many sessions (`MAX_WORKERS = 200`).
- It mixed discovery with exploratory extraction goals.
- It was notebook-oriented rather than pipeline-oriented.

### 23.2 What was right in the later manifest-analysis code

- It separated discovery output from semantic analysis.
- It treated filenames as latent metadata carriers.
- It added exclusion and auxiliary path rules.
- It used directory-level relational validation.
- It inferred partitioning and date formats.
- It tried to attach documentation probabilistically rather than manually.
- It grouped series into systems using path context.

### 23.3 What to do next

- Keep the manifest-analysis logic.
- Rewrite the crawler if desired, but only as a manifest producer.
- Build the canonical data substrate immediately after discovery/acquisition.

