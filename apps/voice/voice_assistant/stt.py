"""Speech-to-text stage using faster-whisper (CTranslate2, no PyTorch)."""
import logging
import time

import numpy as np
from faster_whisper import WhisperModel

from . import config

log = logging.getLogger("stt")


def load_whisper() -> WhisperModel:
    """Construct a WhisperModel ready for transcription.

    The model files are baked into the image, so this does not hit the network.
    A cold load is ~0.55 s warm on a Pi 5.
    """
    t0 = time.monotonic()
    model = WhisperModel(
        config.WHISPER_SIZE,
        device="cpu",
        compute_type=config.WHISPER_COMPUTE_TYPE,
        cpu_threads=config.WHISPER_THREADS,
        local_files_only=False,   # allow a first-run download if not baked in
    )
    log.info("Whisper %s loaded in %.2fs (%d threads)",
             config.WHISPER_SIZE, time.monotonic() - t0, config.WHISPER_THREADS)
    return model


def transcribe(whisper: WhisperModel, audio_16k: np.ndarray) -> str:
    """Transcribe a 16 kHz int16 buffer. Empty string if it was all silence."""
    t0 = time.monotonic()
    audio_float = audio_16k.astype(np.float32) / 32768.0

    segments, _ = whisper.transcribe(
        audio_float,
        beam_size=config.WHISPER_BEAM_SIZE,
        language="en",
        vad_filter=False,                  # the recorder already gated on VAD
        condition_on_previous_text=False,   # each command is independent
        no_speech_threshold=0.6,
    )

    parts: list[str] = []
    for seg in segments:
        # Drop segments Whisper itself flags as non-speech. These are the
        # "this." / "thank you." hallucinations it emits on near-silence.
        if seg.no_speech_prob > 0.8:
            continue
        parts.append(seg.text.strip())

    text = " ".join(parts).strip()
    log.debug("STT (%.2fs): %r", time.monotonic() - t0, text)
    return text
