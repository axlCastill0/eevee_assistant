"""Put apps/voice/ on sys.path so tests can import the voice_assistant package.

The package uses flat imports (`from voice_assistant.x import y`) to match how
it runs in the container, where WORKDIR is /app and the package sits directly
beneath it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
