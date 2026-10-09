"""Intent registry — single source of truth for voice intents.

The voice pipeline fetches this over HTTP at startup (`GET /voice/intents`) and
builds its GBNF grammar from the names returned here, so the classifier can
never emit an intent that has no handler.

To add an intent: add an `Intent` to `INTENTS`, write a handler returning
(speech, ok), and register it in `_HANDLERS`. Nothing in apps/voice/ needs to
change — it picks the new name up from the API on its next restart.

WHO WRITES THE WORDS
    This module does, in Python. The language model classifies and nothing
    else. A 1.5B model will state that a service is running without having
    looked, and a second model pass to re-word answers was tried on 2026-10-08
    and removed the same day: it cost more latency than it was worth.

    Variation comes from `_pick`, which chooses between hand-written phrasings.
    Every one of them is true by construction, because a person wrote it next
    to the data it describes.
"""
from __future__ import annotations

import logging
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import events
import services
import sysinfo
import weather

log = logging.getLogger("intents")


@dataclass(frozen=True)
class Intent:
    name: str
    description: str   # shown to the classifier; keep it short and behavioural
    needs_item: bool   # if False, the classifier must emit item=null


# ---------------------------------------------------------------------------
# Phrasing
# ---------------------------------------------------------------------------

# Remembers the last line spoken per variant group so the same one is never
# used twice running. With three options that matters: plain random repeats
# about a third of the time, which is exactly often enough to feel broken.
_last_choice: dict[tuple, int] = {}


def _pick(*options: str) -> str:
    """Choose a phrasing, never the same one twice in a row.

    Keyed on the CALL SITE, not on the strings. Most variants here are
    f-strings, so they are fresh objects on every call and keying on their
    identity or value silently remembers nothing — which is how this was
    first written, and it repeated back-to-back 7 times in 20 draws.
    """
    if len(options) == 1:
        return options[0]

    caller = sys._getframe(1)
    key = (caller.f_code.co_filename, caller.f_lineno)

    previous_index = _last_choice.get(key)
    previous = options[previous_index] if (
        previous_index is not None and previous_index < len(options)
    ) else None
    pool = [i for i, o in enumerate(options) if o != previous] or list(range(len(options)))

    index = random.choice(pool)
    _last_choice[key] = index
    return options[index]


# What was last said, for `repeat_last`. Deliberately module state rather than
# anything persisted: "what did you say" only ever means the current session,
# and a repeat surviving a restart would be a surprise, not a feature.
_last_spoken: Optional[str] = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

