"""Run the external PyCOLMAP sparse baseline on a saved SfM frame directory."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

import numpy as np
import pycolmap as colmap


def hash_file(path):
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def frame_manifest(source):
    inputs = json.loads((source / "inputs.json").read_text())
    names = []
    for frame in inputs["frames"]:
        name = Path(frame["file"]).name
        path = source / "frames" / name
        names.append({"id": frame["id"], "name": name, "source_frame": frame["source_frame"],
                      "work_size": frame["work_size"], "bytes": path.stat().st_size,
                      "sha256": hash_file(path)})
    if sorted(p.name for p in (source / "frames").glob("*.png")) != sorted(r["name"] for r in names):
        raise ValueError("Saved PNGs do not agree with the reference input manifest")
    return names


def export_model(model, names, out):
    image_slots = {record["name"]: record["id"] for record in names}
    views = sorted((image_slots[image.name], image) for image in model.images.values() if image.has_pose)
    camera_ids = {image.camera_id for _, image in views}
    if len(camera_ids) != 1:
        raise ValueError(f"Expected one shared registered camera, got {camera_ids}")
    camera = model.cameras[next(iter(camera_ids))]
    f, cx, cy, *extra = camera.params.tolist()
    # COLMAP uses (0.5, 0.5) for the center of the first pixel.
    K = np.array([[f, 0, cx - .5], [0, f, cy - .5], [0, 0, 1]])
    rotations, translations, registered = [], [], {}
    for i, image in views:
        pose = image.cam_from_world()
        R, t = pose.rotation.matrix(), pose.translation
        rotations.append(R)
        translations.append(t)
        registered[i] = {"image_id_external": image.image_id, "R_cw": R.tolist(),
                         "t_cw": t.tolist(), "center_world": (-R.T @ t).tolist()}
    cameras = [{**row, "registered": row["id"] in registered, **registered.get(row["id"], {})}
               for row in names]
    write_json(out / "cameras_work_px.json",
               {"model": camera.model.name, "parameters_colmap": camera.params.tolist(),
                "K_work": K.tolist(), "k1": extra[0] if extra else 0.0, "cameras": cameras})
    ids, xyz, rgb = [], [], []
    obs_point, obs_view, obs_xy, obs_keypoint = [], [], [], []
    for point_index, (pid, point) in enumerate(sorted(model.points3D.items())):
        ids.append(pid)
        xyz.append(point.xyz)
        rgb.append(point.color)
        for element in point.track.elements:
            image = model.images[element.image_id]
            uv = image.points2D[element.point2D_idx].xy
            obs_point.append(point_index)
            obs_view.append(image_slots[image.name])
            obs_keypoint.append(element.point2D_idx)
            obs_xy.append(uv - .5)
    np.savez_compressed(
        out / "observations_work_px.npz", point_ids=ids, xyz=xyz, rgb=rgb,
        image_ids=[i for i, _ in views], R_cw=rotations, t_cw=translations, K_work=K,
        k1=extra[0] if extra else 0.0, obs_point=obs_point, obs_view=obs_view, obs_xy=obs_xy,
        obs_keypoint=obs_keypoint,
    )
    model.write_text(out / "model_text")
    model.export_PLY(out / "pointcloud.ply")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--focal", type=float, help="Override only the initial focal length")
    parser.add_argument("--radial", action="store_true")
    parser.add_argument("--same-pairs", action="store_true", help="Use the original scheduled image pairs")
    args = parser.parse_args()
    source, out = args.reference.resolve(), args.output.resolve()
    names = frame_manifest(source)
    sizes = {tuple(r["work_size"]) for r in names}
    if len(sizes) != 1:
        raise ValueError("Shared-camera test requires one working image size")
    width, height = sizes.pop()
    config = json.loads((source / "config.resolved.json").read_text())
    with np.load(source / "reconstruction.npz") as original:
        assert np.allclose(original["K_work"][:2, 2] + .5, [width / 2, height / 2])
    initial_cameras = json.loads((source / "cameras.json").read_text())
    focal = args.focal if args.focal is not None else initial_cameras["initial_K_work"][0][0]
    if args.focal is None:
        assert np.isclose(focal, max(width, height) * config["focal_factor"])

    model = "SIMPLE_RADIAL" if args.radial else "SIMPLE_PINHOLE"
    camera_params = [focal, width / 2, height / 2]
    if args.radial:
        camera_params.append(0.0)
    reader = colmap.ImageReaderOptions(camera_model=model, camera_params=",".join(map(str, camera_params)))
    extraction = colmap.FeatureExtractionOptions(max_image_size=max(width, height),
                                                   num_threads=args.threads, use_gpu=False)
    matching = colmap.FeatureMatchingOptions(num_threads=args.threads, use_gpu=False)
    verification = colmap.TwoViewGeometryOptions()
    verification.ransac.random_seed = config["seed"]
    mapping = colmap.IncrementalPipelineOptions(
        num_threads=args.threads, random_seed=config["seed"], ba_refine_focal_length=True,
        ba_refine_principal_point=False, ba_refine_extra_params=args.radial, ba_use_gpu=False,
        structure_less_registration_fallback=False, min_focal_length_ratio=config["focal_bounds"][0],
        max_focal_length_ratio=config["focal_bounds"][1],
    )
    mapping.triangulation.ignore_two_view_tracks = False
    mapping.triangulation.random_seed = config["seed"]
    mapping.mapper.random_seed = config["seed"]
    out.mkdir(parents=True)
    colmap.logging.logtostderr = True
    for directory in ("models", "model_text"):
        (out / directory).mkdir()
    write_json(out / "frame_manifest.json", names)
    pairs_file = out / "pair_list.txt"
    if args.same_pairs:
        pairs = json.loads((source / "pairs.json").read_text())
        pairs_file.write_text("".join(f"{names[p['i']]['name']} {names[p['j']]['name']}\n" for p in pairs))
        pairing = colmap.ImportedPairingOptions(match_list_path=str(pairs_file))
        count = len(pairs)
    else:
        pairing = colmap.ExhaustivePairingOptions()
        count = len(names) * (len(names) - 1) // 2
    database = out / "database.db"
    record = {
        "command": [sys.executable, *sys.argv], "python": platform.python_version(),
        "pycolmap": colmap.__version__, "numpy": np.__version__, "cuda_build": colmap.has_cuda,
        "runner_sha256": hash_file(Path(__file__)), "reference": str(source),
        "input_manifest_sha256": hash_file(out / "frame_manifest.json"), "device": "cpu",
        "pair_schedule": "reference pairs" if args.same_pairs else "exhaustive",
        "scheduled_pairs": count, "camera_mode": "SINGLE", "initial_model": model,
        "initial_focal_px": focal, "initial_camera_params_colmap_px": camera_params,
        "reader": repr(reader), "extraction": repr(extraction), "matching": repr(matching),
        "verification": repr(verification), "pairing": repr(pairing), "mapping": repr(mapping),
    }
    write_json(out / "configuration.json", record)
    elapsed = {}
    start = perf_counter()
    phase = start
    colmap.extract_features(database, source / "frames", image_names=[r["name"] for r in names],
                            camera_mode=colmap.CameraMode.SINGLE, reader_options=reader,
                            extraction_options=extraction, device=colmap.Device.cpu)
    elapsed["features"] = perf_counter() - phase
    with colmap.Database.open(database) as db:
        cameras = db.read_all_cameras()
        assert len(cameras) == 1 and np.allclose(cameras[0].params, camera_params)
    phase = perf_counter()
    matcher = colmap.match_image_pairs if args.same_pairs else colmap.match_exhaustive
    matcher(database, matching_options=matching, pairing_options=pairing,
            verification_options=verification, device=colmap.Device.cpu)
    elapsed["matching"] = perf_counter() - phase
    if frame_manifest(source) != names:
        raise ValueError("Working inputs changed during matching")
    phase = perf_counter()
    models = colmap.incremental_mapping(database, source / "frames", out / "models", mapping)
    elapsed["mapping"] = perf_counter() - phase
    stats = [{"id": i, "registered": m.num_reg_images(), "points": m.num_points3D()} for i, m in models.items()]
    selected = max(stats, key=lambda row: (row["registered"], row["points"], -row["id"]), default=None)
    if selected:
        export_model(models[selected["id"]], names, out)
    elapsed["total"] = perf_counter() - start
    write_json(out / "run_summary.json", {"models": stats, "selected": selected, "elapsed_seconds": elapsed})
    print(selected, elapsed, flush=True)
    return 0 if selected else 2


if __name__ == "__main__":
    sys.exit(main())
