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


def _download_one(plan: DatasusDownloadPlan) -> dict:
    settings = get_settings()
    target = ensure_parent(plan.target_path)
    parsed = urlparse(plan.source_url)
    host = parsed.hostname or settings.datasus_ftp_host
    path = parsed.path
    ftp = ftplib.FTP(host, timeout=settings.datasus_download_timeout_seconds)
    ftp.login()
    ftp.set_pasv(True)
    try:
        with target.open("wb") as handle:
            ftp.retrbinary(f"RETR {path}", handle.write)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    metadata = {
        **asdict(plan),
        "source": "datasus_ftp",
        "downloaded_at": _now(),
        "size_bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "transport": "ftp",
        "listing_method": "manifest",
        "etag": None,
        "notes": [],
    }
    metadata_path = ensure_parent(plan.metadata_path)
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
    return metadata


def download_manifest_entries(plans: list[DatasusDownloadPlan]) -> list[dict]:
    return [_download_one(plan) for plan in plans]