INTENTS: dict[str, Intent] = {
    "system_health": Intent(
        name="system_health",
        description=(
            "ask whether everything is working, or which services are down. "
            "covers health, status and 'is everything ok' questions"
        ),
        needs_item=False,
    ),
    "get_time": Intent(
        name="get_time",
        description="ask for the current time",
        needs_item=False,
    ),
    "get_date": Intent(
        name="get_date",
        description="ask for today's date or what day of the week it is",
        needs_item=False,
    ),
    "greeting": Intent(
        name="greeting",
        description="greet the assistant. hello, hey, good morning, are you there",
        needs_item=False,
    ),
    "repeat_last": Intent(
        name="repeat_last",
        description="ask the assistant to repeat what it just said",
        needs_item=False,
    ),
    "set_theme": Intent(
        name="set_theme",
        description=(
            "change the dashboard's colour theme. item is 'dark', 'light' "
            "or 'auto'"
        ),
        needs_item=True,
    ),
    "wake_screen": Intent(
        name="wake_screen",
        description="turn the dashboard screen back on, wake the display",
        needs_item=False,
    ),
    "sleep_screen": Intent(
        name="sleep_screen",
        description="turn the dashboard screen off, blank or dim the display",
        needs_item=False,
    ),
    "get_weather": Intent(
        name="get_weather",
        description="ask about the weather, the temperature, or whether it is raining",
        needs_item=False,
    ),
    "list_capabilities": Intent(
        name="list_capabilities",
        description="ask what the assistant can do, or what it can be asked",
        needs_item=False,
    ),
    "get_uptime": Intent(
        name="get_uptime",
        description="ask how long the machine or the assistant has been running",
        needs_item=False,
    ),
    "cpu_temp": Intent(
        name="cpu_temp",
        description="ask how hot the machine or the processor is running",
        needs_item=False,
    ),
    "unknown": Intent(
        name="unknown",
        description=(
            "anything else. music, timers, lights, maths, jokes — all unknown. "
            "when in doubt, use this"
        ),
        needs_item=False,
    ),
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
# Each returns (speech, ok). `ok` reports whether the request was served, not
# whether the news was good — a health check that finds a service down is
# still ok=True.


def _system_health(item: Optional[str]) -> tuple[str, bool]:
    summary, all_healthy = services.summarize()

    if all_healthy:
        return _pick(
            "Everything good.",
            "All systems are running.",
            "No problems to report.",
            "Everything's up.",
        ), True

    # The summary names what is broken and is composed by services.summarize(),
    # so the variation here is only the lead-in. The facts stay in one place.
    return _pick(
        summary.capitalize(),
        f"Not quite. {summary.capitalize()}",
        f"We have a problem. {summary.capitalize()}",
        f"Not everything, no. {summary.capitalize()}",
    ), True


def _get_time(item: Optional[str]) -> tuple[str, bool]:
    # %-I is glibc-specific (no zero padding); this runs on Debian.
    clock = datetime.now().strftime("%-I:%M %p").lower()
    return _pick(
        f"It is {clock}.",
        f"{clock.capitalize()}.",
        f"Right now it's {clock}.",
    ), True


def _get_date(item: Optional[str]) -> tuple[str, bool]:
    now = datetime.now()
    weekday = now.strftime("%A")
    # %-d for the same reason as %-I: "October 8", not "October 08".
    date = now.strftime("%B %-d")

    return _pick(
        f"It's {weekday}, {date}.",
        f"Today is {weekday}, {date}.",
        f"{weekday}, the {_ordinal(now.day)} of {now.strftime('%B')}.",
    ), True


def _ordinal(day: int) -> str:
    """'1st', '2nd', '23rd' — spoken naturally by Piper."""
    if 11 <= day % 100 <= 13:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def _greeting(item: Optional[str]) -> tuple[str, bool]:
    """The line that gets said in front of other people. Make it land.

    Time-aware, because "good evening" at 2pm is the kind of detail that makes
    a demo feel canned.
    """
    hour = datetime.now().hour
    if hour < 12:
        part = "Good morning"
    elif hour < 18:
        part = "Good afternoon"
    else:
        part = "Good evening"

    _, all_healthy = services.summarize()

    if all_healthy:
        return _pick(
            f"{part}. All systems are online and standing by.",
            f"{part}. Everything's running. What do you need?",
            f"{part}. I'm here, and everything's green.",
            f"{part}. Online, and all systems nominal.",
        ), True

    # Even the showpiece line does not lie. If something is down while you are
    # demonstrating this, that is worth knowing before someone else asks.
    return _pick(
        f"{part}. I'm here, though not everything is.",
        f"{part}. Online, but something needs attention.",
        f"{part}. I'm up. Ask me about the system when you get a moment.",
    ), False


def _repeat_last(item: Optional[str]) -> tuple[str, bool]:
    if _last_spoken is None:
        return _pick(
            "I haven't said anything yet.",
            "Nothing to repeat — this is the first thing I've said.",
            "There's nothing behind me yet.",
        ), False

    return _pick(
        _last_spoken,
        f"I said: {_last_spoken}",
        f"Again: {_last_spoken}",
        f"Once more: {_last_spoken}",
    ), True


_THEMES = {
    "dark": "dark", "night": "dark", "black": "dark",
    "light": "light", "day": "light", "bright": "light", "white": "light",
    "auto": "auto", "automatic": "auto",
}


def _set_theme(item: Optional[str]) -> tuple[str, bool]:
    theme = _THEMES.get((item or "").strip().lower())

    if theme is None:
        return _pick(
            "I can set the panel to dark, light, or auto.",
            "Try dark, light, or auto.",
            "Dark, light, or auto — which one?",
        ), False

    events.hub.publish_command("set_theme", theme)

    if theme == "auto":
        return _pick(
            "Theme's on automatic now.",
            "Switching to automatic. It'll follow the clock.",
            "Auto theme. It'll change itself at sunrise and sunset.",
        ), True

    return _pick(
        f"Switching to {theme} mode.",
        f"{theme.capitalize()} mode it is.",
        f"Done. {theme.capitalize()} mode.",
    ), True


def _sleep_screen(item: Optional[str]) -> tuple[str, bool]:
    events.hub.publish_command("sleep_screen")
    return _pick(
        "Dimming the screen. Say wake up when you need it.",
        "Screen off. I'm still listening.",
        "Going dark. Just say wake up.",
    ), True


def _wake_screen(item: Optional[str]) -> tuple[str, bool]:
    events.hub.publish_command("wake_screen")
    return _pick(
        "Screen's back.",
        "Waking it up.",
        "Here you go.",
    ), True


def _get_weather(item: Optional[str]) -> tuple[str, bool]:
    if not weather.is_configured():
        return _pick(
            "I don't have a location set for weather yet.",
            "Nobody's told me where we are, so I can't check the weather.",
            "I'd need a location before I can answer that.",
        ), False

    now = weather.current()
    if now is None:
        return _pick(
            "I can't reach the weather service right now.",
            "The weather service isn't answering.",
            "No luck getting the forecast — we may be offline.",
        ), False

    where = f" in {now.place}" if now.place else ""
    temp = f"{now.temp_c:.0f}"

    # Mention "feels like" only when it actually differs enough to be worth
    # the extra words. Three degrees is about where people notice.
    feels = ""
    if abs(now.feels_like_c - now.temp_c) >= 3:
        feels = _pick(
            f" Feels more like {now.feels_like_c:.0f}.",
            f" Though it feels like {now.feels_like_c:.0f}.",
            f" Feels closer to {now.feels_like_c:.0f} out there.",
        )

    return _pick(
        f"It's {temp} degrees and {now.description}{where}.{feels}",
        f"{now.description.capitalize()}, {temp} degrees{where}.{feels}",
        f"Currently {temp} degrees{where}, {now.description}.{feels}",
    ), True


def _list_capabilities(item: Optional[str]) -> tuple[str, bool]:
    """Reads the registry, so it can never fall out of date.

    Spoken, not enumerated: reading eleven intent names aloud is unlistenable,
    so this describes the shape of what it does and invites a follow-up.
    """
    count = len([n for n in INTENTS if n != "unknown"])

    return _pick(
        f"I can check the system, tell you the time and date, read the "
        f"weather, report how hot and how long this machine has been running, "
        f"and control the panel. {count} things in total.",

        f"Ask me how the system's doing, what the time or date is, what the "
        f"weather's like, how hot the Pi is running, or tell me to change the "
        f"panel's theme or turn the screen off.",

        f"System health, time, date, weather, uptime, temperature, and the "
        f"dashboard itself — theme and screen. That's {count} things I answer to.",
    ), True


def _get_uptime(item: Optional[str]) -> tuple[str, bool]:
    seconds = sysinfo.uptime_seconds()

    if seconds is None:
        return _pick(
            "I can't read the uptime from in here.",
            "The uptime isn't readable right now.",
            "No uptime available — I can't see the clock on that.",
        ), False

    duration = sysinfo.human_duration(seconds)
    return _pick(
        f"Up {duration}.",
        f"This machine has been running {duration}.",
        f"{duration.capitalize()} since the last boot.",
    ), True


def _cpu_temp(item: Optional[str]) -> tuple[str, bool]:
    celsius = sysinfo.cpu_temp_c()

    if celsius is None:
        return _pick(
            "I can't read the temperature sensor.",
            "No temperature reading available from in here.",
            "The thermal sensor isn't reporting anything I can see.",
        ), False

    temp = f"{celsius:.0f}"

    # The Pi 5 throttles at 80C and is entirely comfortable below 60. Saying
    # the number alone makes the listener do the interpreting, which is the
    # assistant's job.
    if celsius >= 80:
        return _pick(
            f"{temp} degrees. That's hot enough to be throttling.",
            f"Running hot — {temp} degrees. Worth checking the airflow.",
            f"{temp} degrees, which is too hot. Something's not breathing.",
        ), True
    if celsius >= 70:
        return _pick(
            f"{temp} degrees. Warm, but within range.",
            f"A bit warm at {temp} degrees. Nothing alarming yet.",
            f"{temp} degrees — warmer than I'd like, but fine.",
        ), True

    return _pick(
        f"{temp} degrees. Comfortable.",
        f"Running at {temp} degrees.",
        f"{temp} degrees — all cool.",
    ), True


def _unknown(item: Optional[str]) -> tuple[str, bool]:
    return _pick(
        "Sorry, I didn't catch that.",
        "I didn't get that one.",
        "That's not something I know how to do yet.",
    ), False


_HANDLERS: dict[str, Callable[[Optional[str]], tuple[str, bool]]] = {
    "system_health": _system_health,
    "get_time": _get_time,
    "get_date": _get_date,
    "greeting": _greeting,
    "repeat_last": _repeat_last,
    "set_theme": _set_theme,
    "wake_screen": _wake_screen,
    "sleep_screen": _sleep_screen,
    "get_weather": _get_weather,
    "list_capabilities": _list_capabilities,
    "get_uptime": _get_uptime,
    "cpu_temp": _cpu_temp,
    "unknown": _unknown,
}


def handle(intent: str, item: Optional[str]) -> tuple[str, bool]:
    """Execute `intent` and return (speech, ok).

    `speech` is always safe to say verbatim.
    """
    global _last_spoken

    handler = _HANDLERS.get(intent, _unknown)
    speech, ok = handler(item)

    # Remember it for repeat_last — but never remember a repeat, or asking
    # twice would wrap the answer in "I said: I said: ...".
    if intent != "repeat_last":
        _last_spoken = speech

    return speech, ok
