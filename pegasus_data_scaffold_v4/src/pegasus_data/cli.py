from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .common.io import read_jsonl, write_json, write_jsonl
from .common.logging import configure_logging
from .datasus.decode.inspect import inspect_dbase_file
from .datasus.discovery.catalog import build_series_catalog, write_series_catalog
from .datasus.discovery.manifest import parse_manifest_text, read_manifest_jsonl, write_manifest_jsonl
from .datasus.ftp import DatasusFtpScanner, diff_scan_outputs
from .datasus.inventory import build_dataset_families, build_family_registry, inventory_from_scan_jsonl
from .datasus.profile import build_variable_catalog, profile_dbase_file
from .datasus.translate import (
    build_translation_bundle,
    emit_translation_grammar,
    parse_translation_grammar_file,
    translate_field_samples,
    validate_translation_registry,
)
from .sidra.catalog.ingest import ingest_by_coverage, ingest_table
from .sidra.catalog.schema import ensure_schema
from .sidra.catalog.search import SearchArgs, search_tables, show_table
from .sidra.values import fetch_and_normalize_values_sharded


_DBASE_EXTS = {'.dbf', '.dbc'}


def _load_manifest_like(path: str, *, scan_id: str | None = None):
    return read_manifest_jsonl(path) if path.lower().endswith('.jsonl') else parse_manifest_text(path, scan_id=scan_id)


def _load_json(path: str):
    return json.loads(Path(path).read_text(encoding='utf-8'))


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


def _profile_signature_map(profile_jsonl: str | None) -> tuple[dict[str, str], list[dict]]:
    schema_signatures: dict[str, str] = {}
    profile_rows: list[dict] = []
    if profile_jsonl:
        for row in read_jsonl(profile_jsonl):
            profile_rows.append(row)
            if 'path' in row and 'schema_signature' in row:
                schema_signatures[str(row['path'])] = str(row['schema_signature'])
    return schema_signatures, profile_rows


def _cmd_datasus_datasets(args: argparse.Namespace) -> None:
    files = inventory_from_scan_jsonl(args.input)
    schema_signatures, _ = _profile_signature_map(args.profile_jsonl)
    datasets = build_dataset_families(files, schema_signatures=schema_signatures)
    write_json(args.output, [row.to_dict() for row in datasets])
    print(f'wrote {len(datasets)} dataset families -> {args.output}')


def _cmd_datasus_family_registry(args: argparse.Namespace) -> None:
    families = _load_json(args.families)
    _, profile_rows = _profile_signature_map(args.profile_jsonl)
    registry = build_family_registry(families, profile_rows=profile_rows)
    write_json(args.output, [row.to_dict() for row in registry])
    print(f'wrote {len(registry)} family registry rows -> {args.output}')


def _cmd_datasus_inspect(args: argparse.Namespace) -> None:
    preview = inspect_dbase_file(args.path, sample_rows=args.rows)
    print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2, default=str))


def _cmd_datasus_profile(args: argparse.Namespace) -> None:
    profile = profile_dbase_file(args.path, sample_rows=args.sample_rows)
    if args.output:
        write_json(args.output, profile.to_dict())
        print(f'wrote profile -> {args.output}')
        return
    print(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2, default=str))


def _cmd_datasus_profile_many(args: argparse.Namespace) -> None:
    rows = list(read_jsonl(args.input))
    out_rows = []
    count = 0
    for row in rows:
        path = row.get('path') or row.get('full_path')
        if not path or Path(path).suffix.lower() not in _DBASE_EXTS:
            continue
        try:
            profile = profile_dbase_file(path, sample_rows=args.sample_rows)
        except Exception as exc:
            out_rows.append({'path': path, 'error': str(exc)})
            continue
        out_rows.append(profile.to_dict())
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
    scope = args.scope
    translated = []
    for field in profile['field_profiles']:
        translated.append(translate_field_samples(field['name'], field.get('samples', []), registry, scope=scope).to_dict())
    if args.output:
        write_json(args.output, translated)
        print(f'wrote translated samples -> {args.output}')
        return
    print(json.dumps(translated, ensure_ascii=False, indent=2))


