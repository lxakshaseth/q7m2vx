"""Public response schemas for the FastAPI surface."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    """Use predictable camelCase JSON while keeping Python code idiomatic."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: str = "wind-forecast-insight-backend"
    timestamp_utc: datetime


class DataQuality(ApiModel):
    source_actual_record_count: int = Field(ge=0)
    source_forecast_record_count: int = Field(ge=0)
    normalized_actual_interval_count: int = Field(ge=0)
    normalized_forecast_version_count: int = Field(ge=0)
    actual_exact_duplicates_removed: int = Field(ge=0)
    actual_revisions_resolved: int = Field(ge=0)
    forecast_exact_duplicates_removed: int = Field(ge=0)
    observed_native_forecast_target_count: int = Field(ge=0)
    expected_native_forecast_target_count: int = Field(ge=0)
    selected_native_forecast_count: int = Field(ge=0)


class AnalysisMetadata(ApiModel):
    timezone: Literal["Europe/London"] = "Europe/London"
    decision_cutoff_time: str
    decision_cutoff_policy: str
    adjustable_demo_assumption: bool = True
    forecast_selection_rule: str
    analysis_resolution: str
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    forecast_publication_from_utc: datetime
    forecast_publication_to_utc: datetime
    retrieved_at_utc: datetime
    actual_source_url: str
    forecast_source_url: str
    data_quality: DataQuality
    warnings: list[str] = Field(default_factory=list)


class Metrics(ApiModel):
    """Metrics use only rows containing both an actual and an eligible forecast."""

    mae_mw: float | None
    rmse_mw: float | None
    wape_percent: float | None
    bias_mw: float | None
    expected_interval_count: int = Field(ge=0)
    actual_interval_count: int = Field(ge=0)
    eligible_forecast_interval_count: int = Field(ge=0)
    matched_interval_count: int = Field(ge=0)
    missing_actual_interval_count: int = Field(ge=0)
    missing_forecast_interval_count: int = Field(ge=0)
    forecast_coverage_percent: float | None = Field(default=None, ge=0, le=100)


class IntervalResult(ApiModel):
    delivery_start_utc: datetime
    delivery_start_local: datetime
    actual_mw: float | None
    forecast_mw: float | None
    error_mw: float | None
    absolute_error_mw: float | None
    squared_error_mw2: float | None
    actual_publish_time_utc: datetime | None
    actual_publish_time_local: datetime | None
    forecast_publish_time_utc: datetime | None
    forecast_publish_time_local: datetime | None
    native_forecast_start_utc: datetime | None
    native_forecast_start_local: datetime | None
    decision_cutoff_utc: datetime
    decision_cutoff_local: datetime
    forecast_was_expanded: bool
    status: Literal["matched", "missing_actual", "missing_forecast", "missing_both"]


class DailySummary(ApiModel):
    delivery_date: date
    metrics: Metrics


class DashboardResponse(ApiModel):
    month: str
    metadata: AnalysisMetadata
    metrics: Metrics
    daily_summaries: list[DailySummary]
    intervals: list[IntervalResult]


class IntervalsResponse(ApiModel):
    delivery_date: date
    metadata: AnalysisMetadata
    metrics: Metrics
    intervals: list[IntervalResult]


class MetricsResponse(ApiModel):
    month: str
    metadata: AnalysisMetadata
    metrics: Metrics
