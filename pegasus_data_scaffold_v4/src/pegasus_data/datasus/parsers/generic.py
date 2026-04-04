from __future__ import annotations

from pathlib import Path

from ..decode.dbase import iter_dbase_rows, load_dbase_metadata
from ..discovery.heuristics import infer_system_guess
from .base import DatasusParser
from ..models import RawSourceRow, SourceFileMetadata, SourceNormalizedRow


class GenericDatasusDbaseParser(DatasusParser):
    source_system = 'DATASUS_GENERIC'
    schema_version = 'datasus_generic_v2'

    def detect_file(self, path: str) -> bool:
        return Path(path).suffix.lower() in {'.dbc', '.dbf'}

    def load_metadata(self, path: str) -> SourceFileMetadata:
        metadata = load_dbase_metadata(path)
        return SourceFileMetadata(
            source_system=infer_system_guess(str(Path(path).parent)) or self.source_system,
            dataset=Path(path).stem,
            path=metadata.path,
            encoding=metadata.encoding,
            file_format=metadata.file_format,
            field_names=metadata.field_names,
            schema_version=self.schema_version,
        )

    def iter_raw_rows(self, path: str):
        yield from iter_dbase_rows(path)

    def normalize_raw_row(self, row: RawSourceRow) -> SourceNormalizedRow:
        return SourceNormalizedRow(
            source=infer_system_guess(str(Path(row.raw_file).parent)) or self.source_system,
            dataset=Path(row.raw_file).stem,
            raw_file=row.raw_file,
            row_number=row.row_number,
            fields=row.fields,
            parse_warnings=[],
            encoding=None,
            schema_version=self.schema_version,
        )
