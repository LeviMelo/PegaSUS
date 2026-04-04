from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from ...common.hashing import sha256_text
from ...common.text import normalize_basic
from ...config import get_settings
from .api import SidraApiClient
from .coverage import eval_coverage, extract_levels, parse_coverage_expr
from .db import create_connection
from .links import build_links_for_table
from .schema import ensure_schema


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _period_to_ord_kind(period_id: Any) -> tuple[int | None, str]:
    digits = "".join(ch for ch in str(period_id or "") if ch.isdigit())
    if len(digits) == 4:
        return int(digits + "00"), "Y"
    if len(digits) == 6:
        return int(digits), "YM"
    if len(digits) == 8:
        return int(digits), "YMD"
    return None, "UNK"


def _canonical_table_text(metadata: dict[str, Any]) -> str:
    periodicity = metadata.get("periodicidade") or {}
    bits = [
        f"id: {metadata.get('id')}",
        f"titulo: {metadata.get('nome') or ''}",
        f"pesquisa: {metadata.get('pesquisa') or ''}",
        f"assunto: {metadata.get('assunto') or ''}",
        f"frequencia: {(periodicity.get('frequencia') or '')}",
        f"inicio: {(periodicity.get('inicio') or '')}",
        f"fim: {(periodicity.get('fim') or '')}",
        f"url: {metadata.get('URL') or metadata.get('url') or ''}",
    ]
    return "\n".join(bits)



async def _fetch_locality_counts(client: SidraApiClient, aggregate_id: int, levels: list[str]) -> tuple[list[tuple[int, str, str, str, int]], list[tuple[int, str, str, str]], int, bool]:
    level_rows: list[tuple[int, str, str, str, int]] = []
    locality_rows: list[tuple[int, str, str, str]] = []
    municipality_count = 0
    for level in levels:
        payload = await client.fetch_localities(aggregate_id, level)
        count = 0
        for item in payload or []:
            locality_id = str(item.get("id") or item.get("codigo") or "")
            name = item.get("nome") or item.get("label") or ""
            if locality_id:
                locality_rows.append((aggregate_id, level, locality_id, name))
                count += 1
        level_rows.append((aggregate_id, level, level, "nivel", count))
        if level.upper() == "N6":
            municipality_count = count
    covers_nat = municipality_count >= get_settings().sidra_value_locality_chunk_size * 200
    return level_rows, locality_rows, municipality_count, covers_nat


