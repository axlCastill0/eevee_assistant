# Python 3.11, not 3.13: several deps here (llama-cpp-python, ctranslate2,
# onnxruntime) have no aarch64 wheels for 3.13 and would fall back to a long
# source build or fail outright. Bookworm matches Raspberry Pi OS Lite.
FROM python:3.11-slim-bookworm

# Audio group id. Must match the host's `audio` group or the container cannot
# open /dev/snd. 29 is correct on Raspberry Pi OS / Debian; check with
# `getent group audio` on the Pi and override with
# `--build-arg AUDIO_GID=<n>` if it differs.
ARG AUDIO_GID=29

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Keep the always-on ONNX models single-threaded; see wake_word._cap_threads.
    OMP_NUM_THREADS=1 \
    # Cache inside the image so the Whisper weights baked in below are found
    # at runtime without a writable home directory.
    HF_HOME=/opt/models-cache \
    XDG_CACHE_HOME=/opt/models-cache

# Runtime libs only:
#   libportaudio2 - sounddevice loads this at runtime (the -dev headers are
#                   not needed; sounddevice binds through CFFI)
#   libsndfile1   - audio file I/O
#   espeak-ng     - Piper's phonemiser backend
#   alsa-utils    - arecord/aplay, for debugging audio from inside the container
RUN apt-get update && apt-get install -y --no-install-recommends \
        libportaudio2 \
        libsndfile1 \
        espeak-ng \
        alsa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps/voice/requirements.txt ./requirements.txt

# The extra index serves prebuilt aarch64 CPU wheels for llama-cpp-python.
# Without it pip compiles llama.cpp from source: 10+ minutes on a Pi 5.
RUN pip install --no-cache-dir \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
        -r requirements.txt

# Bake the small models into the image. These are fixed, modest in size, and
# baking them means no network dependency on first boot.
#   openWakeWord (~50 MB) installs into its own package directory
#   Whisper tiny.en (~75 MB) otherwise downloads on first run, which costs
#   ~24 s and fails entirely on a Pi with no internet
RUN python -c "import openwakeword.utils; openwakeword.utils.download_models()" \
 && python -c "from faster_whisper import WhisperModel; \
WhisperModel('tiny.en', device='cpu', compute_type='int8')" \
 && chmod -R a+rX /opt/models-cache

# The large models (Qwen ~1.2 GB, Piper voice, Silero VAD) are NOT baked in.
# They are bind-mounted read-only at /app/models by docker-compose so the
# image stays small and models can be swapped without a rebuild.

COPY apps/voice/ ./

# Non-root, but in the audio group so /dev/snd is reachable.
RUN groupadd -g "${AUDIO_GID}" hostaudio 2>/dev/null || true \
 && useradd --create-home --shell /usr/sbin/nologin voice \
 && usermod -aG "${AUDIO_GID}" voice \
 && chown -R voice:voice /app
USER voice

CMD ["python", "run.py"]
