"""Dashboard settings, and the sound library behind two of them.

Three settings today: the sound a timer ends with, the sound an alarm ends
with, and the theme.

WHY THE THEME IS NOT STORED HERE
    It is deliberately NOT a server setting. A theme belongs to a display --
    a second browser on a phone should be able to be light while the wall
    panel is dark -- and the dashboard already persists it per-browser in
    localStorage, where the voice command `set_theme` also writes. Moving it
    to the server would make "dark mode" on one screen change every screen,
    which is not what anyone means by it. The Settings page shows the control
    next to the other two because that is where a person looks for it; the
    storage behind it is still the browser's.

SOUNDS
    MP3s (and wav/ogg) dropped into the media directory, which is bind-mounted
    read-only at /app/media. Nothing is uploaded through the API: putting a
    file in a folder is the simplest possible interface, and the alternative
    is an upload endpoint that has to be defended.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

log = logging.getLogger("settings")

DEFAULT_PATH = "/app/state/settings.json"
DEFAULT_MEDIA_DIR = "/app/media"

# Only what a browser will reliably play, and only formats worth the disk.
AUDIO_SUFFIXES = (".mp3", ".wav", ".ogg", ".m4a", ".flac")

_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
}

DEFAULTS = {
    # Empty means "no sound chosen yet" -- the dashboard then shows the
    # ringing banner without audio rather than guessing at a file.
    "timer_sound": "",
    "alarm_sound": "",
    # The interval timer's cue. Played at every phase start and at 3, 2 and 1
    # seconds remaining, so it wants to be SHORT -- a beep, not a song.
    "training_sound": "",
    # Minutes of no touch before the dashboard blanks the screen. "0" means
    # never. Stored as a string like everything else here; the dashboard
    # parses it, and a junk value reads as 0, which is the safe direction --
    # a panel that fails to blank beats one that blanks unpredictably.
    #
    # 30 by default (USER DECISION 2026-10-16): long enough that it never
    # blanks mid-glance, short enough that a panel left alone overnight is not
    # lighting the room. Any voice trigger wakes it again, so the cost of it
    # being wrong is one word.
    "screen_timeout_min": "30",
}

# Sound settings are validated against the media directory; this one is not a
# sound and must not be.
_SOUND_KEYS = ("timer_sound", "alarm_sound", "training_sound")


def _path() -> str:
    return os.environ.get("SETTINGS_PATH", DEFAULT_PATH)


def media_dir() -> str:
    return os.environ.get("MEDIA_DIR", DEFAULT_MEDIA_DIR)


_settings: Optional[dict] = None


def _load() -> dict:
    global _settings
    if _settings is not None:
        return _settings

    _settings = dict(DEFAULTS)
    try:
        with open(_path()) as fh:
            stored = json.load(fh)
        for key in DEFAULTS:
            if isinstance(stored.get(key), str):
                _settings[key] = stored[key]
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        log.warning("Ignoring unreadable settings file %s: %s", _path(), exc)

    return _settings


def _save() -> None:
    path = _path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as fh:
            json.dump(_load(), fh, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        log.error("Could not persist settings to %s: %s", path, exc)


def get(key: str) -> str:
    return _load().get(key, DEFAULTS.get(key, ""))


def update(values: dict) -> dict:
    """Set known keys. Unknown keys are ignored rather than stored.

    A sound is only accepted if the file is actually in the media directory --
    otherwise a typo becomes an alarm that silently does not play, discovered
    at 7am.
    """
    settings = _load()
    available = {s["file"] for s in sounds()}

    for key in DEFAULTS:
        if key not in values:
            continue
        value = str(values[key] or "")

        if key in _SOUND_KEYS:
            if value and value not in available:
                raise ValueError(
                    f"No such sound {value!r} in {media_dir()}. Available: "
                    + (", ".join(sorted(available)) or "(none)")
                )
        elif key == "screen_timeout_min":
            if value and not value.isdigit():
                raise ValueError("screen_timeout_min must be a whole number of minutes")
            value = value or "0"

        settings[key] = value

    _save()
    return dict(settings)


def sounds() -> list[dict]:
    """Every playable file in the media directory, alphabetical."""
    directory = media_dir()
    try:
        names = os.listdir(directory)
    except OSError:
        # Missing or unmounted. Not an error worth raising: the Settings page
        # says the folder is empty and tells you where to put files.
        return []

    found = []
    for name in sorted(names):
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in AUDIO_SUFFIXES:
            continue
        if not os.path.isfile(os.path.join(directory, name)):
            continue
        found.append({
            "file": name,
            # A filename is a poor label; this is the best cheap improvement.
            "label": os.path.splitext(name)[0].replace("_", " ").replace("-", " "),
        })
    return found


def resolve_sound(name: str) -> Optional[tuple[str, str]]:
    """(absolute path, content type) for a media file, or None.

    The name is matched against the directory listing rather than joined
    straight onto a path, so `../` and absolute paths cannot escape: a name
    that is not in the listing simply does not exist here.
    """
    if name not in {s["file"] for s in sounds()}:
        return None

    path = os.path.join(media_dir(), name)
    suffix = os.path.splitext(name)[1].lower()
    return path, _MIME.get(suffix, "application/octet-stream")


def state() -> dict:
    settings = dict(_load())
    settings["sounds"] = sounds()
    settings["media_dir"] = media_dir()
    return settings
