"""C: sparse bundle adjustment in distorted working pixels."""

from time import perf_counter
from types import SimpleNamespace
import warnings

import cv2
import numpy as np
from scipy.linalg import LinAlgWarning, solve
from scipy.sparse import bsr_matrix, coo_matrix
from scipy.spatial.transform import Rotation

from .model import Camera, Point, Pose


def distribution(values):
    values = np.asarray(values)
    if not values.size:
        return {"count": 0}
    return {
        "count": values.size, "rmse": float(np.sqrt(np.mean(values ** 2))),
        "median": float(np.median(values)), "mean": float(values.mean()),
        "p90": float(np.percentile(values, 90)), "p95": float(np.percentile(values, 95)),
        "max": float(values.max()),
    }


def huber_cost(residual):
    absolute = np.abs(residual)
    return float(np.where(absolute <= 2, absolute ** 2 / 2, 2 * (absolute - 1)).sum())


class BundleProblem:
    """Stable observations, exact gauge removal and analytic sparse derivatives."""

    def __init__(self, state, initial_camera, fit_k1, config):
        self.state = state
        self.fit_k1 = fit_k1
        self.config = config
        self.initial_camera = initial_camera
        self.views = sorted(state.poses)
        self.point_ids = sorted(state.points)
        self.view_slots = np.full((len(self.views), 6), -1)
        self.base_views = np.array([
            np.r_[Rotation.from_matrix(state.poses[i].R).as_rotvec(), state.poses[i].t]
            for i in self.views
        ])
        self.xyz = np.array([state.points[i].xyz for i in self.point_ids])

        free = np.ones_like(self.view_slots, dtype=bool)
        free[self.views.index(state.seed[0])] = False
        anchor = self.views.index(state.seed[1])
        fixed_axis = np.argmax(np.abs(self.base_views[anchor, 3:]))
        free[anchor, 3 + fixed_axis] = False
        self.view_slots[free] = np.arange(free.sum())
        self.free = free
        self.camera_end = int(free.sum())
        self.point_end = self.camera_end + self.xyz.size
        self.x0 = np.r_[self.base_views[free], self.xyz.ravel(), np.log(state.camera.focal)]
        if fit_k1:
            self.x0 = np.r_[self.x0, state.camera.k1]
        self.lower = np.full(len(self.x0), -np.inf)
        self.upper = np.full(len(self.x0), np.inf)
        edge = max(state.frames[0].image.shape[:2])
        self.lower[self.point_end], self.upper[self.point_end] = np.log(
            edge * np.array(config["focal_bounds"])
        )
        if fit_k1:
            self.lower[-1], self.upper[-1] = -config["k1_bound"], config["k1_bound"]
        self.prior = np.array([np.log(initial_camera.focal), 0.0][:1 + fit_k1])
        self.sigma = np.array([config["log_focal_prior_sigma"], config["k1_prior_sigma"]][:1 + fit_k1])

        view_index = {image_id: i for i, image_id in enumerate(self.views)}
        camera_obs, point_obs, pixels = [], [], []
        for point_index, tid in enumerate(self.point_ids):
            for image_id in state.points[tid].active:
                camera_obs.append(view_index[image_id])
                point_obs.append(point_index)
                pixels.append(state.frames[image_id].xy[state.tracks[tid][image_id]])
        self.camera_obs = np.array(camera_obs)
        self.point_obs = np.array(point_obs)
        self.pixels = np.array(pixels)
        self.depth_weight = edge * 0.25
        self.n = len(pixels)

        point_cols = self.camera_end + 3 * self.point_obs[:, None] + np.arange(3)
        intrinsic_cols = np.tile(np.arange(self.point_end, len(self.x0)), (self.n, 1))
        cols = np.column_stack((self.view_slots[self.camera_obs], point_cols, intrinsic_cols))
        self.cols = np.broadcast_to(cols[:, None, :], (self.n, 3, cols.shape[1]))
        self.rows = np.broadcast_to(np.arange(3 * self.n).reshape(self.n, 3, 1), self.cols.shape)
        self.nonfixed = self.cols >= 0

    def unpack(self, params):
        views = self.base_views.copy()
        views[self.free] = params[:self.camera_end]
        xyz = params[self.camera_end:self.point_end].reshape(-1, 3)
        camera = Camera(float(np.exp(params[self.point_end])), self.state.camera.cx,
                        self.state.camera.cy, float(params[-1]) if self.fit_k1 else self.state.camera.k1)
        return views, xyz, camera

    def quantities(self, params):
        views, xyz, camera = self.unpack(params)
        rotation_and_derivatives = [cv2.Rodrigues(view[:3]) for view in views]
        rotations = np.array([r for r, _ in rotation_and_derivatives])
        R = rotations[self.camera_obs]
        points = xyz[self.point_obs]
        transformed = np.einsum("nij,nj->ni", R, points) + views[self.camera_obs, 3:]
        projected, depth = camera.project_camera(transformed)
        error = projected - self.pixels
        return transformed, depth, error, R, points, camera, rotation_and_derivatives

    def residual(self, params):
        _, depth, error, *_ = self.quantities(params)
        depth_violation = self.depth_weight * np.minimum(depth - 1e-6, 0)
        return np.r_[np.column_stack((error, depth_violation)).ravel(),
                     (params[self.point_end:] - self.prior) / self.sigma]

    def jacobian(self, params):
        transformed, depth, _, R, points, camera, rotations = self.quantities(params)
        z = np.copysign(np.maximum(np.abs(depth), 1e-8), depth)
        xy = transformed[:, :2] / z[:, None]
        r2 = np.sum(xy ** 2, axis=1)
        radial = 1 + camera.k1 * r2
        # Chain rule: radial model -> perspective divide -> world/pose.
        radial_jac = camera.focal * (radial[:, None, None] * np.eye(2) +
                                     2 * camera.k1 * xy[:, :, None] * xy[:, None, :])
        perspective_jac = np.zeros((self.n, 2, 3))
        perspective_jac[:, :, :2] = np.eye(2) / z[:, None, None]
        perspective_jac[:, :, 2] = -xy / z[:, None] * (np.abs(depth) > 1e-8)[:, None]
        pixel_jac = np.zeros((self.n, 3, 3))
        pixel_jac[:, :2] = radial_jac @ perspective_jac
        pixel_jac[:, 2, 2] = self.depth_weight * (depth < 1e-6)
        rotation_jac = np.array([d.reshape(3, 3, 3) for _, d in rotations])[self.camera_obs]
        d_rotated_point = np.einsum("nkij,nj->nik", rotation_jac, points)
        intrinsic_jac = np.zeros((self.n, 3, 1 + self.fit_k1))
        intrinsic_jac[:, :2, 0] = camera.focal * xy * radial[:, None]
        if self.fit_k1:
            intrinsic_jac[:, :2, 1] = camera.focal * xy * r2[:, None]
        values = np.concatenate((pixel_jac @ d_rotated_point, pixel_jac,
                                 pixel_jac @ R, intrinsic_jac), axis=2)
        prior_rows = 3 * self.n + np.arange(len(self.sigma))
        prior_cols = self.point_end + np.arange(len(self.sigma))
        return coo_matrix(
            (np.r_[values[self.nonfixed], 1 / self.sigma],
             (np.r_[self.rows[self.nonfixed], prior_rows], np.r_[self.cols[self.nonfixed], prior_cols])),
            shape=(3 * self.n + len(self.sigma), len(params)),
        ).tocsr()


