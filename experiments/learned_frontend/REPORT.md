# Learned feature matching for the Double Helix

## Methodology

SIFT's ratio test misses correspondences on the low-texture metal ribbon of the NTU Double Helix. This experiment replaces only the feature frontend. Geometric verification, relative pose, PnP, triangulation, bundle adjustment, and the ribbon audit are the project's existing CPU backend. COLMAP, hloc, and other full reconstruction systems were not used.

Two official pretrained frontends from [cvg/LightGlue](https://github.com/cvg/LightGlue) were compared with the original SIFT ratio test:

- **SIFT + LightGlue.** Detection is the project's grid-sampled OpenCV SIFT, so the keypoint set matches the baseline. Descriptors are converted with LightGlue's RootSIFT (L1 normalize, square root, L2 normalize), which is the normalization expected by the pretrained SIFT matcher. Scale and orientation are passed through.
- **SuperPoint + LightGlue.** SuperPoint v1 detects and describes keypoints. Its internal resize is disabled, so coordinates stay in the 720×1280 work image. The 720×1280 frames are already multiples of SuperPoint's stride of 8, so no padding was applied.

LightGlue was run on an NVIDIA RTX 4080 in `torch.inference_mode`, with all 9 layers enabled (`depth_confidence = -1`, `width_confidence = -1`) and `filter_threshold = 0.1`. SuperPoint kept at most 4096 keypoints. Image pairs, the 49-frame schedule, intrinsics initialization (`focal_factor = 0.65`), RANSAC, and quality gates all come from `configs/orbit49_balanced.json`. Each image is described once and then reused for every pair.

## Experimental setup

The same-machine SIFT baseline was rerun into `outputs/learned_frontend/helix_sift`. It reproduced the published record exactly: 49/49 cameras, 12,609 points, 399 ribbon-supported points, focal length 619.24 px, reprojection RMSE 0.430 px. Published files under `report_reference/` were not modified.

An 8-frame uniform sample was used only as a compatibility check. Those frames are widely separated, so every method returned a partial model. The sample is not a reconstruction result. The repository does not contain the Boxes video, so that generalization run was not attempted.

External software, loaded at runtime from the official release URLs:

- PyTorch 2.6.0+cu124 and torchvision 0.21.0+cu124
- Kornia 0.9.2
- LightGlue 0.0 (cvg/LightGlue `main`; installed from the GitHub source tarball after a git clone failed)
- `superpoint_v1.pth`, `sift_lightglue.pth`, and `superpoint_lightglue.pth` from `https://github.com/cvg/LightGlue/releases/download/v0.1_arxiv/`

A generative coding assistant implemented the frontend adapter, experiment runner, and this write-up. It did not change the geometric solver or the evaluation masks.

## Results

Quantities below are for the 49-frame Double Helix run. Tentative matches are the correspondences passed to the unchanged RANSAC. Ribbon points use `data/evaluation/double_helix_ribbon_regions.json` and `python -m sfm.audit`.

| Method | Cameras | Scene points | Ribbon points | RMSE (px) | Median (px) | Features | In-ribbon keypoints | Tentative matches | RANSAC inliers | Inlier ratio | Verified pairs | Runtime (s) | Peak GPU (MB) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SIFT ratio | 49/49 | 12,609 | 399 | 0.430 | 0.226 | 219,546 | 9,583 (4.4%) | 29,168 | 25,598 | 0.878 | 133/150 | 332.4 | 0 |
| SIFT + LightGlue | 49/49 | 31,703 | 1,152 | 0.700 | 0.407 | 219,546 | 9,583 (4.4%) | 132,682 | 109,325 | 0.824 | 150/150 | 413.5 | 818 |
| SuperPoint + LightGlue | 46/49 | 18,131 | 1,888 | 0.995 | 0.689 | 138,809 | 14,165 (10.2%) | 130,405 | 97,351 | 0.747 | 150/150 | 263.9 | 655 |

SIFT + LightGlue kept the same 219,546 detections and the same 9,583 keypoints inside the ribbon masks. The matcher, not the detector, produced the gain: every one of the 150 pairs was verified, against 133 for the ratio test, and ribbon-supported points rose from 399 to 1,152. The estimated focal length stayed at 619.87 px, against 619.24 px for the baseline. Matching and verification fell from 185.5 s to 9.4 s. Total runtime rose to 413.5 s because bundle adjustment received more points. Reprojection RMSE increased from 0.430 px to 0.700 px, so the extra points are less precise, but they remain inside the existing 3 px gate.

SuperPoint spent 1.4 s extracting features and placed 10.2% of them inside the ribbon masks, against 4.4% for SIFT, despite using fewer keypoints overall. It produced the largest ribbon-supported set, 1,888 points, and the ribbon plot shows a clearer helical twist. Registration stopped at 46/49 cameras. Work frames 19, 20, and 21 (source frames 394, 415, and 435) were rejected by PnP refinement, which opens a gap in the orbit. RMSE rose to 0.995 px. All 150 pairs were still geometrically verified, so the failure is in incremental registration rather than in the absence of matches.

On the 8-frame wide-baseline check, verified pairs were 1/26 (SIFT), 10/26 (SIFT + LightGlue), and 20/26 (SuperPoint + LightGlue). All three reconstructions stayed partial because the seed pair was the distant loop pair. That check only shows that the new matchers plug into the same pair and geometry code.

## Limitations

The two learned models were not trained on this sculpture, and no weights were fine-tuned. SIFT + LightGlue cannot invent keypoints on blank metal; it only matches the SIFT points that already exist. SuperPoint's denser ribbon comes with a missing camera triplet and a higher residual. World scale remains arbitrary, and the side-by-side plots are not similarity-aligned. Peak GPU memory is the PyTorch allocation peak during extraction and matching on one RTX 4080.

## Conclusion

SIFT + LightGlue is the frontend that improves the Double Helix model without giving up a registered camera. With the same detections, calibration, pairs, and backend, it verifies every scheduled pair and nearly triples the ribbon-supported points, at a higher but still sub-pixel RMSE. SuperPoint + LightGlue is the stronger detector for the textureless ribbon and the best ribbon-point count, but the 46/49 partial model should not replace the baseline on point count alone.

## Reproduction

From the repository root, with the project virtualenv:

```bash
bash experiments/learned_frontend/reproduce.sh
```

The commands actually used for the numbers above are:

```bash
source .venv-sfm/bin/activate
export OPENBLAS_NUM_THREADS=1 MPLCONFIGDIR=/tmp/ai6121-mpl
python -m pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 \
  --index-url https://download.pytorch.org/whl/cu124
python -m pip install "kornia>=0.7.3"
curl -L -o /tmp/lightglue.tar.gz \
  https://codeload.github.com/cvg/LightGlue/tar.gz/refs/heads/main
tar -xzf /tmp/lightglue.tar.gz -C /tmp
python -m pip install --no-deps /tmp/LightGlue-main

python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json \
  --output outputs/learned_frontend/helix_sift
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --frontend sift_lightglue \
  --output outputs/learned_frontend/helix_sift_lightglue
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --frontend superpoint_lightglue \
  --output outputs/learned_frontend/helix_superpoint_lightglue
python -m sfm.audit outputs/learned_frontend/helix_sift \
  --output outputs/learned_frontend/helix_sift/audit
python -m sfm.audit outputs/learned_frontend/helix_sift_lightglue \
  --output outputs/learned_frontend/helix_sift_lightglue/audit
python -m sfm.audit outputs/learned_frontend/helix_superpoint_lightglue \
  --output outputs/learned_frontend/helix_superpoint_lightglue/audit
python experiments/learned_frontend/summarize.py
```

`--frontend` defaults to `sift`, so the original command is unchanged. A partial model returns exit code 3, which is the SuperPoint outcome and the expected 8-frame outcome.

Artifacts:

- `experiments/learned_frontend/results.csv`
- `experiments/learned_frontend/figures/helix49_scene_side_by_side.jpg`
- `experiments/learned_frontend/figures/helix49_ribbon_side_by_side.jpg`
- `experiments/learned_frontend/figures/helix49_*_matches_*.jpg` for the seed, weakest adjacent, and loop pairs
- per-run outputs under `outputs/learned_frontend/`
