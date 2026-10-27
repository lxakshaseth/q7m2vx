from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

from backend.app.domain import ActualRecord, DecisionCutoffError, ForecastRecord
from backend.app.services.forecast_selection import (
    build_hourly_aggregated_matches,
    build_interval_matches,
    decision_cutoff_for_date,
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


def test_selected_hour_retains_only_its_native_start_time() -> None:
    selected = select_day_before_forecasts(
        [forecast("2026-01-14T12:00:00Z", 110)],
        [utc("2026-01-15T12:00:00Z")],
        time(12, 0),
    ).selected

    assert len(selected) == 1
    assert selected[0].native_start_time == utc("2026-01-15T12:00:00Z")
    assert selected[0].publish_time == utc("2026-01-14T12:00:00Z")


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
    actual_on_hour = ActualRecord(
        start_time=target,
        publish_time=utc("2026-01-15T12:30:00Z"),
        generation_mw=100,
        settlement_date=date(2026, 1, 15),
        settlement_period=25,
    )
    actual_half_hour = ActualRecord(
        start_time=utc("2026-01-15T12:30:00Z"),
        publish_time=utc("2026-01-15T13:00:00Z"),
        generation_mw=105,
        settlement_date=date(2026, 1, 15),
        settlement_period=26,
    )
    matches = build_interval_matches(
        [target, utc("2026-01-15T12:30:00Z")],
        [actual_on_hour, actual_half_hour],
        selected,
        time(12, 0),
    )

    assert matches[0].status == "matched"
    assert matches[0].error_mw == 10
    assert matches[1].status == "missing_forecast"
    assert matches[1].forecast is None
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
        selected,
        time(12, 0),
    )

    assert matches[0].status == "matched"
    assert matches[0].forecast is not None
    assert matches[0].forecast.generation_mw == 110
    assert matches[0].forecast.native_start_time == actual_start
    assert matches[0].forecast.publish_time != actual_start


def test_hourly_aggregated_matches_averages_complete_pairs_and_handles_incomplete() -> None:
    h1_start = utc("2026-01-15T12:00:00Z")
    h2_start = utc("2026-01-15T13:00:00Z")

    # Complete pair for H1 (12:00 and 12:30)
    act_1200 = ActualRecord(
        start_time=h1_start,
        publish_time=utc("2026-01-15T12:30:00Z"),
        generation_mw=100.0,
        settlement_date=date(2026, 1, 15),
        settlement_period=25,
    )
    act_1230 = ActualRecord(
        start_time=utc("2026-01-15T12:30:00Z"),
        publish_time=utc("2026-01-15T13:00:00Z"),
        generation_mw=200.0,
        settlement_date=date(2026, 1, 15),
        settlement_period=26,
    )
    # Incomplete pair for H2 (only 13:00 is present, 13:30 missing)
    act_1300 = ActualRecord(
        start_time=h2_start,
        publish_time=utc("2026-01-15T13:30:00Z"),
        generation_mw=300.0,
        settlement_date=date(2026, 1, 15),
        settlement_period=27,
    )

    fc_h1 = ForecastRecord(
        start_time=h1_start,
        publish_time=utc("2026-01-14T11:00:00Z"),
        generation_mw=160.0,
    )
    fc_h2 = ForecastRecord(
        start_time=h2_start,
        publish_time=utc("2026-01-14T11:00:00Z"),
        generation_mw=320.0,
    )

    selection = select_day_before_forecasts(
        [fc_h1, fc_h2],
        [h1_start, h2_start],
        time(12, 0),
    ).selected

    matches, complete, incomplete = build_hourly_aggregated_matches(
        [h1_start, h2_start],
        [act_1200, act_1230, act_1300],
        selection,
        time(12, 0),
    )

    assert complete == 1
    assert incomplete == 1
    assert len(matches) == 2

    # First hour: complete pair averaged ((100 + 200) / 2 = 150)
    first = matches[0]
    assert first.status == "matched"
    assert first.actual is not None
    assert first.actual.generation_mw == 150.0
    assert first.actual.publish_time == utc("2026-01-15T13:00:00Z")
    assert first.forecast is not None
    assert first.forecast.generation_mw == 160.0
    assert first.error_mw == 10.0

    # Second hour: incomplete pair is missing actual, not fabricated
    second = matches[1]
    assert second.status == "missing_actual"
    assert second.actual is None
    assert second.forecast is not None
    assert second.error_mw is None
