"""All runtime configuration for the voice pipeline.

Every value can be overridden by an environment variable so the container
needs no rebuild to retune. Defaults are the values measured as good on a
Raspberry Pi 5 (see docs/VOICE_SETUP.md).
"""
import logging
import os


def _str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logging.getLogger("config").warning(
            "%s=%r is not an int; using default %d", name, raw, default
        )
        return default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logging.getLogger("config").warning(
            "%s=%r is not a float; using default %s", name, raw, default
        )
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ============================================================================
# AUDIO DEVICES
# ============================================================================
# Three accepted forms, in descending order of how well they survive a reboot:
#
#   CARD=eeveemic    an ALSA card id, pinned by a udev rule. Resolved through
#                    /proc/asound, so it holds even if the card number moves.
#                    THE RIGHT ANSWER for hardware that stays plugged in.
#   USB Microphone   a case-insensitive substring of the PortAudio device name
#   0                a raw index -- moves on every replug; debugging only
#
# List what the container can see with:
#   docker compose exec voice python -m voice_assistant.devices
#
# NOTE a udev `ATTR{id}` rule renames the card *id*, which is NOT the name
# PortAudio reports: that comes from the card's name field, straight off the
# USB descriptor. So after pinning ids you must use the CARD= form; a name
# substring of "eeveemic" matches nothing. Learned the hard way on the Pi,
# 2026-10-15.
INPUT_DEVICE: str | int = _str("VOICE_INPUT_DEVICE", "0")
OUTPUT_DEVICE: str | int = _str("VOICE_OUTPUT_DEVICE", "1")

# ============================================================================
# SAMPLE RATES
# ============================================================================
MIC_RATE = _int("VOICE_MIC_RATE", 48000)   # what the USB mic produces
MODEL_RATE = 16000                          # wake word, VAD and Whisper all require this

if MIC_RATE % MODEL_RATE != 0:
    raise ValueError(
        f"VOICE_MIC_RATE={MIC_RATE} must be an integer multiple of {MODEL_RATE}; "
        "integer decimation depends on it (48000 or 32000 are safe)"
    )
DOWNSAMPLE = MIC_RATE // MODEL_RATE   # = 3 at 48 kHz

OUTPUT_RATE_FALLBACK = 48000   # only used if probing the output device fails

# ============================================================================
# FRAME SIZES (samples at MIC_RATE)
# ============================================================================
# Wake word: 1280 samples @ 16 kHz = 80 ms  ->  3840 @ 48 kHz
WW_NATIVE_FRAME = 1280 * DOWNSAMPLE
# Silero VAD: 512 samples @ 16 kHz = 32 ms  ->  1536 @ 48 kHz
VAD_NATIVE_FRAME = 512 * DOWNSAMPLE

# ============================================================================
# DETECTION THRESHOLDS
# ============================================================================
# Left unset, each model decides: a heed export carries the threshold it was
# calibrated at in its sidecar. This default only applies to openWakeWord.
#
# NOTE a threshold tuned for one model is meaningless for the other. If
# VOICE_WW_THRESHOLD was raised to 0.9 for the heed model, UNSET IT when going
# back to hey_jarvis -- 0.9 on openWakeWord is deaf, not strict.
WW_THRESHOLD_IS_SET = bool(os.environ.get("VOICE_WW_THRESHOLD", "").strip())
WW_THRESHOLD = _float("VOICE_WW_THRESHOLD", 0.5)
VAD_SPEECH_THRESHOLD = _float("VOICE_VAD_THRESHOLD", 0.5)

# ============================================================================
# RECORDING BEHAVIOUR
# ============================================================================
PRE_ROLL_MS = _int("VOICE_PRE_ROLL_MS", 500)
SILENCE_TIMEOUT_MS = _int("VOICE_SILENCE_TIMEOUT_MS", 800)
MIN_RECORDING_MS = _int("VOICE_MIN_RECORDING_MS", 500)
MAX_RECORDING_MS = _int("VOICE_MAX_RECORDING_MS", 8000)

