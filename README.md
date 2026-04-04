# PegaSUS Data Substrate

This repo currently implements the PegaSUS data substrate, not the downstream graph or statistical engine.

Current backbone:

- DATASUS: `scan -> inventory -> dataset families -> family registry -> generic DBF/DBC decode -> profile -> variable catalog -> translation bundle -> validate/merge/coverage`
- SIDRA: `metadata DB -> ingest -> lexical search/show -> normalized values fetch`

## DATASUS workflow

Default durable artifact layout:

- `data/catalog/` for scan, inventory, families, profiles, and SIDRA metadata outputs
- `data/translations/` for translation bundles, candidate grammar files, and the merged registry

Typical DATASUS command flow:

```powershell
pegasus-data datasus scan data\catalog\datasus_scan.jsonl --checkpoint data\catalog\datasus_scanstate.json
pegasus-data datasus inventory data\catalog\datasus_scan.jsonl data\catalog\datasus_inventory.jsonl
pegasus-data datasus datasets data\catalog\datasus_inventory.jsonl data\catalog\datasus_families.json
pegasus-data datasus profile-many data\catalog\datasus_inventory.jsonl data\catalog\datasus_profiles.jsonl --sample-rows 400
pegasus-data datasus family-registry data\catalog\datasus_families.json data\catalog\datasus_family_registry.json --profile-jsonl data\catalog\datasus_profiles.jsonl
pegasus-data datasus doc-registry data\catalog\datasus_families.json data\catalog\datasus_doc_registry.json --doc-root data\raw\datasus\docs
pegasus-data datasus variable-catalog data\catalog\datasus_profiles.jsonl data\catalog\datasus_variable_catalog.json --families data\catalog\datasus_families.json
pegasus-data datasus translate-bundle SINASC:DN data\catalog\datasus_families.json data\catalog\datasus_profiles.jsonl data\catalog\datasus_variable_catalog.json data\translations\bundles\SINASC_DN.txt --doc-registry data\catalog\datasus_doc_registry.json --output-json data\translations\bundles\SINASC_DN.json
pegasus-data datasus translate-validate data\translations\registry\candidate.grammar
pegasus-data datasus translate-merge data\translations\merged_registry.grammar data\translations\registry\base.grammar data\translations\registry\candidate.grammar
pegasus-data datasus translate-coverage data\translations\merged_registry.grammar data\catalog\datasus_variable_catalog.json --families data\catalog\datasus_families.json --family-registry data\catalog\datasus_family_registry.json --family-id SINASC:DN
```

DATASUS is intentionally centered on generic corpus organization and central translation, not on source-specific semantic parser modules.
The remaining `datasus/discovery/` package is manifest/catalog/doc-enrichment utility code; the canonical live scanner is `datasus/ftp/`.

## Compact translation grammar

Use compact block directives so external UI-driven LLM drafting stays token-efficient.

```text
$ RACACOR cat raça_cor
= 1 branca
= 2 preta
= 3 amarela
= 4 parda
= 5 indigena

$ CODMUNRES mun município_residência
> ibge6

@ SIM:DO CAUSABAS code causa_básica
> cid10
% doc:sim_layout
```

Directive meanings:

- `$ VAR KIND LABEL...` global variable definition
- `@ SCOPE VAR KIND LABEL...` family-scoped override
- `= RAW LABEL...` categorical value translation
- `> RULE...` one or more transformation rules
- `~ ALIAS...` aliases
- `% SOURCE...` provenance/source notes

Suggested kinds:

- `cat`, `date`, `mun`, `uf`, `num`, `txt`, `code`, `id`, `flag`, `unknown`

## What is not implemented yet

- Final PegaSUS graph / scanner / statistical engine
- Rich canonical compilation beyond the current skeleton
- Perfect DATASUS family ontology
- Automatic semantic translation generation without human review
