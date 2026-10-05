"""Service health registry.

Health is inferred from heartbeats, not from asking. A service that has died
cannot answer a probe and cannot report its own failure, so each service
checks in on a timer and the backend marks it down when the check-ins stop.
That is what lets the dashboard show "voice is down" — the voice pipeline
itself is in no position to say so.

The backend is the one exception: if this code is executing, it is up.

State is in-memory and intentionally not persisted — heartbeats are only
meaningful relative to now, and a restarted backend should start from "nobody
has checked in yet" rather than trusting stale timestamps from disk.

NOTE: single-process only. Running uvicorn with --workers > 1 would give each
worker its own copy of this dict and make health reporting inconsistent. If
workers are ever needed, this moves to Redis or a shared store.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("services")


# Services expected to check in. A service listed here but never seen is
# reported DOWN, not "unknown" — if it has not checked in, it is not running.
HEARTBEAT_SERVICES: set[str] = {"voice"}

# How long after the last heartbeat a service is considered down. Must be a
# comfortable multiple of the sender's interval (voice sends every 15 s) so a
# single dropped request or a slow STT pass does not flap the status.
# Keep in step with VOICE_HEARTBEAT_INTERVAL_S on the sending side.
try:
    STALE_AFTER_S = float(os.environ.get("SERVICE_STALE_AFTER_S", "45"))
except ValueError:
    log.warning("SERVICE_STALE_AFTER_S is not a number; using 45")
    STALE_AFTER_S = 45.0


@dataclass(frozen=True)
class ServiceHealth:
    name: str
    healthy: bool
    detail: str                      # human-readable, safe to show on a dashboard
    last_seen_s_ago: Optional[float]  # None if never seen


class _HeartbeatRegistry:
    """Thread-safe last-seen timestamps.

    Uvicorn serves requests from a thread pool, so the lock is not optional.
    Timestamps use monotonic time: staleness is a duration, and a wall-clock
    adjustment (NTP on a Pi that boots without an RTC) must not make a live
    service look stale.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_seen: dict[str, float] = {}

    def beat(self, name: str) -> None:
        with self._lock:
            first = name not in self._last_seen
            self._last_seen[name] = time.monotonic()
        if first:
            log.info("Service %r checked in for the first time", name)

    def seconds_since(self, name: str) -> Optional[float]:
        with self._lock:
            seen = self._last_seen.get(name)
        return None if seen is None else time.monotonic() - seen


_registry = _HeartbeatRegistry()


def record_heartbeat(name: str) -> None:
    """Record a check-in from `name`."""
    _registry.beat(name)


def health() -> list[ServiceHealth]:
    """Current health of every known service, backend first."""
    results = [
        ServiceHealth(
            name="backend",
            healthy=True,
            detail="running",
            last_seen_s_ago=0.0,
        )
    ]

    for name in sorted(HEARTBEAT_SERVICES):
        age = _registry.seconds_since(name)

        if age is None:
            results.append(ServiceHealth(name, False, "never checked in", None))
        elif age > STALE_AFTER_S:
            results.append(ServiceHealth(
                name, False, f"no heartbeat for {int(age)}s", age,
            ))
        else:
            results.append(ServiceHealth(name, True, "running", age))

    return results


def unhealthy() -> list[ServiceHealth]:
    return [s for s in health() if not s.healthy]


def summarize() -> tuple[str, bool]:
    """Spoken summary of overall health. Returns (speech, all_healthy).

    Phrasing is deliberately short — this is read aloud, so it names what is
    broken and stops.
    """
    down = unhealthy()

    if not down:
        return "Everything good.", True

    names = [s.name for s in down]
    if len(names) == 1:
        return f"{names[0]} is down.", False
    if len(names) == 2:
        return f"{names[0]} and {names[1]} are down.", False
    return f"{', '.join(names[:-1])}, and {names[-1]} are down.", False
