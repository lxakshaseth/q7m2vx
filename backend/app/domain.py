"""Internal, framework-independent records used by the analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from backend.app.errors import (
    AmbiguousDataError,
    AnalysisConfigurationError,
    DataNormalizationError,
)


class DataValidationError(DataNormalizationError):
    """An upstream row cannot be interpreted without guessing."""


class DuplicateConflictError(AmbiguousDataError):
    """Rows with the same source identity disagree on their value."""


class DecisionCutoffError(AnalysisConfigurationError):
    """A configured local decision time is ambiguous or does not exist."""


@dataclass(frozen=True, slots=True)
class ActualRecord:
    start_time: datetime
    publish_time: datetime
    generation_mw: float
    settlement_date: date
    settlement_period: int


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    """One native hourly WINDFOR publication version."""

    start_time: datetime
    publish_time: datetime
    generation_mw: float


@dataclass(frozen=True, slots=True)
class SelectedForecast:
    """The last eligible publication for one native forecast hour."""

    native_start_time: datetime
    publish_time: datetime
    generation_mw: float
    decision_cutoff_utc: datetime
    decision_cutoff_local: datetime


@dataclass(frozen=True, slots=True)
class ExpandedForecast:
    """A selected hourly forecast repeated onto one half-hour delivery key."""

    delivery_start: datetime
    native_start_time: datetime
    publish_time: datetime
    generation_mw: float
    decision_cutoff_utc: datetime
    decision_cutoff_local: datetime


IntervalStatus = Literal[
    "matched", "missing_actual", "missing_forecast", "missing_both"
]


@dataclass(frozen=True, slots=True)
class IntervalMatch:
    delivery_start: datetime
    delivery_start_local: datetime
    decision_cutoff_utc: datetime
    decision_cutoff_local: datetime
    actual: ActualRecord | None
    forecast: ExpandedForecast | None

    @property
    def status(self) -> IntervalStatus:
        if self.actual is not None and self.forecast is not None:
            return "matched"
        if self.actual is None and self.forecast is None:
            return "missing_both"
        if self.actual is None:
            return "missing_actual"
        return "missing_forecast"

    @property
    def error_mw(self) -> float | None:
        """Signed error; positive means the forecast exceeded the actual."""

        if self.actual is None or self.forecast is None:
            return None
        return self.forecast.generation_mw - self.actual.generation_mw

    @property
    def absolute_error_mw(self) -> float | None:
        error = self.error_mw
        return abs(error) if error is not None else None


@dataclass(frozen=True, slots=True)
class ActualNormalizationResult:
    records: tuple[ActualRecord, ...]
    exact_duplicates_discarded: int
    revisions_discarded: int
    non_wind_rows_filtered: int


@dataclass(frozen=True, slots=True)
class ForecastNormalizationResult:
    records: tuple[ForecastRecord, ...]
    exact_duplicates_discarded: int


@dataclass(frozen=True, slots=True)
class ForecastSelectionResult:
    selected: tuple[SelectedForecast, ...]
    native_target_count: int
    selected_target_count: int
    missing_target_count: int
    versions_considered: int
    ineligible_versions: int


@dataclass(frozen=True, slots=True)
class MetricResult:
    mae_mw: float | None
    rmse_mw: float | None
    wape_percent: float | None
    bias_mw: float | None
    expected_interval_count: int
    actual_interval_count: int
    forecast_interval_count: int
    matched_interval_count: int
    missing_actual_interval_count: int
    missing_forecast_interval_count: int
    forecast_coverage_percent: float | None
    matched_expected_percent: float | None
    wape_actual_denominator_mw: float
