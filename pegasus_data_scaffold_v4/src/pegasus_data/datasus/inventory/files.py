from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import PurePosixPath

from ...common.io import read_jsonl
from ..discovery.heuristics import classify_path_type, infer_system_guess, is_excluded_path, PATTERNS


@dataclass(frozen=True)
class InventoryFile:
    path: str
    directory: str
    filename: str
    extension: str
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
        pure = PurePosixPath(full_path)
        extension = pure.suffix.lower()
        stem = pure.stem
        pattern_name = prefix = geo = date = None
        for candidate_name, pattern in PATTERNS.items():
            match = pattern.match(stem)
            if match:
                pattern_name = candidate_name
                prefix = match.group(1).upper()
                geo = match.group(2).upper()
                date = match.group(3)
                break
        out.append(InventoryFile(
            path=full_path,
            directory=str(pure.parent),
            filename=pure.name,
            extension=extension,
            system_guess=infer_system_guess(str(pure.parent)),
            path_type=classify_path_type(full_path),
            series_prefix=prefix,
            geo_code=geo,
            date_code=date,
            pattern_name=pattern_name,
        ))
    return out
