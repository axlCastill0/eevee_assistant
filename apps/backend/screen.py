"""Whether the panel's screen should be on.

Three things turn it off -- the top-bar button, a voice command, the idle
timer -- and one acts on it: scripts/screen-agent.sh, running on the host
because the display is a host device no container can reach. They need one
answer to "should the screen be on", and this is it.

The WebSocket command in events.py still fires alongside, because it blanks
the dashboard instantly while the agent polls. A command cannot be asked
"what is true now", which is why this state exists as well.

THE LOCK (USER 2026-10-24) is a separate question: "may the idle timer blank
this?" It holds the screen awake against the TIMEOUT ONLY. The button, the
voice command and the agent all still work -- a lock that could not be
overridden by someone asking for the screen off would be a panel you cannot
turn off.

In memory, both of them: the screen is physically on at boot, so "on" is the
only honest starting point, and nothing is holding it there yet.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger("screen")

_on = True
_changed_at = time.time()
_source = "boot"
_locked = False


def state() -> dict:
    return {
        "on": _on,
        "changed_at": _changed_at,
        # Which of the three asked for it. Only used for logs and debugging,
        # but it is the first question when the screen blanks unexpectedly.
        "source": _source,
        # Held awake against the idle timer. The dashboard is what enforces
        # it -- the timeout is counted there, off touch events this process
        # never sees -- so this is the shared answer both ends read.
        "locked": _locked,
    }


def set_on(on: bool, source: str = "api") -> dict:
    """Turn the screen on or off. Idempotent."""
    global _on, _changed_at, _source

    on = bool(on)
    if on == _on:
        # Not a no-op worth hiding: the source changes, and "woken by touch
        # while already on" is a thing that happens constantly as the veil is
        # dismissed. Keep the timestamp still so the helper does not act.
        _source = source
        return state()

    _on = on
    _changed_at = time.time()
    _source = source
    log.info("Screen %s (%s)", "on" if on else "off", source)
    return state()


def is_on() -> bool:
    return _on


def set_locked(locked: bool, source: str = "api") -> dict:
    """Hold the screen awake, or stop holding it. Idempotent."""
    global _locked

    locked = bool(locked)
    if locked != _locked:
        _locked = locked
        log.info("Screen lock %s (%s)", "on" if locked else "off", source)
    return state()


def is_locked() -> bool:
    return _locked
