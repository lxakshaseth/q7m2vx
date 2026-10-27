# FastAPI backend

This service retrieves live historical data from the official Elexon FUELHH
and WINDFOR stream endpoints, applies an explicit day-before forecast policy,
and returns dashboard-ready half-hourly comparisons. It has no database and no
sample-data fallback.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Local liveness check; it does not call Elexon. |
| `GET /api/dashboard?month=2026-01&decision_cutoff_time=12:00` | Monthly metadata, metrics, daily summaries, and interval rows. |
| `GET /api/intervals?delivery_date=2026-01-15&decision_cutoff_time=12:00` | One Europe/London delivery date and its metrics. |
| `GET /api/metrics?month=2026-01&decision_cutoff_time=12:00` | Monthly metrics and metadata without interval rows. |

`month` must be strict `YYYY-MM`; `delivery_date` must be a valid ISO date; and
`decision_cutoff_time` must be strict 24-hour `HH:MM`. The cutoff defaults to
`12:00`. Delivery years are bounded to 2000–2100 to reject pathological date
ranges before an upstream request is attempted.

Response JSON uses camelCase. Every response identifies the delivery range,
retrieval range, source URLs, data-quality counts, decision rule, and cadence
matching policy.

## Adjustable demo assumption

The assignment does not specify a decision clock time. The initial default is:

> 12:00 Europe/London on the calendar day before each delivery date.

This is explicitly labelled as an adjustable demo assumption in API metadata.
For every native WINDFOR delivery hour, the service selects the record with the
greatest `publishTime` satisfying:

```text
publishTime <= preceding local calendar day's decision cutoff
```

The cutoff is constructed in `Europe/London` and then converted to UTC for all
comparisons. Ambiguous or nonexistent user-selected wall-clock cutoffs at DST
transitions are rejected rather than guessed. `tzdata` is an explicit
dependency so this works on Windows.

## Source retrieval and normalization

Only the verified stream parameters are sent:

- FUELHH: `settlementDateFrom`, `settlementDateTo`, and `fuelType=WIND`.
- WINDFOR: `publishDateTimeFrom` and `publishDateTimeTo`.

WINDFOR does not expose a documented delivery-time filter. The client retrieves
a bounded publication history, filters delivery `startTime` locally, and never
uses a forecast published after its cutoff. The default history starts seven
days before the delivery month; this is deliberately conservative and
configurable. A target without an eligible record remains missing.

All timestamps must include an offset and are normalized to aware UTC
datetimes. Europe/London equivalents are included for UI display. Original
actual and forecast publication instants are retained in interval rows.

Duplicate handling follows the observed source semantics:

- Repeated FUELHH delivery starts are potential revisions. Exact repeats are
  collapsed and the greatest actual `publishTime` is retained.
- Repeated WINDFOR delivery starts with different `publishTime` values are
  expected forecast versions and are preserved for selection.
- Exact WINDFOR repeats are collapsed.
- Conflicting generation values at an identical `(startTime, publishTime)` key
  are treated as invalid upstream data; the service does not guess.

FUELHH is natively half-hourly while WINDFOR is natively hourly. After selecting
one forecast version for a native hour, the backend joins it only to the FUELHH
row with the identical normalized UTC `startTime`. Intervening `:30` rows remain
explicitly `missing_forecast`; no forecast is repeated, interpolated, or carried
forward. A complete January therefore has 744 exact matches across 1,488 actual
half-hour rows, or 50% forecast coverage.

## Metrics and missing data

For each matched half-hour, define:

```text
error = forecast MW - actual MW
```

With `n` matched intervals:

```text
MAE  = sum(abs(error)) / n
RMSE = sqrt(sum(error^2) / n)
Bias = sum(error) / n
WAPE = 100 * sum(abs(error)) / sum(actual MW)
```

Only matched intervals enter these formulas. If there are no matches, all four
metrics are `null`. If matched actual generation sums to zero, WAPE alone is
`null`. Positive bias means over-forecasting.

Forecast coverage is:

```text
100 * matched intervals / available actual intervals
```

It is `null` when no actual intervals are available. Expected, actual,
forecast, matched, missing-actual, and missing-forecast counts are returned
separately. Missing forecasts are never filled, interpolated, or replaced with
fabricated values.

## Failure behavior and caching

- Source timeouts become HTTP 504.
- Exhausted 429/5xx retries become HTTP 503.
- Other upstream HTTP failures and invalid Elexon payloads become HTTP 502.
- Query validation and invalid/ambiguous local cutoff times become HTTP 422.
- Error responses and logs do not include upstream bodies, trace IDs, request
  headers, or credentials.

The HTTP client retries only transport/timeouts, 429, and 5xx responses, at
most three attempts with bounded backoff. Successful validated source responses
and completed analyses use bounded in-process TTL caches. Failures and partial
analyses are not cached. Restarting the process clears both caches.

## Run with Windows PowerShell

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

That command is for a PowerShell prompt at the repository root. If you are
already in the `backend` directory, retain the `backend.app.main:app` import
path and add the parent directory explicitly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8000 --reload
```

Without `--app-dir ..`, Python searches from `backend` itself and cannot find
the top-level `backend` package.

In a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod "http://127.0.0.1:8000/api/metrics?month=2026-01&decision_cutoff_time=12:00"
```

If `python` is intercepted by the Windows Store alias, replace it in the first
command with the full path to an installed Python 3.11+ interpreter. Subsequent
commands use the virtual environment directly.

Run the tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest .\backend\tests -q
```

## Optional environment settings

| Variable | Default | Bounds / purpose |
| --- | ---: | --- |
| `ELEXON_BASE_URL` | official API base | Absolute HTTP(S) URL without credentials. |
| `ELEXON_TIMEOUT_SECONDS` | `30` | 1–120 seconds per HTTP operation. |
| `ELEXON_MAX_ATTEMPTS` | `3` | 1–3 total attempts. |
| `ELEXON_BACKOFF_SECONDS` | `0.5` | Initial retry delay. |
| `ELEXON_MAX_RETRY_DELAY_SECONDS` | `8` | Retry-delay cap. |
| `SOURCE_CACHE_TTL_SECONDS` | `900` | Successful raw-response cache TTL. |
| `SOURCE_CACHE_MAX_ENTRIES` | `16` | Bounded raw-response cache size. |
| `ANALYSIS_CACHE_TTL_SECONDS` | `900` | Completed-analysis cache TTL. |
| `ANALYSIS_CACHE_MAX_ENTRIES` | `8` | Bounded analysis cache size. |
| `FORECAST_LOOKBACK_DAYS` | `7` | Publication history before month start. |
| `DECISION_TIMEZONE` | `Europe/London` | Fixed by this API contract. |
| `LOG_LEVEL` | `INFO` | Standard Python log level. |
