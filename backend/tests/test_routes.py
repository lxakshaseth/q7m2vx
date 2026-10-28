from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone
from typing import Any

import httpx
import pytest

from backend.app.errors import (
    ElexonHTTPError,
    ElexonResponseError,
    ElexonTimeoutError,
    ElexonUnavailableError,
)
from backend.app.main import create_app
from backend.app.schemas import (
    AnalysisMetadata,
    CoverageAudit,
    DashboardResponse,
    DataQuality,
    IntervalsResponse,
    Metrics,
    MetricsResponse,
)


pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def api_client(application) -> AsyncIterator[httpx.AsyncClient]:
    """Exercise routes through ASGI without Starlette's deprecated TestClient."""

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


def empty_metrics(expected: int = 0) -> Metrics:
    return Metrics(
        mae_mw=None,
        rmse_mw=None,
        wape_percent=None,
        bias_mw=None,
        expected_interval_count=expected,
        actual_interval_count=0,
        eligible_forecast_interval_count=0,
        matched_interval_count=0,
        missing_actual_interval_count=expected,
        missing_forecast_interval_count=0,
        forecast_coverage_percent=None,
    )


def metadata() -> AnalysisMetadata:
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return AnalysisMetadata(
        decision_cutoff_time="12:00",
        decision_cutoff_policy="Adjustable demo assumption",
        forecast_selection_rule="greatest eligible publication",
        analysis_resolution="exact startTime matching",
        delivery_start_utc=instant,
        delivery_end_utc=datetime(2026, 2, 1, tzinfo=timezone.utc),
        forecast_publication_from_utc=datetime(2025, 12, 25, tzinfo=timezone.utc),
        forecast_publication_to_utc=datetime(2026, 1, 30, 12, tzinfo=timezone.utc),
        retrieved_at_utc=instant,
        actual_source_url="https://example.test/FUELHH/stream",
        forecast_source_url="https://example.test/WINDFOR/stream",
        data_quality=DataQuality(
            source_actual_record_count=0,
            source_forecast_record_count=0,
            normalized_actual_interval_count=0,
            normalized_forecast_version_count=0,
            actual_exact_duplicates_removed=0,
            actual_revisions_resolved=0,
            forecast_exact_duplicates_removed=0,
            observed_native_forecast_target_count=0,
            expected_native_forecast_target_count=0,
            selected_native_forecast_count=0,
        ),
    )


def sample_day_coverage() -> CoverageAudit:
    return CoverageAudit(
        expected_interval_count=24,
        actual_half_hourly_record_count=48,
        complete_actual_pairs_count=24,
        incomplete_actual_pairs_count=0,
        eligible_forecast_count=24,
        matched_interval_count=24,
        unmatched_interval_count=0,
        forecast_coverage_percent=100.0,
        coverage_denominator="available actual intervals (complete pairs)",
    )


def sample_monthly_coverage() -> CoverageAudit:
    return CoverageAudit(
        expected_interval_count=744,
        actual_half_hourly_record_count=1488,
        complete_actual_pairs_count=744,
        incomplete_actual_pairs_count=0,
        eligible_forecast_count=744,
        matched_interval_count=744,
        unmatched_interval_count=0,
        forecast_coverage_percent=100.0,
        coverage_denominator="available actual intervals (complete pairs)",
    )


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, time, str]] = []

    async def dashboard(
        self,
        month_start: date,
        cutoff: time,
        alignment_method: str = "hourly_aggregated",
    ) -> DashboardResponse:
        self.calls.append(("dashboard", month_start, cutoff, alignment_method))
        return DashboardResponse(
            month=month_start.strftime("%Y-%m"),
            metadata=metadata(),
            metrics=empty_metrics(),
            daily_summaries=[],
            intervals=[],
            monthly_coverage=sample_monthly_coverage(),
        )

    async def intervals(
        self,
        delivery_date: date,
        cutoff: time,
        alignment_method: str = "hourly_aggregated",
    ) -> IntervalsResponse:
        self.calls.append(("intervals", delivery_date, cutoff, alignment_method))
        return IntervalsResponse(
            delivery_date=delivery_date,
            metadata=metadata(),
            metrics=empty_metrics(48),
            monthly_metrics=empty_metrics(1488),
            intervals=[],
            day_coverage=sample_day_coverage(),
            monthly_coverage=sample_monthly_coverage(),
        )

    async def metrics(
        self,
        month_start: date,
        cutoff: time,
        alignment_method: str = "hourly_aggregated",
    ) -> MetricsResponse:
        self.calls.append(("metrics", month_start, cutoff, alignment_method))
        return MetricsResponse(
            month=month_start.strftime("%Y-%m"),
            metadata=metadata(),
            metrics=empty_metrics(),
            monthly_coverage=sample_monthly_coverage(),
        )


