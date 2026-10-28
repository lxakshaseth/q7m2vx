"""Independent verification of January 2026 Elexon FUELHH actuals and WINDFOR forecasts."""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.app.config import Settings
from backend.app.services.elexon_client import ElexonClient
from backend.app.services.forecast_selection import decision_cutoff_for_delivery


async def run_verification() -> dict:
    settings = Settings()
    client = ElexonClient(settings)

    print("Fetching raw FUELHH and WINDFOR datasets from live Elexon API...")
    # Fetch actuals: 2026-01-01 to 2026-01-31
    fuel_rows = await client.fetch_fuelhh(date(2026, 1, 1), date(2026, 1, 31))
    # Fetch forecasts: 7 days lookback (2025-12-25) to cutoff of last delivery day (2026-01-30 12:00 UTC)
    wind_rows = await client.fetch_windfor(
        datetime(2025, 12, 25, tzinfo=timezone.utc),
        datetime(2026, 1, 30, 12, tzinfo=timezone.utc),
    )

    print(f"Retrieved {len(fuel_rows)} raw FUELHH rows and {len(wind_rows)} raw WINDFOR rows.")

    # 1. Audit FUELHH
    wind_fuel_rows = [r for r in fuel_rows if r.get("fuelType") == "WIND"]
    non_wind = len(fuel_rows) - len(wind_fuel_rows)
    assert non_wind == 0, f"Found {non_wind} non-WIND records in FUELHH response"

    # Check duplicates and indexing
    fuel_by_start = {}
    fuel_duplicates = 0
    for r in wind_fuel_rows:
        st = datetime.fromisoformat(r["startTime"].replace("Z", "+00:00"))
        pub = datetime.fromisoformat(r["publishTime"].replace("Z", "+00:00"))
        gen = float(r["generation"])
        if st in fuel_by_start:
            # If revision, retain latest
            existing_pub, _ = fuel_by_start[st]
            if pub > existing_pub:
                fuel_by_start[st] = (pub, gen)
            fuel_duplicates += 1
        else:
            fuel_by_start[st] = (pub, gen)

    # 2. Audit WINDFOR
    # Group forecast versions by target startTime
    forecasts_by_target = defaultdict(list)
    for r in wind_rows:
        st = datetime.fromisoformat(r["startTime"].replace("Z", "+00:00"))
        pub = datetime.fromisoformat(r["publishTime"].replace("Z", "+00:00"))
        gen = float(r["generation"])
        forecasts_by_target[st].append((pub, gen))

    # 3. January 2026 Delivery Grid (744 hours)
    expected_hours = [
        datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
        for i in range(31 * 24)
    ]
    assert len(expected_hours) == 744

    london_zone = ZoneInfo("Europe/London")
    cutoff_time = time(12, 0)

    matched_hours = []
    complete_pairs = 0
    incomplete_pairs = 0
    eligible_forecast_count = 0

    daily_records = defaultdict(list)

    for h in expected_hours:
        # Check actual half-hourly pair
        half00 = fuel_by_start.get(h)
        half30 = fuel_by_start.get(h + timedelta(minutes=30))

        actual_avg = None
        if half00 is not None and half30 is not None:
            complete_pairs += 1
            actual_avg = (half00[1] + half30[1]) / 2.0
        elif half00 is not None or half30 is not None:
            incomplete_pairs += 1

        # Check cutoff forecast selection
        local_cutoff, utc_cutoff = decision_cutoff_for_delivery(h, cutoff_time, "Europe/London")
        versions = forecasts_by_target.get(h, [])
        eligible = [v for v in versions if v[0] <= utc_cutoff]

        selected_forecast = None
        if eligible:
            eligible_forecast_count += 1
            # Latest publication at or before cutoff
            best_version = max(eligible, key=lambda x: x[0])
            selected_forecast = best_version[1]

        if actual_avg is not None and selected_forecast is not None:
            err = selected_forecast - actual_avg
            matched_hours.append({
                "start": h,
                "actual": actual_avg,
                "forecast": selected_forecast,
                "error": err,
            })
            day_key = h.astimezone(london_zone).date()
            daily_records[day_key].append({
                "actual": actual_avg,
                "forecast": selected_forecast,
                "error": err,
            })

    # Metric calculations across all matched hours
    n = len(matched_hours)
    abs_errors = [abs(m["error"]) for m in matched_hours]
    sq_errors = [m["error"] ** 2 for m in matched_hours]
    signed_errors = [m["error"] for m in matched_hours]
    actual_sum = sum(m["actual"] for m in matched_hours)

    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(sq_errors) / n)
    wape = (sum(abs_errors) / actual_sum) * 100.0
    bias = sum(signed_errors) / n
    coverage = (n / complete_pairs) * 100.0

    # Jan 15 specific
    jan15_records = daily_records[date(2026, 1, 15)]
    n_15 = len(jan15_records)
    abs_15 = [abs(m["error"]) for m in jan15_records]
    sq_15 = [m["error"] ** 2 for m in jan15_records]
    signed_15 = [m["error"] for m in jan15_records]
    actual_15 = sum(m["actual"] for m in jan15_records)

    mae_15 = sum(abs_15) / n_15
    rmse_15 = math.sqrt(sum(sq_15) / n_15)
    wape_15 = (sum(abs_15) / actual_15) * 100.0
    bias_15 = sum(signed_15) / n_15

    results = {
        "raw_fuelhh_count": len(fuel_rows),
        "raw_windfor_count": len(wind_rows),
        "fuel_duplicates_or_revisions": fuel_duplicates,
        "unique_actual_half_hours": len(fuel_by_start),
        "expected_hourly_intervals": len(expected_hours),
        "complete_actual_pairs": complete_pairs,
        "incomplete_actual_pairs": incomplete_pairs,
        "eligible_forecast_count": eligible_forecast_count,
        "matched_interval_count": n,
        "coverage_percent": coverage,
        "monthly_mae": mae,
        "monthly_rmse": rmse,
        "monthly_wape": wape,
        "monthly_bias": bias,
        "jan15_matched_count": n_15,
        "jan15_mae": mae_15,
        "jan15_rmse": rmse_15,
        "jan15_wape": wape_15,
        "jan15_bias": bias_15,
    }

    print("\n--- INDEPENDENT HISTORICAL VALIDATION REPORT ---")
    for k, v in results.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    return results


if __name__ == "__main__":
    asyncio.run(run_verification())
