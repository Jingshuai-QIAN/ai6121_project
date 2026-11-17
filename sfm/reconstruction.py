"""C: incremental map scheduling, quality filtering and final optimization."""

from collections import Counter

import numpy as np

from .bundle import bundle_adjust, distribution
from .geometry import register_pnp, sampson_signed, seed_pose, skew, homogeneous
from .model import Reconstruction
from .triangulation import Triangulator


def largest_component(pairs, count):
    neighbors = [set() for _ in range(count)]
    for pair in pairs:
        if pair.F is not None:
            neighbors[pair.i].add(pair.j)
            neighbors[pair.j].add(pair.i)
    remaining = set(range(count))
    components = []
    while remaining:
        pending = [min(remaining)]
        component = set()
        while pending:
            i = pending.pop()
            if i in remaining:
                remaining.remove(i)
                component.add(i)
                pending.extend(neighbors[i] & remaining)
        components.append(component)
    return max(components, key=len)


def update_points(state, config, gate, allow_new, reason):
    before = state.points
    triangulator = Triangulator(state, config, gate)
    updated = {}
    candidates = 0
    lost_observations = gained_observations = 0
    for tid, track in enumerate(state.tracks):
        existing = before.get(tid)
        if existing is None and (not allow_new or len(track.keys() & state.poses.keys()) < 2):
            continue
        candidates += 1
        point = triangulator.fit(track, existing, allow_new=allow_new)
        if point is not None:
            updated[tid] = point
        old_active = set(existing.active) if existing is not None else set()
        new_active = set(point.active) if point is not None else set()
        lost_observations += len(old_active - new_active)
        gained_observations += len(new_active - old_active)
    state.points = updated
    diagnostic = {
        "stage": "quality_gate", "reason": reason, "threshold_px": gate,
        "candidates": candidates, "rejected_tracks": candidates - len(updated),
        "points_before": len(before), "points_after": len(updated),
        "points_created": len(updated.keys() - before.keys()),
        "points_removed": len(before.keys() - updated.keys()),
        "observations_removed": lost_observations, "observations_added": gained_observations,
    }
    state.events.append(diagnostic)
    return lost_observations > 0 or gained_observations > 0


