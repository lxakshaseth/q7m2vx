"""Day-before forecast selection and exact delivery-start matching."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.app.domain import (
    ActualRecord,
    DataValidationError,
    DecisionCutoffError,
    ForecastRecord,
    ForecastSelectionResult,
    IntervalMatch,
    SelectedForecast,
)


LONDON_TIMEZONE = "Europe/London"


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise DecisionCutoffError(f"timezone data is unavailable for {name}") from exc


def decision_cutoff_for_date(
    delivery_local_date: date,
    decision_cutoff_time: time,
    timezone_name: str = LONDON_TIMEZONE,
) -> tuple[datetime, datetime]:
    """Return the preceding local day's cut-off as (local, UTC).

    Ambiguous or nonexistent wall-clock times around DST transitions are
    rejected instead of silently selecting one fold. The default 12:00 demo
    assumption is unaffected by those transitions.
    """

    if decision_cutoff_time.tzinfo is not None:
        raise DecisionCutoffError("decision_cutoff_time must not include a timezone")
    zone = _zone(timezone_name)
    decision_date = delivery_local_date - timedelta(days=1)
    naive = datetime.combine(decision_date, decision_cutoff_time)
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)

    first_valid = (
        first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive
    )
    second_valid = (
        second.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive
    )
    if not first_valid and not second_valid:
        raise DecisionCutoffError(
            f"{naive.isoformat(timespec='minutes')} does not exist in {timezone_name}"
        )
    if first_valid and second_valid and first.utcoffset() != second.utcoffset():
        raise DecisionCutoffError(
            f"{naive.isoformat(timespec='minutes')} is ambiguous in {timezone_name}"
        )

    local = first if first_valid else second
    return local, local.astimezone(timezone.utc)


def decision_cutoff_for_delivery(
    delivery_start: datetime,
    decision_cutoff_time: time,
    timezone_name: str = LONDON_TIMEZONE,
) -> tuple[datetime, datetime]:
    delivery_utc = _aware_utc(delivery_start, "delivery_start")
    local_date = delivery_utc.astimezone(_zone(timezone_name)).date()
    return decision_cutoff_for_date(local_date, decision_cutoff_time, timezone_name)


def half_hour_starts(start: datetime, end: datetime) -> tuple[datetime, ...]:
    start_utc = _aware_utc(start, "start")
    end_utc = _aware_utc(end, "end")
    if end_utc < start_utc:
        raise DataValidationError("end must not be earlier than start")
    if (
        start_utc.minute not in (0, 30)
        or start_utc.second != 0
        or start_utc.microsecond != 0
    ):
        raise DataValidationError("start must align to a half-hour")
    result: list[datetime] = []
    current = start_utc
    while current < end_utc:
        result.append(current)
        current += timedelta(minutes=30)
    return tuple(result)


def hourly_starts(start: datetime, end: datetime) -> tuple[datetime, ...]:
    start_utc = _aware_utc(start, "start")
    end_utc = _aware_utc(end, "end")
    if end_utc < start_utc:
        raise DataValidationError("end must not be earlier than start")
    if start_utc.minute != 0 or start_utc.second != 0 or start_utc.microsecond != 0:
        raise DataValidationError("start must align to a whole hour")
    result: list[datetime] = []
    current = start_utc
    while current < end_utc:
        result.append(current)
        current += timedelta(hours=1)
    return tuple(result)


def select_day_before_forecasts(
    forecasts: Sequence[ForecastRecord],
    target_starts: Iterable[datetime],
    decision_cutoff_time: time,
    timezone_name: str = LONDON_TIMEZONE,
) -> ForecastSelectionResult:
    """Select the greatest publishTime at or before each local daily cut-off."""

    grouped: dict[datetime, list[ForecastRecord]] = defaultdict(list)
    for record in forecasts:
        start = _aware_utc(record.start_time, "forecast.start_time")
        grouped[start].append(record)

    normalized_targets: list[datetime] = []
    seen: set[datetime] = set()
    for target in target_starts:
        target_utc = _aware_utc(target, "target_start")
        if target_utc.minute != 0 or target_utc.second != 0 or target_utc.microsecond != 0:
            raise DataValidationError("forecast targets must align to a whole hour")
        if target_utc in seen:
            raise DataValidationError("forecast target starts must be unique")
        seen.add(target_utc)
        normalized_targets.append(target_utc)
    normalized_targets.sort()

    selected: list[SelectedForecast] = []
    versions_considered = 0
    ineligible_versions = 0
    for target in normalized_targets:
        local_cutoff, utc_cutoff = decision_cutoff_for_delivery(
            target, decision_cutoff_time, timezone_name
        )
        versions = grouped.get(target, [])
        versions_considered += len(versions)
        eligible = [version for version in versions if version.publish_time <= utc_cutoff]
        ineligible_versions += len(versions) - len(eligible)
        if not eligible:
            continue
        winner = max(eligible, key=lambda item: item.publish_time)
        selected.append(
            SelectedForecast(
                native_start_time=target,
                publish_time=winner.publish_time,
                generation_mw=winner.generation_mw,
                decision_cutoff_utc=utc_cutoff,
                decision_cutoff_local=local_cutoff,
            )
        )

    return ForecastSelectionResult(
        selected=tuple(selected),
        native_target_count=len(normalized_targets),
        selected_target_count=len(selected),
        missing_target_count=len(normalized_targets) - len(selected),
        versions_considered=versions_considered,
        ineligible_versions=ineligible_versions,
    )


def build_interval_matches(
    expected_starts: Iterable[datetime],
    actuals: Sequence[ActualRecord],
    forecasts: Sequence[SelectedForecast],
    decision_cutoff_time: time,
    timezone_name: str = LONDON_TIMEZONE,
) -> tuple[IntervalMatch, ...]:
    """Join sources only on exactly equal normalized half-hour delivery starts."""

    actual_by_start: dict[datetime, ActualRecord] = {}
    for actual in actuals:
        start = _aware_utc(actual.start_time, "actual.start_time")
        if start in actual_by_start:
            raise DataValidationError("actual records must be deduplicated before matching")
        actual_by_start[start] = actual

    forecast_by_start: dict[datetime, SelectedForecast] = {}
    for forecast in forecasts:
        start = _aware_utc(forecast.native_start_time, "forecast.native_start_time")
        if start in forecast_by_start:
            raise DataValidationError("forecast records must be deduplicated before matching")
        forecast_by_start[start] = forecast

    zone = _zone(timezone_name)
    normalized: list[datetime] = []
    seen: set[datetime] = set()
    for expected in expected_starts:
        start = _aware_utc(expected, "expected_start")
        if start in seen:
            raise DataValidationError("expected delivery starts must be unique")
        seen.add(start)
        normalized.append(start)
    normalized.sort()

    matches: list[IntervalMatch] = []
    for start in normalized:
        local_cutoff, utc_cutoff = decision_cutoff_for_delivery(
            start, decision_cutoff_time, timezone_name
        )
        forecast = forecast_by_start.get(start)
        if forecast is not None:
            if forecast.publish_time > utc_cutoff:
                raise DataValidationError("a selected forecast is later than its decision cutoff")
            if forecast.decision_cutoff_utc != utc_cutoff:
                raise DataValidationError("forecast decision cutoff does not match delivery date")
        matches.append(
            IntervalMatch(
                delivery_start=start,
                delivery_start_local=start.astimezone(zone),
                decision_cutoff_utc=utc_cutoff,
                decision_cutoff_local=local_cutoff,
                actual=actual_by_start.get(start),
                forecast=forecast,
            )
        )
    return tuple(matches)
