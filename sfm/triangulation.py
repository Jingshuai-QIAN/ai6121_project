"""C: DLT, angular support and raw-pixel quality gates."""

from itertools import combinations

import numpy as np

from .model import Point


def triangulate_dlt(matrices, normalized):
    """Accept (..., views, 3, 4) matrices broadcast against (..., views, 2)."""
    rows = normalized[..., None] * matrices[..., 2:3, :] - matrices[..., :2, :]
    _, singular, vh = np.linalg.svd(rows.reshape(*rows.shape[:-3], -1, 4), full_matrices=False)
    homogeneous = vh[..., -1, :]
    valid = (np.abs(homogeneous[..., 3]) > 1e-10) & (singular[..., -2] > 1e-10)
    return homogeneous[..., :3] / np.where(valid, homogeneous[..., 3], np.nan)[..., None]


def unit(vectors):
    return vectors / np.maximum(np.linalg.norm(vectors, axis=-1, keepdims=True), 1e-15)


def angle_degrees(a, b):
    return np.rad2deg(np.arccos(np.clip(np.sum(a * b, axis=-1), -1, 1)))


def max_angle(xyz, centers):
    rays = unit(xyz - centers)
    return float(np.rad2deg(np.arccos(np.clip(np.min(rays @ rays.T), -1, 1))))


def error_and_depth(camera, pose, xyz, pixels):
    projected, depth = camera.project_camera(pose.transform(xyz))
    return np.linalg.norm(projected - pixels, axis=-1), depth


class Triangulator:
    """Snapshot of the cameras and inverse-distortion rays for one map update."""

    def __init__(self, state, config, gate):
        self.state = state
        self.gate = gate
        self.min_angle = config["min_angle"]
        self.normalized = {i: state.camera.normalize(state.frames[i].xy) for i in state.poses}
        self.matrices = {i: pose.matrix for i, pose in state.poses.items()}
        self.centers = {i: pose.center for i, pose in state.poses.items()}

    def observations(self, track):
        ids = np.array([i for i in track if i in self.matrices], dtype=int)
        matrices = np.array([self.matrices[i] for i in ids])
        xy = np.array([self.normalized[i][track[i]] for i in ids])
        pixels = np.array([self.state.frames[i].xy[track[i]] for i in ids])
        centers = np.array([self.centers[i] for i in ids])
        return ids, matrices, xy, pixels, centers

    def fit(self, track, existing=None, allow_new=True):
        ids, matrices, xy, pixels, centers = self.observations(track)
        if len(ids) < 2:
            return None

        def quality(points):
            xyz_camera = np.einsum("mij,nj->nmi", matrices[..., :3], points) + matrices[..., 3]
            projected, depth = self.state.camera.project_camera(xyz_camera)
            errors = np.linalg.norm(projected - pixels, axis=-1)
            good = np.isfinite(errors) & (depth > 1e-8) & (errors <= self.gate)
            return good, errors

        if existing is not None:
            good, _ = quality(existing.xyz[None])
            active = good[0]
            if active.sum() >= 2 and max_angle(existing.xyz, centers[active]) >= self.min_angle:
                return Point(existing.xyz, tuple(ids[active].tolist()))
            if not allow_new:
                return None

        rays = unit(np.einsum("nij,ni->nj", matrices[..., :3],
                             np.column_stack([xy, np.ones(len(ids))])))
        pairs = np.array(list(combinations(range(len(ids)), 2)))
        cosine = np.sum(rays[pairs[:, 0]] * rays[pairs[:, 1]], axis=-1)
        best_pairs = pairs[np.argsort(cosine)[:12]]
        candidates = triangulate_dlt(matrices[best_pairs], xy[best_pairs])
        good, errors = quality(candidates)
        ranks = np.lexsort((np.where(good, errors, 0).sum(axis=1), -good.sum(axis=1)))
        for index in ranks:
            active = good[index]
            if active.sum() < 2:
                break
            xyz = candidates[index]
            if max_angle(xyz, centers[active]) < self.min_angle:
                continue
            refined = triangulate_dlt(matrices[active], xy[active])
            new_good, new_errors = quality(refined[None])
            new_active = new_good[0]
            if new_active.sum() >= active.sum() and (
                new_active.sum() > active.sum() or
                new_errors[0][new_active].sum() <= errors[index][active].sum()
            ) and max_angle(refined, centers[new_active]) >= self.min_angle:
                xyz, active = refined, new_active
            return Point(xyz, tuple(ids[active].tolist()))
        return None
