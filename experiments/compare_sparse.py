"""Evaluate native and external sparse maps with identical pixel and region rules."""

import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import file_digest
import json
from pathlib import Path
import sqlite3

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.transform import Rotation


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def stats(values):
    values = np.asarray(values)
    if not len(values):
        return {"n": 0}
    return {
        "n": len(values), "rmse": float(np.sqrt(np.mean(values ** 2))),
        **dict(zip(("min", "median", "p95", "max"), np.quantile(values, (0, .5, .95, 1)).tolist())),
    }


def input_manifest(reference):
    rows = []
    for r in read(reference / "inputs.json")["frames"]:
        path = reference / r["file"]
        with path.open("rb") as file:
            digest = file_digest(file, "sha256").hexdigest()
        rows.append({"id": r["id"], "name": path.name, "source_frame": r["source_frame"],
                     "work_size": r["work_size"], "bytes": path.stat().st_size, "sha256": digest})
    return rows


@dataclass
class Regions:
    size: np.ndarray
    work: dict
    masks: dict
    labels_path: Path

    @classmethod
    def load(cls, source, labels):
        inputs, annotations = read(source / "inputs.json"), read(labels)
        if inputs["sha256"] != annotations["video_sha256"]:
            raise ValueError("Audit labels and work images have different video hashes")
        width, height = annotations["preview_size"]
        categories = annotations.get("regions_by_source_frame")
        if categories is None:
            categories = {"ribbon": annotations["polygons_by_source_frame"]}
        frames = {str(row["source_frame"]): row for row in inputs["frames"]}
        masks = {}
        side = 2 * annotations["erosion_preview_px"] + 1
        for category, drawings in categories.items():
            masks[category] = {}
            for source_index, polygons in drawings.items():
                frame = frames[source_index]
                mask = np.zeros((height, width), dtype=np.uint8)
                for polygon in polygons:
                    cv2.fillPoly(mask, [np.array(polygon, dtype=np.int32)], 1)
                masks[category][frame["id"]] = cv2.erode(mask, np.ones((side, side), dtype=np.uint8))
        return cls(np.array([width, height]), {f["id"]: np.array(f["work_size"]) for f in frames.values()},
                   masks, labels.resolve())

    def hits(self, label, image_id, xy):
        mask = self.masks[label].get(image_id)
        if mask is None:
            return np.zeros(len(xy), dtype=bool)
        preview = np.rint((xy + .5) * self.size / self.work[image_id] - .5).astype(int)
        good = ((preview >= 0) & (preview < self.size)).all(axis=1)
        u, v = preview[good].T
        good[good] = mask[v, u] > 0
        return good


def load_map(run):
    path = run / "observations_work_px.npz"
    if path.exists():
        with np.load(path) as data:
            return dict(data)
    with np.load(run / "reconstruction.npz") as data:
        result = dict(data)
    ids = {tid: i for i, tid in enumerate(result.pop("track_ids"))}
    p, v, xy, kp = [], [], [], []
    for track in read(run / "tracks.json"):
        if track["id"] not in ids:
            continue
        for obs in track["observations"]:
            if obs["active"]:
                p.append(ids[track["id"]])
                v.append(obs["image_id"])
                xy.append(obs["xy_work_distorted"])
                kp.append(obs["keypoint_id"])
    return {**result, "obs_point": np.array(p), "obs_view": np.array(v), "obs_xy": np.array(xy),
            "obs_keypoint": np.array(kp)}


