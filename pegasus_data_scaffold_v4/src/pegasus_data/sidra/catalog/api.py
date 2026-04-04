from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from ...common.hashing import sha256_text
from ...config import get_settings
from .db import create_connection
from .schema import ensure_schema


class SidraApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class CachedResponse:
    request_key: str
    endpoint_path: str
    params_json: str
    response_json: str
    fetched_at: str


class SidraApiClient:
    def __init__(self, *, timeout: float | None = None) -> None:
        settings = get_settings()
        t = float(timeout or settings.sidra_request_timeout_seconds)
        self._pause_seconds = settings.sidra_pause_seconds
        self._semaphore = asyncio.Semaphore(settings.sidra_concurrent_requests)
        self._client = httpx.AsyncClient(
            base_url=settings.sidra_base_url,
            timeout=httpx.Timeout(connect=t, read=t, write=t, pool=t),
            headers={"User-Agent": settings.user_agent},
            limits=httpx.Limits(
                max_connections=settings.sidra_max_connections,
                max_keepalive_connections=settings.sidra_concurrent_requests,
            ),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        settings = get_settings()
        last_error: Exception | None = None
        for attempt in range(1, settings.sidra_request_retries + 1):
            try:
                async with self._semaphore:
                    response = await self._client.get(path, params=params)
                    await asyncio.sleep(self._pause_seconds)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise SidraApiError(f"SIDRA API failed {response.status_code}: {response.text[:200]}")
                if response.status_code >= 400:
                    raise RuntimeError(f"SIDRA API failed {response.status_code}: {response.text[:200]}")
                return response.json()
            except (httpx.TransportError, SidraApiError) as exc:
                last_error = exc
                if attempt >= settings.sidra_request_retries:
                    raise
                await asyncio.sleep(min(10.0, 2 ** (attempt - 1)))
        assert last_error is not None
        raise last_error

    async def fetch_catalog(
        self,
        *,
        subject_id: int | None = None,
        periodicity: str | None = None,
        levels: list[str] | None = None,
    ) -> Any:
        params: dict[str, Any] = {}
        if subject_id is not None:
            params["assunto"] = subject_id
        if periodicity:
            params["periodicidade"] = periodicity
        if levels:
            params["nivel"] = "|".join(level.upper() for level in levels)
        return await self._get_json("", params or None)

    async def fetch_metadata(self, aggregate_id: int) -> Any:
        return await self._get_json(f"/{aggregate_id}/metadados")

    async def fetch_periods(self, aggregate_id: int) -> Any:
        return await self._get_json(f"/{aggregate_id}/periodos")

    async def fetch_localities(self, aggregate_id: int, level: str) -> Any:
        return await self._get_json(f"/{aggregate_id}/localidades/{level}")

    async def fetch_values(
        self,
        *,
        aggregate_id: int,
        variable_id: int | str,
        periods: str | None = None,
        localities: str,
        classification: str | None = None,
        view: str | None = None,
        use_cache: bool = True,
    ) -> Any:
        if periods:
            endpoint = f"/{aggregate_id}/periodos/{periods}/variaveis/{variable_id}"
        else:
            endpoint = f"/{aggregate_id}/variaveis/{variable_id}"
        params: dict[str, Any] = {"localidades": localities}
        if classification:
            params["classificacao"] = classification
        if view:
            params["view"] = view
        request_key = sha256_text(endpoint + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False))
        if use_cache:
            cached = self._read_cached_response(request_key)
            if cached is not None:
                return json.loads(cached.response_json)
        payload = await self._get_json(endpoint, params)
        self._write_cached_response(request_key, endpoint, params, payload)
        return payload

    def _read_cached_response(self, request_key: str) -> CachedResponse | None:
        ensure_schema()
        conn = create_connection()
        try:
            row = conn.execute(
                "SELECT request_key, endpoint_path, params_json, response_json, fetched_at FROM raw_value_cache WHERE request_key=?",
                (request_key,),
            ).fetchone()
            if row is None:
                return None
            return CachedResponse(**dict(row))
        finally:
            conn.close()

    def _write_cached_response(
        self,
        request_key: str,
        endpoint_path: str,
        params: Mapping[str, Any],
        payload: Any,
    ) -> None:
        ensure_schema()
        conn = create_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO raw_value_cache(request_key, endpoint_path, params_json, response_json, fetched_at) VALUES(?,?,?,?,?)",
                (
                    request_key,
                    endpoint_path,
                    json.dumps(dict(params), ensure_ascii=False, sort_keys=True),
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )
            conn.commit()
        finally:
            conn.close()