PRE_ROLL_SAMPLES = (PRE_ROLL_MS * MODEL_RATE) // 1000
SILENCE_TIMEOUT_SAMPLES = (SILENCE_TIMEOUT_MS * MODEL_RATE) // 1000
MIN_RECORDING_SAMPLES = (MIN_RECORDING_MS * MODEL_RATE) // 1000
MAX_RECORDING_SAMPLES = (MAX_RECORDING_MS * MODEL_RATE) // 1000

# Pause after speaking before re-listening, so the tail of TTS playback does
# not retrigger the wake word through an open mic.
POST_TTS_GRACE_MS = _int("VOICE_POST_TTS_GRACE_MS", 300)

# ============================================================================
# MODEL PATHS
# ============================================================================
# MODEL_DIR is a read-only bind mount in the container. Large models are not
# baked into the image; see infra/docker/voice/Dockerfile.
MODEL_DIR = _str("VOICE_MODEL_DIR", "models")

VAD_MODEL_PATH = _str("VOICE_VAD_MODEL", f"{MODEL_DIR}/silero_vad.onnx")

# "hey_jarvis", an openWakeWord model baked into the image. Back to being the
# default on 2026-10-16: the "hey eevee" heed export fired on non-speech room
# noise even at a 0.9 threshold (USER DECISION).
#
# Other accepted values:
#   models/hey_eevee.onnx    the heed export (needs its .json sidecar beside
#                            it; scripts/install-wake-model.sh puts both in
#                            place). Still supported, still works.
#   models/my_word.onnx      an openWakeWord export (no .json beside it)
# wake_word.make_detector() picks the engine by looking for the sidecar, so
# switching back is one env var and a restart.
WAKE_WORD_NAME = _str("VOICE_WAKE_WORD", "hey_jarvis")

# Only needed if the sidecar is not named after the model (hey_eevee.onnx ->
# hey_eevee.json). Empty means "derive it".
WAKE_WORD_META = _str("VOICE_WAKE_WORD_META", "")

WHISPER_SIZE = _str("VOICE_WHISPER_SIZE", "tiny.en")
WHISPER_COMPUTE_TYPE = _str("VOICE_WHISPER_COMPUTE", "int8")
WHISPER_BEAM_SIZE = _int("VOICE_WHISPER_BEAM", 1)

# Load Whisper from the baked-in cache ONLY, never from the network.
#
# This defaults to True because the Dockerfile bakes tiny.en into
# /opt/models-cache at build time. With it False, faster-whisper calls
# huggingface_hub.snapshot_download even when the cache is complete — the call
# contacts HF to revalidate, and a Pi that has just rebooted will happily
# connect and then have the connection cut, which raises RemoteProtocolError.
# huggingface_hub only falls back to the cache on connection/timeout errors, so
# that one escapes and kills the pipeline at startup. Seen on the real Pi
# 2026-10-08.
#
# Set VOICE_WHISPER_ALLOW_DOWNLOAD=true for a bare-metal first run, or when
# changing VOICE_WHISPER_SIZE to something the image does not carry.
WHISPER_LOCAL_ONLY = not _bool("VOICE_WHISPER_ALLOW_DOWNLOAD", False)

# Qwen2.5-1.5B Q5_K_M: chosen for classification quality over latency.
# Budget on a Pi 5 is roughly 4-5 s per classification (the 0.5B/Q4 was
# 1.3-1.7 s) and ~1.1 GB resident. The fast path below is what keeps typical
# utterances responsive; only unmatched phrasings pay the model cost.
# Swap to models/qwen2.5-0.5b-instruct-q4_k_m.gguf via VOICE_SLM_MODEL if
# latency ever matters more than accuracy.
SLM_PATH = _str("VOICE_SLM_MODEL", f"{MODEL_DIR}/qwen2.5-1.5b-instruct-q5_k_m.gguf")
# Context window. This has to hold the ENTIRE system prompt, which grows with
# the intent catalogue -- every intent adds a line to it. 1024 was the default
# until 2026-10-19, when the 22nd intent pushed the prompt to 1048 tokens and
# llama.cpp refused to run at all:
#   ValueError: Requested tokens (1048) exceed context window of 1024
# slm.py now measures the prompt and grows this on its own if it is still too
# small, so adding intents cannot break the pipeline again; this is the
# starting point, with room for a good few more.
SLM_N_CTX = _int("VOICE_SLM_N_CTX", 2048)
SLM_MAX_TOKENS = _int("VOICE_SLM_MAX_TOKENS", 40)

