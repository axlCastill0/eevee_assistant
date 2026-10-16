"""Current conditions, for the panel.

WHY NOT IN /clock/state
    That endpoint is polled once a second and every field behind it is in
    memory. `weather.current()` is a cache read almost always -- but on a
    miss it blocks for up to four seconds on Open-Meteo, which is exactly the
    4s client timeout the dashboard gives that poll. One slow refresh would
    stall the poll that rings alarms. So weather gets its own route and its
    own, much slower, poll.

NO ERRORS OF OUR OWN
    Every failure comes back 200 with a `status`, like the Spotify snapshot:
    "no location configured" and "cannot reach Open-Meteo" are different
    sentences on screen, and neither is this backend malfunctioning.
"""
from fastapi import APIRouter, Depends

import weather
from auth import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("")
def current():
    return weather.state()
