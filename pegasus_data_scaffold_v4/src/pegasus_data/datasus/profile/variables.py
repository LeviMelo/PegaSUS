from __future__ import annotations

from collections import Counter, defaultdict
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
    for fam in families:
        family_id = str(fam.get('family_id') or '')
        for path in fam.get('files', []) or []:
            out.setdefault(str(path), set()).add(family_id)
    return out


def build_variable_catalog(profile_rows: list[dict[str, Any]], *, families: list[dict[str, Any]] | None = None, sample_limit: int = 12) -> list[VariableCatalogEntry]:
    path_to_families = _family_index(families or [])
    bucket: dict[str, dict[str, Any]] = {}

    for row in profile_rows:
        path = str(row.get('path') or '')
        families_for_path = path_to_families.get(path) or set()
        profile_fields = row.get('field_profiles') or []
        for field in profile_fields:
            var = str(field.get('name') or '').upper()
            if not var:
                continue
            b = bucket.setdefault(var, {
                'file_paths': set(),
                'family_ids': set(),
                'primitive_types': Counter(),
                'samples': Counter(),
                'signals': Counter(),
                'dataset_overrides': set(),
            })
            b['file_paths'].add(path)
            b['family_ids'].update(families_for_path)
            primitive = str(field.get('primitive_type') or 'unknown')
            b['primitive_types'][primitive] += 1
            for sample in field.get('samples') or []:
                s = str(sample).strip()
                if s:
                    b['samples'][s] += 1
            for sig in field.get('signals') or []:
                b['signals'][str(sig)] += 1
            if families_for_path:
                for fid in families_for_path:
                    b['dataset_overrides'].add(fid)

    out: list[VariableCatalogEntry] = []
    for var in sorted(bucket):
        b = bucket[var]
        out.append(VariableCatalogEntry(
            variable=var,
            family_count=len(b['family_ids']),
            file_count=len(b['file_paths']),
            primitive_types=[name for name, _ in b['primitive_types'].most_common()],
            scopes=sorted(b['family_ids']),
            samples=[name for name, _ in b['samples'].most_common(sample_limit)],
            signals=[name for name, _ in b['signals'].most_common()],
            dataset_overrides=sorted(b['dataset_overrides']),
        ))
    return out
