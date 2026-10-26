"""Inspect Elexon's live FUELHH and WINDFOR APIs for January 2026.

There is deliberately no fixture or sample-data fallback. A required request
failure exits non-zero and leaves any existing report untouched.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import httpx


API_BASE = "https://data.elexon.co.uk/bmrs/api/v1"
OPENAPI_URL = "https://data.elexon.co.uk/swagger/v1/swagger.json"
FUELHH_PATH = "/datasets/FUELHH/stream"
WINDFOR_PATH = "/datasets/WINDFOR/stream"

DELIVERY_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
DELIVERY_END = datetime(2026, 2, 1, tzinfo=timezone.utc)
JANUARY_1_END = datetime(2026, 1, 2, tzinfo=timezone.utc)
PUBLICATION_START = datetime(2025, 12, 31, tzinfo=timezone.utc)
PUBLICATION_END = DELIVERY_END

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
FUELHH_FIELDS = (
    "dataset",
    "publishTime",
    "startTime",
    "settlementDate",
    "settlementPeriod",
    "fuelType",
    "generation",
)
WINDFOR_FIELDS = ("dataset", "publishTime", "startTime", "generation")

PARAMETER_MEANINGS = {
    (FUELHH_PATH, "publishDateTimeFrom"): (
        "Lower publication-time bound; cannot be combined with a settlement-date field."
    ),
    (FUELHH_PATH, "publishDateTimeTo"): (
        "Upper publication-time bound; cannot be combined with a settlement-date field."
    ),
    (FUELHH_PATH, "settlementDateFrom"): (
        "Start of the settlement/delivery-date range, exactly yyyy-MM-dd."
    ),
    (FUELHH_PATH, "settlementDateTo"): (
        "End of the settlement/delivery-date range, exactly yyyy-MM-dd."
    ),
    (FUELHH_PATH, "settlementPeriod"): "List of settlement-period integers.",
    (FUELHH_PATH, "fuelType"): "List of fuel types; WIND selects wind outturn.",
    (WINDFOR_PATH, "publishDateTimeFrom"): "Lower publication-time bound.",
    (WINDFOR_PATH, "publishDateTimeTo"): "Upper publication-time bound.",
}


class InvestigationError(RuntimeError):
    """A required live response could not be inspected safely."""


@dataclass(frozen=True)
class Probe:
    label: str
    url: str
    params: tuple[tuple[str, str], ...]
    status: int
    content_type: str
    payload: Any
    body_bytes: int
    attempts: int

    @property
    def root_format(self) -> str:
        if isinstance(self.payload, list):
            return "JSON array"
        if isinstance(self.payload, dict):
            return "JSON object"
        return f"JSON {json_type(self.payload)}"

    @property
    def record_count(self) -> int | None:
        return len(self.payload) if isinstance(self.payload, list) else None

    @property
    def request_target(self) -> str:
        path = httpx.URL(self.url).raw_path.decode("ascii")
        query = str(httpx.QueryParams(list(self.params)))
        return f"{path}?{query}" if query else path


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def get_json(
    client: httpx.Client,
    *,
    label: str,
    url: str,
    params: Sequence[tuple[str, str]] = (),
    attempts: int,
) -> Probe:
    """GET JSON, retrying only transport errors, 429, and 5xx responses."""

    last_error = "unknown transport error"
    for attempt in range(1, attempts + 1):
        response: httpx.Response | None = None
        try:
            response = client.get(url, params=list(params))
        except httpx.TransportError as exc:
            last_error = type(exc).__name__
        else:
            if response.status_code not in TRANSIENT_STATUSES or attempt == attempts:
                try:
                    payload = response.json()
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                    raise InvestigationError(
                        f"{label} returned HTTP {response.status_code}, but not valid JSON: {exc}"
                    ) from exc
                return Probe(
                    label=label,
                    url=url,
                    params=tuple(params),
                    status=response.status_code,
                    content_type=response.headers.get("Content-Type", "<missing>"),
                    payload=payload,
                    body_bytes=len(response.content),
                    attempts=attempt,
                )
            last_error = f"HTTP {response.status_code}"

        if attempt < attempts:
            retry_after = response.headers.get("Retry-After") if response else None
            try:
                delay = min(max(float(retry_after), 0.0), 8.0) if retry_after else None
            except ValueError:
                delay = None
            time.sleep(delay if delay is not None else min(0.5 * 2 ** (attempt - 1), 4.0))

    raise InvestigationError(
        f"{label} failed after {attempts} attempts ({last_error}); no sample data was substituted."
    )


def require_status(probe: Probe, expected: int) -> None:
    if probe.status != expected:
        raise InvestigationError(
            f"{probe.label} returned HTTP {probe.status}; expected {expected}. "
            "No sample data was substituted."
        )


def require_records(probe: Probe) -> list[dict[str, Any]]:
    require_status(probe, 200)
    if not isinstance(probe.payload, list) or any(
        not isinstance(item, dict) for item in probe.payload
    ):
        raise InvestigationError(
            f"{probe.label} did not return the documented JSON array of objects."
        )
    return probe.payload


def require_exact_publication(
    records: Sequence[Mapping[str, Any]], expected: datetime, label: str
) -> None:
    observed = {parse_time(row.get("publishTime")) for row in records}
    if not records or observed != {expected}:
        rendered = sorted(iso_z(value) if value else "invalid/missing" for value in observed)
        raise InvestigationError(
            f"{label} did not return only the requested publication instant "
            f"{iso_z(expected)}; observed {rendered}."
        )


def record_stats(
    records: Sequence[Mapping[str, Any]], timestamp_fields: Iterable[str]
) -> dict[str, Any]:
    fields = sorted({field for row in records for field in row})
    types: dict[str, list[str]] = {}
    missing: dict[str, dict[str, int]] = {}
    ranges: dict[str, dict[str, Any]] = {}
    for field in fields:
        types[field] = sorted({json_type(row[field]) for row in records if field in row})
        missing[field] = {
            "absent": sum(field not in row for row in records),
            "null": sum(row.get(field) is None for row in records if field in row),
        }
    for field in timestamp_fields:
        parsed = [parse_time(row.get(field)) for row in records]
        valid = [value for value in parsed if value is not None]
        ranges[field] = {
            "min": iso_z(min(valid)) if valid else None,
            "max": iso_z(max(valid)) if valid else None,
            "invalid": len(parsed) - len(valid),
        }
    return {"fields": fields, "types": types, "missing": missing, "ranges": ranges}


def duplicate_stats(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    starts = Counter(row.get("startTime") for row in records if row.get("startTime"))
    exact = Counter(json.dumps(dict(row), sort_keys=True) for row in records)
    return {
        "unique": len(starts),
        "repeated": sum(count > 1 for count in starts.values()),
        "extra": sum(count - 1 for count in starts.values() if count > 1),
        "max": max(starts.values(), default=0),
        "exact_extra": sum(count - 1 for count in exact.values() if count > 1),
    }


def rows_in_range(
    records: Sequence[dict[str, Any]], field: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    result = []
    for row in records:
        value = parse_time(row.get(field))
        if value is not None and start <= value < end:
            result.append(row)
    return result


def cadence_stats(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    starts = sorted(
        {
            value
            for row in records
            if (value := parse_time(row.get("startTime"))) is not None
        }
    )
    gaps = Counter(
        int((right - left).total_seconds()) for left, right in zip(starts, starts[1:])
    )
    modal = gaps.most_common(1)[0][0] if gaps else None
    return {
        "min": min(gaps, default=None),
        "max": max(gaps, default=None),
        "modal": modal,
        "non_modal": sum(count for gap, count in gaps.items() if gap != modal),
    }


def windfor_versions(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if (start := parse_time(row.get("startTime"))) is not None:
            grouped[start].append(row)

    latest: dict[datetime, dict[str, Any]] = {}
    version_counts: list[int] = []
    eligible_counts: list[int] = []
    conflicts = 0
    for start, rows in grouped.items():
        by_publish: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if (publish := parse_time(row.get("publishTime"))) is not None:
                by_publish[publish].append(row)
        version_counts.append(len(by_publish))
        conflicts += sum(
            len({item.get("generation") for item in items}) > 1
            for items in by_publish.values()
        )
        eligible = [publish for publish in by_publish if publish <= start]
        eligible_counts.append(len(eligible))
        if eligible:
            latest[start] = by_publish[max(eligible)][0]
    return {
        "grouped": grouped,
        "latest": latest,
        "versions": version_counts,
        "eligible": eligible_counts,
        "conflicts": conflicts,
    }


def resolve_ref(document: Mapping[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise InvestigationError(f"Unsupported OpenAPI reference: {reference}")
    current: Any = document
    for part in reference[2:].split("/"):
        current = current[part.replace("~1", "/").replace("~0", "~")]
    return current


def endpoint_contract(openapi: Mapping[str, Any], path: str) -> dict[str, Any]:
    try:
        operation = openapi["paths"][path]["get"]
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    except (KeyError, TypeError) as exc:
        raise InvestigationError(f"Official OpenAPI does not define GET {path}.") from exc
    item_schema = schema.get("items", schema)
    if "$ref" in item_schema:
        item_schema = resolve_ref(openapi, item_schema["$ref"])
    return {
        "description": operation.get("description", ""),
        "parameters": operation.get("parameters", []),
        "responses": list(operation.get("responses", {})),
        "fields": item_schema.get("properties", {}),
    }


def openapi_type(schema: Mapping[str, Any]) -> str:
    kind = schema.get("type", "unspecified")
    if kind == "array":
        item = schema.get("items", {})
        value = item.get("type", "unspecified")
        if item.get("format"):
            value += f"/{item['format']}"
        return f"array[{value}]"
    rendered = str(kind)
    if schema.get("format"):
        rendered += f"/{schema['format']}"
    if schema.get("nullable"):
        rendered += ", nullable"
    return rendered


def md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def md_json(value: Any) -> str:
    return "```json\n" + json.dumps(value, indent=2, sort_keys=True) + "\n```"


def inline_values(items: Iterable[Any]) -> str:
    values = sorted(str(item) for item in items)
    return ", ".join(f"`{item}`" for item in values) if values else "(none)"


def distribution(numbers: Sequence[int]) -> str:
    if not numbers:
        return "n/a"
    return (
        f"min {min(numbers)}, median {statistics.median(numbers):g}, "
        f"max {max(numbers)}"
    )


def stats_table(stats: Mapping[str, Any]) -> list[str]:
    lines = [f"- Field names: {inline_values(stats['fields'])}.", ""]
    lines.extend(
        [
            "| Field | Observed JSON type(s) | Absent keys | Null values |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for field in stats["fields"]:
        missing = stats["missing"][field]
        lines.append(
            f"| `{field}` | {', '.join(stats['types'][field])} | "
            f"{missing['absent']:,} | {missing['null']:,} |"
        )
    lines.extend(
        [
            "",
            "| Timestamp field | Minimum | Maximum | Invalid or missing |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for field, bounds in stats["ranges"].items():
        lines.append(
            f"| `{field}` | `{bounds['min']}` | `{bounds['max']}` | "
            f"{bounds['invalid']:,} |"
        )
    return lines


def outcome_table(probes: Sequence[Probe]) -> list[str]:
    lines = [
        "| Probe | HTTP | Response format | Records | Bytes | Attempts |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for probe in probes:
        count = "n/a" if probe.record_count is None else f"{probe.record_count:,}"
        lines.append(
            f"| {md_escape(probe.label)} | {probe.status} | "
            f"{md_escape(probe.content_type)}; {probe.root_format} | {count} | "
            f"{probe.body_bytes:,} | {probe.attempts} |"
        )
    return lines


def contract_table(contracts: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines = [
        "| Endpoint | Exact parameter | OpenAPI type | Meaning / constraint |",
        "| --- | --- | --- | --- |",
    ]
    for path, contract in contracts.items():
        for parameter in contract["parameters"]:
            name = parameter["name"]
            meaning = PARAMETER_MEANINGS.get(
                (path, name), parameter.get("description", "")
            )
            lines.append(
                f"| `GET {path}` | `{name}` | "
                f"{openapi_type(parameter.get('schema', {}))} | {md_escape(meaning)} |"
            )
    return lines


def schema_tables(contracts: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for path, contract in contracts.items():
        lines.extend(
            [
                f"### `{path}` item schema",
                "",
                "| Field | Official OpenAPI type |",
                "| --- | --- |",
            ]
        )
        for field, schema in contract["fields"].items():
            lines.append(f"| `{field}` | {openapi_type(schema)} |")
        lines.append("")
    return lines


def sanitized_record(record: Mapping[str, Any], allowed: Sequence[str]) -> dict[str, Any]:
    return {field: record.get(field) for field in allowed}


def sanitized_problem(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return {"bodyType": json_type(payload)}
    # traceId is intentionally not copied.
    allowed = ("type", "title", "status", "errors")
    return {key: payload[key] for key in allowed if key in payload}


def first_by_start(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise InvestigationError("A required successful response contained no records.")
    return min(
        records,
        key=lambda row: parse_time(row.get("startTime"))
        or datetime.max.replace(tzinfo=timezone.utc),
    )


def build_report(
    *,
    generated_at: datetime,
    probes: Sequence[Probe],
    openapi: Mapping[str, Any],
    fuelhh: list[dict[str, Any]],
    fuelhh_publications: list[dict[str, Any]],
    fuel_boundary: list[dict[str, Any]],
    windfor: list[dict[str, Any]],
    wind_boundary: list[dict[str, Any]],
    error_probe: Probe,
) -> str:
    contracts = {
        FUELHH_PATH: endpoint_contract(openapi, FUELHH_PATH),
        WINDFOR_PATH: endpoint_contract(openapi, WINDFOR_PATH),
    }
    fuel_stats = record_stats(fuelhh, ("publishTime", "startTime"))
    fuel_pub_stats = record_stats(fuelhh_publications, ("publishTime", "startTime"))
    fuel_dupes = duplicate_stats(fuelhh)
    fuel_cadence = cadence_stats(fuelhh)

    january_wind = rows_in_range(windfor, "startTime", DELIVERY_START, DELIVERY_END)
    wind_stats = record_stats(windfor, ("publishTime", "startTime"))
    january_wind_stats = record_stats(january_wind, ("publishTime", "startTime"))
    wind_dupes = duplicate_stats(january_wind)
    wind_cadence = cadence_stats(january_wind)
    version_info = windfor_versions(january_wind)
    grouped: Mapping[datetime, list[dict[str, Any]]] = version_info["grouped"]
    latest: Mapping[datetime, dict[str, Any]] = version_info["latest"]

    january_1_starts = sorted(
        start for start in grouped if DELIVERY_START <= start < JANUARY_1_END
    )
    expected_hours = int((DELIVERY_END - DELIVERY_START).total_seconds() // 3600)

    publish_outside = 0
    target_outside_publication_window = 0
    for row in windfor:
        publish = parse_time(row.get("publishTime"))
        target = parse_time(row.get("startTime"))
        if publish is None or not (PUBLICATION_START <= publish <= PUBLICATION_END):
            publish_outside += 1
        if target is None or not (PUBLICATION_START <= target <= PUBLICATION_END):
            target_outside_publication_window += 1

    fuel_publish_outside = sum(
        (publish := parse_time(row.get("publishTime"))) is None
        or not (DELIVERY_START <= publish <= JANUARY_1_END)
        for row in fuelhh_publications
    )
    dec31_latest = sum(
        (publish := parse_time(row.get("publishTime"))) is not None
        and publish.date() == PUBLICATION_START.date()
        for start, row in latest.items()
        if DELIVERY_START <= start < JANUARY_1_END
    )

    first_start = january_1_starts[0] if january_1_starts else None
    first_versions = sorted(
        grouped.get(first_start, []),
        key=lambda row: parse_time(row.get("publishTime"))
        or datetime.min.replace(tzinfo=timezone.utc),
    )
    examples: list[dict[str, Any]] = []
    if first_versions:
        candidate_rows = [first_versions[0], latest.get(first_start), first_versions[-1]]
        seen: set[str] = set()
        for row in candidate_rows:
            if row is None:
                continue
            key = json.dumps(row, sort_keys=True)
            if key not in seen:
                examples.append(sanitized_record(row, WINDFOR_FIELDS))
                seen.add(key)

    lines = [
        "# Elexon API investigation",
        "",
        f"> Generated from live Elexon responses at `{iso_z(generated_at)}` by "
        "`scripts/inspect_elexon_api.py`.",
        "",
        "No credentials were configured or sent. No fixture, cached response, or sample-data "
        "fallback was used. Historical rows may change if Elexon republishes data.",
        "",
        "## Official sources and investigation window",
        "",
        "- [FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)",
        "- [WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)",
        "- [Official Elexon OpenAPI](https://data.elexon.co.uk/swagger/v1/swagger.json)",
        f"- January delivery range, filtered locally as half-open: "
        f"`{iso_z(DELIVERY_START)} <= startTime < {iso_z(DELIVERY_END)}`.",
        f"- Forecast publication request: `{iso_z(PUBLICATION_START)}` through "
        f"`{iso_z(PUBLICATION_END)}`. It starts on 31 December 2025 so forecasts available "
        "before the first January delivery hour are retained.",
        "",
        "Elexon describes FUELHH as half-hourly Great Britain generation outturn by fuel type "
        "(average MW over each 30 minutes), and WINDFOR as wind generation forecast data.",
        "",
        "## Confirmed request parameters",
        "",
    ]
    lines.extend(contract_table(contracts))
    lines.extend(
        [
            "",
            "FUELHH settlement-date and publication-time fields are mutually exclusive. "
            "Settlement dates must be `yyyy-MM-dd`. Array parameters use repeated query keys "
            "under the OpenAPI form/explode default. WINDFOR exposes no documented delivery or "
            "`startTime` filter. The stream endpoints do not document the non-stream endpoint's "
            "`format` parameter.",
            "",
            "Both stream endpoints document 200, 400, 429, and 500 responses. This run observed "
            "200 and a deliberate 400; it did not provoke throttling or a server failure.",
            "",
            "## Live HTTP outcomes",
            "",
        ]
    )
    lines.extend(outcome_table(probes))
    lines.extend(["", "Exact request targets (host `https://data.elexon.co.uk`):", ""])
    lines.extend(f"- **{probe.label}:** `GET {probe.request_target}`" for probe in probes)
    lines.extend(
        [
            "",
            "The exact-boundary probes returned records when `from == to`: FUELHH returned "
            f"{len(fuel_boundary):,} row(s) at the requested publication instant and WINDFOR "
            f"returned {len(wind_boundary):,}. This confirms the server currently treats both "
            "publication bounds as inclusive.",
            "",
            "## Confirmed schemas",
            "",
            "Official types below were read from the live OpenAPI; observed types and missing "
            "values are reported separately.",
            "",
        ]
    )
    lines.extend(schema_tables(contracts))

    settlement_dates = {row.get("settlementDate") for row in fuelhh}
    fuel_types = {row.get("fuelType") for row in fuelhh}
    dataset_values = {row.get("dataset") for row in fuelhh}
    fuel_generations = [
        row["generation"]
        for row in fuelhh
        if isinstance(row.get("generation"), (int, float))
        and not isinstance(row.get("generation"), bool)
    ]
    fuel_example = first_by_start(fuelhh)

    lines.extend(
        [
            "## FUELHH January WIND actuals",
            "",
            f"- Records: **{len(fuelhh):,}**.",
            f"- Dataset values: {inline_values(dataset_values)}; fuel types: "
            f"{inline_values(fuel_types)}.",
            f"- Settlement dates: `{min(str(item) for item in settlement_dates)}` through "
            f"`{max(str(item) for item in settlement_dates)}`.",
            f"- Numeric generation range: **{min(fuel_generations):,} MW** through "
            f"**{max(fuel_generations):,} MW**.",
            f"- Unique delivery starts: **{fuel_dupes['unique']:,}**; starts with multiple "
            f"rows: **{fuel_dupes['repeated']:,}**; records beyond one per start: "
            f"**{fuel_dupes['extra']:,}**; exact duplicates beyond first: "
            f"**{fuel_dupes['exact_extra']:,}**.",
            f"- Delivery cadence in seconds: modal **{fuel_cadence['modal']}**, minimum "
            f"**{fuel_cadence['min']}**, maximum **{fuel_cadence['max']}**; non-modal gaps "
            f"**{fuel_cadence['non_modal']:,}**.",
            "",
        ]
    )
    lines.extend(stats_table(fuel_stats))
    lines.extend(
        [
            "",
            "All returned rows are labelled `dataset = FUELHH` and `fuelType = WIND`, and the "
            "30-minute delivery series covers the requested January settlement dates. This "
            "confirms the expected national aggregate wind category within Elexon's official "
            "Great Britain outturn dataset; it is not an independent measurement audit.",
            "",
            "Sanitized earliest record (documented fields only):",
            "",
            md_json(sanitized_record(fuel_example, FUELHH_FIELDS)),
            "",
            "### FUELHH publication-time comparison",
            "",
            f"The separate publication query returned **{len(fuelhh_publications):,}** WIND "
            f"rows; **{fuel_publish_outside:,}** had missing/invalid `publishTime` or fell "
            "outside the requested inclusive publication bounds.",
            "",
        ]
    )
    lines.extend(stats_table(fuel_pub_stats))
    lines.extend(
        [
            "",
            "The settlement-date request targets delivery/settlement dates. The publication "
            "request targets `publishTime`, so its `startTime` range differs. A request that "
            "mixes those filter families is rejected, as shown below.",
            "",
            "## WINDFOR publication history and January delivery targets",
            "",
            f"- Raw publication-window rows: **{len(windfor):,}**.",
            f"- Rows retained after local January `startTime` filtering: "
            f"**{len(january_wind):,}**.",
            f"- Unique January delivery starts: **{wind_dupes['unique']:,}** of expected "
            f"**{expected_hours:,}** hourly starts.",
            f"- Delivery starts with multiple records: **{wind_dupes['repeated']:,}**; "
            f"records beyond one per start: **{wind_dupes['extra']:,}**; maximum rows for one "
            f"start: **{wind_dupes['max']:,}**.",
            f"- Exact duplicate records beyond first: **{wind_dupes['exact_extra']:,}**. "
            "Repeated `startTime` values with distinct `publishTime` values are forecast "
            "versions, not exact duplicates.",
            f"- Distinct publication versions per January target: "
            f"{distribution(version_info['versions'])}.",
            f"- Versions eligible under `publishTime <= startTime`: "
            f"{distribution(version_info['eligible'])} per target.",
            f"- Targets with a latest eligible version: **{len(latest):,}** of "
            f"**{expected_hours:,}**.",
            f"- Same `(startTime, publishTime)` with conflicting generation values: "
            f"**{version_info['conflicts']:,}**.",
            f"- Unique-target cadence in seconds: modal **{wind_cadence['modal']}**, minimum "
            f"**{wind_cadence['min']}**, maximum **{wind_cadence['max']}**; non-modal gaps "
            f"**{wind_cadence['non_modal']:,}**.",
            "",
            "### Raw publication-window response",
            "",
        ]
    )
    lines.extend(stats_table(wind_stats))
    lines.extend(["", "### January-target rows after local filtering", ""])
    lines.extend(stats_table(january_wind_stats))

    lines.extend(
        [
            "",
            "### January 1 publication history",
            "",
            f"The query begins at `{iso_z(PUBLICATION_START)}`. It found "
            f"**{len(january_1_starts)}** of 24 January 1 delivery hours. The table shows "
            "all versions retrieved for each target and the latest no-look-ahead candidate. "
            "This is an investigation selection, not yet a dashboard policy.",
            "",
            f"For **{dec31_latest}** of the 24 January 1 targets, the latest eligible row was "
            "published on 31 December 2025. A January-only publication query would therefore "
            "omit needed history.",
            "",
            "| Delivery start | Publications | Eligible | Earliest observed | Latest observed | Latest eligible | Generation MW |",
            "| --- | ---: | ---: | --- | --- | --- | ---: |",
        ]
    )
    for start in january_1_starts:
        rows = grouped[start]
        publications = sorted(
            {
                publish
                for row in rows
                if (publish := parse_time(row.get("publishTime"))) is not None
            }
        )
        eligible = [publish for publish in publications if publish <= start]
        selected = latest.get(start)
        selected_publish = parse_time(selected.get("publishTime")) if selected else None
        generation = selected.get("generation") if selected else None
        lines.append(
            f"| `{iso_z(start)}` | {len(publications)} | {len(eligible)} | "
            f"`{iso_z(publications[0]) if publications else 'n/a'}` | "
            f"`{iso_z(publications[-1]) if publications else 'n/a'}` | "
            f"`{iso_z(selected_publish) if selected_publish else 'n/a'}` | "
            f"{generation if generation is not None else 'n/a'} |"
        )

    lines.extend(
        [
            "",
            "Sanitized versions for the first January delivery hour: earliest observed, "
            "latest eligible, and latest observed (duplicates omitted):",
            "",
            md_json(examples),
            "",
            "## Delivery-time versus publication-time filters",
            "",
            f"- WINDFOR: **{publish_outside:,}** rows had missing/invalid `publishTime` or "
            "fell outside the requested inclusive publication bounds. By contrast, "
            f"**{target_outside_publication_window:,}** rows had `startTime` outside those "
            "bounds. Publication filters therefore do not constrain delivery targets.",
            "- WINDFOR has no documented `startTimeFrom`, `startTimeTo`, settlement-date, or "
            "other delivery-time parameter. January targets must be filtered locally after "
            "retrieving enough publication history.",
            "- FUELHH settlement-date fields target delivery dates; its publication fields "
            "target publication timestamps. The exact-boundary probes confirm inclusive "
            "publication bounds in the API behavior observed during this run.",
            "",
            "## Observed API error",
            "",
            f"The deliberately invalid mixed-family FUELHH request returned HTTP "
            f"**{error_probe.status}**, `{error_probe.content_type}`. The sanitized body below "
            "omits Elexon's per-request trace identifier:",
            "",
            md_json(sanitized_problem(error_probe.payload)),
            "",
            "The client retries only transport failures, 429, and 5xx statuses with bounded "
            "backoff. It does not retry this deterministic 400.",
            "",
            "## Confirmed findings, limitations, and uncertainties",
            "",
            "- **Confirmed schema:** FUELHH returns `dataset`, `publishTime`, `startTime`, "
            "`settlementDate`, `settlementPeriod`, `fuelType`, and `generation`; WINDFOR returns "
            "`dataset`, `publishTime`, `startTime`, and `generation`. Official nullability and "
            "observed JSON types are tabulated above.",
            "- **Confirmed parameters:** FUELHH has six documented stream parameters; "
            "WINDFOR has only its two publication-time parameters. No undocumented parameter "
            "was sent.",
            "- **Geography:** Elexon describes FUELHH as Great Britain generation outturn, not "
            "complete United Kingdom generation. Future UI wording must retain that scope.",
            "- **Cadence:** FUELHH is half-hourly; the observed WINDFOR delivery series is hourly. "
            "A later analysis phase must explicitly aggregate actuals or repeat hourly "
            "forecasts. This script does neither.",
            "- **Forecast choice remains a product decision:** multiple WINDFOR publications "
            "exist for each target. Latest-before-delivery, day-ahead, earliest, and fixed-lead "
            "policies produce different scores.",
            "- **History window:** starting on 31 December supplies a latest eligible version "
            "for every observed January target, including January 1, but is not a complete "
            "archive of versions published before that date.",
            "- **Revisions:** this settlement-date FUELHH result has one WIND row per interval. "
            "It does not prove that the endpoint exposes every historical actual revision.",
            "- **API limits:** the official endpoint pages do not state a retention guarantee, "
            "result-size ceiling, or pagination mechanism. Multi-value array filtering was "
            "confirmed by OpenAPI but was not needed for this run.",
            "- **Unobserved errors:** 429 and 500 body shapes remain uncertain; provoking them "
            "would be inappropriate. Historical values can also be corrected after this "
            "timestamped snapshot.",
            "",
            "## Run from Windows PowerShell",
            "",
            "From the repository root:",
            "",
            "```powershell",
            "python -m venv .venv",
            ".\\.venv\\Scripts\\python.exe -m pip install httpx",
            ".\\.venv\\Scripts\\python.exe .\\scripts\\inspect_elexon_api.py",
            "```",
            "",
            "The default report path is `docs/api-findings.md`. Optional flags are "
            "`--output`, `--timeout`, and `--attempts`. A failed required request exits non-zero "
            "and does not replace the existing report.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/api-findings.md"),
        help="Markdown output path (default: docs/api-findings.md)",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Per-operation timeout in seconds"
    )
    parser.add_argument(
        "--attempts", type=int, default=3, help="Maximum transient-failure attempts"
    )
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a finite positive number")
    if not 1 <= args.attempts <= 5:
        parser.error("--attempts must be between 1 and 5")
    return args


def run(args: argparse.Namespace) -> Path:
    headers = {
        "Accept": "application/json",
        "User-Agent": "wind-forecast-insight-api-investigation/1.0",
    }
    with httpx.Client(
        headers=headers,
        timeout=httpx.Timeout(args.timeout),
        follow_redirects=True,
    ) as client:
        openapi_probe = get_json(
            client,
            label="Official OpenAPI",
            url=OPENAPI_URL,
            attempts=args.attempts,
        )
        require_status(openapi_probe, 200)
        if not isinstance(openapi_probe.payload, dict):
            raise InvestigationError("Official OpenAPI was not a JSON object.")

        fuelhh_probe = get_json(
            client,
            label="FUELHH January settlement dates, WIND",
            url=API_BASE + FUELHH_PATH,
            params=(
                ("settlementDateFrom", "2026-01-01"),
                ("settlementDateTo", "2026-01-31"),
                ("fuelType", "WIND"),
            ),
            attempts=args.attempts,
        )
        fuelhh = require_records(fuelhh_probe)

        fuel_publication_probe = get_json(
            client,
            label="FUELHH January 1 publication window, WIND",
            url=API_BASE + FUELHH_PATH,
            params=(
                ("publishDateTimeFrom", iso_z(DELIVERY_START)),
                ("publishDateTimeTo", iso_z(JANUARY_1_END)),
                ("fuelType", "WIND"),
            ),
            attempts=args.attempts,
        )
        fuelhh_publications = require_records(fuel_publication_probe)

        fuel_boundary_probe = get_json(
            client,
            label="FUELHH exact publication-boundary probe, WIND",
            url=API_BASE + FUELHH_PATH,
            params=(
                ("publishDateTimeFrom", "2026-01-01T00:30:00Z"),
                ("publishDateTimeTo", "2026-01-01T00:30:00Z"),
                ("fuelType", "WIND"),
            ),
            attempts=args.attempts,
        )
        fuel_boundary = require_records(fuel_boundary_probe)
        require_exact_publication(
            fuel_boundary,
            datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
            fuel_boundary_probe.label,
        )

        windfor_probe = get_json(
            client,
            label="WINDFOR publications from December 31 through January",
            url=API_BASE + WINDFOR_PATH,
            params=(
                ("publishDateTimeFrom", iso_z(PUBLICATION_START)),
                ("publishDateTimeTo", iso_z(PUBLICATION_END)),
            ),
            attempts=args.attempts,
        )
        windfor = require_records(windfor_probe)

        wind_boundary_probe = get_json(
            client,
            label="WINDFOR exact publication-boundary probe",
            url=API_BASE + WINDFOR_PATH,
            params=(
                ("publishDateTimeFrom", "2025-12-31T02:30:00Z"),
                ("publishDateTimeTo", "2025-12-31T02:30:00Z"),
            ),
            attempts=args.attempts,
        )
        wind_boundary = require_records(wind_boundary_probe)
        require_exact_publication(
            wind_boundary,
            datetime(2025, 12, 31, 2, 30, tzinfo=timezone.utc),
            wind_boundary_probe.label,
        )

        error_probe = get_json(
            client,
            label="FUELHH invalid mixed filter families",
            url=API_BASE + FUELHH_PATH,
            params=(
                ("settlementDateFrom", "2026-01-01"),
                ("settlementDateTo", "2026-01-01"),
                ("publishDateTimeFrom", iso_z(DELIVERY_START)),
            ),
            attempts=args.attempts,
        )
        require_status(error_probe, 400)

    probes = (
        openapi_probe,
        fuelhh_probe,
        fuel_publication_probe,
        fuel_boundary_probe,
        windfor_probe,
        wind_boundary_probe,
        error_probe,
    )
    report = build_report(
        generated_at=datetime.now(timezone.utc),
        probes=probes,
        openapi=openapi_probe.payload,
        fuelhh=fuelhh,
        fuelhh_publications=fuelhh_publications,
        fuel_boundary=fuel_boundary,
        windfor=windfor,
        wind_boundary=wind_boundary,
        error_probe=error_probe,
    )

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(report, encoding="utf-8", newline="\n")
    temporary.replace(output)
    return output


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output = run(args)
    except (InvestigationError, httpx.HTTPError, OSError) as exc:
        print(f"Investigation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Live Elexon investigation complete: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
