"""Command-line reconstruction from image,landmark,x,y CSV observations."""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from sfm import reconstruct


def read_tracks(path):
    by_image = {}
    landmarks = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        if reader.fieldnames != ["image", "landmark", "x", "y"]:
            raise ValueError("Expected CSV header: image,landmark,x,y")
        for row in reader:
            line = reader.line_num
            if None in row or None in row.values():
                raise ValueError(f"CSV line {line}: expected four fields.")
            image, landmark = row["image"].strip(), row["landmark"].strip()
            if not image or not landmark:
                raise ValueError(f"CSV line {line}: image and landmark IDs must be nonempty.")
            tracks = by_image.setdefault(image, {})
            if landmark in tracks:
                raise ValueError(f"CSV line {line}: duplicate observation of {landmark!r} in {image!r}.")
            try:
                coordinate = float(row["x"]), float(row["y"])
            except ValueError as exc:
                raise ValueError(f"CSV line {line}: x and y must be numeric.") from exc
            if not np.isfinite(coordinate).all():
                raise ValueError(f"CSV line {line}: x and y must be finite.")
            tracks[landmark] = coordinate
            landmarks[landmark] = None

    if not by_image:
        raise ValueError("CSV contains no landmark observations.")
    for image, tracks in by_image.items():
        missing = landmarks.keys() - tracks.keys()
        if missing:
            raise ValueError(f"Image {image!r} is missing landmarks: {', '.join(sorted(missing))}.")
    observations = np.array([[tracks[name] for name in landmarks] for tracks in by_image.values()])
    return list(by_image), list(landmarks), observations


def write_results(directory, images, landmarks, observations, result):
    initial_error = np.sum((result.initial_projections - observations) ** 2, axis=2)
    final_error = np.sum((result.projections - observations) ** 2, axis=2)
    metrics = {
        "seed_images": [images[i] for i in result.seed],
        "frame_landmarks": [landmarks[i] for i in result.frame],
        "initial_rmse_px": float(np.sqrt(initial_error.mean())),
        "final_rmse_px": float(np.sqrt(final_error.mean())),
        "views": [
            {
                "image": image,
                "initial_rmse_px": float(np.sqrt(before.mean())),
                "final_rmse_px": float(np.sqrt(after.mean())),
            }
            for image, before, after in zip(images, initial_error, final_error)
        ],
        "optimizer": {
            "converged": result.converged,
            "message": result.optimizer_message,
            "function_evaluations": result.evaluations,
        },
    }
    directory.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        directory / "reconstruction.npz",
        image_ids=images,
        landmark_ids=landmarks,
        cameras=result.cameras,
        points=result.points,
        observations=observations,
        initial_projections=result.initial_projections,
        projections=result.projections,
    )
    with (directory / "point_cloud.ply").open("w", encoding="ascii", newline="\n") as cloud:
        cloud.write(
            "ply\nformat ascii 1.0\n"
            f"element vertex {len(landmarks)}\n"
            "property double x\nproperty double y\nproperty double z\nend_header\n"
        )
        np.savetxt(cloud, result.points[:, :3], fmt="%.17g")
    (directory / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tracks", type=Path, help="CSV of complete landmark tracks")
    parser.add_argument("--output", type=Path, default=Path("tmp/sfm"), help="output directory")
    parser.add_argument("--seed", nargs=2, metavar=("FIRST", "SECOND"), help="seed image IDs")
    parser.add_argument("--max-nfev", type=int, default=2000, help="bundle adjustment evaluation limit")
    args = parser.parse_args()

    try:
        images, landmarks, observations = read_tracks(args.tracks)
        seed = None
        if args.seed:
            unknown = [name for name in args.seed if name not in images]
            if unknown:
                raise ValueError(f"Unknown seed image(s): {', '.join(unknown)}.")
            seed = tuple(images.index(name) for name in args.seed)
        result = reconstruct(observations, seed=seed, max_nfev=args.max_nfev)
        metrics = write_results(args.output, images, landmarks, observations, result)
    except (OSError, ValueError, csv.Error, np.linalg.LinAlgError) as exc:
        parser.exit(1, f"SfM error: {exc}\n")

    print(f"Reconstructed {len(landmarks)} landmarks from {len(images)} views in {args.output}")
    print(f"Reprojection RMSE: {metrics['initial_rmse_px']:.4f} -> {metrics['final_rmse_px']:.4f} px")
    if not result.converged:
        print(f"Bundle adjustment did not converge: {result.optimizer_message}", file=sys.stderr)


if __name__ == "__main__":
    main()
