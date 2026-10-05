"""Command recording stage.

After the wake word fires, capture audio until the VAD reports
SILENCE_TIMEOUT_MS of continuous non-speech, or MAX_RECORDING_MS is reached.
"""
import logging
from collections import deque

import numpy as np
import sounddevice as sd

from . import config
from .helpers import downsample_mic
from .vad import SileroVAD

log = logging.getLogger("recorder")


class CommandRecorder:
    """Holds the pre-roll buffer and runs VAD-driven recording."""

    def __init__(self, vad: SileroVAD):
        self.vad = vad

        # Pre-roll holds whole frames rather than individual samples. The
        # original per-sample deque called ndarray.tolist() on every 80 ms
        # frame, which allocates 1280 Python ints each time — real cost on a
        # Pi when it runs forever. Frames are cheap: one append, no conversion.
        frame_samples = config.WW_NATIVE_FRAME // config.DOWNSAMPLE   # 1280
        max_frames = (config.PRE_ROLL_SAMPLES + frame_samples - 1) // frame_samples
        self.pre_roll: deque[np.ndarray] = deque(maxlen=max(1, max_frames))

    def feed_pre_roll(self, chunk_16k: np.ndarray) -> None:
        """Call on every wake-word frame to keep the pre-roll fresh.

        `chunk_16k` must already be a copy (downsample_mic guarantees that);
        storing a view of a reused sounddevice buffer would corrupt the
        pre-roll in place.
        """
        self.pre_roll.append(chunk_16k)

    def clear_pre_roll(self) -> None:
        self.pre_roll.clear()

    def _pre_roll_audio(self) -> np.ndarray:
        """Flatten the pre-roll, trimmed to exactly PRE_ROLL_SAMPLES."""
        if not self.pre_roll:
            return np.empty(0, dtype=np.int16)
        joined = np.concatenate(self.pre_roll)
        return joined[-config.PRE_ROLL_SAMPLES:]

    def record(self, stream: sd.RawInputStream) -> tuple[np.ndarray, bool]:
        """Record until the VAD reports silence.

        Returns (audio_16k, speech_seen). `audio_16k` is int16 PCM at
        MODEL_RATE including the pre-roll. When `speech_seen` is False the
        caller must skip STT — Whisper hallucinates words on pure silence.
        """
        pre_roll = self._pre_roll_audio()
        buffer: list[np.ndarray] = [pre_roll] if len(pre_roll) else []
        total_samples = len(pre_roll)
        silence_samples = 0
        speech_seen = False
        overflows = 0

        self.vad.reset()

        while total_samples < config.MAX_RECORDING_SAMPLES:
            chunk_bytes, overflowed = stream.read(config.VAD_NATIVE_FRAME)
            if overflowed:
                # The pipeline fell behind the mic; samples were dropped. Not
                # fatal for a command capture, but worth counting.
                overflows += 1

            chunk_native = np.frombuffer(chunk_bytes, dtype=np.int16)
            chunk_16k = downsample_mic(chunk_native)

            buffer.append(chunk_16k)
            total_samples += len(chunk_16k)

            if self.vad(chunk_16k) >= config.VAD_SPEECH_THRESHOLD:
                silence_samples = 0
                speech_seen = True
            else:
                silence_samples += len(chunk_16k)

            if (speech_seen
                    and silence_samples >= config.SILENCE_TIMEOUT_SAMPLES
                    and total_samples >= config.MIN_RECORDING_SAMPLES):
                break

        if overflows:
            log.warning("%d input overflow(s) during capture", overflows)

        audio = np.concatenate(buffer) if buffer else np.empty(0, dtype=np.int16)
        log.debug("Recorded %.2fs (speech_seen=%s)",
                  len(audio) / config.MODEL_RATE, speech_seen)
        return audio, speech_seen
