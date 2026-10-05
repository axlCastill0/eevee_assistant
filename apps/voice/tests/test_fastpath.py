"""Fast-path regression tests.

These matter more than they look: a wrong fast-path hit silently bypasses the
classifier and produces a confidently wrong answer. The miss cases are the
important half of this file — anything ambiguous must fall through to the SLM.

Run with:  python -m pytest apps/voice/tests -q
No models or audio hardware required; fastpath.py is pure stdlib.
"""
import pytest

from voice_assistant.fastpath import FastPath

INTENTS = ["service_status", "list_services", "get_time", "unknown"]


@pytest.fixture(scope="module")
def fp():
    return FastPath(INTENTS)


HITS = [
    # -- get_time ---------------------------------------------------------
    ("what time is it", "get_time", None),
    ("what's the time", "get_time", None),
    ("the time", "get_time", None),
    ("time", "get_time", None),
    ("current time", "get_time", None),
    ("tell me the time", "get_time", None),
    ("give me the time please", "get_time", None),

    # -- list_services ----------------------------------------------------
    ("list services", "list_services", None),
    ("what services do you know about", "list_services", None),
    ("what services are there", "list_services", None),
    ("what services do you have", "list_services", None),
    ("what is running", "list_services", None),
    ("what's running", "list_services", None),
    ("show me the services", "list_services", None),

    # -- service_status ---------------------------------------------------
    ("is the backend running", "service_status", "backend"),
    ("is voice up", "service_status", "voice"),
    ("is the backend running right now", "service_status", "backend"),
    ("is voice up yet", "service_status", "voice"),
    ("is the voice pipeline healthy", "service_status", "voice pipeline"),
    ("status of voice", "service_status", "voice"),
    ("what is the status of the api", "service_status", "api"),
    ("what's the status for voice", "service_status", "voice"),
    ("check on the backend", "service_status", "backend"),
    ("check voice please", "service_status", "voice"),
    ("how is voice doing", "service_status", "voice"),
    ("how's the backend", "service_status", "backend"),
    ("voice status", "service_status", "voice"),
]

# Must fall through to the SLM. A hit on any of these is a bug.
MISSES = [
    "tell me a joke",
    "turn on the lights",
    "play some music",
    "what is the weather",
    "set a timer for five minutes",
    "is it",          # pronoun-only item
    "check it",       # pronoun-only item
    "check that",
    "",
]


@pytest.mark.parametrize("text,intent,item", HITS)
def test_hits(fp, text, intent, item):
    result = fp.match(text)
    assert result is not None, f"{text!r} should have matched"
    assert result == (intent, item)


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
    # service_status is not advertised, so its rules are inactive.
    assert limited.match("is the backend running") is None


def test_trailing_filler_tolerated(fp):
    """Rules use fullmatch, so trailing filler must be stripped beforehand."""
    for text in ("is the backend running right now", "check voice please"):
        assert fp.match(text) is not None, f"{text!r} should match despite filler"
