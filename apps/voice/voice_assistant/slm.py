"""Intent classification using Qwen2.5 via llama-cpp-python.

Output is constrained by a GBNF grammar built from the API's intent catalogue,
which makes an invalid intent name literally impossible to generate. Without
the grammar, Qwen invents plausible-sounding intents that no handler exists for.

The model returns structured data only. Spoken responses are composed by the
backend, never here — a small model will happily state a service is running
without having looked.
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

# Room left over the prompt for the user's sentence and the model's answer.
# The answer is capped by SLM_MAX_TOKENS and a transcript is short, so this is
# slack rather than a budget.
_CONTEXT_HEADROOM = 256


def _estimate_tokens(text: str) -> int:
    """Rough token count, used before a tokenizer exists.

    ~3.2 characters per token for English prose with punctuation, which errs
    high for this prompt (lots of short JSON fragments). Erring high is the
    safe direction: the cost is a slightly larger KV cache, and the cost of
    erring low is the crash this exists to prevent.
    """
    return int(len(text) / 3.2) + 1


_PROMPT_TEMPLATE = """You are a strict intent classifier for a home server voice assistant.

Read the user's message and return ONE JSON object with EXACTLY these two fields:
{{"intent": "<intent_name>", "item": "<name_or_null>"}}

Valid intents:
{intent_block}

Rules:
- Pick exactly one intent. Never invent intent names.
- "item" is the subject being asked about, lowercase, no articles. Two intents
  take one: set_theme ("dark", "light" or "auto") and show_page ("dashboard",
  "music" or "systems"). Everything else is null.
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

User: "what's today's date"
Output: {{"intent": "get_date", "item": null}}

User: "good evening"
Output: {{"intent": "greeting", "item": null}}

User: "sorry, what was that"
Output: {{"intent": "repeat_last", "item": null}}

User: "put the dashboard in dark mode"
Output: {{"intent": "set_theme", "item": "dark"}}

User: "switch the panel back to automatic"
Output: {{"intent": "set_theme", "item": "auto"}}

User: "go to music"
Output: {{"intent": "show_page", "item": "music"}}

User: "take me back to the dashboard"
Output: {{"intent": "show_page", "item": "dashboard"}}

User: "check systems"
Output: {{"intent": "show_page", "item": "systems"}}

User: "kill the screen for now"
Output: {{"intent": "sleep_screen", "item": null}}

User: "bring the display back"
Output: {{"intent": "wake_screen", "item": null}}

User: "keep the screen on"
Output: {{"intent": "lock_screen", "item": null}}

User: "don't let the panel turn itself off"
Output: {{"intent": "lock_screen", "item": null}}

User: "you can let the screen sleep again"
Output: {{"intent": "unlock_screen", "item": null}}

User: "do I need an umbrella today"
Output: {{"intent": "get_weather", "item": null}}

User: "what sort of things can I ask you"
Output: {{"intent": "list_capabilities", "item": null}}

User: "how long since the last reboot"
Output: {{"intent": "get_uptime", "item": null}}

User: "is the pi running hot"
Output: {{"intent": "cpu_temp", "item": null}}

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

        # The system prompt grows every time an intent is added, and llama.cpp
        # does not degrade when it no longer fits -- it raises and takes the
        # whole pipeline down at startup. That happened on the Pi on
        # 2026-10-19 with the 22nd intent (1048 tokens into a 1024 window),
        # and the container restart-looped until someone looked at the logs.
        #
        # So size the window from the prompt rather than hoping. The estimate
        # is deliberately generous; the exact count is checked below, once
        # there is a tokenizer to ask.
        n_ctx = self._fit_context(config.SLM_N_CTX, _estimate_tokens(self.system_prompt))

        t0 = time.monotonic()
        self.llm = Llama(
            model_path=config.SLM_PATH,
            n_ctx=n_ctx,
            n_threads=config.SLM_THREADS,
            # The prompt is fixed and long relative to the user turn, so the
            # whole thing is worth keeping resident.
            use_mlock=False,   # mlock can fail in a container without IPC_LOCK
            verbose=False,
        )

        # Now measure it properly. A reload costs about a second and only
        # happens when the estimate was wrong in the dangerous direction.
        exact = len(self.llm.tokenize(self.system_prompt.encode(), add_bos=True))
        needed = self._fit_context(n_ctx, exact)
        if needed > n_ctx:
            log.warning("System prompt is %d tokens; reloading with n_ctx=%d",
                        exact, needed)
            self.llm = Llama(
                model_path=config.SLM_PATH,
                n_ctx=needed,
                n_threads=config.SLM_THREADS,
                use_mlock=False,
                verbose=False,
            )
            n_ctx = needed

        self.n_ctx = n_ctx
        self.prompt_tokens = exact
        self.ok = True

        self.grammar = LlamaGrammar.from_string(build_grammar_text(catalog.names))
        log.info("SLM loaded in %.1fs (%d threads, n_ctx=%d, prompt=%d tokens, %s)",
                 time.monotonic() - t0, config.SLM_THREADS, n_ctx, exact,
                 config.SLM_PATH)

    @staticmethod
    def _fit_context(configured: int, prompt_tokens: int) -> int:
        """A context window the prompt actually fits in.

        Never shrinks below what was configured -- an explicit
        VOICE_SLM_N_CTX is a floor, not a target -- and leaves room for the
        user's sentence and the answer on top of the prompt.
        """
        needed = prompt_tokens + config.SLM_MAX_TOKENS + _CONTEXT_HEADROOM
        if needed <= configured:
            return configured

        # Round up to a multiple of 256: llama.cpp allocates the KV cache from
        # this, and odd sizes buy nothing.
        return ((needed + 255) // 256) * 256

    def warmup(self) -> None:
        """One call with the real prompt shape, so the first user utterance is
        not charged for KV-cache initialisation.

        On a Pi 5 with the 1.5B this takes a while — run it before announcing
        readiness, not lazily on the first command.

        NEVER RAISES. A classifier that cannot warm up is a degraded
        assistant; a pipeline that exits is a dead one, and on an always-on
        panel it restart-loops instead of telling anyone. The fast path still
        answers every common phrasing, so `self.ok = False` costs the long
        tail and nothing else.
        """
        t0 = time.monotonic()
        try:
            self._complete("warmup")
        except Exception:
            self.ok = False
            log.exception(
                "SLM warmup failed; continuing WITHOUT the classifier. "
                "Fast-path phrasings still work, anything else becomes "
                "'unknown'. n_ctx=%d, prompt=%d tokens.",
                self.n_ctx, self.prompt_tokens,
            )
            return
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
        if not self.ok:
            # Warmup already said why, loudly. Repeating it per utterance
            # would bury everything else in the log.
            return "unknown", None

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
