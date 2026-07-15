#!/usr/bin/env bash
# Install all project dependencies into the active Python environment.
# Run from the project root with your conda env activated.
#
#   conda activate real-time-inference
#   bash scripts/install_dev.sh
#
# GPU users: pass --cuda to install the CUDA 12.1 PyTorch wheel instead.

set -euo pipefail

# Warn if Python version is below 3.11 (untested) or above 3.13 (some deps lag)
PY_VER=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python $PY_VER detected"

CUDA=false
for arg in "$@"; do
  [[ "$arg" == "--cuda" ]] && CUDA=true
done

echo "==> Step 1/3 — Installing PyTorch..."
if $CUDA; then
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
else
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
fi

echo ""
echo "==> Step 2/3 — Installing YOLOX (inference only, skips onnx/cmake deps)..."
# --no-deps skips yolox's pinned onnx==1.8.1 which requires cmake to build.
# --no-build-isolation lets setup.py find the already-installed torch.
pip install yolox --no-deps --no-build-isolation

echo ""
echo "==> Step 3/3 — Installing remaining service dependencies..."
pip install \
  -r services/inference/requirements.txt \
  -r services/consumer/requirements.txt \
  -r services/api/requirements.txt

echo ""
echo "Done. To pre-download model weights:"
echo "  python scripts/download_weights.py --model yolox-nano"
