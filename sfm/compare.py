"""Compare runs with identical frame sampling after similarity-aligning common cameras."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .bundle import distribution
from .export import write_json


def compare(reference, candidate):
    inputs = [json.loads((run / "inputs.json").read_text()) for run in (reference, candidate)]
    keys = ("source_frame", "work_size", "oriented_to_work")
    frame_lists = [[tuple(row[key] for key in keys) for row in entry["frames"]] for entry in inputs]
    if inputs[0]["sha256"] != inputs[1]["sha256"] or frame_lists[0] != frame_lists[1]:
        raise ValueError("Comparison requires identical input video, selected frames and work transforms")
    metrics = json.loads((candidate / "metrics.json").read_text())
    result = {key: metrics[key] for key in (
        "status", "views", "registered", "points", "initial_focal_work_px", "estimated_focal_work_px",
        "estimated_k1", "final_reprojection_px", "active_track_lengths",
    )}
    result["run"] = str(candidate)
    paths = [run / "reconstruction.npz" for run in (reference, candidate)]
    if not all(path.exists() for path in paths):
        return result
    datasets = []
    for path in paths:
        with np.load(path) as data:
            datasets.append(dict(data))
    ref, new = datasets
    ids, i, j = np.intersect1d(ref["image_ids"], new["image_ids"], return_indices=True)
    result["shared_cameras"] = ids
    if len(ids) < 3:
        return result
    ref_R, new_R = ref["R_cw"][i], new["R_cw"][j]
    ref_C = -np.einsum("nji,nj->ni", ref_R, ref["t_cw"][i])
    new_C = -np.einsum("nji,nj->ni", new_R, new["t_cw"][j])
    a, b = new_C - new_C.mean(axis=0), ref_C - ref_C.mean(axis=0)
    if min(np.linalg.matrix_rank(a), np.linalg.matrix_rank(b)) < 2:
        return result
    u, s, v = np.linalg.svd(a.T @ b)
    correction = np.array([1, 1, np.linalg.det(u @ v)])
    rotation = (u * correction) @ v
    scale = (s @ correction) / np.sum(a ** 2)
    ref_scale = np.sqrt(np.mean(np.sum(b ** 2, axis=1)))
    c_errors = np.linalg.norm(scale * a @ rotation - b, axis=1) / ref_scale
    r_errors = np.rad2deg(Rotation.from_matrix(new_R @ rotation @ ref_R.transpose(0, 2, 1)).magnitude())
    result["camera_error_divided_by_reference_orbit_rms_radius"] = distribution(c_errors)
    result["camera_rotation_difference_deg"] = distribution(r_errors)

    track_files = [json.loads((run / "tracks.json").read_text()) for run in (reference, candidate)]
    signatures = [
        [tuple((o["image_id"], tuple(o["xy_work_distorted"])) for o in row["observations"]) for row in tracks]
        for tracks in track_files
    ]
    new_index = {signatures[1][tid]: k for k, tid in enumerate(new["track_ids"])}
    shared = [(k, new_index[signatures[0][tid]]) for k, tid in enumerate(ref["track_ids"])
              if signatures[0][tid] in new_index]
    if shared:
        k, l = np.array(shared).T
        aligned_xyz = scale * (new["xyz"][l] - new_C.mean(axis=0)) @ rotation + ref_C.mean(axis=0)
        normalized_error = np.linalg.norm(aligned_xyz - ref["xyz"][k], axis=1) / ref_scale
        result["common_track_3d_difference_divided_by_reference_orbit_rms_radius"] = distribution(
            normalized_error
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_json(args.output, {"reference": str(args.reference),
                             "runs": [compare(args.reference, run) for run in args.runs]})
