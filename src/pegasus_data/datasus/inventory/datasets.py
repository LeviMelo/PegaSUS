from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from ..discovery.docs import associate_pdfs
from ..discovery.heuristics import (
    MIN_FILES_FOR_PATTERN_VALIDATION,
    classify_partition,
    classify_path_semantic,
    format_normalized_date,
    infer_date_format,
    infer_inner_candidate_name,
    normalize_datecode,
)
from .files import InventoryFile


@dataclass(frozen=True)
class DatasetFamily:
    family_id: str
    system_guess: str | None
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
    associated_docs: list[dict]
    schema_signatures: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def build_dataset_families(files: list[InventoryFile], *, schema_signatures: dict[str, str] | None = None) -> list[DatasetFamily]:
    schema_signatures = schema_signatures or {}
    by_key: dict[tuple[str | None, str | None], list[InventoryFile]] = defaultdict(list)
    for item in files:
        if item.path_type != 'Primary':
            continue
        key = (item.system_guess, item.series_prefix or infer_inner_candidate_name(item.filename))
        by_key[key].append(item)

    out: list[DatasetFamily] = []
    for (system_guess, prefix), rows in sorted(by_key.items(), key=lambda kv: (kv[0][0] or '', kv[0][1] or '')):
        if len(rows) < MIN_FILES_FOR_PATTERN_VALIDATION and any(r.pattern_name for r in rows):
            continue
        geo_coverage = sorted({row.geo_code for row in rows if row.geo_code})
        partition = classify_partition(set(geo_coverage)) if geo_coverage else 'Unknown'
        date_codes = [row.date_code for row in rows if row.date_code]
        date_format = infer_date_format(date_codes) if date_codes else None
        time_range_display = None
        path_semantics: dict[str, str] = {}
        if date_format and date_codes:
            normalized = [normalize_datecode(code, date_format) for code in date_codes]
            time_range_display = f"{format_normalized_date(min(normalized))} to {format_normalized_date(max(normalized))}"
            for directory in sorted({row.directory for row in rows}):
                path_rows = [row for row in rows if row.directory == directory and row.date_code]
                path_dates = [normalize_datecode(row.date_code, date_format) for row in path_rows]
                if path_dates:
                    path_semantics[directory] = classify_path_semantic(directory, global_max_date=max(normalized), path_max_date=max(path_dates), date_format=date_format)
        files_for_family = sorted(row.path for row in rows)
        signatures = sorted({schema_signatures.get(path, '') for path in files_for_family if schema_signatures.get(path)})
        docs = [match.__dict__ for match in associate_pdfs(prefix or (system_guess or 'UNKNOWN'), sorted({r.directory for r in rows}), [
            type('ManifestLike', (), {'path': f.path, 'url': f'ftp://ftp.datasus.gov.br{f.path}', 'directory': f.directory, 'filename': f.filename, 'extension': f.extension, 'path_components': [p for p in f.directory.split('/') if p], 'source': 'datasus_ftp', 'scan_id': None, 'path_type': f.path_type, 'pattern_name': f.pattern_name, 'series_prefix': f.series_prefix, 'geo_code': f.geo_code, 'date_code': f.date_code, 'raw_listing_facts': None})
            for f in files
        ])]
        family_id = f"{system_guess or 'UNKNOWN'}:{prefix or infer_inner_candidate_name(rows[0].filename)}"
        if signatures:
            family_id += f":s{len(signatures)}"
        out.append(DatasetFamily(
            family_id=family_id,
            system_guess=system_guess,
            series_prefix=prefix,
            partition_type=partition,
            date_format=date_format,
            time_range=time_range_display,
            time_range_display=time_range_display,
            file_count=len(rows),
            member_files=files_for_family,
            files=files_for_family,
            source_paths=sorted({row.directory for row in rows}),
            geo_coverage=geo_coverage,
            path_semantics=path_semantics,
            associated_docs=docs,
            schema_signatures=signatures,
        ))
    return out
