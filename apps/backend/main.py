import logging
import os

from fastapi import FastAPI, Depends

try:
    from dotenv import load_dotenv

    load_dotenv()  # load .env from cwd if present (local dev)
except ImportError:
    pass

from auth import require_api_key
from routes import voice

# Uvicorn configures its own loggers but not the root logger, so module-level
# loggers (routes.voice, intents) would otherwise be silent.
logging.basicConfig(
    level=logging.DEBUG if os.environ.get("BACKEND_VERBOSE") else logging.INFO,
    format="%(asctime)s [%(name)-12s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="Eevee Assistant Backend")

app.include_router(voice.router, prefix="/voice", tags=["voice"])

@app.get("/", dependencies=[Depends(require_api_key)])
def root():
    return {"status": "ok", "service": "eevee-assistant-backend"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
