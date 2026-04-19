from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .common.io import read_jsonl, write_json, write_jsonl
from .common.logging import configure_logging
from .datasus.decode.inspect import inspect_file
from .datasus.discovery.catalog import build_series_catalog, write_series_catalog
from .datasus.discovery.docs import build_family_document_registry
from .datasus.discovery.manifest import parse_manifest_text, read_manifest_jsonl, write_manifest_jsonl
from .datasus.fetch import download_plans, plan_family_candidate_downloads, select_family_candidates
from .datasus.ftp import DatasusFtpScanner, diff_scan_outputs
from .datasus.inventory import build_dataset_families, build_dataset_family_summary, build_family_registry, inventory_from_scan_jsonl
from .datasus.profile import (
    build_family_similarity_report,
    build_variable_catalog,
    build_variable_similarity_report,
    profile_file,
)
from .datasus.translate import (
    build_translation_bundle,
    emit_translation_grammar,
    parse_translation_grammar_file,
    translate_field_samples,
    validate_translation_registry,
)
from .sidra.catalog.schema import ensure_schema
from .sidra.catalog.search import SearchArgs, search_tables, show_table
from .sidra.values import fetch_and_normalize_values_sharded

from .datasus.fetch.pdfs import build_pdf_audit, plan_pdf_downloads_from_scan
from .datasus.inventory.audit import build_family_audit


def _load_manifest_like(path: str, *, scan_id: str | None = None):
    return read_manifest_jsonl(path) if path.lower().endswith('.jsonl') else parse_manifest_text(path, scan_id=scan_id)


def _load_json(path: str):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _load_rows_input(path: str) -> list[dict]:
    if path.lower().endswith('.jsonl'):
        return list(read_jsonl(path))
    payload = _load_json(path)
    if isinstance(payload, list):
        return payload
    for key in ('rows', 'downloads', 'items', 'selected_data_files'):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    raise SystemExit(f'unsupported row payload: {path}')


def _load_family_row(path: str, family_id: str) -> dict:
    families = _load_json(path)
    family = next((row for row in families if str(row.get('family_id')) == family_id), None)
    if family is None:
        raise SystemExit(f'family not found: {family_id}')
    return family


def _profile_signature_map(profile_jsonl: str | None) -> tuple[dict[str, str], list[dict]]:
    schema_signatures: dict[str, str] = {}
    profile_rows: list[dict] = []
    if profile_jsonl:
        for row in read_jsonl(profile_jsonl):
            profile_rows.append(row)
            source_path = str(row.get('source_path') or row.get('path') or '')
            if source_path and 'schema_signature' in row:
                schema_signatures[source_path] = str(row['schema_signature'])
    return schema_signatures, profile_rows


def _profile_input_path(row: dict) -> str | None:
    for key in ('local_path', 'path', 'full_path', 'target_path'):
        value = row.get(key)
        if value:
            return str(value)
    return None


def _cmd_datasus_manifest(args: argparse.Namespace) -> None:
    rows = parse_manifest_text(args.input, scan_id=args.scan_id)
    write_manifest_jsonl(args.output, rows)
    print(f'parsed {len(rows)} manifest rows -> {args.output}')


def _cmd_datasus_catalog(args: argparse.Namespace) -> None:
    rows = _load_manifest_like(args.input, scan_id=args.scan_id)
    catalog = build_series_catalog(rows)
    write_series_catalog(args.output, catalog)
    print(f'built {len(catalog)} series catalog rows -> {args.output}')


def _cmd_datasus_scan(args: argparse.Namespace) -> None:
    scanner = DatasusFtpScanner(connections=args.connections)
    state = scanner.scan_to_jsonl(output_path=args.output, checkpoint_path=args.checkpoint, append=not args.replace)
    print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))


