"""Command-line entry points. Run from the repository root."""

import argparse
import json
import logging
from pathlib import Path
import platform
import subprocess
from time import perf_counter
import sys

import cv2
import matplotlib
import numpy as np
import scipy

from .data import (appearance_key, build_tracks, candidate_pairs, extract_features, initial_camera,
                   load_appearance, match_pair, prepare_frames, save_appearance, sha256)
from .export import contact_sheet, export_result, write_json
from .geometry import verify_pair
from .reconstruction import final_pair_geometry, reconstruct


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "configs/default.json"
logger = logging.getLogger("sfm")


def resolve_config(args):
    config = json.loads(DEFAULT_CONFIG.read_text())
    if args.config:
        overrides = json.loads(args.config.read_text())
        unknown = overrides.keys() - config.keys()
        if unknown:
            raise ValueError(f"Unknown config fields: {sorted(unknown)}")
        config.update(overrides)
    for key in ("frames", "start", "end", "focal_factor"):
        value = getattr(args, key)
        if value is not None:
            config[key] = value
    if args.fit_k1:
        config["fit_k1"] = True
    integer_minima = {"frames": 2, "start": 0, "long_edge": 100, "features": 1, "window": 1,
                      "loop_window": 0, "grid_cell": 0, "seed": 0, "ransac_trials": 32, "min_pair_inliers": 8,
                      "seed_candidates": 1, "min_pnp_inliers": 6, "max_attempts": 1, "ba_every": 1,
                      "ba_evaluations": 1, "ba_final_evaluations": 1}
    for key, minimum in integer_minima.items():
        if type(config[key]) is not int or config[key] < minimum:
            raise ValueError(f"{key} requires an integer >= {minimum}")
    if config["end"] is not None and type(config["end"]) is not int:
        raise ValueError("end requires a source frame index or null")
    for key in ("ratio", "min_pnp_ratio", "contrast"):
        if not 0 < config[key] < 1:
            raise ValueError(f"{key} must be in (0, 1)")
    for key in ("sampson_px", "min_seed_angle", "min_angle", "pixel_gate", "final_pixel_gate",
                "focal_factor", "log_focal_prior_sigma", "k1_bound", "k1_prior_sigma"):
        if not np.isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f"{key} must be finite and positive")
    low, high = config["focal_bounds"]
    if (not 0 < low < high < np.inf or
        config["final_pixel_gate"] > config["pixel_gate"] or
        not 0 <= config["clahe_clip"] < np.inf or
        any(type(config[key]) is not bool for key in ("fit_k1", "root_sift"))):
        raise ValueError("Invalid focal bounds, reprojection gates or fit_k1 flag")
    return config


