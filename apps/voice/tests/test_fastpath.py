"""Fast-path regression tests.

These matter more than they look: a wrong fast-path hit silently bypasses the
classifier and produces a confidently wrong answer. The miss cases are the
important half of this file — anything ambiguous must fall through to the SLM.

Run with:  python -m pytest apps/voice/tests -q
No models or audio hardware required; fastpath.py is pure stdlib.
"""
import pytest

from voice_assistant.fastpath import FastPath

INTENTS = ["system_health", "get_time", "unknown"]


@pytest.fixture(scope="module")
def fp():
    return FastPath(INTENTS)


HITS = [
    # -- get_time ---------------------------------------------------------
    ("what time is it", "get_time"),
    ("what's the time", "get_time"),
    ("the time", "get_time"),
    ("time", "get_time"),
    ("current time", "get_time"),
    ("tell me the time", "get_time"),
    ("give me the time please", "get_time"),

    # -- system_health ----------------------------------------------------
    ("is everything ok", "system_health"),
    ("is everything okay", "system_health"),
    ("is everything good", "system_health"),
    ("everything good", "system_health"),
    ("everything ok", "system_health"),
    ("is everything working", "system_health"),
    ("is everything healthy", "system_health"),
    ("are all systems good", "system_health"),
    ("all systems ok", "system_health"),
    ("are all services up", "system_health"),
    ("health", "system_health"),
    ("health check", "system_health"),
    ("system health", "system_health"),
    ("systems check", "system_health"),
    ("system status", "system_health"),
    ("status", "system_health"),
    ("what's the status", "system_health"),
    ("is anything down", "system_health"),
    ("anything down", "system_health"),
    ("is something broken", "system_health"),
    ("anything offline", "system_health"),
    ("what's down", "system_health"),
    ("how are things", "system_health"),
    ("how are things doing", "system_health"),
    ("how is everything", "system_health"),
    ("how are we doing", "system_health"),
    ("check the services", "system_health"),
    ("check everything", "system_health"),
    ("check health", "system_health"),
]

# Must fall through to the SLM. A hit on any of these is a bug.
MISSES = [
    "tell me a joke",
    "turn on the lights",
    "play some music",
    "what is the weather",
    "set a timer for five minutes",
    "restart the voice pipeline",   # an action, not a query
    "shut everything down",         # an action, and dangerously close to health
    "is it",
    "check it",
    "check that",
    "",
]


@pytest.mark.parametrize("text,intent", HITS)
def test_hits(fp, text, intent):
    result = fp.match(text)
    assert result is not None, f"{text!r} should have matched"
    got_intent, got_item = result
    assert got_intent == intent
    # No current intent takes an item, so a captured item is a bug.
    assert got_item is None, f"{text!r} captured an unexpected item {got_item!r}"


@pytest.mark.parametrize("text", MISSES)
def test_misses(fp, text):
    assert fp.match(text) is None, f"{text!r} should have fallen through to the SLM"


def test_disabled_never_matches():
    disabled = FastPath(INTENTS, enabled=False)
    assert disabled.match("what time is it") is None


def test_rules_pruned_to_advertised_intents():
    """A fast path must never emit an intent the API does not advertise."""
    limited = FastPath(["get_time", "unknown"])
    assert limited.match("what time is it") == ("get_time", None)
    # system_health is not advertised, so its rules are inactive.
    assert limited.match("is everything ok") is None


def test_trailing_filler_tolerated(fp):
    """Rules use fullmatch, so trailing filler must be stripped beforehand."""
    for text in ("is everything ok right now", "status please", "health check again"):
        assert fp.match(text) is not None, f"{text!r} should match despite filler"
