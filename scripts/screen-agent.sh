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
#   1. sysfs bl_power  — the real backlight switch on a DSI panel (the
#      official 7" touchscreen and most DSI clones). 0 = on, 4 = off.
#   2. wlr-randr       — Wayland (labwc). Powers the output down; on an HDMI
#      monitor this is what makes it sleep.
#   3. xset dpms       — the X11 (i3) equivalent.
#   4. vcgencmd        — Pi-specific HDMI power. Last because it is the
#      coarsest and needs /dev/vcio.
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
fi

if [ -z "${METHOD}" ]; then
    log "no way to control this display found. Tried: sysfs backlight, wlr-randr, xset, vcgencmd."
    log "the dashboard will still black itself out; the backlight will stay on."
    exit 1
fi

log "using ${METHOD}${BACKLIGHT:+ (${BACKLIGHT})}${OUTPUT:+ (${OUTPUT})}, polling ${URL} every ${INTERVAL}s"

apply() {
    local want="$1"      # on | off
    case "${METHOD}" in
        sysfs)
            # 4 is FB_BLANK_POWERDOWN. Writing 1-3 dims on some panels and
            # does nothing on others; 4 is the one that is actually off.
            [ "${want}" = "on" ] && echo 0 > "${BACKLIGHT}" || echo 4 > "${BACKLIGHT}"
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
