from __future__ import annotations

import json

from ...common.hashing import sha256_text
from ...common.text import normalize_basic
from .db import create_connection


def build_links_for_table(table_id: int) -> dict[str, int]:
    conn = create_connection()
    try:
        conn.execute("DELETE FROM name_keys WHERE table_id=?", (table_id,))
        conn.execute("DELETE FROM link_var WHERE table_id=?", (table_id,))
        conn.execute("DELETE FROM link_class WHERE table_id=?", (table_id,))
        conn.execute("DELETE FROM link_cat WHERE table_id=?", (table_id,))

        var_rows = conn.execute("SELECT id, nome FROM variables WHERE agregado_id=?", (table_id,)).fetchall()
        class_rows = conn.execute("SELECT id, nome FROM classifications WHERE agregado_id=?", (table_id,)).fetchall()
        cat_rows = conn.execute("SELECT classification_id, categoria_id, nome FROM categories WHERE agregado_id=?", (table_id,)).fetchall()

        for row in var_rows:
            key = normalize_basic(row["nome"])
            if not key:
                continue
            conn.execute("INSERT OR IGNORE INTO name_keys(kind, key, table_id, entity_id) VALUES(?,?,?,?)", ("var", key, table_id, str(row["id"])))
            conn.execute("INSERT OR IGNORE INTO link_var(var_key, table_id, variable_id) VALUES(?,?,?)", (key, table_id, int(row["id"])))

        for row in class_rows:
            key = normalize_basic(row["nome"])
            if not key:
                continue
            conn.execute("INSERT OR IGNORE INTO name_keys(kind, key, table_id, entity_id) VALUES(?,?,?,?)", ("class", key, table_id, str(row["id"])))
            conn.execute("INSERT OR IGNORE INTO link_class(class_key, table_id, class_id) VALUES(?,?,?)", (key, table_id, int(row["id"])))

        class_name_map = {int(row["id"]): normalize_basic(row["nome"]) for row in class_rows}
        for row in cat_rows:
            class_key = class_name_map.get(int(row["classification_id"]), "")
            cat_key = normalize_basic(row["nome"])
            if not class_key or not cat_key:
                continue
            conn.execute("INSERT OR IGNORE INTO name_keys(kind, key, table_id, entity_id) VALUES(?,?,?,?)", ("cat", f"{class_key}::{cat_key}", table_id, f"{row['classification_id']}:{row['categoria_id']}"))
            conn.execute(
                "INSERT OR IGNORE INTO link_cat(class_key, cat_key, table_id, class_id, cat_id) VALUES(?,?,?,?,?)",
                (class_key, cat_key, table_id, int(row["classification_id"]), int(row["categoria_id"])),
            )
        conn.commit()
        return {
            "vars": conn.execute("SELECT COUNT(*) FROM link_var WHERE table_id=?", (table_id,)).fetchone()[0],
            "classes": conn.execute("SELECT COUNT(*) FROM link_class WHERE table_id=?", (table_id,)).fetchone()[0],
            "cats": conn.execute("SELECT COUNT(*) FROM link_cat WHERE table_id=?", (table_id,)).fetchone()[0],
        }
    finally:
        conn.close()
