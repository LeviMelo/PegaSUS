# DATASUS translation workflow

The current DATASUS path is organized around generic corpus handling:

1. Scan the FTP tree into a durable JSONL manifest.
2. Build inventory rows from scan output.
3. Build dataset families from path and filename heuristics.
4. Profile `.dbc` / `.dbf` files empirically.
5. Build a family registry from families plus profile output.
6. Build a local document registry from fetched docs and extract text where possible.
7. Build a cross-family variable catalog.
8. Generate a translation bundle for one family.
9. Draft compact grammar externally using docs, profile summaries, and variable context.
10. Validate the returned grammar.
11. Merge accepted grammar files into the master registry.
12. Check registry coverage against the variable catalog or one family.

Example commands:

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

Notes:

- FileZilla exports are optional bootstrap inputs, not the operational dependency.
- The master registry should stay text-first under `data/translations/`.
- Grammar produced by an external model is draft material; code validation and human review remain the acceptance gate.
- PDF extraction is best-effort and uses optional PDF parser dependencies when available; text-like local docs are handled directly.
