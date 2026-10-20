"""Wake-on-LAN for one machine on the LAN.

WHAT THIS IS
    A magic packet sender and a liveness probe, for the PC sitting next to
    the Pi. One target, configured in the environment (USER DECISION
    2026-10-16) -- there is no keyboard on this panel, so a MAC address was
    never going to be typed into Settings, and this is set once.

WHY THE BACKEND CAN DO THIS AT ALL
    `network_mode: host` in infra/docker/docker-compose.yml. A bridged
    container cannot put a broadcast on the LAN -- the packet would die at
    the docker0 interface and the PC would never see it. Host networking is
    already the project-wide convention on this Pi for other reasons, and it
    is load-bearing here. IF THE BACKEND IS EVER MOVED OFF HOST NETWORKING,
    THIS STOPS WORKING SILENTLY: the send succeeds, nothing wakes.

WHY NO DEPENDENCY
    A magic packet is six 0xFF bytes followed by the target MAC sixteen
    times. That is two lines; `wakeonlan` would be a dependency for a
    constant. Same reasoning as urllib in weather.py.

THE PROBE
    WoL is fire-and-forget by design: nothing acknowledges a magic packet. To
    tell you whether the PC actually came up, the backend opens a TCP
    connection to a port the machine listens on when awake (3389 for Windows
    RDP by default) and reports whether it connected.

    ICMP would be the obvious choice and is deliberately not used: a raw
    socket needs CAP_NET_RAW, which means either a privileged container or a
    setuid ping binary in the image. A TCP connect needs neither.

    Cached, because the dashboard polls: the probe costs a connect() with a
    timeout, and a panel left open would otherwise knock on that port once a
    second forever.
"""
from __future__ import annotations

import logging
import os
import re
import socket
import time
from typing import Optional

log = logging.getLogger("wol")

# Discard protocol. Nothing listens on it; the packet is read by the NIC's
# firmware, not by any program, so the port is conventional rather than
# meaningful. 7 and 0 are equally common.
DEFAULT_PORT = 9

# Ports tried, in order, until one answers. A LIST rather than one port
# (2026-10-19): 3389 only exists if Remote Desktop is enabled, and a PC that
# was plainly awake read as offline for exactly that reason.
#   3389 Windows Remote Desktop   445/139 Windows file sharing
#   22   ssh                      5900 VNC
# Override with WOL_PROBE_PORT, which takes a comma-separated list.
DEFAULT_PROBE_PORTS = (3389, 445, 139, 22)
_PROBE_TIMEOUT_S = 0.6             # a LAN machine answers in single-digit ms
_PROBE_TTL_S = 5.0
# Worst case per probe is len(ports) * _PROBE_TIMEOUT_S, and only while the
# machine is down; a single answer ends the sweep.
_MAX_PROBE_PORTS = 4

# Accepts aa:bb:cc:dd:ee:ff, aa-bb-..., and bare aabbccddeeff.
_MAC_RE = re.compile(r"^([0-9a-f]{2}[:-]?){5}[0-9a-f]{2}$", re.IGNORECASE)

# (checked_at, online). Monotonic, like everything else here that measures an
# interval -- the Pi has no RTC and steps its wall clock at boot.
_probe_cache: Optional[tuple[float, bool]] = None


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def mac() -> str:
    return _env("WOL_MAC")


def name() -> str:
    """What the machine is called, in speech and on screen."""
    return _env("WOL_NAME", "the computer") or "the computer"


def is_configured() -> bool:
    return bool(_MAC_RE.match(mac()))


def _packet(raw_mac: str) -> bytes:
    clean = raw_mac.replace(":", "").replace("-", "")
    return b"\xff" * 6 + bytes.fromhex(clean) * 16


