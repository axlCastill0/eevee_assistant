"""Voice routes.

The voice pipeline (apps/voice/) runs in a separate container and talks to
these endpoints over HTTP. It must be able to fail without affecting the API,
so nothing here holds state belonging to the pipeline.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth import require_api_key
from intents import INTENTS, handle

log = logging.getLogger("voice")

router = APIRouter(dependencies=[Depends(require_api_key)])


class IntentRequest(BaseModel):
    intent: str = Field(..., description="intent name from GET /voice/intents")
    item: Optional[str] = Field(None, description="item/subject, or null")
    transcript: Optional[str] = Field(
        None, description="raw transcript, for logging and later retraining"
    )


class IntentResponse(BaseModel):
    speech: str          # say this verbatim
    intent: str          # echoed back, after normalisation
    item: Optional[str]
    ok: bool


@router.get("/health")
def voice_health():
    return {"status": "ok", "route": "voice"}


@router.get("/intents")
def voice_intents():
    """Intent catalogue. The pipeline builds its grammar from this at startup."""
    return {
        "intents": {
            name: {"description": i.description, "needs_item": i.needs_item}
            for name, i in INTENTS.items()
        }
    }


@router.post("/intent", response_model=IntentResponse)
def voice_intent(req: IntentRequest):
    """Resolve a classified intent into a sentence to speak."""
    intent = req.intent if req.intent in INTENTS else "unknown"
    if intent != req.intent:
        log.warning("Unknown intent %r from pipeline; treating as unknown", req.intent)

    # Enforce the item contract server-side; the pipeline's grammar is advisory.
    item = req.item if INTENTS[intent].needs_item else None

    speech, ok = handle(intent, item)
    log.info("intent=%s item=%r transcript=%r -> %r", intent, item, req.transcript, speech)
    return IntentResponse(speech=speech, intent=intent, item=item, ok=ok)
