from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

from ...common.io import read_jsonl, read_text_lines, write_jsonl
from .heuristics import DATA_EXTENSIONS, PATTERNS, classify_path_type, is_excluded_path


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    url: str
    directory: str
    filename: str
    extension: str
    path_components: list[str]
    source: str
    scan_id: str | None
    path_type: str
    pattern_name: str | None
    series_prefix: str | None
    geo_code: str | None
    date_code: str | None
    raw_listing_facts: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_url_or_path(raw: str) -> tuple[str, str]:
    if "://" in raw:
        parsed = urlparse(raw)
        return raw, parsed.path
    path = raw
    url = raw if raw.startswith("ftp://") else f"ftp://ftp.datasus.gov.br{raw}"
    return url, path


def parse_manifest_line(raw: str, *, scan_id: str | None = None, source: str = "datasus_ftp") -> ManifestEntry | None:
    raw = raw.strip()
    if not raw:
        return None
    url, path = _parse_url_or_path(raw)
    if is_excluded_path(path):
        return None
    pure = PurePosixPath(path)
    directory = str(pure.parent)
    filename = pure.name
    extension = pure.suffix.lower()
    stem = pure.stem
    path_type = classify_path_type(path)
    pattern_name = None
    series_prefix = None
    geo_code = None
    date_code = None
    if extension in DATA_EXTENSIONS and path_type == "Primary":
        for candidate_name, pattern in PATTERNS.items():
            match = pattern.match(stem)
            if match:
                pattern_name = candidate_name
                series_prefix = match.group(1).upper()
                geo_code = match.group(2).upper()
                date_code = match.group(3)
                break
    return ManifestEntry(
        path=path,
        url=url,
        directory=directory,
        filename=filename,
        extension=extension,
        path_components=[part for part in directory.split("/") if part],
        source=source,
        scan_id=scan_id,
        path_type=path_type,
        pattern_name=pattern_name,
        series_prefix=series_prefix,
        geo_code=geo_code,
        date_code=date_code,
        raw_listing_facts=None,
    )


def parse_manifest_text(path: str, *, scan_id: str | None = None) -> list[ManifestEntry]:
    rows: list[ManifestEntry] = []
    for line in read_text_lines(path):
        parsed = parse_manifest_line(line, scan_id=scan_id)
        if parsed is not None:
            rows.append(parsed)
    return rows


def read_manifest_jsonl(path: str) -> list[ManifestEntry]:
    return [ManifestEntry(**row) for row in read_jsonl(path)]


def write_manifest_jsonl(path: str, entries: list[ManifestEntry]) -> None:
    write_jsonl(path, (entry.to_dict() for entry in entries))