def send() -> tuple[bool, str]:
    """Broadcast the magic packet. Returns (sent, detail).

    `detail` is a sentence, because both callers -- the panel and the voice
    assistant -- need to tell a person what happened, and wording it twice is
    how the two drift apart. Same rule as services.summarize().
    """
    if not is_configured():
        return False, "no machine is configured to wake"

    broadcast = _env("WOL_BROADCAST", "255.255.255.255") or "255.255.255.255"
    try:
        port = int(_env("WOL_PORT") or DEFAULT_PORT)
    except ValueError:
        log.warning("WOL_PORT is not a number; using %s", DEFAULT_PORT)
        port = DEFAULT_PORT

    try:
        payload = _packet(mac())
    except ValueError:
        # Matched the regex but is not valid hex -- shouldn't happen, but a
        # bad .env should not take the route down.
        log.error("WOL_MAC %r is not a usable MAC address", mac())
        return False, "the configured MAC address is not valid"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Sent three times. A single UDP broadcast is allowed to be
            # dropped by any switch on the way and nothing retransmits it;
            # three costs nothing and makes a missed wake much rarer.
            for _ in range(3):
                sock.sendto(payload, (broadcast, port))
    except OSError as exc:
        # Most likely cause by far: the backend is NOT on host networking.
        log.error("Could not send the magic packet to %s:%s: %s",
                  broadcast, port, exc)
        return False, "the wake packet could not be sent"

    log.info("Magic packet sent to %s via %s:%s", mac(), broadcast, port)

    # The machine is booting, so whatever the probe last said is now stale.
    global _probe_cache
    _probe_cache = None

    return True, f"waking {name()} now"


def probe_ports() -> tuple[int, ...]:
    """Ports to try, from WOL_PROBE_PORT. Junk entries are dropped."""
    raw = _env("WOL_PROBE_PORT") or ""
    ports: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            port = int(part)
        except ValueError:
            log.warning("WOL_PROBE_PORT entry %r is not a number; ignoring", part)
            continue
        if 1 <= port <= 65535:
            ports.append(port)

    return tuple(ports[:_MAX_PROBE_PORTS]) or DEFAULT_PROBE_PORTS


def _answered(host: str, port: int) -> bool:
    """Did anything at `host:port` respond at all?

    A CONNECTION REFUSED COUNTS AS AWAKE. Something has to be running a TCP
    stack to send that reset, so the machine is up and only the port is shut
    -- which is the common case on a PC with a firewall and no listener. Only
    silence (a timeout) or "no route" mean asleep.
    """
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_S):
            return True
    except ConnectionRefusedError:
        return True
    except OSError:
        # Timed out, host unreachable, DNS failure. All of them read the same
        # to the person looking at the panel: not reachable.
        return False


def online(force: bool = False) -> Optional[bool]:
    """True/False if a probe target is configured, None if it is not.

    Cached for `_PROBE_TTL_S`; `force` ignores the cache.
    """
    host = _env("WOL_HOST")
    if not host:
        return None

    global _probe_cache
    now = time.monotonic()
    if not force and _probe_cache is not None and now - _probe_cache[0] < _PROBE_TTL_S:
        return _probe_cache[1]

    was = _probe_cache[1] if _probe_cache is not None else None

    up = False
    answered_on: Optional[int] = None
    for port in probe_ports():
        if _answered(host, port):
            up, answered_on = True, port
            break

    # Logged only on a CHANGE: this runs every few seconds for as long as the
    # panel sits on the Home app, and a line per probe would be the loudest
    # thing in the log by an order of magnitude.
    if up != was:
        if up:
            log.info("%s answered on port %d", host, answered_on)
        else:
            log.info("%s is not answering on %s", host,
                     ", ".join(str(p) for p in probe_ports()))

    _probe_cache = (now, up)
    return up


def state() -> dict:
    """What the panel polls."""
    return {
        "configured": is_configured(),
        "name": name(),
        "mac": mac(),
        # None = no WOL_HOST set, so the panel says "status unknown" rather
        # than drawing a confident offline dot it has not earned.
        "online": online(),
        "probe_host": _env("WOL_HOST"),
        # Shown on the panel: when the dot is wrong, the port being tried is
        # the first thing worth knowing.
        "probe_ports": list(probe_ports()) if _env("WOL_HOST") else [],
    }
