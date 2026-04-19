from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _normalize_name(name: str) -> str:
    return ''.join(ch for ch in str(name).upper() if ch.isalnum())


def _name_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_name(left), _normalize_name(right)).ratio()


def _family_members(family: dict[str, Any]) -> list[str]:
    return [str(path) for path in family.get('member_files', family.get('files', [])) or []]


@dataclass(frozen=True)
class FamilySimilarityPair:
    family_a: str
    family_b: str
    similarity: float
    shared_variables: list[str]
    family_a_variable_count: int
    family_b_variable_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FamilySimilarityCluster:
    cluster_id: str
    families: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VariableSimilarityCluster:
    cluster_id: str
    family_cluster_id: str
    variables: list[str]
    families: list[str]
    strongest_name_similarity: float
    strongest_value_similarity: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _family_variable_sets(profile_rows: list[dict[str, Any]], families: list[dict[str, Any]]) -> dict[str, set[str]]:
    path_to_family: dict[str, set[str]] = {}
    for family in families:
        family_id = str(family.get('family_id') or '')
        for path in _family_members(family):
            path_to_family.setdefault(path, set()).add(family_id)

    out: dict[str, set[str]] = {}
    for row in profile_rows:
        path = str(row.get('source_path') or row.get('path') or '')
        variables = {
            str(field.get('name') or '').upper()
            for field in row.get('field_profiles') or []
            if str(field.get('name') or '').strip()
        }
        for family_id in path_to_family.get(path, set()):
            out.setdefault(family_id, set()).update(variables)
    return out


def _connected_components(adjacency: dict[str, set[str]]) -> list[list[str]]:
    seen: set[str] = set()
    components: list[list[str]] = []
    for node in adjacency:
        if node in seen:
            continue
        stack = [node]
        component: list[str] = []
        seen.add(node)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda values: (-len(values), values))


def build_family_similarity_report(
    profile_rows: list[dict[str, Any]],
    families: list[dict[str, Any]],
    *,
    similarity_threshold: float = 0.8,
) -> dict[str, Any]:
    variable_sets = _family_variable_sets(profile_rows, families)
    family_ids = sorted(variable_sets)
    pairs: list[FamilySimilarityPair] = []
    adjacency: dict[str, set[str]] = {family_id: set() for family_id in family_ids}

    for idx, family_a in enumerate(family_ids):
        for family_b in family_ids[idx + 1:]:
            left = variable_sets[family_a]
            right = variable_sets[family_b]
            similarity = _jaccard(left, right)
            shared = sorted(left & right)
            pairs.append(FamilySimilarityPair(
                family_a=family_a,
                family_b=family_b,
                similarity=round(similarity, 4),
                shared_variables=shared,
                family_a_variable_count=len(left),
                family_b_variable_count=len(right),
            ))
            if similarity >= similarity_threshold:
                adjacency[family_a].add(family_b)
                adjacency[family_b].add(family_a)

    components = _connected_components(adjacency) if adjacency else []
    clusters = [
        FamilySimilarityCluster(cluster_id=f'family_cluster_{index + 1}', families=component)
        for index, component in enumerate(components)
    ]
    return {
        'threshold': similarity_threshold,
        'family_pairs': [row.to_dict() for row in sorted(pairs, key=lambda row: row.similarity, reverse=True)],
        'family_clusters': [row.to_dict() for row in clusters],
    }


def build_variable_similarity_report(
    profile_rows: list[dict[str, Any]],
    families: list[dict[str, Any]],
    *,
    family_similarity_threshold: float = 0.8,
    name_similarity_threshold: float = 0.85,
    value_similarity_threshold: float = 0.6,
) -> dict[str, Any]:
    family_report = build_family_similarity_report(profile_rows, families, similarity_threshold=family_similarity_threshold)
    path_to_family: dict[str, set[str]] = {}
    for family in families:
        family_id = str(family.get('family_id') or '')
        for path in _family_members(family):
            path_to_family.setdefault(path, set()).add(family_id)

    variable_profiles: dict[str, dict[str, Any]] = {}
    for row in profile_rows:
        path = str(row.get('source_path') or row.get('path') or '')
        scopes = path_to_family.get(path, set())
        for field in row.get('field_profiles') or []:
            variable = str(field.get('name') or '').upper()
            if not variable:
                continue
            profile = variable_profiles.setdefault(variable, {
                'scopes': set(),
                'value_space': set(),
            })
            profile['scopes'].update(scopes)
            profile['value_space'].update(str(sample).strip() for sample in field.get('samples') or [] if str(sample).strip())

    contexts = family_report['family_clusters'] or [
        {'cluster_id': f'family_cluster_{index + 1}', 'families': [str(family.get('family_id') or '')]}
        for index, family in enumerate(families)
    ]
    clusters: list[VariableSimilarityCluster] = []
    for context in contexts:
        context_id = str(context.get('cluster_id') or '')
        context_families = set(str(value) for value in context.get('families') or [])
        context_variables = [
            name for name, profile in variable_profiles.items()
            if profile['scopes'] & context_families
        ]
        adjacency: dict[str, set[str]] = {name: set() for name in context_variables}
        strengths: dict[tuple[str, str], tuple[float, float]] = {}
        for idx, left_name in enumerate(context_variables):
            left_profile = variable_profiles[left_name]
            for right_name in context_variables[idx + 1:]:
                right_profile = variable_profiles[right_name]
                if left_profile['scopes'] & right_profile['scopes']:
                    continue
                name_similarity = _name_similarity(left_name, right_name)
                value_similarity = _jaccard(left_profile['value_space'], right_profile['value_space'])
                if name_similarity >= name_similarity_threshold and value_similarity >= value_similarity_threshold:
                    adjacency[left_name].add(right_name)
                    adjacency[right_name].add(left_name)
                    strengths[(left_name, right_name)] = (name_similarity, value_similarity)
        for component in _connected_components(adjacency):
            if len(component) < 2:
                continue
            strongest_name = 0.0
            strongest_value = 0.0
            component_pairs = [
                strengths.get((left, right)) or strengths.get((right, left))
                for idx, left in enumerate(component)
                for right in component[idx + 1:]
            ]
            for pair in component_pairs:
                if pair is None:
                    continue
                strongest_name = max(strongest_name, pair[0])
                strongest_value = max(strongest_value, pair[1])
            scopes = sorted({
                family_id
                for variable in component
                for family_id in variable_profiles[variable]['scopes']
                if family_id in context_families
            })
            clusters.append(VariableSimilarityCluster(
                cluster_id=f'{context_id}_var_cluster_{len(clusters) + 1}',
                family_cluster_id=context_id,
                variables=component,
                families=scopes,
                strongest_name_similarity=round(strongest_name, 4),
                strongest_value_similarity=round(strongest_value, 4),
            ))

    return {
        'family_similarity': family_report,
        'variable_similarity_thresholds': {
            'name_similarity_threshold': name_similarity_threshold,
            'value_similarity_threshold': value_similarity_threshold,
        },
        'variable_clusters': [row.to_dict() for row in clusters],
    }