def measure(data, regions):
    xyz, R, t = (data[k] for k in ("xyz", "R_cw", "t_cw"))
    p, v, pixels = (data[k] for k in ("obs_point", "obs_view", "obs_xy"))
    centers = -np.einsum("nji,nj->ni", R, t)
    v_to_slot = {view: i for i, view in enumerate(data["image_ids"])}
    view_slot = np.array([v_to_slot[i] for i in v])
    depth, predicted = np.empty(len(p)), np.empty_like(pixels)
    radial = np.array([float(data["k1"]), 0., 0., 0., 0.])
    for view, i in v_to_slot.items():
        rows = v == view
        pts = xyz[p[rows]]
        if len(pts):
            predicted[rows] = cv2.projectPoints(pts, cv2.Rodrigues(R[i])[0], t[i],
                                                data["K_work"], radial)[0].reshape(-1, 2)
            depth[rows] = (pts @ R[i].T + t[i])[:, 2]
    error = np.linalg.norm(predicted - pixels, axis=1)
    raw_error = error.copy()
    raw_negative_depth = int(np.sum(depth <= 0))
    # External tracks can associate two keypoints with one point in the same image.
    # Count distinct views and score one observation per view, retaining all raw data.
    ordered = np.lexsort((error, v, p))
    sorted_pairs = np.column_stack((p[ordered], v[ordered]))
    keep = ordered[np.r_[True, np.any(np.diff(sorted_pairs, axis=0), axis=1)]]
    p, v, pixels, depth, predicted, error, view_slot = (
        array[keep] for array in (p, v, pixels, depth, predicted, error, view_slot)
    )
    lengths = np.bincount(p, minlength=len(xyz))
    sorted_rows = np.argsort(p, kind="stable")
    groups = np.split(sorted_rows, np.cumsum(lengths)[:-1])

    def angle(rows):
        if len(rows) < 2:
            return 0.
        rays = xyz[p[rows[0]]] - centers[view_slot[rows]]
        rays /= np.linalg.norm(rays, axis=1, keepdims=True)
        return np.degrees(np.arccos(np.clip((rays @ rays.T).min(), -1, 1)))

    angles = np.array([angle(rows) for rows in groups])
    # Apply one common diagnostic gate to both maps, without changing either map.
    accepted = (depth > 0) & (error <= 3)
    common_gate = np.array([angle(rows[accepted[rows]]) >= 1 for rows in groups])
    target = np.zeros(len(xyz), dtype=bool)
    target_hits = np.zeros(len(p), dtype=bool)
    details = {}
    for label, by_view in regions.masks.items():
        hits = np.zeros(len(p), dtype=bool)
        for view in by_view:
            rows = v == view
            hits[rows] = (regions.hits(label, view, pixels[rows]) &
                          regions.hits(label, view, predicted[rows]) & (depth[rows] > 0))
        label_lengths = np.bincount(p[hits], minlength=len(xyz))
        supported = label_lengths >= 2
        confirmed = hits & supported[p]
        cells = np.floor(pixels[confirmed] / 32).astype(int)
        occupied = np.unique(np.column_stack((v[confirmed], cells)), axis=0)
        details[label] = {
            "annotated_views": len(by_view), "registered_annotated_views": len(set(by_view) & set(v)),
            "confirmed_points": int(supported.sum()), "labeled_views_3plus": int((label_lengths >= 3).sum()),
            "confirmed_active_track_3plus": int(np.sum(supported & (lengths >= 3))),
            "confirmed_and_common_gate": int(np.sum(supported & common_gate)),
            "confirmed_observations": int(confirmed.sum()),
            "observations_past_3px": int(np.sum(confirmed & ~accepted)),
            "occupied_view_cells_32px": len(occupied),
            "occupied_view_cells_by_image": dict(Counter(map(int, occupied[:, 0]))),
            "support_views_by_image": dict(Counter(map(int, v[confirmed]))),
        }
        target |= supported
        target_hits |= confirmed
    report = {
        "registered": len(R), "total": len(regions.work),
        "unregistered_ids": sorted(set(regions.work) - set(map(int, data["image_ids"]))),
        "points": len(xyz), "observations": len(p),
        "same_image_repeat_observations": len(raw_error) - len(p),
        "raw_pixels_including_same_image_repeats": stats(raw_error),
        "raw_nonpositive_depth": raw_negative_depth,
        "track_lengths": dict(Counter(map(int, lengths))),
        "fraction_length_2": float(np.mean(lengths == 2)),
        "pixels": stats(error), "nonpositive_depth": int(np.sum(depth <= 0)),
        "past_3px_observations": int((error > 3).sum()),
        "min_2valid_obs_and_1deg_points": int(common_gate.sum()),
        "max_triangulation_angle_deg": stats(angles), "focal_work_px": float(data["K_work"][0, 0]),
        "principal_work_px": data["K_work"][:2, 2].tolist(), "k1": float(data["k1"]),
        "regions": details, "target_points": int(target.sum()),
        "target_active_track_3plus": int(np.sum(target & (lengths >= 3))),
        "target_error_px": stats(error[target_hits]), "target_parallax_deg": stats(angles[target]),
        "target_common_gate": int(np.sum(target & common_gate)),
    }
    return report, centers, target, lengths


