"""Screen power state.

Its own router because the consumer is scripts/screen-agent.sh on the host,
polling on its own cadence. The dashboard reads the same state out of
/clock/state, which it already polls.
"""
import logging

from fastapi import APIRouter, Body, Depends

import screen
from auth import require_api_key

log = logging.getLogger("routes.screen")

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("")
def get_screen():
    """What the screen should be doing. Polled by the host helper."""
    return screen.state()


@router.post("")
def set_screen(on: bool = Body(..., embed=True),
               source: str = Body("api", embed=True)):
    """Turn it on or off.

    `source` is free text from the caller (button, idle, touch, voice) and is
    only ever logged -- it is the first thing you want to know when a panel
    blanks for no apparent reason.
    """
    return screen.set_on(on, source)


@router.post("/lock")
def set_lock(locked: bool = Body(..., embed=True),
             source: str = Body("api", embed=True)):
    """Hold the screen awake against the idle timer, or release it.

    Deliberately NOT part of POST /screen: "is the screen on" and "may the
    timer turn it off" are different questions, and a caller that wants one
    must not have to restate the other.
    """
    return screen.set_locked(locked, source)
