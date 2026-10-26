"""Async client for the verified Elexon FUELHH and WINDFOR stream APIs."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

import httpx

from backend.app.config import Settings
from backend.app.errors import (
    ElexonHTTPError,
    ElexonResponseError,
    ElexonTimeoutError,
    ElexonUnavailableError,
)
from backend.app.services.cache import AsyncTTLCache


LOGGER = logging.getLogger(__name__)

FUELHH_PATH = "/datasets/FUELHH/stream"
WINDFOR_PATH = "/datasets/WINDFOR/stream"
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

FUELHH_FIELDS = (
    "dataset",
    "publishTime",
    "startTime",
    "settlementDate",
    "settlementPeriod",
    "fuelType",
    "generation",
)
WINDFOR_FIELDS = ("dataset", "publishTime", "startTime", "generation")

CacheKey = tuple[str, tuple[tuple[str, str], ...]]
CachedRows = tuple[dict[str, Any], ...]


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("publication bounds must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ElexonClient:
    """Retrieve and validate public Elexon rows without altering source values."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.elexon_timeout_seconds),
            headers={
                "Accept": "application/json",
                "User-Agent": "wind-forecast-insight-backend/1.0",
            },
            follow_redirects=True,
        )
        self._cache: AsyncTTLCache[CacheKey, CachedRows] = AsyncTTLCache(
            max_entries=settings.source_cache_max_entries,
            ttl_seconds=settings.source_cache_ttl_seconds,
        )

    async def __aenter__(self) -> "ElexonClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def fetch_fuelhh(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        """Fetch WIND actuals using the documented settlement-date filter family."""

        if start_date > end_date:
            raise ValueError("start_date must not be later than end_date")
        params = (
            ("settlementDateFrom", start_date.isoformat()),
            ("settlementDateTo", end_date.isoformat()),
            ("fuelType", "WIND"),
        )
        return await self._fetch(
            dataset="FUELHH",
            path=FUELHH_PATH,
            params=params,
            required_fields=FUELHH_FIELDS,
        )

    async def fetch_windfor(
        self, publication_from: datetime, publication_to: datetime
    ) -> list[dict[str, Any]]:
        """Fetch forecast history using only documented publication-time filters."""

        start = _utc_iso(publication_from)
        end = _utc_iso(publication_to)
        if publication_from.astimezone(timezone.utc) > publication_to.astimezone(timezone.utc):
            raise ValueError("publication_from must not be later than publication_to")
        params = (
            ("publishDateTimeFrom", start),
            ("publishDateTimeTo", end),
        )
        return await self._fetch(
            dataset="WINDFOR",
            path=WINDFOR_PATH,
            params=params,
            required_fields=WINDFOR_FIELDS,
        )

    async def _fetch(
        self,
        *,
        dataset: str,
        path: str,
        params: Sequence[tuple[str, str]],
        required_fields: Sequence[str],
    ) -> list[dict[str, Any]]:
        cache_key: CacheKey = (dataset, tuple(params))
        cached = await self._cache.get(cache_key)
        if cached is not None:
            LOGGER.debug("Elexon cache hit", extra={"dataset": dataset})
            return [row.copy() for row in cached]

        url = f"{self._settings.elexon_base_url}{path}"
        for attempt in range(1, self._settings.elexon_max_attempts + 1):
            try:
                response = await self._http.get(url, params=list(params))
            except httpx.TimeoutException:
                LOGGER.warning(
                    "Elexon request timed out",
                    extra={"dataset": dataset, "attempt": attempt},
                )
                if attempt == self._settings.elexon_max_attempts:
                    raise ElexonTimeoutError(dataset) from None
                await self._sleep(self._retry_delay(attempt, None))
                continue
            except httpx.TransportError:
                LOGGER.warning(
                    "Elexon transport failure",
                    extra={"dataset": dataset, "attempt": attempt},
                )
                if attempt == self._settings.elexon_max_attempts:
                    raise ElexonUnavailableError(dataset) from None
                await self._sleep(self._retry_delay(attempt, None))
                continue

            if response.status_code == 200:
                rows = self._decode_and_validate(response, dataset, required_fields)
                canonical: CachedRows = tuple(row.copy() for row in rows)
                await self._cache.set(cache_key, canonical)
                LOGGER.info(
                    "Elexon dataset retrieved",
                    extra={"dataset": dataset, "records": len(rows), "attempt": attempt},
                )
                return [row.copy() for row in canonical]

            if response.status_code in RETRYABLE_STATUSES:
                LOGGER.warning(
                    "Retryable Elexon response",
                    extra={
                        "dataset": dataset,
                        "status_code": response.status_code,
                        "attempt": attempt,
                    },
                )
                if attempt == self._settings.elexon_max_attempts:
                    raise ElexonUnavailableError(dataset, response.status_code)
                await self._sleep(self._retry_delay(attempt, response))
                continue

            # Do not include the response body, URL query, or headers in the error.
            raise ElexonHTTPError(dataset, response.status_code)

        raise ElexonUnavailableError(dataset)  # pragma: no cover - defensive

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        retry_after = response.headers.get("Retry-After") if response else None
        if retry_after:
            try:
                return min(
                    max(float(retry_after), 0.0),
                    self._settings.elexon_max_retry_delay_seconds,
                )
            except ValueError:
                pass
        return min(
            self._settings.elexon_backoff_seconds * 2 ** (attempt - 1),
            self._settings.elexon_max_retry_delay_seconds,
        )

    @staticmethod
    def _decode_and_validate(
        response: httpx.Response,
        dataset: str,
        required_fields: Sequence[str],
    ) -> list[dict[str, Any]]:
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise ElexonResponseError(dataset, "body is not valid JSON") from exc
        if not isinstance(payload, list):
            raise ElexonResponseError(dataset, "top-level JSON value is not an array")

        rows: list[dict[str, Any]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ElexonResponseError(dataset, f"row {index} is not an object")
            missing = [field for field in required_fields if item.get(field) is None]
            if missing:
                raise ElexonResponseError(
                    dataset,
                    f"row {index} has missing or null required fields: {', '.join(missing)}",
                )
            ElexonClient._validate_field_types(item, dataset, index)
            rows.append(dict(item))
        return rows

    @staticmethod
    def _validate_field_types(item: Mapping[str, Any], dataset: str, index: int) -> None:
        expected_dataset = item.get("dataset")
        if not isinstance(expected_dataset, str) or expected_dataset != dataset:
            raise ElexonResponseError(dataset, f"row {index} has an unexpected dataset value")
        for field in ("publishTime", "startTime"):
            value = item.get(field)
            if not isinstance(value, str):
                raise ElexonResponseError(dataset, f"row {index} field {field} is not a string")
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ElexonResponseError(
                    dataset, f"row {index} field {field} is not a valid ISO timestamp"
                ) from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ElexonResponseError(
                    dataset, f"row {index} field {field} has no timezone offset"
                )
        generation = item.get("generation")
        if (
            isinstance(generation, bool)
            or not isinstance(generation, (int, float))
            or not math.isfinite(float(generation))
            or generation < 0
        ):
            raise ElexonResponseError(
                dataset,
                f"row {index} field generation is not a valid non-negative finite number",
            )
        if dataset == "FUELHH":
            settlement_date = item.get("settlementDate")
            if not isinstance(settlement_date, str):
                raise ElexonResponseError(
                    dataset, f"row {index} field settlementDate is not a string"
                )
            try:
                date.fromisoformat(settlement_date)
            except ValueError as exc:
                raise ElexonResponseError(
                    dataset,
                    f"row {index} field settlementDate is not a valid ISO date",
                ) from exc
            period = item.get("settlementPeriod")
            if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
                raise ElexonResponseError(
                    dataset,
                    f"row {index} field settlementPeriod is not a positive integer",
                )
            if not isinstance(item.get("fuelType"), str):
                raise ElexonResponseError(
                    dataset, f"row {index} field fuelType is not a string"
                )
