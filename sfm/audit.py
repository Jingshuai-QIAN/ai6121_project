"""Audit whether reconstructed tracks land on visible metal, using evaluation-only regions."""

import argparse
from collections import Counter
import json
from pathlib import Path

import cv2
import numpy as np

from .export import plot_map, write_json, write_ply
from .model import Camera, Pose


def audit(run, annotations, output):
    regions = json.loads(annotations.read_text())
    inputs = json.loads((run / "inputs.json").read_text())
    if inputs["sha256"] != regions["video_sha256"]:
        raise ValueError("The annotation video hash does not match this run")
    tracks = json.loads((run / "tracks.json").read_text())
    with np.load(run / "reconstruction.npz") as reconstruction:
        xyz = reconstruction["xyz"]
        rgb = reconstruction["rgb"]
        tids = reconstruction["track_ids"]
        poses = {int(i): Pose(R, t) for i, R, t in zip(
            reconstruction["image_ids"], reconstruction["R_cw"], reconstruction["t_cw"], strict=True
        )}
        K = reconstruction["K_work"]
        camera = Camera(K[0, 0], K[0, 2], K[1, 2], float(reconstruction["k1"]))

    width, height = regions["preview_size"]
    masks = {}
    for frame in inputs["frames"]:
        key = str(frame["source_frame"])
        if frame["id"] not in poses or key not in regions["polygons_by_source_frame"]:
            continue
        mask = np.zeros((height, width), dtype=np.uint8)
        for polygon in regions["polygons_by_source_frame"][key]:
            cv2.fillPoly(mask, [np.array(polygon, dtype=np.int32)], 1)
        erosion = regions["erosion_preview_px"]
        masks[frame["id"]] = cv2.erode(mask, np.ones((2 * erosion + 1,) * 2, dtype=np.uint8))

    minimum = regions["required_active_views"]
    checked = []
    near_region = Counter()
    confirmed = []
    for j, tid in enumerate(tids):
        hits = []
        audited_views = 0
        for obs in tracks[tid]["observations"]:
            i = obs["image_id"]
            if not obs["active"] or i not in masks:
                continue
            audited_views += 1
            projected, depth = camera.project_camera(poses[i].transform(xyz[j]))
            factor = np.array([width, height]) / inputs["frames"][i]["work_size"]
            hit = depth > 0
            for pixel in (obs["xy_work_distorted"], projected):
                u, v = np.rint((np.array(pixel) + 0.5) * factor - 0.5).astype(int)
                hit &= 0 <= u < width and 0 <= v < height and bool(masks[i][v, u])
            if hit:
                near_region[i] += 1
                hits.append(i)
        if len(hits) >= minimum:
            confirmed.append(j)
        checked.append((int(tid), audited_views, hits))

    output.mkdir(parents=True)
    confirmed_ids = {int(tids[index]) for index in confirmed}
    tiles = []
    per_view = []
    for i, mask in masks.items():
        frame = inputs["frames"][i]
        image = cv2.resize(cv2.imread(str(run / frame["file"])), (width, height),
                           interpolation=cv2.INTER_AREA)
        overlay = image.copy()
        overlay[mask > 0] = (55, 213, 137)
        image = cv2.addWeighted(image, .72, overlay, .28, 0)
        count = 0
        for tid, _, hits in checked:
            if (tid not in confirmed_ids) or i not in hits:
                continue
            obs = next(obs for obs in tracks[tid]["observations"] if obs["image_id"] == i)
            xy = (np.array(obs["xy_work_distorted"]) + 0.5) * (
                np.array([width, height]) / frame["work_size"]
            ) - 0.5
            uv = tuple(np.rint(xy).astype(int))
            cv2.circle(image, uv, 4, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(image, uv, 2, (255, 245, 80), -1, cv2.LINE_AA)
            count += 1
        cv2.rectangle(image, (0, 0), (width, 24), (28, 28, 28), -1)
        cv2.putText(image, f'Frame {frame["source_frame"]:03d} | {count} confirmed obs.', (8, 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(image)
        per_view.append({"image_id": i, "source_frame": frame["source_frame"],
                         "in_region": near_region[i], "confirmed_observations": count})
    if tiles:
        columns = min(5, len(tiles))
        while len(tiles) % columns:
            tiles.append(np.full_like(tiles[0], 245))
        cv2.imwrite(str(output / "ribbon_support.jpg"), np.vstack([
            np.hstack(tiles[i:i+columns]) for i in range(0, len(tiles), columns)
        ]))
    if confirmed:
        write_ply(output / "ribbon_supported.ply", xyz[confirmed], rgb[confirmed])
        plot_map(output / "ribbon_and_cameras.png", xyz[confirmed], rgb[confirmed], poses,
                 subset_label="Ribbon-supported subset")
        plot_map(output / "ribbon_closeup.png", xyz[confirmed], rgb[confirmed], poses,
                 subset_label="Metal ribbon observations in 3D", show_cameras=False)
    result = {
        "run": str(run), "annotations": str(annotations), "scene_points": len(xyz),
        "at_least_two_auditable_views": sum(audited >= minimum for _, audited, _ in checked),
        "with_region_hit": sum(bool(hits) for _, _, hits in checked),
        "ribbon_supported_points": len(confirmed), "required_active_views": minimum,
        "ribbon_support_lengths": dict(Counter(len(hits) for tid, _, hits in checked
                                              if tid in confirmed_ids)),
        "per_view": per_view,
        "confirmed_tracks": [{"id": tid, "hit_image_ids": hits} for tid, _, hits in checked
                             if tid in confirmed_ids],
    }
    write_json(output / "ribbon_audit.json", result)
    print(f"{len(confirmed)}/{len(xyz)} points supported by ribbon regions in {minimum}+ active views")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--regions", type=Path,
                        default=Path("data/evaluation/double_helix_ribbon_regions.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.run.resolve(), args.regions.resolve(), args.output.resolve())
