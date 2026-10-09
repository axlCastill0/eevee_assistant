"""Intent classification using Qwen2.5 via llama-cpp-python.

Output is constrained by a GBNF grammar built from the API's intent catalogue,
which makes an invalid intent name literally impossible to generate. Without
the grammar, Qwen invents plausible-sounding intents that no handler exists for.

This module returns structured data only. It never decides what is true: a
small model will happily state a service is running without having looked.

Re-wording the backend's answer into something that does not sound canned is a
SEPARATE stage, in phrasing.py, which shares this model but is given the facts
and is validated against them.
"""
from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Optional

from . import config

if TYPE_CHECKING:
    # Type-only: importing api_client at runtime would drag httpx in, and
    # build_grammar_text below is pure string work that should stay testable
    # without the HTTP stack installed.
    from .api_client import IntentCatalog

log = logging.getLogger("slm")


_PROMPT_TEMPLATE = """You are a strict intent classifier for a home server voice assistant.

Read the user's message and return ONE JSON object with EXACTLY these two fields:
{{"intent": "<intent_name>", "item": "<name_or_null>"}}

Valid intents:
{intent_block}

Rules:
- Pick exactly one intent. Never invent intent names.
- "item" is the subject being asked about, lowercase, no articles. No current
  intent takes one, so "item" is null unless a listed intent clearly needs it.
- For intents that take no item, "item" MUST be null.
- Health questions cover ALL services at once. "is the voice pipeline up" is
  still system_health with item null, not a per-service query.
- If the request does not clearly match an intent, return "unknown" with item null.
- Output ONLY the JSON object. No prose, no explanation.

Examples:

User: "is everything ok"
Output: {{"intent": "system_health", "item": null}}

User: "are all systems good"
Output: {{"intent": "system_health", "item": null}}

User: "is anything down"
Output: {{"intent": "system_health", "item": null}}

User: "how are things looking"
Output: {{"intent": "system_health", "item": null}}

User: "is the voice pipeline healthy"
Output: {{"intent": "system_health", "item": null}}

User: "what time is it"
Output: {{"intent": "get_time", "item": null}}

User: "tell me a joke"
Output: {{"intent": "unknown", "item": null}}

User: "turn on the lights"
Output: {{"intent": "unknown", "item": null}}
"""


def build_grammar_text(intent_names: list[str]) -> str:
    """GBNF forcing valid JSON with one of `intent_names`.

    Note the char class: `-` must come last. GBNF rejects `\\-` as an escape
    inside a bracket expression, and llama.cpp segfaults rather than reporting
    the error cleanly.
    """
    alts = " | ".join(f'"\\"{name}\\""' for name in intent_names)
    return rf'''
root        ::= "{{" ws "\"intent\":" ws intent "," ws "\"item\":" ws item ws "}}"
intent      ::= {alts}
item        ::= "null" | string
string      ::= "\"" char+ "\""
char        ::= [a-zA-Z0-9 _-]
ws          ::= [ \t\n]*
'''


class IntentClassifier:
    """Holds the model, the compiled grammar, and the catalogue they encode."""

    def __init__(self, catalog: 'IntentCatalog'):
        from llama_cpp import Llama
        from llama_cpp.llama_grammar import LlamaGrammar

        self.catalog = catalog
        self.system_prompt = _PROMPT_TEMPLATE.format(
            intent_block=catalog.prompt_block()
        )

        t0 = time.monotonic()
        self.llm = Llama(
            model_path=config.SLM_PATH,
            n_ctx=config.SLM_N_CTX,
            n_threads=config.SLM_THREADS,
            # The prompt is fixed and long relative to the user turn, so the
            # whole thing is worth keeping resident.
            use_mlock=False,   # mlock can fail in a container without IPC_LOCK
            verbose=False,
        )
        self.grammar = LlamaGrammar.from_string(build_grammar_text(catalog.names))
        log.info("SLM loaded in %.1fs (%d threads, %s)",
                 time.monotonic() - t0, config.SLM_THREADS, config.SLM_PATH)

    def warmup(self) -> None:
        """One call with the real prompt shape, so the first user utterance is
        not charged for KV-cache initialisation.

        On a Pi 5 with the 1.5B this takes a while — run it before announcing
        readiness, not lazily on the first command.
        """
        t0 = time.monotonic()
        self._complete("warmup")
        log.info("SLM warmup took %.1fs", time.monotonic() - t0)

    def _complete(self, text: str) -> str:
        result = self.llm.create_chat_completion(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.0,              # deterministic classification
            max_tokens=config.SLM_MAX_TOKENS,
            grammar=self.grammar,
        )
        return result["choices"][0]["message"]["content"]

    def classify(self, text: str) -> tuple[str, Optional[str]]:
        """Classify `text` into (intent, item)."""
        t0 = time.monotonic()
        try:
            raw = self._complete(text)
        except Exception:
            log.exception("SLM inference failed for %r", text)
            return "unknown", None

        try:
            parsed = json.loads(raw)
            intent = parsed.get("intent", "unknown")
            item = parsed.get("item")
        except (json.JSONDecodeError, AttributeError):
            # The grammar makes this near-impossible, but a malformed answer
            # must not crash the loop.
            log.warning("SLM produced unparseable output: %r", raw)
            return "unknown", None

        if intent not in self.catalog.intents:
            log.warning("SLM emitted unknown intent %r", intent)
            return "unknown", None

        # Enforce the item contract locally too, so the backend is not asked to
        # clean up after the classifier.
        if not self.catalog.needs_item(intent):
            item = None
        elif isinstance(item, str):
            item = item.strip().lower() or None

        log.debug("SLM (%.2fs): intent=%r item=%r",
                  time.monotonic() - t0, intent, item)
        return intent, item
