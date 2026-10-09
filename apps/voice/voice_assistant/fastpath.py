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

# Filler that may trail an utterance ("is everything ok right now").
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

# Words meaning "working", used by several health patterns.
_OK = r"(ok|okay|good|alright|all\s*right|fine|working|healthy|up|running|online)"

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

    # -- system_health ----------------------------------------------------
    # There is exactly one health intent, covering every service at once, so
    # these patterns do not capture a subject.

    # "is everything ok" / "everything good" / "are all systems good"
    (re.compile(rf"(is|are)?\s*(everything|everthing|all\s+systems|all\s+services|"
                rf"all\s+good|we\s+good)\s*{_OK}?", re.I), "system_health", None),
    # "system health" / "health check" / "systems check" / "health"
    (re.compile(r"(system|systems)?\s*health(\s+check)?", re.I), "system_health", None),
    (re.compile(r"(system|systems)\s+(check|status)", re.I), "system_health", None),
    # "status" / "what's the status"
    (re.compile(r"(what('?s| is)\s+the\s+)?status", re.I), "system_health", None),
    # "is anything down" / "anything down" / "what's down"
    (re.compile(r"(is\s+)?(anything|something)\s+(down|broken|offline|failing)", re.I),
     "system_health", None),
    (re.compile(r"what('?s| is)\s+(down|broken|offline)", re.I), "system_health", None),
    # "how are things" / "how are we doing"
    (re.compile(r"how\s+(are|is)\s+(things|we|everything)(\s+doing)?", re.I),
     "system_health", None),
    # "check the services" / "check everything"
    (re.compile(r"check\s+(on\s+)?(the\s+)?(services|systems|everything|health)", re.I),
     "system_health", None),

    # -- get_date ---------------------------------------------------------
    (re.compile(r"(what('?s| is)\s+)?(the\s+)?date", re.I), "get_date", None),
    (re.compile(r"what('?s| is)\s+today('?s)?(\s+date)?", re.I), "get_date", None),
    (re.compile(r"what\s+day\s+is\s+it(\s+today)?", re.I), "get_date", None),
    (re.compile(r"what\s+day\s+of\s+the\s+week\s+is\s+it", re.I), "get_date", None),
    (re.compile(r"(tell\s+me\s+)?(the\s+)?today('?s)?\s+date", re.I), "get_date", None),

    # -- greeting ---------------------------------------------------------
    # Anchored tightly: "hello" alone is a greeting, but "hello can you turn
    # on the lights" is not, and fullmatch keeps those apart.
    (re.compile(r"(hello|hi|hey|yo|howdy)(\s+there)?", re.I), "greeting", None),
    (re.compile(r"good\s+(morning|afternoon|evening)", re.I), "greeting", None),
    (re.compile(r"(are\s+you\s+)?(there|awake|up|online|listening)\??", re.I),
     "greeting", None),

    # -- repeat_last ------------------------------------------------------
    # NOTE: these are written against the output of _strip_trailing, which
    # removes a trailing "again". "say that again" arrives here as "say that",
    # so matching the literal phrase would never fire. Same trap as "there" in
    # the health rules. Do not "fix" these by adding \s+again back.
    (re.compile(r"(can\s+you\s+|could\s+you\s+)?(say|repeat)\s+(that|it)", re.I),
     "repeat_last", None),
    (re.compile(r"(what\s+did\s+you\s+say|what\s+was\s+that)", re.I), "repeat_last", None),
    (re.compile(r"repeat", re.I), "repeat_last", None),
    (re.compile(r"come\s+again", re.I), "repeat_last", None),

    # -- set_theme --------------------------------------------------------
    # The item group is the theme name; the handler maps synonyms.
    # "go" is deliberately NOT a verb here: "go dark" means the screen, not
    # the palette, and sleep_screen claims it below.
    (re.compile(r"(switch|change|set)\s+(to\s+|the\s+)?"
                r"(?P<theme>dark|light|night|day|auto|automatic)(\s+mode|\s+theme)?", re.I),
     "set_theme", "theme"),
    (re.compile(r"(?P<theme>dark|light|night|day|auto|automatic)\s+(mode|theme)", re.I),
     "set_theme", "theme"),
    (re.compile(r"(set|change)\s+the\s+(theme|mode)\s+to\s+"
                r"(?P<theme>dark|light|night|day|auto|automatic)", re.I),
     "set_theme", "theme"),

    # -- sleep_screen / wake_screen ---------------------------------------
    (re.compile(r"(turn\s+)?(the\s+)?(screen|display|panel|monitor)\s+off", re.I),
     "sleep_screen", None),
    (re.compile(r"turn\s+off\s+(the\s+)?(screen|display|panel|monitor)", re.I),
     "sleep_screen", None),
    (re.compile(r"(go\s+)?(dark|to\s+sleep)", re.I), "sleep_screen", None),
    (re.compile(r"(blank|dim|sleep)\s+(the\s+)?(screen|display)", re.I),
     "sleep_screen", None),
    (re.compile(r"good\s*night", re.I), "sleep_screen", None),

    (re.compile(r"(turn\s+)?(the\s+)?(screen|display|panel|monitor)\s+(on|back\s+on)", re.I),
     "wake_screen", None),
    (re.compile(r"turn\s+on\s+(the\s+)?(screen|display|panel|monitor)", re.I),
     "wake_screen", None),
    (re.compile(r"wake(\s+up)?\s+(the\s+)?(screen|display|panel)", re.I),
     "wake_screen", None),
    # Bare "wake up" is the screen. sleep_screen's spoken reply tells the user
    # to say exactly this, so it must not land on greeting.
    (re.compile(r"wake\s+up", re.I), "wake_screen", None),

    # -- get_weather ------------------------------------------------------
    (re.compile(r"(what('?s| is)\s+)?(the\s+)?weather(\s+like)?(\s+outside|\s+today)?", re.I),
     "get_weather", None),
    (re.compile(r"how('?s| is)\s+(the\s+)?weather(\s+outside|\s+today)?", re.I),
     "get_weather", None),
    (re.compile(r"(what('?s| is)\s+)?(the\s+)?temperature\s+outside", re.I),
     "get_weather", None),
    (re.compile(r"is\s+it\s+(raining|snowing|cold|hot|warm|sunny)(\s+outside)?", re.I),
     "get_weather", None),
    (re.compile(r"(do\s+i\s+need\s+)(a\s+)?(coat|jacket|umbrella)", re.I),
     "get_weather", None),

    # -- list_capabilities ------------------------------------------------
    (re.compile(r"what\s+can\s+(you|i)\s+(do|ask)(\s+you)?", re.I),
     "list_capabilities", None),
    (re.compile(r"(what\s+are\s+)?your\s+(capabilities|commands|features)", re.I),
     "list_capabilities", None),
    (re.compile(r"help(\s+me)?", re.I), "list_capabilities", None),
    (re.compile(r"what\s+do\s+you\s+do", re.I), "list_capabilities", None),

    # -- get_uptime -------------------------------------------------------
    (re.compile(r"(what('?s| is)\s+)?(the\s+)?uptime", re.I), "get_uptime", None),
    (re.compile(r"how\s+long\s+(have\s+you\s+been|has\s+(it|this|the\s+\w+)\s+been)"
                r"\s+(up|running|on)", re.I), "get_uptime", None),
    (re.compile(r"when\s+did\s+(you|it|this)\s+(boot|start|last\s+reboot)", re.I),
     "get_uptime", None),

    # -- cpu_temp ---------------------------------------------------------
    (re.compile(r"(what('?s| is)\s+)?(the\s+)?(cpu\s+|processor\s+)?temp(erature)?", re.I),
     "cpu_temp", None),
    (re.compile(r"how\s+hot\s+(is|are)\s+(it|you|the\s+\w+)", re.I), "cpu_temp", None),
    (re.compile(r"(are\s+you\s+)?(running\s+)?hot", re.I), "cpu_temp", None),
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
