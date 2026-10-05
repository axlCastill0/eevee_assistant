"""Intent registry — single source of truth for voice intents.

The voice pipeline fetches this over HTTP at startup (`GET /voice/intents`) and
builds its GBNF grammar from the names returned here, so the classifier can
never emit an intent that has no handler.

To add an intent: add an `Intent` to `INTENTS` and a branch in `handle()`.
Nothing in apps/voice/ needs to change — it picks the new name up from the API
on its next restart.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import services


@dataclass(frozen=True)
class Intent:
    name: str
    description: str   # shown to the classifier; keep it short and behavioural
    needs_item: bool   # if False, the classifier must emit item=null


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
# Handlers return the exact sentence to speak. Response text is composed here,
# in Python, never by the language model — a small model will happily state
# that everything is fine without having looked.


def handle(intent: str, item: Optional[str]) -> tuple[str, bool]:
    """Execute `intent` and return (speech, ok).

    `speech` is always safe to say verbatim. `ok` reports whether the request
    was served, not whether the news was good — a successful health check that
    finds a service down still returns ok=True.
    """
    if intent == "system_health":
        speech, _all_healthy = services.summarize()
        return speech, True

    if intent == "get_time":
        # %-I is glibc-specific (no zero padding); this runs on Debian.
        return f"It is {datetime.now().strftime('%-I:%M %p').lower()}.", True

    return "Sorry, I didn't catch that.", False
