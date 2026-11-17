"""C: reproducible result files and headless diagnostic figures."""

from collections import Counter
import csv
import json

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .bundle import distribution
from .triangulation import max_angle


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False,
                               default=lambda value: value.item() if isinstance(value, np.generic)
                               else value.tolist()) + "\n")


def contact_sheet(frames, destination, tile_width=190, columns=5):
    width, height = frames[0].record["work_size"]
    tile_height = round(tile_width * height / width)
    columns = min(columns, len(frames))
    rows = (len(frames) + columns - 1) // columns
    result = np.full((rows * tile_height, columns * tile_width, 3), 245, dtype=np.uint8)
    for frame in frames:
        tile = cv2.resize(frame.image, (tile_width, tile_height), interpolation=cv2.INTER_AREA)
        label = f'{frame.id:02d} / {frame.record["source_frame"]:03d}'
        cv2.rectangle(tile, (0, 0), (90, 21), (30, 30, 30), -1)
        cv2.putText(tile, label, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1,
                    cv2.LINE_AA)
        r, c = divmod(frame.id, columns)
        result[r*tile_height:(r+1)*tile_height, c*tile_width:(c+1)*tile_width] = tile
    cv2.imwrite(str(destination), result)


def match_visualization(pair, frames, path, seed):
    a, b = [frames[i] for i in (pair.i, pair.j)]
    display = np.hstack((a.image, b.image))
    rng = np.random.default_rng(seed)
    for mask, color in [(~pair.inliers, (55, 73, 235)), (pair.inliers, (124, 239, 107))]:
        pool = np.flatnonzero(mask)
        sample = rng.choice(pool, min(len(pool), 90), replace=False)
        for p, q in pair.indices[sample]:
            u = np.rint(a.xy[p]).astype(int)
            v = np.rint(b.xy[q] + [a.image.shape[1], 0]).astype(int)
            cv2.line(display, u, v, color, 1, cv2.LINE_AA)
            cv2.circle(display, u, 4, color, -1, cv2.LINE_AA)
            cv2.circle(display, v, 4, color, -1, cv2.LINE_AA)
    cv2.imwrite(str(path), display)


def write_ply(path, points, colors):
    with path.open("w") as file:
        file.write("ply\nformat ascii 1.0\n")
        file.write(f"element vertex {len(points)}\n")
        file.write("property double x\nproperty double y\nproperty double z\n")
        file.write("property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        np.savetxt(file, np.column_stack((points, colors)), fmt="%.10g %.10g %.10g %d %d %d")


def point_arrays(state):
    tids = sorted(state.points)
    xyz = np.array([state.points[i].xyz for i in tids]).reshape(-1, 3)
    rgb = np.array([
        np.median([state.frames[v].rgb[state.tracks[i][v]] for v in state.points[i].active], axis=0)
        for i in tids
    ], dtype=np.uint8).reshape(-1, 3)
    return tids, xyz, rgb


def plot_map(path, xyz, rgb, poses, subset_label=None, show_cameras=True):
    ids = sorted(poses)
    centers = np.array([poses[i].center for i in ids])
    directions = np.array([poses[i].R[2] for i in ids])
    all_points = np.vstack((xyz, centers)) if show_cameras else xyz
    median = np.median(all_points, axis=0)
    # Use a camera-based orientation so typical orbit data has a legible horizontal plane.
    up = -np.mean([poses[i].R[1] for i in ids], axis=0)
    up /= max(np.linalg.norm(up), 1e-12)
    right = poses[ids[0]].R[0].copy()
    right -= (right @ up) * up
    right /= max(np.linalg.norm(right), 1e-12)
    basis = np.column_stack((right, np.cross(up, right), up))
    plot_xyz = (xyz - median) @ basis
    plot_c = (centers - median) @ basis
    plot_d = directions @ basis
    extent = np.vstack((plot_xyz, plot_c)) if show_cameras else plot_xyz
    low, high = extent.min(axis=0), extent.max(axis=0)
    midpoint = (low + high) / 2
    span = (high - low).max()
    figure = plt.figure(figsize=(11, 5), layout="constrained")
    viewpoints = ((22, -75), (75, -120)) if show_cameras else ((7, -80), (9, 18))
    for index, (elev, azim) in enumerate(viewpoints, start=1):
        ax = figure.add_subplot(1, 2, index, projection="3d")
        size = (4 if subset_label else 1.6) if show_cameras else 9
        ax.scatter(*plot_xyz.T, c=rgb / 255, s=size, depthshade=False)
        if show_cameras:
            ax.plot(*plot_c.T, "o-", color="#166b9b", markersize=2.8, linewidth=1)
            ax.quiver(*plot_c.T, *plot_d.T, length=span * 0.025, color="#166b9b", linewidth=0.75)
        for setter, center in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), midpoint, strict=True):
            setter(center - span * .52, center + span * .52)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.set_title(("Oblique" if index == 1 else "Overhead") if show_cameras else f"View {index}")
    label = subset_label or "Scene"
    cameras_label = f" · {len(ids)} cameras" if show_cameras else ""
    figure.suptitle(f"{label} · {len(xyz):,} points{cameras_label} · arbitrary units")
    figure.savefig(path, dpi=185)
    plt.close(figure)


