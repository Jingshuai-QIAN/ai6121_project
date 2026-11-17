"""Run a single native frontend change on the exact PNGs saved by a reference run."""

import argparse
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

import cv2
import numpy as np
import scipy

from experiments.compare_sparse import input_manifest
from sfm.__main__ import git_provenance
from sfm.data import (appearance_key, build_tracks, candidate_pairs, extract_features, load_appearance,
                      match_pair, save_appearance)
from sfm.export import contact_sheet, export_result, write_json
from sfm.geometry import verify_pair
from sfm.model import Camera, Frame
from sfm.reconstruction import final_pair_geometry, reconstruct


def prepare(reference, out, frames, inputs, manifest, base, config, change):
    out.mkdir(parents=True)
    (out / "frames").symlink_to(reference / "frames", target_is_directory=True)
    figures = out / "figures"
    figures.mkdir()
    write_json(out / "inputs.json", inputs)
    write_json(out / "frame_manifest.json", manifest)
    write_json(out / "config.resolved.json", config)
    old = {}
    if change == "window":
        original = load_appearance(reference, frames, appearance_key(inputs, base))
        old = {(pair.i, pair.j): pair for pair in original}
        saved = [(frame.xy.copy(), frame.rgb.copy()) for frame in frames]
    start = perf_counter()
    contact_sheet(frames, figures / "contact_sheet.jpg")
    elapsed = {"contact_sheet": perf_counter() - start}
    stage = perf_counter()
    extract_features(frames, config)
    if old:
        for frame, (xy, rgb) in zip(frames, saved, strict=True):
            np.testing.assert_array_equal(frame.xy, xy)
            np.testing.assert_array_equal(frame.rgb, rgb)
    elapsed["sift"] = perf_counter() - stage
    stage = perf_counter()
    new = []
    rng = np.random.default_rng(config["seed"])
    for (i, j), schedule in candidate_pairs(len(frames), config["window"], config["loop_window"]):
        if (i, j) in old:
            continue
        pair = match_pair(frames[i], frames[j], config["ratio"])
        pair.counts["schedule"] = schedule
        pair_rng = np.random.default_rng(np.random.SeedSequence([config["seed"], i, j])) if old else rng
        verify_pair(pair, frames[i], frames[j], config, pair_rng)
        new.append(pair)
    elapsed["matching_and_geometry"] = perf_counter() - stage
    stage = perf_counter()
    pairs = sorted([*old.values(), *new], key=lambda pair: (pair.i, pair.j))
    save_appearance(out, frames, pairs, appearance_key(inputs, config))
    elapsed["appearance_write"] = perf_counter() - stage
    if input_manifest(reference) != manifest:
        raise ValueError("Saved inputs changed during appearance processing")
    record = {
        "prepare_command": [sys.executable, "-m", "experiments.native_ablation", *sys.argv[1:]],
        "reference": str(reference), "reused_exact_verified_pairs": len(old), "computed_pairs": len(new),
        "computed_pairs_verified": sum(pair.F is not None for pair in new),
        "seed_for_pairs": "[reference_seed, image_i, image_j]" if old else "original sequential PRNG",
        "working_pixels": "Exact saved PNGs",
        "single_changed_parameter": {change: [base[change], config[change]]},
        "elapsed_seconds": elapsed, "python": platform.python_version(), "git": git_provenance(),
        "versions": {"numpy": np.__version__, "opencv": cv2.__version__, "scipy": scipy.__version__},
    }
    write_json(out / "provenance.json", record)
    print(f"{len(new)} pairs computed ({record['computed_pairs_verified']} verified), {len(old)} reused",
          flush=True)
    return pairs, record


def map_prepared(reference, out, frames, config, pairs, record):
    elapsed = dict(record["elapsed_seconds"])
    K = json.loads((reference / "cameras.json").read_text())["initial_K_work"]
    camera = Camera(K[0][0], K[0][2], K[1][2])
    stage = perf_counter()
    tracks, conflicts = build_tracks(pairs)
    elapsed["tracks"] = perf_counter() - stage
    stage = perf_counter()
    state = reconstruct(frames, pairs, tracks, camera, config)
    elapsed["incremental_and_ba"] = perf_counter() - stage
    stage = perf_counter()
    checks = final_pair_geometry(state, pairs, config["sampson_px"])
    elapsed["final_geometry_check"] = perf_counter() - stage
    stage = perf_counter()
    metrics = export_result(out, state, pairs, checks, elapsed, conflicts, camera)
    elapsed["export"] = perf_counter() - stage
    elapsed["total"] = sum(elapsed.values())
    write_json(out / "provenance.json", record)
    write_json(out / "metrics.json", metrics)
    print(state.status, len(state.poses), len(state.points), state.camera.focal, flush=True)
    return {"success": 0, "partial": 3}.get(state.status, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    setting = parser.add_mutually_exclusive_group(required=True)
    setting.add_argument("--window", type=int)
    setting.add_argument("--features", type=int)
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument("--match-only", action="store_true")
    stage.add_argument("--finish", action="store_true")
    args = parser.parse_args()
    reference, out = args.reference.resolve(), args.output.resolve()
    inputs = json.loads((reference / "inputs.json").read_text())
    base = json.loads((reference / "config.resolved.json").read_text())
    change = "window" if args.window is not None else "features"
    value = getattr(args, change)
    if value <= base[change] or (change == "window" and value >= len(inputs["frames"])):
        parser.error("Supply an increased feature limit or a longer window within the frame count")
    config = {**base, change: value}
    cv2.setNumThreads(1)
    cv2.setRNGSeed(config["seed"] % (2 ** 31))
    manifest = input_manifest(reference)
    frames = [Frame(row["id"], row, cv2.imread(str(reference / row["file"]))) for row in inputs["frames"]]
    if args.finish:
        if (out / "metrics.json").exists():
            parser.error("This run already has a map")
        if json.loads((out / "frame_manifest.json").read_text()) != manifest:
            parser.error("The prepared frame manifest no longer matches")
        record = json.loads((out / "provenance.json").read_text())
        pairs = load_appearance(out, frames, appearance_key(inputs, config))
    else:
        pairs, record = prepare(reference, out, frames, inputs, manifest, base, config, change)
    if args.match_only:
        return 0

    record["reconstruct_command"] = [sys.executable, "-m", "experiments.native_ablation", *sys.argv[1:]]
    return map_prepared(reference, out, frames, config, pairs, record)


if __name__ == "__main__":
    sys.exit(main())
