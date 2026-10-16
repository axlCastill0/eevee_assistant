"""Card lookups straight from ALSA, without /proc.

WHY THIS EXISTS
    A udev rule pins each card's ALSA *id* (eeveemic, eeveespk). Mapping that
    id to the card NUMBER that appears in PortAudio's device names ("USB
    Microphone: Audio (hw:0,0)") is the whole job.

    The obvious source is /proc/asound -- and it works on the host. It does
    NOT work in the container: /proc/asound is on the container runtime's
    DEFAULT MASKED PATHS list, so Docker mounts an empty tmpfs over it. The
    directory exists and is empty, which surfaces as
    `No such file or directory: '/proc/asound/cards'` while `cat
    /proc/asound/cards` on the host prints every card. Confirmed on the Pi,
    2026-10-16.

    So ask libasound instead. snd_card_get_index() and the control interface
    go through ioctls on /dev/snd/controlC*, which the container already has
    mounted for the audio hardware itself. No /proc, no extra privilege, and
    no new package: libasound2 is already present because libportaudio2 links
    against it.

    /proc is kept as a fallback for bare-metal runs where, for whatever
    reason, libasound cannot be loaded.
"""
from __future__ import annotations

import ctypes
import logging
import os
from typing import Optional

log = logging.getLogger("alsa")

# Try the versioned soname first: a slim image ships the runtime library but
# not the -dev symlink, so plain "libasound.so" is often absent.
_CANDIDATES = ("libasound.so.2", "libasound.so")

_lib: Optional[ctypes.CDLL] = None
_tried = False


def _libasound() -> Optional[ctypes.CDLL]:
    global _lib, _tried
    if _tried:
        return _lib

    _tried = True
    for name in _CANDIDATES:
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            continue

        # Return types matter: ctypes assumes int, which truncates the
        # pointers these return on a 64-bit build.
        lib.snd_card_get_index.argtypes = [ctypes.c_char_p]
        lib.snd_card_get_index.restype = ctypes.c_int
        lib.snd_card_next.argtypes = [ctypes.POINTER(ctypes.c_int)]
        lib.snd_card_next.restype = ctypes.c_int
        lib.snd_ctl_open.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_int]
        lib.snd_ctl_open.restype = ctypes.c_int
        lib.snd_ctl_close.argtypes = [ctypes.c_void_p]
        lib.snd_ctl_close.restype = ctypes.c_int
        lib.snd_ctl_card_info_sizeof.restype = ctypes.c_size_t
        lib.snd_ctl_card_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.snd_ctl_card_info.restype = ctypes.c_int
        lib.snd_ctl_card_info_get_id.argtypes = [ctypes.c_void_p]
        lib.snd_ctl_card_info_get_id.restype = ctypes.c_char_p
        lib.snd_ctl_card_info_get_name.argtypes = [ctypes.c_void_p]
        lib.snd_ctl_card_info_get_name.restype = ctypes.c_char_p

        _lib = lib
        return _lib

    log.debug("libasound not loadable; falling back to /proc/asound")
    return None


def card_index(card_id: str) -> Optional[int]:
    """Card number for an ALSA card id, or None if there is no such card.

    Tries libasound first because it is the only source that works inside the
    container.
    """
    lib = _libasound()
    if lib is not None:
        index = lib.snd_card_get_index(card_id.encode())
        if index >= 0:
            return index
        # A negative return is -ENODEV etc: the library works, the card is
        # simply not there. Still fall through to /proc, which costs nothing
        # and covers a host where the two disagree.

    return _card_index_from_proc(card_id)


def _card_index_from_proc(card_id: str) -> Optional[int]:
    """The /proc route. Works on the host, masked to empty in the container."""
    link = f"/proc/asound/{card_id}"
    if os.path.islink(link):
        target = os.path.basename(os.path.realpath(link))   # "card0"
        if target.startswith("card") and target[4:].isdigit():
            return int(target[4:])

    try:
        with open("/proc/asound/cards") as fh:
            for line in fh:
                # Only the index line carries brackets; the name line follows.
                if "[" not in line:
                    continue
                number, _, rest = line.strip().partition(" ")
                name = rest.partition("[")[2].partition("]")[0].strip()
                if name == card_id and number.isdigit():
                    return int(number)
    except OSError:
        pass

    return None


def list_cards() -> list[tuple[int, str, str]]:
    """Every card as (index, id, name). Empty if ALSA cannot be queried.

    Uses the control interface rather than /proc for the same reason as
    above: this is what the container can actually see.
    """
    lib = _libasound()
    if lib is None:
        return _list_cards_from_proc()

    cards: list[tuple[int, str, str]] = []
    info = ctypes.create_string_buffer(lib.snd_ctl_card_info_sizeof())
    index = ctypes.c_int(-1)

    while lib.snd_card_next(ctypes.byref(index)) == 0 and index.value >= 0:
        ctl = ctypes.c_void_p()
        if lib.snd_ctl_open(ctypes.byref(ctl), f"hw:{index.value}".encode(), 0) < 0:
            continue
        try:
            if lib.snd_ctl_card_info(ctl, info) == 0:
                card_id = (lib.snd_ctl_card_info_get_id(info) or b"").decode()
                name = (lib.snd_ctl_card_info_get_name(info) or b"").decode()
                cards.append((index.value, card_id, name))
        finally:
            lib.snd_ctl_close(ctl)

    return cards or _list_cards_from_proc()


def _list_cards_from_proc() -> list[tuple[int, str, str]]:
    cards: list[tuple[int, str, str]] = []
    try:
        with open("/proc/asound/cards") as fh:
            for line in fh:
                if "[" not in line:
                    continue
                number, _, rest = line.strip().partition(" ")
                card_id = rest.partition("[")[2].partition("]")[0].strip()
                name = rest.partition("]:")[2].strip()
                if number.isdigit():
                    cards.append((int(number), card_id, name))
    except OSError:
        pass
    return cards


def describe_cards() -> str:
    """Cards as a readable block, for error messages and the device lister."""
    cards = list_cards()
    if not cards:
        return ("  (none -- libasound could not be queried and /proc/asound is "
                "empty, which is what a container's masked /proc looks like)")
    return "\n".join(f"  {i} [{card_id}] {name}" for i, card_id, name in cards)
