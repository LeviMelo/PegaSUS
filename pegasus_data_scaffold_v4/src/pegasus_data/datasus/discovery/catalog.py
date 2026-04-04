from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import defaultdict

from ...common.io import write_json
from .docs import associate_pdfs
from .heuristics import (
    MIN_FILES_FOR_PATTERN_VALIDATION,
    classify_partition,
    classify_path_semantic,
    format_normalized_date,
    infer_date_format,
    infer_system_guess,
    normalize_datecode,
)
from .manifest import ManifestEntry


@dataclass(frozen=True)
class SeriesCatalogEntry:
    series_id: str
    series_prefix: str
    system_guess: str | None
    partition_type: str
    date_format: str
    time_range_raw: tuple[int, int]
    time_range_display: str
    geo_coverage: list[str]
    file_count: int
    source_paths: list[str]
    path_semantics: dict[str, str]
    associated_pdfs: list[dict]
    validated_pattern: str
    file_samples: list[str]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["time_range_raw"] = list(self.time_range_raw)
        return payload


def build_series_catalog(manifest_rows: list[ManifestEntry]) -> list[SeriesCatalogEntry]:
    by_directory: dict[str, list[ManifestEntry]] = defaultdict(list)
    for row in manifest_rows:
        if row.pattern_name:
            by_directory[row.directory].append(row)

    validated_rows: list[ManifestEntry] = []
    for rows in by_directory.values():
        if len(rows) >= MIN_FILES_FOR_PATTERN_VALIDATION:
            validated_rows.extend(rows)

    by_prefix: dict[str, list[ManifestEntry]] = defaultdict(list)
    for row in validated_rows:
        if row.series_prefix:
            by_prefix[row.series_prefix].append(row)

    out: list[SeriesCatalogEntry] = []
    for prefix, rows in sorted(by_prefix.items()):
        geo_coverage = sorted({row.geo_code for row in rows if row.geo_code})
        partition = classify_partition(set(geo_coverage))
        if partition == "Unknown":
            continue
        date_codes = [row.date_code for row in rows if row.date_code]
        date_format = infer_date_format(date_codes)
        normalized = [normalize_datecode(code, date_format) for code in date_codes]
        if not normalized:
            continue
        min_date = min(normalized)
        max_date = max(normalized)
        system_guess = infer_system_guess(rows[0].directory)
        source_paths = sorted({row.directory for row in rows})
        path_semantics: dict[str, str] = {}
        for path in source_paths:
            path_rows = [row for row in rows if row.directory == path and row.date_code]
            path_dates = [normalize_datecode(row.date_code, date_format) for row in path_rows]
            if path_dates:
                path_semantics[path] = classify_path_semantic(path, global_max_date=max_date, path_max_date=max(path_dates), date_format=date_format)
        pdfs = [match.__dict__ for match in associate_pdfs(prefix, source_paths, manifest_rows)]
        entry = SeriesCatalogEntry(
            series_id=f"{system_guess or 'UNKNOWN'}:{prefix}",
            series_prefix=prefix,
            system_guess=system_guess,
            partition_type=partition,
            date_format=date_format,
            time_range_raw=(min_date, max_date),
            time_range_display=f"{format_normalized_date(min_date)} to {format_normalized_date(max_date)}",
            geo_coverage=geo_coverage,
            file_count=len(rows),
            source_paths=source_paths,
            path_semantics=path_semantics,
            associated_pdfs=pdfs,
            validated_pattern=rows[0].pattern_name or "",
            file_samples=[row.filename for row in rows[:10]],
        )
        out.append(entry)
    return out


def write_series_catalog(path: str, series_rows: list[SeriesCatalogEntry]) -> None:
    write_json(path, [row.to_dict() for row in series_rows])
