from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

from ..canonical.schema import CanonicalRecord, CompiledObservable
from ..registry.codes import CodeQuery, any_code_matches


def compile_code_query_counts(
    records: Iterable[CanonicalRecord],
    *,
    family: str,
    query: CodeQuery,
    support_keys: Sequence[str],
    subgroup_keys: Sequence[str] = (),
) -> CompiledObservable:
    counts: dict[tuple, float] = defaultdict(float)
    sources: set[str] = set()
    support_role: str | None = None
    for record in records:
        role_values = record.code_roles.get(query.role, [])
        annotation_values: list[str] = []
        for value in record.annotations.values():
            if isinstance(value, list):
                annotation_values.extend(str(item) for item in value)
        if not (any_code_matches(role_values, query) or any_code_matches(annotation_values, query)):
            continue
        support_role = support_role or record.support_role
        sources.add(record.source.get("system", ""))
        key = tuple(record.support.get(name) for name in support_keys) + tuple(record.subgroups.get(name) for name in subgroup_keys)
        counts[key] += float(record.weight)
    values: list[dict] = []
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
        lineage={
            "sources": sorted(filter(None, sources)),
            "compiler": "compile_code_query_counts",
            "query": {
                "role": query.role,
                "system": query.system,
                "node": query.node,
                "descendants": query.descendants,
            },
        },
        uncertainty={"count_model": "poisson", "notes": []},
    )
