from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

from ..discovery.heuristics import format_normalized_date, infer_format_family, infer_pattern_components, infer_primary_extension, is_probably_structured_data, normalize_datecode


@dataclass(frozen=True)
class FamilyCandidateFile:
    source_path: str
    source_url: str
    filename: str
    directory: str
    extension: str
    primary_extension: str | None
    format_family: str
    geo_code: str | None
    date_code: str | None
    normalized_date: int | None
    time_display: str | None
    path_semantic: str | None
    selection_rank: int
    selection_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FamilyCandidateDoc:
    url: str
    filename: str
    score: float | None
    selection_rank: int
    selection_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FamilyCandidateSelection:
    family_id: str
    series_prefix: str | None
    partition_type: str
    date_format: str | None
    time_range_display: str | None
    member_file_count: int
    selected_data_files: list[FamilyCandidateFile]
    selected_docs: list[FamilyCandidateDoc]

    def to_dict(self) -> dict[str, Any]:
        return {
            'family_id': self.family_id,
            'series_prefix': self.series_prefix,
            'partition_type': self.partition_type,
            'date_format': self.date_format,
            'time_range_display': self.time_range_display,
            'member_file_count': self.member_file_count,
            'selected_data_files': [row.to_dict() for row in self.selected_data_files],
            'selected_docs': [row.to_dict() for row in self.selected_docs],
        }


def _parse_member_file(path: str, *, date_format: str | None, path_semantics: dict[str, str]) -> dict[str, Any]:
    pure = PurePosixPath(path)
    parsed = infer_pattern_components(path)
    filename = str(parsed['filename'])
    geo_code = parsed['geo_code']
    date_code = parsed['date_code']
    normalized_date = None
    time_display = None
    if date_code and date_format:
        try:
            normalized_date = normalize_datecode(date_code, date_format)
            time_display = format_normalized_date(normalized_date)
        except Exception:
            normalized_date = None
    return {
        'source_path': path,
        'source_url': f'ftp://ftp.datasus.gov.br{path}',
        'filename': filename,
        'directory': str(pure.parent),
        'extension': parsed['extension'],
        'primary_extension': parsed['primary_extension'],
        'format_family': parsed['format_family'],
        'geo_code': geo_code,
        'date_code': date_code,
        'normalized_date': normalized_date,
        'time_display': time_display,
        'path_semantic': path_semantics.get(str(pure.parent)),
    }


def _primary_rank(path_semantic: str | None) -> int:
    if path_semantic == '[Primary]':
        return 2
    if path_semantic == '[Legacy Archive]':
        return 1
    return 0


def _sort_candidates(parsed_files: list[dict[str, Any]], *, prefer_br: bool) -> list[dict[str, Any]]:
    return sorted(
        parsed_files,
        key=lambda row: (
            row.get('normalized_date') or -1,
            _primary_rank(row.get('path_semantic')),
            1 if prefer_br and row.get('geo_code') == 'BR' else 0,
            row.get('filename') or '',
        ),
        reverse=True,
    )


def _reason_for_selection(
    candidate: dict[str, Any],
    *,
    partition_type: str,
    seen_geos: set[str],
    seen_dates: set[int],
    first_pick: bool,
) -> str:
    reasons: list[str] = []
    geo_code = str(candidate.get('geo_code') or '')
    normalized_date = candidate.get('normalized_date')
    if first_pick:
        if partition_type == 'Mixed-Partition' and geo_code == 'BR':
            reasons.append('latest nation-wide member in mixed family')
        elif partition_type == 'Nation-Wide':
            reasons.append('latest nation-wide family member')
        else:
            reasons.append('most recent family member')
    else:
        if geo_code and geo_code not in seen_geos:
            reasons.append(f'adds geo coverage ({geo_code})')
        if normalized_date is not None and normalized_date not in seen_dates:
            reasons.append('adds time coverage')
    if candidate.get('path_semantic') == '[Primary]':
        reasons.append('preferred primary path')
    primary_extension = candidate.get('primary_extension')
    if primary_extension:
        reasons.append(f'format={str(primary_extension).lstrip(".")}')
    if not reasons:
        reasons.append('best remaining recent candidate')
    return '; '.join(reasons)


