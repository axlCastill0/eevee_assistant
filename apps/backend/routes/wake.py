"""Wake-on-LAN: status and the one button.

Its own route, not a field on /clock/state, for the same reason weather is:
the liveness probe opens a TCP connection with a timeout, and /clock/state is
the poll that rings alarms. See wol.py.
"""
import logging

from fastapi import APIRouter, Depends

import wol
from auth import require_api_key

log = logging.getLogger("routes.wake")

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("")
def state():
    return wol.state()


@router.post("")
def wake():
    """Send the magic packet.

    Always 200, never a 4xx/5xx: "no machine configured" is a sentence the
    panel shows and the assistant says, not an error of this backend's
    making. Same posture as the Spotify command results.
    """
    sent, detail = wol.send()
    return {"sent": sent, "detail": detail, **wol.state()}
