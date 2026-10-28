"""Orchestrate live retrieval, normalization, selection, matching, and metrics."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.app.config import Settings
from backend.app.domain import ActualRecord, IntervalMatch, MetricResult
from backend.app.errors import AnalysisConfigurationError
from backend.app.schemas import (
    AnalysisMetadata,
    CoverageAudit,
    DashboardResponse,
    DailySummary,
    DataQuality,
    IntervalResult,
    IntervalsResponse,
    Metrics,
    MetricsResponse,
)
from backend.app.services.cache import AsyncTTLCache
from backend.app.services.elexon_client import ElexonClient, FUELHH_PATH, WINDFOR_PATH
from backend.app.services.forecast_selection import (
    build_hourly_aggregated_matches,
    build_interval_matches,
    decision_cutoff_for_date,
    half_hour_starts,
    hourly_starts,
    select_day_before_forecasts,
)
from backend.app.services.metrics import calculate_metrics
from backend.app.services.normalization import (
    normalize_actual_rows,
    normalize_forecast_rows,
)


LOGGER = logging.getLogger(__name__)

DECISION_POLICY = (
    "Adjustable demo assumption: preceding calendar day at the configured "
    "Europe/London clock time."
)
SELECTION_RULE = (
    "For each native WINDFOR delivery hour, select the greatest publishTime "
    "that is not later than that delivery date's decision cutoff."
)
HOURLY_RESOLUTION_POLICY = (
    "Hourly aggregated alignment: two consecutive half-hourly FUELHH outturn observations "
    "(H:00 and H:30) are averaged ((Actual_00 + Actual_30)/2.0) to match the 1-hour "
    "WINDFOR delivery window. Incomplete pairs are marked as missing actuals and excluded "
    "from error metrics."
)
HALF_HOURLY_RESOLUTION_POLICY = (
    "Exact UTC startTime matching: native hourly WINDFOR values match only the "
    "same-start FUELHH interval; intervening :30 half-hours remain missing."
)
RESOLUTION_POLICY = HOURLY_RESOLUTION_POLICY


def compute_coverage_audit(
    matches: Sequence[IntervalMatch],
    actual_records: Sequence[ActualRecord],
    alignment_method: str = "hourly_aggregated",
) -> CoverageAudit:
    expected_count = len(matches)
    actual_half_hourly_count = len(actual_records)

    if alignment_method == "hourly_aggregated":
        complete_pairs = sum(1 for m in matches if m.actual is not None)
        actual_starts = {r.start_time for r in actual_records}
        incomplete_pairs = 0
        for m in matches:
            has_00 = m.delivery_start in actual_starts
            has_30 = (m.delivery_start + timedelta(minutes=30)) in actual_starts
            if (has_00 and not has_30) or (has_30 and not has_00):
                incomplete_pairs += 1
        available_actual_intervals = complete_pairs
        denominator_label = "available actual intervals (complete pairs)"
    else:
        complete_pairs = actual_half_hourly_count // 2
        incomplete_pairs = 0
        available_actual_intervals = sum(1 for m in matches if m.actual is not None)
        denominator_label = "available actual intervals"

    eligible_forecasts = sum(1 for m in matches if m.forecast is not None)
    matched_count = sum(1 for m in matches if m.actual is not None and m.forecast is not None)
    unmatched_count = expected_count - matched_count
    coverage_pct = (
        (100.0 * matched_count / available_actual_intervals)
        if available_actual_intervals > 0
        else None
    )

    return CoverageAudit(
        expected_interval_count=expected_count,
        actual_half_hourly_record_count=actual_half_hourly_count,
        complete_actual_pairs_count=complete_pairs,
        incomplete_actual_pairs_count=incomplete_pairs,
        eligible_forecast_count=eligible_forecasts,
        matched_interval_count=matched_count,
        unmatched_interval_count=unmatched_count,
        forecast_coverage_percent=coverage_pct,
        coverage_denominator=denominator_label,
    )


@dataclass(frozen=True, slots=True)
class AnalysisBundle:
    month_start: date
    metadata: AnalysisMetadata
    metrics: Metrics
    intervals: tuple[IntervalResult, ...]
    daily_summaries: tuple[DailySummary, ...]
    internal_matches: tuple[IntervalMatch, ...]
    raw_actuals: tuple[ActualRecord, ...]
    monthly_coverage: CoverageAudit


def _next_month(first_day: date) -> date:
    if first_day.month == 12:
        return date(first_day.year + 1, 1, 1)
    return date(first_day.year, first_day.month + 1, 1)


def _iter_dates(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def _metrics_schema(result: MetricResult) -> Metrics:
    return Metrics(
        mae_mw=result.mae_mw,
        rmse_mw=result.rmse_mw,
        wape_percent=result.wape_percent,
        bias_mw=result.bias_mw,
        expected_interval_count=result.expected_interval_count,
        actual_interval_count=result.actual_interval_count,
        eligible_forecast_interval_count=result.forecast_interval_count,
        matched_interval_count=result.matched_interval_count,
        missing_actual_interval_count=result.missing_actual_interval_count,
        missing_forecast_interval_count=result.missing_forecast_interval_count,
        forecast_coverage_percent=result.forecast_coverage_percent,
    )


def _interval_schema(interval: IntervalMatch, zone: ZoneInfo) -> IntervalResult:
    error = interval.error_mw
    actual = interval.actual
    forecast = interval.forecast
    return IntervalResult(
        delivery_start_utc=interval.delivery_start,
        delivery_start_local=interval.delivery_start_local,
        actual_mw=actual.generation_mw if actual else None,
        forecast_mw=forecast.generation_mw if forecast else None,
        error_mw=error,
        absolute_error_mw=abs(error) if error is not None else None,
        squared_error_mw2=error * error if error is not None else None,
        actual_publish_time_utc=actual.publish_time if actual else None,
        actual_publish_time_local=(actual.publish_time.astimezone(zone) if actual else None),
        forecast_publish_time_utc=forecast.publish_time if forecast else None,
        forecast_publish_time_local=(
            forecast.publish_time.astimezone(zone) if forecast else None
        ),
        decision_cutoff_utc=interval.decision_cutoff_utc,
        decision_cutoff_local=interval.decision_cutoff_local,
        status=interval.status,
    )


class AnalysisService:
    """Application service shared by the three data routes."""

    def __init__(
        self,
        client: ElexonClient,
        settings: Settings,
    ) -> None:
        self._client = client
        self._settings = settings
        self._cache: AsyncTTLCache[tuple[str, str, str], AnalysisBundle] = AsyncTTLCache(
            max_entries=settings.analysis_cache_max_entries,
            ttl_seconds=settings.analysis_cache_ttl_seconds,
        )

    async def dashboard(
        self,
        month_start: date,
        decision_cutoff_time: time,
        alignment_method: str = "hourly_aggregated",
    ) -> DashboardResponse:
        bundle = await self._month(month_start, decision_cutoff_time, alignment_method)
        return DashboardResponse(
            month=month_start.strftime("%Y-%m"),
            metadata=bundle.metadata,
            metrics=bundle.metrics,
            daily_summaries=list(bundle.daily_summaries),
            intervals=list(bundle.intervals),
            monthly_coverage=bundle.monthly_coverage,
        )

    async def metrics(
        self,
        month_start: date,
        decision_cutoff_time: time,
        alignment_method: str = "hourly_aggregated",
    ) -> MetricsResponse:
        bundle = await self._month(month_start, decision_cutoff_time, alignment_method)
        return MetricsResponse(
            month=month_start.strftime("%Y-%m"),
            metadata=bundle.metadata,
            metrics=bundle.metrics,
            monthly_coverage=bundle.monthly_coverage,
        )

    async def intervals(
        self,
        delivery_date: date,
        decision_cutoff_time: time,
        alignment_method: str = "hourly_aggregated",
    ) -> IntervalsResponse:
        month_start = delivery_date.replace(day=1)
        bundle = await self._month(month_start, decision_cutoff_time, alignment_method)
        try:
            zone = ZoneInfo(self._settings.decision_timezone)
        except ZoneInfoNotFoundError as exc:
            raise AnalysisConfigurationError(
                f"timezone data is unavailable for {self._settings.decision_timezone}"
            ) from exc

        rows = [
            row
            for row in bundle.intervals
            if row.delivery_start_local.date() == delivery_date
        ]
        # Recalculate on the selected day so missing values affect daily
        # coverage exactly as they do for the month.
        internal = tuple(
            row
            for row in bundle.internal_matches
            if row.delivery_start_local.date() == delivery_date
        )
        day_actuals = tuple(
            row
            for row in bundle.raw_actuals
            if row.start_time.astimezone(zone).date() == delivery_date
        )
        day_cov = compute_coverage_audit(
            matches=internal,
            actual_records=day_actuals,
            alignment_method=alignment_method,
        )
        return IntervalsResponse(
            delivery_date=delivery_date,
            metadata=bundle.metadata,
            metrics=_metrics_schema(calculate_metrics(internal)),
            monthly_metrics=bundle.metrics,
            intervals=rows,
            day_coverage=day_cov,
            monthly_coverage=bundle.monthly_coverage,
        )

    async def _month(
        self,
        month_start: date,
        decision_cutoff_time: time,
        alignment_method: str = "hourly_aggregated",
    ) -> AnalysisBundle:
        if month_start.day != 1:
            raise AnalysisConfigurationError("month_start must be the first day of a month")
        if decision_cutoff_time.tzinfo is not None:
            raise AnalysisConfigurationError("decision cutoff time must not include a timezone")
        cache_key = (
            month_start.strftime("%Y-%m"),
            decision_cutoff_time.strftime("%H:%M"),
            alignment_method,
        )
        cached = await self._cache.get(cache_key)
        if cached is not None:
            LOGGER.debug("Analysis cache hit", extra={"month": cache_key[0], "alignment": alignment_method})
            return cached

        bundle, _ = await self._build(month_start, decision_cutoff_time, alignment_method)
        await self._cache.set(cache_key, bundle)
        return bundle

    async def _build(
        self,
        month_start: date,
        decision_cutoff_time: time,
        alignment_method: str = "hourly_aggregated",
    ) -> tuple[AnalysisBundle, tuple[IntervalMatch, ...]]:
        month_end = _next_month(month_start)
        try:
            zone = ZoneInfo(self._settings.decision_timezone)
        except ZoneInfoNotFoundError as exc:
            raise AnalysisConfigurationError(
                f"timezone data is unavailable for {self._settings.decision_timezone}"
            ) from exc
        if self._settings.decision_timezone != "Europe/London":
            raise AnalysisConfigurationError(
                "DECISION_TIMEZONE must remain Europe/London for this API contract"
            )

        local_start = datetime.combine(month_start, time.min, tzinfo=zone)
        local_end = datetime.combine(month_end, time.min, tzinfo=zone)
        delivery_start_utc = local_start.astimezone(timezone.utc)
        delivery_end_utc = local_end.astimezone(timezone.utc)
        last_delivery_date = month_end - timedelta(days=1)

        publication_from_local = datetime.combine(
            month_start - timedelta(days=self._settings.forecast_lookback_days),
            time.min,
            tzinfo=zone,
        )
        publication_from_utc = publication_from_local.astimezone(timezone.utc)
        _, publication_to_utc = decision_cutoff_for_date(
            last_delivery_date,
            decision_cutoff_time,
            self._settings.decision_timezone,
        )

        actual_rows, forecast_rows = await asyncio.gather(
            self._client.fetch_fuelhh(month_start, last_delivery_date),
            self._client.fetch_windfor(publication_from_utc, publication_to_utc),
        )
        actual_result = normalize_actual_rows(actual_rows)
        forecast_result = normalize_forecast_rows(forecast_rows)

        native_targets = hourly_starts(delivery_start_utc, delivery_end_utc)
        target_set = set(native_targets)
        actuals = tuple(
            row
            for row in actual_result.records
            if delivery_start_utc <= row.start_time < delivery_end_utc
        )
        relevant_forecasts = tuple(
            row for row in forecast_result.records if row.start_time in target_set
        )
        selection = select_day_before_forecasts(
            relevant_forecasts,
            native_targets,
            decision_cutoff_time,
            self._settings.decision_timezone,
        )

        if alignment_method == "hourly_aggregated":
            matches, complete_pairs, incomplete_pairs = build_hourly_aggregated_matches(
                native_targets,
                actuals,
                selection.selected,
                decision_cutoff_time,
                self._settings.decision_timezone,
            )
            resolution_policy = HOURLY_RESOLUTION_POLICY
        elif alignment_method == "half_hourly":
            expected_starts = half_hour_starts(delivery_start_utc, delivery_end_utc)
            matches = build_interval_matches(
                expected_starts,
                actuals,
                selection.selected,
                decision_cutoff_time,
                self._settings.decision_timezone,
            )
            complete_pairs = len(actuals) // 2
            incomplete_pairs = 0
            resolution_policy = HALF_HOURLY_RESOLUTION_POLICY
        else:
            raise AnalysisConfigurationError(
                f"Unsupported alignment_method '{alignment_method}'. Must be 'hourly_aggregated' or 'half_hourly'."
            )

        metric_result = calculate_metrics(matches)

        warnings = [
            DECISION_POLICY,
            resolution_policy,
            (
                "Forecast history is bounded to "
                f"{self._settings.forecast_lookback_days} days before the month; "
                "targets without an eligible publication remain missing."
            ),
        ]
        if alignment_method == "hourly_aggregated" and incomplete_pairs > 0:
            warnings.append(
                f"{incomplete_pairs} delivery hours had incomplete half-hourly actual pairs "
                "and were excluded from error metrics."
            )
        if metric_result.actual_interval_count == 0:
            warnings.append("No actual WIND intervals were available for this month.")
        elif metric_result.missing_actual_interval_count:
            warnings.append(
                f"{metric_result.missing_actual_interval_count} expected intervals have no actual."
            )
        if metric_result.missing_forecast_interval_count:
            warnings.append(
                f"{metric_result.missing_forecast_interval_count} available actual intervals "
                "have no forecast selected and are excluded from metrics."
            )
        if (
            metric_result.matched_interval_count > 0
            and metric_result.wape_percent is None
        ):
            warnings.append("WAPE is unavailable because matched actual generation sums to zero.")

        observed_native_targets = len({row.start_time for row in relevant_forecasts})
        quality = DataQuality(
            source_actual_record_count=len(actual_rows),
            source_forecast_record_count=len(forecast_rows),
            normalized_actual_interval_count=len(actuals),
            normalized_forecast_version_count=len(relevant_forecasts),
            actual_exact_duplicates_removed=actual_result.exact_duplicates_discarded,
            actual_revisions_resolved=actual_result.revisions_discarded,
            forecast_exact_duplicates_removed=forecast_result.exact_duplicates_discarded,
            observed_native_forecast_target_count=observed_native_targets,
            expected_native_forecast_target_count=len(native_targets),
            selected_native_forecast_count=selection.selected_target_count,
            complete_actual_pairs_count=complete_pairs,
            incomplete_actual_pairs_count=incomplete_pairs,
        )
        retrieved_at = datetime.now(timezone.utc)
        metadata = AnalysisMetadata(
            decision_cutoff_time=decision_cutoff_time.strftime("%H:%M"),
            decision_cutoff_policy=DECISION_POLICY,
            forecast_selection_rule=SELECTION_RULE,
            alignment_method=alignment_method,
            analysis_resolution=resolution_policy,
            delivery_start_utc=delivery_start_utc,
            delivery_end_utc=delivery_end_utc,
            forecast_publication_from_utc=publication_from_utc,
            forecast_publication_to_utc=publication_to_utc,
            retrieved_at_utc=retrieved_at,
            actual_source_url=f"{self._settings.elexon_base_url}{FUELHH_PATH}",
            forecast_source_url=f"{self._settings.elexon_base_url}{WINDFOR_PATH}",
            data_quality=quality,
            warnings=warnings,
        )
        public_intervals = tuple(_interval_schema(row, zone) for row in matches)
        monthly_coverage = compute_coverage_audit(
            matches=matches,
            actual_records=actuals,
            alignment_method=alignment_method,
        )
        daily_summaries = tuple(
            DailySummary(
                delivery_date=day,
                metrics=_metrics_schema(
                    calculate_metrics(
                        tuple(
                            row
                            for row in matches
                            if row.delivery_start_local.date() == day
                        )
                    )
                ),
                coverage=compute_coverage_audit(
                    matches=tuple(
                        row
                        for row in matches
                        if row.delivery_start_local.date() == day
                    ),
                    actual_records=tuple(
                        row
                        for row in actuals
                        if row.start_time.astimezone(zone).date() == day
                    ),
                    alignment_method=alignment_method,
                ),
            )
            for day in _iter_dates(month_start, month_end)
        )
        bundle = AnalysisBundle(
            month_start=month_start,
            metadata=metadata,
            metrics=_metrics_schema(metric_result),
            intervals=public_intervals,
            daily_summaries=daily_summaries,
            internal_matches=matches,
            raw_actuals=actuals,
            monthly_coverage=monthly_coverage,
        )
        return bundle, matches