def solve_bundle(problem, budget):
    """Damped robust least squares with 3x3 point blocks eliminated by a Schur complement."""
    x = problem.x0.copy()
    residual = problem.residual(x)
    cost = huber_cost(residual)
    camera_cols = np.r_[0:problem.camera_end, problem.point_end:len(x)]
    point_cols = slice(problem.camera_end, problem.point_end)
    count = len(problem.point_ids)
    damping, optimality = 1e-3, np.inf
    status, message = 0, "Evaluation budget reached"
    accepted = 0
    linear_retries = 0
    for evaluation in range(1, budget + 1):
        J = problem.jacobian(x)
        weight = np.sqrt(2 / np.maximum(np.abs(residual), 2))
        Jw = J.multiply(weight[:, None]).tocsr()
        weighted_residual = residual * weight
        A, B = Jw[:, camera_cols], Jw[:, point_cols]
        g, h = A.T @ weighted_residual, B.T @ weighted_residual
        U = (A.T @ A).toarray()
        V = (B.T @ B).tobsr(blocksize=(3, 3))
        # A residual depends on a single point, so these blocks are diagonal.
        blocks = np.zeros((count, 3, 3))
        blocks[V.indices] = V.data
        cross = (A.T @ B).tocsr()
        u_diag = np.maximum(U.diagonal(), 1e-8)
        v_diag = np.maximum(blocks.diagonal(axis1=1, axis2=2), 1e-8)
        optimality = float(max(np.max(np.abs(g) / np.sqrt(u_diag)),
                               np.max(np.abs(h) / np.sqrt(v_diag.ravel()))))
        if optimality < 1e-5:
            status, message = 1, "Scaled gradient tolerance reached"
            break
        damped = blocks + (damping * v_diag)[:, None, :] * np.eye(3)
        inverse = bsr_matrix((np.linalg.inv(damped), np.arange(count), np.arange(count + 1)),
                             shape=(3 * count, 3 * count))
        product = cross @ inverse
        reduced = U + np.diag(damping * u_diag) - (product @ cross.T).toarray()
        scale = 1 / np.sqrt(u_diag)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", LinAlgWarning)
                delta_camera = scale * solve(
                    scale[:, None] * reduced * scale, scale * (-g + product @ h), assume_a="pos",
                )
        except (LinAlgWarning, np.linalg.LinAlgError):
            linear_retries += 1
            damping *= 10
            if damping > 1e8:
                status, message = -1, "Schur system remained ill-conditioned after damping"
                break
            continue
        delta_points = -inverse @ (h + cross.T @ delta_camera)
        trial = x.copy()
        trial[camera_cols] += delta_camera
        trial[point_cols] += delta_points
        trial = np.clip(trial, problem.lower, problem.upper)
        _, depth, pixels, _, _, camera, _ = problem.quantities(trial)
        penalty = problem.depth_weight * np.minimum(depth - 1e-6, 0)
        candidate = np.r_[np.column_stack((pixels, penalty)).ravel(),
                          (trial[problem.point_end:] - problem.prior) / problem.sigma]
        trial_cost = huber_cost(candidate)
        if (np.isfinite(trial_cost) and trial_cost < cost and
            np.all(depth > 1e-8) and camera.monotone_at_corners()):
            relative = (cost - trial_cost) / max(cost, 1.0)
            x, residual, cost = trial, candidate, trial_cost
            accepted += 1
            damping = max(damping / 3, 1e-10)
            if relative < 1e-8:
                status, message = 2, "Relative robust-cost tolerance reached"
                break
        else:
            damping *= 10
            if damping > 1e8:
                status, message = (2, "No further valid cost-reducing step") if accepted else (
                    -1, "Failed to find a valid cost-reducing step"
                )
                break
    return SimpleNamespace(x=x, status=status, success=status > 0, nfev=evaluation + 1,
                           accepted_steps=accepted, linear_retries=linear_retries,
                           optimality=optimality, message=message)


