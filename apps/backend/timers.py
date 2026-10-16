"""Countdown timers.

Several can run at once. Each one is identified by a short id and labelled by
its own duration ("10 minutes"), which is what makes a spoken "cancel the
timer" resolvable when more than one is running.

WHY MONOTONIC DEADLINES
    `time.monotonic()`, like services.py and for the same reason: the Pi has no
    RTC, so its wall clock steps when NTP catches up after boot. A timer set 30
    seconds before that step would otherwise fire minutes early or late. Wall
    time appears only in `ends_at`, which is a display string recomputed from
    the monotonic remainder.

WHY NOT PERSISTED
    A timer is meaningful only relative to now, exactly like a heartbeat. The
    backend restarting means it genuinely does not know what was counting, and
    silently resurrecting a timer that should have fired two minutes ago is
    worse than losing it. Alarms, which are a schedule rather than a countdown,
    ARE persisted -- see alarms.py.

RINGING
    A timer that reaches zero becomes `fired` and stays that way until it is
    stopped: by the Stop button, or by the dashboard reporting that the song
    ended. Nothing expires it on a timer of its own, because an alarm nobody
    acknowledged is not an alarm that has been dealt with.
"""
from __future__ import annotations

import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger("timers")

# A spoken "set a timer for eight hours" is almost certainly a misheard
# transcript, and a 30-second cap on the other end stops "one second" timers
# that fire before the assistant finishes saying it set one.
MIN_DURATION_S = 5
MAX_DURATION_S = 12 * 3600


@dataclass
class Timer:
    id: str
    label: str
    duration_s: int
    # Monotonic deadline. Compare only against time.monotonic().
    deadline: float
    created_at: float = field(default_factory=time.time)
    fired_at: Optional[float] = None

    @property
    def remaining_s(self) -> float:
        if self.fired_at is not None:
            return 0.0
        return max(0.0, self.deadline - time.monotonic())

    @property
    def ringing(self) -> bool:
        return self.fired_at is not None


_timers: dict[str, Timer] = {}


# ---------------------------------------------------------------------------
# duration parsing
# ---------------------------------------------------------------------------

# Whisper writes numbers as digits often but not always, and "a minute" and
# "half an hour" are both things people say to a kitchen timer.
_WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty-five": 45, "fortyfive": 45, "fifty": 50, "sixty": 60, "ninety": 90,
}

_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}

_PART = re.compile(
    r"(?P<count>\d+|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")"
    r"\s*(?:and\s+)?(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)",
    re.IGNORECASE,
)


def parse_duration(phrase: str) -> Optional[int]:
    """"10 minutes", "1 hour 30 minutes", "half an hour" -> seconds.

    None when nothing duration-shaped is in there, which the handler reports
    as "I didn't catch how long" rather than guessing at a default.
    """
    if not phrase:
        return None

    text = phrase.lower().strip()

    # Handled ahead of the general parser: "half" is not a count, and
    # "an hour and a half" needs the fraction applied to the unit before it.
    if re.fullmatch(r"(an?\s+)?half\s+(an?\s+)?hour", text):
        return 1800
    if re.fullmatch(r"(an?\s+)?half\s+(an?\s+)?(a\s+)?minute", text):
        return 30
    if re.fullmatch(r"(an?\s+)?hour\s+and\s+a\s+half", text):
        return 5400

    total = 0
    for match in _PART.finditer(text):
        raw = match.group("count").lower()
        count = int(raw) if raw.isdigit() else _WORD_NUMBERS.get(raw, 0)
        total += count * _UNITS[match.group("unit").lower()]

    # A bare number with no unit means minutes: "set a timer for ten" is a
    # ten-minute timer in every kitchen in the world.
    if total == 0:
        bare = re.fullmatch(r"(?:for\s+)?(\d+|" +
                            "|".join(_WORD_NUMBERS) + r")", text)
        if bare:
            raw = bare.group(1)
            minutes = int(raw) if raw.isdigit() else _WORD_NUMBERS[raw]
            total = minutes * 60

    return total or None


def describe(seconds: int) -> str:
    """Seconds -> a label a person would say. Used as the timer's name."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)

    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    if secs:
        parts.append(f"{secs} second" + ("s" if secs != 1 else ""))
    return " ".join(parts) or "0 seconds"


# ---------------------------------------------------------------------------
# operations
# ---------------------------------------------------------------------------

def add(duration_s: int, label: Optional[str] = None) -> Timer:
    """Start a timer. Duration is clamped to the sane band."""
    duration_s = max(MIN_DURATION_S, min(MAX_DURATION_S, int(duration_s)))

    timer = Timer(
        id=secrets.token_hex(3),
        label=label or describe(duration_s),
        duration_s=duration_s,
        deadline=time.monotonic() + duration_s,
    )
    _timers[timer.id] = timer
    log.info("Timer %s started: %s", timer.id, timer.label)
    return timer


def cancel(timer_id: str) -> bool:
    """Remove a timer, running or ringing. True if there was one."""
    removed = _timers.pop(timer_id, None)
    if removed:
        log.info("Timer %s cancelled (%s)", timer_id, removed.label)
    return removed is not None


def cancel_all() -> int:
    """Remove every timer. Returns how many there were."""
    count = len(_timers)
    _timers.clear()
    return count


def stop_ringing(timer_id: str) -> bool:
    """Acknowledge a fired timer. Same as cancel, named for what it means."""
    return cancel(timer_id)


def _sweep() -> None:
    """Mark anything past its deadline as fired. Called before every read."""
    now = time.monotonic()
    for timer in _timers.values():
        if timer.fired_at is None and timer.deadline <= now:
            timer.fired_at = time.time()
            log.info("Timer %s fired (%s)", timer.id, timer.label)


def active() -> list[Timer]:
    """Timers still counting down, soonest first."""
    _sweep()
    return sorted((t for t in _timers.values() if not t.ringing),
                  key=lambda t: t.remaining_s)


def ringing() -> list[Timer]:
    """Timers that have fired and not been acknowledged, oldest first."""
    _sweep()
    return sorted((t for t in _timers.values() if t.ringing),
                  key=lambda t: t.fired_at or 0)


def all_timers() -> list[Timer]:
    _sweep()
    return ringing() + active()


def as_dict(timer: Timer) -> dict:
    remaining = timer.remaining_s
    return {
        "id": timer.id,
        "label": timer.label,
        "duration_s": timer.duration_s,
        "remaining_s": round(remaining, 1),
        "ringing": timer.ringing,
        # Display only, and recomputed from the monotonic remainder every
        # read, so an NTP step corrects it instead of baking in an error.
        "ends_at": (datetime.now() + timedelta(seconds=remaining)).strftime("%-I:%M %p")
        if not timer.ringing else None,
    }


def state() -> dict:
    return {
        "timers": [as_dict(t) for t in all_timers()],
        "ringing": [as_dict(t) for t in ringing()],
    }
