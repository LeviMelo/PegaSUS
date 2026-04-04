from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class FieldProfile:
    name: str
    primitive_type: str
    non_null_count: int
    null_count: int
    distinct_sample_count: int
    samples: list[str]
    signals: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stringify(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip()


def infer_primitive_type(values: list[str], field_name: str) -> tuple[str, list[str]]:
    signals: list[str] = []
    non_empty = [v for v in values if v != '']
    upper_name = field_name.upper()
    if not non_empty:
        return 'empty', signals
    if upper_name.startswith('DT') or upper_name.endswith('DATA') or 'DT' in upper_name[:3]:
        signals.append('date_name_hint')
    if upper_name.startswith('CODMUN'):
        signals.append('municipality_name_hint')
        return 'municipality_code', signals
    if all(v.isdigit() for v in non_empty):
        lengths = {len(v) for v in non_empty[:100]}
        if lengths.issubset({6, 7}) and upper_name.startswith('CODMUN'):
            return 'municipality_code', signals
        if lengths == {2} and upper_name.startswith('DT'):
            return 'date_fragment', signals
        if max(lengths) <= 2 and len(set(non_empty[:50])) <= 20:
            return 'categorical_code', signals
        return 'integer', signals
    if all(_looks_date(v) for v in non_empty[:50]):
        signals.append('date_value_hint')
        return 'date', signals
    if all(_looks_float(v) for v in non_empty[:50]):
        return 'numeric', signals
    if len(set(non_empty[:100])) <= 20:
        return 'categorical_text', signals
    return 'text', signals


def _looks_float(value: str) -> bool:
    try:
        float(value.replace(',', '.'))
        return True
    except ValueError:
        return False


def _looks_date(value: str) -> bool:
    raw = value.replace('-', '').replace('/', '')
    return raw.isdigit() and len(raw) in {6, 8}


def profile_field(name: str, values: Iterable[Any], *, sample_limit: int = 12) -> FieldProfile:
    string_values = [_stringify(v) for v in values]
    primitive_type, signals = infer_primitive_type(string_values, name)
    non_null = [v for v in string_values if v != '']
    sample_counter = Counter(non_null)
    samples = [value for value, _ in sample_counter.most_common(sample_limit)]
    return FieldProfile(
        name=name,
        primitive_type=primitive_type,
        non_null_count=len(non_null),
        null_count=len(string_values) - len(non_null),
        distinct_sample_count=len(set(non_null[:1000])),
        samples=samples,
        signals=signals,
    )
