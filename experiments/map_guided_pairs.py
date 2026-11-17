"""Pose-guided geometric verification of extra native appearance matches.

Only added pairs are eligible. The output is rebuilt by the native mapper,
using the same original initial focal, not using the guide as fixed poses.
"""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import cv2
import numpy as np

from experiments.compare_sparse import input_manifest
from experiments.native_ablation import map_prepared
from sfm.data import appearance_key, load_appearance, save_appearance, sha256
from sfm.export import contact_sheet, write_json
from sfm.geometry import homogeneous, sampson_signed, skew
from sfm.model import Camera, Frame, Pose
from sfm.triangulation import angle_degrees, error_and_depth, triangulate_dlt, unit


def guide_pair(pair, frames, poses, camera, cfg):
    a, b = poses[pair.i], poses[pair.j]
    pixels_a = frames[pair.i].xy[pair.indices[:, 0]]
    pixels_b = frames[pair.j].xy[pair.indices[:, 1]]
    rays_a, rays_b = camera.normalize(pixels_a), camera.normalize(pixels_b)
    R = b.R @ a.R.T
    E = skew(b.t - R @ a.t) @ R
    errors = camera.focal * np.abs(sampson_signed(E, homogeneous(rays_a), homogeneous(rays_b)))
    candidate = np.flatnonzero((errors <= cfg["sampson_px"]) & ~pair.inliers)
    if not len(candidate):
        return 0
    mats = np.stack((a.matrix, b.matrix))
    observed = np.stack((rays_a[candidate], rays_b[candidate]), axis=1)
    xyz = triangulate_dlt(mats, observed)
    err_a, z_a = error_and_depth(camera, a, xyz, pixels_a[candidate])
    err_b, z_b = error_and_depth(camera, b, xyz, pixels_b[candidate])
    angles = angle_degrees(unit(xyz - a.center), unit(xyz - b.center))
    keep = candidate[(z_a > 0) & (z_b > 0) & (angles >= cfg["min_angle"]) &
                     (np.maximum(err_a, err_b) <= cfg["final_pixel_gate"])]
    if not len(keep):
        return 0
    pair.inliers[keep] = True
    pair.errors[keep] = errors[keep]
    if pair.F is None:
        inv = np.linalg.inv(camera.K)
        pair.F = inv.T @ E @ inv
    pair.counts.update(guided_added=len(keep), final_verified_edges=int(pair.inliers.sum()),
                       status="verified_with_native_pose_guidance")
    return len(keep)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="Native run with original pair schedule")
    parser.add_argument("guide", type=Path, help="Native extended-window result")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    ref, guide, out = args.reference.resolve(), args.guide.resolve(), args.output.resolve()
    inputs = json.loads((guide / "inputs.json").read_text())
    configs = [json.loads((run / "config.resolved.json").read_text()) for run in (ref, guide)]
    cfg = configs[1]
    if {key for key in cfg if configs[0][key] != cfg[key]} != {"window"}:
        raise ValueError("Guide must differ only in the pair window")
    manifest = input_manifest(ref)
    if manifest != input_manifest(guide):
        raise ValueError("Guide needs the exact original saved frame geometry and hashes")
    cv2.setNumThreads(1)
    cv2.setRNGSeed(cfg["seed"] % (2 ** 31))
    frames = [Frame(row["id"], row, cv2.imread(str(ref / row["file"]))) for row in inputs["frames"]]
    pairs = load_appearance(guide, frames, appearance_key(inputs, cfg))
    original_pairs = {(p["i"], p["j"]) for p in json.loads((ref / "pairs.json").read_text())}
    with np.load(guide / "reconstruction.npz") as model:
        poses = {int(i): Pose(R, t) for i, R, t in zip(
            model["image_ids"], model["R_cw"], model["t_cw"], strict=True
        )}
        K = model["K_work"]
        camera = Camera(K[0, 0], K[0, 2], K[1, 2], float(model["k1"]))
    if len(poses) != len(frames) or camera.k1 != 0:
        raise ValueError("This experiment requires a complete zero-distortion guide")
    out.mkdir(parents=True)
    (out / "frames").symlink_to(ref / "frames", target_is_directory=True)
    (out / "figures").mkdir()
    contact_sheet(frames, out / "figures/contact_sheet.jpg")
    stage = perf_counter()
    scores = {}
    for pair in pairs:
        key = (pair.i, pair.j)
        if key not in original_pairs and len(pair.indices):
            added = guide_pair(pair, frames, poses, camera, cfg)
            if added:
                scores[key] = added
    record = {
        "command": [sys.executable, "-m", "experiments.map_guided_pairs", *sys.argv[1:]],
        "reference": str(ref), "guide": str(guide),
        "guide_reconstruction_sha256": sha256(guide / "reconstruction.npz"),
        "elapsed_seconds": {"guide_existing_raw_matches": perf_counter() - stage},
        "guided_edges_added": sum(scores.values()),
        "guided_pairs": [{"i": i, "j": j, "added": n} for (i, j), n in scores.items()],
        "evaluation_labels_used_in_reconstruction": False,
        "reuses": "Work PNGs and original cached mutual descriptor matches",
        "secondary_pass_timing_excludes": "Upstream native window-6 run",
    }
    write_json(out / "frame_manifest.json", manifest)
    write_json(out / "inputs.json", inputs)
    write_json(out / "config.resolved.json", cfg)
    key = {**appearance_key(inputs, cfg), "geometry_verification": "native_map_guided",
           "guide_reconstruction_sha256": record["guide_reconstruction_sha256"]}
    save_appearance(out, frames, pairs, key)
    print(f"Guided pass added {record['guided_edges_added']} edges in {len(scores)} pairs", flush=True)
    return map_prepared(ref, out, frames, cfg, pairs, record)


if __name__ == "__main__":
    sys.exit(main())
