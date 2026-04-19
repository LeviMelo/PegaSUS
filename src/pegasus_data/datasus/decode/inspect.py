from __future__ import annotations

import csv
import gzip
import json
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .dbase import iter_dbase_rows, load_dbase_metadata

_STRUCTURED_EXTS = {'.dbf', '.dbc', '.json', '.xml', '.csv'}


@dataclass(frozen=True)
class DecodedFilePreview:
    path: str
    file_format: str
    field_names: list[str]
    sample_rows: list[dict[str, Any]]
    source_path: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key).upper(): value for key, value in row.items()}


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
        if rows:
            return [_normalize_row(item) for item in rows]
    if isinstance(payload, dict):
        list_candidates = [
            value for value in payload.values()
            if isinstance(value, list) and any(isinstance(item, dict) for item in value)
        ]
        if list_candidates:
            best = max(list_candidates, key=lambda value: len(value))
            return [_normalize_row(item) for item in best if isinstance(item, dict)]
        return [_normalize_row(payload)]
    return []


def _xml_rows(path: Path) -> list[dict[str, Any]]:
    root = ET.parse(path).getroot()
    repeated: dict[str, list[ET.Element]] = {}
    for child in list(root):
        repeated.setdefault(child.tag, []).append(child)
    repeated = {tag: nodes for tag, nodes in repeated.items() if len(nodes) > 1}
    if repeated:
        tag, nodes = max(repeated.items(), key=lambda item: len(item[1]))
        rows: list[dict[str, Any]] = []
        for node in nodes:
            row = {sub.tag.upper(): (sub.text or '').strip() for sub in list(node)}
            if row:
                rows.append(row)
        if rows:
            return rows
    row = {child.tag.upper(): (child.text or '').strip() for child in list(root)}
    return [row] if row else []


def _csv_rows(path: Path, *, sample_rows: int) -> list[dict[str, Any]]:
    with path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, Any]] = []
        for row in reader:
            rows.append(_normalize_row(dict(row)))
            if len(rows) >= sample_rows:
                break
    return rows


def _choose_archive_member(names: list[str]) -> str | None:
    ranked: list[tuple[int, str]] = []
    for name in names:
        lower = name.lower()
        for extension in ('.json', '.xml', '.csv', '.dbf', '.dbc'):
            if lower.endswith(extension):
                rank = {'.json': 5, '.xml': 4, '.csv': 3, '.dbf': 2, '.dbc': 1}[extension]
                ranked.append((rank, name))
                break
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][1]


def _inspect_zip(path: Path, *, sample_rows: int) -> DecodedFilePreview:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith('/')]
        chosen = _choose_archive_member(names)
        if chosen is None:
            rows = [{'ARCHIVE_MEMBER': name} for name in names[:sample_rows]]
            return DecodedFilePreview(
                path=str(path),
                file_format='zip',
                field_names=['ARCHIVE_MEMBER'],
                sample_rows=rows,
                warnings=['zip archive does not contain an obvious structured primary member'],
            )
        suffix = Path(chosen).suffix.lower()
        with archive.open(chosen) as handle:
            data = handle.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(data)
            temp_path = Path(temp.name)
        try:
            preview = inspect_file(str(temp_path), sample_rows=sample_rows, source_path=str(path))
            warnings = list(preview.warnings)
            warnings.append(f'parsed archive member: {chosen}')
            return DecodedFilePreview(
                path=str(path),
                file_format=f'zip:{preview.file_format}',
                field_names=preview.field_names,
                sample_rows=preview.sample_rows,
                source_path=str(path),
                warnings=warnings,
            )
        finally:
            temp_path.unlink(missing_ok=True)


def _inspect_gzip(path: Path, *, sample_rows: int) -> DecodedFilePreview:
    target_name = path.stem
    suffix = Path(target_name).suffix.lower()
    with gzip.open(path, 'rb') as handle:
        data = handle.read()
    with tempfile.NamedTemporaryFile(suffix=suffix or '.tmp', delete=False) as temp:
        temp.write(data)
        temp_path = Path(temp.name)
    try:
        preview = inspect_file(str(temp_path), sample_rows=sample_rows, source_path=str(path))
        warnings = list(preview.warnings)
        warnings.append(f'parsed gzip payload: {target_name}')
        return DecodedFilePreview(
            path=str(path),
            file_format=f'gzip:{preview.file_format}',
            field_names=preview.field_names,
            sample_rows=preview.sample_rows,
            source_path=str(path),
            warnings=warnings,
        )
    finally:
        temp_path.unlink(missing_ok=True)


def inspect_file(path: str, *, sample_rows: int = 5, source_path: str | None = None) -> DecodedFilePreview:
    target = Path(path)
    suffixes = [suffix.lower() for suffix in target.suffixes]
    if not suffixes:
        raise RuntimeError(f'unsupported file format: {path}')
    suffix = suffixes[-1]
    if suffix in {'.dbf', '.dbc'}:
        metadata = load_dbase_metadata(path)
        rows: list[dict[str, Any]] = []
        for row in iter_dbase_rows(path):
            rows.append(row.fields)
            if len(rows) >= sample_rows:
                break
        return DecodedFilePreview(
            path=str(target),
            file_format=metadata.file_format,
            field_names=metadata.field_names,
            sample_rows=rows,
            source_path=source_path,
        )
    if suffix == '.json':
        payload = json.loads(target.read_text(encoding='utf-8'))
        rows = _json_rows(payload)[:sample_rows]
        field_names = sorted({key for row in rows for key in row})
        return DecodedFilePreview(str(target), 'json', field_names, rows, source_path=source_path)
    if suffix == '.xml':
        rows = _xml_rows(target)[:sample_rows]
        field_names = sorted({key for row in rows for key in row})
        return DecodedFilePreview(str(target), 'xml', field_names, rows, source_path=source_path)
    if suffix == '.csv':
        rows = _csv_rows(target, sample_rows=sample_rows)
        field_names = sorted({key for row in rows for key in row})
        return DecodedFilePreview(str(target), 'csv', field_names, rows, source_path=source_path)
    if suffix == '.zip':
        return _inspect_zip(target, sample_rows=sample_rows)
    if suffix == '.gz':
        return _inspect_gzip(target, sample_rows=sample_rows)
    raise RuntimeError(f'unsupported file format: {path}')


def inspect_dbase_file(path: str, *, sample_rows: int = 5) -> DecodedFilePreview:
    return inspect_file(path, sample_rows=sample_rows)
