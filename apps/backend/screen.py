"""Whether the panel's screen should be on.

WHY THE BACKEND OWNS THIS
    Three things turn the screen off -- the top-bar button, a voice command,
    and the dashboard's own idle timer -- and one thing acts on it: a helper
    running on the Pi itself, outside Docker, because the backlight is a host
    device no container can reach. They all need one answer to "should the
    screen be on right now", and this is it.

WHY NOT JUST THE WEBSOCKET COMMAND
    `events.publish_command("sleep_screen")` already existed and still fires:
    it is what makes the dashboard black out instantly instead of up to a
    second later. But a command is a thing that happened once -- a helper that
    starts up, or reconnects, or missed it, has no way to ask "what is true
    now". That is a state question, so it gets state. Same split as the
    retained event versus the command in events.py.

IN MEMORY, NOT PERSISTED
    The screen is physically on when the Pi boots, so "on" is the only honest
    starting point. Restoring "off" from disk would mean a reboot that leaves
    the panel dark with no sign anything is running.
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
