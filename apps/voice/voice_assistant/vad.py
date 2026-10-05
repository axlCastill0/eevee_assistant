"""Silero VAD v5 wrapper using onnxruntime directly.

The v5 ONNX model expects each call's input to be:
  [last 64 samples of previous chunk] + [512 new samples]
The 64-sample "context" prefix is essential — without it, every chunk is
treated as starting from silence and speech scores stay near zero.
"""
import logging

import numpy as np
import onnxruntime as ort

from . import config

log = logging.getLogger("vad")


class SileroVAD:
    CHUNK_SAMPLES = 512    # new audio per call (32 ms at 16 kHz)
    CONTEXT_SAMPLES = 64   # carried from the tail of the previous chunk

    def __init__(self, model_path: str = config.VAD_MODEL_PATH,
                 sample_rate: int = config.MODEL_RATE):
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self.sample_rate = sample_rate
        self.reset()
        log.debug("Silero VAD loaded from %s", model_path)

    def reset(self) -> None:
        """Clear RNN state and context. Call between utterances."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self.CONTEXT_SAMPLES), dtype=np.float32)

    def __call__(self, pcm_int16: np.ndarray) -> float:
        """Return P(speech) in [0, 1] for a 512-sample int16 chunk."""
        if len(pcm_int16) != self.CHUNK_SAMPLES:
            raise ValueError(
                f"Expected {self.CHUNK_SAMPLES} samples, got {len(pcm_int16)}"
            )
        new_samples = (pcm_int16.astype(np.float32, copy=True) / 32768.0).reshape(1, -1)
        model_input = np.concatenate([self._context, new_samples], axis=1)
        sr = np.array(self.sample_rate, dtype=np.int64)
        prob, self._state = self.session.run(
            None,
            {"input": model_input, "state": self._state, "sr": sr},
        )
        self._context = new_samples[:, -self.CONTEXT_SAMPLES:]
        return float(prob.item())
