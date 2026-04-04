from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CanonicalRecord:
    support: dict[str, Any]
    support_role: str
    source: dict[str, Any]
    event_type: str
    code_roles: dict[str, list[str]]
    subgroups: dict[str, Any]
    continuous: dict[str, Any]
    annotations: dict[str, Any]
    weight: float
    quality: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class CompiledObservable:
    family: str
    support_role: str
    support_grain: list[str]
    measure: str
    representation: str
    values: list[dict[str, Any]]
    lineage: dict[str, Any]
    uncertainty: dict[str, Any]
