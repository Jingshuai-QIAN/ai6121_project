"""A: video decoding, intrinsics initialization, SIFT, matching and tracks."""

from hashlib import file_digest
import json
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np

from .model import Camera, Frame, Pair


def sha256(path):
    with open(path, "rb") as source:
        return file_digest(source, "sha256").hexdigest()


def probe_metadata(path):
    ffprobe = shutil.which("ffprobe")
    if ffprobe is not None:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, check=False,
        )
        if not result.returncode:
            return {"status": "ok", "tool": "ffprobe", **json.loads(result.stdout)}
    try:
        import av
    except ImportError:
        return {"status": "container_metadata_unavailable", "tools": ["ffprobe", "PyAV"]}
    try:
        with av.open(str(path)) as container:
            return {
                "status": "ok", "tool": "PyAV", "version": av.__version__,
                "format": container.format.name, "tags": container.metadata,
                "duration_s": None if container.duration is None else container.duration / av.time_base,
                "streams": [
                    {"type": stream.type, "frames": stream.frames, "codec": stream.codec_context.name,
                     "duration_s": None if stream.duration is None or stream.time_base is None
                     else float(stream.duration * stream.time_base), "tags": stream.metadata}
                    for stream in container.streams
                ],
            }
    except av.FFmpegError as error:
        return {"status": "container_metadata_failed", "tool": "PyAV", "message": str(error)}


def prepare_frames(path, config, output):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video {path}")
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        rotation = capture.get(cv2.CAP_PROP_ORIENTATION_META)
        if count < 2 or not np.isfinite(fps) or fps <= 0:
            raise ValueError("Video backend did not report a valid duration and frame count")
        capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
        coded = [int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                 int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))]
        capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        oriented = [int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))]
        end = config["end"] if config["end"] is not None else count - 1
        start = config["start"]
        if not 0 <= start < end < count or config["frames"] > end - start + 1:
            raise ValueError("Frame range and count do not fit the video")
        indices = np.rint(np.linspace(start, end, config["frames"])).astype(int)
        frames = []
        output.mkdir(parents=True)
        for frame_id, index in enumerate(indices):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, image = capture.read()
            if not ok:
                raise ValueError(f"Could not decode requested frame {index}")
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
            height, width = image.shape[:2]
            if [width, height] != oriented:
                raise ValueError("Frame dimensions changed within the segment")
            factor = min(1.0, config["long_edge"] / max(width, height))
            work_width, work_height = round(factor * width), round(factor * height)
            if min(work_width, work_height) < 2:
                raise ValueError("Working resolution is too small")
            if factor != 1:
                image = cv2.resize(image, (work_width, work_height), interpolation=cv2.INTER_AREA)
            sx, sy = work_width / width, work_height / height
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            name = f"{frame_id:03d}.png"
            if not cv2.imwrite(str(output / name), image):
                raise OSError(f"Could not save frame {output / name}")
            record = {
                "id": frame_id, "file": f"frames/{name}", "source_frame": int(index),
                "timestamp_s": timestamp, "nominal_time_s": index / fps,
                "oriented_size": [width, height], "work_size": [work_width, work_height],
                "oriented_to_work": [[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1]],
                "laplacian_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
            }
            frames.append(Frame(frame_id, record, image))
        metadata = {
            "path": str(path), "sha256": sha256(path), "backend": capture.getBackendName(),
            "coded_size": coded, "display_size": oriented, "orientation_metadata_deg": rotation,
            "reported_frames": count, "reported_mean_fps": fps, "nominal_duration_s": count / fps,
            "sample_aspect_ratio": [capture.get(cv2.CAP_PROP_SAR_NUM),
                                    capture.get(cv2.CAP_PROP_SAR_DEN)],
            "container": probe_metadata(path), "segment": [start, end],
            "selection": "uniform source-frame indices, rounded to nearest integer",
            "frames": [frame.record for frame in frames],
        }
        return frames, metadata
    finally:
        capture.release()


def initial_camera(frames, config, source_focal=None):
    height, width = frames[0].image.shape[:2]
    if source_focal is not None:
        sx, sy = np.diag(frames[0].record["oriented_to_work"])[:2]
        if not np.isclose(sx, sy, rtol=0.002):
            raise ValueError("Rounded image scales are too different for the square-pixel model")
        focal = source_focal * (sx + sy) / 2
    else:
        focal = config["focal_factor"] * max(width, height)
    return Camera(focal, (width - 1) / 2, (height - 1) / 2)


