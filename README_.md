# AI6121 Project · Double Helix Sparse SfM

[简体中文](README.zh.md)

This CPU pipeline reconstructs a colored scene point cloud, camera poses, and shared intrinsics from the [NTU Double Helix video](data/video/double_helix.mp4). The main route is `feat/sift-calibrated-sfm`. The `feat/manual-projective-sfm` branch preserves the manual-landmark projective geometry baseline.

## Run

Use Python 3.11 from the repository root.

```bash
python3.11 -m venv .venv-sfm
. .venv-sfm/bin/activate
pip install -r requirements.txt
export OPENBLAS_NUM_THREADS=1
export MPLCONFIGDIR=/tmp/ai6121-mpl

python -m unittest discover -s tests -v
python -m sfm inspect --video data/video/double_helix.mp4 --output outputs/inspection_demo
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --output outputs/orbit_repro
python -m sfm.audit outputs/orbit_repro --output outputs/orbit_repro/audit
```

The run directory contains a colored PLY, per-frame camera parameters and registration status, original pixel observations and active tracks, metrics, matches, reprojection overlays, and input and dependency provenance. The audit exports a sculpture-supported subset and evidence overlays. The reconstruction scale is arbitrary. Use a new output path for each run.

[Experiments and reproduction](docs/SFM_RESULTS.md) · [Architecture](docs/SFM_ARCHITECTURE.md) 

Build the LaTeX report with `cd report && latexmk main.tex`. The cover has fields for team names and matriculation numbers.
