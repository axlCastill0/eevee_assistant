#!/usr/bin/env bash
# Install the "hey eevee" wake-word model into ./models/ at the repo root.
#
# Unlike the models fetch-voice-models.sh downloads, this one is small (44 KB)
# and lives in the repo at hey_eevee_model/, so there is nothing to download --
# it just has to land in models/, which is what the voice container bind-mounts
# read-only at /app/models.
#
# Both files are required: the .onnx is the graph, the .json carries the
# threshold and the preprocessing constants the detector reads at startup.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_ROOT}/hey_eevee_model"
MODEL_DIR="${REPO_ROOT}/models"

# int8 is smaller but SLOWER on the Pi 5's CPU (quantize/dequantize overhead
# with no NPU to pay it off), so the float32 export is what gets installed.
# Set WAKE_VARIANT=int8 to install wake.int8.onnx instead.
VARIANT="${WAKE_VARIANT:-fp32}"
case "${VARIANT}" in
  fp32) SRC_ONNX="${SRC}/wake.onnx" ;;
  int8) SRC_ONNX="${SRC}/wake.int8.onnx" ;;
  *) echo "WAKE_VARIANT must be fp32 or int8, got ${VARIANT}" >&2; exit 1 ;;
esac

mkdir -p "${MODEL_DIR}"
install -m 0644 "${SRC_ONNX}"     "${MODEL_DIR}/hey_eevee.onnx"
install -m 0644 "${SRC}/wake.json" "${MODEL_DIR}/hey_eevee.json"

echo "Installed ${VARIANT} wake model:"
ls -lh "${MODEL_DIR}/hey_eevee.onnx" "${MODEL_DIR}/hey_eevee.json"
echo
echo "VOICE_WAKE_WORD defaults to models/hey_eevee.onnx; no .env change needed."
echo "Restart the pipeline:  cd infra/docker && docker compose restart voice"