def _select_diverse_files(parsed_files: list[dict[str, Any]], *, partition_type: str, max_data_files: int) -> list[FamilyCandidateFile]:
    if not parsed_files:
        return []
    selected: list[FamilyCandidateFile] = []
    seen_geos: set[str] = set()
    seen_dates: set[int] = set()
    remaining = list(parsed_files)

    if partition_type == 'Mixed-Partition':
        br_candidates = [row for row in remaining if row.get('geo_code') == 'BR']
        if br_candidates:
            first = _sort_candidates(br_candidates, prefer_br=True)[0]
            reason = _reason_for_selection(first, partition_type=partition_type, seen_geos=seen_geos, seen_dates=seen_dates, first_pick=True)
            selected.append(FamilyCandidateFile(selection_rank=1, selection_reason=reason, **first))
            seen_geos.add(str(first.get('geo_code') or ''))
            if first.get('normalized_date') is not None:
                seen_dates.add(int(first['normalized_date']))
            remaining = [row for row in remaining if row['source_path'] != first['source_path']]

    while remaining and len(selected) < max_data_files:
        if not selected:
            chosen = _sort_candidates(remaining, prefer_br=(partition_type != 'State-Partitioned'))[0]
        else:
            chosen = max(
                remaining,
                key=lambda row: (
                    1 if str(row.get('geo_code') or '') not in seen_geos else 0,
                    1 if row.get('normalized_date') not in seen_dates else 0,
                    _primary_rank(row.get('path_semantic')),
                    row.get('normalized_date') or -1,
                    row.get('filename') or '',
                ),
            )
        reason = _reason_for_selection(
            chosen,
            partition_type=partition_type,
            seen_geos=seen_geos,
            seen_dates=seen_dates,
            first_pick=not selected,
        )
        selected.append(FamilyCandidateFile(selection_rank=len(selected) + 1, selection_reason=reason, **chosen))
        seen_geos.add(str(chosen.get('geo_code') or ''))
        if chosen.get('normalized_date') is not None:
            seen_dates.add(int(chosen['normalized_date']))
        remaining = [row for row in remaining if row['source_path'] != chosen['source_path']]

    return selected


def select_family_candidates(
    family: dict[str, Any],
    *,
    max_data_files: int = 3,
    max_docs: int = 5,
) -> FamilyCandidateSelection:
    member_files = [str(path) for path in family.get('member_files', family.get('files', [])) or []]
    path_semantics = dict(family.get('path_semantics') or {})
    date_format = family.get('date_format')
    partition_type = str(family.get('partition_type') or 'Unknown')

    parsed_files = [
        _parse_member_file(path, date_format=date_format, path_semantics=path_semantics)
        for path in member_files
    ]
    parsed_files = [row for row in parsed_files if is_probably_structured_data(row['source_path'])]
    parsed_files = _sort_candidates(parsed_files, prefer_br=(partition_type != 'State-Partitioned'))

    selected_docs: list[FamilyCandidateDoc] = []
    docs = sorted(
        list(family.get('associated_docs') or []),
        key=lambda row: (float(row.get('score') or 0.0), str(row.get('filename') or row.get('url') or '')),
        reverse=True,
    )
    seen_doc_urls: set[str] = set()
    for row in docs:
        url = str(row.get('url') or '')
        if not url or url in seen_doc_urls:
            continue
        seen_doc_urls.add(url)
        selected_docs.append(FamilyCandidateDoc(
            url=url,
            filename=str(row.get('filename') or PurePosixPath(url).name),
            score=float(row['score']) if row.get('score') is not None else None,
            selection_rank=len(selected_docs) + 1,
            selection_reason='top associated document by relevance score',
        ))
        if len(selected_docs) >= max_docs:
            break

    return FamilyCandidateSelection(
        family_id=str(family.get('family_id') or ''),
        series_prefix=family.get('series_prefix'),
        partition_type=partition_type,
        date_format=date_format,
        time_range_display=family.get('time_range_display'),
        member_file_count=len(member_files),
        selected_data_files=_select_diverse_files(parsed_files, partition_type=partition_type, max_data_files=max_data_files),
        selected_docs=selected_docs,
    )
