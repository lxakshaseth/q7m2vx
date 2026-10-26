from __future__ import annotations

import math
from datetime import date, datetime, timezone

import pytest

from backend.app.domain import ActualRecord, ExpandedForecast, IntervalMatch
from backend.app.services.metrics import calculate_metrics


UTC = timezone.utc


def interval(
    minute: int,
    actual_mw: float | None,
    forecast_mw: float | None,
) -> IntervalMatch:
    start = datetime(2026, 1, 1, 0, minute, tzinfo=UTC)
    cutoff = datetime(2025, 12, 31, 12, 0, tzinfo=UTC)
    actual = (
        ActualRecord(start, start, actual_mw, date(2026, 1, 1), minute // 30 + 1)
        if actual_mw is not None
        else None
    )
    forecast = (
        ExpandedForecast(start, start.replace(minute=0), cutoff, forecast_mw, cutoff, cutoff)
        if forecast_mw is not None
        else None
    )
    return IntervalMatch(start, start, cutoff, cutoff, actual, forecast)


def test_metric_formulas_use_forecast_minus_actual() -> None:
    result = calculate_metrics([interval(0, 100, 110), interval(30, 200, 180)])

    assert result.mae_mw == 15
    assert result.rmse_mw == pytest.approx(math.sqrt(250))
    assert result.wape_percent == 10
    assert result.bias_mw == -5
    assert result.matched_interval_count == 2
    assert result.forecast_coverage_percent == 100


def test_missing_forecasts_reduce_coverage_and_do_not_enter_metrics() -> None:
    result = calculate_metrics(
        [interval(0, 100, 110), interval(30, 200, None), interval(0, None, None)]
    )
    assert result.matched_interval_count == 1
    assert result.actual_interval_count == 2
    assert result.forecast_coverage_percent == 50
    assert result.mae_mw == 10
    assert result.missing_forecast_interval_count == 1
    assert result.missing_actual_interval_count == 1


def test_zero_actual_denominator_makes_only_wape_unavailable() -> None:
    result = calculate_metrics([interval(0, 0, 0), interval(30, 0, 10)])
    assert result.wape_percent is None
    assert result.mae_mw == 5
    assert result.rmse_mw == pytest.approx(math.sqrt(50))
    assert result.bias_mw == 5


def test_empty_interval_set_has_null_metrics_and_coverage() -> None:
    result = calculate_metrics([])
    assert result.mae_mw is None
    assert result.rmse_mw is None
    assert result.wape_percent is None
    assert result.bias_mw is None
    assert result.forecast_coverage_percent is None
    assert result.matched_expected_percent is None