async def ingest_table(table_id: int, *, client: SidraApiClient | None = None, build_links: bool = True) -> None:
    ensure_schema()
    own_client = client is None
    if client is None:
        client = SidraApiClient()
    try:
        metadata = await client.fetch_metadata(table_id)
        periods = await client.fetch_periods(table_id)
        levels = []
        territorial = metadata.get("nivelTerritorial") or metadata.get("nivel territorial") or {}
        if isinstance(territorial, dict):
            for values in territorial.values():
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str):
                            levels.append(value.upper())
                        elif isinstance(value, dict) and value.get("id"):
                            levels.append(str(value["id"]).upper())
        levels = sorted(set(levels))
        level_rows, locality_rows, municipality_count, covers_nat = await _fetch_locality_counts(client, table_id, levels)

        variables = metadata.get("variaveis") or []
        classifications = metadata.get("classificacoes") or []

        var_rows = [
            (int(item.get("id")), table_id, item.get("nome") or "", item.get("unidade"), json.dumps(item.get("sumarizacao") or [], ensure_ascii=False), sha256_text(f"{item.get('id')}||{item.get('nome')}||{item.get('unidade')}"))
            for item in variables if item.get("id") is not None
        ]
        class_rows = [
            (int(item.get("id")), table_id, item.get("nome") or "", int(bool(item.get("sumarizacao"))), json.dumps(item.get("sumarizacaoExcecao") or [], ensure_ascii=False))
            for item in classifications if item.get("id") is not None
        ]
        cat_rows = []
        for classification in classifications:
            class_id = classification.get("id")
            for category in classification.get("categorias") or []:
                if class_id is None or category.get("id") is None:
                    continue
                cat_rows.append((
                    table_id,
                    int(class_id),
                    int(category.get("id")),
                    category.get("nome") or "",
                    category.get("unidade"),
                    category.get("nivel"),
                    sha256_text(f"{class_id}||{category.get('id')}||{category.get('nome')}||{category.get('unidade')}")
                ))

        period_rows = []
        for period in periods or []:
            period_id = period.get("id") if isinstance(period, dict) else period
            literals = period.get("literals", [period_id]) if isinstance(period, dict) else [period_id]
            modification = period.get("modificacao") if isinstance(period, dict) else None
            ord_value, kind = _period_to_ord_kind(period_id)
            period_rows.append((table_id, str(period_id), json.dumps(literals, ensure_ascii=False), modification, ord_value, kind))

        conn = create_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT OR REPLACE INTO agregados(id, nome, pesquisa, assunto, url, freq, periodo_inicio, periodo_fim, raw_json, fetched_at, municipality_locality_count, covers_national_municipalities) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    metadata.get("id"),
                    metadata.get("nome"),
                    metadata.get("pesquisa"),
                    metadata.get("assunto"),
                    metadata.get("URL") or metadata.get("url"),
                    (metadata.get("periodicidade") or {}).get("frequencia"),
                    (metadata.get("periodicidade") or {}).get("inicio"),
                    (metadata.get("periodicidade") or {}).get("fim"),
                    json.dumps(metadata, ensure_ascii=False),
                    _now(),
                    municipality_count,
                    int(covers_nat),
                ),
            )
            for table in ("localities", "agregados_levels", "categories", "classifications", "variables", "periods"):
                conn.execute(f"DELETE FROM {table} WHERE agregado_id=?", (table_id,))
            if level_rows:
                conn.executemany("INSERT OR REPLACE INTO agregados_levels(agregado_id, level_id, level_name, level_type, locality_count) VALUES(?,?,?,?,?)", level_rows)
            if var_rows:
                conn.executemany("INSERT OR REPLACE INTO variables(id, agregado_id, nome, unidade, sumarizacao, text_hash) VALUES(?,?,?,?,?,?)", var_rows)
            if class_rows:
                conn.executemany("INSERT OR REPLACE INTO classifications(id, agregado_id, nome, sumarizacao_status, sumarizacao_excecao) VALUES(?,?,?,?,?)", class_rows)
            if cat_rows:
                conn.executemany("INSERT OR REPLACE INTO categories(agregado_id, classification_id, categoria_id, nome, unidade, nivel, text_hash) VALUES(?,?,?,?,?,?,?)", cat_rows)
            if period_rows:
                conn.executemany("INSERT OR REPLACE INTO periods(agregado_id, periodo_id, literals, modificacao, periodo_ord, periodo_kind) VALUES(?,?,?,?,?,?)", period_rows)
            if locality_rows:
                conn.executemany("INSERT OR REPLACE INTO localities(agregado_id, level_id, locality_id, nome) VALUES(?,?,?,?)", locality_rows)
            conn.execute("INSERT INTO ingestion_log(agregado_id, stage, status, detail, run_at) VALUES(?,?,?,?,?)", (table_id, "metadata", "success", None, _now()))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        if build_links:
            build_links_for_table(table_id)
    finally:
        if own_client:
            await client.close()


@dataclass(frozen=True)
class CoverageIngestReport:
    coverage: str
    matched_table_ids: list[int]


async def ingest_by_coverage(coverage: str, *, subject_contains: str | None = None, survey_contains: str | None = None, limit: int | None = None, concurrency: int = 4) -> CoverageIngestReport:
    expr = parse_coverage_expr(coverage)
    levels = sorted(extract_levels(expr))
    async with SidraApiClient() as client:
        catalog = await client.fetch_catalog(levels=levels or None)
        candidates: list[dict[str, Any]] = []
        for survey in catalog or []:
            for ag in survey.get("agregados") or []:
                title = ag.get("nome") or ""
                survey_name = survey.get("nome") or ""
                subject_name = ag.get("assunto") or survey.get("assunto") or ""
                if subject_contains and normalize_basic(subject_contains) not in normalize_basic(subject_name):
                    continue
                if survey_contains and normalize_basic(survey_contains) not in normalize_basic(survey_name):
                    continue
                candidates.append({"id": int(ag["id"]), "title": title})
        matched: list[int] = []
        sem = asyncio.Semaphore(concurrency)
        async def probe(table_id: int) -> None:
            async with sem:
                await ingest_table(table_id, client=client)
                conn = create_connection()
                try:
                    rows = conn.execute("SELECT level_id, locality_count FROM agregados_levels WHERE agregado_id=?", (table_id,)).fetchall()
                    counts = {str(row["level_id"]).upper(): int(row["locality_count"] or 0) for row in rows}
                finally:
                    conn.close()
                if eval_coverage(expr, counts):
                    matched.append(table_id)
        tasks = [probe(item["id"]) for item in candidates[: limit or None]]
        await asyncio.gather(*tasks)
    return CoverageIngestReport(coverage=coverage, matched_table_ids=sorted(set(matched)))
