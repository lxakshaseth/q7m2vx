# Wind Forecast Intelligence — submission demo script

**Maximum duration:** 10 minutes

**Before recording:** start the application, select a delivery day, and make a
note of the four KPI values shown by that live response. Elexon can revise
historical data, so do not reuse a metric value from a previous recording.

The final local production-container verification used **15 January 2026** at
the **12:00 Europe/London** cut-off. It returned **48 of 48 matched
half-hourly intervals**, **100% forecast coverage**, **MAE 1,189.79 MW**,
**RMSE 1,304.38 MW**, **WAPE 11.26%**, and **bias +1,189.79 MW**. These are
real results from that one live query, not a claim about all dates or a fixed
accuracy result: Elexon can revise historical rows, so read the current screen
values before recording.

## Part 1 — customer presentation (0:00–5:00)

### 0:00–0:35 — Problem and outcome

**Show:** the dashboard header and selected date controls.

> Electricity-system operators make day-ahead decisions using expected wind
> generation. This dashboard makes the forecast quality behind those decisions
> visible: it compares the forecast that would have been available at a
> selected decision point with actual Great Britain wind generation. It focuses
> on January 2026, and makes missing data and forecast availability explicit
> rather than hiding them.

### 0:35–1:25 — Select the decision context

**Show:** delivery-date and day-before decision cut-off selectors. Keep the
default 12:00 Europe/London selected initially.

> I can select a January delivery date and the time at which a day-ahead
> decision would have been made. The displayed 12:00 Europe/London value is a
> configurable demo assumption; the assignment did not prescribe a clock time.
> Changing either control asks the backend to recalculate the selected-day
> comparison. This decision cut-off is not the same thing as the forecast
> publication time, which is shown for each selected forecast later in the
> page.

### 1:25–2:20 — Read the accuracy summary

**Show:** the five summary cards.

> The cards show mean absolute error, root mean squared error, weighted
> absolute percentage error, forecast bias, and the number of matched delivery
> intervals with coverage. MAE describes a typical miss. RMSE puts more weight
> on large misses. WAPE expresses total absolute error relative to actual
> generation. Bias is positive when the forecasts are high on average and
> negative when they are low.

**Say only after reading the current dashboard:**

> For this live selection, MAE is **[read MAE and unit]**, RMSE is **[read
> RMSE and unit]**, WAPE is **[read WAPE]**, and bias is **[read bias and
> unit]**. The coverage is **[read matched/available and percentage]**.

Do not substitute a historical recording value into these brackets.

### 2:20–3:15 — Explain the profile and errors

**Show:** actual-versus-forecast chart, then error chart. Hover one point in
each chart.

> The upper chart compares actual generation with the selected forecast over
> the delivery day. The lower chart shows forecast minus actual, with zero
> clearly marked. Values above zero are over-forecasts; values below zero are
> under-forecasts. The tooltip gives the delivery time, the two MW values, and
> the publication time of the selected forecast version.

> A blank segment is meaningful: it represents missing data, not an estimate.
> The dashboard does not interpolate a missing forecast or actual value.

### 3:15–4:15 — Auditability and decision support

**Show:** half-hourly table and the forecast-publication column; scroll to an
expanded hourly source badge if present.

> The table supports an audit conversation. Each half-hour lists the selected
> forecast, actual generation, signed and absolute error, and the forecast
> publication timestamp. If no forecast is eligible at the selected cut-off,
> the row says so rather than presenting a synthetic value. The hourly WINDFOR
> forecast is explicitly marked where it is repeated to the matching half-hour.

> This lets a planning team distinguish forecast quality from data availability
> and consider whether a different decision time would have changed the
> information available to them.

### 4:15–5:00 — Data quality and close

**Show:** decision policy and data-coverage panel.

> The data-quality panel records the cut-off policy, forecast publication
> history, cadence transformation, revisions, expected intervals, and matched
> intervals. The source scope is Great Britain transmission-system data as
> described by Elexon. The tool therefore supports transparent day-ahead
> evaluation, while making its data and methodology limitations clear.

## Part 2 — technical review (5:00–10:00)

### 5:00–5:40 — Architecture

**Show:** repository tree or architecture diagram, then `/api/health`.

> The application has a React/Vite presentation layer and a FastAPI analysis
> layer. React requests dashboard-ready results; it never calls Elexon and does
> not reproduce forecast selection or metric calculations. FastAPI retrieves,
> validates, normalises, selects, matches, and scores the source records.

### 5:40–6:30 — Elexon integration and source safety

**Show:** `backend/app/services/elexon_client.py` and the source request notes.

> Actual wind generation comes from Elexon FUELHH, queried with
> `settlementDateFrom`, `settlementDateTo`, and `fuelType=WIND`. Forecasts come
> from WINDFOR, queried by `publishDateTimeFrom` and `publishDateTimeTo`.
> Forecast publication history starts before the delivery period, because a
> valid day-ahead forecast can have been published before the first delivery
> day. The HTTP client validates data, bounds retries and timeouts, and returns
> safe API errors instead of creating a misleading partial result.

### 6:30–7:35 — Selection and cadence methodology

**Show:** `backend/app/services/forecast_selection.py`, then one table row.

> For each native hourly delivery target, the backend constructs the selected
> Europe/London time on the preceding calendar day and retains the forecast with
> the greatest publication time less than or equal to that cut-off. A forecast
> published exactly at the cut-off is eligible. Actual revisions are resolved by
> retaining the latest actual publication for the delivery interval.

> FUELHH is half-hourly and WINDFOR is hourly. Rather than silently dropping
> every :30 actual, the selected hourly forecast is repeated across its two
> matching half-hour intervals. That transformation is retained in response
> metadata and flagged in the UI; it does not imply that WINDFOR is natively
> half-hourly.

### 7:35–8:25 — Metrics and tests

**Show:** `backend/app/services/metrics.py`, the test directory, and the test
command result.

> For matched values only, the error is forecast minus actual. MAE is the mean
> absolute error; RMSE is the square root of mean squared error; bias is mean
> signed error; and WAPE is 100 times total absolute error divided by total
> actual generation. A missing forecast or actual is excluded from a metric
> denominator and surfaced in coverage instead.

> The test suite covers normalisation, duplicate and revision handling,
> cut-off selection, metric edge cases, upstream-client validation, API routes,
> and missing-data behaviour. Show the actual passing test count from the final
> verification run; do not state a count that was not produced by the command.

### 8:25–9:20 — Containers and deployment path

**Show:** root Dockerfile, `docker-compose.yml`, then a running container and
the homepage/API health response.

> Local development runs the frontend and backend as separate services using
> Docker Compose. The production Docker build first compiles the Vite frontend,
> then packages its static output with FastAPI into one web image. FastAPI keeps
> `/api` routes and serves the client application for non-API paths. The web
> process honours the platform-provided `PORT` environment variable.

> The project is prepared for Heroku container deployment. No public URL is
> claimed until an authenticated deployment has completed and both the homepage
> and `/api/health` have been checked.

### 9:20–10:00 — Important choices and close

**Show:** README limitations and deployment checklist.

> Important choices are explicit: the decision time is configurable, missing
> records are never fabricated, the hourly-to-half-hour conversion is visible,
> and live source data can be revised. The README includes Windows, Docker,
> production, test, and Heroku instructions, as well as the remaining
> submission checks. This keeps the tool suitable for review rather than
> overstating certainty in live public data.
