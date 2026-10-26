"""Validate and normalize Elexon rows without inventing missing values."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from backend.app.domain import (
    ActualNormalizationResult,
    ActualRecord,
    DataValidationError,
    DuplicateConflictError,
    ForecastNormalizationResult,
    ForecastRecord,
)


def parse_aware_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DataValidationError(f"{field_name} must be a non-empty ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataValidationError(f"{field_name} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DataValidationError(f"{field_name} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def parse_generation(value: Any, field_name: str = "generation") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataValidationError(f"{field_name} must be numeric")
    generation = float(value)
    if not math.isfinite(generation):
        raise DataValidationError(f"{field_name} must be finite")
    if generation < 0:
        raise DataValidationError(f"{field_name} must not be negative")
    return generation


def _required(row: Mapping[str, Any], field: str, row_index: int) -> Any:
    if field not in row or row[field] is None:
        raise DataValidationError(f"row {row_index} is missing required field {field}")
    return row[field]


def _mapping(row: Any, row_index: int) -> Mapping[str, Any]:
    if not isinstance(row, Mapping):
        raise DataValidationError(f"row {row_index} is not an object")
    return row


def normalize_actual_rows(
    rows: Sequence[Mapping[str, Any]],
) -> ActualNormalizationResult:
    """Keep WIND rows and resolve repeated actuals as publication revisions.

    Distinct publications for one delivery start are revisions; the latest is
    retained. Exact repeats are counted and collapsed. If the same source key
    (startTime, publishTime) has contradictory content, proceeding would require
    guessing, so the response is rejected.
    """

    by_identity: dict[tuple[datetime, datetime], ActualRecord] = {}
    duplicate_count = 0
    non_wind_count = 0

    for index, raw_row in enumerate(rows):
        row = _mapping(raw_row, index)
        fuel_type = _required(row, "fuelType", index)
        if fuel_type != "WIND":
            non_wind_count += 1
            continue
        if _required(row, "dataset", index) != "FUELHH":
            raise DataValidationError(f"row {index} is not a FUELHH record")

        start = parse_aware_utc(_required(row, "startTime", index), "startTime")
        publish = parse_aware_utc(
            _required(row, "publishTime", index), "publishTime"
        )
        generation = parse_generation(_required(row, "generation", index))

        settlement_date_raw = _required(row, "settlementDate", index)
        if not isinstance(settlement_date_raw, str):
            raise DataValidationError("settlementDate must be an ISO date string")
        try:
            settlement_date = date.fromisoformat(settlement_date_raw)
        except ValueError as exc:
            raise DataValidationError("settlementDate is not a valid ISO date") from exc

        period = _required(row, "settlementPeriod", index)
        if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
            raise DataValidationError("settlementPeriod must be a positive integer")

        record = ActualRecord(
            start_time=start,
            publish_time=publish,
            generation_mw=generation,
            settlement_date=settlement_date,
            settlement_period=period,
        )
        identity = (start, publish)
        previous = by_identity.get(identity)
        if previous is None:
            by_identity[identity] = record
        elif previous == record:
            duplicate_count += 1
        else:
            raise DuplicateConflictError(
                "FUELHH rows with the same startTime and publishTime conflict"
            )

    by_start: dict[datetime, list[ActualRecord]] = defaultdict(list)
    for record in by_identity.values():
        by_start[record.start_time].append(record)

    selected: list[ActualRecord] = []
    revisions_discarded = 0
    for start, versions in by_start.items():
        versions.sort(key=lambda item: item.publish_time)
        selected.append(versions[-1])
        revisions_discarded += len(versions) - 1

    selected.sort(key=lambda item: item.start_time)
    return ActualNormalizationResult(
        records=tuple(selected),
        exact_duplicates_discarded=duplicate_count,
        revisions_discarded=revisions_discarded,
        non_wind_rows_filtered=non_wind_count,
    )


def normalize_forecast_rows(
    rows: Sequence[Mapping[str, Any]],
) -> ForecastNormalizationResult:
    """Preserve distinct WINDFOR publications and collapse only exact repeats."""

    by_identity: dict[tuple[datetime, datetime], ForecastRecord] = {}
    duplicate_count = 0

    for index, raw_row in enumerate(rows):
        row = _mapping(raw_row, index)
        if _required(row, "dataset", index) != "WINDFOR":
            raise DataValidationError(f"row {index} is not a WINDFOR record")
        start = parse_aware_utc(_required(row, "startTime", index), "startTime")
        publish = parse_aware_utc(
            _required(row, "publishTime", index), "publishTime"
        )
        generation = parse_generation(_required(row, "generation", index))
        if start.minute != 0 or start.second != 0 or start.microsecond != 0:
            raise DataValidationError(
                "WINDFOR startTime must be aligned to a native whole hour"
            )

        record = ForecastRecord(
            start_time=start,
            publish_time=publish,
            generation_mw=generation,
        )
        identity = (start, publish)
        previous = by_identity.get(identity)
        if previous is None:
            by_identity[identity] = record
        elif previous == record:
            duplicate_count += 1
        else:
            raise DuplicateConflictError(
                "WINDFOR rows with the same startTime and publishTime conflict"
            )

    records = tuple(
        sorted(by_identity.values(), key=lambda item: (item.start_time, item.publish_time))
    )
    return ForecastNormalizationResult(
        records=records,
        exact_duplicates_discarded=duplicate_count,
    )


# British-spelling aliases match the project documentation while the American
# forms remain convenient for callers accustomed to common Python terminology.
normalise_actual_rows = normalize_actual_rows
normalise_forecast_rows = normalize_forecast_rows
