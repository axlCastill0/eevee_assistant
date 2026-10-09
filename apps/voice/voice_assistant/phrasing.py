"""Response phrasing — the SLM says the backend's answer in its own words.

WHAT THIS IS AND IS NOT
    The backend decides what is true and ships a canonical sentence that is
    always safe to say. This module asks Qwen to say that same thing better,
    and then REFUSES the result unless it provably still says it. The model
    never learns a fact here; it is only ever told one.

    That distinction is the whole design. The original rule — "never let the
    model compose responses" — existed because a 1.5B model will cheerfully
    report that a service is running without having looked. It still would.
    The difference is that it is no longer the thing that looked.

THE VALIDATOR IS THE POINT
    A rewrite is rejected if it drops a required substring (the down service's
    name, the digits of the time) or contains a forbidden one (a service name
    when nothing is wrong — the exact shape an invented outage takes). Both
    lists come from the backend, which is the only thing that knows. Anything
    rejected falls back to the canonical sentence, so a bad rewrite costs
    naturalness, never accuracy.

COST
    One extra SLM call per answer, on a Pi, with a different system prompt from
    the classifier's — so the KV cache is cold each time. The prompt here is
    kept deliberately short for that reason. See config.PHRASE_SCOPE for which
    answers pay it.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from . import config

log = logging.getLogger("phrasing")


# The persona. Dry, composed, economical — the house style of a certain
# fictional British butler and his Irish successor. Two hard rules carry the
# safety story and are repeated deliberately: say only what you are given, and
# say it in one sentence.
_SYSTEM_TEMPLATE = """You are the voice of a home server assistant. Your manner is calm, dry and \
economical — composed, quietly witty, never chirpy and never robotic.{address_rule}

You are given a fact sheet and a plain sentence stating it. Rewrite that \
sentence in your own voice.

Hard rules:
- Say ONLY what the facts state. Never add a cause, a reassurance, a \
suggestion, a time, a number or a service name that is not in the facts.
- If the facts say something is down, your sentence must say that plainly. \
Never soften it into something that sounds fine.
- ONE short sentence. Under twenty words. It is spoken aloud, not read.
- Vary the wording between calls. Do not reuse the plain sentence verbatim.
- Output the sentence only. No quotes, no JSON, no preamble, no emoji."""

_ADDRESS_RULE = (
    " You address the user as \"{address}\", occasionally — about one reply in "
    "three, never twice in one sentence."
)

_USER_TEMPLATE = """Facts: {facts}
Plain sentence: {speech}

Your sentence:"""


# Guards against the model answering with something that is not a sentence.
_MAX_CHARS = 140
_MIN_CHARS = 2


class PhrasingRejected(Exception):
    """A rewrite failed the contract. Not an error — the expected outcome
    often enough that the caller just falls back."""


def validate(candidate: str,
             must_include: list[str],
             forbid: list[str],
             require_any: list[str] | None = None) -> str:
    """Return the cleaned rewrite, or raise PhrasingRejected.

    Matching is case-insensitive and whitespace-normalised, and `forbid`
    matches on WORD BOUNDARIES: forbidding the service name "voice" must not
    reject the perfectly good "no issues" because of some substring, and must
    not be fooled by "Voice." with punctuation attached either.
    """
    text = " ".join(candidate.split())

    # Models like to wrap an answer in quotes when told to output only a
    # sentence. Strip one matched pair rather than rejecting over it.
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1].strip()

    if not (_MIN_CHARS <= len(text) <= _MAX_CHARS):
        raise PhrasingRejected(f"length {len(text)}")

    if "{" in text or "}" in text:
        raise PhrasingRejected("looks like JSON")

    lowered = text.lower()

    for needle in must_include:
        if needle.lower() not in lowered:
            raise PhrasingRejected(f"dropped required {needle!r}")

    for needle in forbid:
        if re.search(rf"\b{re.escape(needle.lower())}\b", lowered):
            raise PhrasingRejected(f"contains forbidden {needle!r}")

    # Polarity. Requiring the service's name is satisfied just as well by
    # "voice is up and running", so when the backend says something is wrong
    # the sentence has to contain a word that means it.
    if require_any and not any(n.lower() in lowered for n in require_any):
        raise PhrasingRejected("no polarity marker")

    return text


class ResponsePhraser:
    """Wraps a Llama instance that someone else owns.

    IMPORTANT: this takes the classifier's model, it does not load its own.
    A second Llama would be another ~1.2 GB resident on a board that is
    already running Chromium, and the two stages are sequential so they can
    never contend for it.
    """

    def __init__(self, llm: Any,
                 address: str = config.PERSONA_ADDRESS,
                 temperature: float = config.PHRASE_TEMPERATURE,
                 max_tokens: int = config.PHRASE_MAX_TOKENS):
        self.llm = llm
        self.temperature = temperature
        self.max_tokens = max_tokens

        address_rule = _ADDRESS_RULE.format(address=address) if address else ""
        self.system_prompt = _SYSTEM_TEMPLATE.format(address_rule=address_rule)

    def phrase(self,
               speech: str,
               facts: dict,
               must_include: list[str],
               forbid: list[str],
               require_any: list[str] | None = None) -> str:
        """Re-word `speech`. Returns the canonical sentence on any failure.

        Never raises. A phrasing problem must not cost the user their answer,
        so every path out of here is speakable.
        """
        if not facts:
            # Nothing to ground a rewrite in. Refuse rather than let the model
            # improvise from the sentence alone.
            return speech

        t0 = time.monotonic()
        try:
            raw = self._complete(speech, facts)
        except Exception:
            log.exception("Phrasing inference failed; using canonical")
            return speech

        try:
            text = validate(raw, must_include, forbid, require_any)
        except PhrasingRejected as exc:
            # info, not warning: this is a designed outcome and will happen.
            # A sustained run of them is the signal worth noticing, which is
            # why the reason is logged every time.
            log.info("Rewrite rejected (%s): %r", exc, raw)
            return speech

        log.debug("Phrased in %.2fs: %r -> %r", time.monotonic() - t0, speech, text)
        return text

    def _complete(self, speech: str, facts: dict) -> str:
        result = self.llm.create_chat_completion(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": _USER_TEMPLATE.format(
                    facts=json.dumps(facts, separators=(",", ":")),
                    speech=speech,
                )},
            ],
            # Unlike classification, this WANTS variation — a fixed seed and
            # temperature 0 would produce the same sentence forever, which is
            # the thing being fixed.
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            # No grammar: the output is prose. The validator is what makes
            # that safe, and it checks meaning-bearing content rather than
            # shape, which a grammar cannot do.
        )
        return result["choices"][0]["message"]["content"]
