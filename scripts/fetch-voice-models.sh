#!/usr/bin/env bash
# Download the large voice models into ./models/ at the repo root.
#
# These are not baked into the Docker image (~1.4 GB total) and not committed.
# The voice container bind-mounts ./models read-only at /app/models.
#
# Small models (openWakeWord, Whisper tiny.en) are baked into the image
# instead; see infra/docker/voice/Dockerfile.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${REPO_ROOT}/models"

mkdir -p "${MODEL_DIR}"
cd "${MODEL_DIR}"

# fetch <url> <output> <description>
# Skips an existing non-empty file so the script is safe to re-run.
fetch() {
  local url="$1" out="$2" desc="$3"
  if [[ -s "${out}" ]]; then
    echo "✓ ${out} already present (${desc})"
    return
  fi
  echo "↓ ${out} — ${desc}"
  # -L follows redirects (Hugging Face uses them); --fail turns an HTML error
  # page into a non-zero exit instead of a corrupt model file.
  curl -L --fail --progress-bar -o "${out}.part" "${url}"
  mv "${out}.part" "${out}"
}

echo "Fetching voice models into ${MODEL_DIR}"
echo

# --- Voice activity detection (~2 MB) --------------------------------------
fetch \
  "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx" \
  "silero_vad.onnx" \
  "Silero VAD v5, ~2 MB"

# --- Intent classifier (~1.2 GB) -------------------------------------------
# Qwen2.5-1.5B-Instruct Q5_K_M: chosen for classification quality. Expect
# ~4-5 s per classification on a Pi 5. The 0.5B/Q4 alternative is ~3x faster
# and ~470 MB if you ever want to trade accuracy back for latency.
fetch \
  "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q5_k_m.gguf" \
  "qwen2.5-1.5b-instruct-q5_k_m.gguf" \
  "Qwen2.5-1.5B-Instruct Q5_K_M, ~1.2 GB"

# --- Text to speech (~60 MB) -----------------------------------------------
# Piper needs the .onnx and its .onnx.json side by side; the json carries the
# sample rate and phoneme map.
#
# JARVIS (USER 2026-10-24), replacing en_US-amy-medium. A community voice from
# jgkawell/jarvis, MIT licensed, fine-tuned for 2000 epochs from the official
# en_GB-alan-medium -- which is the usual stand-in for this voice and is why
# this one starts from it rather than from an American speaker. Same shape as
# the voice it replaces (medium, 22.05 kHz, single speaker, espeak phonemes,
# ~60 MB), so nothing downstream changes; its espeak voice is en-gb-x-rp,
# Received Pronunciation, which is the whole point.
#
# The same repo has a `high` variant at ~108 MB. Better, and slower to
# synthesize on a Pi 5, which is the trade this pipeline cannot afford by
# default -- TTS sits in the user's waiting time. Swap the two URLs and
# VOICE_TTS_MODEL/VOICE_TTS_CONFIG if you want it.
#
# Renamed on the way down to the lang-voice-quality convention the other
# model files here use; upstream calls them plain jarvis-medium.*.
fetch \
  "https://huggingface.co/jgkawell/jarvis/resolve/main/en/en_GB/jarvis/medium/jarvis-medium.onnx" \
  "en_GB-jarvis-medium.onnx" \
  "Piper voice en_GB-jarvis-medium, ~60 MB"

fetch \
  "https://huggingface.co/jgkawell/jarvis/resolve/main/en/en_GB/jarvis/medium/jarvis-medium.onnx.json" \
  "en_GB-jarvis-medium.onnx.json" \
  "Piper voice config"

echo
echo "Done. Contents of ${MODEL_DIR}:"
ls -lh "${MODEL_DIR}"
