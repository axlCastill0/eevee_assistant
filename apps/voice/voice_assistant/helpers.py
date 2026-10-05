"""Utilities shared by multiple pipeline stages.

Anything used by exactly one stage lives in that stage's module instead.
"""
import re
from math import gcd

import numpy as np
from scipy.signal import resample_poly

from . import config


# ============================================================================
# AUDIO RESAMPLING
# ============================================================================

def downsample_mic(chunk_native: np.ndarray) -> np.ndarray:
    """Downsample a mic frame from MIC_RATE to MODEL_RATE.

    Naive decimation (every Nth sample). Speech content lives below 4 kHz so
    aliasing is negligible here.

    Returns a contiguous copy, never a view: sounddevice reuses its input
    buffers between reads, so a view can be overwritten while a model is still
    reading from it.
    """
    return np.ascontiguousarray(chunk_native[::config.DOWNSAMPLE])


def resample_for_output(audio_f32: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Anti-aliased resample for TTS output (typically 22050 -> 48000)."""
    if src_rate == dst_rate:
        return audio_f32
    g = gcd(src_rate, dst_rate)
    up, down = dst_rate // g, src_rate // g
    return resample_poly(audio_f32, up=up, down=down).astype(np.float32)


# ============================================================================
# TRANSCRIPT CLEANUP
# ============================================================================

# Whisper picks up wake-word leakage from the pre-roll buffer ("Jarvis, what
# time is it") and leading disfluencies. Strip them so the classifier sees the
# command itself.
_LEADING_NOISE = re.compile(
    r"^\s*(hey jarvis|jarvis|hey|ok|okay|um|uh|so|like|is)[\s,.!?]+",
    re.IGNORECASE,
)


def preprocess_transcript(text: str) -> str:
    """Strip wake-word leakage and trailing punctuation from a transcript."""
    text = text.strip()
    # Apply repeatedly to catch stacked prefixes ("Jarvis, hey, ...").
    while True:
        stripped = _LEADING_NOISE.sub("", text)
        if stripped == text:
            break
        text = stripped
    return text.rstrip(".,!? ").strip()
