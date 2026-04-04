from __future__ import annotations

import sqlite3
from pathlib import Path

from ...common.storage import ensure_parent
from ...config import get_settings


def create_connection(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or get_settings().sidra_catalog_db_path)
    ensure_parent(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
