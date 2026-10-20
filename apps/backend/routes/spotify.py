"""Spotify routes — now playing, four controls, and the one-time connect flow.

TWO ROUTERS, ON PURPOSE
    `router` is behind the usual X-API-Key dependency, like everything else.
    `public_router` holds exactly one route: the OAuth callback. Spotify
    redirects a BROWSER there, and that browser has no API key -- nginx only
    injects it on /api/*, and the redirect goes straight to the backend.

    That route is protected instead by the single-use `state` minted by
    /spotify/login, which IS key-protected. No key, no state; no state, the
    callback refuses. Same split as the WebSocket route in voice.py, which
    authenticates by hand for its own reasons.
"""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse

import lyrics
import spotify
from auth import require_api_key

log = logging.getLogger("routes.spotify")

router = APIRouter(dependencies=[Depends(require_api_key)])
public_router = APIRouter()


@router.get("/now-playing")
def now_playing():
    """Current playback. Cached by spotify.py; safe to poll once a second.

    Always 200 with a `status` field. A panel that has to distinguish "paused"
    from "not connected" from "Spotify is down" cannot do it from HTTP codes
    without reimplementing this logic, and an error code would make the
    dashboard's generic "backend unreachable" handler swallow all three.
    """
    return spotify.snapshot()


@router.post("/command")
def command(action: str = Body(..., embed=True)):
    """previous | play | pause | toggle | next.

    No seek: the progress bar is a readout, not a scrubber.
    """
    result = spotify.command(action)
    if result["status"] == "unsupported":
        raise HTTPException(status_code=400, detail=f"Unknown action {action!r}")
    return result


@router.get("/lyrics")
def track_lyrics():
    """Lyrics for whatever is playing, from LRCLIB. Cached per track.

    Reads the CACHED playback snapshot rather than asking Spotify again: the
    panel polls now-playing once a second already, and this must not double
    that. Always 200 with a `status`, for the same reason /now-playing is.
    """
    snap = spotify.snapshot()
    if snap.get("status") != "ok" or not snap.get("item"):
        return {"status": "idle"}

    return lyrics.lookup(snap["item"])


@router.get("/art/{image_id}")
def art(image_id: str):
    """Proxy one cover image.

    Three reasons this is not just a link to i.scdn.co:
      - same-origin pixels, so the panel can read them on a canvas to pick its
        background colours without depending on the CDN's CORS headers
      - the kiosk browser needs no direct internet access
      - covers are immutable, so nginx and the browser can cache them hard
    """
    fetched = spotify.fetch_art(image_id)
    if fetched is None:
        raise HTTPException(status_code=404, detail="No such cover")

    data, content_type = fetched
    return Response(content=data, media_type=content_type, headers={
        # Spotify image ids are content-addressed, so this can never go stale.
        "Cache-Control": "public, max-age=31536000, immutable",
    })


@router.get("/status")
def status():
    """Whether the account is connected, for the connect screen."""
    return {
        "configured": spotify.is_configured(),
        "connected": spotify.is_connected(),
        "redirect_uri": spotify.redirect_uri(),
        "scopes": spotify.SCOPES.split(),
    }


@router.get("/login")
def login():
    """The URL to open in a browser to connect the account.

    Returned as JSON rather than a 302 so this is usable from curl, from the
    dashboard, and from a browser pointed at /api/spotify/login -- which is the
    easiest path on the Pi, because nginx adds the key for you.
    """
    if not spotify.is_configured():
        raise HTTPException(
            status_code=503,
            detail="SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET are not set; "
                   "see docs/SPOTIFY.md",
        )

    state = spotify.new_state()
    return {
        "authorize_url": spotify.authorize_url(state),
        "redirect_uri": spotify.redirect_uri(),
    }


@router.post("/code")
def submit_code(code: str = Body(..., embed=True)):
    """Complete the flow by hand, with the code copied from the redirect URL.

    The escape hatch for authorizing from a laptop: the redirect lands on
    127.0.0.1 *there*, which fails to load, but the code is sitting in the
    address bar. This takes it. No state check -- the API key is the
    authentication for this one, and the code is single-use and short-lived
    at Spotify's end.
    """
    if not spotify.exchange_code(code.strip()):
        raise HTTPException(
            status_code=400,
            detail="Spotify rejected that code. They are single-use and expire "
                   "in about a minute -- start again at /spotify/login.",
        )
    return {"status": "connected"}


@router.post("/disconnect")
def disconnect():
    """Forget the stored tokens. Revoking the grant is done at Spotify."""
    spotify.disconnect()
    return {"status": "disconnected"}


# ---------------------------------------------------------------------------
# public: the OAuth redirect target
# ---------------------------------------------------------------------------

def _page(title: str, body: str, ok: bool) -> HTMLResponse:
    """A plain self-contained page. The browser that lands here is not the
    dashboard -- it is whatever the user authorized in -- so it gets no bundle,
    no fonts and no API calls."""
    colour = "#3ecf8e" if ok else "#f6685e"
    return HTMLResponse(
        status_code=200 if ok else 400,
        content=f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin:0; min-height:100vh; display:grid; place-items:center;
         background:#08090b; color:#e8eaed;
         font:16px/1.5 ui-sans-serif, system-ui, sans-serif; }}
  main {{ max-width:34rem; padding:2rem; text-align:center; }}
  h1 {{ font-size:1.5rem; margin:0 0 .75rem; color:{colour}; }}
  p {{ margin:.5rem 0; color:#9aa3af; }}
  code {{ font-family:ui-monospace, monospace; color:#e8eaed; }}
</style></head>
<body><main><h1>{title}</h1>{body}</main></body></html>""",
    )


@public_router.get("/callback")
def callback(code: str | None = None, state: str | None = None,
             error: str | None = None):
    """Where Spotify sends the browser after the consent screen."""
    if error:
        # The user pressed Cancel, or the app is misconfigured at Spotify.
        return _page("Not connected", f"<p>Spotify said: <code>{error}</code></p>"
                                      "<p>Nothing was saved.</p>", ok=False)

    if not code or not state or not spotify.consume_state(state):
        # Also the path for a replayed callback: states are single-use.
        log.warning("Rejected a Spotify callback with a missing or unknown state")
        return _page("Not connected",
                     "<p>That link is expired or was not issued by this "
                     "dashboard.</p><p>Start again at "
                     "<code>/api/spotify/login</code>.</p>", ok=False)

    if not spotify.exchange_code(code):
        return _page("Not connected",
                     "<p>Spotify would not exchange the code. Check "
                     "<code>SPOTIFY_CLIENT_SECRET</code> and that the redirect "
                     "URI registered in the Spotify dashboard matches exactly."
                     "</p>", ok=False)

    return _page("Spotify connected",
                 "<p>The panel will pick it up within a couple of seconds.</p>"
                 "<p>You can close this tab.</p>", ok=True)
