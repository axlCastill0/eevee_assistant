"""Wake-word detection for `heed`-exported ONNX models.

openWakeWord cannot run these. Its models take the output of its own
melspectrogram+embedding frontend; a heed export takes log-mel features
directly (shape (1, n_mels, frames)) and carries its whole preprocessing
chain in a JSON sidecar. So this module reimplements that chain on numpy +
scipy and drives the ONNX session itself.

The chain, in the order the sidecar mandates:

  1. high-pass (Butterworth) + 50/60 Hz mains notches, causal, streaming
  2. peak normalize to -3 dBFS
  3. log-mel spectrogram (HTK mel scale, power 2, centred reflect-padded STFT)
  4. CMN: subtract the per-window mean of each mel bin across time

Step 4 is why 2 is cosmetic here: CMN removes any constant log offset, and a
gain change is exactly that. It is kept for fidelity with training.

Conventions NOT pinned down by the sidecar (mel scale, filter normalisation,
log base, notch Q) default to what PyTorch/torchaudio does, because the export
came from a torch 2.11 graph. They are env-overridable so a mismatch can be
corrected without touching code -- see `MelConfig`.
"""
import json
import logging
import os
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("wakeword")

INT16_FULL_SCALE = 32768.0

# log(0) guard. Only matters in near-silence, which the energy gate skips.
LOG_EPS = 1e-10


def is_heed_model(model_path: str) -> bool:
    """True when `model_path` looks like a heed export (has its sidecar)."""
    return os.path.exists(sidecar_path(model_path))


