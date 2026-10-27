from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

import pytest

from backend.app.config import Settings
from backend.app.services.analysis import AnalysisService


def fuel_row(
    start: str,
    publish: str,
    generation: int,
    period: int,
    settlement_date: str = "2026-01-01",
) -> dict[str, Any]:
    return {
        "dataset": "FUELHH",
        "publishTime": publish,
        "startTime": start,
        "settlementDate": settlement_date,
        "settlementPeriod": period,
        "fuelType": "WIND",
        "generation": generation,
    }


def wind_row(start: str, publish: str, generation: int) -> dict[str, Any]:
    return {
        "dataset": "WINDFOR",
        "publishTime": publish,
        "startTime": start,
        "generation": generation,
    }


class FakeClient:
    def __init__(self, actuals: list[dict[str, Any]], forecasts: list[dict[str, Any]]):
        self.actuals = actuals
        self.forecasts = forecasts
        self.fuel_calls: list[tuple[date, date]] = []
        self.wind_calls: list[tuple[datetime, datetime]] = []

    async def fetch_fuelhh(self, start: date, end: date) -> list[dict[str, Any]]:
        self.fuel_calls.append((start, end))
        return list(self.actuals)

    async def fetch_windfor(
        self, publication_from: datetime, publication_to: datetime
    ) -> list[dict[str, Any]]:
        self.wind_calls.append((publication_from, publication_to))
        return list(self.forecasts)


def make_settings() -> Settings:
    return Settings(
        elexon_base_url="https://example.test/bmrs/api/v1",
        source_cache_ttl_seconds=0,
        analysis_cache_ttl_seconds=60,
        forecast_lookback_days=7,
    )


@pytest.mark.asyncio
async def test_service_selects_cutoff_version_and_matches_exact_start_only() -> None:
    client = FakeClient(
        actuals=[
            fuel_row(
                "2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z", 100, 1
            ),
            fuel_row(
                "2026-01-01T00:30:00Z", "2026-01-01T01:00:00Z", 200, 2
            ),
        ],
        forecasts=[
            wind_row(
                "2026-01-01T00:00:00Z", "2025-12-31T11:00:00Z", 90
            ),
            wind_row(
                "2026-01-01T00:00:00Z", "2025-12-31T12:00:00Z", 110
            ),
            wind_row(
                "2026-01-01T00:00:00Z", "2025-12-31T12:01:00Z", 999
            ),
        ],
    )
    service = AnalysisService(client, make_settings())  # type: ignore[arg-type]

    response = await service.dashboard(date(2026, 1, 1), time(12, 0))

    assert client.fuel_calls == [(date(2026, 1, 1), date(2026, 1, 31))]
    assert client.wind_calls == [
        (
            datetime(2025, 12, 25, tzinfo=timezone.utc),
            datetime(2026, 1, 30, 12, tzinfo=timezone.utc),
        )
    ]
    assert len(response.intervals) == 1_488
    first, second = response.intervals[:2]
    assert first.forecast_mw == 110
    assert second.forecast_mw is None
    assert first.forecast_publish_time_utc == datetime(
        2025, 12, 31, 12, tzinfo=timezone.utc
    )
    assert second.forecast_publish_time_utc is None
    assert first.decision_cutoff_utc == datetime(
        2025, 12, 31, 12, tzinfo=timezone.utc
    )
    assert response.metrics.matched_interval_count == 1
    assert response.metrics.actual_interval_count == 2
    assert response.metrics.eligible_forecast_interval_count == 1
    assert response.metrics.missing_forecast_interval_count == 1
    assert response.metrics.forecast_coverage_percent == 50
    assert response.metrics.mae_mw == 10
    assert response.metrics.bias_mw == 10
    assert response.metrics.wape_percent == 10
    assert response.metrics.rmse_mw == 10
    assert response.metadata.adjustable_demo_assumption is True
    assert "Exact UTC startTime matching" in response.metadata.analysis_resolution
    assert response.metadata.data_quality.normalized_forecast_version_count == 3
    assert response.metadata.data_quality.selected_native_forecast_count == 1


