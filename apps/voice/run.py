"""Entry point for the voice assistant.

    python run.py

Configuration is environment-driven; see voice_assistant/config.py for the
full list of VOICE_* variables and their defaults.
"""
import logging
import os
import sys

# Load .env BEFORE importing anything from voice_assistant: config.py reads the
# environment at import time, so a later load_dotenv() would have no effect.
# Only used for bare-metal runs; in Docker the env comes from compose env_file.
if os.path.exists(".env"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print(".env present but python-dotenv is not installed; ignoring it",
              file=sys.stderr)

from voice_assistant.config import configure_logging  # noqa: E402
from voice_assistant.pipeline import run              # noqa: E402

log = logging.getLogger("main")


if __name__ == "__main__":
    configure_logging()
    try:
        run()
    except FileNotFoundError as exc:
        # Almost always a missing model file. Report which one; a setup problem
        # does not deserve a traceback in the container logs.
        log.error("Missing file: %s", exc)
        log.error("Run scripts/fetch-voice-models.sh and check that the models "
                  "bind mount is populated.")
        sys.exit(1)
    except RuntimeError as exc:
        # config.resolve_device raises this with the full device list attached.
        log.error("%s", exc)
        sys.exit(1)
