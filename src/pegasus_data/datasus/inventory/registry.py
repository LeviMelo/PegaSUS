from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FamilyRegistryEntry:
    family_id: str
    system_guess: str | None
    series_prefix: str | None
    partition_type: str
    date_format: str | None
    time_range_display: str | None
    file_count: int
    source_paths: list[str]
    schema_signatures: list[str]
    variable_count: int
    variables: list[str]
    associated_docs: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_family_registry(
    families: list[dict[str, Any]],
    profile_rows: list[dict[str, Any]] | None = None,
) -> list[FamilyRegistryEntry]:
    profile_rows = profile_rows or []
    variables_by_path: dict[str, set[str]] = {}
    for row in profile_rows:
        path = str(row.get('path') or '')
        field_names = {
            str(field.get('name') or '').upper()
            for field in row.get('field_profiles') or []
            if str(field.get('name') or '').strip()
        }
        variables_by_path[path] = field_names

    out: list[FamilyRegistryEntry] = []
    for family in families:
        paths = [str(path) for path in family.get('files', []) or []]
        family_vars: set[str] = set()
        for path in paths:
            family_vars.update(variables_by_path.get(path, set()))
        out.append(FamilyRegistryEntry(
            family_id=str(family.get('family_id') or ''),
            system_guess=family.get('system_guess'),
            series_prefix=family.get('series_prefix'),
            partition_type=str(family.get('partition_type') or 'Unknown'),
            date_format=family.get('date_format'),
            time_range_display=family.get('time_range_display'),
            file_count=int(family.get('file_count') or 0),
            source_paths=list(family.get('source_paths') or []),
            schema_signatures=list(family.get('schema_signatures') or []),
            variable_count=len(family_vars),
            variables=sorted(family_vars),
            associated_docs=list(family.get('associated_docs') or []),
        ))
    return out