@pytest.mark.asyncio
async def test_missing_forecast_reduces_coverage_without_fabrication() -> None:
    client = FakeClient(
        actuals=[
            fuel_row(
                "2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z", 100, 1
            )
        ],
        forecasts=[],
    )
    response = await AnalysisService(  # type: ignore[arg-type]
        client, make_settings()
    ).metrics(date(2026, 1, 1), time(12))

    assert response.metrics.mae_mw is None
    assert response.metrics.rmse_mw is None
    assert response.metrics.wape_percent is None
    assert response.metrics.bias_mw is None
    assert response.metrics.matched_interval_count == 0
    assert response.metrics.missing_forecast_interval_count == 1
    assert response.metrics.forecast_coverage_percent == 0
    assert any(
        "no exact-start forecast selected" in warning
        for warning in response.metadata.warnings
    )


@pytest.mark.asyncio
async def test_empty_month_returns_null_metrics_and_explicit_missing_grid() -> None:
    response = await AnalysisService(  # type: ignore[arg-type]
        FakeClient([], []), make_settings()
    ).dashboard(date(2026, 1, 1), time(12))

    assert len(response.intervals) == 1_488
    assert {row.status for row in response.intervals} == {"missing_both"}
    assert response.metrics.expected_interval_count == 1_488
    assert response.metrics.actual_interval_count == 0
    assert response.metrics.matched_interval_count == 0
    assert response.metrics.forecast_coverage_percent is None
    assert response.metrics.mae_mw is None
    assert any("No actual WIND" in warning for warning in response.metadata.warnings)


@pytest.mark.asyncio
async def test_day_endpoint_uses_cached_month_and_returns_local_date_only() -> None:
    client = FakeClient([], [])
    service = AnalysisService(client, make_settings())  # type: ignore[arg-type]

    first = await service.intervals(date(2026, 1, 15), time(12))
    second = await service.metrics(date(2026, 1, 1), time(12))

    assert len(first.intervals) == 48
    assert all(
        row.delivery_start_local.date() == date(2026, 1, 15)
        for row in first.intervals
    )
    assert first.metrics.expected_interval_count == 48
    assert second.metrics.expected_interval_count == 1_488
    assert len(client.fuel_calls) == 1
    assert len(client.wind_calls) == 1


@pytest.mark.asyncio
async def test_january_boundaries_include_last_half_hour_and_exclude_february() -> None:
    february_start = "2026-02-01T00:00:00Z"
    client = FakeClient(
        actuals=[
            fuel_row(
                "2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z", 100, 1
            ),
            fuel_row(
                "2026-01-31T23:30:00Z",
                "2026-02-01T00:00:00Z",
                200,
                48,
                "2026-01-31",
            ),
            # Deliberately supplied by the fake source to prove local filtering
            # uses the exclusive February boundary.
            fuel_row(
                february_start,
                "2026-02-01T00:30:00Z",
                300,
                1,
                "2026-02-01",
            ),
        ],
        forecasts=[
            wind_row(
                "2026-01-01T00:00:00Z", "2025-12-31T12:00:00Z", 110
            ),
            wind_row(
                "2026-01-31T23:00:00Z", "2026-01-30T12:00:00Z", 210
            ),
            wind_row(february_start, "2026-01-31T12:00:00Z", 310),
        ],
    )

    response = await AnalysisService(  # type: ignore[arg-type]
        client, make_settings()
    ).dashboard(date(2026, 1, 1), time(12))

    starts = [row.delivery_start_utc for row in response.intervals]
    assert len(starts) == 1_488
    assert starts[0] == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert starts[-1] == datetime(2026, 1, 31, 23, 30, tzinfo=timezone.utc)
    assert datetime(2026, 2, 1, tzinfo=timezone.utc) not in starts
    assert response.metrics.actual_interval_count == 2
    assert response.intervals[-1].forecast_mw is None
    assert response.intervals[-2].forecast_mw == 210
    assert response.intervals[-1].decision_cutoff_utc == datetime(
        2026, 1, 30, 12, tzinfo=timezone.utc
    )
    assert response.metadata.delivery_end_utc == datetime(
        2026, 2, 1, tzinfo=timezone.utc
    )
