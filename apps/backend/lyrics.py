"""Lyrics for whatever Spotify is playing, from LRCLIB.

WHY LRCLIB
    Spotify's own lyrics are Musixmatch's and are not in the public Web API at
    all, so this is a separate lookup whatever we do. LRCLIB needs no account,
    no key and no signup, and it returns LRC -- lines with timestamps -- which
    is the whole point: an unsynced wall of text on a panel across the room is
    not worth the screen. Same reasoning as Open-Meteo in weather.py.

    Swapping provider means rewriting `_fetch`; nothing else knows where the
    lines came from.

WHY urllib
    The backend's dependency list is FastAPI, uvicorn and dotenv. One GET per
    track does not justify an HTTP client. Same as weather.py.

MATCHING
    /api/get wants artist, track, album AND duration, and is strict about the
    last one -- which is what makes it reliable when it hits. When it misses,
    /api/search is tried and a result is accepted only if its duration is
    within a few seconds of the track Spotify is actually playing. A
    confidently wrong set of lyrics scrolling past in time with the music is
    worse than none.

FAILURE POSTURE
    Never raises, short timeout, no retries. Every failure is a status the
    panel can show, and the lyrics button simply stays disabled.
"""
from __future__ import annotations

import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Optional

log = logging.getLogger("lyrics")

_ENDPOINT = "https://lrclib.net/api"

# On the path between tapping the lyrics button and seeing words. Short.
_TIMEOUT_S = 4.0

# LRCLIB asks callers to identify themselves. No user data in it.
_USER_AGENT = "eevee-assistant/0.1 (Raspberry Pi wall panel)"

# How far a /api/search result's duration may be from the track Spotify
# reports before it is rejected as a different recording.
_DURATION_SLACK_S = 4.0

# Lyrics never change, so an `ok` entry is kept for as long as it is in the
# cache. The other statuses are re-checked, because "not found" can mean the
# database simply has not got to this track yet, and "unreachable" is usually
# the network being briefly away.
_CACHE_MAX = 64
_RETRY_AFTER_S = {
    "none": 6 * 3600.0,
    "instrumental": 6 * 3600.0,
    "unreachable": 60.0,
}

_cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()

# [mm:ss.xx] or [mm:ss:xx], one or more per line.
_TAG = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]")


def _ssl_context() -> ssl.SSLContext:
    """TLS context with a CA bundle that is actually present. See weather.py
    for why this is not just the system store."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# Returned by _get for a 404. Distinct from None, which means the request
# never got an answer -- "nobody has these lyrics" is cached for hours, "the
# network was away" is retried in a minute, and conflating the two means a
# track that loses one lookup to a flaky link never gets lyrics again.
MISSING = object()


def _get(path: str, params: dict):
    """-> parsed JSON, MISSING on a 404, or None if the request failed."""
    url = f"{_ENDPOINT}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S,
                                    context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return MISSING
        log.warning("LRCLIB %s returned %d", path, exc.code)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        log.warning("LRCLIB %s failed: %s", path, exc)
    return None


def parse_lrc(lrc: str) -> list[dict]:
    """LRC text -> [{"t": seconds, "text": line}], sorted.

    A line may carry several timestamps (a chorus reused); each becomes its
    own entry. Empty lines are KEPT: in a synced file they are the instrumental
    gaps, and a view that drops them holds the last sung line on screen through
    a thirty-second solo.
    """
    out: list[dict] = []

    for raw in lrc.splitlines():
        tags = list(_TAG.finditer(raw))
        if not tags:
            continue
        text = raw[tags[-1].end():].strip()
        for tag in tags:
            seconds = float(tag.group(2).replace(":", "."))
            out.append({"t": round(int(tag.group(1)) * 60 + seconds, 2),
                        "text": text})

    out.sort(key=lambda line: line["t"])
    return out


def _from_record(record: dict) -> dict:
    """One LRCLIB record -> what the panel gets."""
    if record.get("instrumental"):
        return {"status": "instrumental"}

    synced = (record.get("syncedLyrics") or "").strip()
    if synced:
        lines = parse_lrc(synced)
        if lines:
            return {"status": "ok", "synced": True, "lines": lines}

    plain = (record.get("plainLyrics") or "").strip()
    if plain:
        # Unsynced: the view shows them as a block it cannot follow, which is
        # still worth having and is labelled as such.
        return {
            "status": "ok",
            "synced": False,
            "lines": [{"t": None, "text": line.strip()}
                      for line in plain.splitlines()],
        }

    return {"status": "none"}


def _search(track: str, artist: str, duration_s: float):
    """Fallback when the exact lookup misses, usually over a duration or a
    remaster in the album name. Same return contract as _get."""
    results = _get("search", {"track_name": track, "artist_name": artist})
    if results is None:
        return None
    if not isinstance(results, list):
        return MISSING

    best: Optional[dict] = None
    for record in results:
        try:
            delta = abs(float(record.get("duration") or 0) - duration_s)
        except (TypeError, ValueError):
            continue
        if delta > _DURATION_SLACK_S:
            continue
        # Prefer a synced record even if another is a slightly closer length:
        # being in time is the feature.
        if best is None or (record.get("syncedLyrics") and not best.get("syncedLyrics")):
            best = record

    return best if best is not None else MISSING


def _fetch(item: dict) -> dict:
    title = (item.get("title") or "").strip()
    artist = (item.get("artist") or "").strip()
    album = (item.get("album") or "").strip()
    duration_s = (item.get("duration_ms") or 0) / 1000.0

    if not title or not artist:
        return {"status": "none"}

    record = _get("get", {
        "track_name": title,
        "artist_name": artist,
        "album_name": album,
        "duration": int(round(duration_s)),
    })

    if record is MISSING:
        record = _search(title, artist, duration_s)

    if record is None:
        return {"status": "unreachable"}
    if not isinstance(record, dict):
        return {"status": "none"}

    return _from_record(record)


def lookup(item: dict) -> dict:
    """Lyrics for one now-playing item. Never raises.

    `item` is spotify.py's track payload: title, artist, album, duration_ms,
    id, kind.
    """
    track_id = item.get("id") or f"{item.get('artist')}::{item.get('title')}"

    # Podcasts have no lyrics and asking makes an episode title look like a
    # song title to the database.
    if item.get("kind") == "episode":
        return {"status": "none", "track_id": track_id}

    now = time.monotonic()
    cached = _cache.get(track_id)
    if cached is not None:
        stored_at, result = cached
        retry_after = _RETRY_AFTER_S.get(result["status"])
        if retry_after is None or now - stored_at < retry_after:
            _cache.move_to_end(track_id)
            return {**result, "track_id": track_id}

    try:
        result = _fetch(item)
    except Exception:
        # The panel polls this; an unexpected shape upstream must not become a
        # 500 on every track change.
        log.exception("Lyrics lookup failed for %r", item.get("title"))
        result = {"status": "unreachable"}

    _cache[track_id] = (now, result)
    _cache.move_to_end(track_id)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)

    if result["status"] == "ok":
        log.info("Lyrics for %r by %r: %d lines, %s",
                 item.get("title"), item.get("artist"),
                 len(result["lines"]), "synced" if result["synced"] else "plain")

    return {**result, "track_id": track_id}
