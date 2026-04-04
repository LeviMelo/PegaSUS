from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path.cwd()
    data_root: Path = Path("data")
    datasus_ftp_host: str = "ftp.datasus.gov.br"
    datasus_ftp_base_path: str = "/dissemin/publicos"
    datasus_scan_timeout_seconds: float = 30.0
    datasus_download_timeout_seconds: float = 60.0
    datasus_scan_connections: int = 8
    datasus_default_encoding: str = "latin1"
    datasus_download_root: Path = Path("data/raw/datasus/ftp")
    sidra_base_url: str = "https://servicodados.ibge.gov.br/api/v3/agregados"
    sidra_request_timeout_seconds: float = 30.0
    sidra_request_retries: int = 3
    sidra_max_connections: int = 16
    sidra_concurrent_requests: int = 4
    sidra_pause_seconds: float = 0.15
    sidra_value_locality_chunk_size: int = 25
    sidra_value_period_chunk_size: int = 12
    sidra_catalog_db_path: Path = Path("data/cache/sidra_catalog.sqlite3")
    sidra_value_output_root: Path = Path("data/compiled/sidra")
    user_agent: str = "pegasus-data/0.2"


def _env(name: str) -> str | None:
    for candidate in (name, name.upper(), name.lower()):
        if candidate in os.environ:
            return os.environ[candidate]
    return None


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = Path(_env("PEGASUS_DATA_PROJECT_ROOT") or Path.cwd())
    data_root = Path(_env("PEGASUS_DATA_DATA_ROOT") or root / "data")
    return Settings(
        project_root=root,
        data_root=data_root,
        datasus_scan_connections=_env_int("PEGASUS_DATA_DATASUS_SCAN_CONNECTIONS", 8),
        datasus_scan_timeout_seconds=_env_float("PEGASUS_DATA_DATASUS_SCAN_TIMEOUT_SECONDS", 30.0),
        datasus_download_timeout_seconds=_env_float("PEGASUS_DATA_DATASUS_DOWNLOAD_TIMEOUT_SECONDS", 60.0),
        datasus_default_encoding=_env("PEGASUS_DATA_DATASUS_DEFAULT_ENCODING") or "latin1",
        datasus_download_root=Path(_env("PEGASUS_DATA_DATASUS_DOWNLOAD_ROOT") or data_root / "raw" / "datasus" / "ftp"),
        sidra_request_timeout_seconds=_env_float("PEGASUS_DATA_SIDRA_REQUEST_TIMEOUT_SECONDS", 30.0),
        sidra_request_retries=_env_int("PEGASUS_DATA_SIDRA_REQUEST_RETRIES", 3),
        sidra_max_connections=_env_int("PEGASUS_DATA_SIDRA_MAX_CONNECTIONS", 16),
        sidra_concurrent_requests=_env_int("PEGASUS_DATA_SIDRA_CONCURRENT_REQUESTS", 4),
        sidra_pause_seconds=_env_float("PEGASUS_DATA_SIDRA_PAUSE_SECONDS", 0.15),
        sidra_value_locality_chunk_size=_env_int("PEGASUS_DATA_SIDRA_LOCALITY_CHUNK_SIZE", 25),
        sidra_value_period_chunk_size=_env_int("PEGASUS_DATA_SIDRA_PERIOD_CHUNK_SIZE", 12),
        sidra_catalog_db_path=Path(_env("PEGASUS_DATA_SIDRA_DB_PATH") or data_root / "cache" / "sidra_catalog.sqlite3"),
        sidra_value_output_root=Path(_env("PEGASUS_DATA_SIDRA_VALUE_OUTPUT_ROOT") or data_root / "compiled" / "sidra"),
        user_agent=_env("PEGASUS_DATA_USER_AGENT") or "pegasus-data/0.2",
    )