def _cmd_datasus_translate_merge(args: argparse.Namespace) -> None:
    registries = [parse_translation_grammar_file(path) for path in args.inputs]
    merged = registries[0]
    for reg in registries[1:]:
        merged = merged.merge(reg)
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
        family = next((f for f in families if str(f.get('family_id')) == args.family_id), None)
        if family is None:
            raise SystemExit(f'family not found: {args.family_id}')
        family_vars = set(family.get('variables') or [])
        if not family_vars:
            family_registry = _load_json(args.family_registry) if args.family_registry else []
            fam_row = next((f for f in family_registry if str(f.get('family_id')) == args.family_id), None)
            family_vars = set((fam_row or {}).get('variables') or [])
        payload = registry.coverage_for_variables(family_vars, scopes=[args.family_id])
        payload['family_id'] = args.family_id
    else:
        all_vars = [row.get('variable') for row in variables]
        payload = registry.coverage_for_variables(all_vars)
    if args.output:
        write_json(args.output, payload)
        print(f'wrote translation coverage -> {args.output}')
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_datasus_translate_bundle(args: argparse.Namespace) -> None:
    families = _load_json(args.families)
    family = next((f for f in families if str(f.get('family_id')) == args.family_id), None)
    if family is None:
        raise SystemExit(f'family not found: {args.family_id}')
    profile_rows = list(read_jsonl(args.profile_jsonl))
    variable_catalog = _load_json(args.variable_catalog)
    bundle = build_translation_bundle(family, profile_rows, variable_catalog, max_fields=args.max_fields)
    if args.output_json:
        write_json(args.output_json, bundle.to_dict())
    Path(args.output_text).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_text).write_text(bundle.prompt_text, encoding='utf-8')
    print(f'wrote translation bundle prompt -> {args.output_text}')
    if args.output_json:
        print(f'wrote translation bundle json -> {args.output_json}')


# SIDRA commands

def _cmd_sidra_db(args: argparse.Namespace) -> None:
    ensure_schema()
    print('SIDRA catalog schema ensured')


def _cmd_sidra_ingest(args: argparse.Namespace) -> None:
    ensure_schema()
    for table_id in args.table_ids:
        asyncio.run(ingest_table(table_id))
        print(f'ingested {table_id}')


def _cmd_sidra_ingest_coverage(args: argparse.Namespace) -> None:
    ensure_schema()
    report = asyncio.run(ingest_by_coverage(args.coverage, subject_contains=args.subject_contains, survey_contains=args.survey_contains, limit=args.limit, concurrency=args.concurrent))
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
    datasets.add_argument('input', help='Scanner JSONL output')
    datasets.add_argument('output')
    datasets.add_argument('--profile-jsonl', default=None)
    datasets.set_defaults(func=_cmd_datasus_datasets)

    family_registry = datasus_sub.add_parser('family-registry')
    family_registry.add_argument('families')
    family_registry.add_argument('output')
    family_registry.add_argument('--profile-jsonl', default=None)
    family_registry.set_defaults(func=_cmd_datasus_family_registry)

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
    profile_many.add_argument('input', help='Inventory JSONL or scan JSONL')
    profile_many.add_argument('output')
    profile_many.add_argument('--sample-rows', type=int, default=500)
    profile_many.add_argument('--limit', type=int, default=None)
    profile_many.set_defaults(func=_cmd_datasus_profile_many)

    variable_catalog = datasus_sub.add_parser('variable-catalog')
    variable_catalog.add_argument('profile_jsonl')
    variable_catalog.add_argument('output')
    variable_catalog.add_argument('--families', default=None)
    variable_catalog.set_defaults(func=_cmd_datasus_variable_catalog)

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
