"""B: normalized eight-point geometry, RANSAC, essential pose and PnP."""

import math

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .model import Pose
from .triangulation import angle_degrees, error_and_depth, triangulate_dlt, unit


def homogeneous(xy):
    return np.column_stack((xy, np.ones(len(xy))))


def normalize_points_2d(xy):
    center = xy.mean(axis=0)
    centered = xy - center
    spread = np.linalg.norm(centered, axis=1).mean()
    if not np.isfinite(spread) or spread < 1e-10:
        raise ValueError("Coincident or nonfinite coordinates")
    scale = np.sqrt(2) / spread
    transform = np.eye(3)
    transform[:2, :2] *= scale
    transform[:2, 2] = -scale * center
    return homogeneous(centered * scale), transform


def eight_point(first, second):
    if len(first) != len(second) or len(first) < 8:
        raise ValueError("Eight paired observations are required")
    a, T_a = normalize_points_2d(first)
    b, T_b = normalize_points_2d(second)
    rows = (b[:, :, None] * a[:, None, :]).reshape(-1, 9)
    _, singular, vh = np.linalg.svd(rows, full_matrices=len(rows) == 8)
    if singular[7] < singular[0] * 1e-7:
        raise ValueError("Rank-deficient eight-point sample")
    u, s, v = np.linalg.svd(vh[-1].reshape(3, 3))
    s[2] = 0
    F = T_b.T @ ((u * s) @ v) @ T_a
    return F / np.linalg.norm(F)


def sampson_signed(F, first_h, second_h):
    lines_b = first_h @ F.T
    lines_a = second_h @ F
    numerator = np.sum(second_h * lines_b, axis=1)
    denominator = np.linalg.norm(np.column_stack((lines_a[:, :2], lines_b[:, :2])), axis=1)
    return numerator / np.where(denominator > 1e-15, denominator, np.nan)


def fundamental_ransac(first, second, threshold, max_trials, rng):
    count = len(first)
    if count < 8:
        return None, np.zeros(count, dtype=bool), np.full(count, np.inf), 0, 0
    a, b = homogeneous(first), homogeneous(second)
    best = None
    score = (0, -np.inf)
    trials = degenerate = 0
    budget = max_trials

    def evaluate(F):
        errors = np.abs(sampson_signed(F, a, b))
        mask = errors <= threshold
        score = (int(mask.sum()), -float(np.median(errors[mask]))) if mask.any() else (0, -np.inf)
        return score, mask, errors

    while trials < budget:
        sample = rng.choice(count, 8, replace=False)
        trials += 1
        try:
            F = eight_point(first[sample], second[sample])
        except (ValueError, np.linalg.LinAlgError):
            degenerate += 1
            continue
        candidate, mask, errors = evaluate(F)
        if candidate > score:
            score, best = candidate, (F, mask, errors)
            all_inliers = (score[0] / count) ** 8
            required = 1 if all_inliers == 1 else math.ceil(math.log(0.001) / math.log1p(-all_inliers))
            budget = min(budget, max(32, required))
    if best is None:
        return None, np.zeros(count, dtype=bool), np.full(count, np.inf), trials, degenerate
    F, mask, errors = best
    for _ in range(5):
        if mask.sum() < 8:
            break
        try:
            refined = eight_point(first[mask], second[mask])
        except (ValueError, np.linalg.LinAlgError):
            break
        candidate, new_mask, new_errors = evaluate(refined)
        if candidate < score:
            break
        stable = np.array_equal(mask, new_mask)
        score, F, mask, errors = candidate, refined, new_mask, new_errors
        if stable:
            break
    return F, mask, errors, trials, degenerate


def verify_pair(pair, first, second, config, rng):
    i, j = pair.indices.T
    F, mask, errors, trials, degenerate = fundamental_ransac(
        first.xy[i], second.xy[j], config["sampson_px"], config["ransac_trials"], rng,
    )
    pair.counts.update(ransac_inliers=int(mask.sum()), trials=trials, degenerate_samples=degenerate)
    if mask.sum() >= config["min_pair_inliers"]:
        pair.F, pair.inliers, pair.errors = F, mask, errors
        pair.counts["status"] = "verified"
    else:
        pair.counts["status"] = "insufficient_geometry_inliers"


def decompose_essential(E):
    u, _, v = np.linalg.svd(E)
    if np.linalg.det(u) < 0:
        u[:, -1] *= -1
    if np.linalg.det(v) < 0:
        v[-1] *= -1
    W = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    # Equivalent to enforcing singular values (s,s,0) before decomposition.
    return [Pose(u @ w @ v, sign * u[:, 2]) for w in (W, W.T) for sign in (1, -1)]


def skew(t):
    x, y, z = t
    return np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])


