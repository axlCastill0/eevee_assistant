"""Text-to-speech stage using piper-onnx.

Piper emits float32 at the voice model's native rate (22050 Hz for medium
voices). USB audio devices generally only accept 44100 or 48000, so output is
resampled before playback (~5 ms per phrase).
"""
import json
import logging
import time

import numpy as np
import sounddevice as sd

from . import config
from .helpers import resample_for_output

log = logging.getLogger("tts")


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

        log.info("Piper loaded in %.2fs (model %d Hz -> device %d @ %d Hz)",
                 time.monotonic() - t0, self.model_rate,
                 self.output_device, self.output_rate)

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
        audio_out = resample_for_output(audio_f32, model_rate, self.output_rate)
        log.debug("TTS (%.0fms): %r", synth_ms, text)

        try:
            sd.play(audio_out, samplerate=self.output_rate, device=self.output_device)
            sd.wait()
        except Exception:
            log.exception("Audio playback failed")