def _cmd_datasus_scan_diff(args: argparse.Namespace) -> None:
    diff = diff_scan_outputs(args.old, args.new)
    if args.output:
        write_json(args.output, diff.to_dict())
        print(f'wrote diff -> {args.output}')
        return
    print(json.dumps(diff.to_dict(), ensure_ascii=False, indent=2))


def _cmd_datasus_inventory(args: argparse.Namespace) -> None:
    files = inventory_from_scan_jsonl(args.input)
    write_jsonl(args.output, (item.to_dict() for item in files))
    print(f'wrote {len(files)} inventory file rows -> {args.output}')


def _cmd_datasus_datasets(args: argparse.Namespace) -> None:
    rows = list(read_jsonl(args.input))
    if not rows:
        write_json(args.output, [])
        print(f'wrote 0 dataset families -> {args.output}')
        if args.summary_output:
            write_json(args.summary_output, {'family_count': 0, 'families': []})
            print(f'wrote dataset family summary -> {args.summary_output}')
        return
    if 'full_path' in rows[0]:
        files = inventory_from_scan_jsonl(args.input)
    else:
        from .datasus.inventory.files import InventoryFile
        files = [InventoryFile(**row) for row in rows]
    schema_signatures, _ = _profile_signature_map(args.profile_jsonl)
    datasets = build_dataset_families(files, schema_signatures=schema_signatures)
    write_json(args.output, [row.to_dict() for row in datasets])
    print(f'wrote {len(datasets)} dataset families -> {args.output}')
    if args.summary_output:
        summary = build_dataset_family_summary(files, datasets)
        write_json(args.summary_output, summary)
        print(f'wrote dataset family summary -> {args.summary_output}')

def _cmd_datasus_family_audit(args: argparse.Namespace) -> None:
    families = _load_json(args.families)
    payload = build_family_audit(families, family_id=args.family_id, only_issues=args.only_issues)
    write_json(args.output, payload)
    print(f'wrote family audit -> {args.output}')


def _cmd_datasus_download_pdfs(args: argparse.Namespace) -> None:
    plans = plan_pdf_downloads_from_scan(args.scan_jsonl, endpoint=args.endpoint, root=args.root)
    results = download_plans(plans, overwrite=args.overwrite, dry_run=args.dry_run)
    write_json(args.output, results)
    print(f'wrote {len(results)} pdf download rows -> {args.output}')
    if args.audit_output:
        families = _load_json(args.families) if args.families else None
        audit = build_pdf_audit(args.scan_jsonl, endpoint=args.endpoint, families=families)
        write_json(args.audit_output, audit)
        print(f'wrote pdf audit -> {args.audit_output}')

def _cmd_datasus_family_registry(args: argparse.Namespace) -> None:
    families = _load_json(args.families)
    _, profile_rows = _profile_signature_map(args.profile_jsonl)
    registry = build_family_registry(families, profile_rows=profile_rows)
    write_json(args.output, [row.to_dict() for row in registry])
    print(f'wrote {len(registry)} family registry rows -> {args.output}')


def _cmd_datasus_family_candidates(args: argparse.Namespace) -> None:
    family = _load_family_row(args.family_registry, args.family_id)
    selection = select_family_candidates(family, max_data_files=args.max_data_files, max_docs=args.max_docs)
    write_json(args.output, selection.to_dict())
    print(f'wrote candidate selection -> {args.output}')


def _cmd_datasus_download_candidates(args: argparse.Namespace) -> None:
    selection = _load_json(args.input)
    plans = plan_family_candidate_downloads(selection, asset_kind='data', root=args.root)
    results = download_plans(plans, overwrite=args.overwrite, dry_run=args.dry_run)
    write_json(args.output, results)
    print(f'wrote {len(results)} candidate download rows -> {args.output}')


def _cmd_datasus_download_docs(args: argparse.Namespace) -> None:
    selection = _load_json(args.input)
    plans = plan_family_candidate_downloads(selection, asset_kind='doc', root=args.root)
    results = download_plans(plans, overwrite=args.overwrite, dry_run=args.dry_run)
    write_json(args.output, results)
    print(f'wrote {len(results)} document download rows -> {args.output}')


