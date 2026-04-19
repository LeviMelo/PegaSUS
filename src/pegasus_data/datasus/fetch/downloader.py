from __future__ import annotations

import ftplib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from ...common.hashing import sha256_file
from ...common.storage import ensure_parent
from ...config import get_settings
from .planner import DatasusDownloadPlan


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _existing_metadata(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _finalize_metadata(plan: DatasusDownloadPlan, *, local_path: Path, status: str) -> dict:
    metadata = {
        **asdict(plan),
        'local_path': str(local_path),
        'source': 'datasus_ftp',
        'downloaded_at': _now(),
        'size_bytes': local_path.stat().st_size,
        'sha256': sha256_file(local_path),
        'transport': 'ftp',
        'status': status,
    }
    metadata_path = ensure_parent(plan.metadata_path)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    return metadata


def _download_one(plan: DatasusDownloadPlan, *, overwrite: bool = False, dry_run: bool = False) -> dict:
    target = Path(plan.target_path)
    if dry_run:
        return {
            **asdict(plan),
            'local_path': str(target),
            'status': 'planned',
        }
    if target.exists() and not overwrite:
        existing = _existing_metadata(Path(plan.metadata_path))
        if existing is not None:
            existing['status'] = 'cached'
            return existing
        return _finalize_metadata(plan, local_path=target, status='cached')

    settings = get_settings()
    ensure_parent(target)
    temp_path = target.with_suffix(target.suffix + '.part')
    parsed = urlparse(plan.source_url)
    host = parsed.hostname or settings.datasus_ftp_host
    ftp = ftplib.FTP(host, timeout=settings.datasus_download_timeout_seconds)
    ftp.login()
    ftp.set_pasv(True)
    try:
        with temp_path.open('wb') as handle:
            ftp.retrbinary(f"RETR {parsed.path}", handle.write)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    temp_path.replace(target)
    return _finalize_metadata(plan, local_path=target, status='downloaded')


def download_plans(
    plans: list[DatasusDownloadPlan],
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    return [_download_one(plan, overwrite=overwrite, dry_run=dry_run) for plan in plans]
