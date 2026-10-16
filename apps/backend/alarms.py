"""Weekly alarms — one slot per weekday.

SHAPE
    Seven slots, Monday to Sunday, each with a time and an on/off toggle
    (USER DECISION 2026-10-16: "an alarm on each day of the week"). Not a list
    of arbitrary alarms: the whole week then fits on one screen with
    touch-sized controls and there is no add/delete flow to design.

WHY PERSISTED, WHEN TIMERS ARE NOT
    An alarm is a schedule, not a countdown. "7:30 on Tuesdays" is still true
    after a restart, and an alarm clock that forgets when the power blinks is
    not an alarm clock. Stored next to the Spotify token in the state volume.

WHY WALL CLOCK HERE, WHEN TIMERS USE MONOTONIC
    The opposite choice, for the opposite reason: this IS a wall-clock
    question. "Has 7:30 happened yet" can only be answered by the clock on the
    wall, so an NTP step correcting the Pi's clock at boot must move the
    alarm with it. `last_fired` is a date string for the same reason.

FIRING, AND NOT FIRING TWICE
    A slot rings when the local time is inside a short window after its time
    and it has not already fired today. Acknowledging it (Stop, or the song
    ending) records today's date against the slot, which is also what stops a
    backend restart at 7:31 from ringing an alarm that was already dealt with.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Optional

log = logging.getLogger("alarms")

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")

# How long after its minute a slot still counts as due. Long enough that a
# backend restart or a slow poll does not skip an alarm entirely, short enough
# that one started 10 minutes late is not a surprise.
FIRE_WINDOW_S = 120.0

DEFAULT_PATH = "/app/state/alarms.json"


def _path() -> str:
    return os.environ.get("ALARMS_PATH", DEFAULT_PATH)


@dataclass
class Alarm:
    weekday: int            # 0 = Monday, matching datetime.weekday()
    hour: int = 7           # 24-hour internally; the UI presents AM/PM
    minute: int = 0
    enabled: bool = False
    # ISO date this slot last rang, so it fires once per day at most.
    last_fired: Optional[str] = None


_alarms: dict[int, Alarm] = {}
_loaded = False

# Which slot is ringing right now, if any. In memory: "ringing" is a thing
# happening now, and a restart genuinely interrupts it.
_ringing_weekday: Optional[int] = None


def _load() -> dict[int, Alarm]:
    global _alarms, _loaded
    if _loaded:
        return _alarms

    _loaded = True
    _alarms = {d: Alarm(weekday=d) for d in range(7)}

    try:
        with open(_path()) as fh:
            stored = json.load(fh)
    except FileNotFoundError:
        return _alarms
    except (OSError, ValueError) as exc:
        log.warning("Ignoring unreadable alarms file %s: %s", _path(), exc)
        return _alarms

    for raw in stored.get("alarms", []):
        try:
            weekday = int(raw["weekday"])
            if not 0 <= weekday <= 6:
                continue
            _alarms[weekday] = Alarm(
                weekday=weekday,
                hour=max(0, min(23, int(raw.get("hour", 7)))),
                minute=max(0, min(59, int(raw.get("minute", 0)))),
                enabled=bool(raw.get("enabled", False)),
                last_fired=raw.get("last_fired"),
            )
        except (KeyError, TypeError, ValueError):
            log.warning("Skipping malformed alarm entry: %.120s", raw)

    return _alarms


def _save() -> None:
    path = _path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as fh:
            json.dump({"alarms": [asdict(a) for a in _load().values()]}, fh, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        # Same posture as the Spotify token: keep working in memory, say
        # loudly that it will not survive a restart.
        log.error("Could not persist alarms to %s: %s. Changes will be lost "
                  "on restart.", path, exc)


# ---------------------------------------------------------------------------
# operations
# ---------------------------------------------------------------------------

def set_alarm(weekday: int, hour: Optional[int] = None,
              minute: Optional[int] = None,
              enabled: Optional[bool] = None) -> Alarm:
    """Update one slot. Only the fields given change."""
    alarms = _load()
    if not 0 <= weekday <= 6:
        raise ValueError(f"weekday must be 0-6, got {weekday}")

    alarm = alarms[weekday]
    if hour is not None:
        alarm.hour = max(0, min(23, int(hour)))
    if minute is not None:
        alarm.minute = max(0, min(59, int(minute)))
    if enabled is not None:
        alarm.enabled = bool(enabled)

    # Changing the time clears today's acknowledgement: moving an alarm to
    # later today should be able to ring today.
    if hour is not None or minute is not None:
        alarm.last_fired = None

    _save()
    return alarm


def next_fire(alarm: Alarm, now: Optional[datetime] = None) -> Optional[datetime]:
    """When this slot next rings, or None if it is off."""
    if not alarm.enabled:
        return None

    now = now or datetime.now()
    days_ahead = (alarm.weekday - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=alarm.hour, minute=alarm.minute, second=0, microsecond=0)

    # Today but already past (or already acknowledged) means next week.
    if days_ahead == 0 and (candidate <= now
                            or alarm.last_fired == now.date().isoformat()):
        candidate += timedelta(days=7)
    return candidate


def next_alarm(now: Optional[datetime] = None) -> Optional[tuple[Alarm, datetime]]:
    """The soonest enabled slot, with when it fires."""
    now = now or datetime.now()
    upcoming = [(a, when) for a in _load().values()
                if (when := next_fire(a, now)) is not None]
    return min(upcoming, key=lambda pair: pair[1]) if upcoming else None


def check(now: Optional[datetime] = None) -> Optional[Alarm]:
    """Start ringing if a slot is due. Returns whatever is ringing, if any.

    Called on every read of the state, which the dashboard polls once a
    second -- so this is what actually makes alarms go off.
    """
    global _ringing_weekday

    if _ringing_weekday is not None:
        return _load()[_ringing_weekday]

    now = now or datetime.now()
    today = now.date().isoformat()
    alarm = _load().get(now.weekday())

    if alarm is None or not alarm.enabled or alarm.last_fired == today:
        return None

    due_at = now.replace(hour=alarm.hour, minute=alarm.minute,
                         second=0, microsecond=0)
    elapsed = (now - due_at).total_seconds()
    if 0 <= elapsed <= FIRE_WINDOW_S:
        _ringing_weekday = alarm.weekday
        log.info("Alarm ringing: %s %02d:%02d", WEEKDAYS[alarm.weekday],
                 alarm.hour, alarm.minute)
        return alarm

    return None


def stop() -> bool:
    """Acknowledge the ringing alarm. True if one was ringing.

    Records today against the slot so it does not immediately ring again
    inside the fire window -- which is what would happen on the very next
    poll otherwise.
    """
    global _ringing_weekday
    if _ringing_weekday is None:
        return False

    alarm = _load()[_ringing_weekday]
    alarm.last_fired = date.today().isoformat()
    _ringing_weekday = None
    _save()
    log.info("Alarm stopped: %s", WEEKDAYS[alarm.weekday])
    return True


def as_dict(alarm: Alarm, now: Optional[datetime] = None) -> dict:
    when = next_fire(alarm, now)
    return {
        "weekday": alarm.weekday,
        "day": WEEKDAYS[alarm.weekday],
        "hour": alarm.hour,
        "minute": alarm.minute,
        "enabled": alarm.enabled,
        # Pre-formatted so the dashboard and anything spoken agree on the
        # wording, the same way services.summarize() works.
        "label": datetime(2000, 1, 1, alarm.hour, alarm.minute).strftime("%-I:%M %p"),
        "next_fire_in_s": round((when - (now or datetime.now())).total_seconds())
        if when else None,
    }


def state() -> dict:
    now = datetime.now()
    ringing = check(now)
    upcoming = next_alarm(now)

    return {
        "alarms": [as_dict(a, now) for a in _load().values()],
        "ringing": as_dict(ringing, now) if ringing else None,
        # Drives the top bar's alarm icon: "something is set for the next
        # 24 hours" is the only question that pill answers.
        "next_fire_in_s": round((upcoming[1] - now).total_seconds())
        if upcoming else None,
    }
