"""Timers, alarms, settings and the sound library.

ONE STATE ENDPOINT
    `GET /clock/state` returns timers, alarms and the settings in a single
    response. The dashboard polls it once a second from the app shell, not
    from a view, because an alarm has to ring whatever page is on screen --
    and because one poll for three things beats three polls for one each.

    It is also what drives the top bar's status icons, which is the other
    reason it cannot live inside the Dashboard view.
"""
import logging
import os

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

import alarms
import settings
import timers
from auth import require_api_key

log = logging.getLogger("routes.clock")

router = APIRouter(dependencies=[Depends(require_api_key)])


# ---------------------------------------------------------------------------
# combined state
# ---------------------------------------------------------------------------

@router.get("/state")
def state():
    """Everything the dashboard polls. Cheap: all of it is in memory."""
    return {
        "timers": timers.state(),
        "alarms": alarms.state(),
        "settings": settings.state(),
    }


# ---------------------------------------------------------------------------
# timers
# ---------------------------------------------------------------------------

@router.post("/timers")
def create_timer(duration_s: int = Body(..., embed=True),
                 label: str | None = Body(None, embed=True)):
    """Start a timer. The screen sends seconds; voice sends a phrase and the
    intent handler parses it there, so this stays a dumb setter."""
    if duration_s <= 0:
        raise HTTPException(status_code=400, detail="duration_s must be positive")
    return timers.as_dict(timers.add(duration_s, label))


@router.delete("/timers/{timer_id}")
def delete_timer(timer_id: str):
    """Cancel a running timer, or acknowledge a ringing one -- the same
    operation, because a timer that has been dealt with is gone either way."""
    if not timers.cancel(timer_id):
        raise HTTPException(status_code=404, detail="No such timer")
    return {"status": "cancelled"}


@router.post("/timers/stop-all")
def stop_all_timers():
    """The Stop button on the ringing banner, which does not care which of
    several timers went off while nobody was looking."""
    return {"stopped": [timers.stop_ringing(t.id) for t in timers.ringing()].count(True)}


# ---------------------------------------------------------------------------
# alarms
# ---------------------------------------------------------------------------

@router.put("/alarms/{weekday}")
def update_alarm(weekday: int,
                 hour: int | None = Body(None, embed=True),
                 minute: int | None = Body(None, embed=True),
                 enabled: bool | None = Body(None, embed=True)):
    try:
        return alarms.as_dict(alarms.set_alarm(weekday, hour, minute, enabled))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/alarms/stop")
def stop_alarm():
    """Stop the ringing alarm. Sent by the Stop button AND by the dashboard
    when the song finishes on its own -- both mean 'this one is dealt with'."""
    return {"stopped": alarms.stop()}


# ---------------------------------------------------------------------------
# settings and sounds
# ---------------------------------------------------------------------------

@router.get("/settings")
def get_settings():
    return settings.state()


@router.put("/settings")
def put_settings(values: dict = Body(...)):
    try:
        return settings.update(values)
    except ValueError as exc:
        # A sound that is not in the media directory. Worth a 400 rather than
        # storing it: the alternative is finding out at 7am.
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/sounds/{name}")
def sound(name: str):
    """Serve one file from the media directory.

    FileResponse streams it, so a 5-minute song is not read into memory, and
    the browser gets range support for free -- which it needs to seek, and
    some versions of Chromium want before they will play at all.
    """
    resolved = settings.resolve_sound(name)
    if resolved is None:
        raise HTTPException(status_code=404, detail="No such sound")

    path, media_type = resolved
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="No such sound")

    return FileResponse(path, media_type=media_type, headers={
        # The file behind a name can be replaced by dropping a new one in, so
        # this is cached for an hour rather than forever.
        "Cache-Control": "public, max-age=3600",
    })
