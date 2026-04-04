from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class VariableTranslation:
    scope: str
    variable: str
    kind: str
    label: str
    value_map: dict[str, str] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TranslationRegistry:
    def __init__(self, entries: list[VariableTranslation]) -> None:
        self.entries = entries
        self._by_scope_var = {(e.scope.upper(), e.variable.upper()): e for e in entries}
        self._by_alias: dict[tuple[str, str], VariableTranslation] = {}
        for entry in entries:
            for alias in entry.aliases:
                self._by_alias[(entry.scope.upper(), alias.upper())] = entry
                if entry.scope.upper() != 'GLOBAL':
                    self._by_alias[('GLOBAL', alias.upper())] = entry

    def resolve(self, variable: str, *, scope: str | None = None) -> VariableTranslation | None:
        variable_u = variable.upper()
        if scope:
            scope_u = scope.upper()
            hit = self._by_scope_var.get((scope_u, variable_u)) or self._by_alias.get((scope_u, variable_u))
            if hit is not None:
                return hit
        return self._by_scope_var.get(('GLOBAL', variable_u)) or self._by_alias.get(('GLOBAL', variable_u))

    def merge(self, *others: 'TranslationRegistry') -> 'TranslationRegistry':
        merged: dict[tuple[str, str], VariableTranslation] = {
            (entry.scope.upper(), entry.variable.upper()): entry for entry in self.entries
        }
        for other in others:
            for entry in other.entries:
                merged[(entry.scope.upper(), entry.variable.upper())] = entry
        return TranslationRegistry(list(merged.values()))

    def coverage_for_variables(self, variables: Iterable[str], *, scopes: Iterable[str] | None = None) -> dict[str, Any]:
        coverage_scopes = [scope for scope in (scopes or []) if scope]
        covered: list[str] = []
        missing: list[str] = []
        for variable in sorted({str(value).upper() for value in variables if str(value).strip()}):
            hit = None
            for scope in coverage_scopes:
                hit = self.resolve(variable, scope=scope)
                if hit is not None:
                    break
            if hit is None:
                hit = self.resolve(variable)
            if hit is None:
                missing.append(variable)
            else:
                covered.append(variable)
        return {
            'variable_count': len(covered) + len(missing),
            'covered_count': len(covered),
            'missing_count': len(missing),
            'covered': covered,
            'missing': missing,
        }

    def to_dict(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.entries]
