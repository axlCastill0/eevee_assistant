"""Voice routes.

The voice pipeline (apps/voice/) runs in a separate container and talks to
these endpoints over HTTP. It must be able to fail without affecting the API,
so nothing here holds state belonging to the pipeline — only the timestamp of
its last heartbeat, which is what lets the backend report the pipeline as down
when it stops checking in.
"""
import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import events
import services
from auth import API_KEY_HEADER, require_api_key
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
    """Liveness of this route. Does NOT report pipeline health — see /services."""
    return {"status": "ok", "route": "voice"}


@router.post("/heartbeat")
def voice_heartbeat():
    """Called by the pipeline on a timer to prove it is alive.

    Health is inferred from these check-ins stopping, because a dead pipeline
    cannot answer a probe or report its own failure.
    """
    services.record_heartbeat("voice")
    return {"status": "ok", "stale_after_s": services.STALE_AFTER_S}


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


# ---------------------------------------------------------------------------
# Voice activity — the push channel behind the dashboard's voice pill.
#
# This is deliberately separate from the heartbeat above. The heartbeat
# answers "is the pipeline alive" on a 45s window; these events answer "what
# is it doing right now", and the UI needs them within a frame or two of the
# wake word firing. See apps/backend/events.py for the rationale.
# ---------------------------------------------------------------------------


class VoiceStateRequest(BaseModel):
    state: str = Field(..., description="ready | listening | thinking | speaking | offline")
    transcript: Optional[str] = Field(None, description="what was heard, once STT has run")
    speech: Optional[str] = Field(None, description="what is being said, on 'speaking'")


@router.post("/state")
async def voice_state(req: VoiceStateRequest):
    """Called by the pipeline on every stage transition.

    async on purpose: publishing touches asyncio queues, and a sync endpoint
    would be run in a threadpool with no running loop of its own. It is also
    the fastest possible handler — the pipeline is waiting on this call before
    it starts recording.
    """
    event = events.hub.publish(req.state, transcript=req.transcript, speech=req.speech)
    # debug, not info: there are four of these per utterance and the
    # interesting ones (transcript, speech) are already logged by /intent.
    log.debug("voice state -> %s", event["state"])
    return {"status": "ok", "seq": event["seq"]}


@router.get("/state")
def voice_state_current():
    """Last known activity state.

    The dashboard's WebSocket already receives this on connect; this exists so
    a client that cannot hold a socket open (or a curl during debugging) can
    still read it.
    """
    return {"event": events.hub.last, "subscribers": events.hub.subscriber_count}


# The WebSocket lives on its own router because the HTTP router applies
# `require_api_key` router-wide, and that dependency raises HTTPException —
# which has no meaning on a socket that has not been accepted yet. The handler
# below does the same check by hand and closes with a WebSocket status code
# instead.
ws_router = APIRouter()

# Seconds of silence before the server sends a keepalive frame. Two things
# need this:
#   - nginx closes an idle proxied connection (proxy_read_timeout), and a
#     kiosk can sit untouched for hours between utterances
#   - a Pi that suspends its network leaves a socket that looks open but is
#     dead; the write is what discovers that, so the UI can reconnect
# Must stay well below the proxy_read_timeout set for this location.
PING_INTERVAL_S = 20.0


@ws_router.websocket("/events")
async def voice_events(websocket: WebSocket):
    """Push voice activity to the dashboard as it happens.

    Auth is the same shared secret as everywhere else, injected by the ui's
    nginx into the upgrade request. The browser still never holds the key.
    """
    expected = os.environ.get("API_KEY")
    presented = websocket.headers.get(API_KEY_HEADER.lower())

    if not expected:
        # Mirrors auth.py: an unconfigured server is a server error, not a
        # rejected client. 1011 = internal error.
        await websocket.close(code=1011, reason="Server API key not configured")
        return

    if presented != expected:
        # 1008 = policy violation. Closing BEFORE accept() would send an HTTP
        # 403 instead, which a browser reports only as an opaque failure; this
        # way the UI can tell "rejected" from "unreachable".
        await websocket.accept()
        await websocket.close(code=1008, reason="Invalid or missing API key")
        return

    await websocket.accept()
    queue = events.hub.subscribe()
    log.info("Dashboard subscribed to voice events (%d total)",
             events.hub.subscriber_count)

    # Reading from the client is not for the client's benefit — nothing is
    # expected to arrive. It is how a disconnect is noticed promptly instead of
    # on the next failed write, which could be a keepalive away.
    reader = asyncio.create_task(websocket.receive_text())
    try:
        while True:
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {getter, reader},
                timeout=PING_INTERVAL_S,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if reader in done:
                break                       # client went away (or spoke; same action)

            if getter in done:
                await websocket.send_json(getter.result())
                continue

            getter.cancel()                 # timed out: keepalive instead
            await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError is what Starlette raises for a send on an already
        # closed socket, which is a normal way for a kiosk reload to end.
        pass
    finally:
        reader.cancel()
        events.hub.unsubscribe(queue)
        log.info("Dashboard unsubscribed from voice events (%d left)",
                 events.hub.subscriber_count)
