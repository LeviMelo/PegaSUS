from __future__ import annotations

from .db import create_connection

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS agregados (
        id INTEGER PRIMARY KEY,
        nome TEXT NOT NULL,
        pesquisa TEXT,
        assunto TEXT,
        url TEXT,
        freq TEXT,
        periodo_inicio TEXT,
        periodo_fim TEXT,
        raw_json TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        municipality_locality_count INTEGER DEFAULT 0,
        covers_national_municipalities INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agregados_levels (
        agregado_id INTEGER NOT NULL,
        level_id TEXT NOT NULL,
        level_name TEXT,
        level_type TEXT NOT NULL,
        locality_count INTEGER DEFAULT 0,
        PRIMARY KEY (agregado_id, level_id, level_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS variables (
        id INTEGER NOT NULL,
        agregado_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        unidade TEXT,
        sumarizacao TEXT,
        text_hash TEXT NOT NULL,
        PRIMARY KEY (agregado_id, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS classifications (
        id INTEGER NOT NULL,
        agregado_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        sumarizacao_status INTEGER,
        sumarizacao_excecao TEXT,
        PRIMARY KEY (agregado_id, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories (
        agregado_id INTEGER NOT NULL,
        classification_id INTEGER NOT NULL,
        categoria_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        unidade TEXT,
        nivel INTEGER,
        text_hash TEXT NOT NULL,
        PRIMARY KEY (agregado_id, classification_id, categoria_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS periods (
        agregado_id INTEGER NOT NULL,
        periodo_id TEXT NOT NULL,
        literals TEXT,
        modificacao TEXT,
        periodo_ord INTEGER,
        periodo_kind TEXT,
        PRIMARY KEY (agregado_id, periodo_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS localities (
        agregado_id INTEGER NOT NULL,
        level_id TEXT NOT NULL,
        locality_id TEXT NOT NULL,
        nome TEXT,
        PRIMARY KEY (agregado_id, level_id, locality_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS name_keys (
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        table_id INTEGER NOT NULL,
        entity_id TEXT,
        PRIMARY KEY (kind, key, table_id, entity_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS link_var (
        var_key TEXT NOT NULL,
        table_id INTEGER NOT NULL,
        variable_id INTEGER NOT NULL,
        PRIMARY KEY (var_key, table_id, variable_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS link_class (
        class_key TEXT NOT NULL,
        table_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        PRIMARY KEY (class_key, table_id, class_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS link_cat (
        class_key TEXT NOT NULL,
        cat_key TEXT NOT NULL,
        table_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        cat_id INTEGER NOT NULL,
        PRIMARY KEY (class_key, cat_key, table_id, class_id, cat_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingestion_log (
        agregado_id INTEGER,
        stage TEXT NOT NULL,
        status TEXT NOT NULL,
        detail TEXT,
        run_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_value_cache (
        request_key TEXT PRIMARY KEY,
        endpoint_path TEXT NOT NULL,
        params_json TEXT NOT NULL,
        response_json TEXT NOT NULL,
        fetched_at TEXT NOT NULL
    )
    """,
)


def ensure_schema(path: str | None = None) -> None:
    conn = create_connection(path)
    try:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()
