from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...config import get_settings
from ..catalog.api import SidraApiClient
from .normalize import SidraValueRow, normalize_value_payload


@dataclass(frozen=True)
class ValueRequestShard:
    aggregate_id: int
    variable_id: int | str
    periods: str | None
    localities: str
    classification: str | None
    view: str | None


def _chunked(values: list[str], size: int) -> list[list[str]]:
    if not values:
        return [[]]
    return [values[idx: idx + size] for idx in range(0, len(values), size)]


def _format_localities(level: str, locality_ids: list[str]) -> str:
    return f"{level}[{','.join(locality_ids)}]" if locality_ids else level


async def fetch_values_sharded(
    *,
    aggregate_id: int,
    variable_id: int | str,
    periods: list[str],
    level: str,
    locality_ids: list[str],
    classification: str | None = None,
    view: str | None = 'flat',
    use_cache: bool = True,
) -> list[Any]:
    settings = get_settings()
    locality_chunks = _chunked(locality_ids, settings.sidra_value_locality_chunk_size)
    period_chunks = _chunked(periods, settings.sidra_value_period_chunk_size)
    shards = [
        ValueRequestShard(
            aggregate_id=aggregate_id,
            variable_id=variable_id,
            periods='|'.join(period_chunk) if period_chunk and period_chunk[0] else None,
            localities=_format_localities(level, locality_chunk),
            classification=classification,
            view=view,
        )
        for locality_chunk in locality_chunks
        for period_chunk in period_chunks
    ]
    results: list[Any] = []
    async with SidraApiClient() as client:
        for shard in shards:
            payload = await client.fetch_values(
                aggregate_id=shard.aggregate_id,
                variable_id=shard.variable_id,
                periods=shard.periods,
                localities=shard.localities,
                classification=shard.classification,
                view=shard.view,
                use_cache=use_cache,
            )
            results.append(payload)
    return results


async def fetch_and_normalize_values_sharded(
    *,
    aggregate_id: int,
    variable_id: int | str,
    periods: list[str],
    level: str,
    locality_ids: list[str],
    classification: str | None = None,
    view: str | None = 'flat',
    use_cache: bool = True,
) -> list[SidraValueRow]:
    payloads = await fetch_values_sharded(
        aggregate_id=aggregate_id,
        variable_id=variable_id,
        periods=periods,
        level=level,
        locality_ids=locality_ids,
        classification=classification,
        view=view,
        use_cache=use_cache,
    )
    out: list[SidraValueRow] = []
    for payload in payloads:
        out.extend(normalize_value_payload(aggregate_id=aggregate_id, variable_id=variable_id, payload=payload))
    return out
