from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .dbase import iter_dbase_rows, load_dbase_metadata


@dataclass(frozen=True)
class DecodedFilePreview:
    path: str
    file_format: str
    field_names: list[str]
    sample_rows: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_dbase_file(path: str, *, sample_rows: int = 5) -> DecodedFilePreview:
    metadata = load_dbase_metadata(path)
    rows: list[dict[str, Any]] = []
    for row in iter_dbase_rows(path):
        rows.append(row.fields)
        if len(rows) >= sample_rows:
            break
    return DecodedFilePreview(
        path=str(Path(path)),
        file_format=metadata.file_format,
        field_names=metadata.field_names,
        sample_rows=rows,
    )
