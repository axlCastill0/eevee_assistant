"""Spotify playback — read the current track, and control it.

WHAT THIS CAN AND CANNOT DO
    The Web API is a REMOTE CONTROL for a session that already exists. It
    cannot originate audio. With nothing playing anywhere on the account,
    every control returns 404 NO_ACTIVE_DEVICE and there is no way around it
    from here -- the fix is to start playback on a phone/desktop, or to run a
    Spotify Connect client (raspotify/librespot) on the Pi so the Pi itself is
    a device. Playback control also requires Premium; reading does not.

WHY urllib AND NOT httpx
    Same reason as weather.py: the backend's dependency list is FastAPI,
    uvicorn and dotenv, and nothing here justifies a third HTTP client.

WHY A DEMAND-DRIVEN CACHE AND NOT A BACKGROUND POLLER
    The dashboard polls this backend once a second so its progress bar stays
    honest, but Spotify must not be asked that often. So the snapshot is
    cached with a TTL and refreshed inside whichever request finds it stale:
    ~3 s while something plays, ~10 s when it does not. No background task, no
    polling when nobody is looking at the screen, and the same shape as
    weather.py's cache. The cost is that one request in three does real work;
    at localhost latencies the UI never notices.

TOKENS
    Authorization Code flow. The client secret stays here and never reaches a
    browser. Access tokens last an hour and are refreshed on demand; the
    refresh token does not expire unless revoked, which is what lets the Pi
    run for months after a single authorization. It is written to
    SPOTIFY_TOKEN_PATH, which must be on a writable volume -- see
    docs/SPOTIFY.md.

FAILURE POSTURE
    Every failure becomes a `status` string the dashboard can render, never an
    exception. "Spotify is unreachable" is a legitimate thing for a panel to
    say; a 500 is not.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

log = logging.getLogger("spotify")

_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API = "https://api.spotify.com/v1"
_IMAGE_HOST = "https://i.scdn.co/image/"

# Everything the panel needs and nothing more. Adding a scope later means
# re-authorizing, so the list is deliberately complete for the four controls
# that exist: previous, play, pause, next.
SCOPES = (
    "user-read-playback-state "
    "user-read-currently-playing "
    "user-modify-playback-state"
)

# On the path between a touch and the UI updating, so short.
_TIMEOUT_S = 6.0

# Refresh the snapshot this often. Playing needs to be tight enough that a
# track change is noticed promptly; paused or idle does not.
_TTL_PLAYING_S = 3.0
_TTL_IDLE_S = 10.0

# Refresh the access token this long before it actually expires, so a request
# cannot fail on a token that died in flight.
_TOKEN_MARGIN_S = 60.0

# Single-use CSRF states handed out by /spotify/login. Short-lived because the
# only legitimate use is "a human completes a consent screen right now".
_STATE_TTL_S = 600.0

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/spotify/callback"
DEFAULT_TOKEN_PATH = "/app/state/spotify.json"


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

def client_id() -> str:
    return os.environ.get("SPOTIFY_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.environ.get("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()


def _token_path() -> str:
    return os.environ.get("SPOTIFY_TOKEN_PATH", DEFAULT_TOKEN_PATH).strip()


def is_configured() -> bool:
    """False when no app credentials are set, so the UI can say what to do."""
    return bool(client_id() and _client_secret())


def _ssl_context() -> ssl.SSLContext:
    """TLS context with a CA bundle that exists. See weather.py for the why."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ---------------------------------------------------------------------------
# token store
# ---------------------------------------------------------------------------

_tokens: Optional[dict] = None          # mirrors the file, None until loaded
_loaded = False


def _load_tokens() -> Optional[dict]:
    global _tokens, _loaded
    if _loaded:
        return _tokens

    _loaded = True
    path = _token_path()
    try:
        with open(path) as fh:
            _tokens = json.load(fh)
        log.info("Loaded Spotify tokens from %s", path)
    except FileNotFoundError:
        _tokens = None
    except (OSError, ValueError) as exc:
        # A corrupt file must not wedge the service. Treat it as not connected
        # and let the user re-authorize, which overwrites it.
        log.warning("Ignoring unreadable Spotify token file %s: %s", path, exc)
        _tokens = None
    return _tokens