def native_graph(run, inputs):
    keypoints, raw, verified = {}, {}, {}
    with np.load(run / "appearance.npz") as data:
        for row in inputs:
            keypoints[row["id"]] = data[f"xy_{row['id']}"]
        for j, row in enumerate(read(run / "appearance.json")["pairs"]):
            key = (row["i"], row["j"])
            raw[key] = data[f"indices_{j}"]
            verified[key] = raw[key][data[f"inliers_{j}"]]
    return keypoints, raw, verified


def external_graph(run, inputs):
    names = {r["name"]: r["id"] for r in inputs}
    with sqlite3.connect(f"file:{run.resolve() / 'database.db'}?mode=ro", uri=True) as sql:
        convert = {i: names[name] for i, name in sql.execute("SELECT image_id,name FROM images")}
        keypoints = {
            convert[i]: np.frombuffer(blob, dtype="<f4").reshape(n, d)[:, :2].astype(float) - .5
            for i, n, d, blob in sql.execute("SELECT image_id,rows,cols,data FROM keypoints")
        }
        graphs = []
        for table in ("matches", "two_view_geometries"):
            graph = {}
            for pair, n, d, blob in sql.execute(f"SELECT pair_id,rows,cols,data FROM {table}"):
                first, second = divmod(pair, 2147483647)
                a, b = convert[first], convert[second]
                values = np.frombuffer(blob or b"", dtype="<u4").reshape(n, d or 2)
                graph[tuple(sorted((a, b)))] = values if a < b else values[:, ::-1]
            graphs.append(graph)
    return (keypoints, *graphs)


def graph_summary(graph, regions, common):
    keypoints, raw, verified = graph
    result = {"features": sum(map(len, keypoints.values())), "matched_pairs": sum(bool(len(a)) for a in raw.values()),
              "verified_pairs": sum(bool(len(a)) for a in verified.values()),
              "raw_edges": sum(map(len, raw.values())), "verified_edges": sum(map(len, verified.values())),
              "regions": {}}
    for label in regions.masks:
        hit = {i: regions.hits(label, i, xy) for i, xy in keypoints.items()}
        info = {"features_inside": sum(int(flags.sum()) for flags in hit.values()), "view": {}}
        for scope, pair_filter in (("all", lambda pair: True), ("reference_pair_schedule", common.__contains__)):
            for stage, edges in (("matched", raw), ("verified", verified)):
                region_edges, nodes = 0, Counter()
                for (i, j), index in edges.items():
                    if not pair_filter((i, j)) or not len(index):
                        continue
                    a, b = index.T
                    use = hit[i][a] & hit[j][b]
                    if not use.any():
                        continue
                    region_edges += int(use.sum())
                    nodes.update((i, int(k)) for k in np.unique(a[use]))
                    nodes.update((j, int(k)) for k in np.unique(b[use]))
                info[f"{scope}_{stage}_edges"] = region_edges
                info[f"{scope}_{stage}_unique_features"] = len(nodes)
                info[f"{scope}_{stage}_features_connected_to_2plus_other_views"] = sum(
                    n >= 2 for n in nodes.values()
                )
                if scope == "all" and stage == "verified":
                    verified_by_view = Counter(i for i, _ in nodes)
                    info["view"] = {str(i): {"features": int(flags.sum()),
                                            "verified_unique": verified_by_view[i]}
                                    for i, flags in hit.items() if i in regions.masks[label]}
        result["regions"][label] = info
    return result


def native_region_candidates(run, regions):
    """Count measurement-only region support before reconstruction rejects observations."""
    result = Counter()
    for track in read(run / "tracks.json"):
        for label, views in regions.masks.items():
            hits = sum(regions.hits(label, o["image_id"], np.array([o["xy_work_distorted"]]))[0]
                       for o in track["observations"] if o["image_id"] in views)
            if hits >= 2:
                result[label] += 1
    return dict(result)


