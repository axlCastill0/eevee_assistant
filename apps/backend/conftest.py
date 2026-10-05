"""Put apps/backend/ on sys.path so tests can import the app's flat modules.

The app uses flat imports (`import services`, `from auth import ...`) to match
how it runs in the container, where WORKDIR is /app and the modules sit
directly beneath it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
