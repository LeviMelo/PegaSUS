from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .registry import TranslationRegistry, VariableTranslation


@dataclass(frozen=True)
class TranslatedFieldProfile:
    variable: str
    scope: str
    kind: str | None
    label: str | None
    rules: list[str]
    aliases: list[str]
    samples: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _translate_scalar(value: Any, entry: VariableTranslation | None) -> Any:
    if entry is None or value is None:
        return value
    raw = str(value).strip()
    if raw == '':
        return None
    if entry.kind == 'cat':
        return entry.value_map.get(raw, raw)
    result: Any = raw
    for rule in entry.rules:
        result = _apply_rule(result, rule)
    return result


def _apply_rule(value: Any, rule: str) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text == '':
        return None
    if rule == 'ibge6':
        digits = ''.join(ch for ch in text if ch.isdigit())
        return digits[:6] if len(digits) >= 6 else digits
    if rule == 'ibge7':
        digits = ''.join(ch for ch in text if ch.isdigit())
        return digits[:7] if len(digits) >= 7 else digits
    if rule == 'cid10':
        return text.upper().replace('.', '')
    if rule == 'date8':
        digits = ''.join(ch for ch in text if ch.isdigit())
        return digits if len(digits) == 8 else text
    return text


def translate_field_samples(variable: str, raw_samples: list[str], registry: TranslationRegistry, *, scope: str | None = None) -> TranslatedFieldProfile:
    entry = registry.resolve(variable, scope=scope)
    translated_samples = []
    for raw in raw_samples:
        translated_samples.append({'raw': raw, 'label': _translate_scalar(raw, entry) if entry else raw})
    return TranslatedFieldProfile(
        variable=variable,
        scope=scope or 'GLOBAL',
        kind=entry.kind if entry else None,
        label=entry.label if entry else None,
        rules=list(entry.rules) if entry else [],
        aliases=list(entry.aliases) if entry else [],
        samples=translated_samples,
    )


def translate_row_fields(fields: dict[str, Any], registry: TranslationRegistry, *, scope: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field_name, value in fields.items():
        entry = registry.resolve(field_name, scope=scope)
        out[field_name] = _translate_scalar(value, entry)
    return out
