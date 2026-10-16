"""Score a WAV file against the configured wake-word model.

    docker compose exec voice python -m voice_assistant.wake_check clip.wav

Prints the probability and whether it crosses the threshold. The point is to
confirm the preprocessing chain here matches the one the model was trained
with: run the clips the trainer printed probabilities for, and the numbers
should land on the same side of the threshold (and be close in value).

If they do not, the unpinned conventions are the suspects, in this order:
VOICE_WW_MEL_SCALE (htk|slaney), VOICE_WW_MEL_NORM (none|slaney),
VOICE_WW_LOG_BASE (e|10). See wake_heed.MelConfig.
"""
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from . import config
from .wake_heed import HeedWakeWordDetector, is_heed_model


def load_16k_mono(path: str) -> np.ndarray:
    rate, data = wavfile.read(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if data.dtype != np.int16:
        # Floats are already [-1, 1]; other int widths scale by their own range.
        data = (data.astype(np.float64) * 32767 if np.issubdtype(data.dtype, np.floating)
                else data.astype(np.float64) / np.iinfo(data.dtype).max * 32767)
    data = data.astype(np.float64)
    if rate != 16000:
        from math import gcd
        g = gcd(int(rate), 16000)
        data = resample_poly(data, 16000 // g, int(rate) // g)
    return np.clip(data, -32768, 32767).astype(np.int16)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    model = config.WAKE_WORD_NAME
    if not is_heed_model(model):
        print(f"{model} is not a heed export (no .json sidecar); nothing to check.")
        return 2

    config.configure_logging()
    det = HeedWakeWordDetector(model)

    for path in sys.argv[1:]:
        audio = load_16k_mono(path)
        # Pad to a full window so a clip shorter than 1 s still scores, then
        # feed it as the pipeline would: 1280-sample frames.
        if len(audio) < det.cfg.window_samples:
            pad = det.cfg.window_samples - len(audio)
            audio = np.concatenate((np.zeros(pad // 2, np.int16), audio,
                                    np.zeros(pad - pad // 2, np.int16)))
        best, fired = 0.0, False
        for i in range(0, len(audio) - 1279, 1280):
            triggered, prob = det.process(audio[i:i + 1280])
            best = max(best, prob)
            fired = fired or triggered
        det.reset()
        print(f"{path}: peak prob = {best:.3f}  threshold = {det.threshold:.3f}  "
              f"triggered = {fired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
