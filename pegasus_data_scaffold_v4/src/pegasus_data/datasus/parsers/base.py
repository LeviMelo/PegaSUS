from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from ...pegasus.canonical.schema import CanonicalRecord
from ..models import RawSourceRow, SourceFileMetadata, SourceNormalizedRow


class DatasusParser(ABC):
    source_system: str = 'DATASUS_GENERIC'
    dataset: str | None = None
    schema_version: str = 'v1'

    @abstractmethod
    def detect_file(self, path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def load_metadata(self, path: str) -> SourceFileMetadata:
        raise NotImplementedError

    @abstractmethod
    def iter_raw_rows(self, path: str) -> Iterator[RawSourceRow]:
        raise NotImplementedError

    @abstractmethod
    def normalize_raw_row(self, row: RawSourceRow) -> SourceNormalizedRow:
        raise NotImplementedError

    def iter_normalized_rows(self, path: str) -> Iterator[SourceNormalizedRow]:
        for row in self.iter_raw_rows(path):
            yield self.normalize_raw_row(row)

    def to_canonical(self, row: SourceNormalizedRow) -> CanonicalRecord | None:
        return None
