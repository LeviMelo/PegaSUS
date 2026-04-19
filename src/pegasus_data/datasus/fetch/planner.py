from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from ...config import get_settings


@dataclass(frozen=True)
class DatasusDownloadPlan:
    asset_kind: str
    family_id: str
    selection_rank: int
    selection_reason: str
    source_url: str
    source_path: str
    filename: str
    target_path: str
    metadata_path: str
    geo_code: str | None
    date_code: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _asset_root(root: str | Path | None, *, asset_kind: str) -> Path:
    if root is not None:
        return Path(root)
    settings = get_settings()
    return settings.data_root / 'raw' / 'datasus' / ('docs' if asset_kind == 'doc' else 'candidates')


def _plan_target_path(source_path: str, *, root: Path) -> Path:
    parsed_path = PurePosixPath(source_path)
    relative = Path(*[part for part in parsed_path.parts if part not in {'/'}])
    return root / relative


def _normalize_asset_entry(entry: dict[str, Any], *, asset_kind: str) -> dict[str, Any]:
    source_url = str(entry.get('source_url') or entry.get('url') or '')
    source_path = str(entry.get('source_path') or urlparse(source_url).path or '')
    return {
        'asset_kind': asset_kind,
        'selection_rank': int(entry.get('selection_rank') or 0),
        'selection_reason': str(entry.get('selection_reason') or ''),
        'source_url': source_url,
        'source_path': source_path,
        'filename': str(entry.get('filename') or PurePosixPath(source_path).name),
        'geo_code': entry.get('geo_code'),
        'date_code': entry.get('date_code'),
    }


def plan_family_candidate_downloads(
    selection: dict[str, Any],
    *,
    asset_kind: str,
    root: str | Path | None = None,
) -> list[DatasusDownloadPlan]:
    if asset_kind not in {'data', 'doc'}:
        raise ValueError(f'unsupported asset kind: {asset_kind}')
    family_id = str(selection.get('family_id') or '')
    entries = selection.get('selected_data_files' if asset_kind == 'data' else 'selected_docs') or []
    asset_root = _asset_root(root, asset_kind=asset_kind)
    out: list[DatasusDownloadPlan] = []
    for entry in entries:
        normalized = _normalize_asset_entry(dict(entry), asset_kind=asset_kind)
        source_path = normalized['source_path']
        target = _plan_target_path(source_path, root=asset_root)
        out.append(DatasusDownloadPlan(
            asset_kind=asset_kind,
            family_id=family_id,
            selection_rank=normalized['selection_rank'],
            selection_reason=normalized['selection_reason'],
            source_url=normalized['source_url'],
            source_path=source_path,
            filename=normalized['filename'],
            target_path=str(target),
            metadata_path=str(target) + '.metadata.json',
            geo_code=normalized['geo_code'],
            date_code=normalized['date_code'],
        ))
    return out
