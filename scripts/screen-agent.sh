#!/usr/bin/env bash
# Switches the Pi's display on and off, following GET /screen.
#
# This runs on the HOST, inside the kiosk session: the backlight is a host
# device, and the two compositor methods below need the session's own
# WAYLAND_DISPLAY or DISPLAY. Over SSH it has neither and will pick the wrong
# method. Start it from the session's autostart; see docs/README_PI.md.
#
# It polls through the ui's nginx, which injects the API key, so this script
# holds no secret.
set -uo pipefail

URL="${SCREEN_AGENT_URL:-http://127.0.0.1:8080/api/screen}"
INTERVAL="${SCREEN_AGENT_INTERVAL:-2}"
KEY="${SCREEN_AGENT_KEY:-}"          # only needed if URL skips nginx

log() { printf '%s screen-agent: %s\n' "$(date '+%H:%M:%S')" "$*"; }

# --- pick a method ---------------------------------------------------------
#   sysfs     a DSI panel's real backlight switch (0 = on, 1 = off)
#   wlr-randr Wayland (labwc). Powers the output down.
#   xset      the X11 equivalent.
BACKLIGHT=""
for candidate in /sys/class/backlight/*/bl_power; do
    [ -w "${candidate}" ] && BACKLIGHT="${candidate}" && break
done

METHOD=""
OUTPUT=""
if [ -n "${BACKLIGHT}" ]; then
    METHOD="sysfs"
elif [ -n "${WAYLAND_DISPLAY:-}" ] && command -v wlr-randr >/dev/null; then
    METHOD="wlr-randr"
    OUTPUT="$(wlr-randr 2>/dev/null | awk 'NR==1{print $1}')"
elif [ -n "${DISPLAY:-}" ] && command -v xset >/dev/null; then
    METHOD="xset"
fi

if [ -z "${METHOD}" ]; then
    log "no way to control this display. Need a writable /sys/class/backlight"
    log "entry, or wlr-randr with WAYLAND_DISPLAY set, or xset with DISPLAY."
    log "Running over SSH instead of inside the session is the usual cause."
    exit 1
fi

apply() {
    case "${METHOD}" in
        sysfs)     [ "$1" = on ] && echo 0 > "${BACKLIGHT}" || echo 1 > "${BACKLIGHT}" ;;
        wlr-randr) wlr-randr --output "${OUTPUT}" --"$1" >/dev/null 2>&1 ;;
        xset)      if [ "$1" = on ]; then xset dpms force on
                   else xset s off -dpms; xset dpms force off; fi ;;
    esac
}

if [ "${1:-}" = "--test" ]; then
    log "using ${METHOD}${OUTPUT:+ (${OUTPUT})}${BACKLIGHT:+ (${BACKLIGHT})}"
    log "screen off for 5 seconds -- watch the panel"
    apply off; sleep 5; apply on
    log "back on"
    exit 0
fi

log "using ${METHOD}${OUTPUT:+ (${OUTPUT})}${BACKLIGHT:+ (${BACKLIGHT})}, polling ${URL} every ${INTERVAL}s"

current=""
complained=""

while true; do
    response="$(curl -sS --max-time 3 -w '\n%{http_code}' \
                     ${KEY:+-H "X-API-Key: ${KEY}"} "${URL}" 2>/dev/null || true)"
    code="${response##*$'\n'}"
    body="${response%$'\n'*}"

    case "${body}" in
        *'"on":true'*|*'"on": true'*)   want="on" ;;
        *'"on":false'*|*'"on": false'*) want="off" ;;
        *)
            # Report a persistent failure once, not every two seconds. Never
            # touch the screen on an error: blanking it because the API is
            # unreachable would hide the dashboard reporting the outage.
            if [ "${complained}" != "${code}" ]; then
                case "${code}" in
                    401|403) log "backend rejected the request (${code}); point this at nginx (/api/screen) or set SCREEN_AGENT_KEY" ;;
                    *)       log "no answer from ${URL} (HTTP ${code:-none}); waiting" ;;
                esac
                complained="${code}"
            fi
            sleep "${INTERVAL}"
            continue
            ;;
    esac

    [ -n "${complained}" ] && log "backend reachable again" && complained=""

    if [ "${want}" != "${current}" ]; then
        log "-> ${want}"
        apply "${want}"
        current="${want}"
    fi

    sleep "${INTERVAL}"
done