def region_image_stats(reference, inputs, regions):
    """Descriptive texture/brightness at the common annotation preview resolution."""
    images = {}
    for i in set().union(*(by_view.keys() for by_view in regions.masks.values())):
        decoded = cv2.imread(str(reference / "frames" / inputs[i]["name"]), cv2.IMREAD_GRAYSCALE)
        preview = cv2.resize(decoded, regions.size.tolist(), interpolation=cv2.INTER_AREA)
        images[i] = (preview, cv2.Laplacian(preview, cv2.CV_64F))
    return {label: {
        i: {"source_frame": inputs[i]["source_frame"], "preview_pixels": int(mask.sum()),
            "median_gray": float(np.median(images[i][0][mask > 0])),
            "laplacian_rms": float(np.sqrt(np.mean(images[i][1][mask > 0] ** 2)))}
        for i, mask in by_view.items() if mask.any()
    } for label, by_view in regions.masks.items()}


def align(ref, run, base_c, run_c):
    ids, i, j = np.intersect1d(ref["image_ids"], run["image_ids"], return_indices=True)
    if len(ids) < 3:
        raise ValueError("Fewer than three shared cameras for similarity alignment")
    a, b = run_c[j], base_c[i]
    ac, bc = a.mean(axis=0), b.mean(axis=0)
    a, b = a - ac, b - bc
    if min(np.linalg.matrix_rank(a), np.linalg.matrix_rank(b)) < 2:
        raise ValueError("Camera centers are collinear")
    u, s, v = np.linalg.svd(a.T @ b)
    sign = np.array([1, 1, np.linalg.det(u @ v)])
    rotation = (u * sign) @ v
    scale = (s @ sign) / np.sum(a ** 2)
    offset = bc - scale * ac @ rotation
    orbit_radius = np.sqrt(np.mean(np.sum(b ** 2, axis=1)))
    residuals = np.linalg.norm(scale * a @ rotation - b, axis=1) / orbit_radius
    rotations = run["R_cw"][j] @ rotation @ ref["R_cw"][i].transpose(0, 2, 1)
    degree = np.rad2deg(Rotation.from_matrix(rotations).magnitude())
    return scale, rotation, offset, {"common_camera_ids": ids.tolist(), "scale": float(scale),
                                     "row_rotation": rotation.tolist(), "offset": offset.tolist(),
                                     "centers_over_reference_orbit_rms_radius": stats(residuals),
                                     "rotations_deg": stats(degree)}


def cube(points, margin=1.12):
    lo, hi = points.min(axis=0), points.max(axis=0)
    center = (lo + hi) / 2
    half = np.max(hi - lo) * margin / 2
    return center - half, center + half


