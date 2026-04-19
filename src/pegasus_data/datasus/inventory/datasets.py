from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ..discovery.docs import associate_pdfs, build_pdf_manifest_rows
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
    primary_files = [item for item in files if item.path_type != 'Auxiliary']
    pdf_rows = build_pdf_manifest_rows(files)

    by_key: dict[tuple[str | None, str | None], list[InventoryFile]] = defaultdict(list)
    for item in primary_files:
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
            min_date, max_date = min(normalized), max(normalized)
            time_range_display = f"{format_normalized_date(min_date)} to {format_normalized_date(max_date)}"
            rows_by_directory: dict[str, list[InventoryFile]] = defaultdict(list)
            for row in rows:
                if row.date_code:
                    rows_by_directory[row.directory].append(row)
            for directory in sorted(rows_by_directory):
                path_rows = rows_by_directory[directory]
                path_dates = [normalize_datecode(row.date_code, date_format) for row in path_rows if row.date_code]
                if path_dates:
                    path_semantics[directory] = classify_path_semantic(directory, global_max_date=max_date, path_max_date=max(path_dates), date_format=date_format)
        files_for_family = sorted(row.path for row in rows)
        source_paths = sorted({row.directory for row in rows})
        signatures = sorted({schema_signatures.get(path, '') for path in files_for_family if schema_signatures.get(path)})
        docs = [match.__dict__ for match in associate_pdfs(prefix or (system_guess or 'UNKNOWN'), source_paths, pdf_rows)]
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
            source_paths=source_paths,
            geo_coverage=geo_coverage,
            path_semantics=path_semantics,
            associated_docs=docs,
            schema_signatures=signatures,
        ))
    return out