"""Screen power state.

Its own router rather than a corner of /clock because the consumer is
different: `scripts/screen-agent.sh` runs on the host, outside Docker, and
polls GET /screen on its own cadence. The dashboard reads the same state out
of /clock/state, which it is already polling once a second.
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
