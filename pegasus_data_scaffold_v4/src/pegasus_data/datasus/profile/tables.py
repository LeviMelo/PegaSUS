from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any

from ..decode.dbase import iter_dbase_rows, load_dbase_metadata
from .fields import FieldProfile, profile_field


@dataclass(frozen=True)
class TableProfile:
    path: str
    file_format: str
    row_count_sampled: int
    field_names: list[str]
    schema_signature: str
    field_profiles: list[FieldProfile]

    def to_dict(self) -> dict[str, Any]:
        return {
            'path': self.path,
            'file_format': self.file_format,
            'row_count_sampled': self.row_count_sampled,
            'field_names': self.field_names,
            'field_count': len(self.field_names),
            'schema_signature': self.schema_signature,
            'field_profiles': [fp.to_dict() for fp in self.field_profiles],
        }


def profile_dbase_file(path: str, *, sample_rows: int = 500) -> TableProfile:
    metadata = load_dbase_metadata(path)
    values_by_field: dict[str, list[Any]] = defaultdict(list)
    sampled = 0
    for row in iter_dbase_rows(path):
        sampled += 1
        for field_name in metadata.field_names:
            values_by_field[field_name].append(row.fields.get(field_name))
        if sampled >= sample_rows:
            break
    field_profiles = [profile_field(name, values_by_field.get(name, [])) for name in metadata.field_names]
    schema_signature = sha1('|'.join(metadata.field_names).encode('utf-8')).hexdigest()[:16]
    return TableProfile(
        path=str(Path(path)),
        file_format=metadata.file_format,
        row_count_sampled=sampled,
        field_names=metadata.field_names,
        schema_signature=schema_signature,
        field_profiles=field_profiles,
    )
