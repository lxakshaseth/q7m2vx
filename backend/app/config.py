"""Environment-backed settings for the FastAPI backend.

Only operational tuning is configurable. The client never reads API keys or
other credentials because the verified Elexon endpoints are public.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit


def _float_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _base_url_env() -> str:
    value = os.getenv(
        "ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1"
    ).rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("ELEXON_BASE_URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("ELEXON_BASE_URL must not contain credentials")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated application settings with conservative operational bounds."""

    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    elexon_timeout_seconds: float = 30.0
    elexon_max_attempts: int = 3
    elexon_backoff_seconds: float = 0.5
    elexon_max_retry_delay_seconds: float = 8.0
    source_cache_ttl_seconds: float = 900.0
    source_cache_max_entries: int = 16
    analysis_cache_ttl_seconds: float = 900.0
    analysis_cache_max_entries: int = 8
    forecast_lookback_days: int = 7
    decision_timezone: str = "Europe/London"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard Python logging level")
        return cls(
            elexon_base_url=_base_url_env(),
            elexon_timeout_seconds=_float_env(
                "ELEXON_TIMEOUT_SECONDS", 30.0, minimum=1.0, maximum=120.0
            ),
            elexon_max_attempts=_int_env(
                "ELEXON_MAX_ATTEMPTS", 3, minimum=1, maximum=3
            ),
            elexon_backoff_seconds=_float_env(
                "ELEXON_BACKOFF_SECONDS", 0.5, minimum=0.0, maximum=10.0
            ),
            elexon_max_retry_delay_seconds=_float_env(
                "ELEXON_MAX_RETRY_DELAY_SECONDS",
                8.0,
                minimum=0.0,
                maximum=30.0,
            ),
            source_cache_ttl_seconds=_float_env(
                "SOURCE_CACHE_TTL_SECONDS", 900.0, minimum=0.0, maximum=86_400.0
            ),
            source_cache_max_entries=_int_env(
                "SOURCE_CACHE_MAX_ENTRIES", 16, minimum=1, maximum=128
            ),
            analysis_cache_ttl_seconds=_float_env(
                "ANALYSIS_CACHE_TTL_SECONDS", 900.0, minimum=0.0, maximum=86_400.0
            ),
            analysis_cache_max_entries=_int_env(
                "ANALYSIS_CACHE_MAX_ENTRIES", 8, minimum=1, maximum=64
            ),
            forecast_lookback_days=_int_env(
                "FORECAST_LOOKBACK_DAYS", 7, minimum=1, maximum=31
            ),
            decision_timezone=os.getenv("DECISION_TIMEZONE", "Europe/London"),
            log_level=log_level,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
