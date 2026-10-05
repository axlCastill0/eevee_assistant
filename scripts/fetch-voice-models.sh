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
fetch \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx" \
  "en_US-amy-medium.onnx" \
  "Piper voice en_US-amy-medium, ~60 MB"

fetch \
  "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json" \
  "en_US-amy-medium.onnx.json" \
  "Piper voice config"

echo
echo "Done. Contents of ${MODEL_DIR}:"
ls -lh "${MODEL_DIR}"
