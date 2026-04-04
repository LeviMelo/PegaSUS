from __future__ import annotations

from typing import Callable, Iterable, Sequence

from .counts import compile_counts
from ..canonical.schema import CanonicalRecord, CompiledObservable


def compile_threshold_counts(records: Iterable[CanonicalRecord], *, family: str, support_keys: Sequence[str], field_name: str, predicate: Callable[[object], bool], subgroup_keys: Sequence[str] = ()) -> CompiledObservable:
    filtered = [record for record in records if predicate(record.continuous.get(field_name))]
    return compile_counts(filtered, family=family, support_keys=support_keys, subgroup_keys=subgroup_keys)