def extract_features(frames, config):
    grid_cell = config["grid_cell"]
    sift = cv2.SIFT_create(nfeatures=0 if grid_cell else config["features"],
                           contrastThreshold=config["contrast"])
    clahe = cv2.createCLAHE(clipLimit=config["clahe_clip"]) if config["clahe_clip"] else None
    for frame in frames:
        gray = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY)
        if clahe is not None:
            gray = clahe.apply(gray)
        if grid_cell:
            height, width = gray.shape
            columns = (width + grid_cell - 1) // grid_cell
            rows = (height + grid_cell - 1) // grid_cell
            quota = max(1, config["features"] // (rows * columns))
            # A cap per tile prevents pavement contrast from consuming the entire budget.
            keypoints = sorted(sift.detect(gray), key=lambda key: -key.response)
            counts = np.zeros((rows, columns), dtype=int)
            selected = []
            for key in keypoints:
                x, y = np.floor(np.array(key.pt) / grid_cell).astype(int)
                if counts[y, x] < quota:
                    selected.append(key)
                    counts[y, x] += 1
            keypoints, frame.descriptors = sift.compute(gray, selected)
        else:
            keypoints, frame.descriptors = sift.detectAndCompute(gray, None)
        if config["root_sift"] and frame.descriptors is not None:
            desc = frame.descriptors
            frame.descriptors = np.sqrt(desc / np.maximum(desc.sum(axis=1, keepdims=True), 1e-12))
        frame.xy = np.array([key.pt for key in keypoints], dtype=float).reshape(-1, 2)
        u, v = np.rint(frame.xy).astype(int).T
        u = np.clip(u, 0, gray.shape[1] - 1)
        v = np.clip(v, 0, gray.shape[0] - 1)
        frame.rgb = frame.image[v, u, ::-1]


def match_pair(first, second, ratio):
    matcher = cv2.BFMatcher(cv2.NORM_L2)

    def filtered(source, target):
        if source is None or target is None or len(target) < 2:
            return {}
        return {
            best.queryIdx: best for best, runner_up in matcher.knnMatch(source, target, k=2)
            if best.distance < ratio * runner_up.distance
        }

    forward = filtered(first.descriptors, second.descriptors)
    backward = filtered(second.descriptors, first.descriptors)
    mutual = [match for i, match in forward.items()
              if match.trainIdx in backward and backward[match.trainIdx].trainIdx == i]
    indices = np.array([(m.queryIdx, m.trainIdx) for m in mutual], dtype=int).reshape(-1, 2)
    distances = np.array([m.distance for m in mutual])
    counts = {"queries_i": len(first.xy), "queries_j": len(second.xy),
              "ratio_ij": len(forward), "ratio_ji": len(backward), "mutual": len(indices)}
    return Pair(first.id, second.id, indices, distances, counts,
                np.zeros(len(indices), dtype=bool), np.full(len(indices), np.inf))


def candidate_pairs(count, window, loop_window):
    pairs = {(i, j): "temporal" for i in range(count)
             for j in range(i + 1, min(count, i + window + 1))}
    # End-to-start candidates undergo the same appearance/geometric checks.
    for i in range(min(loop_window, count)):
        for j in range(max(i + 1, count - loop_window), count):
            pairs.setdefault((i, j), "boundary")
    return sorted(pairs.items())


def build_tracks(pairs):
    edges = []
    for pair in pairs:
        for index in np.flatnonzero(pair.inliers):
            a, b = pair.indices[index]
            edges.append((pair.errors[index], pair.distances[index],
                          (pair.i, int(a)), (pair.j, int(b))))
    parent, groups = {}, {}

    def root(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    conflicts = 0
    for _, _, first, second in sorted(edges):
        a, b = root(first), root(second)
        if a == b:
            continue
        group_a = groups.get(a, {a[0]: a[1]})
        group_b = groups.get(b, {b[0]: b[1]})
        if group_a.keys() & group_b.keys():
            conflicts += 1
            continue
        if len(group_b) > len(group_a):
            a, b, group_a, group_b = b, a, group_b, group_a
        parent[b] = a
        group_a.update(group_b)
        groups[a] = group_a
        groups.pop(b, None)
    return [dict(sorted(group.items())) for _, group in sorted(groups.items())], conflicts


def appearance_key(inputs, config):
    settings = ("seed", "features", "contrast", "grid_cell", "clahe_clip", "root_sift",
                "ratio", "window", "loop_window", "sampson_px", "ransac_trials", "min_pair_inliers")
    return {
        "video_sha256": inputs["sha256"], "frames": inputs["frames"],
        "settings": {key: config[key] for key in settings},
        "opencv": cv2.__version__, "numpy": np.__version__,
        "source": {name: sha256(Path(__file__).with_name(name))
                   for name in ("data.py", "geometry.py")},
    }


def save_appearance(output, frames, pairs, key):
    arrays = {}
    for frame in frames:
        arrays[f"xy_{frame.id}"] = frame.xy
        arrays[f"rgb_{frame.id}"] = frame.rgb
    for i, pair in enumerate(pairs):
        arrays[f"indices_{i}"] = pair.indices
        arrays[f"distances_{i}"] = pair.distances
        arrays[f"inliers_{i}"] = pair.inliers
        arrays[f"errors_{i}"] = pair.errors
        if pair.F is not None:
            arrays[f"F_{i}"] = pair.F
    np.savez_compressed(output / "appearance.npz", **arrays)
    manifest = {"key": key, "pairs": [{"i": p.i, "j": p.j, "counts": p.counts} for p in pairs]}
    (output / "appearance.json").write_text(json.dumps(manifest, allow_nan=False) + "\n")


def load_appearance(source, frames, key):
    manifest = json.loads((source / "appearance.json").read_text())
    if manifest["key"] != key:
        raise ValueError("Appearance cache does not match input frames, code, libraries or configuration")
    with np.load(source / "appearance.npz") as arrays:
        for frame in frames:
            frame.xy = arrays[f"xy_{frame.id}"]
            frame.rgb = arrays[f"rgb_{frame.id}"]
        return [Pair(row["i"], row["j"], arrays[f"indices_{i}"], arrays[f"distances_{i}"],
                     row["counts"], arrays[f"inliers_{i}"], arrays[f"errors_{i}"],
                     arrays.get(f"F_{i}")) for i, row in enumerate(manifest["pairs"])]