def refine_relative_pose(pose, a, b, camera, px):
    fixed = np.argmax(np.abs(pose.t))
    free = np.arange(3) != fixed
    a_h, b_h = homogeneous(a), homogeneous(b)

    def unpack(params):
        R = Rotation.from_rotvec(params[:3]).as_matrix()
        t = pose.t.copy()
        t[free] = params[3:]
        return Pose(R, unit(t))

    def residual(params):
        candidate = unpack(params)
        return camera.focal * sampson_signed(skew(candidate.t) @ candidate.R, a_h, b_h)

    initial = np.r_[Rotation.from_matrix(pose.R).as_rotvec(), pose.t[free]]
    if not np.all(np.isfinite(residual(initial))):
        return pose
    try:
        result = least_squares(residual, initial, loss="huber", f_scale=px, max_nfev=35)
    except (ValueError, np.linalg.LinAlgError):
        return pose
    return unpack(result.x)


def seed_pose(pair, frames, camera, config):
    p, q = pair.indices[pair.inliers].T
    first, second = frames[pair.i].xy[p], frames[pair.j].xy[q]
    a, b = camera.normalize(first), camera.normalize(second)
    first_pose = Pose(np.eye(3), np.zeros(3))
    bearings = homogeneous(a)
    best, best_score = None, (0, 0.0)
    diagnostic = {"pair": [pair.i, pair.j], "inliers": len(a), "status": "low_parallax_or_cheirality"}
    for hypothesis in decompose_essential(camera.K.T @ pair.F @ camera.K):
        # The unrestricted F used for matching need not have exact essential singular values.
        pose = refine_relative_pose(hypothesis, a, b, camera, config["sampson_px"])
        matrices = np.stack((first_pose.matrix, pose.matrix))
        points = triangulate_dlt(matrices, np.stack((a, b), axis=1))
        error_a, depth_a = error_and_depth(camera, first_pose, points, first)
        error_b, depth_b = error_and_depth(camera, pose, points, second)
        angles = angle_degrees(unit(bearings), unit(homogeneous(b) @ pose.R))
        positive = (depth_a > 0) & (depth_b > 0)
        consistent = positive & (np.maximum(error_a, error_b) <= config["pixel_gate"])
        good = consistent & (angles >= config["min_angle"])
        median_angle = float(np.median(angles[consistent])) if consistent.any() else 0.0
        score = (int(good.sum()), median_angle)
        if score > best_score or best is None:
            best_score = score
            best = first_pose, pose
            diagnostic.update(points=score[0], median_angle_deg=median_angle,
                              positive_depth_ratio=float(positive.mean()))
    if (best_score[0] >= config["min_pair_inliers"] and
        best_score[1] >= config["min_seed_angle"] and
        diagnostic["positive_depth_ratio"] >= 0.75):
        diagnostic["status"] = "usable"
        return best, diagnostic
    return None, diagnostic


def register_pnp(xyz, pixels, camera, config, seed):
    minimum = config["min_pnp_inliers"]
    if len(xyz) < minimum:
        return None, {"reason": "insufficient_3d_2d_support", "correspondences": len(xyz)}
    cv2.setRNGSeed(seed)
    xyz, pixels = np.ascontiguousarray(xyz), np.ascontiguousarray(pixels)
    try:
        ok, r, t, inliers = cv2.solvePnPRansac(
            xyz, pixels, camera.K, camera.distortion, iterationsCount=1000,
            reprojectionError=config["pixel_gate"], confidence=0.999, flags=cv2.SOLVEPNP_EPNP,
        )
        if not ok or len(inliers) < minimum:
            return None, {"reason": "pnp_ransac_failed", "correspondences": len(xyz),
                          "ransac_inliers": 0 if inliers is None else int(inliers.size)}
        r, t = cv2.solvePnPRefineLM(xyz[inliers[:, 0]], pixels[inliers[:, 0]],
                                    camera.K, camera.distortion, r, t)
    except cv2.error as error:
        return None, {"reason": "pnp_exception", "message": str(error), "correspondences": len(xyz)}
    pose = Pose(cv2.Rodrigues(r)[0], t.ravel())
    error, depth = error_and_depth(camera, pose, xyz, pixels)
    good = (depth > 0) & (error <= config["pixel_gate"])
    count = int(good.sum())
    ratio = float(good.mean())
    diagnostic = {"correspondences": len(good), "inliers": count, "inlier_ratio": ratio,
                  "median_px": float(np.median(error[good])) if count else None}
    if count < minimum or ratio < config["min_pnp_ratio"]:
        return None, {"reason": "pnp_refinement_rejected", **diagnostic}
    return pose, {"reason": "registered", **diagnostic}
