from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceFileMetadata:
    source_system: str
    dataset: str | None
    path: str
    encoding: str | None
    file_format: str
    field_names: list[str]
    schema_version: str


@dataclass(frozen=True)
class RawSourceRow:
    raw_file: str
    row_number: int
    fields: dict[str, Any]


@dataclass(frozen=True)
class SourceNormalizedRow:
    source: str
    dataset: str
    raw_file: str
    row_number: int
    fields: dict[str, Any]
    parse_warnings: list[str] = field(default_factory=list)
    encoding: str | None = None
    schema_version: str | None = None
