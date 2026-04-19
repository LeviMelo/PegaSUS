from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from ...common.io import read_jsonl, read_text_lines, write_jsonl
from .heuristics import classify_path_type, infer_pattern_components, is_excluded_path, is_probably_structured_data


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    url: str
    directory: str
    filename: str
    extension: str
    primary_extension: str | None
    format_family: str
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
    parsed = infer_pattern_components(path)
    directory = path.rsplit('/', 1)[0] if '/' in path else ''
    filename = str(parsed['filename'])
    extension = str(parsed['extension'])
    path_type = classify_path_type(path)
    pattern_name = None
    series_prefix = None
    geo_code = None
    date_code = None
    if path_type == "Primary" and is_probably_structured_data(path):
        pattern_name = parsed['pattern_name']
        series_prefix = parsed['series_prefix']
        geo_code = parsed['geo_code']
        date_code = parsed['date_code']
    return ManifestEntry(
        path=path,
        url=url,
        directory=directory,
        filename=filename,
        extension=extension,
        primary_extension=parsed['primary_extension'],
        format_family=str(parsed['format_family']),
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
    out: list[ManifestEntry] = []
    for row in read_jsonl(path):
        row.setdefault('primary_extension', None)
        row.setdefault('format_family', 'unknown')
        out.append(ManifestEntry(**row))
    return out


def write_manifest_jsonl(path: str, entries: list[ManifestEntry]) -> None:
    write_jsonl(path, (entry.to_dict() for entry in entries))
