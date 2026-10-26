from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import httpx
import pytest

from backend.app.config import Settings
from backend.app.errors import (
    ElexonHTTPError,
    ElexonResponseError,
    ElexonTimeoutError,
    ElexonUnavailableError,
)
from backend.app.services.elexon_client import ElexonClient


def settings(**overrides: Any) -> Settings:
    values = {
        "elexon_base_url": "https://example.test/bmrs/api/v1",
        "elexon_timeout_seconds": 1.0,
        "elexon_max_attempts": 3,
        "elexon_backoff_seconds": 0.0,
        "elexon_max_retry_delay_seconds": 0.0,
        "source_cache_ttl_seconds": 60.0,
        "source_cache_max_entries": 4,
    }
    values.update(overrides)
    return Settings(**values)


def fuel_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "dataset": "FUELHH",
        "publishTime": "2026-01-01T00:30:00Z",
        "startTime": "2026-01-01T00:00:00Z",
        "settlementDate": "2026-01-01",
        "settlementPeriod": 1,
        "fuelType": "WIND",
        "generation": 100,
    }
    row.update(overrides)
    return row


def wind_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "dataset": "WINDFOR",
        "publishTime": "2025-12-31T12:00:00Z",
        "startTime": "2026-01-01T00:00:00Z",
        "generation": 110,
    }
    row.update(overrides)
    return row


async def no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_fuelhh_uses_only_verified_parameters_and_caches_success() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path.endswith("/datasets/FUELHH/stream")
        assert list(request.url.params.multi_items()) == [
            ("settlementDateFrom", "2026-01-01"),
            ("settlementDateTo", "2026-01-31"),
            ("fuelType", "WIND"),
        ]
        return httpx.Response(200, json=[fuel_row()])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(settings(), http_client=http, sleep=no_sleep)
        first = await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 31))
        first[0]["generation"] = -1
        second = await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 31))

    assert calls == 1
    assert second[0]["generation"] == 100


@pytest.mark.asyncio
async def test_windfor_uses_publication_filters_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/datasets/WINDFOR/stream")
        assert list(request.url.params.multi_items()) == [
            ("publishDateTimeFrom", "2025-12-31T00:00:00Z"),
            ("publishDateTimeTo", "2026-01-31T12:00:00Z"),
        ]
        return httpx.Response(200, json=[wind_row()])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(settings(), http_client=http, sleep=no_sleep)
        rows = await client.fetch_windfor(
            datetime(2025, 12, 31, tzinfo=timezone.utc),
            datetime(2026, 1, 31, 12, tzinfo=timezone.utc),
        )
    assert rows == [wind_row()]


@pytest.mark.asyncio
async def test_timeout_is_retried_and_sanitized() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("sensitive transport detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(settings(), http_client=http, sleep=no_sleep)
        with pytest.raises(ElexonTimeoutError, match="FUELHH request timed out") as caught:
            await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 1))
    assert calls == 3
    assert "sensitive" not in str(caught.value)


@pytest.mark.asyncio
async def test_retryable_http_status_is_bounded() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="do not expose this body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(settings(), http_client=http, sleep=no_sleep)
        with pytest.raises(ElexonUnavailableError) as caught:
            await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 1))
    assert calls == 3
    assert caught.value.status_code == 503
    assert "do not expose" not in str(caught.value)


@pytest.mark.asyncio
async def test_non_retryable_400_is_not_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"traceId": "upstream-trace-id"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(settings(), http_client=http, sleep=no_sleep)
        with pytest.raises(ElexonHTTPError, match="HTTP 400") as caught:
            await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 1))
    assert calls == 1
    assert "traceId" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, reason",
    [
        ({"data": []}, "top-level JSON value is not an array"),
        (["not-an-object"], "row 0 is not an object"),
        ([fuel_row(startTime=None)], "missing or null required fields"),
        ([fuel_row(startTime="2026-01-01T00:00:00")], "has no timezone offset"),
        ([fuel_row(publishTime="not-a-time")], "not a valid ISO timestamp"),
        ([fuel_row(generation=True)], "valid non-negative finite number"),
        ([fuel_row(generation=-1)], "valid non-negative finite number"),
        ([fuel_row(settlementDate="2026-02-30")], "not a valid ISO date"),
        ([fuel_row(dataset="OTHER")], "unexpected dataset value"),
    ],
)
async def test_invalid_response_shapes_are_rejected(payload: Any, reason: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(settings(), http_client=http, sleep=no_sleep)
        with pytest.raises(ElexonResponseError, match=reason):
            await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 1))


@pytest.mark.asyncio
async def test_invalid_json_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(settings(), http_client=http, sleep=no_sleep)
        with pytest.raises(ElexonResponseError, match="body is not valid JSON"):
            await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 1))


@pytest.mark.asyncio
async def test_failed_request_is_not_cached() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json=[fuel_row()])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(
            settings(elexon_max_attempts=1), http_client=http, sleep=no_sleep
        )
        with pytest.raises(ElexonUnavailableError):
            await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 1))
        rows = await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 1))
    assert calls == 2
    assert rows == [fuel_row()]


@pytest.mark.asyncio
async def test_naive_publication_bound_is_rejected_before_request() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[wind_row()])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ElexonClient(settings(), http_client=http, sleep=no_sleep)
        with pytest.raises(ValueError, match="timezone-aware"):
            await client.fetch_windfor(
                datetime(2025, 12, 31),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
    assert calls == 0