def _save_tokens(data: dict) -> None:
    """Write the token file atomically, owner-readable only.

    Atomic because a refresh racing a crash would otherwise leave a truncated
    file, which costs a re-authorization. 0600 because this file is the
    account: anything holding the refresh token can read playback state.
    """
    global _tokens
    _tokens = data

    path = _token_path()
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        tmp = f"{path}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except OSError as exc:
        # Keep the in-memory copy: the current process stays usable until it
        # restarts, which is better than refusing to work at all. The volume
        # is almost certainly missing or read-only; docs/SPOTIFY.md covers it.
        log.error("Could not persist Spotify tokens to %s: %s. Authorization "
                  "will be lost on restart.", path, exc)


def is_connected() -> bool:
    tokens = _load_tokens()
    return bool(tokens and tokens.get("refresh_token"))


def disconnect() -> None:
    """Forget the account. The Spotify-side grant is revoked by the user."""
    global _tokens
    _tokens = None
    try:
        os.remove(_token_path())
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("Could not remove the token file: %s", exc)
    _invalidate()


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

_states: dict[str, float] = {}


def new_state() -> str:
    """Mint a single-use CSRF state for an authorization attempt."""
    now = time.monotonic()
    for old, issued in list(_states.items()):
        if now - issued > _STATE_TTL_S:
            del _states[old]

    state = secrets.token_urlsafe(24)
    _states[state] = now
    return state


def consume_state(state: str) -> bool:
    """True exactly once per state, and only within its TTL.

    This is what makes the keyless callback route safe: a caller who cannot
    authenticate to /spotify/login cannot obtain a state, so they cannot bind
    their own Spotify account to this panel.
    """
    issued = _states.pop(state, None)
    return issued is not None and (time.monotonic() - issued) <= _STATE_TTL_S


def authorize_url(state: str) -> str:
    query = urllib.parse.urlencode({
        "client_id": client_id(),
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "scope": SCOPES,
        "state": state,
        # Force the consent screen. Without it a re-authorization silently
        # reuses the previous grant, which hides a scope change.
        "show_dialog": "true",
    })
    return f"{_AUTH_URL}?{query}"


def _basic_auth_header() -> str:
    raw = f"{client_id()}:{_client_secret()}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _token_request(form: dict[str, str]) -> Optional[dict]:
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        _TOKEN_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": _basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S,
                                    context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        log.error("Spotify token request failed (%s): %s", exc.code, detail)
        return None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        log.error("Spotify token request failed: %s", exc)
        return None


def exchange_code(code: str) -> bool:
    """Trade an authorization code for tokens. True on success."""
    payload = _token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
    })
    if not payload or "refresh_token" not in payload:
        return False

    _save_tokens({
        "refresh_token": payload["refresh_token"],
        "access_token": payload.get("access_token", ""),
        "expires_at": time.time() + float(payload.get("expires_in", 3600)),
        "scope": payload.get("scope", ""),
    })
    _invalidate()
    log.info("Spotify account connected (scopes: %s)", payload.get("scope", "?"))
    return True


def _access_token() -> Optional[str]:
    """A valid access token, refreshing if needed. None when not connected."""
    tokens = _load_tokens()
    if not tokens or not tokens.get("refresh_token"):
        return None

    if tokens.get("access_token") and \
            time.time() < float(tokens.get("expires_at", 0)) - _TOKEN_MARGIN_S:
        return tokens["access_token"]

    payload = _token_request({
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    })
    if not payload or "access_token" not in payload:
        return None

    tokens = dict(tokens)
    tokens["access_token"] = payload["access_token"]
    tokens["expires_at"] = time.time() + float(payload.get("expires_in", 3600))
    # Spotify may hand back a new refresh token; keep the old one if it does not.
    if payload.get("refresh_token"):
        tokens["refresh_token"] = payload["refresh_token"]
    _save_tokens(tokens)
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

# Set when Spotify rate-limits us; no call is attempted before it passes.
_rate_limited_until = 0.0


def _call(method: str, path: str, token: str,
          query: Optional[dict] = None) -> tuple[int, Optional[Any]]:
    """One Web API call. Returns (http_status, parsed_body_or_None).

    A status of 0 means the request never completed (offline, DNS, TLS, or a
    timeout) -- the caller reports that as "unreachable" rather than guessing.
    """
    url = f"{_API}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    req = urllib.request.Request(url, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Length": "0",      # Spotify rejects PUT/POST with no length
    })

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S,
                                    context=_ssl_context()) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, None
            return resp.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        global _rate_limited_until
        if exc.code == 429:
            # Honour Retry-After to the second. Ignoring it is how an app gets
            # its rate limit tightened.
            wait = 5.0
            try:
                wait = max(1.0, float(exc.headers.get("Retry-After", "5")))
            except (TypeError, ValueError):
                pass
            _rate_limited_until = time.monotonic() + wait
            log.warning("Spotify rate-limited us; backing off %.0fs", wait)
            return 429, None

        body = exc.read().decode("utf-8", "replace")[:300]
        log.warning("Spotify %s %s -> %s: %s", method, path, exc.code, body)
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        log.warning("Spotify %s %s failed: %s", method, path, exc)
        return 0, None