def _cmd_datasus_doc_registry(args: argparse.Namespace) -> None:
    families = _load_json(args.families)
    registry = build_family_document_registry(families, doc_root=args.doc_root, max_chars=args.max_chars)
    write_json(args.output, [row.to_dict() for row in registry])
    print(f'wrote {len(registry)} family document rows -> {args.output}')


def _cmd_datasus_inspect(args: argparse.Namespace) -> None:
    preview = inspect_file(args.path, sample_rows=args.rows)
    print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2, default=str))


def _cmd_datasus_profile(args: argparse.Namespace) -> None:
    profile = profile_file(args.path, sample_rows=args.sample_rows)
    if args.output:
        write_json(args.output, profile.to_dict())
        print(f'wrote profile -> {args.output}')
        return
    print(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2, default=str))


def _cmd_datasus_profile_many(args: argparse.Namespace) -> None:
    rows = _load_rows_input(args.input)
    out_rows = []
    count = 0
    for row in rows:
        path = _profile_input_path(row)
        if not path:
            continue
        try:
            profile = profile_file(
                path,
                sample_rows=args.sample_rows,
                source_path=str(row.get('source_path') or row.get('path') or path),
                local_path=str(row.get('local_path') or path),
            )
        except Exception as exc:
            out_rows.append({
                'path': path,
                'source_path': row.get('source_path') or row.get('path') or path,
                'local_path': row.get('local_path') or path,
                'error': str(exc),
            })
            continue
        payload = profile.to_dict()
        if row.get('source_path'):
            payload['source_path'] = row['source_path']
        if row.get('family_id'):
            payload['family_id'] = row['family_id']
        if row.get('local_path'):
            payload['local_path'] = row['local_path']
        out_rows.append(payload)
        count += 1
        if args.limit and count >= args.limit:
            break
    write_jsonl(args.output, out_rows)
    print(f'wrote {len(out_rows)} profiles -> {args.output}')


def _cmd_datasus_variable_catalog(args: argparse.Namespace) -> None:
    profiles = list(read_jsonl(args.profile_jsonl))
    families = _load_json(args.families) if args.families else None
    catalog = build_variable_catalog(profiles, families=families)
    write_json(args.output, [row.to_dict() for row in catalog])
    print(f'wrote {len(catalog)} variable catalog rows -> {args.output}')


def _cmd_datasus_similarity_report(args: argparse.Namespace) -> None:
    profiles = list(read_jsonl(args.profile_jsonl))
    families = _load_json(args.families)
    payload = build_variable_similarity_report(
        profiles,
        families,
        family_similarity_threshold=args.family_threshold,
        name_similarity_threshold=args.name_threshold,
        value_similarity_threshold=args.value_threshold,
    )
    write_json(args.output, payload)
    print(f'wrote similarity report -> {args.output}')


def _cmd_datasus_family_similarity(args: argparse.Namespace) -> None:
    profiles = list(read_jsonl(args.profile_jsonl))
    families = _load_json(args.families)
    payload = build_family_similarity_report(profiles, families, similarity_threshold=args.threshold)
    write_json(args.output, payload)
    print(f'wrote family similarity report -> {args.output}')


def _cmd_datasus_translate_validate(args: argparse.Namespace) -> None:
    registry = parse_translation_grammar_file(args.input)
    report = validate_translation_registry(registry)
    payload = {
        'validation': report.to_dict(),
        'entries': registry.to_dict() if args.dump_entries else None,
    }
    if args.output:
        write_json(args.output, payload)
        print(f'wrote translation validation -> {args.output}')
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_datasus_translate_samples(args: argparse.Namespace) -> None:
    registry = parse_translation_grammar_file(args.grammar)
    profile = _load_json(args.profile)
    translated = []
    for field in profile['field_profiles']:
        translated.append(translate_field_samples(field['name'], field.get('samples', []), registry, scope=args.scope).to_dict())
    if args.output:
        write_json(args.output, translated)
        print(f'wrote translated samples -> {args.output}')
        return
    print(json.dumps(translated, ensure_ascii=False, indent=2))


