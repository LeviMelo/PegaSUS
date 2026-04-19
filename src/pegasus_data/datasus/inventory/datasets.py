from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from ..discovery.docs import associate_pdfs, build_pdf_manifest_rows
from ..discovery.heuristics import (
    MIN_FILES_FOR_PATTERN_VALIDATION,
    classify_partition,
    classify_path_semantic,
    format_normalized_date,
    infer_date_format,
    normalize_datecode,
)
from .files import InventoryFile


_EXTENSION_PRIORITY = {'.json': 0, '.parquet': 1, '.xml': 2, '.csv': 3, '.dbf': 4, '.dbc': 5}
_PATH_PRIORITY = {'[Primary]': 0, '[Legacy Archive]': 1, '[Staging]': 2}
_FORMAT_PREFERENCE = ['json', 'parquet', 'xml', 'csv', 'dbf', 'dbc']


@dataclass(frozen=True)
class DatasetFamily:
    family_id: str
    system_guess: str | None
    source_systems: list[str]
    series_prefix: str | None
    partition_type: str
    date_format: str | None
    time_range: str | None
    time_range_display: str | None
    file_count: int
    member_files: list[str]
    files: list[str]
    source_paths: list[str]
    geo_coverage: list[str]
    path_semantics: dict[str, str]
    format_families: list[str]
    primary_extensions: list[str]
    physical_variants: list[dict[str, Any]]
    preferred_working_series: dict[str, Any]
    associated_docs: list[dict]
    schema_signatures: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _sort_extensions(values: list[str | None]) -> list[str]:
    return sorted({value for value in values if value}, key=lambda value: (_EXTENSION_PRIORITY.get(value, 99), value))


def _discard_reason(item: InventoryFile) -> str | None:
    if item.path_type == 'Auxiliary':
        return 'auxiliary_path'
    if not item.series_prefix:
        return 'missing_series_prefix'
    if not item.primary_extension:
        return 'missing_primary_extension'
    if item.format_family == 'unknown':
        return 'unknown_format_family'
    return None


def _time_bounds(date_codes: list[str], date_format: str | None) -> tuple[int | None, int | None]:
    if not date_format:
        return None, None
    normalized = [normalize_datecode(code, date_format) for code in date_codes if code]
    normalized = [value for value in normalized if value]
    if not normalized:
        return None, None
    return min(normalized), max(normalized)


def _display_range(start: int | None, end: int | None) -> str | None:
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    if start == end:
        return format_normalized_date(start)
    return f"{format_normalized_date(start)} to {format_normalized_date(end)}"


def _next_normalized_date(value: int, date_format: str | None) -> int:
    year, month = divmod(value, 100)
    if date_format == 'YYMM':
        month += 1
        if month > 12:
            year += 1
            month = 1
        return year * 100 + month
    if date_format in {'YY', 'YYYY'}:
        return (year + 1) * 100
    return value


def _dates_are_contiguous(left: int, right: int, date_format: str | None) -> bool:
    return right == _next_normalized_date(left, date_format)


def _ranges_touch_or_overlap(left_min: int | None, left_max: int | None, right_min: int | None, right_max: int | None, date_format: str | None) -> bool:
    if left_min is None or left_max is None or right_min is None or right_max is None:
        return False
    if right_min < left_min:
        left_min, right_min = right_min, left_min
        left_max, right_max = right_max, left_max
    if right_min <= left_max:
        return True
    return _dates_are_contiguous(left_max, right_min, date_format)


def _group_signature(system_guess: str | None, series_prefix: str, rows: list[InventoryFile]) -> dict[str, Any]:
    geo_coverage = sorted({row.geo_code for row in rows if row.geo_code})
    partition_type = classify_partition(set(geo_coverage)) if geo_coverage else 'Unknown'
    date_codes = [row.date_code for row in rows if row.date_code]
    date_format = infer_date_format(date_codes) if date_codes else None
    time_min, time_max = _time_bounds(date_codes, date_format)
    return {
        'system_guess': system_guess,
        'series_prefix': series_prefix,
        'rows': rows,
        'geo_coverage': geo_coverage,
        'partition_type': partition_type,
        'date_format': date_format,
        'time_min': time_min,
        'time_max': time_max,
        'time_range_display': _display_range(time_min, time_max),
        'source_paths': sorted({row.directory for row in rows}),
        'format_families': sorted({row.format_family for row in rows}),
        'primary_extensions': _sort_extensions([row.primary_extension for row in rows]),
        'file_count': len(rows),
        'sample_files': sorted(row.path for row in rows)[:10],
    }


