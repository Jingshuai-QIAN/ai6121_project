"""Learned matchers in front of the existing geometric SfM backend.

SIFT + LightGlue keeps this project's grid-sampled OpenCV detections and only
replaces the ratio test. SuperPoint + LightGlue replaces detection as well.
Geometric verification, pose, triangulation and bundle adjustment stay in
``sfm.geometry`` and ``sfm.reconstruction``.
"""

import json
import logging
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
import torch

from .data import candidate_pairs
from .geometry import verify_pair
from .model import Pair


logger = logging.getLogger("sfm")
SETTINGS_PATH = Path(__file__).resolve().parents[1] / "experiments/learned_frontend/settings.json"
FRONTENDS = ("sift_lightglue", "superpoint_lightglue")


def load_settings():
    settings = json.loads(SETTINGS_PATH.read_text())
    if settings["device"] != "cuda":
        raise ValueError("This frontend is configured for CUDA")
    if settings["resize"] is not None:
        raise ValueError("resize must stay null so keypoints remain in work-image pixels")
    return settings


def cache_key(frontend):
    import lightglue
    settings = load_settings()
    return {
        "name": frontend,
        "lightglue_file": str(Path(lightglue.__file__).resolve()),
        "settings": settings,
        "learned_sha256": __import__("sfm.data", fromlist=["sha256"]).sha256(Path(__file__)),
    }


def _assign_measurements(frame, xy):
    if len(xy) == 0:
        frame.xy = np.zeros((0, 2), dtype=float)
        frame.rgb = np.zeros((0, 3), dtype=np.uint8)
        frame.descriptors = None
        return
    height, width = frame.image.shape[:2]
    frame.xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    u = np.clip(np.rint(frame.xy[:, 0]).astype(int), 0, width - 1)
    v = np.clip(np.rint(frame.xy[:, 1]).astype(int), 0, height - 1)
    frame.rgb = frame.image[v, u, ::-1]
    frame.descriptors = None


def _project_sift(frame, config):
    """Same detection budget as ``extract_features``, plus scale and orientation."""
    grid_cell = config["grid_cell"]
    sift = cv2.SIFT_create(nfeatures=0 if grid_cell else config["features"],
                           contrastThreshold=config["contrast"])
    clahe = cv2.createCLAHE(clipLimit=config["clahe_clip"]) if config["clahe_clip"] else None
    gray = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY)
    if clahe is not None:
        gray = clahe.apply(gray)
    if grid_cell:
        height, width = gray.shape
        columns = (width + grid_cell - 1) // grid_cell
        rows = (height + grid_cell - 1) // grid_cell
        quota = max(1, config["features"] // (rows * columns))
        keypoints = sorted(sift.detect(gray), key=lambda key: -key.response)
        counts = np.zeros((rows, columns), dtype=int)
        selected = []
        for key in keypoints:
            x, y = np.floor(np.array(key.pt) / grid_cell).astype(int)
            if counts[y, x] < quota:
                selected.append(key)
                counts[y, x] += 1
        keypoints, descriptors = sift.compute(gray, selected)
    else:
        keypoints, descriptors = sift.detectAndCompute(gray, None)
    if not keypoints or descriptors is None:
        empty = np.zeros((0, 2), dtype=np.float32)
        return empty, np.zeros(0, np.float32), np.zeros(0, np.float32), np.zeros((0, 128), np.float32)
    xy = np.array([key.pt for key in keypoints], dtype=np.float32)
    scales = np.array([key.size for key in keypoints], dtype=np.float32)
    oris = np.deg2rad(np.array([key.angle for key in keypoints], dtype=np.float32))
    return xy, scales, oris, np.ascontiguousarray(descriptors, dtype=np.float32)


def _image_tensor(frame):
    """RGB float tensor. Reflect-pad to a multiple of 8 for SuperPoint's stride."""
    rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    pad_h = (8 - height % 8) % 8
    pad_w = (8 - width % 8) % 8
    if pad_h or pad_w:
        rgb = cv2.copyMakeBorder(rgb, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT_101)
    tensor = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1).float().div_(255)
    return tensor, width, height


def _pack_sift(xy, scales, oris, descriptors, width, height, device):
    from lightglue.sift import sift_to_rootsift
    if len(xy) == 0:
        desc = torch.zeros((1, 0, 128), dtype=torch.float32, device=device)
        return {
            "keypoints": torch.zeros((1, 0, 2), dtype=torch.float32, device=device),
            "scales": torch.zeros((1, 0), dtype=torch.float32, device=device),
            "oris": torch.zeros((1, 0), dtype=torch.float32, device=device),
            "descriptors": desc,
            "image_size": torch.tensor([[width, height]], dtype=torch.float32, device=device),
        }
    rooted = sift_to_rootsift(torch.from_numpy(descriptors))
    return {
        "keypoints": torch.from_numpy(xy)[None].to(device),
        "scales": torch.from_numpy(scales)[None].to(device),
        "oris": torch.from_numpy(oris)[None].to(device),
        "descriptors": rooted[None].to(device),
        "image_size": torch.tensor([[width, height]], dtype=torch.float32, device=device),
    }


