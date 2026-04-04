from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import tempfile

from ...config import get_settings
from ..models import RawSourceRow, SourceFileMetadata


class DatasusDecodeError(RuntimeError):
    pass


@contextmanager
def dbc_as_temp_dbf(path: str):
    try:
        import datasus_dbc
    except ImportError as exc:
        raise DatasusDecodeError('datasus-dbc is required to read .dbc files') from exc
    source = Path(path)
    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        datasus_dbc.decompress(str(source), str(temp_path))
        yield temp_path
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def open_dbf(path: str | Path, *, encoding: str | None = None):
    try:
        from dbfread import DBF
    except ImportError as exc:
        raise DatasusDecodeError('dbfread is required to read DBF/DBC contents') from exc
    return DBF(
        str(path),
        encoding=encoding or get_settings().datasus_default_encoding,
        ignore_missing_memofile=True,
        char_decode_errors='ignore',
        lowernames=False,
        load=False,
    )


def load_dbase_metadata(path: str, *, encoding: str | None = None) -> SourceFileMetadata:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == '.dbc':
        with dbc_as_temp_dbf(path) as dbf_path:
            table = open_dbf(dbf_path, encoding=encoding)
            fields = [field.name for field in table.fields]
    elif suffix == '.dbf':
        table = open_dbf(path, encoding=encoding)
        fields = [field.name for field in table.fields]
    else:
        raise DatasusDecodeError(f'Unsupported file format: {path}')
    return SourceFileMetadata(
        source_system='DATASUS_GENERIC',
        dataset=source.stem,
        path=path,
        encoding=encoding or get_settings().datasus_default_encoding,
        file_format=suffix.lstrip('.'),
        field_names=fields,
        schema_version='dbase_v2',
    )


def iter_dbase_rows(path: str, *, encoding: str | None = None):
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == '.dbc':
        with dbc_as_temp_dbf(path) as dbf_path:
            yield from _iter_dbf_rows(str(dbf_path), raw_file=path, encoding=encoding)
        return
    if suffix == '.dbf':
        yield from _iter_dbf_rows(path, raw_file=path, encoding=encoding)
        return
    raise DatasusDecodeError(f'Unsupported file format: {path}')


def _iter_dbf_rows(dbf_path: str, *, raw_file: str, encoding: str | None = None):
    table = open_dbf(dbf_path, encoding=encoding)
    for index, record in enumerate(table, start=1):
        yield RawSourceRow(
            raw_file=raw_file,
            row_number=index,
            fields={str(k).upper(): v for k, v in dict(record).items()},
        )
