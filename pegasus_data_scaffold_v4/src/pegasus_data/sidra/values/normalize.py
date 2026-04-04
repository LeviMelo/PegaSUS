from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


KNOWN_META_KEYS = {
    'NC', 'NN', 'MC', 'MN', 'V', 'D1C', 'D1N', 'D2C', 'D2N', 'D3C', 'D3N', 'D4C', 'D4N', 'D5C', 'D5N'
}


@dataclass(frozen=True)
class SidraValueRow:
    aggregate_id: int
    variable_id: str
    variable_name: str | None
    locality_id: str | None
    locality_name: str | None
    period_id: str | None
    period_name: str | None
    value: float | None
    raw_value: str | None
    dimensions: dict[str, dict[str, str | None]]
    raw_row: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_float(value: Any) -> float | None:
    if value in (None, '', '...'):
        return None
    try:
        return float(str(value).replace(',', '.'))
    except ValueError:
        return None


def normalize_value_payload(*, aggregate_id: int, variable_id: int | str, payload: Any) -> list[SidraValueRow]:
    rows: list[SidraValueRow] = []
    if not isinstance(payload, list):
        return rows
    for item in payload:
        if not isinstance(item, dict):
            continue
        locality_id = item.get('NC') or item.get('MC')
        locality_name = item.get('NN') or item.get('MN')
        period_id = item.get('D3C') or item.get('D2C') or item.get('P')
        period_name = item.get('D3N') or item.get('D2N') or item.get('PN')
        variable_name = item.get('D1N') if item.get('D1C') == str(variable_id) else item.get('D1N')
        dims: dict[str, dict[str, str | None]] = {}
        for idx in range(1, 10):
            code_key = f'D{idx}C'
            name_key = f'D{idx}N'
            if item.get(code_key) is None and item.get(name_key) is None:
                continue
            dims[f'D{idx}'] = {'code': item.get(code_key), 'name': item.get(name_key)}
        rows.append(SidraValueRow(
            aggregate_id=aggregate_id,
            variable_id=str(variable_id),
            variable_name=variable_name,
            locality_id=str(locality_id) if locality_id not in (None, '') else None,
            locality_name=str(locality_name) if locality_name not in (None, '') else None,
            period_id=str(period_id) if period_id not in (None, '') else None,
            period_name=str(period_name) if period_name not in (None, '') else None,
            value=_coerce_float(item.get('V')),
            raw_value=str(item.get('V')) if item.get('V') is not None else None,
            dimensions=dims,
            raw_row=item,
        ))
    return rows