def _cpu_matches(raw):
    from lightglue.utils import rbd
    # The empty-keypoint path returns a tensor; the normal path returns a list.
    matches = raw["matches"]
    scores = raw["scores"]
    if isinstance(matches, list):
        matches = matches[0]
        scores = scores[0]
    else:
        reduced = rbd(raw)
        matches = reduced["matches"]
        scores = reduced["scores"]
    matches = matches.detach().cpu().numpy()
    scores = scores.detach().cpu().numpy()
    if matches.size == 0:
        return np.zeros((0, 2), dtype=int), np.zeros(0, dtype=float)
    return matches.astype(int).reshape(-1, 2), scores.astype(float).reshape(-1)


def match_with_lightglue(frames, config, frontend, rng):
    if frontend not in FRONTENDS:
        raise ValueError(f"Unknown frontend {frontend}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the LightGlue frontend")
    from lightglue import LightGlue, SuperPoint

    settings = load_settings()
    device = torch.device("cuda")
    torch.manual_seed(config["seed"])
    torch.cuda.manual_seed_all(config["seed"])
    torch.cuda.reset_peak_memory_stats()
    elapsed = {}
    stage = perf_counter()
    matcher_name = "sift" if frontend == "sift_lightglue" else "superpoint"
    matcher = LightGlue(
        features=matcher_name,
        depth_confidence=settings["depth_confidence"],
        width_confidence=settings["width_confidence"],
        filter_threshold=settings["filter_threshold"],
        n_layers=settings["n_layers"],
    ).eval().to(device)
    extractor = None
    if frontend == "superpoint_lightglue":
        extractor = SuperPoint(max_num_keypoints=settings["superpoint_max_keypoints"]).eval().to(device)

    cached = []
    with torch.inference_mode():
        for frame in frames:
            height, width = frame.image.shape[:2]
            if frontend == "sift_lightglue":
                xy, scales, oris, descriptors = _project_sift(frame, config)
                _assign_measurements(frame, xy)
                cached.append(_pack_sift(xy, scales, oris, descriptors, width, height, device))
            else:
                tensor, width, height = _image_tensor(frame)
                feats = extractor.extract(tensor.to(device), resize=None)
                feats["image_size"] = torch.tensor([[width, height]], dtype=torch.float32, device=device)
                xy = feats["keypoints"][0].detach().cpu().numpy()
                inside = (
                    (xy[:, 0] >= 0) & (xy[:, 0] < width) &
                    (xy[:, 1] >= 0) & (xy[:, 1] < height)
                )
                if not np.all(inside):
                    keep = torch.from_numpy(inside).to(device)
                    for name in ("keypoints", "descriptors", "keypoint_scores"):
                        if name in feats:
                            feats[name] = feats[name][:, keep]
                    xy = xy[inside]
                _assign_measurements(frame, xy)
                cached.append(feats)
        elapsed["features"] = perf_counter() - stage
        logger.info("[frontend] Extracted %d features (%.1f s)",
                    sum(len(frame.xy) for frame in frames), elapsed["features"])

        stage = perf_counter()
        scheduled = candidate_pairs(len(frames), config["window"], config["loop_window"])
        total = len(scheduled)
        interval = max(1, (total + 9) // 10)
        pairs = []
        verified = 0
        match_seconds = 0.0
        logger.info("[match] LightGlue and geometric verification for %d image pairs", total)
        for done, ((i, j), schedule) in enumerate(scheduled, 1):
            tick = perf_counter()
            if len(frames[i].xy) == 0 or len(frames[j].xy) == 0:
                indices = np.zeros((0, 2), dtype=int)
                scores = np.zeros(0, dtype=float)
            else:
                raw = matcher({"image0": cached[i], "image1": cached[j]})
                indices, scores = _cpu_matches(raw)
            match_seconds += perf_counter() - tick
            pair = Pair(
                i, j, indices, 1.0 - scores,
                {"queries_i": len(frames[i].xy), "queries_j": len(frames[j].xy),
                 "mutual": len(indices), "lightglue_matches": len(indices),
                 "mean_match_score": float(scores.mean()) if len(scores) else 0.0,
                 "schedule": schedule, "frontend": frontend},
                np.zeros(len(indices), dtype=bool), np.full(len(indices), np.inf),
            )
            verify_pair(pair, frames[i], frames[j], config, rng)
            pairs.append(pair)
            verified += pair.F is not None
            if done == 1 or done % interval == 0 or done == total:
                logger.info("[match] %d/%d pairs checked, %d verified (%.1f s)",
                            done, total, verified, perf_counter() - stage)
        torch.cuda.synchronize()
        elapsed["lightglue"] = match_seconds
        elapsed["matching_and_geometry"] = perf_counter() - stage
    peak_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)
    del cached, matcher, extractor
    torch.cuda.empty_cache()
    info = {
        "frontend": frontend,
        "matcher": f"LightGlue pretrained on {matcher_name}",
        "detector": ("OpenCV SIFT with the project grid budget; official LightGlue RootSIFT"
                     if frontend == "sift_lightglue" else
                     "SuperPoint v1 pretrained weights from cvg/LightGlue"),
        "geometry": "sfm.geometry.verify_pair then the existing incremental SfM backend",
        "settings": settings,
        "resize": None,
        "coordinate_frame": "work-image pixels; SuperPoint resize disabled so no scale-back is required",
        "device": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "peak_gpu_memory_mb": round(peak_mb, 2),
        "features_per_image": [int(len(frame.xy)) for frame in frames],
        "elapsed": elapsed,
    }
    return pairs, info
