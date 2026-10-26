from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

from backend.app.domain import ActualRecord, DecisionCutoffError, ForecastRecord
from backend.app.services.forecast_selection import (
    build_interval_matches,
    decision_cutoff_for_date,
    expand_hourly_forecasts,
    select_day_before_forecasts,
)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def forecast(publish: str, generation: float) -> ForecastRecord:
    return ForecastRecord(
        start_time=utc("2026-01-15T12:00:00Z"),
        publish_time=utc(publish),
        generation_mw=generation,
    )


def test_latest_publication_at_or_before_day_before_cutoff_is_selected() -> None:
    result = select_day_before_forecasts(
        [
            forecast("2026-01-14T12:01:00Z", 999),
            forecast("2026-01-14T11:59:00Z", 100),
            forecast("2026-01-14T12:00:00Z", 110),
            forecast("2026-01-15T01:00:00Z", 1000),
        ],
        [utc("2026-01-15T12:00:00Z")],
        time(12, 0),
    )

    assert result.selected_target_count == 1
    assert result.selected[0].publish_time == utc("2026-01-14T12:00:00Z")
    assert result.selected[0].generation_mw == 110
    assert result.selected[0].decision_cutoff_utc == utc("2026-01-14T12:00:00Z")
    assert result.ineligible_versions == 2


def test_missing_eligible_forecast_remains_missing() -> None:
    result = select_day_before_forecasts(
        [forecast("2026-01-14T12:01:00Z", 999)],
        [utc("2026-01-15T12:00:00Z"), utc("2026-01-15T13:00:00Z")],
        time(12, 0),
    )
    assert result.selected == ()
    assert result.missing_target_count == 2


def test_selected_hour_is_expanded_to_exactly_two_half_hours() -> None:
    selected = select_day_before_forecasts(
        [forecast("2026-01-14T12:00:00Z", 110)],
        [utc("2026-01-15T12:00:00Z")],
        time(12, 0),
    ).selected
    expanded = expand_hourly_forecasts(selected)

    assert [item.delivery_start for item in expanded] == [
        utc("2026-01-15T12:00:00Z"),
        utc("2026-01-15T12:30:00Z"),
    ]
    assert all(item.native_start_time == utc("2026-01-15T12:00:00Z") for item in expanded)
    assert all(item.publish_time == utc("2026-01-14T12:00:00Z") for item in expanded)


def test_london_cutoff_uses_dst_offset_in_summer() -> None:
    local, cutoff_utc = decision_cutoff_for_date(date(2026, 7, 15), time(12, 0))
    assert local.isoformat() == "2026-07-14T12:00:00+01:00"
    assert cutoff_utc == utc("2026-07-14T11:00:00Z")


def test_ambiguous_local_cutoff_is_rejected() -> None:
    # Delivery on Oct 26 means the cut-off falls on the Oct 25 clock change.
    with pytest.raises(DecisionCutoffError, match="ambiguous"):
        decision_cutoff_for_date(date(2026, 10, 26), time(1, 30))


def test_matching_uses_equal_half_hour_keys_and_preserves_missing_rows() -> None:
    target = utc("2026-01-15T12:00:00Z")
    selected = select_day_before_forecasts(
        [forecast("2026-01-14T12:00:00Z", 110)], [target], time(12, 0)
    ).selected
    expanded = expand_hourly_forecasts(selected)
    actual = ActualRecord(
        start_time=target,
        publish_time=utc("2026-01-15T12:30:00Z"),
        generation_mw=100,
        settlement_date=date(2026, 1, 15),
        settlement_period=25,
    )
    matches = build_interval_matches(
        [target, utc("2026-01-15T12:30:00Z")],
        [actual],
        expanded,
        time(12, 0),
    )

    assert matches[0].status == "matched"
    assert matches[0].error_mw == 10
    assert matches[1].status == "missing_actual"
    assert matches[1].forecast is not None
    assert all(
        item.forecast is None
        or item.forecast.publish_time <= item.decision_cutoff_utc
        for item in matches
    )


def test_matching_uses_delivery_start_not_publication_time() -> None:
    actual_start = utc("2026-01-15T12:00:00Z")
    actual = ActualRecord(
        start_time=actual_start,
        publish_time=utc("2026-01-15T12:30:00Z"),
        generation_mw=100,
        settlement_date=date(2026, 1, 15),
        settlement_period=25,
    )
    correct_target = ForecastRecord(
        start_time=actual_start,
        publish_time=utc("2026-01-14T10:00:00Z"),
        generation_mw=110,
    )
    adjacent_target = ForecastRecord(
        start_time=utc("2026-01-15T13:00:00Z"),
        publish_time=utc("2026-01-14T11:00:00Z"),
        generation_mw=999,
    )
    selected = select_day_before_forecasts(
        [correct_target, adjacent_target],
        [actual_start, utc("2026-01-15T13:00:00Z")],
        time(12, 0),
    ).selected
    matches = build_interval_matches(
        [actual_start],
        [actual],
        expand_hourly_forecasts(selected),
        time(12, 0),
    )

    assert matches[0].status == "matched"
    assert matches[0].forecast is not None
    assert matches[0].forecast.generation_mw == 110
    assert matches[0].forecast.delivery_start == actual_start
    assert matches[0].forecast.publish_time != actual_start
