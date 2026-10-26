"""Stable, sanitized exception types shared by backend modules."""

from __future__ import annotations


class BackendError(Exception):
    """Base class whose string representation is safe for logs and API output."""

    code = "backend_error"

    def __init__(self, message: str) -> None:
        self.safe_message = message
        super().__init__(message)


class ElexonError(BackendError):
    code = "elexon_error"


class ElexonTimeoutError(ElexonError):
    code = "elexon_timeout"

    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        super().__init__(f"Elexon {dataset} request timed out")


class ElexonUnavailableError(ElexonError):
    code = "elexon_unavailable"

    def __init__(self, dataset: str, status_code: int | None = None) -> None:
        self.dataset = dataset
        self.status_code = status_code
        status = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"Elexon {dataset} is temporarily unavailable{status}")


class ElexonHTTPError(ElexonError):
    code = "elexon_http_error"

    def __init__(self, dataset: str, status_code: int) -> None:
        self.dataset = dataset
        self.status_code = status_code
        super().__init__(f"Elexon {dataset} request failed with HTTP {status_code}")


class ElexonResponseError(ElexonError):
    code = "invalid_elexon_response"

    def __init__(self, dataset: str, reason: str) -> None:
        self.dataset = dataset
        super().__init__(f"Elexon {dataset} returned an invalid response: {reason}")


class DataNormalizationError(BackendError):
    code = "data_normalization_error"


class AmbiguousDataError(DataNormalizationError):
    code = "ambiguous_source_data"


class AnalysisConfigurationError(BackendError):
    code = "invalid_analysis_configuration"
