from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TranslationBundle:
    family_id: str
    prompt_text: str
    variables: list[dict[str, Any]]
    docs: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_translation_bundle(
    family: dict[str, Any],
    profile_rows: list[dict[str, Any]],
    variable_catalog: list[dict[str, Any]],
    *,
    document_registry: list[dict[str, Any]] | None = None,
    max_fields: int = 120,
) -> TranslationBundle:
    profile_map = {str(row.get('path') or ''): row for row in profile_rows}
    catalog_map = {str(row.get('variable') or '').upper(): row for row in variable_catalog}
    variables: list[dict[str, Any]] = []
    for path in family.get('files', []) or []:
        row = profile_map.get(str(path))
        if not row:
            continue
        for field in row.get('field_profiles', []) or []:
            name = str(field.get('name') or '').upper()
            merged = dict(field)
            if name in catalog_map:
                merged['catalog'] = catalog_map[name]
            merged['path'] = str(path)
            variables.append(merged)

    variables.sort(key=lambda item: (-(item.get('catalog') or {}).get('family_count', 0), str(item.get('name') or '')))
    variables = variables[:max_fields]

    lines: list[str] = [
        'TASK: produce compact translation grammar blocks for this DATASUS dataset family.',
        'OUTPUT ONLY grammar lines using directives: $, @, =, >, ~, %.',
        'Prefer GLOBAL entries for shared variables. Use @ only for real family-specific overrides.',
        'Kinds: cat date mun uf num txt code id flag unknown',
        'Rules available: ibge6 ibge7 cid10 date8 date6 upper stripdigits',
        '',
        f'FAMILY {family.get("family_id")}',
        f'SYSTEM {family.get("system_guess") or "UNKNOWN"}',
        f'PREFIX {family.get("series_prefix") or "UNKNOWN"}',
        f'FILES {family.get("file_count") or 0}',
    ]
    if family.get('time_range_display'):
        lines.append(f'TIME {family.get("time_range_display")}')
    lines.append('')
    docs = family.get('associated_docs') or []
    doc_context = [
        row for row in (document_registry or [])
        if str(row.get('family_id') or '') == str(family.get('family_id') or '')
    ]
    if docs:
        lines.append('DOCS')
        for doc in docs[:12]:
            url = doc.get('url') or ''
            score = doc.get('score')
            lines.append(f'- {score} {url}'.rstrip())
        lines.append('')
    if doc_context:
        lines.append('DOC_EXCERPTS')
        for item in doc_context[:6]:
            status = str(item.get('extraction_status') or 'unknown')
            filename = str(item.get('filename') or '')
            excerpt = str(item.get('excerpt') or '').strip()
            if not excerpt:
                lines.append(f'- {filename} | {status}')
                continue
            compact = ' '.join(excerpt.split())
            lines.append(f'- {filename} | {status} | {compact[:500]}')
        lines.append('')
    lines.append('FIELDS')
    for item in variables:
        name = str(item.get('name') or '')
        primitive = str(item.get('primitive_type') or 'unknown')
        samples = ', '.join((item.get('samples') or [])[:6])
        shared = (item.get('catalog') or {}).get('family_count', 0)
        signals = ','.join((item.get('signals') or [])[:4])
        lines.append(f'- {name} | {primitive} | shared={shared} | sig={signals} | samp={samples}')
    lines.extend(['', 'Return grammar only.'])

    return TranslationBundle(
        family_id=str(family.get('family_id') or ''),
        prompt_text='\n'.join(lines),
        variables=variables,
        docs=list(docs),
    )
