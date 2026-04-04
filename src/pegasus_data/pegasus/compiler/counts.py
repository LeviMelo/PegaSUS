from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

from ..canonical.schema import CanonicalRecord, CompiledObservable


def compile_counts(records: Iterable[CanonicalRecord], *, family: str, support_keys: Sequence[str], subgroup_keys: Sequence[str] = ()) -> CompiledObservable:
    counts: dict[tuple, float] = defaultdict(float)
    source_systems: set[str] = set()
    support_role = None
    for record in records:
        support_role = support_role or record.support_role
        source_systems.add(record.source.get("system", ""))
        key = tuple(record.support.get(name) for name in support_keys) + tuple(record.subgroups.get(name) for name in subgroup_keys)
        counts[key] += float(record.weight)
    values = []
    for key, value in sorted(counts.items()):
        row = {name: key[idx] for idx, name in enumerate(support_keys)}
        offset = len(support_keys)
        for idx, name in enumerate(subgroup_keys):
            row[name] = key[offset + idx]
        row["value"] = value
        values.append(row)
    return CompiledObservable(
        family=family,
        support_role=support_role or "unknown",
        support_grain=list(support_keys),
        measure="count",
        representation="extensive",
        values=values,
        lineage={"sources": sorted(source_systems), "compiler": "compile_counts"},
        uncertainty={"count_model": "poisson", "notes": []},
    )
