"""Host readings — uptime and SoC temperature.

WHY THIS WORKS FROM INSIDE A CONTAINER
    Both of these read pseudo-files that Docker passes through from the host:
    `/proc/uptime` is the host's uptime (containers do not get their own), and
    `/sys/class/thermal/*` is the host's thermal zones, mounted read-only by
    default. Neither needs a bind mount, a privileged container, or vcgencmd.

    The catch is that neither is guaranteed. A non-Pi host may have no thermal
    zone at all, and a hardened runtime may hide /sys. Every reader here
    returns None rather than raising, and the intent handler turns that into a
    sentence that admits it instead of inventing a number.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("sysinfo")

_UPTIME = Path("/proc/uptime")

# Preferred first. On a Pi 5 under Raspberry Pi OS the SoC sensor is
# thermal_zone0, but the index is not contractual, so the type file is checked
# before trusting it.
_THERMAL_ROOT = Path("/sys/class/thermal")
_SOC_ZONE_TYPES = ("cpu-thermal", "soc_thermal", "bcm2835_thermal", "x86_pkg_temp")


def uptime_seconds() -> Optional[float]:
    """Host uptime in seconds, or None if it cannot be read."""
    try:
        return float(_UPTIME.read_text().split()[0])
    except (OSError, ValueError, IndexError) as exc:
        log.debug("Could not read uptime: %s", exc)
        return None


def cpu_temp_c() -> Optional[float]:
    """SoC temperature in degrees Celsius, or None if no sensor is readable."""
    try:
        zones = sorted(_THERMAL_ROOT.glob("thermal_zone*"))
    except OSError as exc:
        log.debug("No thermal zones: %s", exc)
        return None

    # A known SoC sensor wins; otherwise fall back to the first zone that
    # reads a plausible value. Guessing wrong here means reporting the
    # temperature of something that is not the processor.
    preferred, fallback = [], []
    for zone in zones:
        try:
            kind = (zone / "type").read_text().strip()
        except OSError:
            kind = ""
        (preferred if kind in _SOC_ZONE_TYPES else fallback).append(zone)

    for zone in preferred + fallback:
        try:
            milli = int((zone / "temp").read_text().strip())
        except (OSError, ValueError):
            continue

        celsius = milli / 1000.0
        # Sanity bound. A zone reporting 0 or 200 is a sensor that is not
        # measuring a running processor, and saying so out loud is worse than
        # saying nothing.
        if 5.0 <= celsius <= 120.0:
            return celsius

    log.debug("No thermal zone produced a plausible reading")
    return None


def human_duration(seconds: float) -> str:
    """Spoken-length duration: '3 days, 4 hours', '12 minutes'.

    Deliberately coarse. This is read aloud, and "3 days, 4 hours, 11 minutes
    and 6 seconds" is not an answer anyone wanted.
    """
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60

    def unit(n: int, name: str) -> str:
        return f"{n} {name}" if n == 1 else f"{n} {name}s"

    if days:
        return f"{unit(days, 'day')}, {unit(hours, 'hour')}" if hours else unit(days, "day")
    if hours:
        return f"{unit(hours, 'hour')}, {unit(minutes, 'minute')}" if minutes else unit(hours, "hour")
    if minutes:
        return unit(minutes, "minute")
    return "less than a minute"
