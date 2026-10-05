"""Keyword fast path, tried before the SLM.

Most utterances to a fixed-vocabulary assistant are one of a handful of
phrasings. Matching those with regex skips the model entirely — worth ~4-5 s
per command with Qwen2.5-1.5B/Q5 on a Pi 5.

This is a cache, not a classifier. It only ever returns a match it is certain
about; anything else returns None and goes to the SLM. A wrong fast-path hit is
far worse than a slow correct answer, so the patterns are deliberately narrow
and anchored.

Fast-path coverage is per-intent and hand-written. Intents the API adds later
are simply not covered here and fall through to the SLM, which is correct
behaviour — add patterns only once you know the real phrasings.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("fastpath")

# Filler that may trail an utterance ("is the backend running right now").
# Stripped from the whole probe BEFORE matching, because the rules below use
# fullmatch and trailing filler would otherwise defeat every one of them.
# Applied repeatedly, so stacked filler ("running right now please") also goes.
_TRAILING = re.compile(
    # Note: "there" is deliberately NOT here. It is load-bearing in
    # "what services are there", and stripping it breaks that rule.
    r"\s*\b(right now|now|at the moment|currently|yet|still|please|again|"
    r"for me|about)\b\s*$",
    re.IGNORECASE,
)


def _strip_trailing(text: str) -> str:
    """Remove trailing filler words, repeatedly until stable."""
    while True:
        stripped = _TRAILING.sub("", text).strip()
        if stripped == text:
            return text
        text = stripped

# Each entry: (compiled pattern, intent, item-capture-group or None).
# Patterns are fullmatch-anchored against the cleaned transcript.
_RULES: list[tuple[re.Pattern, str, Optional[str]]] = [
    # -- get_time ---------------------------------------------------------
    (re.compile(r"(what('?s| is)\s+)?the\s+time", re.I), "get_time", None),
    (re.compile(r"what('?s| is)\s+the\s+time", re.I), "get_time", None),
    (re.compile(r"what\s+time\s+is\s+it", re.I), "get_time", None),
    (re.compile(r"time", re.I), "get_time", None),
    (re.compile(r"(tell|give)\s+me\s+the\s+time", re.I), "get_time", None),
    (re.compile(r"current\s+time", re.I), "get_time", None),

    # -- list_services ----------------------------------------------------
    (re.compile(r"(list|what)\s+(are\s+the\s+)?services", re.I), "list_services", None),
    (re.compile(r"what\s+services\s+(do\s+you\s+know|do\s+you\s+have"
                r"|are\s+there|are\s+running|exist)", re.I),
     "list_services", None),
    (re.compile(r"what('?s| is)\s+running", re.I), "list_services", None),
    (re.compile(r"(list|show)\s+(me\s+)?(the\s+)?services", re.I), "list_services", None),

    # -- service_status ---------------------------------------------------
    # "is the backend running" / "is voice up"
    (re.compile(r"is\s+(?:the\s+)?(?P<item>.+?)\s+(running|up|online|alive|healthy|ok|okay)", re.I),
     "service_status", "item"),
    # "status of voice" / "what's the status of the api"
    (re.compile(r"(what('?s| is)\s+the\s+)?status\s+(of|for)\s+(?:the\s+)?(?P<item>.+)", re.I),
     "service_status", "item"),
    # "check voice" / "check on the backend"
    (re.compile(r"check\s+(on\s+)?(?:the\s+)?(?P<item>.+)", re.I),
     "service_status", "item"),
    # "how is voice doing"
    (re.compile(r"how('?s| is)\s+(?:the\s+)?(?P<item>.+?)(\s+doing)?", re.I),
     "service_status", "item"),
    # "voice status"
    (re.compile(r"(?:the\s+)?(?P<item>.+?)\s+status", re.I),
     "service_status", "item"),
]


class FastPath:
    """Regex pre-classifier. Only matches intents the API actually advertises."""

    def __init__(self, known_intents: list[str], enabled: bool = True):
        self.enabled = enabled
        self.known = set(known_intents)

        # Drop rules for intents this backend does not expose, so a fast path
        # can never emit an intent the API would reject.
        self.rules = [r for r in _RULES if r[1] in self.known]

        skipped = {r[1] for r in _RULES} - self.known
        if skipped:
            log.debug("Fast-path rules ignored for unknown intents: %s",
                      ", ".join(sorted(skipped)))
        log.info("Fast path %s (%d rules active)",
                 "enabled" if enabled else "disabled", len(self.rules))

    def match(self, text: str) -> Optional[tuple[str, Optional[str]]]:
        """Return (intent, item) on a confident match, else None."""
        if not self.enabled or not text:
            return None

        probe = _strip_trailing(text.strip().rstrip(".,!?").strip())
        if not probe:
            return None

        for pattern, intent, group in self.rules:
            m = pattern.fullmatch(probe)
            if not m:
                continue

            item: Optional[str] = None
            if group:
                item = _strip_trailing((m.group(group) or "").strip())
                # A captured item that is empty or pure filler means the
                # pattern matched too loosely. Defer to the SLM.
                if not item or item.lower() in ("it", "that", "this", "things"):
                    return None

            log.debug("Fast path hit: %r -> intent=%s item=%r", probe, intent, item)
            return intent, item

        return None
