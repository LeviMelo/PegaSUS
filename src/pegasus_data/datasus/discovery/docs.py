from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from rapidfuzz import fuzz
except ImportError:
    class _FuzzFallback:
        @staticmethod
        def partial_ratio(left: str, right: str) -> float:
            if not left and not right:
                return 100.0
            if not left or not right:
                return 0.0
            return round(SequenceMatcher(None, left, right).ratio() * 100, 2)

    fuzz = _FuzzFallback()

from .heuristics import (
    KEYWORD_BONUS,
    PDF_KEYWORDS,
    PDF_RELEVANCE_THRESHOLD,
    WEIGHT_FUZZY_NAME,
    WEIGHT_FUZZY_PATH,
    WEIGHT_PROXIMITY,
)
from .manifest import ManifestEntry


@dataclass(frozen=True)
class PdfMatch:
    url: str
    score: float
    filename: str


@dataclass(frozen=True)
class FamilyDocumentEntry:
    family_id: str
    url: str
    filename: str
    score: float | None
    local_path: str | None
    extraction_status: str
    content_type: str | None
    excerpt: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def tree_distance(a_parts: list[str], b_parts: list[str]) -> int:
    common = 0
    for left, right in zip(a_parts, b_parts):
        if left == right:
            common += 1
        else:
            break
    return (len(a_parts) - common) + (len(b_parts) - common)


def score_pdf_candidate(series_name: str, data_path_parts: list[str], pdf_entry: ManifestEntry) -> float:
    dist = tree_distance(data_path_parts, pdf_entry.path_components)
    if dist > 4:
        return -1.0
    pdf_name = pdf_entry.filename.rsplit(".", 1)[0].lower()
    series_context = f"{series_name} {' '.join(data_path_parts[-2:])}".lower()
    pdf_context = f"{pdf_name} {' '.join(pdf_entry.path_components[-2:])}".lower()
    fuzzy_name = fuzz.partial_ratio(series_name.lower(), pdf_name)
    fuzzy_path = fuzz.partial_ratio(series_context, pdf_context)
    proximity = max(0, 100 - dist * 20)
    bonus = KEYWORD_BONUS if any(keyword in pdf_name for keyword in PDF_KEYWORDS) else 0
    return (WEIGHT_PROXIMITY * proximity) + (WEIGHT_FUZZY_NAME * fuzzy_name) + (WEIGHT_FUZZY_PATH * fuzzy_path) + bonus


def associate_pdfs(series_name: str, source_paths: list[str], manifest_rows: list[ManifestEntry]) -> list[PdfMatch]:
    if not source_paths:
        return []
    data_path_parts = [part for part in source_paths[0].split("/") if part]
    matches: list[PdfMatch] = []
    for row in manifest_rows:
        if row.extension != ".pdf":
            continue
        score = score_pdf_candidate(series_name, data_path_parts, row)
        if score >= PDF_RELEVANCE_THRESHOLD:
            matches.append(PdfMatch(url=row.url, score=round(score, 2), filename=row.filename))
    matches.sort(key=lambda item: item.score, reverse=True)
    return matches


def _candidate_local_paths(url: str, filename: str, doc_root: str | Path) -> list[Path]:
    root = Path(doc_root)
    parsed = urlparse(url)
    path = Path(parsed.path.lstrip('/')) if parsed.path else None
    candidates = [root / filename]
    if path is not None:
        candidates.append(root / path)
        candidates.append(root / path.name)
    out: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


def _extract_pdf_text(path: Path, *, max_chars: int) -> tuple[str | None, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return None, 'pdf_parser_unavailable'
    try:
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages[:3]:
            chunks.append((page.extract_text() or '').strip())
        text = '\n'.join(chunk for chunk in chunks if chunk).strip()
        return (text[:max_chars] if text else None), ('ok' if text else 'empty')
    except Exception:
        return None, 'extract_failed'


def extract_document_excerpt(path: str | Path, *, max_chars: int = 4000) -> tuple[str | None, str, str | None]:
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix in {'.txt', '.md', '.csv', '.json', '.xml', '.html', '.htm'}:
        try:
            text = target.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            text = target.read_text(encoding='latin1', errors='ignore')
        text = text.strip()
        return (text[:max_chars] if text else None), ('ok' if text else 'empty'), suffix.lstrip('.')
    if suffix == '.pdf':
        excerpt, status = _extract_pdf_text(target, max_chars=max_chars)
        return excerpt, status, 'pdf'
    return None, 'unsupported_format', suffix.lstrip('.') or None


def build_family_document_registry(
    families: list[dict[str, Any]],
    *,
    doc_root: str | Path,
    max_chars: int = 4000,
) -> list[FamilyDocumentEntry]:
    out: list[FamilyDocumentEntry] = []
    for family in families:
        family_id = str(family.get('family_id') or '')
        for doc in family.get('associated_docs') or []:
            url = str(doc.get('url') or '')
            filename = str(doc.get('filename') or Path(urlparse(url).path).name or '')
            local_path = None
            excerpt = None
            status = 'missing_local_copy'
            content_type = None
            for candidate in _candidate_local_paths(url, filename, doc_root):
                if candidate.exists():
                    local_path = str(candidate)
                    excerpt, status, content_type = extract_document_excerpt(candidate, max_chars=max_chars)
                    break
            out.append(FamilyDocumentEntry(
                family_id=family_id,
                url=url,
                filename=filename,
                score=float(doc['score']) if doc.get('score') is not None else None,
                local_path=local_path,
                extraction_status=status,
                content_type=content_type,
                excerpt=excerpt,
            ))
    return out
