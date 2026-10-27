"""FastAPI application factory and sanitized exception mapping."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config import Settings, get_settings
from backend.app.domain import (
    DataValidationError,
    DecisionCutoffError,
    DuplicateConflictError,
)
from backend.app.errors import (
    AnalysisConfigurationError,
    BackendError,
    ElexonHTTPError,
    ElexonResponseError,
    ElexonTimeoutError,
    ElexonUnavailableError,
)
from backend.app.services.analysis import AnalysisService
from backend.app.services.elexon_client import ElexonClient


LOGGER = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message}},
    )


def _frontend_dist_directory() -> Path | None:
    """Return an explicitly configured production frontend directory, if present."""

    configured_path = os.getenv("FRONTEND_DIST_DIR")
    if not configured_path:
        return None

    frontend_dist = Path(configured_path).resolve()
    if not (frontend_dist / "index.html").is_file():
        LOGGER.warning("Configured frontend distribution is missing index.html")
        return None

    return frontend_dist


def _configure_frontend_serving(application: FastAPI) -> None:
    """Serve the Vite build in the production image without changing API routes."""

    frontend_dist = _frontend_dist_directory()
    if frontend_dist is None:
        return

    assets_directory = frontend_dist / "assets"
    if assets_directory.is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=assets_directory),
            name="frontend-assets",
        )

    # The SPA fallback must never turn a misspelled API URL into a successful
    # HTML response. Registered API routes are matched first, while this keeps
    # unknown GET API paths machine-readable in the production image.
    @application.get("/api/{requested_path:path}", include_in_schema=False)
    async def unknown_api_route(requested_path: str) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "api_route_not_found",
            f"No API route exists at /api/{requested_path}",
        )

    @application.get("/{requested_path:path}", include_in_schema=False)
    async def serve_frontend(requested_path: str) -> FileResponse:
        requested_file = (frontend_dist / requested_path).resolve()
        if (
            requested_path
            and requested_file.is_relative_to(frontend_dist)
            and requested_file.is_file()
        ):
            return FileResponse(requested_file)

        return FileResponse(frontend_dist / "index.html")


def create_app(
    *,
    settings: Settings | None = None,
    client: ElexonClient | None = None,
    analysis_service: Any | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    logging.basicConfig(
        level=getattr(logging, resolved_settings.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    owned_client: ElexonClient | None = None
    if analysis_service is not None:
        service_instance = analysis_service
    else:
        source_client = client
        if source_client is None:
            source_client = ElexonClient(resolved_settings)
            owned_client = source_client
        service_instance = AnalysisService(source_client, resolved_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.analysis_service = service_instance
        try:
            yield
        finally:
            if owned_client is not None:
                await owned_client.aclose()

    application = FastAPI(
        title="Wind Forecast Insight API",
        version="0.1.0",
        description=(
            "Compare Elexon FUELHH wind outturn with cutoff-eligible WINDFOR "
            "publications. The default 12:00 Europe/London day-before cutoff is "
            "an adjustable demo assumption."
        ),
        lifespan=lifespan,
    )
    application.state.analysis_service = service_instance
    application.include_router(router)
    _configure_frontend_serving(application)

    @application.exception_handler(ElexonTimeoutError)
    async def handle_timeout(
        _request: Request, exc: ElexonTimeoutError
    ) -> JSONResponse:
        LOGGER.warning("Upstream timeout", extra={"dataset": exc.dataset})
        return _error_response(
            status.HTTP_504_GATEWAY_TIMEOUT, exc.code, exc.safe_message
        )

    @application.exception_handler(ElexonUnavailableError)
    async def handle_unavailable(
        _request: Request, exc: ElexonUnavailableError
    ) -> JSONResponse:
        LOGGER.warning(
            "Upstream unavailable",
            extra={"dataset": exc.dataset, "status_code": exc.status_code},
        )
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, exc.code, exc.safe_message
        )

    @application.exception_handler(ElexonHTTPError)
    async def handle_upstream_http(
        _request: Request, exc: ElexonHTTPError
    ) -> JSONResponse:
        LOGGER.warning(
            "Upstream rejected request",
            extra={"dataset": exc.dataset, "status_code": exc.status_code},
        )
        return _error_response(status.HTTP_502_BAD_GATEWAY, exc.code, exc.safe_message)

    @application.exception_handler(ElexonResponseError)
    async def handle_upstream_response(
        _request: Request, exc: ElexonResponseError
    ) -> JSONResponse:
        LOGGER.warning("Invalid upstream response", extra={"dataset": exc.dataset})
        return _error_response(status.HTTP_502_BAD_GATEWAY, exc.code, exc.safe_message)

    @application.exception_handler(DuplicateConflictError)
    @application.exception_handler(DataValidationError)
    async def handle_invalid_source(
        _request: Request, exc: DataValidationError | DuplicateConflictError
    ) -> JSONResponse:
        LOGGER.warning("Source data failed normalization")
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "invalid_elexon_data",
            str(exc),
        )

    @application.exception_handler(DecisionCutoffError)
    @application.exception_handler(AnalysisConfigurationError)
    async def handle_bad_analysis_configuration(
        _request: Request, exc: BackendError | DecisionCutoffError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_analysis_configuration",
            str(exc),
        )

    return application


app = create_app()
