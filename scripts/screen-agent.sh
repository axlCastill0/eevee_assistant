#!/usr/bin/env bash
# Turn the Pi's screen on and off, following the dashboard's state.
#
# WHY THIS EXISTS
#   The backlight is a host device. The dashboard runs in a browser and the
#   backend runs in a container, and neither can touch it -- a black overlay
#   in the UI hides the picture but leaves the panel lit, which in a dark room
#   is exactly as bright as before. This script is the piece that actually
#   switches it.
#
# WHERE IT RUNS
#   Inside the kiosk session on the Pi, as the same user, because two of the
#   three methods below need the session's display (WAYLAND_DISPLAY or
#   DISPLAY). Start it next to kiosk.sh; see docs/README_PI.md.
#
# HOW IT TALKS TO THE BACKEND
#   It polls the dashboard's own nginx, which injects the API key server-side,
#   so this script holds no secret. Point it straight at the backend instead
#   (SCREEN_AGENT_URL=http://127.0.0.1:8000/screen) and you must also set
#   SCREEN_AGENT_KEY, because the backend itself requires the header.
set -uo pipefail

URL="${SCREEN_AGENT_URL:-http://127.0.0.1:8080/api/screen}"
INTERVAL="${SCREEN_AGENT_INTERVAL:-2}"
KEY="${SCREEN_AGENT_KEY:-}"

log() { printf '%s screen-agent: %s\n' "$(date '+%H:%M:%S')" "$*"; }

# --- pick a method, once, at startup ---------------------------------------
# In order of how directly each one controls the actual backlight:
#
#   1. sysfs bl_power  — the REAL backlight switch, and the only method here
#      that physically darkens a DSI panel (the official touchscreen and its
#      clones). 0 = on, 1 = off, per the Pi's own backlight driver.
#   2. wlopm           — Wayland output power management (labwc, wayfire).
#      Proper DPMS off; preferred over wlr-randr, which disables the output
#      rather than powering it down.
#   3. wlr-randr       — the fallback for Wayland sessions without wlopm.
#   4. xset dpms       — the X11 (i3) equivalent.
#   5. vcgencmd        — LEGACY, and DEAD ON A PI 5: the firmware refuses
#      `display_power` whenever vc4-kms-v3d is in use, which is always on a
#      Pi 5. Kept only for older boards.
#
# ON AN HDMI PANEL, methods 2-4 cut the video signal and the monitor decides
# what to do about it. A real monitor goes to standby and goes dark; a cheap
# driver board may keep its LED backlight lit regardless, and no software on
# the Pi can change that -- cutting the panel's power is the only fix. A DSI
# panel has no such ambiguity, which is why the sysfs method is first.
#
# Detection is deliberate rather than "try everything": a panel that supports
# two of these would otherwise get contradictory instructions.
BACKLIGHT=""
for candidate in /sys/class/backlight/*/bl_power; do
    [ -e "${candidate}" ] || continue
    BACKLIGHT="${candidate}"
    break
done

METHOD=""
if [ -n "${BACKLIGHT}" ] && [ -w "${BACKLIGHT}" ]; then
    METHOD="sysfs"
elif [ -n "${BACKLIGHT}" ]; then
    # The file exists but this user cannot write it. Say so loudly with the
    # fix, rather than silently falling back to something coarser.
    log "WARNING: ${BACKLIGHT} is not writable by $(id -un)."
    log "         Add the udev rule from docs/README_PI.md, or run: sudo usermod -aG video $(id -un)"
fi

if [ -z "${METHOD}" ] && [ -n "${WAYLAND_DISPLAY:-}" ] && command -v wlopm >/dev/null; then
    METHOD="wlopm"
fi

if [ -z "${METHOD}" ] && [ -n "${WAYLAND_DISPLAY:-}" ] && command -v wlr-randr >/dev/null; then
    METHOD="wlr-randr"
    OUTPUT="$(wlr-randr --json 2>/dev/null | sed -n 's/.*"name": "\([^"]*\)".*/\1/p' | head -1)"
    [ -z "${OUTPUT}" ] && OUTPUT="$(wlr-randr 2>/dev/null | awk 'NR==1{print $1}')"
fi

if [ -z "${METHOD}" ] && [ -n "${DISPLAY:-}" ] && command -v xset >/dev/null; then
    METHOD="xset"
fi

