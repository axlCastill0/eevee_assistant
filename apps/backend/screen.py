"""Whether the panel's screen should be on.

Three things turn it off -- the top-bar button, a voice command, the idle
timer -- and one acts on it: scripts/screen-agent.sh, running on the host
because the display is a host device no container can reach. They need one
answer to "should the screen be on", and this is it.

The WebSocket command in events.py still fires alongside, because it blanks
the dashboard instantly while the agent polls. A command cannot be asked
"what is true now", which is why this state exists as well.

In memory: the screen is physically on at boot, so "on" is the only honest
starting point.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger("screen")

_on = True
_changed_at = time.time()
_source = "boot"


def state() -> dict:
    return {
        "on": _on,
        "changed_at": _changed_at,
        # Which of the three asked for it. Only used for logs and debugging,
        # but it is the first question when the screen blanks unexpectedly.
        "source": _source,
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