def _authed_call(method: str, path: str,
                 query: Optional[dict] = None) -> tuple[int, Optional[Any]]:
    """`_call` plus token handling and one retry after a 401.

    The 401 retry exists because a token can be revoked or expire early; one
    forced refresh distinguishes "needs re-auth" from "unlucky timing".
    """
    if time.monotonic() < _rate_limited_until:
        return 429, None

    token = _access_token()
    if not token:
        return 401, None

    status, body = _call(method, path, token, query)
    if status == 401:
        tokens = _load_tokens()
        if tokens:
            tokens = dict(tokens)
            tokens["expires_at"] = 0        # force a refresh
            _save_tokens(tokens)
        token = _access_token()
        if not token:
            return 401, None
        status, body = _call(method, path, token, query)

    return status, body


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

# Statuses the dashboard knows how to render. Anything else is a bug here.
#   ok              a track (or episode) is loaded; may be playing or paused
#   idle            nothing is playing on the account
#   unconfigured    no client id/secret in the environment
#   unauthorized    not connected, or the grant was revoked
#   unreachable     Spotify could not be contacted
#   rate_limited    backing off; the last known snapshot is still shown
_cache: Optional[tuple[float, dict]] = None


def _invalidate() -> None:
    global _cache
    _cache = None


def _image_id(url: str) -> Optional[str]:
    """The id out of an i.scdn.co image URL, or None if it is not one.

    Only the id travels to the browser; the panel asks this backend for
    /spotify/art/<id>, which rebuilds the URL. That keeps the proxy from being
    a general-purpose fetcher, and it means the kiosk needs no direct access
    to Spotify's CDN -- and that the image is same-origin, so the canvas can
    read its pixels to pick the background colours.
    """
    if not url or not url.startswith(_IMAGE_HOST):
        return None
    image_id = url[len(_IMAGE_HOST):]
    return image_id if image_id.isalnum() and 8 <= len(image_id) <= 120 else None


def _best_image(images: list[dict]) -> Optional[str]:
    """The largest image's id. Big is right here: the cover is the whole page."""
    best, best_px = None, -1
    for image in images or []:
        px = int(image.get("width") or 0)
        image_id = _image_id(image.get("url", ""))
        if image_id and px > best_px:
            best, best_px = image_id, px
    return best


def _track_payload(item: dict, kind: str) -> dict:
    """Normalise a track or a podcast episode into one shape."""
    if kind == "episode":
        show = item.get("show") or {}
        return {
            "kind": "episode",
            "id": item.get("id"),
            "title": item.get("name") or "",
            "artist": show.get("name") or "",
            "album": show.get("name") or "",
            "duration_ms": int(item.get("duration_ms") or 0),
            "art_id": _best_image(item.get("images") or show.get("images") or []),
        }

    album = item.get("album") or {}
    return {
        "kind": "track",
        "id": item.get("id"),
        "title": item.get("name") or "",
        "artist": ", ".join(a.get("name", "") for a in item.get("artists") or []),
        "album": album.get("name") or "",
        "duration_ms": int(item.get("duration_ms") or 0),
        "art_id": _best_image(album.get("images") or []),
    }


def _fetch_snapshot() -> dict:
    if not is_configured():
        return {"status": "unconfigured"}
    if not is_connected():
        return {"status": "unauthorized"}

    # additional_types=episode or a podcast comes back as a null item, which
    # would look like "nothing is playing" while audio is audibly playing.
    status, body = _authed_call("GET", "/me/player",
                                {"additional_types": "track,episode"})

    if status == 429:
        return {"status": "rate_limited"}
    if status == 401:
        return {"status": "unauthorized"}
    if status == 0:
        return {"status": "unreachable"}
    # 204 means a valid session exists but nothing is loaded. Not an error.
    if status == 204 or not body:
        return {"status": "idle"}
    if status != 200:
        return {"status": "unreachable"}

    item = body.get("item")
    if not item:
        return {"status": "idle"}

    kind = body.get("currently_playing_type") or "track"
    device = body.get("device") or {}

    return {
        "status": "ok",
        "is_playing": bool(body.get("is_playing")),
        "progress_ms": int(body.get("progress_ms") or 0),
        # Wall clock, so the UI can tell how old the reading is and advance the
        # progress bar from it rather than from the moment it arrived.
        "fetched_at": time.time(),
        "device": {
            "name": device.get("name") or "",
            "type": device.get("type") or "",
            # Whether the Pi can control volume on it. Not used by the four
            # controls, but it is the usual next question.
            "volume_percent": device.get("volume_percent"),
        },
        "item": _track_payload(item, kind),
    }


