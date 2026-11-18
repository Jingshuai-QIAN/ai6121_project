#!/usr/bin/env bash
# Learned matching frontend for the Double Helix sequence.
# Run from the repository root. Existing report_reference/ results are not modified.
set -euo pipefail
# Partial reconstructions return 3. That is a recorded outcome, not an aborted run.
run_sfm() {
  set +e
  python -m sfm reconstruct "$@"
  code=$?
  set -e
  if [ "$code" -ne 0 ] && [ "$code" -ne 3 ]; then
    exit "$code"
  fi
}
cd "$(dirname "$0")/../.."
source .venv-sfm/bin/activate
export OPENBLAS_NUM_THREADS=1
export MPLCONFIGDIR=/tmp/ai6121-mpl

python -m pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 \
  --index-url https://download.pytorch.org/whl/cu124
python -m pip install "kornia>=0.7.3"
# The git+ URL is the upstream install. If that clone fails, use the source tarball
# and --no-deps so pip does not replace opencv-python-headless.
if ! python -m pip install "git+https://github.com/cvg/LightGlue.git"; then
  curl -L --retry 5 -o /tmp/lightglue.tar.gz \
    https://codeload.github.com/cvg/LightGlue/tar.gz/refs/heads/main
  rm -rf /tmp/LightGlue-main
  tar -xzf /tmp/lightglue.tar.gz -C /tmp
  python -m pip install --no-deps /tmp/LightGlue-main
fi

COMMON=(--video data/video/double_helix.mp4 --config configs/orbit49_balanced.json)

# Compatibility check on 8 uniformly sampled frames.
run_sfm "${COMMON[@]}" --frames 8 \
  --output outputs/learned_frontend/smoke_sift
run_sfm "${COMMON[@]}" --frames 8 --frontend sift_lightglue \
  --output outputs/learned_frontend/smoke_sift_lightglue
run_sfm "${COMMON[@]}" --frames 8 --frontend superpoint_lightglue \
  --output outputs/learned_frontend/smoke_superpoint_lightglue

# Full 49-frame experiment. The SIFT ratio-test run is the same-machine baseline.
run_sfm "${COMMON[@]}" \
  --output outputs/learned_frontend/helix_sift
run_sfm "${COMMON[@]}" --frontend sift_lightglue \
  --output outputs/learned_frontend/helix_sift_lightglue
run_sfm "${COMMON[@]}" --frontend superpoint_lightglue \
  --output outputs/learned_frontend/helix_superpoint_lightglue

python -m sfm.audit outputs/learned_frontend/helix_sift \
  --output outputs/learned_frontend/helix_sift/audit
python -m sfm.audit outputs/learned_frontend/helix_sift_lightglue \
  --output outputs/learned_frontend/helix_sift_lightglue/audit
python -m sfm.audit outputs/learned_frontend/helix_superpoint_lightglue \
  --output outputs/learned_frontend/helix_superpoint_lightglue/audit

python experiments/learned_frontend/summarize.py
