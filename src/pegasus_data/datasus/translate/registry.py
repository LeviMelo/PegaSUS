from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class VariableTranslation:
    scope: str
    variable: str
    kind: str
    label: str
    value_map: dict[str, str] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TranslationRegistry:
    def __init__(self, entries: list[VariableTranslation]) -> None:
        self.entries = entries
        self._by_scope_var = {(e.scope.upper(), e.variable.upper()): e for e in entries}

    def resolve(self, variable: str, *, scope: str | None = None) -> VariableTranslation | None:
        variable_u = variable.upper()
        if scope:
            hit = self._by_scope_var.get((scope.upper(), variable_u))
            if hit is not None:
                return hit
        return self._by_scope_var.get(('GLOBAL', variable_u))

    def to_dict(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.entries]