TTS_MODEL_PATH = _str("VOICE_TTS_MODEL", f"{MODEL_DIR}/en_US-amy-medium.onnx")
TTS_CONFIG_PATH = _str("VOICE_TTS_CONFIG", f"{MODEL_DIR}/en_US-amy-medium.onnx.json")

# ============================================================================
# CPU BUDGET
# ============================================================================
# The Pi 5 has 4 Cortex-A76 cores. Pipeline stages run strictly sequentially,
# so Whisper and the SLM can each claim all 4 without contending. The wake
# word and VAD are pinned to 1 thread each: they are tiny, always-on, and
# thread handoff costs more than the work itself.
CPU_THREADS = _int("VOICE_CPU_THREADS", os.cpu_count() or 4)
WHISPER_THREADS = _int("VOICE_WHISPER_THREADS", CPU_THREADS)
SLM_THREADS = _int("VOICE_SLM_THREADS", CPU_THREADS)
ALWAYS_ON_THREADS = 1   # wake word + VAD onnxruntime sessions

# ============================================================================
# BACKEND API
# ============================================================================
API_BASE_URL = _str("VOICE_API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = _str("API_KEY", "")           # same shared secret the backend checks
API_TIMEOUT_S = _float("VOICE_API_TIMEOUT_S", 5.0)
API_RETRIES = _int("VOICE_API_RETRIES", 2)

# Fetch the intent catalogue from the API at startup. If the API is down we
# fall back to the baked-in list so the pipeline still boots and can still
# answer "the backend is not responding".
INTENTS_FETCH_TIMEOUT_S = _float("VOICE_INTENTS_FETCH_TIMEOUT_S", 3.0)

# How often to tell the backend this pipeline is alive. The backend marks voice
# down after 45 s of silence (services.STALE_AFTER_S), so this must stay a
# comfortable fraction of that — 15 s allows two dropped beats before flapping.
# Set to 0 to disable.
HEARTBEAT_INTERVAL_S = _float("VOICE_HEARTBEAT_INTERVAL_S", 15.0)

# Report every stage transition (ready/listening/thinking/speaking) to
# POST /voice/state so the dashboard's voice pill can change colour as it
# happens. Posted from a background thread and never waited on, so the worst
# case of a dead backend is a stale pill, not added latency.
# Set to false to stop publishing (the dashboard then shows "unknown").
STATE_EVENTS_ENABLED = _bool("VOICE_STATE_EVENTS", True)

# Per-post timeout for state events, deliberately far shorter than
# API_TIMEOUT_S. A state event is worthless the moment it is late, so a slow
# backend should drop it rather than have the reporter thread queue up behind
# it. No retries, for the same reason.
STATE_EVENT_TIMEOUT_S = _float("VOICE_STATE_EVENT_TIMEOUT_S", 1.0)

# Re-send the current state when nothing has changed for this long. The
# backend's event hub is in-memory, so a backend restart forgets what the
# pipeline is doing and the dashboard would sit on "unknown" until the next
# utterance — possibly hours. The backend ignores an identical republish
# (same state, same text) rather than treating it as a new event, so this
# costs one loopback POST per interval and nothing else. 0 disables.
STATE_REPEAT_S = _float("VOICE_STATE_REPEAT_S", HEARTBEAT_INTERVAL_S)

# ============================================================================
# FAST PATH
# ============================================================================
# Regex matching before the SLM. Skips ~1.5 s of model inference on the common
# phrasings. Set VOICE_FASTPATH=false to always go through the SLM (useful when
# measuring classifier accuracy).
FASTPATH_ENABLED = _bool("VOICE_FASTPATH", True)

# Load the SLM at all. With the fast path on and a fixed command vocabulary you
# can run without it and save ~400 MB of RSS; unmatched utterances then become
# "unknown" instead of being classified.
SLM_ENABLED = _bool("VOICE_SLM_ENABLED", True)


# ============================================================================
# LOGGING
# ============================================================================
VERBOSE = _bool("VOICE_VERBOSE", False)
LOG_LEVEL = logging.DEBUG if VERBOSE else logging.INFO
LOG_FORMAT = "%(asctime)s [%(name)-9s] %(message)s"
LOG_DATEFMT = "%H:%M:%S"


def configure_logging() -> None:
    """Call once at process startup. Idempotent."""
    logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
    # Container logs go to the journal via Docker; unbuffered stdout matters
    # more than format here (see PYTHONUNBUFFERED in the Dockerfile).


def alsa_card_index(card_id: str) -> int:
    """ALSA card id -> card number. See voice_assistant.alsa for the lookup.

    Short version: this asks libasound over /dev/snd rather than reading
    /proc/asound, because the container runtime masks /proc/asound to an
    empty directory and the /proc route therefore only works on the host.
    """
    from . import alsa

    index = alsa.card_index(card_id)
    if index is None:
        raise RuntimeError(
            f"No ALSA card with id {card_id!r}. Cards visible here:\n"
            + alsa.describe_cards()
            + "\n\nIf that list is empty inside the container but `cat "
              "/proc/asound/cards` works on the host, libasound could not be "
              "loaded -- check that /dev/snd is mapped in and that the "
              "container user is in the audio group (AUDIO_GID)."
        )
    return index


def resolve_device(spec: str | int, kind: str) -> int:
    """Resolve a device spec to a sounddevice index.

    See the AUDIO DEVICES block above for the three accepted forms.
    """
    import sounddevice as sd

    if isinstance(spec, int) or str(spec).strip().lstrip("-").isdigit():
        return int(spec)

    raw = str(spec).strip()
    want_input = kind == "input"

    # CARD=<id> / hw:CARD=<id>: resolve the id to a card number, then find the
    # PortAudio device that wraps it. PortAudio appends the ALSA address to
    # every hardware device's name -- "USB Microphone: Audio (hw:0,0)" -- which
    # is the only place the card number appears.
    if raw.upper().startswith(("CARD=", "HW:CARD=")):
        card_id = raw.partition("=")[2]
        index = alsa_card_index(card_id)
        token = f"(hw:{index},"
        for idx, dev in enumerate(sd.query_devices()):
            channels = dev["max_input_channels"] if want_input else dev["max_output_channels"]
            if channels > 0 and token in dev["name"]:
                logging.getLogger("config").info(
                    "%s device %s -> card %d -> [%d] %s",
                    kind, raw, index, idx, dev["name"],
                )
                return idx
        from . import alsa
        raise RuntimeError(
            f"ALSA card {card_id!r} is card {index}, but no PortAudio {kind} "
            f"device wraps it. Devices:\n{sd.query_devices()}\n\nCards:\n"
            + alsa.describe_cards()
        )

    needle = raw.lower()

    matches = [
        (idx, dev["name"])
        for idx, dev in enumerate(sd.query_devices())
        if (dev["max_input_channels"] if want_input else dev["max_output_channels"]) > 0
        and needle in dev["name"].lower()
    ]

    if not matches:
        from . import alsa
        raise RuntimeError(
            f"No {kind} device matching {spec!r}. Available devices:\n"
            f"{sd.query_devices()}\n\n"
            "If that spec is a udev-pinned ALSA card id, it will never match a "
            f"device name -- use CARD={spec} instead. Cards:\n"
            + alsa.describe_cards()
        )

    if len(matches) > 1:
        # Taking the first match silently is how you end up recording from the
        # wrong microphone and never understanding why. A bare "USB" needle
        # matches every USB audio device on the bus, which is common: a USB mic
        # and a USB speaker both advertise it.
        listed = ", ".join(f"[{i}] {n}" for i, n in matches)
        logging.getLogger("config").warning(
            "%s device spec %r matched %d devices (%s). Using [%d]. "
            "Narrow the substring to pick deliberately.",
            kind, spec, len(matches), listed, matches[0][0],
        )

    return matches[0][0]
