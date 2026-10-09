"""Activity reporting — tells the dashboard what the pipeline is doing.

WHY A THREAD
    The pill exists so the user knows when to start talking, which means the
    `listening` event has to be published *before* recording begins. Doing
    that with a synchronous POST would put an HTTP round trip — and, with a
    backend that is down, a full connect timeout — between the wake word and
    the microphone. That is the one place in this pipeline where added latency
    is actually harmful, so publishing happens on a daemon thread and the main
    loop never waits for it.

WHY A QUEUE WITH A SMALL BOUND
    Transitions arrive in bursts of four per utterance. If the backend is
    slow, posts must not accumulate: an unbounded queue would publish a
    growing backlog of states that are no longer true. The queue holds a few
    events and drops the OLDEST when full, because the newest event is the
    current state and that is the only one that has to be right.

FAILURE POSTURE
    Same as everything else in this package: degrade and keep listening. A
    dropped state event makes the dashboard's pill stale. It never affects
    whether the assistant hears or answers. Nothing here raises upward.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from . import config
from .api_client import BackendClient

log = logging.getLogger("activity")

# Four transitions per utterance, so this holds a couple of utterances' worth.
# Anything older than that is history the dashboard does not need.
QUEUE_MAX = 8

# Sentinel for "stop", distinguishable from a real event.
_STOP = object()


class StateReporter:
    """Fire-and-forget publisher for voice pipeline state changes."""

    def __init__(self, api: BackendClient,
                 enabled: bool = config.STATE_EVENTS_ENABLED,
                 repeat_s: float = config.STATE_REPEAT_S):
        self.api = api
        self.enabled = enabled
        self.repeat_s = repeat_s if repeat_s > 0 else None
        self._queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAX)
        self._thread: Optional[threading.Thread] = None
        # Last event published, re-sent on a timer. See _loop.
        self._latest: Optional[tuple] = None
        # Transitions are logged at debug; only the backend going quiet or
        # coming back is worth an info line, and only on change.
        self._last_ok: Optional[bool] = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if not self.enabled:
            log.info("State events disabled; the dashboard pill will not update")
            return

        self._thread = threading.Thread(
            target=self._loop, name="activity", daemon=True,
        )
        self._thread.start()
        log.info("State reporter started")

    def stop(self, final_state: Optional[str] = "offline") -> None:
        """Publish one last state, then shut the thread down.

        `offline` is sent synchronously on the way out: the thread is about to
        stop, so queueing it would mean it never gets sent, and a pill left on
        `ready` after a clean shutdown would be a lie. A failure here is
        ignored — if the backend is also gone, heartbeat staleness covers it
        within 45s anyway.
        """
        if not self.enabled:
            return

        if final_state is not None:
            try:
                self.api.post_state(final_state)
            except Exception:
                log.debug("Final state %r not delivered", final_state)

        # Clear the backlog first. Queued events are stale by now, and the
        # sentinel must not be dropped by a full queue or the thread would
        # block on get() until the process exits.
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put_nowait(_STOP)

        if self._thread is not None:
            # Short join. The thread is a daemon and each post has a 1s
            # timeout, so shutdown must not wait on the network.
            self._thread.join(timeout=2.0)

    # -- publishing --------------------------------------------------------

    def set(self, state: str, transcript: Optional[str] = None,
            speech: Optional[str] = None) -> None:
        """Queue a state change. Returns immediately; never raises."""
        if not self.enabled:
            return

        event = (state, transcript, speech)

        if self._queue.full():
            # Drop the oldest, not this one: the newest event is the truth.
            try:
                self._queue.get_nowait()
            except queue.Empty:            # pragma: no cover - raced
                pass
            log.debug("State queue full; dropped an older event")

        try:
            self._queue.put_nowait(event)
        except queue.Full:                 # pragma: no cover - raced
            pass

    # -- thread ------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=self.repeat_s)
            except queue.Empty:
                # REPUBLISH. The hub's state is in-memory, so a backend restart
                # loses it and the dashboard would sit on "unknown" until the
                # next utterance — which on a quiet evening could be hours.
                # Re-sending the current state on the heartbeat's cadence makes
                # the pill self-heal, and costs one loopback POST per interval.
                if self._latest is None:
                    continue
                item = self._latest

            if item is _STOP:
                return

            self._latest = item
            state, transcript, speech = item
            try:
                ok = self.api.post_state(state, transcript=transcript, speech=speech)
            except Exception:
                # Must never kill the thread; a dead reporter would freeze the
                # pill on whatever colour it happened to be showing.
                log.exception("State event raised unexpectedly")
                ok = False

            # A republish that lands is not news; only a change in whether the
            # backend accepts them at all is worth a line, and this fires
            # forever.
            if ok != self._last_ok:
                if ok:
                    log.info("State events accepted by backend")
                else:
                    log.warning("State events failing; dashboard pill will be stale")
                self._last_ok = ok