if [ -z "${METHOD}" ] && command -v vcgencmd >/dev/null; then
    METHOD="vcgencmd"
    if grep -q "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null; then
        log "WARNING: falling back to vcgencmd on a Pi 5, where the firmware"
        log "         refuses display_power under vc4-kms-v3d. This will NOT"
        log "         switch your screen. Install wlopm (Wayland) or"
        log "         x11-xserver-utils (X11), or check that"
        log "         /sys/class/backlight is populated -- on Pi OS Lite that"
        log "         needs dtoverlay=rpi-backlight in /boot/firmware/config.txt."
    fi
fi

if [ -z "${METHOD}" ]; then
    log "no way to control this display found. Tried: sysfs backlight, wlr-randr, xset, vcgencmd."
    log "the dashboard will still black itself out; the backlight will stay on."
    exit 1
fi


apply() {
    local want="$1"      # on | off
    case "${METHOD}" in
        sysfs)
            # 1 = off, 0 = on. The Pi's backlight driver documents these two
            # and nothing else; 4 (FB_BLANK_POWERDOWN) happens to work on
            # some drivers and is silently ignored by others, which is a very
            # good way to end up with a panel that is "off" but still lit.
            [ "${want}" = "on" ] && echo 0 > "${BACKLIGHT}" || echo 1 > "${BACKLIGHT}"
            ;;
        wlopm)
            [ "${want}" = "on" ] && wlopm --on '"'"'*'"'"' >/dev/null 2>&1 \
                                 || wlopm --off '"'"'*'"'"' >/dev/null 2>&1
            ;;
        wlr-randr)
            wlr-randr --output "${OUTPUT}" --"${want}" >/dev/null 2>&1
            ;;
        xset)
            if [ "${want}" = "on" ]; then
                xset dpms force on
            else
                # force off alone is undone by the next input event on some
                # setups; setting the timeouts to 0 first stops X putting it
                # straight back.
                xset s off -dpms
                xset dpms force off
            fi
            ;;
        vcgencmd)
            [ "${want}" = "on" ] && vcgencmd display_power 1 >/dev/null \
                                 || vcgencmd display_power 0 >/dev/null
            ;;
    esac
}

if [ "${1:-}" = "--test" ]; then
    log "using ${METHOD}${BACKLIGHT:+ (${BACKLIGHT})}${OUTPUT:+ (${OUTPUT})}"
    log "turning the screen OFF for 5 seconds -- watch the panel"
    apply off
    sleep 5
    apply on
    log "back on. If the panel stayed lit, this method does not control its"
    log "backlight; see 'The screen agent' in docs/README_PI.md."
    exit 0
fi

log "using ${METHOD}${BACKLIGHT:+ (${BACKLIGHT})}${OUTPUT:+ (${OUTPUT})}, polling ${URL} every ${INTERVAL}s"

# Start from a known state, so the panel and the backend agree before the
# first change rather than after it.
current=""

# Report a persistent failure ONCE rather than every two seconds, but do
# report it: an agent that polls a 401 forever looks exactly like an agent
# that is working, right up until the screen does not turn off.
complained=""

while true; do
    # --max-time keeps a hung backend from stalling the loop forever. The
    # HTTP status comes back on its own line so a 401 can be told apart from
    # "the backend is not up yet".
    response="$(curl -sS --max-time 3 -w '\n%{http_code}' \
                     ${KEY:+-H "X-API-Key: ${KEY}"} "${URL}" 2>/dev/null || true)"
    code="${response##*$'\n'}"
    body="${response%$'\n'*}"

    case "${body}" in
        *'"on":true'*|*'"on": true'*)   want="on" ;;
        *'"on":false'*|*'"on": false'*) want="off" ;;
        *)
            if [ "${complained}" != "${code}" ]; then
                case "${code}" in
                    401|403) log "backend rejected the request (${code}). Point this at the ui's nginx (/api/screen), which adds the key, or set SCREEN_AGENT_KEY." ;;
                    000|"")  log "cannot reach ${URL}. Waiting." ;;
                    *)       log "unexpected reply from ${URL} (HTTP ${code}). Waiting." ;;
                esac
                complained="${code}"
            fi
            # Deliberately do NOT touch the screen: blanking it because the
            # API is unreachable would hide the very dashboard that reports
            # the outage.
            sleep "${INTERVAL}"
            continue
            ;;
    esac

    if [ -n "${complained}" ]; then
        log "backend reachable again"
        complained=""
    fi

    if [ "${want}" != "${current}" ]; then
        log "-> ${want}"
        apply "${want}"
        current="${want}"
    fi

    sleep "${INTERVAL}"
done
