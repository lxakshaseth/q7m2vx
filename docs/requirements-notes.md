# Requirements and analysis notes

## Goal

Build a React dashboard backed by FastAPI that evaluates wind-generation forecasts against actual national outturn for the 31-day period **2026-01-01 through 2026-01-31**. The dashboard should make both accuracy and the selection of the compared forecast transparent.

There is a source-resolution conflict that must be resolved openly: FUELHH is half-hourly and WINDFOR is hourly. The raw sources cannot be joined one-to-one on every half-hourly `startTime`. The implementation must choose and label a conversion rule rather than silently omitting `:30` actual rows.

## In-scope behaviour

1. Retrieve actual records from Elexon's `FUELHH/stream` dataset.
2. Retain only `fuelType = WIND` records.
3. Retrieve historical forecast records from `WINDFOR/stream`.
4. Use `startTime` as the native delivery-interval key in both datasets, then derive a common analysis interval using the selected resolution policy.
5. Use `generation` as the MW value in both datasets.
6. Use `publishTime` to decide which forecast was available for a delivery interval.
7. Match one selected forecast with one actual value for the same **normalised analysis interval**; preserve the native source timing and resampling policy in metadata.
8. Return summary metrics, time-series rows, coverage information, and the selected forecast's `publishTime`.

The primary sources are the [FUELHH stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream), [WINDFOR stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream), and the [official OpenAPI specification](https://data.elexon.co.uk/swagger/v1/swagger.json).

## Observed source contract

| Dataset | Relevant fields | Cadence and retrieval implication |
| --- | --- | --- |
| `FUELHH` | `publishTime`, `startTime`, `settlementDate`, `settlementPeriod`, `fuelType`, `generation` | Half-hourly GB generation outturn aggregated by fuel type; values are average MW. Filter to `WIND` and use the delivery interval, not record order. |
| `WINDFOR` | `publishTime`, `startTime`, `generation` | **Hourly** wind forecasts. Multiple forecasts can exist for one delivery hour. Fetch a bounded publication history and select one row per interval locally. |

The stream endpoints return JSON. `FUELHH` supports delivery-date filters or publish-time filters; those filter families should not be combined. `WINDFOR` is queried by publication time, so an analysis request must include publication history from before the target month. Do not infer forecast availability from row order or a hard-coded publishing schedule.

## Implemented forecast-selection convention

The backend requirement now defines a day-before decision point. For each
delivery date, construct a decision cutoff on the preceding local calendar day
in `Europe/London`. The default is **12:00 Europe/London**, clearly labelled in
responses as an adjustable demo assumption because the assignment does not
specify an exact clock time.

> For each native hourly delivery `startTime`, select the forecast with the
> greatest `publishTime` that is less than or equal to that delivery date's
> day-before decision cutoff.

The cutoff time is configurable through the API. Timestamps are compared in
UTC after constructing the cutoff in `Europe/London`; a forecast published
after the cutoff is never eligible. Missing eligible forecasts remain missing
and reduce reported coverage.

Use the half-open UTC delivery range:

```text
2026-01-01T00:00:00Z <= startTime < 2026-02-01T00:00:00Z
```

January is GMT, so UTC and UK civil time align for this requested month. There are **1,488 native FUELHH intervals** and **744 native WINDFOR hours**. Still normalise all parsed timestamps to UTC rather than relying on strings.

For actuals, select the latest `publishTime` if repeated FUELHH rows exist for the same `(startTime, fuelType)`; retain the choice and duplicate count in data-quality metadata. This treats the latest published outturn as the best available actual, rather than pretending historical revisions did not occur.

## Implemented cadence-resolution decision

Elexon's [wind-generation page](https://bmrs.elexon.co.uk/wind-generation) describes WINDFOR as an hourly forecast. The assignment wording asks for matching half-hourly delivery intervals, which is not available natively in both sources. The backend therefore uses the explicit expansion policy below.

| Option | Transformation | Scored rows in January | Trade-off |
| --- | --- | ---: | --- |
| Alternative retained for reference: hourly-aligned | For each forecast hour, average its two FUELHH half-hourly MW values and join to the hourly forecast by the hour start. | 744 | Not implemented. |
| **Implemented: half-hourly expansion** | Select one hourly forecast version, treat it as applying to `[startTime, startTime + 1 hour)`, and repeat it for the `:00` and `:30` actual intervals. | 1,488 | Preserves every actual interval but does not create genuinely half-hourly forecasts. Responses label it `hourly WINDFOR repeated to half-hour intervals`. |

The backend does **not** join only FUELHH records whose minute is `00`; doing so
would silently discard half the actual data. It selects a forecast once for the
native hour, then expands that selected version to both half-hours while
preserving `nativeForecastStart` and `publishTime` in the API response.

Forecast eligibility is evaluated once for the native hourly target against the
day-before cutoff. The selected value and publication timestamp are then copied
to the two matching half-hour keys; selection is not repeated independently for
`:30`.

## Metrics

For each matched interval, let `errorMw = forecastMw - actualMw` and let `n` be the number of matched intervals.

| Metric | Formula | Reason to show it |
| --- | --- | --- |
| MAE | `sum(abs(errorMw)) / n` | Typical miss in MW; easy to interpret. |
| RMSE | `sqrt(sum(errorMw²) / n)` | Makes large misses more visible. |
| Bias | `sum(errorMw) / n` | Shows systematic over-forecasting (positive) or under-forecasting (negative). |
| WAPE | `100 * sum(abs(errorMw)) / sum(actualMw)` | Scale-aware percentage metric that remains defined when individual actual values are zero. |

Do not use MAPE as the headline metric: wind generation can be zero or close to zero. If added later, calculate it only on non-zero actuals and state the excluded-count rule.

## Data-quality rules

- Do not fabricate or forward-fill an actual or forecast value. The only permitted value repetition is the named, reviewer-approved hourly-to-half-hour expansion above.
- Exclude unmatched intervals from metric denominators and report matched, missing-actual, missing-forecast, and duplicate/revision counts.
- Validate that `generation` is numeric and that selected rows fall inside the requested delivery range.
- Record the target delivery range, the publication retrieval range, the selection policy, `analysisResolution`, and data retrieval time in the response metadata.
- Treat source/network failures as visible API errors; do not silently return partial data as a complete month.

## Ambiguities that affect correctness

The cutoff clock time remains adjustable, but the selection and cadence rules
below are now explicit implementation decisions.

1. **Cutoff clock time:** The implemented default is the adjustable 12:00 Europe/London demo assumption. A reviewer-mandated time would change selected versions and scores.
2. **Alternative forecast definitions:** A fixed lead time, earliest forecast, or latest-before-delivery policy would produce different scores; they are not silently substituted.
3. **Cutoff boundary:** A forecast published exactly at the configured decision cutoff is eligible (`<=`).
4. **Actual revisions:** Should scores use the latest revised FUELHH actual, the first published actual, or actual data frozen at a historical cutoff?
5. **Geography:** The brief says UK, while the Elexon description refers to Great Britain transmission-system data. The dashboard should label the source scope accurately unless the brief confirms UK is intended colloquially.
6. **Time boundary:** The default is UTC/UK local midnight through midnight. A different business-day or settlement-day boundary would change included intervals.
7. **Missing and duplicate rows:** Should an incomplete month be rejected, scored on available matches, or surfaced both ways? The default is score matched rows and prominently report coverage.
8. **Percent-error definition:** WAPE is proposed as the primary percentage error. If MAPE, sMAPE, or energy-weighted scoring is mandated, values will differ.
9. **Presentation granularity:** Are interval-only metrics sufficient, or does the reviewer expect daily aggregates, peak-period breakdowns, or forecast-lead buckets?
10. **Reproducibility:** Is a live API result acceptable for the demo, or must a checked-in/snapshotted source response be used to preserve the original analysis?

## Deliberate non-requirements for the first version

- No user accounts, persistence layer, background workers, or database.
- No arbitrary historical date explorer; fix the assignment period first.
- No separate analytics engine or microservices.
- No client-side Elexon calls or duplicated business logic.

## Acceptance checks

- Exactly the requested delivery window is analysed.
- Every scored row has an explicitly defined common analysis interval; the response identifies whether it is hourly-aligned or an hourly forecast expanded to half-hours.
- Every selected forecast satisfies the stated publish-time policy.
- The API reports coverage and selection metadata alongside metrics.
- The UI labels MW, metric units, date range, and forecast convention.
- Fixture-based tests prove duplicate selection, missing-data behaviour, zero-generation behaviour, and metric calculations.
