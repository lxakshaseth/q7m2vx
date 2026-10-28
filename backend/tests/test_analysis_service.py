from __future__ import annotations

from datetime import date, datetime, time, timezone
import math
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

    response = await service.dashboard(date(2026, 1, 1), time(12, 0), alignment_method="half_hourly")

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
    ).metrics(date(2026, 1, 1), time(12), alignment_method="half_hourly")

    assert response.metrics.mae_mw is None
    assert response.metrics.rmse_mw is None
    assert response.metrics.wape_percent is None
    assert response.metrics.bias_mw is None
    assert response.metrics.matched_interval_count == 0
    assert response.metrics.missing_forecast_interval_count == 1
    assert response.metrics.forecast_coverage_percent == 0
    assert any(
        "no forecast selected" in warning or "no exact-start forecast" in warning
        for warning in response.metadata.warnings
    )


@pytest.mark.asyncio
async def test_empty_month_returns_null_metrics_and_explicit_missing_grid() -> None:
    response = await AnalysisService(  # type: ignore[arg-type]
        FakeClient([], []), make_settings()
    ).dashboard(date(2026, 1, 1), time(12), alignment_method="half_hourly")

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

    first = await service.intervals(date(2026, 1, 15), time(12), alignment_method="half_hourly")
    second = await service.metrics(date(2026, 1, 1), time(12), alignment_method="half_hourly")

    assert len(first.intervals) == 48
    assert all(
        row.delivery_start_local.date() == date(2026, 1, 15)
        for row in first.intervals
    )
    assert first.metrics.expected_interval_count == 48
    assert first.monthly_metrics is not None
    assert first.monthly_metrics.expected_interval_count == 1_488
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
    ).dashboard(date(2026, 1, 1), time(12), alignment_method="half_hourly")

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


@pytest.mark.asyncio
async def test_service_hourly_aggregated_alignment_averages_actuals_and_handles_incomplete_pairs() -> None:
    client = FakeClient(
        actuals=[
            fuel_row("2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z", 100, 1),
            fuel_row("2026-01-01T00:30:00Z", "2026-01-01T01:00:00Z", 200, 2),
            fuel_row("2026-01-01T01:00:00Z", "2026-01-01T01:30:00Z", 300, 3),
        ],
        forecasts=[
            wind_row("2026-01-01T00:00:00Z", "2025-12-31T12:00:00Z", 160),
            wind_row("2026-01-01T01:00:00Z", "2025-12-31T12:00:00Z", 350),
        ],
    )
    service = AnalysisService(client, make_settings())  # type: ignore[arg-type]
    response = await service.dashboard(date(2026, 1, 1), time(12, 0), alignment_method="hourly_aggregated")

    assert len(response.intervals) == 744
    first, second = response.intervals[:2]

    assert first.status == "matched"
    assert first.actual_mw == 150.0
    assert first.forecast_mw == 160.0
    assert first.error_mw == 10.0
    assert first.absolute_error_mw == 10.0

    assert second.status == "missing_actual"
    assert second.actual_mw is None
    assert second.forecast_mw == 350.0
    assert second.error_mw is None

    assert response.metadata.alignment_method == "hourly_aggregated"
    assert "Hourly aggregated alignment" in response.metadata.analysis_resolution
    assert response.metadata.data_quality.complete_actual_pairs_count == 1
    assert response.metadata.data_quality.incomplete_actual_pairs_count == 1
    assert any("incomplete half-hourly actual pairs" in w for w in response.metadata.warnings)

    assert response.metrics.matched_interval_count == 1
    assert response.metrics.mae_mw == 10.0
    assert response.metrics.bias_mw == 10.0
    assert response.metrics.wape_percent == pytest.approx(10.0 / 150.0 * 100)


