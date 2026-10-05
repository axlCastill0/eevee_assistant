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


@dataclass(frozen=True)
class Intent:
    name: str
    description: str   # shown to the classifier; keep it short and behavioural
    needs_item: bool   # if False, the classifier must emit item=null


INTENTS: dict[str, Intent] = {
    "service_status": Intent(
        name="service_status",
        description="ask whether a named service is running or healthy",
        needs_item=True,
    ),
    "list_services": Intent(
        name="list_services",
        description="ask which services exist or what is running",
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
# Service registry
# ---------------------------------------------------------------------------
# Only `backend` is self-reported today. Anything else is declared but has no
# real health probe yet — handle() says so out loud rather than inventing a
# status. Wire real probes here as services come online.
KNOWN_SERVICES: dict[str, str] = {
    "backend": "live",       # if this code is running, the backend is up
    "voice": "declared",     # voice pipeline; no probe yet
}

_ALIASES: dict[str, str] = {
    "api": "backend",
    "the api": "backend",
    "server": "backend",
    "voice pipeline": "voice",
    "voice assistant": "voice",
    "assistant": "voice",
}


def _resolve_service(item: str) -> Optional[str]:
    key = item.strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in KNOWN_SERVICES else None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
# Handlers return the exact sentence to speak. Response text is composed here,
# in Python, never by the language model — a small model will happily state a
# service is running without having looked.


def handle(intent: str, item: Optional[str]) -> tuple[str, bool]:
    """Execute `intent` and return (speech, ok).

    `ok` is False when the intent was not understood or could not be served;
    `speech` is always safe to say verbatim.
    """
    if intent == "get_time":
        # %-I is glibc-specific (no zero padding); this runs on Debian.
        return f"It is {datetime.now().strftime('%-I:%M %p').lower()}.", True

    if intent == "list_services":
        names = ", ".join(sorted(KNOWN_SERVICES))
        return f"I know about {names}.", True

    if intent == "service_status":
        if not item:
            return "Which service?", False

        resolved = _resolve_service(item)
        if resolved is None:
            return f"I don't know a service called {item}.", False

        state = KNOWN_SERVICES[resolved]
        if state == "live":
            return f"{resolved} is running.", True
        # Declared but unprobed. Say that honestly.
        return f"I can't check {resolved} yet. No health probe is wired up.", False

    return "Sorry, I didn't catch that.", False