def _cmd_datasus_translate_merge(args: argparse.Namespace) -> None:
    registries = [parse_translation_grammar_file(path) for path in args.inputs]
    merged = registries[0]
    for registry in registries[1:]:
        merged = merged.merge(registry)
    report = validate_translation_registry(merged)
    if report.errors:
        raise SystemExit('merge produced invalid registry: ' + '; '.join(report.errors))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(emit_translation_grammar(merged), encoding='utf-8')
    print(f'wrote merged translation grammar -> {args.output}')


def _cmd_datasus_translate_coverage(args: argparse.Namespace) -> None:
    registry = parse_translation_grammar_file(args.grammar)
    variables = _load_json(args.variable_catalog)
    families = _load_json(args.families) if args.families else None
    if args.family_id:
        if not families:
            raise SystemExit('--family-id requires --families')
        family = next((row for row in families if str(row.get('family_id')) == args.family_id), None)
        if family is None:
            raise SystemExit(f'family not found: {args.family_id}')
        family_vars = set(family.get('variables') or [])
        if not family_vars:
            family_registry = _load_json(args.family_registry) if args.family_registry else []
            family_row = next((row for row in family_registry if str(row.get('family_id')) == args.family_id), None)
            family_vars = set((family_row or {}).get('variables') or [])
        payload = registry.coverage_for_variables(family_vars, scopes=[args.family_id])
        payload['family_id'] = args.family_id
    else:
        payload = registry.coverage_for_variables([row.get('variable') for row in variables])
    if args.output:
        write_json(args.output, payload)
        print(f'wrote translation coverage -> {args.output}')
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_datasus_translate_bundle(args: argparse.Namespace) -> None:
    families = _load_json(args.families)
    family = next((row for row in families if str(row.get('family_id')) == args.family_id), None)
    if family is None:
        raise SystemExit(f'family not found: {args.family_id}')
    profile_rows = list(read_jsonl(args.profile_jsonl))
    variable_catalog = _load_json(args.variable_catalog)
    document_registry = _load_json(args.doc_registry) if args.doc_registry else None
    bundle = build_translation_bundle(
        family,
        profile_rows,
        variable_catalog,
        document_registry=document_registry,
        max_fields=args.max_fields,
    )
    if args.output_json:
        write_json(args.output_json, bundle.to_dict())
    Path(args.output_text).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_text).write_text(bundle.prompt_text, encoding='utf-8')
    print(f'wrote translation bundle prompt -> {args.output_text}')
    if args.output_json:
        print(f'wrote translation bundle json -> {args.output_json}')


def _cmd_sidra_db(args: argparse.Namespace) -> None:
    ensure_schema()
    print('SIDRA catalog schema ensured')


def _cmd_sidra_ingest(args: argparse.Namespace) -> None:
    from .sidra.catalog.ingest import ingest_table

    ensure_schema()
    for table_id in args.table_ids:
        asyncio.run(ingest_table(table_id))
        print(f'ingested {table_id}')


def _cmd_sidra_ingest_coverage(args: argparse.Namespace) -> None:
    from .sidra.catalog.ingest import ingest_by_coverage

    ensure_schema()
    report = asyncio.run(ingest_by_coverage(
        args.coverage,
        subject_contains=args.subject_contains,
        survey_contains=args.survey_contains,
        limit=args.limit,
        concurrency=args.concurrent,
    ))
    print(json.dumps({'coverage': report.coverage, 'matched_table_ids': report.matched_table_ids}, ensure_ascii=False, indent=2))


