from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class VariableCatalogEntry:
    variable: str
    family_count: int
    file_count: int
    primitive_types: list[str]
    scopes: list[str]
    samples: list[str]
    signals: list[str]
    dataset_overrides: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _family_index(families: list[dict[str, Any]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for family in families:
        family_id = str(family.get('family_id') or '')
        for path in family.get('files', []) or []:
            out.setdefault(str(path), set()).add(family_id)
    return out


def build_variable_catalog(
    profile_rows: list[dict[str, Any]],
    *,
    families: list[dict[str, Any]] | None = None,
    sample_limit: int = 12,
) -> list[VariableCatalogEntry]:
    path_to_families = _family_index(families or [])
    bucket: dict[str, dict[str, Any]] = {}

    for row in profile_rows:
        path = str(row.get('path') or '')
        families_for_path = path_to_families.get(path) or set()
        for field in row.get('field_profiles') or []:
            variable = str(field.get('name') or '').upper()
            if not variable:
                continue
            slot = bucket.setdefault(variable, {
                'file_paths': set(),
                'family_ids': set(),
                'primitive_types': Counter(),
                'samples': Counter(),
                'signals': Counter(),
                'dataset_overrides': set(),
            })
            slot['file_paths'].add(path)
            slot['family_ids'].update(families_for_path)
            slot['primitive_types'][str(field.get('primitive_type') or 'unknown')] += 1
            for sample in field.get('samples') or []:
                text = str(sample).strip()
                if text:
                    slot['samples'][text] += 1
            for signal in field.get('signals') or []:
                slot['signals'][str(signal)] += 1
            for family_id in families_for_path:
                slot['dataset_overrides'].add(family_id)

    out: list[VariableCatalogEntry] = []
    for variable in sorted(bucket):
        slot = bucket[variable]
        out.append(VariableCatalogEntry(
            variable=variable,
            family_count=len(slot['family_ids']),
            file_count=len(slot['file_paths']),
            primitive_types=[name for name, _ in slot['primitive_types'].most_common()],
            scopes=sorted(slot['family_ids']),
            samples=[name for name, _ in slot['samples'].most_common(sample_limit)],
            signals=[name for name, _ in slot['signals'].most_common()],
            dataset_overrides=sorted(slot['dataset_overrides']),
        ))
    return out
