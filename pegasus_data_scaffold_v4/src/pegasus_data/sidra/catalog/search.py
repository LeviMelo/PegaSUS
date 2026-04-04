from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ...common.text import normalize_basic
from .coverage import eval_coverage
from .db import create_connection
from .where_expr import WhereNode, _And, _Cmp, _Contains, _Not, _Or, parse_where_expr


@dataclass(frozen=True)
class TableHit:
    table_id: int
    title: str
    period_start: str | None
    period_end: str | None
    n3: int
    n6: int
    why: list[str]
    score: float


@dataclass(frozen=True)
class SearchArgs:
    q: str | None
    limit: int = 20


def _cmp(op: str, left: int, right: int) -> bool:
    return {">=": left >= right, ">": left > right, "<=": left <= right, "<": left < right, "==": left == right, "!=": left != right}[op]


def _load_context(table_id: int) -> dict[str, Any]:
    conn = create_connection()
    try:
        head = conn.execute("SELECT nome, pesquisa, assunto, periodo_inicio, periodo_fim, municipality_locality_count, covers_national_municipalities FROM agregados WHERE id=?", (table_id,)).fetchone()
        vars_ = [normalize_basic(row[0]) for row in conn.execute("SELECT nome FROM variables WHERE agregado_id=?", (table_id,)).fetchall()]
        classes = [normalize_basic(row[0]) for row in conn.execute("SELECT nome FROM classifications WHERE agregado_id=?", (table_id,)).fetchall()]
        cats = []
        for row in conn.execute("SELECT c.nome, k.nome FROM categories c JOIN classifications k ON k.agregado_id=c.agregado_id AND k.id=c.classification_id WHERE c.agregado_id=?", (table_id,)).fetchall():
            cats.append(f"{normalize_basic(row[1])}::{normalize_basic(row[0])}")
        counts = {str(row["level_id"]).upper(): int(row["locality_count"] or 0) for row in conn.execute("SELECT level_id, locality_count FROM agregados_levels WHERE agregado_id=?", (table_id,)).fetchall()}
        return {
            "title": head["nome"] if head else "",
            "title_norm": normalize_basic(head["nome"] if head else ""),
            "survey_norm": normalize_basic(head["pesquisa"] if head else ""),
            "subject_norm": normalize_basic(head["assunto"] if head else ""),
            "vars": vars_,
            "classes": classes,
            "cats": cats,
            "coverage_counts": counts,
            "period_start": head["periodo_inicio"] if head else None,
            "period_end": head["periodo_fim"] if head else None,
            "n3": counts.get("N3", 0),
            "n6": counts.get("N6", 0),
        }
    finally:
        conn.close()


def _eval(node: WhereNode, ctx: dict[str, Any], why: list[str]) -> bool:
    if isinstance(node, _Not):
        return not _eval(node.node, ctx, why)
    if isinstance(node, _And):
        return _eval(node.left, ctx, why) and _eval(node.right, ctx, why)
    if isinstance(node, _Or):
        return _eval(node.left, ctx, why) or _eval(node.right, ctx, why)
    if isinstance(node, _Cmp):
        result = _cmp(node.op, int(ctx["coverage_counts"].get(node.ident, 0)), node.number)
        if result:
            why.append(f"{node.ident}{node.op}{node.number}")
        return result
    if isinstance(node, _Contains):
        needle = normalize_basic(node.text)
        field = node.field.upper()
        haystacks = {
            "TITLE": [ctx["title_norm"]],
            "SURVEY": [ctx["survey_norm"]],
            "SUBJECT": [ctx["subject_norm"]],
            "VAR": ctx["vars"],
            "CLASS": ctx["classes"],
            "CAT": ctx["cats"],
        }.get(field, [])
        result = any(needle in item for item in haystacks)
        if result:
            why.append(f"{field}~{node.text}")
        return result
    raise TypeError(node)


def search_tables(args: SearchArgs) -> list[TableHit]:
    conn = create_connection()
    try:
        rows = conn.execute("SELECT id FROM agregados ORDER BY id").fetchall()
        table_ids = [int(row[0]) for row in rows]
    finally:
        conn.close()
    node = parse_where_expr(args.q) if args.q else None
    hits: list[TableHit] = []
    for table_id in table_ids:
        ctx = _load_context(table_id)
        why: list[str] = []
        if node is not None and not _eval(node, ctx, why):
            continue
        hits.append(TableHit(
            table_id=table_id,
            title=ctx["title"],
            period_start=ctx["period_start"],
            period_end=ctx["period_end"],
            n3=ctx["n3"],
            n6=ctx["n6"],
            why=why,
            score=float(len(why) + (1 if ctx["n6"] else 0)),
        ))
    hits.sort(key=lambda hit: (-hit.score, hit.table_id))
    return hits[: args.limit]


def show_table(table_id: int) -> dict[str, Any]:
    conn = create_connection()
    try:
        head = conn.execute("SELECT id, nome, pesquisa, assunto, url, freq, periodo_inicio, periodo_fim, municipality_locality_count, covers_national_municipalities FROM agregados WHERE id=?", (table_id,)).fetchone()
        if head is None:
            raise RuntimeError(f"table {table_id} not found")
        periods = [row[0] for row in conn.execute("SELECT periodo_id FROM periods WHERE agregado_id=? ORDER BY COALESCE(periodo_ord, 99999999), periodo_id", (table_id,)).fetchall()]
        levels = [{"level_id": row[0], "locality_count": row[1]} for row in conn.execute("SELECT level_id, locality_count FROM agregados_levels WHERE agregado_id=? ORDER BY level_id", (table_id,)).fetchall()]
        variables = [{"id": row[0], "name": row[1], "unit": row[2]} for row in conn.execute("SELECT id, nome, unidade FROM variables WHERE agregado_id=? ORDER BY id", (table_id,)).fetchall()]
        classes = [{"id": row[0], "name": row[1]} for row in conn.execute("SELECT id, nome FROM classifications WHERE agregado_id=? ORDER BY id", (table_id,)).fetchall()]
        return {
            "id": int(head["id"]),
            "title": head["nome"],
            "survey": head["pesquisa"],
            "subject": head["assunto"],
            "url": head["url"] or f"https://sidra.ibge.gov.br/tabela/{int(head['id'])}",
            "frequency": head["freq"],
            "period_start": head["periodo_inicio"],
            "period_end": head["periodo_fim"],
            "municipality_locality_count": int(head["municipality_locality_count"] or 0),
            "covers_national_municipalities": bool(head["covers_national_municipalities"]),
            "periods": periods,
            "levels": levels,
            "variables": variables,
            "classifications": classes,
        }
    finally:
        conn.close()
