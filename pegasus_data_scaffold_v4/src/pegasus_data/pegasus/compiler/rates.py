from __future__ import annotations

from typing import Iterable

from ..canonical.schema import CompiledObservable


def compile_rates(*, numerator: CompiledObservable, denominator_rows: list[dict], family: str, alpha: float = 0.5, beta: float = 0.5) -> CompiledObservable:
    denominator_index = {tuple((key, value) for key, value in row.items() if key != "value"): float(row["value"]) for row in denominator_rows}
    values: list[dict] = []
    for row in numerator.values:
        key = tuple((name, value) for name, value in row.items() if name != "value")
        denom = denominator_index.get(key)
        if denom is None or denom <= 0:
            continue
        num = float(row["value"])
        shrunk = (num + alpha) / (denom + alpha + beta)
        out = dict(row)
        out["denominator"] = denom
        out["value"] = shrunk
        values.append(out)
    return CompiledObservable(
        family=family,
        support_role=numerator.support_role,
        support_grain=numerator.support_grain,
        measure="rate",
        representation="shrunk_rate",
        values=values,
        lineage={**numerator.lineage, "compiler": "compile_rates"},
        uncertainty={"notes": ["beta-binomial style shrinkage"], "alpha": alpha, "beta": beta},
    )