@pytest.mark.asyncio
async def test_intervals_separates_day_coverage_from_monthly_coverage() -> None:
    client = FakeClient(
        actuals=[
            fuel_row("2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z", 100, 1, settlement_date="2026-01-01"),
            fuel_row("2026-01-01T00:30:00Z", "2026-01-01T01:00:00Z", 200, 2, settlement_date="2026-01-01"),
            fuel_row("2026-01-02T00:00:00Z", "2026-01-02T00:30:00Z", 300, 1, settlement_date="2026-01-02"),
        ],
        forecasts=[
            wind_row("2026-01-01T00:00:00Z", "2025-12-31T12:00:00Z", 150),
            wind_row("2026-01-02T00:00:00Z", "2026-01-01T12:00:00Z", 350),
        ],
    )
    service = AnalysisService(client, make_settings())  # type: ignore[arg-type]

    # Query Day 1
    day1_resp = await service.intervals(date(2026, 1, 1), time(12, 0), alignment_method="hourly_aggregated")
    assert day1_resp.day_coverage is not None
    assert day1_resp.monthly_coverage is not None

    # Day 1 coverage: strictly 24 hours expected, 2 actual observations, 1 complete pair, 0 incomplete
    assert day1_resp.day_coverage.expected_interval_count == 24
    assert day1_resp.day_coverage.actual_half_hourly_record_count == 2
    assert day1_resp.day_coverage.complete_actual_pairs_count == 1
    assert day1_resp.day_coverage.incomplete_actual_pairs_count == 0
    assert day1_resp.day_coverage.eligible_forecast_count == 1
    assert day1_resp.day_coverage.matched_interval_count == 1
    assert day1_resp.day_coverage.unmatched_interval_count == 23
    assert day1_resp.day_coverage.forecast_coverage_percent == 100.0
    assert "complete pairs" in day1_resp.day_coverage.coverage_denominator

    # Monthly coverage: 744 hours expected, 3 actual observations total, 1 complete pair, 1 incomplete
    assert day1_resp.monthly_coverage.expected_interval_count == 744
    assert day1_resp.monthly_coverage.actual_half_hourly_record_count == 3
    assert day1_resp.monthly_coverage.complete_actual_pairs_count == 1
    assert day1_resp.monthly_coverage.incomplete_actual_pairs_count == 1
    assert day1_resp.monthly_coverage.eligible_forecast_count == 2
    assert day1_resp.monthly_coverage.matched_interval_count == 1

    # Verify no accidental bleed of monthly counts into day counts
    assert day1_resp.day_coverage.expected_interval_count != day1_resp.monthly_coverage.expected_interval_count
    assert day1_resp.day_coverage.actual_half_hourly_record_count != day1_resp.monthly_coverage.actual_half_hourly_record_count

    # Query Day 2
    day2_resp = await service.intervals(date(2026, 1, 2), time(12, 0), alignment_method="hourly_aggregated")
    assert day2_resp.day_coverage is not None
    assert day2_resp.day_coverage.expected_interval_count == 24
    assert day2_resp.day_coverage.actual_half_hourly_record_count == 1
    assert day2_resp.day_coverage.complete_actual_pairs_count == 0
    assert day2_resp.day_coverage.incomplete_actual_pairs_count == 1
    assert day2_resp.day_coverage.matched_interval_count == 0
    assert day2_resp.day_coverage.unmatched_interval_count == 24


@pytest.mark.asyncio
async def test_monthly_metrics_are_not_simple_average_of_daily_metrics() -> None:
    """Prove that monthly MAE/RMSE/WAPE/Bias compute across all observations, not mean of daily KPIs."""
    client = FakeClient(
        actuals=[
            fuel_row("2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z", 100, 1, settlement_date="2026-01-01"),
            fuel_row("2026-01-01T00:30:00Z", "2026-01-01T01:00:00Z", 100, 2, settlement_date="2026-01-01"),
            fuel_row("2026-01-02T00:00:00Z", "2026-01-02T00:30:00Z", 1000, 1, settlement_date="2026-01-02"),
            fuel_row("2026-01-02T00:30:00Z", "2026-01-02T01:00:00Z", 1000, 2, settlement_date="2026-01-02"),
            fuel_row("2026-01-02T01:00:00Z", "2026-01-02T01:30:00Z", 1000, 3, settlement_date="2026-01-02"),
            fuel_row("2026-01-02T01:30:00Z", "2026-01-02T02:00:00Z", 1000, 4, settlement_date="2026-01-02"),
        ],
        forecasts=[
            wind_row("2026-01-01T00:00:00Z", "2025-12-31T12:00:00Z", 120),
            wind_row("2026-01-02T00:00:00Z", "2026-01-01T12:00:00Z", 1010),
            wind_row("2026-01-02T01:00:00Z", "2026-01-01T12:00:00Z", 1010),
        ],
    )
    service = AnalysisService(client, make_settings())  # type: ignore[arg-type]
    dashboard = await service.dashboard(date(2026, 1, 1), time(12, 0), alignment_method="hourly_aggregated")

    day1 = next(d for d in dashboard.daily_summaries if d.delivery_date == date(2026, 1, 1))
    day2 = next(d for d in dashboard.daily_summaries if d.delivery_date == date(2026, 1, 2))

    assert day1.metrics.mae_mw == 20.0
    assert day1.metrics.wape_percent == 20.0
    assert day1.metrics.bias_mw == 20.0

    assert day2.metrics.mae_mw == 10.0
    assert day2.metrics.wape_percent == pytest.approx(20.0 / 2000.0 * 100)
    assert day2.metrics.bias_mw == 10.0

    # True monthly metrics across all 3 observations
    monthly = dashboard.metrics
    assert monthly.matched_interval_count == 3
    assert monthly.mae_mw == pytest.approx(40.0 / 3.0)
    assert monthly.rmse_mw == pytest.approx(math.sqrt(200.0))
    assert monthly.wape_percent == pytest.approx(40.0 / 2100.0 * 100)
    assert monthly.bias_mw == pytest.approx(40.0 / 3.0)

    # Prove mathematically that monthly metrics are NOT the simple average of daily metrics
    daily_avg_mae = (day1.metrics.mae_mw + day2.metrics.mae_mw) / 2.0
    daily_avg_wape = (day1.metrics.wape_percent + day2.metrics.wape_percent) / 2.0
    assert monthly.mae_mw != daily_avg_mae
    assert monthly.wape_percent != daily_avg_wape
