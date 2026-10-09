"""Intent registry — single source of truth for voice intents.

The voice pipeline fetches this over HTTP at startup (`GET /voice/intents`) and
builds its GBNF grammar from the names returned here, so the classifier can
never emit an intent that has no handler.

To add an intent: add an `Intent` to `INTENTS`, write a handler returning an
`Answer`, and register it in `_HANDLERS`.
Nothing in apps/voice/ needs to change — it picks the new name up from the API
on its next restart.

WHO OWNS THE WORDS (changed 2026-10-08)
    This module still composes a canonical sentence that is always safe to say,
    and it is still the only thing here that looks at real data. What changed
    is that an answer now also carries the FACTS it was built from and a
    contract describing what any re-wording of it must preserve. The voice
    container may hand those to the SLM and speak a generated sentence instead
    — but only if it survives that contract.

    The rule the original decision was protecting still holds: a small model
    must never be the thing that decides whether a service is up. It is now
    allowed to decide how to say what this module already determined.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import services


@dataclass(frozen=True)
class Intent:
    name: str
    description: str   # shown to the classifier; keep it short and behavioural
    needs_item: bool   # if False, the classifier must emit item=null


@dataclass
class Answer:
    """An intent's result, plus everything needed to re-word it safely.

    `speech` is the canonical sentence and is ALWAYS safe to say verbatim. The
    rest exists so the voice container can ask the SLM for a better-sounding
    version and then prove the result did not drift.
    """

    speech: str
    ok: bool

    # Structured truth, handed to the phrasing model so it never has to infer
    # anything. Keep it small; it goes into a prompt on a Pi.
    facts: dict[str, Any] = field(default_factory=dict)

    # Substrings that MUST appear in a rewrite (case-insensitive). These are
    # the load-bearing words: service names when something is down, the actual
    # digits of the time. A rewrite missing one is rejected, not corrected.
    must_include: list[str] = field(default_factory=list)

    # Substrings that must NOT appear. Used for polarity: when everything is
    # healthy, naming a service at all is the shape a hallucinated outage
    # takes, so the names are forbidden outright.
    forbid: list[str] = field(default_factory=list)

    # At least ONE of these must appear. `must_include` alone cannot carry
    # polarity: requiring the word "voice" is equally satisfied by "voice is
    # down" and "voice is up and running". This is how the sentence is forced
    # to actually sound like bad news when the news is bad.
    require_any: list[str] = field(default_factory=list)

    # False for answers that must never be re-worded — the error lines, which
    # are spoken precisely when something is already broken.
    phrasable: bool = True


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
    "unknown": Intent(
        name="unknown",
        description=(
            "anything else. music, jokes, weather, math, timers, lights "
            "— all unknown. when in doubt, use this"
        ),
        needs_item=False,
    ),
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
# Handlers read real data and return an Answer. They never ask a model what is
# true; the model only ever gets told.


# Words that make a sentence read as an outage. A rewrite about a down service
# must contain at least one, or it is not reporting the outage no matter which
# service it names. Generous on purpose: a rewrite rejected for using a word
# not on this list costs only naturalness, but a short list would reject most
# of them and the persona would never be heard.
_DOWN_MARKERS = [
    "down", "offline", "off", "out", "stopped", "stalled", "silent", "quiet",
    "unresponsive", "not responding", "unreachable", "dead", "gone", "lost",
    "missing", "failed", "failing", "trouble", "problem", "issue", "wrong",
    "no heartbeat", "isn't running", "is not running", "isn't up", "is not up",
]


def _system_health() -> Answer:
    speech, all_healthy = services.summarize()
    entries = services.health()

    down = [s.name for s in entries if not s.healthy]
    up = [s.name for s in entries if s.healthy]

    if all_healthy:
        # Nothing is wrong, so naming a service is the exact shape an invented
        # outage would take. Forbidding the names is a cheap, deterministic
        # polarity check that still allows "all clear", "no issues", "nothing
        # to report" — none of which contain a service name.
        return Answer(
            speech=speech,
            ok=True,
            facts={"all_healthy": True, "services_up": up, "services_down": []},
            forbid=up,
        )

    # Something IS down. Every down name must survive, and the rewrite has to
    # actually sound negative — "voice" alone could appear in a sentence
    # claiming it is fine.
    #
    # Healthy names are forbidden here too. That loses the genuinely nice
    # "backend's fine, but voice is down", and it is the deliberate trade: the
    # one failure this must not have is naming the wrong service as broken.
    return Answer(
        speech=speech,
        ok=True,
        facts={"all_healthy": False, "services_up": up, "services_down": down},
        must_include=down,
        forbid=up,
        require_any=_DOWN_MARKERS,
    )


def _get_time() -> Answer:
    # %-I is glibc-specific (no zero padding); this runs on Debian.
    now = datetime.now()
    clock = now.strftime("%-I:%M").lower()
    meridiem = now.strftime("%p").lower()

    return Answer(
        speech=f"It is {clock} {meridiem}.",
        ok=True,
        facts={"time": f"{clock} {meridiem}"},
        # The digits and the half of the day. A rewrite that drops either is
        # not an answer to "what time is it".
        must_include=[clock, meridiem],
    )


def _unknown() -> Answer:
    # Hardcoded by user decision 2026-10-08: this is what gets said when the
    # assistant already failed to understand, and dressing that up helps
    # nobody.
    return Answer(
        speech="Sorry, I didn't catch that.",
        ok=False,
        phrasable=False,
    )


_HANDLERS = {
    "system_health": _system_health,
    "get_time": _get_time,
    "unknown": _unknown,
}


def handle(intent: str, item: Optional[str]) -> Answer:
    # `item` is unused: no current intent takes one. The parameter stays
    # because the route passes it and the first intent that needs a subject
    # (a shopping list, a light, a timer) will want it here.
    """Execute `intent` and return its Answer.

    `Answer.ok` reports whether the request was served, not whether the news
    was good — a successful health check that finds a service down is ok=True.
    """
    handler = _HANDLERS.get(intent, _unknown)
    return handler()