def reconstruct(frames, pairs, tracks, initial_camera, config):
    component = largest_component(pairs, len(frames))
    state = Reconstruction(frames, tracks, initial_camera, (), {})
    ranked = sorted((p for p in pairs if p.F is not None and p.i in component),
                    key=lambda pair: -int(pair.inliers.sum()))
    seeds = []
    for pair in ranked[:config["seed_candidates"]]:
        poses, row = seed_pose(pair, frames, initial_camera, config)
        state.events.append({"stage": "seed_candidate", **row})
        if poses is not None:
            # Favor ample support and a wide baseline without rewarding extreme angles.
            score = row["points"] * min(1.0, row["median_angle_deg"] / 9)
            seeds.append((score, pair, poses))

    for _, pair, poses in sorted(seeds, key=lambda row: -row[0]):
        state.seed = (pair.i, pair.j)
        state.poses = dict(zip(state.seed, poses, strict=True))
        update_points(state, config, config["pixel_gate"], True, "seed")
        if len(state.points) >= config["min_pair_inliers"]:
            break
        state.events.append({"stage": "seed_rejected", "pair": list(state.seed),
                             "reason": "insufficient_triangulated_tracks_after_conflict_checks"})
        state.poses, state.points, state.seed = {}, {}, ()

    if not state.poses:
        state.status = "no_valid_seed"
        return state

    by_view = [[] for _ in frames]
    for tid, track in enumerate(tracks):
        for i in track:
            by_view[i].append(tid)
    attempts = Counter()
    last_attempt = {}
    revision = 0
    last_ba_size = len(state.poses)
    stalled_ba = False
    while len(state.poses) < len(component):
        options = []
        for i in sorted(component - state.poses.keys()):
            if attempts[i] >= config["max_attempts"] or last_attempt.get(i) == revision:
                continue
            supported = [tid for tid in by_view[i] if tid in state.points]
            options.append((i, supported))
        registered = False
        for i, supported in sorted(options, key=lambda item: (-len(item[1]), item[0])):
            available = len(supported) >= config["min_pnp_inliers"]
            if available:
                attempts[i] += 1
            last_attempt[i] = revision
            xyz = np.array([state.points[tid].xyz for tid in supported])
            pixels = np.array([frames[i].xy[tracks[tid][i]] for tid in supported])
            pose, detail = register_pnp(xyz, pixels, state.camera, config,
                                        (config["seed"] + 4099 * i + attempts[i]) % (2 ** 31))
            state.events.append({"stage": "pnp", "image_id": i, "attempt": attempts[i], **detail})
            if pose is None:
                continue
            state.poses[i] = pose
            update_points(state, config, config["pixel_gate"], True, f"registered_{i}")
            registered = True
            revision += 1
            stalled_ba = False
            break

        periodic = len(state.poses) - last_ba_size >= config["ba_every"]
        stalled = not registered and not stalled_ba and len(state.poses) >= 3
        if periodic or stalled:
            if bundle_adjust(state, initial_camera, config, "incremental",
                             config["ba_evaluations"]):
                update_points(state, config, config["pixel_gate"], True, "after_incremental_ba")
                revision += 1
            last_ba_size = len(state.poses)
            stalled_ba = not registered
        elif not registered:
            break

    completed_focal = bundle_adjust(state, initial_camera, config, "final_focal",
                                     config["ba_final_evaluations"])
    if completed_focal and config["fit_k1"] and len(state.poses) >= 5:
        bundle_adjust(state, initial_camera, config, "final_radial", config["ba_final_evaluations"],
                      fit_k1=True)
    changed = update_points(state, config, config["final_pixel_gate"], False, "final_filter")
    if completed_focal and changed:
        use_k1 = any(row["fit_k1"] and row["accepted"] for row in state.ba)
        bundle_adjust(state, initial_camera, config, "after_filter",
                      config["ba_final_evaluations"], fit_k1=use_k1)
        update_points(state, config, config["final_pixel_gate"], False, "after_filter_ba")

    active_by_view = Counter(i for point in state.points.values() for i in point.active)
    unsupported = [i for i in state.poses if active_by_view[i] < config["min_pnp_inliers"]]
    for i in sorted(set(range(len(frames))) - component):
        state.events.append({"stage": "view_failure", "image_id": i, "reason": "disconnected"})
    for i in unsupported:
        state.events.append({"stage": "view_failure", "image_id": i, "reason": "low_final_3d_support",
                             "active_observations": active_by_view[i]})
    long_tracks = any(len(point.active) >= 3 for point in state.points.values())
    if not completed_focal or not state.points:
        state.status = "ba_or_filter_failed"
    elif len(frames) == 2:
        state.status = "two_view"
    elif len(state.poses) < 5 or unsupported or not long_tracks or len(state.poses) < len(frames):
        state.status = "partial"
    else:
        state.status = "success"
    return state


def final_pair_geometry(state, pairs, threshold):
    """Compare the final pose-derived epipolar geometry against original pair matches."""
    normalized = {i: homogeneous(state.camera.normalize(state.frames[i].xy)) for i in state.poses}
    checks = {}
    for pair in pairs:
        if pair.F is None or pair.i not in state.poses or pair.j not in state.poses:
            continue
        a, b = state.poses[pair.i], state.poses[pair.j]
        R = b.R @ a.R.T
        t = b.t - R @ a.t
        E = skew(t) @ R
        i, j = pair.indices[pair.inliers].T
        error = np.abs(sampson_signed(E, normalized[pair.i][i], normalized[pair.j][j]))
        px = state.camera.focal * error
        checks[(pair.i, pair.j)] = {
            "final_epipolar_equivalent_px": distribution(px[np.isfinite(px)]),
            "final_epipolar_pass": int(np.sum(px <= threshold)),
            "final_epipolar_nonfinite": int(np.sum(~np.isfinite(px))),
        }
    return checks
