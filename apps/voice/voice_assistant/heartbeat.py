"""Periodic heartbeat to the backend.

The backend infers this pipeline's health from these check-ins stopping. A
crashed or hung pipeline cannot report its own failure, so silence is the
signal — which is what lets the dashboard show "voice is down".

Runs on a daemon thread so it keeps beating while the main loop is blocked in
Whisper or the SLM, and so it never holds process exit open.
"""
from __future__ import annotations

import logging
import threading

from . import config
from .api_client import BackendClient

log = logging.getLogger("heartbeat")


class Heartbeat:
    """Beats on a timer until stopped."""

    def __init__(self, api: BackendClient,
                 interval_s: float = config.HEARTBEAT_INTERVAL_S):
        self.api = api
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Only log transitions, not every beat — this fires forever.
        self._last_ok: bool | None = None

    def start(self) -> None:
        if self.interval_s <= 0:
            log.info("Heartbeat disabled (interval=%s)", self.interval_s)
            return

        self._thread = threading.Thread(
            target=self._loop, name="heartbeat", daemon=True,
        )
        self._thread.start()
        log.info("Heartbeat started (every %.0fs)", self.interval_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            # Short join: the thread is a daemon and wakes on the event, so a
            # slow in-flight request must not delay shutdown.
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        # Beat immediately so the backend sees us without waiting a full
        # interval, then settle into the timer.
        while True:
            self._beat_once()
            if self._stop.wait(self.interval_s):
                return

    def _beat_once(self) -> None:
        try:
            ok = self.api.heartbeat()
        except Exception:
            # Must never kill the thread: losing the heartbeat permanently
            # would make a healthy pipeline look dead forever.
            log.exception("Heartbeat raised unexpectedly")
            ok = False

        if ok != self._last_ok:
            if ok:
                log.info("Heartbeat accepted by backend")
            else:
                log.warning("Heartbeat failing; backend will mark voice down")
            self._last_ok = ok