async def test_health_is_local_and_valid_routes_parse_parameters() -> None:
    service = FakeService()
    async with api_client(create_app(analysis_service=service)) as client:
        health = await client.get("/api/health")
        dashboard = await client.get(
            "/api/dashboard?month=2026-01&decision_cutoff_time=12:00"
        )
        intervals = await client.get(
            "/api/intervals?delivery_date=2026-01-15&decision_cutoff_time=12:00"
        )
        metrics = await client.get(
            "/api/metrics?month=2026-01&decision_cutoff_time=12:00"
        )

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert dashboard.status_code == 200
    assert dashboard.json()["month"] == "2026-01"
    assert dashboard.json()["metadata"]["adjustableDemoAssumption"] is True
    assert intervals.status_code == 200
    assert intervals.json()["deliveryDate"] == "2026-01-15"
    assert intervals.json()["monthlyMetrics"]["expectedIntervalCount"] == 1488
    assert intervals.json()["dayCoverage"]["expectedIntervalCount"] == 24
    assert intervals.json()["dayCoverage"]["actualHalfHourlyRecordCount"] == 48
    assert intervals.json()["monthlyCoverage"]["expectedIntervalCount"] == 744
    assert intervals.json()["monthlyCoverage"]["actualHalfHourlyRecordCount"] == 1488
    assert (
        intervals.json()["dayCoverage"]["expectedIntervalCount"]
        != intervals.json()["monthlyCoverage"]["expectedIntervalCount"]
    )
    assert metrics.status_code == 200
    assert service.calls == [
        ("dashboard", date(2026, 1, 1), time(12), "hourly_aggregated"),
        ("intervals", date(2026, 1, 15), time(12), "hourly_aggregated"),
        ("metrics", date(2026, 1, 1), time(12), "hourly_aggregated"),
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard?month=2026-1",
        "/api/dashboard?month=2026-13",
        "/api/dashboard?month=0001-01",
        "/api/dashboard?month=9999-12",
        "/api/dashboard?month=2026-01&decision_cutoff_time=24:00",
        "/api/dashboard?month=2026-01&decision_cutoff_time=12:60",
        "/api/dashboard?month=2026-01&decision_cutoff_time=noon",
        "/api/intervals?delivery_date=2026-02-30",
        "/api/intervals?delivery_date=0001-01-01",
        "/api/dashboard?month=2026-01&alignment_method=invalid",
    ],
)
async def test_invalid_query_parameters_return_422(path: str) -> None:
    async with api_client(create_app(analysis_service=FakeService())) as client:
        response = await client.get(path)
    assert response.status_code == 422


@pytest.mark.parametrize("cutoff", ["00:00", "23:59"])
async def test_cutoff_boundaries_are_accepted(cutoff: str) -> None:
    service = FakeService()
    async with api_client(create_app(analysis_service=service)) as client:
        response = await client.get(
            f"/api/metrics?month=2026-01&decision_cutoff_time={cutoff}"
        )
    assert response.status_code == 200


class FailingService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def dashboard(self, _month: date, _cutoff: time, _alignment: str = "hourly_aggregated"):
        raise self.error


@pytest.mark.parametrize(
    "error, expected_status, expected_code",
    [
        (ElexonTimeoutError("WINDFOR"), 504, "elexon_timeout"),
        (
            ElexonResponseError("FUELHH", "missing field"),
            502,
            "invalid_elexon_response",
        ),
        (ElexonHTTPError("FUELHH", 400), 502, "elexon_http_error"),
        (ElexonUnavailableError("WINDFOR", 503), 503, "elexon_unavailable"),
    ],
)
async def test_upstream_errors_are_sanitized(
    error: Exception, expected_status: int, expected_code: str
) -> None:
    async with api_client(create_app(analysis_service=FailingService(error))) as client:
        response = await client.get("/api/dashboard?month=2026-01")
    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert "traceId" not in response.text


async def test_production_frontend_serving_preserves_api_routes(
    tmp_path, monkeypatch
) -> None:
    """The production SPA fallback serves HTML without swallowing /api misses."""

    frontend_dist = tmp_path / "frontend_dist"
    assets = frontend_dist / "assets"
    assets.mkdir(parents=True)
    (frontend_dist / "index.html").write_text(
        "<!doctype html><title>Wind Forecast Intelligence</title>", encoding="utf-8"
    )
    (assets / "app.js").write_text("console.log('wind');", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(frontend_dist))

    async with api_client(create_app(analysis_service=FakeService())) as client:
        homepage = await client.get("/")
        spa_route = await client.get("/delivery/2026-01-15")
        asset = await client.get("/assets/app.js")
        health = await client.get("/api/health")
        unknown_api = await client.get("/api/not-a-route")

    assert homepage.status_code == 200
    assert homepage.text == spa_route.text
    assert "Wind Forecast Intelligence" in homepage.text
    assert asset.status_code == 200
    assert asset.text == "console.log('wind');"
    assert health.status_code == 200
    assert health.headers["content-type"].startswith("application/json")
    assert unknown_api.status_code == 404
    assert unknown_api.json()["detail"]["code"] == "api_route_not_found"
