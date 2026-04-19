from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from hashlib import sha1
from pathlib import Path
import tempfile
from typing import Any

from ...common.hashing import sha256_file
from ...common.storage import ensure_directory, ensure_parent
from ...config import get_settings
from ..decode.inspect import inspect_file
from .fields import FieldProfile, profile_field


@dataclass(frozen=True)
class TableProfile:
    path: str
    file_format: str
    row_count_sampled: int
    field_names: list[str]
    schema_signature: str
    field_profiles: list[FieldProfile]
    source_path: str | None = None
    local_path: str | None = None
    file_hash: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'path': self.path,
            'file_format': self.file_format,
            'row_count_sampled': self.row_count_sampled,
            'field_names': self.field_names,
            'schema_signature': self.schema_signature,
            'field_profiles': [fp.to_dict() for fp in self.field_profiles],
            'source_path': self.source_path,
            'local_path': self.local_path,
            'file_hash': self.file_hash,
            'warnings': list(self.warnings),
        }


def _cache_root() -> Path:
    preferred_root = get_settings().data_root / 'cache' / 'datasus_profiles'
    try:
        return ensure_directory(preferred_root)
    except OSError:
        return ensure_directory(Path(tempfile.gettempdir()) / 'pegasus_data' / 'datasus_profiles')


def _cache_path(path: str, *, file_hash: str, sample_rows: int) -> Path:
    key = sha1(f'{Path(path).resolve()}|{file_hash}|{sample_rows}'.encode('utf-8')).hexdigest()
    return _cache_root() / f'{key}.json'


def _profile_from_payload(payload: dict[str, Any]) -> TableProfile:
    return TableProfile(
        path=str(payload.get('path') or ''),
        file_format=str(payload.get('file_format') or 'unknown'),
        row_count_sampled=int(payload.get('row_count_sampled') or 0),
        field_names=list(payload.get('field_names') or []),
        schema_signature=str(payload.get('schema_signature') or ''),
        field_profiles=[FieldProfile(**field) for field in payload.get('field_profiles') or []],
        source_path=payload.get('source_path'),
        local_path=payload.get('local_path'),
        file_hash=payload.get('file_hash'),
        warnings=list(payload.get('warnings') or []),
    )


def profile_file(
    path: str,
    *,
    sample_rows: int = 500,
    source_path: str | None = None,
    local_path: str | None = None,
) -> TableProfile:
    local = Path(path)
    file_hash = sha256_file(local)
    cache_path = _cache_path(path, file_hash=file_hash, sample_rows=sample_rows)
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding='utf-8'))
        return _profile_from_payload(payload)

    preview = inspect_file(path, sample_rows=sample_rows, source_path=source_path)
    values_by_field: dict[str, list[Any]] = defaultdict(list)
    for row in preview.sample_rows:
        for field_name in preview.field_names:
            values_by_field[field_name].append(row.get(field_name))
    field_profiles = [profile_field(name, values_by_field.get(name, [])) for name in preview.field_names]
    schema_signature = sha1('|'.join(preview.field_names).encode('utf-8')).hexdigest()[:16]
    profile = TableProfile(
        path=str(local),
        file_format=preview.file_format,
        row_count_sampled=len(preview.sample_rows),
        field_names=preview.field_names,
        schema_signature=schema_signature,
        field_profiles=field_profiles,
        source_path=source_path or str(local),
        local_path=local_path or str(local),
        file_hash=file_hash,
        warnings=list(preview.warnings),
    )
    target = ensure_parent(cache_path)
    target.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    return profile


def profile_dbase_file(path: str, *, sample_rows: int = 500) -> TableProfile:
    return profile_file(path, sample_rows=sample_rows)
