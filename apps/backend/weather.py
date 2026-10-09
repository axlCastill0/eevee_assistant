"""Weather, from Open-Meteo.

WHY OPEN-METEO
    No account, no API key, no signup, free for non-commercial use. That
    matters here because every other part of this system works with nothing
    but the Pi — adding a service that needs a secret in .env to answer "is it
    cold out" would be the heaviest dependency in the project.

    The call is one unauthenticated GET. Swapping provider later means
    rewriting `_fetch` and the code table; nothing else knows where this came
    from.

WHY urllib AND NOT httpx
    The backend's entire dependency list is FastAPI, uvicorn and dotenv. One
    GET per ten minutes does not justify adding a third-party HTTP client to
    an image that is deliberately small.

FAILURE POSTURE
    The Pi may be offline, and this runs on a voice command, so a hang is
    worse than a failure. Short timeout, no retries, and every error path
    returns None — the handler then says it cannot reach the service rather
    than inventing a forecast.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("weather")

_ENDPOINT = "https://api.open-meteo.com/v1/forecast"

# Timeout is short on purpose: this is on the path between a spoken question
# and a spoken answer. Waiting ten seconds in silence reads as a crash.
_TIMEOUT_S = 4.0

# Weather does not change in the time it takes to ask twice, and a voice
# assistant invites repeat questions. This also means a flaky connection does
# not produce a flaky assistant.
_CACHE_TTL_S = 600.0

_cache: Optional[tuple[float, "Weather"]] = None


def _ssl_context() -> ssl.SSLContext:
    """TLS context with a CA bundle that is actually present.

    `urllib` uses the system trust store, which is not guaranteed: a slim
    Python image may ship without ca-certificates, and a macOS dev host fails
    the same way unless Python's "Install Certificates" step was run. Both
    produce CERTIFICATE_VERIFY_FAILED, which reads like a weather-service
    outage rather than a missing package. certifi comes along with several
    common dependencies, so prefer it and fall back to the system store.

    Verification is never disabled. A weather lookup is not worth teaching
    this codebase that unverified TLS is acceptable.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        log.warning("%s is not a number; using %s", name, default)
        return default


@dataclass
class Weather:
    temp_c: float
    feels_like_c: float
    description: str        # already spoken-friendly, e.g. "light rain"
    is_day: bool
    place: str


# WMO weather interpretation codes, worded for speech rather than for a table.
# Open-Meteo documents the full set; these are grouped where the distinction
# would not survive being read aloud.
_CODES: dict[int, str] = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy", 48: "foggy",
    51: "drizzling", 53: "drizzling", 55: "drizzling",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "raining", 65: "pouring",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snowing", 75: "heavy snow",
    77: "snow grains",
    80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def _fetch() -> Optional[Weather]:
    lat = _env_float("WEATHER_LAT", 0.0)
    lon = _env_float("WEATHER_LON", 0.0)
    place = os.environ.get("WEATHER_PLACE", "").strip()

    query = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,weather_code,is_day",
        "temperature_unit": os.environ.get("WEATHER_UNITS", "celsius"),
        "timezone": "auto",
    })

    try:
        with urllib.request.urlopen(f"{_ENDPOINT}?{query}", timeout=_TIMEOUT_S,
                                    context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        # Includes DNS failure, no route, TLS problems and malformed JSON. All
        # of them mean the same thing to the person asking. If this is
        # CERTIFICATE_VERIFY_FAILED, the image is missing ca-certificates —
        # see the backend Dockerfile.
        log.warning("Weather lookup failed: %s", exc)
        return None

    try:
        current = payload["current"]
        return Weather(
            temp_c=round(float(current["temperature_2m"])),
            feels_like_c=round(float(current["apparent_temperature"])),
            description=_CODES.get(int(current["weather_code"]), "unsettled"),
            is_day=bool(current.get("is_day", 1)),
            place=place,
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("Unexpected weather payload (%s): %.200s", exc, payload)
        return None


def current() -> Optional[Weather]:
    """Current conditions, cached. None when they cannot be fetched."""
    global _cache

    now = time.monotonic()
    if _cache is not None:
        fetched_at, cached = _cache
        if now - fetched_at < _CACHE_TTL_S:
            return cached

    fresh = _fetch()
    if fresh is not None:
        _cache = (now, fresh)
        return fresh

    # A failed refresh falls back to whatever is cached, however old. Slightly
    # stale weather is a better answer than no weather, and the alternative is
    # the assistant going mute every time the wifi hiccups.
    if _cache is not None:
        log.info("Weather refresh failed; using the cached reading")
        return _cache[1]

    return None


def is_configured() -> bool:
    """False when no location has been set, so the handler can say so."""
    return bool(os.environ.get("WEATHER_LAT") and os.environ.get("WEATHER_LON"))
