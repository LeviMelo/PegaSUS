from __future__ import annotations

from dataclasses import asdict, dataclass

from .registry import TranslationRegistry

_ALLOWED_KINDS = {'cat', 'date', 'mun', 'uf', 'num', 'txt', 'code', 'id', 'flag', 'unknown'}


@dataclass(frozen=True)
class TranslationValidationReport:
    errors: list[str]
    warnings: list[str]
    entry_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def validate_translation_registry(registry: TranslationRegistry) -> TranslationValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()
    for entry in registry.entries:
        key = (entry.scope.upper(), entry.variable.upper())
        if key in seen:
            errors.append(f'duplicate entry for {entry.scope}:{entry.variable}')
        seen.add(key)
        if entry.kind not in _ALLOWED_KINDS:
            errors.append(f'unknown kind {entry.kind!r} for {entry.scope}:{entry.variable}')
        if entry.kind == 'cat' and not entry.value_map:
            warnings.append(f'categorical variable without value map: {entry.scope}:{entry.variable}')
    return TranslationValidationReport(errors=errors, warnings=warnings, entry_count=len(registry.entries))
