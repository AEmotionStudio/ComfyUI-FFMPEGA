#!/usr/bin/env bash
# ============================================================================
#  ComfyUI-FFMPEGA — Install ALL Optional Dependencies
# ============================================================================
#
#  Usage (from ComfyUI root, with venv activated):
#    bash custom_nodes/ComfyUI-FFMPEGA/install-all-deps.sh
#
#  Or with a specific Python:
#    PYTHON=/path/to/venv/bin/python bash install-all-deps.sh
#
# ============================================================================

set -e

PYTHON="${PYTHON:-python}"
PIP="$PYTHON -m pip install --quiet"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "  FFMPEGA — Installing ALL optional deps"
echo "============================================"
echo "Python: $($PYTHON --version)"
echo ""

# --- Step 1: Git packages (--no-deps) ---
echo "[1/3] Installing git packages (--no-deps)..."

echo "  → SAM3..."
$PIP --no-deps git+https://github.com/facebookresearch/sam3.git 2>/dev/null && \
  echo "  ✓ SAM3" || echo "  ✗ SAM3 failed (non-critical)"

echo "  → MMAudio..."
$PIP --no-deps git+https://github.com/hkchengrex/MMAudio.git 2>/dev/null && \
  echo "  ✓ MMAudio" || echo "  ✗ MMAudio failed"

echo "  → AudioX..."
$PIP --no-deps git+https://github.com/ZeyueT/AudioX.git 2>/dev/null && \
  echo "  ✓ AudioX" || echo "  ✗ AudioX failed"

echo "  → SAM-Audio..."
$PIP --no-deps git+https://github.com/facebookresearch/sam-audio.git 2>/dev/null && \
  echo "  ✓ SAM-Audio" || echo "  ✗ SAM-Audio failed"

echo "  → dacvae..."
$PIP --no-deps git+https://github.com/facebookresearch/dacvae.git 2>/dev/null && \
  echo "  ✓ dacvae" || echo "  ✗ dacvae failed"

echo "  → perception_models..."
$PIP --no-deps git+https://github.com/facebookresearch/perception_models@unpin-deps 2>/dev/null && \
  echo "  ✓ perception_models" || echo "  ✗ perception_models failed"

# --- Step 2: Pip packages from requirements ---
echo ""
echo "[2/3] Installing pip packages..."
$PIP -r "$SCRIPT_DIR/requirements-optional.txt" && \
  echo "  ✓ All pip packages installed" || echo "  ✗ Some pip packages failed"

# --- Step 3: Verify ---
echo ""
echo "[3/3] Verifying imports..."
$PYTHON -c "
failures = []
for mod in ['sam3', 'simple_lama_inpainting', 'mmaudio', 'sam_audio', 'dacvae',
            'torchdiffeq', 'xformers', 'torchcodec', 'pydub']:
    try:
        __import__(mod)
        print(f'  ✓ {mod}')
    except ImportError as e:
        print(f'  ✗ {mod}: {e}')
        failures.append(mod)
if failures:
    print(f'\n⚠  {len(failures)} package(s) failed to import — see above')
else:
    print('\n✅ All packages imported successfully!')
"

echo ""
echo "============================================"
echo "  Done! Restart ComfyUI to use new features."
echo "============================================"