def export_result(run, state, pairs, checks, elapsed, conflicts, initial_camera):
    figures = run / "figures"
    tids, xyz, rgb = point_arrays(state)
    rows = []
    all_errors, all_angles, final_lengths = [], [], []
    active_by_view = {frame.id: [] for frame in state.frames}
    for tid in tids:
        point = state.points[tid]
        final_lengths.append(len(point.active))
        all_angles.append(max_angle(point.xyz, np.array([state.poses[i].center for i in point.active])))
        for i in point.active:
            predicted, depth = state.camera.project_camera(state.poses[i].transform(point.xyz))
            actual = state.frames[i].xy[state.tracks[tid][i]]
            active_by_view[i].append((actual, predicted, float(np.linalg.norm(predicted - actual)),
                                      float(depth)))

    poses = state.poses
    camera_rows = []
    cameras_with_overlay = set(state.seed)
    registered_ids = sorted(poses)
    if registered_ids:
        cameras_with_overlay |= {registered_ids[0], registered_ids[len(poses) // 2], registered_ids[-1]}
    for frame in state.frames:
        i = frame.id
        pose = poses.get(i)
        failures = [event["reason"] for event in state.events
                    if event.get("image_id") == i and event["stage"] in ("pnp", "view_failure")]
        reason = failures[-1] if failures else ("seed" if i in state.seed else "no_valid_seed")
        errors = [entry[2] for entry in active_by_view[i]]
        all_errors.extend(errors)
        row = {"id": i, "source_frame": frame.record["source_frame"], "registered": i in poses,
               "reason": reason, "features": len(frame.xy), "observations": len(errors),
               "median_px": float(np.median(errors)) if errors else None}
        rows.append(row)
        camera_rows.append({**row, "R_cw": None if pose is None else pose.R,
                            "t_cw": None if pose is None else pose.t,
                            "center_world": None if pose is None else pose.center})
        if i in cameras_with_overlay and errors:
            canvas = frame.image.copy()
            for actual, predicted, _, _ in active_by_view[i]:
                # Blue-green marker = measured; magenta cross = predicted.
                measured, projected = np.rint([actual, predicted]).astype(int)
                cv2.circle(canvas, measured, 4, (212, 226, 46), 1, cv2.LINE_AA)
                cv2.drawMarker(canvas, projected, (225, 80, 248), cv2.MARKER_CROSS, 5, 1, cv2.LINE_AA)
            cv2.imwrite(str(figures / f"reprojection_{i:03d}.jpg"), canvas)

    write_json(run / "cameras.json", {
        "convention": "X_camera = R_cw @ X_world + t_cw; center = -R_cw.T @ t_cw",
        "scale": "arbitrary; fixed nonzero seed translation component", "K_work": state.camera.K,
        "distortion_opencv": state.camera.distortion, "initial_K_work": initial_camera.K,
        "cameras": camera_rows,
    })
    write_json(run / "tracks.json", [
        {"id": tid, "triangulated": tid in state.points, "observations": [
            {"image_id": i, "keypoint_id": kp, "xy_work_distorted": state.frames[i].xy[kp],
             "active": tid in state.points and i in state.points[tid].active}
            for i, kp in track.items()]} for tid, track in enumerate(state.tracks)
    ])
    pair_rows = [{"i": p.i, "j": p.j, **p.counts, **checks.get((p.i, p.j), {})} for p in pairs]
    write_json(run / "pairs.json", pair_rows)
    with (run / "events.jsonl").open("w") as history:
        for event in state.events:
            history.write(json.dumps(event, allow_nan=False, default=lambda value: value.item()) + "\n")
    with (run / "per_view.csv").open("w", newline="") as table:
        writer = csv.DictWriter(table, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    metrics = {
        "status": state.status, "views": len(rows), "registered": len(poses),
        "registration_rate": len(poses) / len(rows), "seed_pair": state.seed,
        "points": len(tids), "candidate_tracks": len(state.tracks), "track_conflicts": conflicts,
        "candidate_track_lengths": dict(Counter(len(track) for track in state.tracks)),
        "active_track_lengths": dict(Counter(final_lengths)),
        "registered_view_failures": [r for r in rows if r["reason"] == "low_final_3d_support"],
        "unregistered_views": [{k: r[k] for k in ("id", "source_frame", "reason")}
                               for r in rows if not r["registered"]],
        "final_reprojection_px": distribution(all_errors),
        "max_triangulation_angle_deg": distribution(all_angles),
        "initial_focal_work_px": initial_camera.focal, "estimated_focal_work_px": state.camera.focal,
        "estimated_k1": state.camera.k1, "bundle_adjustment": state.ba,
        "quality_gates": [event for event in state.events if event["stage"] == "quality_gate"],
        "pairs_tested": len(pairs), "pairs_verified": sum(pair.F is not None for pair in pairs),
        "elapsed_seconds": elapsed,
    }
    if len(xyz):
        write_ply(run / "pointcloud.ply", xyz, rgb)
        np.savez_compressed(run / "reconstruction.npz", track_ids=tids, xyz=xyz, rgb=rgb,
                            image_ids=registered_ids, R_cw=np.array([poses[i].R for i in registered_ids]),
                            t_cw=np.array([poses[i].t for i in registered_ids]),
                            K_work=state.camera.K, k1=state.camera.k1)
        plot_map(figures / "scene_and_cameras.png", xyz, rgb, poses)
        fig, ax = plt.subplots(figsize=(6, 3.2), layout="constrained")
        ax.hist(all_errors, bins=36, color="#27688f")
        ax.set(xlabel="Raw-pixel reprojection error (px)", ylabel="Observations")
        ax.axvline(np.median(all_errors), color="#d34956", label="Median")
        ax.legend()
        fig.savefig(figures / "reprojection_histogram.png", dpi=170)
        plt.close(fig)
    for label, pair in [
        ("seed", next((p for p in pairs if (p.i, p.j) == state.seed), None)),
        ("weakest", min((p for p in pairs if p.j - p.i == 1),
                        key=lambda p: int(p.inliers.sum()), default=None)),
        ("loop", max((p for p in pairs if p.counts["schedule"] == "boundary"),
                     key=lambda p: int(p.inliers.sum()), default=None)),
    ]:
        if pair is not None:
            match_visualization(pair, state.frames, figures / f"matches_{label}_{pair.i:02d}_{pair.j:02d}.jpg",
                                seed=pair.i + 6121)
    return metrics
