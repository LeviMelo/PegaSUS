# DATASUS translation workflow

1. Scan FTP into JSONL
2. Build inventory rows
3. Build dataset families
4. Profile many files
5. Build family registry
6. Build variable catalog
7. Generate a translation bundle for one family
8. Feed the bundle text plus any external docs/PDF extracts into a strong model via UI
9. Save the model output as compact grammar
10. Validate grammar and merge into the central registry

Core commands:

```powershell
pegasus-data datasus scan data\catalog\datasus_scan.jsonl --checkpoint data\catalog\datasus_scanstate.json
pegasus-data datasus inventory data\catalog\datasus_scan.jsonl data\catalog\datasus_inventory.jsonl
pegasus-data datasus datasets data\catalog\datasus_scan.jsonl data\catalog\datasus_families.json
pegasus-data datasus profile-many data\catalog\datasus_inventory.jsonl data\catalog\datasus_profiles.jsonl --sample-rows 400
pegasus-data datasus family-registry data\catalog\datasus_families.json data\catalog\datasus_family_registry.json --profile-jsonl data\catalog\datasus_profiles.jsonl
pegasus-data datasus variable-catalog data\catalog\datasus_profiles.jsonl data\catalog\datasus_variable_catalog.json --families data\catalog\datasus_families.json
pegasus-data datasus translate-bundle SINASC:DN data\catalog\datasus_families.json data\catalog\datasus_profiles.jsonl data\catalog\datasus_variable_catalog.json data\catalog\bundle_SINASC_DN.txt --output-json data\catalog\bundle_SINASC_DN.json
pegasus-data datasus translate-validate docs\datasus_translation_grammar_example.txt
```