def bundle_adjust(state, initial_camera, config, phase, budget, fit_k1=False):
    start = perf_counter()
    diagnostic = {"phase": phase, "fit_k1": fit_k1, "accepted": False,
                  "observations": 0, "points": len(state.points),
                  "focal_before_px": state.camera.focal, "k1_before": state.camera.k1}
    if len(state.points) < 8:
        diagnostic["message"] = "Insufficient points for bundle adjustment"
    else:
        problem = BundleProblem(state, initial_camera, fit_k1, config)
        before = problem.residual(problem.x0)

        try:
            result = solve_bundle(problem, budget)
            after = problem.residual(result.x)
            rows = slice(0, 3 * problem.n)
            before_norm = np.linalg.norm(before[rows].reshape(-1, 3)[:, :2], axis=1)
            after_norm = np.linalg.norm(after[rows].reshape(-1, 3)[:, :2], axis=1)
            views, points, camera = problem.unpack(result.x)
            _, depth, _, *_ = problem.quantities(result.x)
            finite_after = np.isfinite(after).all()
            diagnostic.update(
                observations=problem.n, before_px=distribution(before_norm),
                cost_before=huber_cost(before),
                candidate_after_px=distribution(after_norm) if finite_after else None,
                candidate_cost_after=huber_cost(after) if finite_after else None,
                candidate_focal_px=camera.focal, candidate_k1=camera.k1,
                nonpositive_depth=int(np.sum(depth <= 1e-8)),
                converged=bool(result.success), solver_status=int(result.status),
                evaluations=int(result.nfev), message=str(result.message),
                accepted_steps=result.accepted_steps, linear_solve_retries=result.linear_retries,
                solver="damped Schur complement",
                optimality=float(result.optimality) if np.isfinite(result.optimality) else None,
            )
            if (result.status >= 0 and (result.accepted_steps or result.success) and
                finite_after and np.isfinite(result.x).all() and
                huber_cost(after) <= huber_cost(before) + 1e-8 and np.all(depth > 1e-8) and
                camera.monotone_at_corners()):
                state.camera = camera
                state.poses.update({
                    i: Pose(Rotation.from_rotvec(v[:3]).as_matrix(), v[3:])
                    for i, v in zip(problem.views, views, strict=True)
                })
                state.points.update({
                    i: Point(xyz, state.points[i].active)
                    for i, xyz in zip(problem.point_ids, points, strict=True)
                })
                diagnostic["accepted"] = True
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as error:
            diagnostic["message"] = str(error)
    diagnostic.update(seconds=perf_counter() - start, focal_after_px=state.camera.focal,
                      k1_after=state.camera.k1)
    state.ba.append(diagnostic)
    return diagnostic["accepted"]
