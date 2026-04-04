from __future__ import annotations

from dataclasses import dataclass

from .schema import CanonicalRecord


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


def validate_canonical_record(record: CanonicalRecord) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not record.support_role:
        errors.append("missing_support_role")
    if not record.event_type:
        errors.append("missing_event_type")
    municipality = record.support.get("municipality")
    if municipality is None:
        warnings.append("missing_support_municipality")
    if record.quality.get("included") is not True:
        warnings.append("record_marked_excluded")
    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
