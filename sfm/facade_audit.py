"""Audit reconstructed UOB Innovation Hub points against facade annotations."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import cv2
import numpy as np

from .export import plot_map, write_json, write_ply
from .model import Camera, Pose


def validate_regions(regions: dict) -> None:
    required = {
        "video_sha256", "preview_size", "erosion_preview_px",
        "polygons_by_source_frame",
    }
    missing = sorted(required - regions.keys())
    if missing:
        raise ValueError(f"annotation file is missing keys: {missing}")
    width, height = regions["preview_size"]
    if width <= 0 or height <= 0:
        raise ValueError("preview_size must contain positive width and height")
    for source_frame, polygons in regions["polygons_by_source_frame"].items():
        for polygon in polygons:
            if len(polygon) < 3:
                raise ValueError(f"source frame {source_frame} has a polygon with fewer than 3 points")


def audit(run: Path, annotations: Path, output: Path) -> dict:
    regions = json.loads(annotations.read_text(encoding="utf-8"))
    validate_regions(regions)
    inputs = json.loads((run / "inputs.json").read_text(encoding="utf-8"))
    if inputs["sha256"] != regions["video_sha256"]:
        raise ValueError("the annotation video hash does not match this run")
    tracks = json.loads((run / "tracks.json").read_text(encoding="utf-8"))
    with np.load(run / "reconstruction.npz") as reconstruction:
        xyz = reconstruction["xyz"]
        rgb = reconstruction["rgb"]
        tids = reconstruction["track_ids"]
        poses = {int(i): Pose(R, t) for i, R, t in zip(
            reconstruction["image_ids"], reconstruction["R_cw"],
            reconstruction["t_cw"], strict=True
        )}
        K = reconstruction["K_work"]
        camera = Camera(K[0, 0], K[0, 2], K[1, 2], float(reconstruction["k1"]))

    width, height = regions["preview_size"]
    masks = {}
    for frame in inputs["frames"]:
        source_key = str(frame["source_frame"])
        polygons = regions["polygons_by_source_frame"].get(source_key, [])
        if frame["id"] not in poses or not polygons:
            continue
        mask = np.zeros((height, width), dtype=np.uint8)
        for polygon in polygons:
            cv2.fillPoly(mask, [np.asarray(polygon, dtype=np.int32)], 1)
        erosion = int(regions["erosion_preview_px"])
        if erosion:
            kernel = np.ones((2 * erosion + 1,) * 2, dtype=np.uint8)
            mask = cv2.erode(mask, kernel)
        masks[frame["id"]] = mask

    if len(masks) < 2:
        raise ValueError("annotate at least two registered frames before running the audit")

    checked = []
    per_view_hits = Counter()
    for point_index, tid_value in enumerate(tids):
        tid = int(tid_value)
        hit_image_ids = []
        auditable_views = 0
        for observation in tracks[tid]["observations"]:
            image_id = observation["image_id"]
            if not observation["active"] or image_id not in masks:
                continue
            auditable_views += 1
            projected, depth = camera.project_camera(poses[image_id].transform(xyz[point_index]))
            factor = np.asarray([width, height]) / inputs["frames"][image_id]["work_size"]
            hit = depth > 0
            for pixel in (observation["xy_work_distorted"], projected):
                u, v = np.rint((np.asarray(pixel) + 0.5) * factor - 0.5).astype(int)
                hit &= 0 <= u < width and 0 <= v < height and bool(masks[image_id][v, u])
            if hit:
                hit_image_ids.append(image_id)
                per_view_hits[image_id] += 1
        checked.append({
            "track_id": tid,
            "point_index": point_index,
            "auditable_views": auditable_views,
            "hit_image_ids": hit_image_ids,
        })

    supported_2 = [item["point_index"] for item in checked if len(item["hit_image_ids"]) >= 2]
    supported_3 = [item["point_index"] for item in checked if len(item["hit_image_ids"]) >= 3]
    supported_2_ids = {int(tids[index]) for index in supported_2}

    output.mkdir(parents=True, exist_ok=True)
    tiles = []
    per_view = []
    for image_id, mask in masks.items():
        frame = inputs["frames"][image_id]
        image = cv2.resize(
            cv2.imread(str(run / frame["file"])), (width, height),
            interpolation=cv2.INTER_AREA
        )
        overlay = image.copy()
        overlay[mask > 0] = (55, 213, 137)
        image = cv2.addWeighted(image, 0.72, overlay, 0.28, 0)
        confirmed_observations = 0
        for item in checked:
            if item["track_id"] not in supported_2_ids or image_id not in item["hit_image_ids"]:
                continue
            observation = next(
                obs for obs in tracks[item["track_id"]]["observations"]
                if obs["image_id"] == image_id
            )
            factor = np.asarray([width, height]) / frame["work_size"]
            uv = np.rint((np.asarray(observation["xy_work_distorted"]) + 0.5) * factor - 0.5)
            uv = tuple(uv.astype(int))
            cv2.circle(image, uv, 4, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(image, uv, 2, (255, 245, 80), -1, cv2.LINE_AA)
            confirmed_observations += 1
        cv2.rectangle(image, (0, 0), (width, 26), (28, 28, 28), -1)
        cv2.putText(
            image,
            f'Frame {frame["source_frame"]:04d} | {confirmed_observations} facade observations',
            (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1, cv2.LINE_AA
        )
        tiles.append(image)
        per_view.append({
            "image_id": image_id,
            "source_frame": frame["source_frame"],
            "region_hits": per_view_hits[image_id],
            "confirmed_2plus_observations": confirmed_observations,
        })

    columns = min(3, len(tiles))
    while len(tiles) % columns:
        tiles.append(np.full_like(tiles[0], 245))
    contact = np.vstack([
        np.hstack(tiles[index:index + columns]) for index in range(0, len(tiles), columns)
    ])
    cv2.imwrite(str(output / "facade_support.jpg"), contact)

    if supported_2:
        write_ply(output / "facade_supported_2plus.ply", xyz[supported_2], rgb[supported_2])
        plot_map(
            output / "facade_and_cameras.png", xyz[supported_2], rgb[supported_2], poses,
            subset_label="Facade-supported subset (2+ views)"
        )
        plot_map(
            output / "facade_closeup.png", xyz[supported_2], rgb[supported_2], poses,
            subset_label="Facade-supported points (2+ views)", show_cameras=False
        )
    if supported_3:
        write_ply(output / "facade_supported_3plus.ply", xyz[supported_3], rgb[supported_3])
        plot_map(
            output / "facade_closeup_3plus.png", xyz[supported_3], rgb[supported_3], poses,
            subset_label="Facade-supported points (3+ views)", show_cameras=False
        )

    support_lengths = Counter(len(item["hit_image_ids"]) for item in checked
                              if item["hit_image_ids"])
    result = {
        "run": str(run),
        "annotations": str(annotations),
        "scene_points": len(xyz),
        "annotated_registered_frames": len(masks),
        "points_auditable_in_2plus_views": sum(
            item["auditable_views"] >= 2 for item in checked
        ),
        "points_with_any_facade_region_hit": sum(
            bool(item["hit_image_ids"]) for item in checked
        ),
        "facade_supported_points_2plus": len(supported_2),
        "facade_supported_points_3plus": len(supported_3),
        "facade_support_lengths": dict(sorted(support_lengths.items())),
        "per_view": per_view,
        "confirmed_tracks_2plus": [
            {"id": item["track_id"], "hit_image_ids": item["hit_image_ids"]}
            for item in checked if len(item["hit_image_ids"]) >= 2
        ],
    }
    write_json(output / "facade_audit.json", result)
    print(
        f"Facade support: {len(supported_2):,} points in 2+ views; "
        f"{len(supported_3):,} points in 3+ views; {len(xyz):,} scene points"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--regions", type=Path,
                        default=Path("data/evaluation/hive_facade_regions.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.run.resolve(), args.regions.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
