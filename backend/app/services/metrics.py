"""Pure metric calculations over matched forecast/actual intervals."""

from __future__ import annotations

import math
from typing import Sequence

from backend.app.domain import IntervalMatch, MetricResult


def calculate_metrics(intervals: Sequence[IntervalMatch]) -> MetricResult:
    expected_count = len(intervals)
    actual_count = sum(interval.actual is not None for interval in intervals)
    forecast_count = sum(interval.forecast is not None for interval in intervals)
    matched = [
        interval
        for interval in intervals
        if interval.actual is not None and interval.forecast is not None
    ]
    matched_count = len(matched)

    coverage = 100.0 * matched_count / actual_count if actual_count else None
    matched_expected = (
        100.0 * matched_count / expected_count if expected_count else None
    )

    if not matched:
        return MetricResult(
            mae_mw=None,
            rmse_mw=None,
            wape_percent=None,
            bias_mw=None,
            expected_interval_count=expected_count,
            actual_interval_count=actual_count,
            forecast_interval_count=forecast_count,
            matched_interval_count=0,
            missing_actual_interval_count=expected_count - actual_count,
            missing_forecast_interval_count=actual_count,
            forecast_coverage_percent=coverage,
            matched_expected_percent=matched_expected,
            wape_actual_denominator_mw=0.0,
        )

    # Every error is forecast minus actual. Missing intervals never enter a
    # numerator or denominator; their impact is visible in the coverage fields.
    errors = [interval.error_mw for interval in matched]
    numeric_errors = [error for error in errors if error is not None]
    absolute_error_sum = math.fsum(abs(error) for error in numeric_errors)
    squared_error_sum = math.fsum(error * error for error in numeric_errors)
    signed_error_sum = math.fsum(numeric_errors)
    actual_denominator = math.fsum(
        interval.actual.generation_mw
        for interval in matched
        if interval.actual is not None
    )

    return MetricResult(
        mae_mw=absolute_error_sum / matched_count,
        rmse_mw=math.sqrt(squared_error_sum / matched_count),
        wape_percent=(
            100.0 * absolute_error_sum / actual_denominator
            if actual_denominator != 0.0
            else None
        ),
        bias_mw=signed_error_sum / matched_count,
        expected_interval_count=expected_count,
        actual_interval_count=actual_count,
        forecast_interval_count=forecast_count,
        matched_interval_count=matched_count,
        missing_actual_interval_count=expected_count - actual_count,
        missing_forecast_interval_count=actual_count - matched_count,
        forecast_coverage_percent=coverage,
        matched_expected_percent=matched_expected,
        wape_actual_denominator_mw=actual_denominator,
    )
