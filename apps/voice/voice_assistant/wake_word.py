"""Wake-word detection stage.

Two model formats are supported and `make_detector()` picks between them:

- a `heed` export (a .onnx with a .json sidecar beside it) -- the "hey eevee"
  model this project ships. Handled by `wake_heed`, which owns its own
  preprocessing because the model takes log-mel features directly.
- an openWakeWord model, bundled by name (`hey_jarvis`) or a plain .onnx with
  no sidecar. Handled by `WakeWordDetector` below.

Both expose the same two methods, `process(frame) -> (triggered, score)` and
`reset()`, so the pipeline never learns which one it got.
"""
import logging
import os

import numpy as np

from . import config
from .wake_heed import HeedWakeWordDetector, is_heed_model

log = logging.getLogger("wakeword")


def make_detector(wake_word_name: str = None, threshold: float = None):
    """Build the detector the configured model needs.

    `threshold` of None means "use the model's own": a heed export carries the
    threshold it was calibrated at in its sidecar, which beats any default we
    could pick here. Setting VOICE_WW_THRESHOLD overrides it.
    """
    name = config.WAKE_WORD_NAME if wake_word_name is None else wake_word_name
    if threshold is None and config.WW_THRESHOLD_IS_SET:
        threshold = config.WW_THRESHOLD

    _cap_threads()
    if is_heed_model(name):
        return HeedWakeWordDetector(name, threshold=threshold,
                                    meta_path=config.WAKE_WORD_META or None)
    return WakeWordDetector(
        name, threshold=config.WW_THRESHOLD if threshold is None else threshold)


def _cap_threads() -> None:
    """Hold the always-on models to one thread each.

    Wake word and VAD run on every 80 ms / 32 ms frame forever. Their work
    is tiny, so onnxruntime's default thread fan-out costs more in handoff
    than it saves, and it steals cores from Whisper and the SLM.

    Must run before onnxruntime is imported anywhere: it reads these at import.
    """
    n = str(config.ALWAYS_ON_THREADS)
    os.environ.setdefault("OMP_NUM_THREADS", n)
    os.environ.setdefault("ORT_NUM_THREADS", n)


class WakeWordDetector:
    """openWakeWord-backed detection in 16 kHz int16 frames.

    Frames must be exactly 1280 samples (80 ms at 16 kHz) — openWakeWord's
    melspectrogram frontend is built around that size.
    """

    # Frames to ignore after a trigger. One utterance spans several frames and
    # each would fire separately without this.
    COOLDOWN_FRAMES = 15

    def __init__(self,
                 wake_word_name: str = config.WAKE_WORD_NAME,
                 threshold: float = config.WW_THRESHOLD):
        # Import here, not at module scope: openWakeWord pulls in onnxruntime
        # and reads env vars at import time, so the thread caps below must be
        # set first.
        _cap_threads()
        from openwakeword.model import Model as OWWModel

        self.threshold = threshold
        self._cooldown = 0

        # A path means a custom-trained model; a bare name means a bundled one.
        if os.path.sep in wake_word_name or wake_word_name.endswith(".onnx"):
            if not os.path.exists(wake_word_name):
                raise FileNotFoundError(
                    f"Wake-word model not found: {wake_word_name}. "
                    "Set VOICE_WAKE_WORD to a bundled name (e.g. hey_jarvis) "
                    "or mount the .onnx file."
                )
            models = [wake_word_name]
        else:
            models = [wake_word_name]

        self.model = OWWModel(wakeword_models=models, inference_framework="onnx")
        log.info("Wake word %r loaded (threshold=%.2f)", wake_word_name, threshold)

    def process(self, chunk_16k: np.ndarray) -> tuple[bool, float]:
        """Process one 1280-sample frame. Returns (triggered, max_score)."""
        result = self.model.predict(chunk_16k)
        scores = result[0] if isinstance(result, tuple) else result
        max_score = max(scores.values()) if scores else 0.0

        if self._cooldown > 0:
            self._cooldown -= 1
            return False, max_score

        if max_score >= self.threshold:
            self._cooldown = self.COOLDOWN_FRAMES
            return True, max_score

        return False, max_score

    def reset(self) -> None:
        """Clear internal state. Call after handling a wake-word event."""
        self.model.reset()
        self._cooldown = 0