def _groups_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left['series_prefix'] != right['series_prefix']:
        return False
    if left['partition_type'] != right['partition_type']:
        return False
    if left['date_format'] != right['date_format']:
        return False
    if left['geo_coverage'] != right['geo_coverage']:
        return False
    return _ranges_touch_or_overlap(left['time_min'], left['time_max'], right['time_min'], right['time_max'], left['date_format'])


def _build_path_semantics(rows: list[InventoryFile], date_format: str | None, global_max_date: int | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not date_format or global_max_date is None:
        return out
    rows_by_directory: dict[str, list[InventoryFile]] = defaultdict(list)
    for row in rows:
        if row.date_code:
            rows_by_directory[row.directory].append(row)
    for directory in sorted(rows_by_directory):
        path_dates = [normalize_datecode(row.date_code, date_format) for row in rows_by_directory[directory] if row.date_code]
        path_dates = [value for value in path_dates if value]
        if path_dates:
            out[directory] = classify_path_semantic(directory, global_max_date=global_max_date, path_max_date=max(path_dates), date_format=date_format)
    return out


def _build_physical_variants(groups: list[dict[str, Any]], path_semantics: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, group in enumerate(sorted(groups, key=lambda item: (item['system_guess'] or '', item['time_min'] or 0, item['source_paths'])), start=1):
        out.append({
            'variant_id': f'variant_{index}',
            'system_guess': group['system_guess'],
            'partition_type': group['partition_type'],
            'date_format': group['date_format'],
            'time_range_display': group['time_range_display'],
            'file_count': group['file_count'],
            'source_paths': list(group['source_paths']),
            'path_semantics': {path: path_semantics.get(path) for path in group['source_paths'] if path in path_semantics},
            'geo_coverage': list(group['geo_coverage']),
            'format_families': list(group['format_families']),
            'primary_extensions': list(group['primary_extensions']),
            'sample_files': list(group['sample_files']),
        })
    return out


def _row_sort_key(row: InventoryFile, path_semantics: dict[str, str]) -> tuple[Any, ...]:
    return (
        _EXTENSION_PRIORITY.get(row.primary_extension, 99),
        _PATH_PRIORITY.get(path_semantics.get(row.directory), 9),
        row.system_guess or '',
        row.directory,
        row.path,
    )


def _expected_dates(start: int | None, end: int | None, date_format: str | None) -> list[int]:
    if start is None or end is None or not date_format:
        return []
    out: list[int] = []
    current = start
    safety = 0
    while current <= end and safety < 5000:
        out.append(current)
        current = _next_normalized_date(current, date_format)
        safety += 1
    return out


def _build_preferred_working_series(rows: list[InventoryFile], date_format: str | None, path_semantics: dict[str, str]) -> dict[str, Any]:
    if not rows:
        return {
            'strategy': 'empty',
            'format_preference': list(_FORMAT_PREFERENCE),
            'coverage_complete': False,
            'coverage_gaps': [],
            'selected_file_count': 0,
            'selected_files': [],
            'selected_primary_extensions': [],
            'selected_format_families': [],
            'segment_count': 0,
            'segments': [],
        }

    dated_rows: dict[int, list[InventoryFile]] = defaultdict(list)
    for row in rows:
        if row.date_code and date_format:
            normalized = normalize_datecode(row.date_code, date_format)
            if normalized:
                dated_rows[normalized].append(row)

    if not dated_rows:
        ordered = sorted(rows, key=lambda row: _row_sort_key(row, path_semantics))
        return {
            'strategy': 'undated_full_family',
            'format_preference': list(_FORMAT_PREFERENCE),
            'coverage_complete': True,
            'coverage_gaps': [],
            'selected_file_count': len(ordered),
            'selected_files': [row.path for row in ordered],
            'selected_primary_extensions': _sort_extensions([row.primary_extension for row in ordered]),
            'selected_format_families': sorted({row.format_family for row in ordered}),
            'segment_count': 1 if ordered else 0,
            'segments': [{
                'time_range_display': None,
                'primary_extension': ordered[0].primary_extension if ordered else None,
                'format_family': ordered[0].format_family if ordered else None,
                'system_guess': ordered[0].system_guess if ordered else None,
                'path_semantic': path_semantics.get(ordered[0].directory) if ordered else None,
                'file_count': len(ordered),
                'selected_files': [row.path for row in ordered],
                'source_paths': sorted({row.directory for row in ordered}),
            }] if ordered else [],
        }

    selected: list[tuple[int, InventoryFile]] = []
    for normalized_date in sorted(dated_rows):
        chosen = sorted(dated_rows[normalized_date], key=lambda row: _row_sort_key(row, path_semantics))[0]
        selected.append((normalized_date, chosen))

    expected_dates = _expected_dates(min(dated_rows), max(dated_rows), date_format)
    selected_dates = {normalized_date for normalized_date, _ in selected}
    coverage_gaps = [format_normalized_date(value) for value in expected_dates if value not in selected_dates]

    segments: list[dict[str, Any]] = []
    current_segment: dict[str, Any] | None = None
    current_signature: tuple[Any, ...] | None = None
    previous_date: int | None = None

    for normalized_date, row in selected:
        signature = (
            row.primary_extension,
            row.format_family,
            row.system_guess,
            path_semantics.get(row.directory),
        )
        contiguous = previous_date is not None and _dates_are_contiguous(previous_date, normalized_date, date_format)
        if current_segment is None or current_signature != signature or not contiguous:
            if current_segment is not None:
                current_segment['time_range_display'] = _display_range(current_segment.pop('_start'), current_segment.pop('_end'))
                current_segment['source_paths'] = sorted(set(current_segment['source_paths']))
                segments.append(current_segment)
            current_segment = {
                '_start': normalized_date,
                '_end': normalized_date,
                'primary_extension': row.primary_extension,
                'format_family': row.format_family,
                'system_guess': row.system_guess,
                'path_semantic': path_semantics.get(row.directory),
                'file_count': 1,
                'selected_files': [row.path],
                'source_paths': [row.directory],
            }
            current_signature = signature
        else:
            current_segment['_end'] = normalized_date
            current_segment['file_count'] += 1
            current_segment['selected_files'].append(row.path)
            current_segment['source_paths'].append(row.directory)
        previous_date = normalized_date

    if current_segment is not None:
        current_segment['time_range_display'] = _display_range(current_segment.pop('_start'), current_segment.pop('_end'))
        current_segment['source_paths'] = sorted(set(current_segment['source_paths']))
        segments.append(current_segment)

    selected_rows = [row for _, row in selected]
    selected_extensions = _sort_extensions([row.primary_extension for row in selected_rows])

    return {
        'strategy': 'single_format' if len(selected_extensions) <= 1 else 'stitched',
        'format_preference': list(_FORMAT_PREFERENCE),
        'coverage_complete': not coverage_gaps,
        'coverage_gaps': coverage_gaps,
        'selected_file_count': len(selected_rows),
        'selected_files': [row.path for row in selected_rows],
        'selected_primary_extensions': selected_extensions,
        'selected_format_families': sorted({row.format_family for row in selected_rows}),
        'segment_count': len(segments),
        'segments': segments,
    }


def build_dataset_families(files: list[InventoryFile], *, schema_signatures: dict[str, str] | None = None) -> list[DatasetFamily]:
    schema_signatures = schema_signatures or {}
    pdf_rows = build_pdf_manifest_rows(files)

    by_physical_group: dict[tuple[str | None, str], list[InventoryFile]] = defaultdict(list)
    for item in files:
        reason = _discard_reason(item)
        if reason is not None:
            continue
        by_physical_group[(item.system_guess, str(item.series_prefix))].append(item)

    groups_by_prefix: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (system_guess, series_prefix), rows in sorted(by_physical_group.items(), key=lambda kv: ((kv[0][0] or ''), kv[0][1])):
        groups_by_prefix[series_prefix].append(_group_signature(system_guess, series_prefix, rows))

    out: list[DatasetFamily] = []
    for series_prefix in sorted(groups_by_prefix):
        groups = groups_by_prefix[series_prefix]
        parent = list(range(len(groups)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            root_left = find(left)
            root_right = find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        for left in range(len(groups)):
            for right in range(left + 1, len(groups)):
                if _groups_compatible(groups[left], groups[right]):
                    union(left, right)

        clusters: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for index, group in enumerate(groups):
            clusters[find(index)].append(group)

        cluster_payloads: list[dict[str, Any]] = []
        for cluster_groups in clusters.values():
            rows = [row for group in cluster_groups for row in group['rows']]
            if len(rows) < MIN_FILES_FOR_PATTERN_VALIDATION and any(row.pattern_name for row in rows):
                continue

            geo_coverage = sorted({row.geo_code for row in rows if row.geo_code})
            partition_type = classify_partition(set(geo_coverage)) if geo_coverage else 'Unknown'
            date_codes = [row.date_code for row in rows if row.date_code]
            date_format = infer_date_format(date_codes) if date_codes else None
            time_min, time_max = _time_bounds(date_codes, date_format)
            time_range_display = _display_range(time_min, time_max)
            source_paths = sorted({row.directory for row in rows})
            member_files = sorted({row.path for row in rows})
            path_semantics = _build_path_semantics(rows, date_format, time_max)
            source_systems = sorted({group['system_guess'] for group in cluster_groups if group['system_guess']})
            system_guess = source_systems[0] if len(source_systems) == 1 else ('MULTI' if source_systems else None)
            primary_extensions = _sort_extensions([row.primary_extension for row in rows])
            format_families = sorted({row.format_family for row in rows})
            physical_variants = _build_physical_variants(cluster_groups, path_semantics)
            preferred_working_series = _build_preferred_working_series(rows, date_format, path_semantics)
            associated_docs = [match.__dict__ for match in associate_pdfs(series_prefix, source_paths, pdf_rows)]
            signatures = sorted({schema_signatures.get(path, '') for path in member_files if schema_signatures.get(path)})

            cluster_payloads.append({
                'system_guess': system_guess,
                'source_systems': source_systems,
                'series_prefix': series_prefix,
                'partition_type': partition_type,
                'date_format': date_format,
                'time_range_display': time_range_display,
                'time_min': time_min,
                'file_count': len(rows),
                'member_files': member_files,
                'source_paths': source_paths,
                'geo_coverage': geo_coverage,
                'path_semantics': path_semantics,
                'format_families': format_families,
                'primary_extensions': primary_extensions,
                'physical_variants': physical_variants,
                'preferred_working_series': preferred_working_series,
                'associated_docs': associated_docs,
                'schema_signatures': signatures,
            })

        cluster_payloads.sort(key=lambda row: (row['time_min'] or 0, -row['file_count'], row['series_prefix'] or ''))
        for index, payload in enumerate(cluster_payloads, start=1):
            family_id = series_prefix if len(cluster_payloads) == 1 else f'{series_prefix}__{index}'
            out.append(DatasetFamily(
                family_id=family_id,
                system_guess=payload['system_guess'],
                source_systems=payload['source_systems'],
                series_prefix=payload['series_prefix'],
                partition_type=payload['partition_type'],
                date_format=payload['date_format'],
                time_range=payload['time_range_display'],
                time_range_display=payload['time_range_display'],
                file_count=payload['file_count'],
                member_files=payload['member_files'],
                files=payload['member_files'],
                source_paths=payload['source_paths'],
                geo_coverage=payload['geo_coverage'],
                path_semantics=payload['path_semantics'],
                format_families=payload['format_families'],
                primary_extensions=payload['primary_extensions'],
                physical_variants=payload['physical_variants'],
                preferred_working_series=payload['preferred_working_series'],
                associated_docs=payload['associated_docs'],
                schema_signatures=payload['schema_signatures'],
            ))

    out.sort(key=lambda row: (row.series_prefix or '', row.family_id))
    return out


def _compact_family_summary_row(family: DatasetFamily) -> dict[str, Any]:
    preferred = family.preferred_working_series or {}
    issues: list[str] = []
    if family.system_guess == 'MULTI':
        issues.append('multi_source_system_family')
    if family.partition_type == 'Unknown':
        issues.append('unknown_partition_type')
    if family.date_format is None:
        issues.append('missing_date_format')
    if not family.associated_docs:
        issues.append('no_associated_docs')
    if preferred.get('strategy') == 'stitched':
        issues.append('stitched_preferred_working_series')
    if preferred.get('coverage_gaps'):
        issues.append('coverage_gaps')

    return {
        'family_id': family.family_id,
        'series_prefix': family.series_prefix,
        'system_guess': family.system_guess,
        'source_systems': list(family.source_systems),
        'partition_type': family.partition_type,
        'date_format': family.date_format,
        'time_range_display': family.time_range_display,
        'file_count': family.file_count,
        'source_path_count': len(family.source_paths),
        'geo_coverage_count': len(family.geo_coverage),
        'geo_coverage': list(family.geo_coverage[:10]),
        'format_families': list(family.format_families),
        'primary_extensions': list(family.primary_extensions),
        'physical_variant_count': len(family.physical_variants),
        'associated_doc_count': len(family.associated_docs),
        'preferred_working_series': {
            'strategy': preferred.get('strategy'),
            'coverage_complete': preferred.get('coverage_complete'),
            'gap_count': len(preferred.get('coverage_gaps') or []),
            'selected_file_count': preferred.get('selected_file_count'),
            'selected_primary_extensions': list(preferred.get('selected_primary_extensions') or []),
            'segment_count': preferred.get('segment_count'),
        },
        'issues': issues,
    }


def build_dataset_family_summary(files: list[InventoryFile], families: list[DatasetFamily]) -> dict[str, Any]:
    discarded: dict[str, list[str]] = defaultdict(list)
    discarded_counts: Counter[str] = Counter()
    eligible_file_count = 0

    for item in files:
        reason = _discard_reason(item)
        if reason is None:
            eligible_file_count += 1
            continue
        discarded_counts[reason] += 1
        if len(discarded[reason]) < 25:
            discarded[reason].append(item.path)

    families_by_partition = Counter(family.partition_type for family in families)
    families_by_date_format = Counter(family.date_format or 'None' for family in families)
    families_by_system_shape = Counter('single_system' if len(family.source_systems) <= 1 else 'multi_system' for family in families)
    working_series_strategies = Counter((family.preferred_working_series or {}).get('strategy') or 'none' for family in families)
    preferred_extensions = Counter()
    matched_doc_urls: set[str] = set()

    compact_rows = [_compact_family_summary_row(family) for family in families]
    compact_by_id = {row['family_id']: row for row in compact_rows}

    for family in families:
        preferred = family.preferred_working_series or {}
        for extension in preferred.get('selected_primary_extensions') or []:
            preferred_extensions[extension] += 1
        for doc in family.associated_docs or []:
            url = str(doc.get('url') or '')
            if url:
                matched_doc_urls.add(url)

    orphan_docs = [
        {'url': row.url, 'filename': row.filename}
        for row in build_pdf_manifest_rows(files)
        if row.url not in matched_doc_urls
    ]

    largest_families = [compact_by_id[family.family_id] for family in sorted(families, key=lambda row: (-row.file_count, row.family_id))[:50]]
    suspicious_families = [row for row in compact_rows if row['issues']]
    stitched_families = [row for row in compact_rows if row['preferred_working_series']['strategy'] == 'stitched']
    gap_families = [row for row in compact_rows if row['preferred_working_series']['gap_count'] > 0]
    families_without_docs = [row for row in compact_rows if row['associated_doc_count'] == 0]
    multi_source_families = [row for row in compact_rows if len(row['source_systems']) > 1]

    return {
        'input_file_count': len(files),
        'eligible_file_count': eligible_file_count,
        'discarded_file_count': len(files) - eligible_file_count,
        'discarded_by_reason': {
            reason: {'count': discarded_counts[reason], 'sample_paths': samples}
            for reason, samples in sorted(discarded.items())
        },
        'family_count': len(families),
        'families_by_partition': dict(sorted(families_by_partition.items())),
        'families_by_date_format': dict(sorted(families_by_date_format.items())),
        'families_by_system_shape': dict(sorted(families_by_system_shape.items())),
        'working_series': {
            'strategies': dict(sorted(working_series_strategies.items())),
            'preferred_primary_extensions': dict(sorted(preferred_extensions.items(), key=lambda item: (_EXTENSION_PRIORITY.get(item[0], 99), item[0]))),
            'families_with_gaps': [row['family_id'] for row in gap_families],
        },
        'docs': {
            'attached_doc_count': sum(len(family.associated_docs) for family in families),
            'orphan_doc_count': len(orphan_docs),
            'orphan_docs_top_100': orphan_docs[:100],
            'families_without_docs': [row['family_id'] for row in families_without_docs],
        },
        'top_families': {
            'largest_by_file_count': largest_families,
            'stitched_working_series': stitched_families[:100],
            'coverage_gaps': gap_families[:100],
            'multi_source': multi_source_families[:100],
            'suspicious': suspicious_families[:100],
        },
        'family_index': compact_rows,
    }