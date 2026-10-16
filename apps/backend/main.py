import logging
import os

from fastapi import FastAPI, Depends

try:
    from dotenv import load_dotenv

    load_dotenv()  # load .env from cwd if present (local dev)
except ImportError:
    pass

from auth import require_api_key
from routes import clock, screen, spotify, status, voice, wake, weather

# Uvicorn configures its own loggers but not the root logger, so module-level
# loggers (routes.voice, intents) would otherwise be silent.
logging.basicConfig(
    level=logging.DEBUG if os.environ.get("BACKEND_VERBOSE") else logging.INFO,
    format="%(asctime)s [%(name)-12s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="Eevee Assistant Backend")

app.include_router(voice.router, prefix="/voice", tags=["voice"])
# Separate router: the WebSocket authenticates by hand, because the HTTP
# router's require_api_key dependency raises HTTPException, which cannot be
# delivered over a socket. See routes/voice.py.
app.include_router(voice.ws_router, prefix="/voice", tags=["voice"])
# No prefix: /services is system-wide, not scoped to a subsystem.
app.include_router(status.router, tags=["status"])

# Timers, alarms, settings and the sound library. One prefix because the
# dashboard polls them as one state object; see routes/clock.py.
app.include_router(clock.router, prefix="/clock", tags=["clock"])

# Polled by scripts/screen-agent.sh on the host, which is the only thing that
# can actually switch a backlight. See screen.py.
app.include_router(screen.router, prefix="/screen", tags=["screen"])

app.include_router(spotify.router, prefix="/spotify", tags=["spotify"])
# Keyless, and only the OAuth callback: Spotify redirects a browser there and
# that browser has no API key. Protected by the single-use state minted by the
# key-protected /spotify/login instead. See routes/spotify.py.
app.include_router(spotify.public_router, prefix="/spotify", tags=["spotify"])

# Its own route rather than a field on /clock/state: a cache miss here blocks
# on the network, and that poll is the one that rings alarms. See
# routes/weather.py.
app.include_router(weather.router, prefix="/weather", tags=["weather"])

# Wake-on-LAN. Works ONLY because the backend runs with network_mode: host --
# a bridged container's broadcast never reaches the LAN. See wol.py.
app.include_router(wake.router, prefix="/wake", tags=["wake"])

@app.get("/", dependencies=[Depends(require_api_key)])
def root():
    return {"status": "ok", "service": "eevee-assistant-backend"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
