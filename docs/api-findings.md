# Elexon API investigation

> Generated from live Elexon responses at `2026-10-27T16:07:14.369172Z` by `scripts/inspect_elexon_api.py`.

No credentials were configured or sent. No fixture, cached response, or sample-data fallback was used. Historical rows may change if Elexon republishes data.

## Official sources and investigation window

- [FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [Official Elexon OpenAPI](https://data.elexon.co.uk/swagger/v1/swagger.json)
- January delivery range, filtered locally as half-open: `2026-01-01T00:00:00Z <= startTime < 2026-02-01T00:00:00Z`.
- Forecast publication request: `2025-12-31T00:00:00Z` through `2026-02-01T00:00:00Z`. It starts on 31 December 2025 so forecasts available before the first January delivery hour are retained.

Elexon describes FUELHH as half-hourly Great Britain generation outturn by fuel type (average MW over each 30 minutes), and WINDFOR as wind generation forecast data.

## Confirmed request parameters

| Endpoint | Exact parameter | OpenAPI type | Meaning / constraint |
| --- | --- | --- | --- |
| `GET /datasets/FUELHH/stream` | `publishDateTimeFrom` | string/date-time | Lower publication-time bound; cannot be combined with a settlement-date field. |
| `GET /datasets/FUELHH/stream` | `publishDateTimeTo` | string/date-time | Upper publication-time bound; cannot be combined with a settlement-date field. |
| `GET /datasets/FUELHH/stream` | `settlementDateFrom` | string/date | Start of the settlement/delivery-date range, exactly yyyy-MM-dd. |
| `GET /datasets/FUELHH/stream` | `settlementDateTo` | string/date | End of the settlement/delivery-date range, exactly yyyy-MM-dd. |
| `GET /datasets/FUELHH/stream` | `settlementPeriod` | array[integer/int32] | List of settlement-period integers. |
| `GET /datasets/FUELHH/stream` | `fuelType` | array[string] | List of fuel types; WIND selects wind outturn. |
| `GET /datasets/WINDFOR/stream` | `publishDateTimeFrom` | string/date-time | Lower publication-time bound. |
| `GET /datasets/WINDFOR/stream` | `publishDateTimeTo` | string/date-time | Upper publication-time bound. |

FUELHH settlement-date and publication-time fields are mutually exclusive. Settlement dates must be `yyyy-MM-dd`. Array parameters use repeated query keys under the OpenAPI form/explode default. WINDFOR exposes no documented delivery or `startTime` filter. The stream endpoints do not document the non-stream endpoint's `format` parameter.

Both stream endpoints document 200, 400, 429, and 500 responses. This run observed 200 and a deliberate 400; it did not provoke throttling or a server failure.

## Live HTTP outcomes

| Probe | HTTP | Response format | Records | Bytes | Attempts |
| --- | ---: | --- | ---: | ---: | ---: |
| Official OpenAPI | 200 | application/json;charset=utf-8; JSON object | n/a | 1,485,139 | 1 |
| FUELHH January settlement dates, WIND | 200 | application/json; charset=utf-8; JSON array | 1,488 | 269,971 | 1 |
| FUELHH January 1 publication window, WIND | 200 | application/json; charset=utf-8; JSON array | 49 | 8,910 | 1 |
| FUELHH exact publication-boundary probe, WIND | 200 | application/json; charset=utf-8; JSON array | 1 | 182 | 1 |
| WINDFOR publications from December 31 through January | 200 | application/json; charset=utf-8; JSON array | 18,688 | 2,105,753 | 1 |
| WINDFOR exact publication-boundary probe | 200 | application/json; charset=utf-8; JSON array | 73 | 8,241 | 1 |
| FUELHH invalid mixed filter families | 400 | application/problem+json; charset=utf-8; JSON object | n/a | 285 | 1 |

Exact request targets (host `https://data.elexon.co.uk`):

- **Official OpenAPI:** `GET /swagger/v1/swagger.json`
- **FUELHH January settlement dates, WIND:** `GET /bmrs/api/v1/datasets/FUELHH/stream?settlementDateFrom=2026-01-01&settlementDateTo=2026-01-31&fuelType=WIND`
- **FUELHH January 1 publication window, WIND:** `GET /bmrs/api/v1/datasets/FUELHH/stream?publishDateTimeFrom=2026-01-01T00%3A00%3A00Z&publishDateTimeTo=2026-01-02T00%3A00%3A00Z&fuelType=WIND`
- **FUELHH exact publication-boundary probe, WIND:** `GET /bmrs/api/v1/datasets/FUELHH/stream?publishDateTimeFrom=2026-01-01T00%3A30%3A00Z&publishDateTimeTo=2026-01-01T00%3A30%3A00Z&fuelType=WIND`
- **WINDFOR publications from December 31 through January:** `GET /bmrs/api/v1/datasets/WINDFOR/stream?publishDateTimeFrom=2025-12-31T00%3A00%3A00Z&publishDateTimeTo=2026-02-01T00%3A00%3A00Z`
- **WINDFOR exact publication-boundary probe:** `GET /bmrs/api/v1/datasets/WINDFOR/stream?publishDateTimeFrom=2025-12-31T02%3A30%3A00Z&publishDateTimeTo=2025-12-31T02%3A30%3A00Z`
- **FUELHH invalid mixed filter families:** `GET /bmrs/api/v1/datasets/FUELHH/stream?settlementDateFrom=2026-01-01&settlementDateTo=2026-01-01&publishDateTimeFrom=2026-01-01T00%3A00%3A00Z`

The exact-boundary probes returned records when `from == to`: FUELHH returned 1 row(s) at the requested publication instant and WINDFOR returned 73. This confirms the server currently treats both publication bounds as inclusive.

## Confirmed schemas

Official types below were read from the live OpenAPI; observed types and missing values are reported separately.

### `/datasets/FUELHH/stream` item schema

| Field | Official OpenAPI type |
| --- | --- |
| `dataset` | string, nullable |
| `publishTime` | string/date-time, nullable |
| `startTime` | string/date-time, nullable |
| `settlementDate` | string/date, nullable |
| `settlementPeriod` | integer/int32, nullable |
| `fuelType` | string, nullable |
| `generation` | integer/int64, nullable |

### `/datasets/WINDFOR/stream` item schema

| Field | Official OpenAPI type |
| --- | --- |
| `dataset` | string, nullable |
| `publishTime` | string/date-time |
| `startTime` | string/date-time |
| `generation` | integer/int64, nullable |

## FUELHH January WIND actuals

- Records: **1,488**.
- Dataset values: `FUELHH`; fuel types: `WIND`.
- Settlement dates: `2026-01-01` through `2026-01-31`.
- Numeric generation range: **1,695 MW** through **17,805 MW**.
- Unique delivery starts: **1,488**; starts with multiple rows: **0**; records beyond one per start: **0**; exact duplicates beyond first: **0**.
- Delivery cadence in seconds: modal **1800**, minimum **1800**, maximum **1800**; non-modal gaps **0**.

- Field names: `dataset`, `fuelType`, `generation`, `publishTime`, `settlementDate`, `settlementPeriod`, `startTime`.

| Field | Observed JSON type(s) | Absent keys | Null values |
| --- | --- | ---: | ---: |
| `dataset` | string | 0 | 0 |
| `fuelType` | string | 0 | 0 |
| `generation` | integer | 0 | 0 |
| `publishTime` | string | 0 | 0 |
| `settlementDate` | string | 0 | 0 |
| `settlementPeriod` | integer | 0 | 0 |
| `startTime` | string | 0 | 0 |

| Timestamp field | Minimum | Maximum | Invalid or missing |
| --- | --- | --- | ---: |
| `publishTime` | `2026-01-01T00:30:00Z` | `2026-02-01T00:00:00Z` | 0 |
| `startTime` | `2026-01-01T00:00:00Z` | `2026-01-31T23:30:00Z` | 0 |

All returned rows are labelled `dataset = FUELHH` and `fuelType = WIND`, and the 30-minute delivery series covers the requested January settlement dates. This confirms the expected national aggregate wind category within Elexon's official Great Britain outturn dataset; it is not an independent measurement audit.

Sanitized earliest record (documented fields only):

```json
{
  "dataset": "FUELHH",
  "fuelType": "WIND",
  "generation": 13756,
  "publishTime": "2026-01-01T00:30:00Z",
  "settlementDate": "2026-01-01",
  "settlementPeriod": 1,
  "startTime": "2026-01-01T00:00:00Z"
}
```

### FUELHH publication-time comparison

The separate publication query returned **49** WIND rows; **0** had missing/invalid `publishTime` or fell outside the requested inclusive publication bounds.

- Field names: `dataset`, `fuelType`, `generation`, `publishTime`, `settlementDate`, `settlementPeriod`, `startTime`.

| Field | Observed JSON type(s) | Absent keys | Null values |
| --- | --- | ---: | ---: |
| `dataset` | string | 0 | 0 |
| `fuelType` | string | 0 | 0 |
| `generation` | integer | 0 | 0 |
| `publishTime` | string | 0 | 0 |
| `settlementDate` | string | 0 | 0 |
| `settlementPeriod` | integer | 0 | 0 |
| `startTime` | string | 0 | 0 |

| Timestamp field | Minimum | Maximum | Invalid or missing |
| --- | --- | --- | ---: |
| `publishTime` | `2026-01-01T00:00:00Z` | `2026-01-02T00:00:00Z` | 0 |
| `startTime` | `2025-12-31T23:30:00Z` | `2026-01-01T23:30:00Z` | 0 |

The settlement-date request targets delivery/settlement dates. The publication request targets `publishTime`, so its `startTime` range differs. A request that mixes those filter families is rejected, as shown below.

## WINDFOR publication history and January delivery targets

- Raw publication-window rows: **18,688**.
- Rows retained after local January `startTime` filtering: **17,904**.
- Unique January delivery starts: **744** of expected **744** hourly starts.
- Delivery starts with multiple records: **744**; records beyond one per start: **17,160**; maximum rows for one start: **32**.
- Exact duplicate records beyond first: **0**. Repeated `startTime` values with distinct `publishTime` values are forecast versions, not exact duplicates.
- Distinct publication versions per January target: min 16, median 24, max 32.
- Versions eligible under `publishTime <= startTime`: min 8, median 19, max 23 per target.
- Targets with a latest eligible version: **744** of **744**.
- Same `(startTime, publishTime)` with conflicting generation values: **0**.
- Unique-target cadence in seconds: modal **3600**, minimum **3600**, maximum **3600**; non-modal gaps **0**.

### Raw publication-window response

- Field names: `dataset`, `generation`, `publishTime`, `startTime`.

| Field | Observed JSON type(s) | Absent keys | Null values |
| --- | --- | ---: | ---: |
| `dataset` | string | 0 | 0 |
| `generation` | integer | 0 | 0 |
| `publishTime` | string | 0 | 0 |
| `startTime` | string | 0 | 0 |

| Timestamp field | Minimum | Maximum | Invalid or missing |
| --- | --- | --- | ---: |
| `publishTime` | `2025-12-31T02:30:00Z` | `2026-01-31T22:30:00Z` | 0 |
| `startTime` | `2025-12-30T21:00:00Z` | `2026-02-02T21:00:00Z` | 0 |

### January-target rows after local filtering

- Field names: `dataset`, `generation`, `publishTime`, `startTime`.

| Field | Observed JSON type(s) | Absent keys | Null values |
| --- | --- | ---: | ---: |
| `dataset` | string | 0 | 0 |
| `generation` | integer | 0 | 0 |
| `publishTime` | string | 0 | 0 |
| `startTime` | string | 0 | 0 |

| Timestamp field | Minimum | Maximum | Invalid or missing |
| --- | --- | --- | ---: |
| `publishTime` | `2025-12-31T02:30:00Z` | `2026-01-31T22:30:00Z` | 0 |
| `startTime` | `2026-01-01T00:00:00Z` | `2026-01-31T23:00:00Z` | 0 |

### January 1 publication history

The query begins at `2025-12-31T00:00:00Z`. It found **24** of 24 January 1 delivery hours. The table shows all versions retrieved for each target and the latest no-look-ahead candidate. This is an investigation selection, not yet a dashboard policy.

For **3** of the 24 January 1 targets, the latest eligible row was published on 31 December 2025. A January-only publication query would therefore omit needed history.

| Delivery start | Publications | Eligible | Earliest observed | Latest observed | Latest eligible | Generation MW |
| --- | ---: | ---: | --- | --- | --- | ---: |
| `2026-01-01T00:00:00Z` | 16 | 8 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2025-12-31T22:30:00Z` | 20032 |
| `2026-01-01T01:00:00Z` | 16 | 8 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2025-12-31T22:30:00Z` | 20017 |
| `2026-01-01T02:00:00Z` | 16 | 8 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2025-12-31T22:30:00Z` | 19966 |
| `2026-01-01T03:00:00Z` | 16 | 9 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T02:30:00Z` | 19907 |
| `2026-01-01T04:00:00Z` | 16 | 9 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T02:30:00Z` | 19673 |
| `2026-01-01T05:00:00Z` | 16 | 10 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T04:30:00Z` | 19574 |
| `2026-01-01T06:00:00Z` | 16 | 10 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T04:30:00Z` | 19554 |
| `2026-01-01T07:00:00Z` | 16 | 10 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T04:30:00Z` | 19612 |
| `2026-01-01T08:00:00Z` | 16 | 11 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T07:30:00Z` | 19378 |
| `2026-01-01T09:00:00Z` | 16 | 11 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T07:30:00Z` | 19319 |
| `2026-01-01T10:00:00Z` | 16 | 12 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T09:30:00Z` | 19401 |
| `2026-01-01T11:00:00Z` | 16 | 12 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T09:30:00Z` | 19778 |
| `2026-01-01T12:00:00Z` | 16 | 13 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T11:30:00Z` | 19918 |
| `2026-01-01T13:00:00Z` | 16 | 13 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T11:30:00Z` | 20345 |
| `2026-01-01T14:00:00Z` | 16 | 13 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T11:30:00Z` | 20442 |
| `2026-01-01T15:00:00Z` | 16 | 13 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T11:30:00Z` | 20369 |
| `2026-01-01T16:00:00Z` | 16 | 14 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T15:30:00Z` | 20327 |
| `2026-01-01T17:00:00Z` | 16 | 14 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T15:30:00Z` | 20339 |
| `2026-01-01T18:00:00Z` | 16 | 14 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T15:30:00Z` | 20162 |
| `2026-01-01T19:00:00Z` | 16 | 15 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T18:30:00Z` | 19622 |
| `2026-01-01T20:00:00Z` | 16 | 15 | `2025-12-31T02:30:00Z` | `2026-01-01T22:30:00Z` | `2026-01-01T18:30:00Z` | 19674 |
| `2026-01-01T21:00:00Z` | 24 | 15 | `2025-12-31T02:30:00Z` | `2026-01-02T22:30:00Z` | `2026-01-01T18:30:00Z` | 19506 |
| `2026-01-01T22:00:00Z` | 24 | 15 | `2025-12-31T02:30:00Z` | `2026-01-02T22:30:00Z` | `2026-01-01T18:30:00Z` | 19386 |
| `2026-01-01T23:00:00Z` | 24 | 16 | `2025-12-31T02:30:00Z` | `2026-01-02T22:30:00Z` | `2026-01-01T22:30:00Z` | 18770 |

Sanitized versions for the first January delivery hour: earliest observed, latest eligible, and latest observed (duplicates omitted):

```json
[
  {
    "dataset": "WINDFOR",
    "generation": 19512,
    "publishTime": "2025-12-31T02:30:00Z",
    "startTime": "2026-01-01T00:00:00Z"
  },
  {
    "dataset": "WINDFOR",
    "generation": 20032,
    "publishTime": "2025-12-31T22:30:00Z",
    "startTime": "2026-01-01T00:00:00Z"
  },
  {
    "dataset": "WINDFOR",
    "generation": 19960,
    "publishTime": "2026-01-01T22:30:00Z",
    "startTime": "2026-01-01T00:00:00Z"
  }
]
```

## Delivery-time versus publication-time filters

- WINDFOR: **0** rows had missing/invalid `publishTime` or fell outside the requested inclusive publication bounds. By contrast, **552** rows had `startTime` outside those bounds. Publication filters therefore do not constrain delivery targets.
- WINDFOR has no documented `startTimeFrom`, `startTimeTo`, settlement-date, or other delivery-time parameter. January targets must be filtered locally after retrieving enough publication history.
- FUELHH settlement-date fields target delivery dates; its publication fields target publication timestamps. The exact-boundary probes confirm inclusive publication bounds in the API behavior observed during this run.

## Observed API error

The deliberately invalid mixed-family FUELHH request returned HTTP **400**, `application/problem+json; charset=utf-8`. The sanitized body below omits Elexon's per-request trace identifier:

```json
{
  "errors": {
    "": [
      "The Settlement Date fields cannot be set when a Publish Date field is set."
    ]
  },
  "status": 400,
  "title": "One or more validation errors occurred.",
  "type": "https://tools.ietf.org/html/rfc9110#section-15.5.1"
}
```

The client retries only transport failures, 429, and 5xx statuses with bounded backoff. It does not retry this deterministic 400.

## Confirmed findings, limitations, and uncertainties

- **Confirmed schema:** FUELHH returns `dataset`, `publishTime`, `startTime`, `settlementDate`, `settlementPeriod`, `fuelType`, and `generation`; WINDFOR returns `dataset`, `publishTime`, `startTime`, and `generation`. Official nullability and observed JSON types are tabulated above.
- **Confirmed parameters:** FUELHH has six documented stream parameters; WINDFOR has only its two publication-time parameters. No undocumented parameter was sent.
- **Geography:** Elexon describes FUELHH as Great Britain generation outturn, not complete United Kingdom generation. Future UI wording must retain that scope.
- **Cadence:** FUELHH is half-hourly; the observed WINDFOR delivery series is hourly. A later analysis phase must explicitly aggregate actuals or repeat hourly forecasts. This script does neither.
- **Forecast choice remains a product decision:** multiple WINDFOR publications exist for each target. Latest-before-delivery, day-ahead, earliest, and fixed-lead policies produce different scores.
- **History window:** starting on 31 December supplies a latest eligible version for every observed January target, including January 1, but is not a complete archive of versions published before that date.
- **Revisions:** this settlement-date FUELHH result has one WIND row per interval. It does not prove that the endpoint exposes every historical actual revision.
- **API limits:** the official endpoint pages do not state a retention guarantee, result-size ceiling, or pagination mechanism. Multi-value array filtering was confirmed by OpenAPI but was not needed for this run.
- **Unobserved errors:** 429 and 500 body shapes remain uncertain; provoking them would be inappropriate. Historical values can also be corrected after this timestamped snapshot.

## Run from Windows PowerShell

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe .\scripts\inspect_elexon_api.py
```

The default report path is `docs/api-findings.md`. Optional flags are `--output`, `--timeout`, and `--attempts`. A failed required request exits non-zero and does not replace the existing report.
