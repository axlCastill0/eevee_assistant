"""Grammar builder tests.

build_grammar_text is pure string work, so it is testable without llama.cpp.
The regression guarded here is the GBNF escape gotcha: a `\\-` inside a
character class makes llama.cpp segfault instead of reporting a parse error,
so `-` must stay last in the bracket.
"""
import re

# slm.py imports llama_cpp lazily, inside IntentClassifier.__init__, so the
# module body is import-safe without the model runtime installed.
from voice_assistant.slm import build_grammar_text as _build


def test_includes_every_intent():
    text = _build(["service_status", "get_time", "unknown"])
    for name in ("service_status", "get_time", "unknown"):
        assert f'\\"{name}\\"' in text


def test_intents_are_alternatives():
    text = _build(["a", "b", "c"])
    intent_line = next(l for l in text.splitlines() if l.startswith("intent"))
    assert intent_line.count("|") == 2


def test_dash_is_last_in_char_class():
    """GBNF rejects \\- inside a bracket; llama.cpp segfaults on it."""
    text = _build(["unknown"])
    char_line = next(l for l in text.splitlines() if l.startswith("char"))
    assert r"\-" not in char_line, "escaped dash will segfault llama.cpp"
    assert char_line.rstrip().endswith("]")
    cls = re.search(r"\[(.*)\]", char_line).group(1)
    assert cls.endswith("-"), f"dash must be last in the class, got {cls!r}"


def test_has_required_rules():
    text = _build(["unknown"])
    for rule in ("root", "intent", "item", "string", "char", "ws"):
        assert re.search(rf"^{rule}\s+::=", text, re.M), f"missing rule {rule}"


def test_item_allows_null():
    assert '"null"' in _build(["unknown"])
