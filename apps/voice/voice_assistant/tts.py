"""Text-to-speech stage using piper-onnx.

Piper emits float32 at the voice model's native rate (22050 Hz for medium
voices). USB audio devices generally only accept 44100 or 48000, so output is
resampled before playback (~5 ms per phrase).

LOUDNESS
    Piper's output peaks wherever the voice happens to peak, which is well
    below full scale, while the timer and alarm sounds are mastered files
    played by Chromium that sit near it. The assistant was audibly quieter
    than its own alarms (USER 2026-10-24). Raising the speaker fixes one and
    ruins the other, so every utterance is normalised HERE instead -- the one
    place that touches TTS audio and nothing else.
"""
import json
import logging
import time

import numpy as np
import sounddevice as sd

from . import config
from .helpers import resample_for_output

log = logging.getLogger("tts")


def _level(audio: np.ndarray) -> np.ndarray:
    """Normalise one utterance to config.TTS_PEAK, then apply the trim.

    Per utterance, not per session: there is no dynamic intent in synthesized
    speech, so every phrase arriving at the same loudness is what is wanted.

    The boost is capped (TTS_MAX_BOOST) so a phrase that came out near-silent
    is not multiplied into amplified noise, and the result is clipped, which
    only bites if TTS_GAIN was pushed above 1.0.
    """
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak <= 1e-6:
        return audio

    scale = config.TTS_GAIN
    if config.TTS_PEAK > 0:
        scale *= min(config.TTS_PEAK / peak, config.TTS_MAX_BOOST)

    if abs(scale - 1.0) < 1e-3:
        return audio

    out = audio * scale
    if float(np.max(np.abs(out))) > 1.0:
        clipped = int(np.count_nonzero(np.abs(out) > 1.0))
        log.warning("TTS clipped %d samples; lower VOICE_TTS_GAIN (%.2f)",
                    clipped, config.TTS_GAIN)
        np.clip(out, -1.0, 1.0, out=out)

    return out.astype(np.float32)


def _detect_output_rate(device_index: int) -> int:
    """Probe the output device for the first sample rate it accepts."""
    for sr in (48000, 44100):
        try:
            sd.check_output_settings(
                device=device_index, samplerate=sr, channels=1, dtype="float32",
            )
            return sr
        except sd.PortAudioError:
            continue
    try:
        info = sd.query_devices(device_index, "output")
        return int(info["default_samplerate"])
    except Exception:
        log.warning("Could not probe output rate; falling back to %d",
                    config.OUTPUT_RATE_FALLBACK)
        return config.OUTPUT_RATE_FALLBACK


class Speaker:
    """Synthesize and play TTS through the configured output device."""

    def __init__(self,
                 model_path: str = config.TTS_MODEL_PATH,
                 config_path: str = config.TTS_CONFIG_PATH,
                 output_device: str | int = config.OUTPUT_DEVICE):
        from piper_onnx import Piper

        t0 = time.monotonic()
        self.piper = Piper(model_path, config_path)

        with open(config_path) as f:
            voice_cfg = json.load(f)
        self.model_rate = voice_cfg["audio"]["sample_rate"]

        self.output_device = config.resolve_device(output_device, "output")
        self.output_rate = _detect_output_rate(self.output_device)

        log.info("Piper loaded in %.2fs (model %d Hz -> device %d @ %d Hz, "
                 "peak %.2f, gain %.2f)",
                 time.monotonic() - t0, self.model_rate,
                 self.output_device, self.output_rate,
                 config.TTS_PEAK, config.TTS_GAIN)

    def say(self, text: str) -> None:
        """Synthesize `text` and play it. Blocking.

        Playback failures are logged, not raised: losing audio output should
        not kill the pipeline, since the wake-word loop is still useful and
        the backend has already acted on the intent.
        """
        if not text:
            return

        t0 = time.monotonic()
        try:
            audio_f32, model_rate = self.piper.create(text)
        except Exception:
            log.exception("TTS synthesis failed for %r", text)
            return

        synth_ms = (time.monotonic() - t0) * 1000
        # Levelled AFTER resampling: resample_poly rings slightly and can
        # overshoot the peak it was handed, which would eat the headroom the
        # normalisation just set.
        audio_out = _level(
            resample_for_output(audio_f32, model_rate, self.output_rate)
        )
        log.debug("TTS (%.0fms): %r", synth_ms, text)

        try:
            sd.play(audio_out, samplerate=self.output_rate, device=self.output_device)
            sd.wait()
        except Exception:
            log.exception("Audio playback failed")
