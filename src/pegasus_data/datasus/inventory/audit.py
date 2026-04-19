from __future__ import annotations

from collections import Counter
from typing import Any


def _issue(code: str, severity: str, summary: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        'code': code,
        'severity': severity,
        'summary': summary,
        'detail': detail,
    }


def _family_audit_row(family: dict[str, Any]) -> dict[str, Any]:
    family_id = str(family.get('family_id') or '')
    preferred = dict(family.get('preferred_working_series') or {})
    physical_variants = list(family.get('physical_variants') or [])
    associated_docs = list(family.get('associated_docs') or [])
    source_systems = list(family.get('source_systems') or [])
    geo_coverage = list(family.get('geo_coverage') or [])
    issues: list[dict[str, Any]] = []
    recommendations: list[str] = []

    gaps = list(preferred.get('coverage_gaps') or [])
    if gaps:
        issues.append(_issue(
            'coverage_gaps',
            'warning',
            f'preferred working series has {len(gaps)} uncovered period(s)',
            {
                'gaps': gaps,
                'gap_count': len(gaps),
                'strategy': preferred.get('strategy'),
                'segment_count': preferred.get('segment_count'),
                'segments': list(preferred.get('segments') or []),
                'selected_primary_extensions': list(preferred.get('selected_primary_extensions') or []),
                'selected_format_families': list(preferred.get('selected_format_families') or []),
            },
        ))
        recommendations.append('inspect the uncovered periods and decide whether additional legacy/open-data files should be admitted into preferred_working_series')

    if preferred.get('strategy') == 'stitched':
        issues.append(_issue(
            'stitched_preferred_working_series',
            'info',
            'preferred working series is composed of multiple segments',
            {
                'segment_count': preferred.get('segment_count'),
                'segments': list(preferred.get('segments') or []),
                'selected_primary_extensions': list(preferred.get('selected_primary_extensions') or []),
            },
        ))
        recommendations.append('verify that stitched segments are expected and not caused by avoidable grouping or format-selection mistakes')

    if not preferred.get('coverage_complete', True):
        recommendations.append('inspect preferred_working_series.coverage_gaps and physical_variants together before downstream downloads/profiling')

    if family.get('partition_type') == 'Unknown':
        issues.append(_issue(
            'unknown_partition_type',
            'warning',
            'family partition type could not be confidently classified',
            {
                'partition_type': family.get('partition_type'),
                'geo_coverage': geo_coverage,
                'geo_coverage_count': len(geo_coverage),
                'physical_variants': physical_variants,
            },
        ))
        recommendations.append('inspect geo coverage and filename pattern extraction for this family')

    if family.get('date_format') is None:
        issues.append(_issue(
            'missing_date_format',
            'warning',
            'family date format could not be inferred',
            {
                'date_format': family.get('date_format'),
                'time_range_display': family.get('time_range_display'),
                'physical_variants': physical_variants,
            },
        ))
        recommendations.append('inspect date code extraction and filename pattern logic for this family')

    if family.get('system_guess') == 'MULTI' or len(source_systems) > 1:
        issues.append(_issue(
            'multi_source_system_family',
            'info',
            'family spans multiple source systems or FTP roots',
            {
                'system_guess': family.get('system_guess'),
                'source_systems': source_systems,
                'physical_variant_count': len(physical_variants),
                'physical_variants': physical_variants,
            },
        ))
        recommendations.append('confirm that all physical variants are truly the same logical series and not an over-merge')

    if not associated_docs:
        issues.append(_issue(
            'no_associated_docs',
            'info',
            'family has no associated documentation PDFs',
            {
                'associated_doc_count': 0,
                'source_paths': list(family.get('source_paths') or []),
                'physical_variants': physical_variants,
            },
        ))
        recommendations.append('check PDF audit output for nearby orphaned documentation under the same endpoint')

    return {
        'family_id': family_id,
        'series_prefix': family.get('series_prefix'),
        'system_guess': family.get('system_guess'),
        'source_systems': source_systems,
        'partition_type': family.get('partition_type'),
        'date_format': family.get('date_format'),
        'time_range_display': family.get('time_range_display'),
        'file_count': int(family.get('file_count') or 0),
        'geo_coverage': geo_coverage,
        'source_paths': list(family.get('source_paths') or []),
        'format_families': list(family.get('format_families') or []),
        'primary_extensions': list(family.get('primary_extensions') or []),
        'physical_variant_count': len(physical_variants),
        'physical_variants': physical_variants,
        'preferred_working_series': preferred,
        'associated_doc_count': len(associated_docs),
        'associated_docs': associated_docs,
        'issue_count': len(issues),
        'issues': issues,
        'recommendations': recommendations,
    }


def build_family_audit(
    families: list[dict[str, Any]],
    *,
    family_id: str | None = None,
    only_issues: bool = False,
) -> dict[str, Any]:
    selected = families
    if family_id is not None:
        selected = [row for row in families if str(row.get('family_id') or '') == family_id]

    audits = [_family_audit_row(family) for family in selected]
    if only_issues:
        audits = [row for row in audits if row['issue_count'] > 0]

    issue_counts = Counter(
        issue['code']
        for row in audits
        for issue in row['issues']
    )

    families_by_issue: dict[str, list[str]] = {}
    for code in sorted(issue_counts):
        families_by_issue[code] = sorted(
            row['family_id']
            for row in audits
            if any(issue['code'] == code for issue in row['issues'])
        )

    return {
        'family_count': len(audits),
        'issue_counts': dict(sorted(issue_counts.items())),
        'families_by_issue': families_by_issue,
        'families': audits,
    }