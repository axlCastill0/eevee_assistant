"""Voice activity fan-out — the push channel behind the dashboard's voice pill.

WHY THIS EXISTS, AND WHY IT IS NOT THE HEARTBEAT
    `services.py` answers "is voice alive?" and is polled every 3s. That is
    fine for health, and useless here: the whole point of the pill is that it
    turns green the instant the wake word fires, so the user knows to start
    talking. A 3s poll would show "listening" an average of 1.5s late — by
    which time they have already spoken into a pipeline that was not yet
    recording. Activity has to be pushed.

WHY WEBSOCKET AND NOT MQTT
    See `## decisions` in AGENT_CONTEXT.md. Short version: the publisher and
    the subscriber already both speak HTTP to this process, so a WebSocket on
    the same port, through the same nginx that already injects the API key,
    adds one endpoint. MQTT would add a broker to supervise, a second
    transport, and paho in two more images — for the same latency.

STATE, AND WHY IT IS RETAINED
    The hub keeps the last event so a browser connecting (or reconnecting
    after a kiosk reload) paints the correct pill immediately instead of
    showing a wrong colour until the next utterance, which may be hours away.
    This is the MQTT retained-message idea, which is the one part of MQTT this
    actually needed, and it is four lines.

STATE IS IN-MEMORY AND NOT PERSISTED, for the same reason heartbeats are not:
    an event is only meaningful relative to now. A restarted backend genuinely
    does not know what the pipeline is doing, and `unknown` is the honest
    answer until the pipeline says otherwise.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

log = logging.getLogger("events")

# The pill's colours map onto these, and the UI falls back to `unknown` for
# anything it does not recognise, so adding a state here does not break a
# dashboard that has not been rebuilt.
STATES = ("ready", "listening", "thinking", "speaking", "offline")

# Per-subscriber buffer. A kiosk browser that has been suspended or is wedged
# must not make the publisher grow memory without bound, so the queue is
# small and the OLDEST event is dropped when it fills. Dropping the oldest
# rather than the newest matters: the newest event is the current state, and a
# client that misses intermediate transitions still ends up correct.
QUEUE_MAX = 16


class VoiceEventHub:
    """Fan-out of voice activity events to connected dashboards.

    Single-process only, exactly like `services.py` — with uvicorn
    --workers > 1 each worker would hold its own subscriber set and only the
    worker that happened to receive the publish would forward it. Moving to
    workers means moving this to Redis pub/sub.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._last: Optional[dict] = None
        self._seq = 0

    # -- publishing --------------------------------------------------------

    def publish(self, state: str, transcript: Optional[str] = None,
                speech: Optional[str] = None) -> dict:
        """Record a state change and hand it to every live subscriber.

        Never raises and never blocks: a slow or dead dashboard must not be
        able to stall the voice pipeline's HTTP call, because that call sits on
        the critical path between the wake word firing and the user being
        told they can speak.
        """
        if state not in STATES:
            # Same posture as an unknown intent name: downgrade rather than
            # reject. The pipeline is not trusted to be in lockstep with this
            # file, and a 422 here would turn a cosmetic mismatch into a
            # logged error on every single utterance.
            log.warning("Unknown voice state %r; recording as 'unknown'", state)
            state = "unknown"

        # A republish of the unchanged state is a refresh, not an event. The
        # pipeline re-sends on a timer so the pill survives a backend restart;
        # bumping seq for those would make the dashboard treat a months-old
        # answer as newly spoken every interval. Only the timestamp moves.
        if self._last is not None and (
            self._last["state"] == state
            and self._last["transcript"] == transcript
            and self._last["speech"] == speech
        ):
            self._last["at"] = time.time()
            return self._last

        self._seq += 1
        event = {
            "seq": self._seq,
            "state": state,
            "transcript": transcript,
            "speech": speech,
            # Wall clock, for display only. Staleness decisions use monotonic
            # time elsewhere; nothing here compares timestamps.
            "at": time.time(),
        }
        self._last = event

        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:      # pragma: no cover - raced
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:           # pragma: no cover - raced
                pass

        return event

    def publish_command(self, command: str, value: Optional[str] = None) -> dict:
        """Send the dashboard an instruction (theme, screen) rather than a state.

        Deliberately NOT retained and NOT part of the state sequence. A command
        is a thing that happened once; replaying it to a browser that
        reconnects an hour later would re-dim the screen or re-flip the theme
        for no reason. Retained state answers "what is true", commands answer
        "do this now", and conflating them is how a kiosk ends up fighting
        the user.
        """
        event = {"type": "command", "command": command, "value": value,
                 "at": time.time()}

        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:      # pragma: no cover - raced
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:           # pragma: no cover - raced
                pass

        log.info("command -> %s=%r (%d dashboards)", command, value,
                 len(self._subscribers))
        return event

    # -- subscribing -------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[dict]:
        """Register a subscriber, pre-loaded with the retained event if any."""
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=QUEUE_MAX)
        if self._last is not None:
            queue.put_nowait(self._last)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        self._subscribers.discard(queue)

    # -- introspection -----------------------------------------------------

    @property
    def last(self) -> Optional[dict]:
        return self._last

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


hub = VoiceEventHub()