def git_provenance():
    def git(*params):
        result = subprocess.run(["git", *params], capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    root = Path(__file__).resolve().parents[1]
    status = git("-C", str(root), "status", "--porcelain")
    return {"commit": git("-C", str(root), "rev-parse", "HEAD"),
            "branch": git("-C", str(root), "branch", "--show-current"),
            "dirty": None if status is None else bool(status),
            "source_sha256": {str(path.relative_to(root)): sha256(path)
                              for path in sorted((root / "sfm").glob("*.py"))}}


def run(args):
    config = resolve_config(args)
    cv2.setNumThreads(1)
    cv2.setRNGSeed(config["seed"] % (2 ** 31))
    rng = np.random.default_rng(config["seed"])
    output = args.output.resolve()
    video = args.video.resolve(strict=True)
    logger.info("[%s] Input: %s", args.action, video)
    logger.info("[%s] Output: %s", args.action, output)
    output.mkdir(parents=True)
    figures = output / "figures"
    figures.mkdir()
    write_json(output / "config.resolved.json", config)
    provenance = {
        "command": [sys.executable, "-m", "sfm", *sys.argv[1:]], "python": platform.python_version(),
        "os": platform.platform(), "cpu": platform.machine(), "seed": config["seed"],
        "versions": {"opencv": cv2.__version__, "numpy": np.__version__,
                     "scipy": scipy.__version__, "matplotlib": matplotlib.__version__},
        "git": git_provenance(), "config_sha256": sha256(output / "config.resolved.json"),
    }
    elapsed = {}
    start = perf_counter()
    stage = start
    end = config["end"] if config["end"] is not None else "last"
    logger.info("[frames] Sampling %d frames from source frames %d to %s (max edge %d px)",
                config["frames"], config["start"], end, config["long_edge"])
    frames, inputs = prepare_frames(video, config, output / "frames")
    contact_sheet(frames, figures / "contact_sheet.jpg")
    elapsed["prepare"] = perf_counter() - stage
    width, height = frames[0].record["work_size"]
    logger.info("[frames] Ready: %d frames at %d x %d px (%.1f s)",
                len(frames), width, height, elapsed["prepare"])
    camera = initial_camera(frames, config, args.source_focal_px)
    high = max(frames[0].image.shape[:2])
    if not config["focal_bounds"][0] * high <= camera.focal <= config["focal_bounds"][1] * high:
        raise ValueError("Initial working focal length is outside the configured search interval")
    inputs["intrinsics_initialization"] = {
        "source": "documented_source_focal_px" if args.source_focal_px is not None else "assumed_factor",
        "source_focal_px": args.source_focal_px, "source_description": args.focal_source,
        "initial_work_K": camera.K, "initial_k1": 0.0, "measured_calibration_available": False,
        "shared_model_assumption": "single selected video segment; inspect for zoom/cuts before fitting",
    }
    write_json(output / "inputs.json", inputs)
    logger.info("[camera] Initial focal length: %.2f working px", camera.focal)
    provenance["video_sha256"] = inputs["sha256"]
    if args.reuse_appearance:
        provenance["reused_appearance"] = {
            "path": str(args.reuse_appearance.resolve()),
            "sha256": sha256(args.reuse_appearance / "appearance.npz"),
        }
    write_json(output / "provenance.json", provenance)
    if args.action == "inspect":
        print(f"Decoded {len(frames)} selected frames of {inputs['reported_frames']}: {output}",
              flush=True)
        return 0

    key_extra = None
    if args.frontend != "sift":
        from .learned import cache_key
        key_extra = cache_key(args.frontend)
    key = appearance_key(inputs, config, key_extra)
    if args.reuse_appearance:
        stage = perf_counter()
        logger.info("[cache] Loading cached features and matches from %s", args.reuse_appearance)
        pairs = load_appearance(args.reuse_appearance, frames, key)
        elapsed["appearance_cache_load"] = perf_counter() - stage
    elif args.frontend == "sift":
        stage = perf_counter()
        logger.info("[SIFT] Extracting features in %d frames", len(frames))
        extract_features(frames, config)
        elapsed["sift"] = perf_counter() - stage
        logger.info("[SIFT] Extracted %d features (%.1f s)",
                    sum(len(frame.xy) for frame in frames), elapsed["sift"])
        stage = perf_counter()
        pairs = []
        scheduled = candidate_pairs(len(frames), config["window"], config["loop_window"])
        total = len(scheduled)
        interval = max(1, (total + 9) // 10)
        verified = 0
        logger.info("[match] Matching and geometrically verifying %d image pairs", total)
        for done, ((i, j), schedule) in enumerate(scheduled, 1):
            pair = match_pair(frames[i], frames[j], config["ratio"])
            pair.counts["schedule"] = schedule
            verify_pair(pair, frames[i], frames[j], config, rng)
            pairs.append(pair)
            verified += pair.F is not None
            if done == 1 or done % interval == 0 or done == total:
                logger.info("[match] %d/%d pairs checked, %d verified (%.1f s)",
                            done, total, verified, perf_counter() - stage)
        elapsed["matching_and_geometry"] = perf_counter() - stage
        stage = perf_counter()
        logger.info("[cache] Saving features and matches")
        save_appearance(output, frames, pairs, key)
        elapsed["appearance_cache_write"] = perf_counter() - stage
    else:
        from .learned import match_with_lightglue
        logger.info("[frontend] %s on CUDA; geometry backend is unchanged", args.frontend)
        pairs, info = match_with_lightglue(frames, config, args.frontend, rng)
        elapsed.update(info.pop("elapsed"))
        write_json(output / "frontend.json", info)
        stage = perf_counter()
        logger.info("[cache] Saving features and matches")
        save_appearance(output, frames, pairs, key)
        elapsed["appearance_cache_write"] = perf_counter() - stage
    stage = perf_counter()
    verified = sum(pair.F is not None for pair in pairs)
    logger.info("[tracks] Linking observations across %d verified image pairs", verified)
    tracks, conflicts = build_tracks(pairs)
    elapsed["tracks"] = perf_counter() - stage
    print(f"{len(pairs)} pairs tested, {verified} verified, "
          f"{len(tracks)} candidate tracks", flush=True)
    stage = perf_counter()
    state = reconstruct(frames, pairs, tracks, camera, config)
    elapsed["incremental_and_ba"] = perf_counter() - stage
    stage = perf_counter()
    logger.info("[check] Rechecking pair geometry against the final camera poses")
    checks = final_pair_geometry(state, pairs, config["sampson_px"])
    elapsed["final_geometry_check"] = perf_counter() - stage
    stage = perf_counter()
    logger.info("[export] Writing results and figures to %s", output)
    metrics = export_result(output, state, pairs, checks, elapsed, conflicts, camera)
    elapsed["export"] = perf_counter() - stage
    elapsed["total"] = perf_counter() - start
    write_json(output / "metrics.json", metrics)
    logger.info("[export] Complete (%.1f s total)", elapsed["total"])
    print(f"{state.status}: {len(state.poses)}/{len(frames)} cameras; {len(state.points)} points; "
          f"f={state.camera.focal:.2f} px, k1={state.camera.k1:.5f}; {output}", flush=True)
    return {"success": 0, "two_view": 0, "partial": 3}.get(state.status, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "reconstruct"))
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument("--config", type=Path, help="JSON with overrides for configs/default.json")
    parser.add_argument("--frames", type=int)
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--focal-factor", type=float)
    parser.add_argument("--source-focal-px", type=float, help="Verified estimate in oriented source pixels")
    parser.add_argument("--focal-source", help="Provenance of --source-focal-px, including crop/mode")
    parser.add_argument("--reuse-appearance", type=Path, help="Load matching cache from a prior run")
    parser.add_argument("--fit-k1", action="store_true")
    parser.add_argument("--frontend", choices=("sift", "sift_lightglue", "superpoint_lightglue"),
                        default="sift",
                        help="sift keeps the ratio-test matcher; the other two replace only matching")
    args = parser.parse_args()
    if (args.source_focal_px is None) != (args.focal_source is None):
        parser.error("--source-focal-px and --focal-source must be supplied together")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[sfm] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        return run(args)
    except (OSError, TypeError, ValueError, cv2.error) as error:
        parser.exit(2, f"sfm: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