def _cmd_sidra_search(args: argparse.Namespace) -> None:
    ensure_schema()
    hits = search_tables(SearchArgs(q=args.q, limit=args.limit))
    print(json.dumps([hit.__dict__ for hit in hits], ensure_ascii=False, indent=2))


def _cmd_sidra_show(args: argparse.Namespace) -> None:
    ensure_schema()
    print(json.dumps(show_table(args.table_id), ensure_ascii=False, indent=2))


def _cmd_sidra_values(args: argparse.Namespace) -> None:
    ensure_schema()
    periods = [item.strip() for item in args.periods.split(',') if item.strip()]
    localities = [item.strip() for item in args.locality_ids.split(',') if item.strip()]
    rows = asyncio.run(fetch_and_normalize_values_sharded(
        aggregate_id=args.aggregate_id,
        variable_id=args.variable_id,
        periods=periods,
        level=args.level,
        locality_ids=localities,
        classification=args.classification,
        view=args.view,
    ))
    payload = [row.to_dict() for row in rows]
    if args.output:
        write_jsonl(args.output, payload)
        print(f'wrote {len(payload)} normalized SIDRA value rows -> {args.output}')
        return
    print(json.dumps(payload[: args.limit], ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='pegasus-data')
    sub = parser.add_subparsers(dest='cmd')

    datasus = sub.add_parser('datasus')
    datasus_sub = datasus.add_subparsers(dest='datasus_cmd')

    manifest = datasus_sub.add_parser('manifest')
    manifest.add_argument('input')
    manifest.add_argument('output')
    manifest.add_argument('--scan-id', default=None)
    manifest.set_defaults(func=_cmd_datasus_manifest)

    scan = datasus_sub.add_parser('scan')
    scan.add_argument('output')
    scan.add_argument('--checkpoint', default=None)
    scan.add_argument('--connections', type=int, default=8)
    scan.add_argument('--replace', action='store_true')
    scan.set_defaults(func=_cmd_datasus_scan)

    scan_diff = datasus_sub.add_parser('scan-diff')
    scan_diff.add_argument('old')
    scan_diff.add_argument('new')
    scan_diff.add_argument('--output', default=None)
    scan_diff.set_defaults(func=_cmd_datasus_scan_diff)

    inventory = datasus_sub.add_parser('inventory')
    inventory.add_argument('input', help='Scanner JSONL output')
    inventory.add_argument('output')
    inventory.set_defaults(func=_cmd_datasus_inventory)

    datasets = datasus_sub.add_parser('datasets')
    datasets.add_argument('input', help='Inventory JSONL or scan JSONL')
    datasets.add_argument('output')
    datasets.add_argument('--profile-jsonl', default=None)
    datasets.add_argument('--summary-output', default=None)
    datasets.set_defaults(func=_cmd_datasus_datasets)
    
    family_audit = datasus_sub.add_parser('family-audit')
    family_audit.add_argument('families')
    family_audit.add_argument('output')
    family_audit.add_argument('--family-id', default=None)
    family_audit.add_argument('--only-issues', action='store_true')
    family_audit.set_defaults(func=_cmd_datasus_family_audit)

    family_registry = datasus_sub.add_parser('family-registry')
    family_registry.add_argument('families')
    family_registry.add_argument('output')
    family_registry.add_argument('--profile-jsonl', default=None)
    family_registry.set_defaults(func=_cmd_datasus_family_registry)

    family_candidates = datasus_sub.add_parser('family-candidates')
    family_candidates.add_argument('family_id')
    family_candidates.add_argument('family_registry')
    family_candidates.add_argument('output')
    family_candidates.add_argument('--max-data-files', type=int, default=3)
    family_candidates.add_argument('--max-docs', type=int, default=5)
    family_candidates.set_defaults(func=_cmd_datasus_family_candidates)

    download_candidates = datasus_sub.add_parser('download-candidates')
    download_candidates.add_argument('input')
    download_candidates.add_argument('output')
    download_candidates.add_argument('--root', default=None)
    download_candidates.add_argument('--overwrite', action='store_true')
    download_candidates.add_argument('--dry-run', action='store_true')
    download_candidates.set_defaults(func=_cmd_datasus_download_candidates)

    download_docs = datasus_sub.add_parser('download-docs')
    download_docs.add_argument('input')
    download_docs.add_argument('output')
    download_docs.add_argument('--root', default=None)
    download_docs.add_argument('--overwrite', action='store_true')
    download_docs.add_argument('--dry-run', action='store_true')
    download_docs.set_defaults(func=_cmd_datasus_download_docs)
    
    download_pdfs = datasus_sub.add_parser('download-pdfs')
    download_pdfs.add_argument('scan_jsonl')
    download_pdfs.add_argument('output')
    download_pdfs.add_argument('--endpoint', default='/dissemin/publicos')
    download_pdfs.add_argument('--root', default=None)
    download_pdfs.add_argument('--families', default=None)
    download_pdfs.add_argument('--audit-output', default=None)
    download_pdfs.add_argument('--overwrite', action='store_true')
    download_pdfs.add_argument('--dry-run', action='store_true')
    download_pdfs.set_defaults(func=_cmd_datasus_download_pdfs)

    doc_registry = datasus_sub.add_parser('doc-registry')
    doc_registry.add_argument('families')
    doc_registry.add_argument('output')
    doc_registry.add_argument('--doc-root', required=True)
    doc_registry.add_argument('--max-chars', type=int, default=4000)
    doc_registry.set_defaults(func=_cmd_datasus_doc_registry)

    catalog = datasus_sub.add_parser('catalog')
    catalog.add_argument('input')
    catalog.add_argument('output')
    catalog.add_argument('--scan-id', default=None)
    catalog.set_defaults(func=_cmd_datasus_catalog)

    inspect = datasus_sub.add_parser('inspect-file')
    inspect.add_argument('path')
    inspect.add_argument('--rows', type=int, default=5)
    inspect.set_defaults(func=_cmd_datasus_inspect)

    profile = datasus_sub.add_parser('profile-file')
    profile.add_argument('path')
    profile.add_argument('--sample-rows', type=int, default=500)
    profile.add_argument('--output', default=None)
    profile.set_defaults(func=_cmd_datasus_profile)

    profile_many = datasus_sub.add_parser('profile-many')
    profile_many.add_argument('input', help='Inventory JSONL, download JSON, or scan JSONL')
    profile_many.add_argument('output')
    profile_many.add_argument('--sample-rows', type=int, default=500)
    profile_many.add_argument('--limit', type=int, default=None)
    profile_many.set_defaults(func=_cmd_datasus_profile_many)

    variable_catalog = datasus_sub.add_parser('variable-catalog')
    variable_catalog.add_argument('profile_jsonl')
    variable_catalog.add_argument('output')
    variable_catalog.add_argument('--families', default=None)
    variable_catalog.set_defaults(func=_cmd_datasus_variable_catalog)

    family_similarity = datasus_sub.add_parser('family-similarity')
    family_similarity.add_argument('profile_jsonl')
    family_similarity.add_argument('families')
    family_similarity.add_argument('output')
    family_similarity.add_argument('--threshold', type=float, default=0.8)
    family_similarity.set_defaults(func=_cmd_datasus_family_similarity)

    similarity_report = datasus_sub.add_parser('similarity-report')
    similarity_report.add_argument('profile_jsonl')
    similarity_report.add_argument('families')
    similarity_report.add_argument('output')
    similarity_report.add_argument('--family-threshold', type=float, default=0.8)
    similarity_report.add_argument('--name-threshold', type=float, default=0.85)
    similarity_report.add_argument('--value-threshold', type=float, default=0.6)
    similarity_report.set_defaults(func=_cmd_datasus_similarity_report)

    tval = datasus_sub.add_parser('translate-validate')
    tval.add_argument('input')
    tval.add_argument('--output', default=None)
    tval.add_argument('--dump-entries', action='store_true')
    tval.set_defaults(func=_cmd_datasus_translate_validate)

    tsamp = datasus_sub.add_parser('translate-samples')
    tsamp.add_argument('grammar')
    tsamp.add_argument('profile')
    tsamp.add_argument('--scope', default=None)
    tsamp.add_argument('--output', default=None)
    tsamp.set_defaults(func=_cmd_datasus_translate_samples)

    tmerge = datasus_sub.add_parser('translate-merge')
    tmerge.add_argument('output')
    tmerge.add_argument('inputs', nargs='+')
    tmerge.set_defaults(func=_cmd_datasus_translate_merge)

    tcov = datasus_sub.add_parser('translate-coverage')
    tcov.add_argument('grammar')
    tcov.add_argument('variable_catalog')
    tcov.add_argument('--families', default=None)
    tcov.add_argument('--family-registry', default=None)
    tcov.add_argument('--family-id', default=None)
    tcov.add_argument('--output', default=None)
    tcov.set_defaults(func=_cmd_datasus_translate_coverage)

    tbundle = datasus_sub.add_parser('translate-bundle')
    tbundle.add_argument('family_id')
    tbundle.add_argument('families')
    tbundle.add_argument('profile_jsonl')
    tbundle.add_argument('variable_catalog')
    tbundle.add_argument('output_text')
    tbundle.add_argument('--doc-registry', default=None)
    tbundle.add_argument('--output-json', default=None)
    tbundle.add_argument('--max-fields', type=int, default=120)
    tbundle.set_defaults(func=_cmd_datasus_translate_bundle)

    sidra = sub.add_parser('sidra')
    sidra_sub = sidra.add_subparsers(dest='sidra_cmd')

    sidra_db = sidra_sub.add_parser('db')
    sidra_db.set_defaults(func=_cmd_sidra_db)

    sidra_ingest = sidra_sub.add_parser('ingest')
    sidra_ingest.add_argument('table_ids', type=int, nargs='+')
    sidra_ingest.set_defaults(func=_cmd_sidra_ingest)

    sidra_cov = sidra_sub.add_parser('ingest-coverage')
    sidra_cov.add_argument('--coverage', required=True)
    sidra_cov.add_argument('--subject-contains', default=None)
    sidra_cov.add_argument('--survey-contains', default=None)
    sidra_cov.add_argument('--limit', type=int, default=None)
    sidra_cov.add_argument('--concurrent', type=int, default=4)
    sidra_cov.set_defaults(func=_cmd_sidra_ingest_coverage)

    sidra_search = sidra_sub.add_parser('search')
    sidra_search.add_argument('--q', required=True)
    sidra_search.add_argument('--limit', type=int, default=20)
    sidra_search.set_defaults(func=_cmd_sidra_search)

    sidra_show = sidra_sub.add_parser('show')
    sidra_show.add_argument('table_id', type=int)
    sidra_show.set_defaults(func=_cmd_sidra_show)

    sidra_values = sidra_sub.add_parser('values')
    sidra_values.add_argument('--aggregate-id', type=int, required=True)
    sidra_values.add_argument('--variable-id', required=True)
    sidra_values.add_argument('--periods', required=True, help='Comma-separated period ids')
    sidra_values.add_argument('--level', required=True, help='Territorial level, e.g. N6')
    sidra_values.add_argument('--locality-ids', required=True, help='Comma-separated locality ids')
    sidra_values.add_argument('--classification', default=None)
    sidra_values.add_argument('--view', default='flat')
    sidra_values.add_argument('--output', default=None)
    sidra_values.add_argument('--limit', type=int, default=20)
    sidra_values.set_defaults(func=_cmd_sidra_values)

    return parser


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, 'func'):
        parser.print_help()
        return
    args.func(args)


if __name__ == '__main__':
    main()