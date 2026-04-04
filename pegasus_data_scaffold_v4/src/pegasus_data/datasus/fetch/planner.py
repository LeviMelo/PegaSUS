from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from ..discovery.manifest import ManifestEntry
from ..discovery.heuristics import infer_system_guess


@dataclass(frozen=True)
class DatasusDownloadPlan:
    source_url: str
    target_path: str
    metadata_path: str
    system: str | None
    prefix: str | None
    geo_code: str | None
    date_code: str | None


def _infer_year(date_code: str | None) -> str:
    if not date_code:
        return "unknown"
    if len(date_code) == 2:
        return f"20{date_code}" if int(date_code) < 70 else f"19{date_code}"
    if len(date_code) == 4 and int(date_code[:2]) in range(19, 21):
        return date_code
    if len(date_code) == 4:
        yy = int(date_code[:2])
        return str(2000 + yy if yy < 70 else 1900 + yy)
    return date_code[:4]


def plan_datasus_downloads(entries: list[ManifestEntry], *, scan_id: str, root: str = "data/raw/datasus/ftp") -> list[DatasusDownloadPlan]:
    out: list[DatasusDownloadPlan] = []
    for entry in entries:
        if entry.extension == ".pdf":
            continue
        system = infer_system_guess(entry.directory)
        prefix = entry.series_prefix or "unknown"
        geo = entry.geo_code or "unknown"
        year = _infer_year(entry.date_code)
        rel = PurePosixPath(root) / f"scan_id={scan_id}" / f"system={system or 'UNKNOWN'}" / f"prefix={prefix}" / f"geo={geo}" / f"year={year}" / entry.filename
        out.append(
            DatasusDownloadPlan(
                source_url=entry.url,
                target_path=str(rel),
                metadata_path=str(rel) + ".metadata.json",
                system=system,
                prefix=entry.series_prefix,
                geo_code=entry.geo_code,
                date_code=entry.date_code,
            )
        )
    return out