def common_figures(rows, directory):
    reference = rows[0][1]
    up = -reference["R_cw"][:, 1].mean(axis=0)
    up /= np.linalg.norm(up)
    right = reference["R_cw"][0, 0].copy()
    right -= right @ up * up
    right /= np.linalg.norm(right)
    basis = np.column_stack((right, np.cross(up, right), up))
    origin = np.median(rows[0][2]["xyz"][rows[0][3]], axis=0)
    clouds = [(aligned["xyz"] - origin) @ basis for _, _, aligned, _, _ in rows]
    cameras = [(aligned["centers"] - origin) @ basis for _, _, aligned, _, _ in rows]
    targets = np.vstack([cloud[mask] for cloud, (_, _, _, mask, _) in zip(clouds, rows, strict=True)])
    target_envelope = np.quantile(targets, [.01, .99], axis=0)
    near = cube(np.vstack(cameras + [target_envelope]), margin=1.2)
    close = cube(target_envelope, margin=1.16)
    full = cube(np.vstack(clouds + cameras))
    report = {"shared_limits": {k: np.array(limit).tolist() for k, limit in
                               (("scene", near), ("target", close), ("unclipped", full))},
              "view_elev_azim": [24, -72], "view_basis": basis.tolist(), "view_origin": origin.tolist(),
              "points_outside": {}}
    fig = plt.figure(figsize=(12, 3.65 * len(rows)), layout="constrained")
    entire = plt.figure(figsize=(4.3 * len(rows), 4), layout="constrained")

    def draw(ax, xyz, color, low, high, title, point_size, centers=None, vectors=None):
        ax.scatter(*xyz.T, c=color / 255, s=point_size, depthshade=False, linewidths=0)
        if centers is not None:
            ax.scatter(*centers.T, color="#137893", s=8, depthshade=False)
            ax.quiver(*centers.T, *vectors.T, color="#137893", length=max(high - low) * .026,
                      linewidths=.65)
        for lim, left, right_edge in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), low, high, strict=True):
            lim(left, right_edge)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=24, azim=-72)
        ax.set_title(title, fontsize=9)
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.set_zticklabels([])

    for i, ((label, data, aligned, target, lengths), xyz, C) in enumerate(zip(rows, clouds, cameras, strict=True)):
        sets = (np.ones(len(xyz), dtype=bool), target, target & (lengths >= 3))
        specs = (("Scene", near, .9), ("Region-supported", close, 4), ("Region + track ≥3", close, 4))
        out = {}
        vectors = aligned["directions"] @ basis
        for j, (subset, (kind, (low, high), size)) in enumerate(zip(sets, specs, strict=True)):
            inside = ((xyz >= low) & (xyz <= high)).all(axis=1)
            sel = subset & inside
            out[kind] = int(np.sum(subset & ~inside))
            draw(fig.add_subplot(len(rows), 3, 3 * i + j + 1, projection="3d"),
                 xyz[sel], data["rgb"][sel], low, high,
                 f"{label} · {kind}\n{sel.sum():,} shown / {subset.sum():,}", size,
                 C if j == 0 else None, vectors if j == 0 else None)
        draw(entire.add_subplot(1, len(rows), i + 1, projection="3d"), xyz, data["rgb"], *full,
             f"{label} · {len(xyz):,} points", .7, C, vectors)
        out["Unclipped"] = 0
        report["points_outside"][label] = out
    fig.savefig(directory / "aligned_comparison.png", dpi=165)
    entire.savefig(directory / "aligned_unclipped.png", dpi=150)
    plt.close(fig)
    plt.close(entire)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("runs", nargs="+", help="LABEL=PATH, reference first")
    parser.add_argument("--metrics-only", action="store_true")
    args = parser.parse_args()
    regions = Regions.load(args.reference, args.labels)
    inputs = input_manifest(args.reference)
    args.output.mkdir(parents=True)
    write(args.output / "frame_manifest.json", inputs)
    common = {(p["i"], p["j"]) for p in read(args.reference / "pairs.json")}
    report = {"audit_labels": str(regions.labels_path), "models": {}, "alignment": {},
              "region_image_stats": region_image_stats(args.reference, inputs, regions)}
    rows = []
    for index, parameter in enumerate(args.runs):
        label, path = parameter.split("=", 1)
        run = Path(path)
        external = (run / "observations_work_px.npz").exists()
        manifest = read(run / "frame_manifest.json") if (run / "frame_manifest.json").exists() else input_manifest(run)
        if inputs != manifest:
            raise ValueError(f"Input content differs for {run}")
        data = load_map(run)
        result, centers, target, lengths = measure(data, regions)
        graph = external_graph(run, inputs) if external else native_graph(run, inputs)
        result["appearance"] = graph_summary(graph, regions, common)
        if not external:
            result["appearance"]["candidate_tracks_observed_in_two_labeled_views"] = (
                native_region_candidates(run, regions)
            )
        result["run"] = str(run.resolve())
        report["models"][label] = result
        if index == 0:
            base_c = centers
            scale, rotation, offset = 1, np.eye(3), np.zeros(3)
        else:
            scale, rotation, offset, detail = align(rows[0][1], data, base_c, centers)
            report["alignment"][label] = detail
        aligned = {"xyz": scale * data["xyz"] @ rotation + offset,
                   "centers": scale * centers @ rotation + offset,
                   "directions": data["R_cw"][:, 2] @ rotation}
        rows.append((label, data, aligned, target, lengths))
        np.savez_compressed(args.output / f"aligned_{index}.npz", xyz=aligned["xyz"], rgb=data["rgb"],
                            centers=aligned["centers"], image_ids=data["image_ids"],
                            region_supported=target, track_lengths=lengths)
    if not args.metrics_only:
        report["display"] = common_figures(rows, args.output)
    write(args.output / "comparison.json", report)
    for label, row in report["models"].items():
        print(label, row["registered"], row["points"], row["target_points"],
              row["target_active_track_3plus"], row["pixels"]["rmse"])


if __name__ == "__main__":
    main()
