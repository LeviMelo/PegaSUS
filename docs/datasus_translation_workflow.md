# DATASUS translation workflow

The current DATASUS path is organized around generic corpus handling:

1. Scan the FTP tree into a durable JSONL manifest.
2. Build inventory rows from scan output.
3. Build dataset families from path and filename heuristics.
4. Build a family registry that preserves the actual `member_files` for each family.
5. For one family, select a tiny curated candidate-file set from its real member files.
6. Download only those candidate data files and relevant associated docs.
7. Profile the downloaded local representatives.
8. Build a local document registry from fetched docs and extract text where possible.
9. Build a cross-family variable catalog and optional similarity artifacts.
10. Generate a translation bundle for one family.
11. Draft compact grammar externally using docs, profile summaries, and variable context.
12. Validate the returned grammar.
13. Merge accepted grammar files into the master registry.
14. Check registry coverage against the variable catalog or one family.

Example commands:

```powershell
pegasus-data datasus scan data\catalog\datasus_scan.jsonl --checkpoint data\catalog\datasus_scanstate.json
pegasus-data datasus inventory data\catalog\datasus_scan.jsonl data\catalog\datasus_inventory.jsonl
pegasus-data datasus datasets data\catalog\datasus_inventory.jsonl data\catalog\datasus_families.json
pegasus-data datasus family-registry data\catalog\datasus_families.json data\catalog\datasus_family_registry.json --profile-jsonl data\catalog\datasus_profiles.jsonl
pegasus-data datasus family-candidates SINASC:DN data\catalog\datasus_family_registry.json data\catalog\candidate_SINASC_DN.json
pegasus-data datasus download-candidates data\catalog\candidate_SINASC_DN.json data\catalog\downloaded_SINASC_DN.json --root data\raw\datasus\candidates
pegasus-data datasus download-docs data\catalog\candidate_SINASC_DN.json data\catalog\downloaded_docs_SINASC_DN.json --root data\raw\datasus\docs
pegasus-data datasus profile-many data\catalog\downloaded_SINASC_DN.json data\catalog\datasus_profiles.jsonl --sample-rows 400
pegasus-data datasus doc-registry data\catalog\datasus_families.json data\catalog\datasus_doc_registry.json --doc-root data\raw\datasus\docs
pegasus-data datasus variable-catalog data\catalog\datasus_profiles.jsonl data\catalog\datasus_variable_catalog.json --families data\catalog\datasus_families.json
pegasus-data datasus similarity-report data\catalog\datasus_profiles.jsonl data\catalog\datasus_family_registry.json data\catalog\datasus_similarity_report.json
pegasus-data datasus translate-bundle SINASC:DN data\catalog\datasus_families.json data\catalog\datasus_profiles.jsonl data\catalog\datasus_variable_catalog.json data\translations\bundles\SINASC_DN.txt --doc-registry data\catalog\datasus_doc_registry.json --output-json data\translations\bundles\SINASC_DN.json
pegasus-data datasus translate-validate data\translations\registry\candidate.grammar
pegasus-data datasus translate-merge data\translations\merged_registry.grammar data\translations\registry\base.grammar data\translations\registry\candidate.grammar
pegasus-data datasus translate-coverage data\translations\merged_registry.grammar data\catalog\datasus_variable_catalog.json --families data\catalog\datasus_families.json --family-registry data\catalog\datasus_family_registry.json --family-id SINASC:DN
```

Notes:

- FileZilla exports are optional bootstrap inputs, not the operational dependency.
- The intended rule is `scan everything, download almost nothing`.
- Candidate selection is family-specific and derived from real family member files, not a hardcoded UF/BR template.
- The master registry should stay text-first under `data/translations/`.
- Grammar produced by an external model is draft material; code validation and human review remain the acceptance gate.
- PDF extraction is best-effort and uses optional PDF parser dependencies when available; text-like local docs are handled directly.
