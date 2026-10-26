"""Thin HTTP handlers; all retrieval and calculation lives in services."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.app.schemas import (
    DashboardResponse,
    HealthResponse,
    IntervalsResponse,
    MetricsResponse,
)


router = APIRouter(prefix="/api")

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
CUTOFF_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
DELIVERY_DATE_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
MIN_API_YEAR = 2000
MAX_API_YEAR = 2100


def parse_month_parameter(
    month: Annotated[
        str,
        Query(
            pattern=MONTH_PATTERN,
            description="Delivery month in strict YYYY-MM form.",
            examples=["2026-01"],
        ),
    ],
) -> date:
    try:
        parsed = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_month", "message": "month must be a valid YYYY-MM"},
        ) from exc
    if not MIN_API_YEAR <= parsed.year <= MAX_API_YEAR:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_month",
                "message": f"month year must be between {MIN_API_YEAR} and {MAX_API_YEAR}",
            },
        )
    return parsed


def parse_delivery_date_parameter(
    delivery_date: Annotated[
        str,
        Query(
            pattern=DELIVERY_DATE_PATTERN,
            description="Europe/London delivery date in strict YYYY-MM-DD form.",
            examples=["2026-01-15"],
        ),
    ],
) -> date:
    try:
        parsed = date.fromisoformat(delivery_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_delivery_date",
                "message": "delivery_date must be a valid YYYY-MM-DD",
            },
        ) from exc
    if not MIN_API_YEAR <= parsed.year <= MAX_API_YEAR:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_delivery_date",
                "message": (
                    f"delivery_date year must be between {MIN_API_YEAR} and {MAX_API_YEAR}"
                ),
            },
        )
    return parsed


def parse_cutoff_parameter(
    decision_cutoff_time: Annotated[
        str,
        Query(
            pattern=CUTOFF_PATTERN,
            description=(
                "Adjustable demo assumption: Europe/London time on the preceding "
                "calendar day."
            ),
            examples=["12:00"],
        ),
    ] = "12:00",
) -> time:
    hour, minute = (int(part) for part in decision_cutoff_time.split(":"))
    return time(hour=hour, minute=minute)


def get_analysis_service(request: Request):
    service = getattr(request.app.state, "analysis_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "service_unavailable", "message": "Analysis service is not ready."},
        )
    return service


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Local liveness only; deliberately does not call Elexon."""

    return HealthResponse(timestamp_utc=datetime.now(timezone.utc))


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    month_start: Annotated[date, Depends(parse_month_parameter)],
    cutoff: Annotated[time, Depends(parse_cutoff_parameter)],
    service=Depends(get_analysis_service),
) -> DashboardResponse:
    return await service.dashboard(month_start, cutoff)


@router.get("/intervals", response_model=IntervalsResponse)
async def intervals(
    delivery_date: Annotated[date, Depends(parse_delivery_date_parameter)],
    cutoff: Annotated[time, Depends(parse_cutoff_parameter)],
    service=Depends(get_analysis_service),
) -> IntervalsResponse:
    return await service.intervals(delivery_date, cutoff)


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(
    month_start: Annotated[date, Depends(parse_month_parameter)],
    cutoff: Annotated[time, Depends(parse_cutoff_parameter)],
    service=Depends(get_analysis_service),
) -> MetricsResponse:
    return await service.metrics(month_start, cutoff)