def sidecar_path(model_path: str) -> str:
    """The metadata JSON that ships beside a heed .onnx.

    `wake.onnx` -> `wake.json`, and `wake.int8.onnx` -> `wake.json` too: the
    quantized export shares the float model's metadata.
    """
    base = model_path
    for suffix in (".int8.onnx", ".onnx"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base + ".json"


# ---------------------------------------------------------------------------
# feature extraction
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MelConfig:
    """Everything needed to turn 1 s of audio into the model's input tensor."""
    sample_rate: int
    window_samples: int
    n_mels: int
    n_fft: int
    win_length: int
    hop_length: int
    fmin: float
    fmax: float
    # Unpinned conventions. Defaults match torchaudio.
    mel_scale: str = "htk"      # or "slaney"
    mel_norm: str = "none"      # or "slaney"
    log_base: str = "e"         # or "10"

    @classmethod
    def from_meta(cls, meta: dict) -> "MelConfig":
        sr = int(meta.get("sample_rate", 16000))
        return cls(
            sample_rate=sr,
            window_samples=int(meta.get("audio_window_samples", sr)),
            n_mels=int(meta.get("n_mels", 40)),
            n_fft=int(meta.get("n_fft", 512)),
            win_length=int(meta.get("win_length", 400)),
            hop_length=int(meta.get("hop_length", 160)),
            fmin=float(meta.get("mel_fmin_hz", 0.0)),
            fmax=float(meta.get("mel_fmax_hz", sr / 2)),
            mel_scale=os.environ.get("VOICE_WW_MEL_SCALE", "htk").lower(),
            mel_norm=os.environ.get("VOICE_WW_MEL_NORM", "none").lower(),
            log_base=os.environ.get("VOICE_WW_LOG_BASE", "e").lower(),
        )


def _hz_to_mel(hz: np.ndarray | float, scale: str) -> np.ndarray | float:
    if scale == "htk":
        return 2595.0 * np.log10(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)
    # Slaney: linear below 1 kHz, logarithmic above.
    hz = np.asarray(hz, dtype=np.float64)
    f_min, f_sp = 0.0, 200.0 / 3
    mel = (hz - f_min) / f_sp
    min_log_hz, min_log_mel = 1000.0, (1000.0 - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    hi = hz >= min_log_hz
    mel = np.where(hi, min_log_mel + np.log(np.maximum(hz, min_log_hz) / min_log_hz) / logstep, mel)
    return mel


def _mel_to_hz(mel: np.ndarray, scale: str) -> np.ndarray:
    if scale == "htk":
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)
    f_min, f_sp = 0.0, 200.0 / 3
    hz = f_min + f_sp * mel
    min_log_hz, min_log_mel = 1000.0, (1000.0 - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    hi = mel >= min_log_mel
    return np.where(hi, min_log_hz * np.exp(logstep * (mel - min_log_mel)), hz)


def mel_filterbank(cfg: MelConfig) -> np.ndarray:
    """(n_mels, n_fft//2+1) triangular filterbank, peak 1.0 unless normalised.

    Matches torchaudio.functional.melscale_fbanks: triangles whose slopes are
    divided by the distance to the neighbouring centre, so every filter peaks
    at 1.0 regardless of its width ("norm=None").
    """
    n_bins = cfg.n_fft // 2 + 1
    all_freqs = np.linspace(0, cfg.sample_rate / 2, n_bins)

    m_min = _hz_to_mel(cfg.fmin, cfg.mel_scale)
    m_max = _hz_to_mel(cfg.fmax, cfg.mel_scale)
    m_pts = np.linspace(m_min, m_max, cfg.n_mels + 2)
    f_pts = _mel_to_hz(m_pts, cfg.mel_scale)

    f_diff = np.diff(f_pts)                       # (n_mels+1,)
    slopes = f_pts[np.newaxis, :] - all_freqs[:, np.newaxis]   # (n_bins, n_mels+2)
    down = -slopes[:, :-2] / f_diff[np.newaxis, :-1]
    up = slopes[:, 2:] / f_diff[np.newaxis, 1:]
    fb = np.maximum(0.0, np.minimum(down, up))    # (n_bins, n_mels)

    if cfg.mel_norm == "slaney":
        fb *= (2.0 / (f_pts[2:] - f_pts[:-2]))[np.newaxis, :]

    return fb.T.astype(np.float32)                # (n_mels, n_bins)


class MelFrontend:
    """Audio window -> CMN'd log-mel tensor. Stateless between calls."""

    def __init__(self, cfg: MelConfig):
        self.cfg = cfg
        self.fb = mel_filterbank(cfg)
        # Periodic Hann, matching torch.hann_window's default, zero-padded to
        # n_fft and centred -- which is what torch.stft does with
        # win_length < n_fft.
        win = np.hanning(cfg.win_length + 1)[:-1].astype(np.float32)
        pad = cfg.n_fft - cfg.win_length
        left = pad // 2
        self.window = np.pad(win, (left, pad - left)).astype(np.float32)
        self._log = np.log if cfg.log_base == "e" else np.log10

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        """`audio`: float32 mono, `window_samples` long. -> (1, n_mels, frames)."""
        cfg = self.cfg
        # center=True with reflect padding, as in torch.stft's default.
        padded = np.pad(audio, cfg.n_fft // 2, mode="reflect")
        n_frames = 1 + (len(padded) - cfg.n_fft) // cfg.hop_length
        frames = np.lib.stride_tricks.as_strided(
            padded,
            shape=(n_frames, cfg.n_fft),
            strides=(padded.strides[0] * cfg.hop_length, padded.strides[0]),
        )
        spec = np.fft.rfft(frames * self.window, n=cfg.n_fft, axis=1)
        power = (spec.real ** 2 + spec.imag ** 2).astype(np.float32)   # (frames, bins)

        mel = self.fb @ power.T                                        # (n_mels, frames)
        logmel = self._log(np.maximum(mel, LOG_EPS))
        # CMN: per-bin mean across time, for this window only.
        logmel -= logmel.mean(axis=1, keepdims=True)
        return logmel[np.newaxis, :, :].astype(np.float32)


class StreamingFilter:
    """Causal HPF + mains notches, biquad state retained across chunks.

    Filtering each chunk once with carried state is identical to filtering the
    whole stream in one pass, which is what training did to the clip.
    """

    def __init__(self, meta_op: dict, sample_rate: int):
        from scipy import signal

        cutoff = float(meta_op.get("cutoff_hz", 100.0))
        order = int(meta_op.get("order", 8))
        sos = [signal.butter(order, cutoff / (sample_rate / 2), btype="high", output="sos")]

        # Q is not in the sidecar; 30 is scipy's documented example value and
        # gives a ~2 Hz notch at 50/60 Hz, narrow enough not to touch speech.
        q = float(os.environ.get("VOICE_WW_NOTCH_Q", "30"))
        for f0 in meta_op.get("mains_notch_hz", []):
            b, a = signal.iirnotch(float(f0), q, fs=sample_rate)
            sos.append(signal.tf2sos(b, a))

        self.sos = np.concatenate(sos, axis=0)
        self._zi = signal.sosfilt_zi(self.sos) * 0.0
        self._sosfilt = signal.sosfilt

    def __call__(self, chunk: np.ndarray) -> np.ndarray:
        out, self._zi = self._sosfilt(self.sos, chunk, zi=self._zi)
        return out.astype(np.float32)

    def reset(self) -> None:
        self._zi *= 0.0


# ---------------------------------------------------------------------------
# detector
# ---------------------------------------------------------------------------

class HeedWakeWordDetector:
    """Streaming wake-word detector for a heed export.

    Same interface as the openWakeWord wrapper: feed 16 kHz int16 frames to
    `process()`, get `(triggered, probability)`. Frame length is free -- the
    detector keeps its own 1 s window -- but the pipeline feeds 1280 samples
    (80 ms), so the model runs at a 80 ms hop.
    """

    def __init__(self, model_path: str, threshold: float | None = None,
                 meta_path: str | None = None):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Wake-word model not found: {model_path}")

        meta_path = meta_path or sidecar_path(model_path)
        if not os.path.exists(meta_path):
            raise FileNotFoundError(
                f"Wake-word metadata not found: {meta_path}. A heed export ships "
                "the .json beside the .onnx; copy both into the models directory."
            )
        with open(meta_path) as fh:
            self.meta = json.load(fh)

        self.cfg = MelConfig.from_meta(self.meta)
        self.frontend = MelFrontend(self.cfg)

        hpf = next((op for op in self.meta.get("preprocessing", [])
                    if op.get("op") == "highpass_filter"), None)
        self.filter = StreamingFilter(hpf, self.cfg.sample_rate) if hpf else None

        self.peak_target = next(
            (float(op.get("target_dbfs", -3.0)) for op in self.meta.get("preprocessing", [])
             if op.get("op") == "peak_normalize"), None)

        trig = self.meta.get("trigger", {})
        self.threshold = self.meta.get("threshold", 0.5) if threshold is None else threshold
        self.consecutive_needed = int(trig.get("consecutive_frames", 1))
        self.refractory_s = float(trig.get("refractory_seconds", 0.0))

        self.gate = self.meta.get("energy_gate") or None

        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            model_path, sess_options=opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

        self._window = np.zeros(self.cfg.window_samples, dtype=np.float32)
        self._raw_window = np.zeros(self.cfg.window_samples, dtype=np.float32)
        self._consecutive = 0
        self._refractory_samples = 0
        self._primed = 0

        log.info(
            "Wake word %r (heed) loaded from %s: threshold=%.3f, %d consecutive "
            "frames, %.2fs refractory",
            self.meta.get("phrase", "?"), model_path, self.threshold,
            self.consecutive_needed, self.refractory_s,
        )

    # -- main entry point --------------------------------------------------

    def process(self, chunk_16k: np.ndarray) -> tuple[bool, float]:
        """Feed one frame of 16 kHz int16 audio. -> (triggered, probability)."""
        raw = chunk_16k.astype(np.float32) / INT16_FULL_SCALE
        filtered = self.filter(raw) if self.filter else raw

        n = len(raw)
        self._window = np.concatenate((self._window[n:], filtered))
        self._raw_window = np.concatenate((self._raw_window[n:], raw))

        # Don't score a window that is still part zeros from startup or reset.
        if self._primed < self.cfg.window_samples:
            self._primed += n
            return False, 0.0

        if self._refractory_samples > 0:
            self._refractory_samples -= n
            return False, 0.0

        if not self._passes_energy_gate():
            self._consecutive = 0
            return False, 0.0

        prob = self._score(self._window)

        if prob < self.threshold:
            self._consecutive = 0
            return False, prob

        self._consecutive += 1
        if self._consecutive < self.consecutive_needed:
            return False, prob

        self._consecutive = 0
        self._refractory_samples = int(self.refractory_s * self.cfg.sample_rate)
        return True, prob

    def reset(self) -> None:
        """Drop all audio and trigger state. Call after handling an event."""
        self._window[:] = 0.0
        self._raw_window[:] = 0.0
        self._consecutive = 0
        self._primed = 0
        if self.filter:
            self.filter.reset()

    # -- internals ---------------------------------------------------------

    def _score(self, window: np.ndarray) -> float:
        audio = window
        if self.peak_target is not None:
            peak = float(np.max(np.abs(audio)))
            if peak > 0:
                audio = audio * (10.0 ** (self.peak_target / 20.0) / peak)
        mel = self.frontend(audio)
        logit = float(np.asarray(self.session.run(None, {self.input_name: mel})[0]).reshape(-1)[0])
        return 1.0 / (1.0 + float(np.exp(-logit)))

    def _passes_energy_gate(self) -> bool:
        """Cheap silence/noise rejection, so the model is skipped in a quiet room.

        Measured on the *unfiltered* window: the point is whether the room's
        energy is speech-shaped, and the high-pass has already deleted the
        rumble that would otherwise prove it is not.
        """
        if not self.gate:
            return True

        audio = self._raw_window
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms <= 0:
            return False
        if 20.0 * np.log10(rms) < float(self.gate.get("rms_threshold_dbfs", -55.0)):
            return False

        min_fraction = float(self.gate.get("voice_band_min_fraction", 0.0))
        if min_fraction <= 0:
            return True

        power = np.abs(np.fft.rfft(audio)) ** 2
        freqs = np.fft.rfftfreq(len(audio), 1.0 / self.cfg.sample_rate)
        total = power.sum()
        if total <= 0:
            return False
        band = (freqs >= float(self.gate.get("voice_band_lo_hz", 100.0))) & \
               (freqs <= float(self.gate.get("voice_band_hi_hz", 7000.0)))
        return (power[band].sum() / total) >= min_fraction