def snapshot(force: bool = False) -> dict:
    """Current playback, cached. Never raises."""
    global _cache

    now = time.monotonic()
    if _cache is not None and not force:
        fetched_at, cached = _cache
        ttl = _TTL_PLAYING_S if cached.get("is_playing") else _TTL_IDLE_S
        if now - fetched_at < ttl:
            return cached

    fresh = _fetch_snapshot()

    # A transient failure should not blank a populated panel. Keep serving the
    # last good snapshot and say so, rather than throwing the track away
    # because one poll timed out.
    if fresh["status"] in ("unreachable", "rate_limited") and _cache is not None:
        stale = dict(_cache[1])
        stale["degraded"] = fresh["status"]
        # Do not re-cache: the next request should try Spotify again (the rate
        # limiter short-circuits that on its own).
        return stale

    _cache = (now, fresh)
    return fresh


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------

# The four the panel exposes, plus "restart", which only voice uses.
#
# `restart` is a seek to zero, NOT the previous-track call. Spotify's
# /previous is device-dependent -- some clients restart the current track when
# you are a few seconds in, others always go back one -- so "start this song
# again" gets an endpoint that does exactly that and nothing else. The panel
# still has no scrubber: the progress bar is a readout (USER DECISION
# 2026-10-16), and seeking to a fixed 0 is not scrubbing.
_COMMANDS = {
    "previous": ("POST", "/me/player/previous", None),
    "next": ("POST", "/me/player/next", None),
    "play": ("PUT", "/me/player/play", None),
    "pause": ("PUT", "/me/player/pause", None),
    "restart": ("PUT", "/me/player/seek", {"position_ms": 0}),
}


def command(action: str) -> dict:
    """Run a playback command. Returns {"status": ...} like `snapshot`.

    Extra statuses here:
      no_device         nothing is playing anywhere, so there is nothing to
                        control -- the API cannot start audio by itself
      premium_required  the account is not Premium; reads work, writes do not
      unsupported       not one of the known commands
    """
    if action == "toggle":
        action = "pause" if snapshot().get("is_playing") else "play"

    if action not in _COMMANDS:
        return {"status": "unsupported"}

    if not is_configured():
        return {"status": "unconfigured"}
    if not is_connected():
        return {"status": "unauthorized"}

    method, path, query = _COMMANDS[action]
    status, _ = _authed_call(method, path, query)

    # The snapshot is now wrong whatever happened, and the UI refetches right
    # after a tap. Clearing beats caching a stale is_playing for 3 seconds.
    _invalidate()

    if status in (200, 202, 204):
        return {"status": "ok", "action": action}
    if status == 404:
        return {"status": "no_device"}
    if status == 403:
        # 403 is also what a free account gets for any write. The message in
        # the body distinguishes them, but not reliably enough to branch on.
        return {"status": "premium_required"}
    if status == 401:
        return {"status": "unauthorized"}
    if status == 429:
        return {"status": "rate_limited"}
    if status == 0:
        return {"status": "unreachable"}
    return {"status": "unreachable", "http": status}


# ---------------------------------------------------------------------------
# album art proxy
# ---------------------------------------------------------------------------

def fetch_art(image_id: str) -> Optional[tuple[bytes, str]]:
    """Fetch one cover by id. Returns (bytes, content_type) or None.

    The id is validated as alphanumeric before it is pasted into the CDN URL,
    so this cannot be pointed at another host. No Spotify auth is involved:
    cover images are public.
    """
    if not image_id.isalnum() or not 8 <= len(image_id) <= 120:
        return None

    req = urllib.request.Request(f"{_IMAGE_HOST}{image_id}",
                                 headers={"Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S,
                                    context=_ssl_context()) as resp:
            if resp.status != 200:
                return None
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            if not content_type.startswith("image/"):
                return None
            return resp.read(), content_type
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError) as exc:
        log.warning("Cover art %s failed: %s", image_id, exc)
        return None
