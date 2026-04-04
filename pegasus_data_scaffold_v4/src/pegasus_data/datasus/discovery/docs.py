from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

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
