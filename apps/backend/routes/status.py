"""Status routes — the dashboard's data source.

Separate from /voice because this is not about voice: it is the whole system's
health, and the dashboard polls it regardless of whether the voice pipeline is
running. That is the point — if voice is down, this endpoint is how you find
out.

The spoken answer and this JSON come from the same services.health(), so the
dashboard and the assistant can never disagree.
"""
from fastapi import APIRouter, Depends

import services
from auth import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/services")
def services_health():
    """Health of every known service.

    `all_healthy` and `speech` are precomputed so a dashboard does not have to
    reimplement the summary logic the voice pipeline already gets.
    """
    entries = services.health()
    speech, all_healthy = services.summarize()

    return {
        "all_healthy": all_healthy,
        "speech": speech,
        "stale_after_s": services.STALE_AFTER_S,
        "services": [
            {
                "name": s.name,
                "healthy": s.healthy,
                "detail": s.detail,
                # Rounded: sub-second precision is noise on a status screen.
                "last_seen_s_ago": (
                    None if s.last_seen_s_ago is None else round(s.last_seen_s_ago, 1)
                ),
            }
            for s in entries
        ],
    }
