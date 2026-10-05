"""Wake-word detection stage.

Wraps openWakeWord so the pipeline never touches the ONNX model directly.
Includes a cooldown to suppress duplicate triggers from one utterance.
"""
import logging
import os

import numpy as np

from . import config

log = logging.getLogger("wakeword")


class WakeWordDetector:
    """Detects the configured wake word in 16 kHz int16 frames.

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
        self._cap_threads()
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

    @staticmethod
    def _cap_threads() -> None:
        """Hold the always-on models to one thread each.

        Wake word and VAD run on every 80 ms / 32 ms frame forever. Their work
        is tiny, so onnxruntime's default thread fan-out costs more in handoff
        than it saves, and it steals cores from Whisper and the SLM.
        """
        n = str(config.ALWAYS_ON_THREADS)
        os.environ.setdefault("OMP_NUM_THREADS", n)
        os.environ.setdefault("ORT_NUM_THREADS", n)

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
