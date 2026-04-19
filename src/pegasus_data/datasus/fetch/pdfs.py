from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from ...common.io import read_jsonl
from ...config import get_settings
from ..discovery.heuristics import PDF_KEYWORDS
from .planner import DatasusDownloadPlan


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip() or '/dissemin/publicos'
    if not endpoint.startswith('/'):
        endpoint = '/' + endpoint
    return endpoint.rstrip('/')


def _path_under_endpoint(path: str, endpoint: str) -> bool:
    normalized = _normalize_endpoint(endpoint)
    return path == normalized or path.startswith(normalized + '/')


def _scan_pdf_rows(scan_jsonl: str, *, endpoint: str) -> list[dict[str, Any]]:
    normalized_endpoint = _normalize_endpoint(endpoint)
    rows: list[dict[str, Any]] = []
    for row in read_jsonl(scan_jsonl):
        full_path = str(row.get('full_path') or '')
        if not full_path or row.get('entry_type') == 'dir':
            continue
        if not full_path.lower().endswith('.pdf'):
            continue
        if not _path_under_endpoint(full_path, normalized_endpoint):
            continue
        pure = PurePosixPath(full_path)
        rows.append({
            'path': full_path,
            'url': f'ftp://ftp.datasus.gov.br{full_path}',
            'directory': str(pure.parent),
            'filename': pure.name,
        })
    rows.sort(key=lambda item: item['path'])
    return rows


def plan_pdf_downloads_from_scan(
    scan_jsonl: str,
    *,
    endpoint: str = '/dissemin/publicos',
    root: str | None = None,
) -> list[DatasusDownloadPlan]:
    pdf_rows = _scan_pdf_rows(scan_jsonl, endpoint=endpoint)
    asset_root = Path(root) if root is not None else get_settings().data_root / 'raw' / 'datasus' / 'docs'
    normalized_endpoint = _normalize_endpoint(endpoint)
    family_id = f'PDFS:{normalized_endpoint}'

    plans: list[DatasusDownloadPlan] = []
    for index, row in enumerate(pdf_rows, start=1):
        pure = PurePosixPath(str(row['path']))
        relative_parts = [part for part in pure.parts if part != '/']
        target = asset_root.joinpath(*relative_parts)
        plans.append(DatasusDownloadPlan(
            asset_kind='doc',
            family_id=family_id,
            selection_rank=index,
            selection_reason=f'pdf_under_endpoint:{normalized_endpoint}',
            source_url=str(row['url']),
            source_path=str(row['path']),
            filename=str(row['filename']),
            target_path=str(target),
            metadata_path=str(target) + '.metadata.json',
            geo_code=None,
            date_code=None,
        ))
    return plans


def build_pdf_audit(
    scan_jsonl: str,
    *,
    endpoint: str = '/dissemin/publicos',
    families: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pdf_rows = _scan_pdf_rows(scan_jsonl, endpoint=endpoint)
    matched_urls: set[str] = set()

    for family in families or []:
        for doc in family.get('associated_docs') or []:
            url = str(doc.get('url') or '')
            if url:
                matched_urls.add(url)

    by_directory = Counter(row['directory'] for row in pdf_rows)
    orphan_rows = [row for row in pdf_rows if row['url'] not in matched_urls]
    orphan_by_directory = Counter(row['directory'] for row in orphan_rows)

    def is_likely_reference(row: dict[str, Any]) -> bool:
        filename = str(row.get('filename') or '').lower()
        directory = str(row.get('directory') or '').upper()
        return any(keyword in filename for keyword in PDF_KEYWORDS) or any(token in directory for token in ('/DOC', '/DOCS', '/DOCUMENTOS', '/TAB', '/TABELAS'))

    likely_reference_orphans = [row for row in orphan_rows if is_likely_reference(row)]

    top_level_counter = Counter()
    normalized_endpoint = _normalize_endpoint(endpoint)
    endpoint_parts = [part for part in PurePosixPath(normalized_endpoint).parts if part != '/']
    for row in pdf_rows:
        parts = [part for part in PurePosixPath(str(row['path'])).parts if part != '/']
        remainder = parts[len(endpoint_parts):]
        key = remainder[0] if remainder else '(endpoint_root)'
        top_level_counter[key] += 1

    return {
        'endpoint': normalized_endpoint,
        'pdf_count': len(pdf_rows),
        'matched_pdf_count': sum(1 for row in pdf_rows if row['url'] in matched_urls),
        'orphan_pdf_count': len(orphan_rows),
        'likely_reference_orphan_pdf_count': len(likely_reference_orphans),
        'top_level_counts': dict(top_level_counter.most_common(50)),
        'top_pdf_directories': [{'directory': key, 'count': value} for key, value in by_directory.most_common(100)],
        'top_orphan_directories': [{'directory': key, 'count': value} for key, value in orphan_by_directory.most_common(100)],
        'orphan_pdfs_top_200': orphan_rows[:200],
        'likely_reference_orphan_pdfs_top_200': likely_reference_orphans[:200],
    }