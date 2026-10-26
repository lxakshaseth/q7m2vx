from __future__ import annotations

import pytest

from backend.app.domain import DataValidationError, DuplicateConflictError
from backend.app.services.normalization import (
    normalize_actual_rows,
    normalize_forecast_rows,
)


def actual_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
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


def forecast_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "dataset": "WINDFOR",
        "publishTime": "2025-12-31T12:00:00Z",
        "startTime": "2026-01-01T00:00:00Z",
        "generation": 110,
    }
    row.update(overrides)
    return row


def test_actuals_filter_non_wind_collapse_duplicates_and_take_latest_revision() -> None:
    first = actual_row()
    latest = actual_row(
        publishTime="2026-01-01T01:00:00+00:00", generation=120
    )
    result = normalize_actual_rows(
        [first, dict(first), latest, actual_row(fuelType="CCGT")]
    )

    assert len(result.records) == 1
    assert result.records[0].generation_mw == 120
    assert result.records[0].start_time.isoformat() == "2026-01-01T00:00:00+00:00"
    assert result.exact_duplicates_discarded == 1
    assert result.revisions_discarded == 1
    assert result.non_wind_rows_filtered == 1


def test_actual_conflicting_same_source_key_is_rejected() -> None:
    with pytest.raises(DuplicateConflictError):
        normalize_actual_rows([actual_row(generation=100), actual_row(generation=101)])


def test_timestamps_require_offsets() -> None:
    with pytest.raises(DataValidationError, match="timezone"):
        normalize_actual_rows([actual_row(startTime="2026-01-01T00:00:00")])


def test_forecast_versions_are_preserved_but_exact_duplicates_are_collapsed() -> None:
    first = forecast_row()
    later = forecast_row(publishTime="2025-12-31T18:00:00Z", generation=115)
    result = normalize_forecast_rows([first, dict(first), later])

    assert [record.generation_mw for record in result.records] == [110, 115]
    assert result.exact_duplicates_discarded == 1


def test_forecast_conflicting_same_start_and_publication_is_rejected() -> None:
    with pytest.raises(DuplicateConflictError):
        normalize_forecast_rows(
            [forecast_row(generation=100), forecast_row(generation=101)]
        )


def test_non_hour_aligned_forecast_is_rejected() -> None:
    with pytest.raises(DataValidationError, match="whole hour"):
        normalize_forecast_rows([forecast_row(startTime="2026-01-01T00:30:00Z")])


def test_missing_or_nonnumeric_values_are_rejected() -> None:
    row = forecast_row()
    del row["generation"]
    with pytest.raises(DataValidationError, match="generation"):
        normalize_forecast_rows([row])
    with pytest.raises(DataValidationError, match="numeric"):
        normalize_forecast_rows([forecast_row(generation="110")])
