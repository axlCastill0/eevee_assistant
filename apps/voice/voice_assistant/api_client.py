"""HTTP client for the backend API.

The voice pipeline is a separate container from the API on purpose: the API
must stay up when the pipeline dies. The inverse also has to hold — the
pipeline stays useful (and audible) when the API is down — so every call here
degrades to a spoken fallback instead of raising.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from . import config

log = logging.getLogger("api")


# Baked-in fallback catalogue, used only when the API cannot be reached at
# startup. The API's /voice/intents is the real source of truth; this exists so
# the pipeline can still boot and still say "the backend is not responding".
FALLBACK_INTENTS: dict[str, dict] = {
    "service_status": {"description": "ask whether a named service is running",
                       "needs_item": True},
    "list_services": {"description": "ask which services exist", "needs_item": False},
    "get_time": {"description": "ask for the current time", "needs_item": False},
    "unknown": {"description": "anything else", "needs_item": False},
}


@dataclass
class IntentCatalog:
    """Intent names plus metadata, as advertised by the API."""
    intents: dict[str, dict]
    from_api: bool   # False means FALLBACK_INTENTS is in use

    @property
    def names(self) -> list[str]:
        return list(self.intents)

    def needs_item(self, name: str) -> bool:
        return bool(self.intents.get(name, {}).get("needs_item", False))

    def prompt_block(self) -> str:
        """Intent list formatted for the classifier's system prompt."""
        return "\n".join(
            f"- {name}: {meta.get('description', '')}"
            for name, meta in self.intents.items()
        )


class BackendClient:
    """Thin wrapper over the API. All methods are failure-tolerant.

"""

    def __init__(self,
                 base_url: str = config.API_BASE_URL,
                 api_key: str = config.API_KEY,
                 timeout: float = config.API_TIMEOUT_S,
                 retries: int = config.API_RETRIES):
        if not api_key:
            # Not fatal here: it fails loudly on the first request instead, and
            # we would rather boot and report the problem out loud than crash.
            log.error("API_KEY is empty. Every backend call will return 401.")

        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-API-Key": api_key},
        )
        log.info("Backend client -> %s", self.base_url)

    def close(self) -> None:
        self._client.close()

    # -- internals ---------------------------------------------------------

    def _request(self, method: str, path: str, **kw) -> Optional[httpx.Response]:
        """Request with linear backoff. Returns None if every attempt failed.

        Only connection/timeout errors are retried. A 4xx is a real answer —
        retrying a 401 just delays the spoken error.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(self.retries + 1):
            try:
                resp = self._client.request(method, path, **kw)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))
                continue

            if resp.status_code >= 500 and attempt < self.retries:
                time.sleep(0.25 * (attempt + 1))
                continue
            return resp

        log.warning("%s %s unreachable after %d attempts: %s",
                    method, path, self.retries + 1, last_exc)
        return None

    # -- endpoints ---------------------------------------------------------

    def health(self) -> bool:
        resp = self._request("GET", "/voice/health")
        return resp is not None and resp.status_code == 200

    def fetch_intents(self) -> IntentCatalog:
        """Fetch the intent catalogue. Falls back to the baked-in list."""
        resp = self._request("GET", "/voice/intents")

        if resp is None:
            log.warning("Intent catalogue unavailable; using built-in fallback")
            return IntentCatalog(FALLBACK_INTENTS, from_api=False)

        if resp.status_code == 401:
            log.error("Backend rejected API_KEY (401); using built-in fallback")
            return IntentCatalog(FALLBACK_INTENTS, from_api=False)

        if resp.status_code != 200:
            log.error("GET /voice/intents returned %d; using built-in fallback",
                      resp.status_code)
            return IntentCatalog(FALLBACK_INTENTS, from_api=False)

        try:
            intents = resp.json()["intents"]
            if not intents:
                raise ValueError("empty catalogue")
        except (KeyError, ValueError, TypeError) as exc:
            log.error("Malformed intent catalogue (%s); using fallback", exc)
            return IntentCatalog(FALLBACK_INTENTS, from_api=False)

        # "unknown" is load-bearing: the grammar and the classifier both need a
        # bail-out label. Add it if the API somehow omits it.
        if "unknown" not in intents:
            intents["unknown"] = FALLBACK_INTENTS["unknown"]

        log.info("Loaded %d intents from API: %s", len(intents), ", ".join(intents))
        return IntentCatalog(intents, from_api=True)

    def submit_intent(self, intent: str, item: Optional[str],
                      transcript: Optional[str] = None) -> str:
        """POST a classified intent and return the sentence to speak.

        On any failure this returns a spoken explanation rather than raising,
        so the user always hears something.
        """
        t0 = time.monotonic()
        resp = self._request("POST", "/voice/intent", json={
            "intent": intent, "item": item, "transcript": transcript,
        })

        if resp is None:
            return "I can't reach the backend right now."
        if resp.status_code == 401:
            return "The backend rejected my credentials."
        if resp.status_code >= 500:
            return "The backend had an error."
        if resp.status_code != 200:
            log.error("POST /voice/intent -> %d: %s", resp.status_code, resp.text[:200])
            return "The backend didn't understand that request."

        try:
            speech = resp.json()["speech"]
        except (KeyError, ValueError):
            log.error("Malformed /voice/intent response: %s", resp.text[:200])
            return "The backend sent back something I couldn't read."

        log.debug("API (%.2fs): %r", time.monotonic() - t0, speech)
        return speech
