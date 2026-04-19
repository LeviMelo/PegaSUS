from __future__ import annotations

from dataclasses import dataclass, asdict

from ...common.io import read_jsonl
from ..discovery.heuristics import classify_path_type, infer_pattern_components, infer_system_guess, is_excluded_path


@dataclass(frozen=True)
class InventoryFile:
    path: str
    directory: str
    filename: str
    extension: str
    primary_extension: str | None
    format_family: str
    system_guess: str | None
    path_type: str
    series_prefix: str | None
    geo_code: str | None
    date_code: str | None
    pattern_name: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def inventory_from_scan_jsonl(path: str) -> list[InventoryFile]:
    out: list[InventoryFile] = []
    for row in read_jsonl(path):
        full_path = row['full_path']
        if row.get('entry_type') == 'dir' or is_excluded_path(full_path):
            continue
        parsed = infer_pattern_components(full_path)
        directory = full_path.rsplit('/', 1)[0] if '/' in full_path else ''
        out.append(InventoryFile(
            path=full_path,
            directory=directory,
            filename=str(parsed['filename']),
            extension=str(parsed['extension']),
            primary_extension=parsed['primary_extension'],
            format_family=str(parsed['format_family']),
            system_guess=infer_system_guess(directory),
            path_type=classify_path_type(full_path),
            series_prefix=parsed['series_prefix'],
            geo_code=parsed['geo_code'],
            date_code=parsed['date_code'],
            pattern_name=parsed['pattern_name'],
        ))
    return out
