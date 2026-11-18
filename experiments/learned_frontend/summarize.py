"""Collect learned-frontend runs into a CSV, match gallery and point-cloud strips.

Run from the repository root after the reconstruction commands in reproduce.sh.
Missing runs are recorded as failed rows instead of being dropped.
"""

import csv
import json
from pathlib import Path
import shutil

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/learned_frontend"
FIGURES = OUT / "figures"
REGIONS = ROOT / "data/evaluation/double_helix_ribbon_regions.json"
RUNS = (
    ("helix49", "sift_ratio", ROOT / "outputs/learned_frontend/helix_sift"),
    ("helix49", "sift_lightglue", ROOT / "outputs/learned_frontend/helix_sift_lightglue"),
    ("helix49", "superpoint_lightglue", ROOT / "outputs/learned_frontend/helix_superpoint_lightglue"),
    ("smoke8", "sift_ratio", ROOT / "outputs/learned_frontend/smoke_sift"),
    ("smoke8", "sift_lightglue", ROOT / "outputs/learned_frontend/smoke_sift_lightglue"),
    ("smoke8", "superpoint_lightglue", ROOT / "outputs/learned_frontend/smoke_superpoint_lightglue"),
)
FIELDS = (
    "split", "method", "status", "frames", "registered_cameras", "scene_points",
    "ribbon_supported_points", "reprojection_rmse_px", "reprojection_median_px",
    "features_total", "features_per_image_mean", "keypoints_in_ribbon",
    "keypoint_ribbon_fraction", "pairs_tested", "pairs_verified",
    "tentative_matches", "ransac_inliers", "ransac_inlier_ratio",
    "runtime_s", "peak_gpu_memory_mb", "run_dir", "notes",
)


def read_json(path):
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def ribbon_masks(run):
    regions = read_json(REGIONS)
    inputs = read_json(run / "inputs.json")
    if regions is None or inputs is None or inputs.get("sha256") != regions["video_sha256"]:
        return None
    width, height = regions["preview_size"]
    erosion = regions["erosion_preview_px"]
    kernel = np.ones((2 * erosion + 1,) * 2, dtype=np.uint8)
    masks = {}
    for frame in inputs["frames"]:
        polygons = regions["polygons_by_source_frame"].get(str(frame["source_frame"]))
        if polygons is None:
            continue
        mask = np.zeros((height, width), dtype=np.uint8)
        for polygon in polygons:
            cv2.fillPoly(mask, [np.array(polygon, dtype=np.int32)], 1)
        masks[frame["id"]] = (cv2.erode(mask, kernel), frame["work_size"], width, height)
    return masks


def ribbon_keypoints(run):
    masks = ribbon_masks(run)
    cache = run / "appearance.npz"
    if masks is None or not cache.is_file():
        return None, None
    inside = total = 0
    with np.load(cache) as arrays:
        for frame_id, (mask, work_size, width, height) in masks.items():
            xy = arrays[f"xy_{frame_id}"]
            if len(xy) == 0:
                continue
            factor = np.array([width, height]) / work_size
            u, v = np.rint((xy + 0.5) * factor - 0.5).astype(int).T
            valid = (u >= 0) & (u < width) & (v >= 0) & (v < height)
            total += len(xy)
            inside += int(mask[v[valid], u[valid]].sum())
    if total == 0:
        return 0, 0.0
    return inside, inside / total


def pair_totals(pairs):
    if not pairs:
        return None
    tentative = sum(int(row.get("mutual", 0)) for row in pairs)
    inliers = sum(int(row.get("ransac_inliers", 0)) for row in pairs)
    verified = sum(row.get("status") == "verified" for row in pairs)
    return {
        "pairs_tested": len(pairs),
        "pairs_verified": verified,
        "tentative_matches": tentative,
        "ransac_inliers": inliers,
        "ransac_inlier_ratio": None if tentative == 0 else inliers / tentative,
    }


def row_for(split, method, run):
    metrics = read_json(run / "metrics.json")
    frontend = read_json(run / "frontend.json") or {}
    audit = read_json(run / "audit/ribbon_audit.json")
    pairs = read_json(run / "pairs.json")
    per_view = run / "per_view.csv"
    notes = ""
    if metrics is None:
        return {"split": split, "method": method, "status": "missing_or_failed",
                "run_dir": str(run), "notes": "metrics.json was not written"}
    features = []
    if per_view.is_file():
        import csv as csvmod
        with per_view.open() as handle:
            features = [int(item["features"]) for item in csvmod.DictReader(handle)]
    ribbon_hits, ribbon_fraction = ribbon_keypoints(run)
    totals = pair_totals(pairs) or {}
    reprojection = metrics.get("final_reprojection_px") or {}
    elapsed = metrics.get("elapsed_seconds") or {}
    return {
        "split": split,
        "method": method,
        "status": metrics.get("status"),
        "frames": metrics.get("views"),
        "registered_cameras": metrics.get("registered"),
        "scene_points": metrics.get("points"),
        "ribbon_supported_points": None if audit is None else audit.get("ribbon_supported_points"),
        "reprojection_rmse_px": reprojection.get("rmse"),
        "reprojection_median_px": reprojection.get("median"),
        "features_total": sum(features) if features else None,
        "features_per_image_mean": (sum(features) / len(features)) if features else None,
        "keypoints_in_ribbon": ribbon_hits,
        "keypoint_ribbon_fraction": ribbon_fraction,
        "runtime_s": elapsed.get("total"),
        "peak_gpu_memory_mb": frontend.get("peak_gpu_memory_mb", 0 if method == "sift_ratio" else None),
        "run_dir": str(run.relative_to(ROOT)),
        "notes": notes,
        **totals,
    }


def labeled_strip(items, destination):
    tiles = []
    target_h = 420
    for label, path in items:
        image = cv2.imread(str(path))
        if image is None:
            continue
        scale = target_h / image.shape[0]
        image = cv2.resize(image, (round(image.shape[1] * scale), target_h),
                           interpolation=cv2.INTER_AREA)
        cv2.rectangle(image, (0, 0), (image.shape[1], 28), (255, 255, 255), -1)
        cv2.putText(image, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20),
                    1, cv2.LINE_AA)
        tiles.append(image)
    if len(tiles) < 2:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(destination), np.hstack(tiles))


def copy_matches(split, method, run):
    figures = run / "figures"
    if not figures.is_dir():
        return
    FIGURES.mkdir(parents=True, exist_ok=True)
    for path in sorted(figures.glob("matches_*.jpg")):
        shutil.copyfile(path, FIGURES / f"{split}_{method}_{path.name}")


def main():
    rows = []
    for split, method, run in RUNS:
        if not run.exists() and split == "smoke8":
            continue
        record = row_for(split, method, run)
        rows.append(record)
        copy_matches(split, method, run)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in rows:
            writer.writerow({key: record.get(key, "") for key in FIELDS})
    helix = [(method, ROOT / "outputs/learned_frontend" / name) for method, name in (
        ("sift_ratio", "helix_sift"),
        ("sift_lightglue", "helix_sift_lightglue"),
        ("superpoint_lightglue", "helix_superpoint_lightglue"),
    )]
    labeled_strip([(method, run / "figures/scene_and_cameras.png") for method, run in helix],
                  FIGURES / "helix49_scene_side_by_side.jpg")
    labeled_strip([(method, run / "audit/ribbon_and_cameras.png") for method, run in helix],
                  FIGURES / "helix49_ribbon_side_by_side.jpg")
    print(f"Wrote {OUT / 'results.csv'} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
