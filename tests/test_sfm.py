"""Ground-truth geometry tests. Run with python -m unittest discover -s tests -v."""

import json
from pathlib import Path
import unittest

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from sfm.bundle import BundleProblem, bundle_adjust
from sfm.data import build_tracks, match_pair
from sfm.geometry import eight_point, fundamental_ransac, homogeneous, sampson_signed, verify_pair
from sfm.model import Camera, Frame, Pair, Point, Pose, Reconstruction
from sfm.reconstruction import reconstruct
from sfm.triangulation import triangulate_dlt


CONFIG = json.loads((Path(__file__).resolve().parents[1] / "configs/default.json").read_text())


def scene(distortion=0.0, noise=0.0, views=7, diverse=False):
    rng = np.random.default_rng(6121)
    camera = Camera(760.0, 479.5, 359.5, distortion)
    xyz = rng.uniform([-1.5, -1.0, 4.0], [1.5, 1.0, 9.0], (140, 3))
    poses = {}
    frames = []
    for i in range(views):
        R = Rotation.from_euler("y", 0.05 * i).as_matrix()
        z = 0.47 * np.sin(i * 0.9) if diverse else 0.11 * i
        C = np.array([0.36 * i, 0.06 * np.sin(i), z])
        pose = Pose(R, -R @ C)
        pixels, _ = camera.project_camera(pose.transform(xyz))
        frame = Frame(i, {}, np.zeros((720, 960, 3), dtype=np.uint8))
        frame.xy = pixels + rng.normal(0, noise, pixels.shape)
        poses[i] = pose
        frames.append(frame)
    return camera, xyz, poses, frames


def similarity_error(actual, target):
    a, b = actual - actual.mean(axis=0), target - target.mean(axis=0)
    u, s, v = np.linalg.svd(a.T @ b)
    correction = np.diag([1, 1, np.linalg.det(u @ v)])
    scale = float((s * np.diag(correction)).sum() / np.sum(a ** 2))
    rotation = u @ correction @ v
    return np.sqrt(np.mean(np.sum((scale * a @ rotation - b) ** 2, axis=1)))


class GeometryTests(unittest.TestCase):
    def test_eight_point_minimal_and_triangulation(self):
        camera, xyz, poses, images = scene(views=2)
        a, b = [frame.xy[:8] for frame in images]
        F = eight_point(a, b)
        self.assertLess(np.max(np.abs(sampson_signed(F, homogeneous(a), homogeneous(b)))), 1e-7)
        recovered = triangulate_dlt(
            np.array([p.matrix for p in poses.values()]),
            np.stack([camera.normalize(image.xy) for image in images], axis=1),
        )
        np.testing.assert_allclose(xyz, recovered, atol=1e-9)
        with self.assertRaises(ValueError):
            eight_point(np.repeat(a[:1], 8, axis=0), b)
        planar = xyz.copy()
        planar[:, 2] = 6.0
        with self.assertRaises(ValueError):
            eight_point(*(camera.project_camera(pose.transform(planar))[0] for pose in poses.values()))

    def test_ransac_outliers_and_pure_rotation(self):
        camera, xyz, _, frames = scene(noise=0.3, views=2)
        rng = np.random.default_rng(42)
        second = frames[1].xy.copy()
        second[:28] = rng.uniform([50, 50], [900, 650], (28, 2))
        _, mask, _, _, _ = fundamental_ransac(frames[0].xy, second, 1.5, 1500, rng)
        self.assertGreaterEqual(mask[28:].mean(), 0.90)
        self.assertGreaterEqual(mask[28:].sum() / mask.sum(), 0.95)
        rotating = Pose(Rotation.from_euler("y", 0.15).as_matrix(), np.zeros(3))
        F, *_ = fundamental_ransac(camera.project_camera(xyz)[0],
                                    camera.project_camera(rotating.transform(xyz))[0], 1.0, 100, rng)
        self.assertIsNone(F)

    def test_match_empty_and_track_conflict(self):
        _, _, _, frames = scene(views=2)
        pair = match_pair(*frames, 0.75)
        self.assertEqual(pair.indices.shape, (0, 2))
        pairs = [Pair(a, b, np.array([[p, q]]), np.array([8.0]), {}, np.array([True]),
                      np.array([err]))
                 for a, b, p, q, err in [(0, 1, 0, 0, 0.01), (1, 2, 0, 0, 0.02),
                                         (0, 2, 1, 0, 0.03)]]
        tracks, conflicts = build_tracks(pairs)
        self.assertEqual(tracks, [{0: 0, 1: 0, 2: 0}])
        self.assertEqual(conflicts, 1)

    def test_projection_and_jacobian_with_distortion(self):
        camera, xyz, poses, frames = scene(distortion=-0.14, views=3)
        camera_xyz = poses[2].transform(xyz)
        expected = cv2.projectPoints(camera_xyz, np.zeros(3), np.zeros(3),
                                     camera.K, camera.distortion)[0].reshape(-1, 2)
        actual, _ = camera.project_camera(camera_xyz)
        np.testing.assert_allclose(actual, expected, atol=1e-9)
        np.testing.assert_allclose(camera.normalize(actual), camera_xyz[:, :2] / camera_xyz[:, 2:],
                                   atol=1e-9)
        tracks = [{i: p for i in poses} for p in range(13)]
        points = {tid: Point(xyz[tid], (0, 1, 2)) for tid in range(len(tracks))}
        state = Reconstruction(frames, tracks, camera, (0, 1), poses, points)
        problem = BundleProblem(state, camera, True, CONFIG)
        rng = np.random.default_rng(13)
        direction = rng.normal(size=len(problem.x0))
        eps = 1e-6
        numeric = (problem.residual(problem.x0 + eps * direction) -
                   problem.residual(problem.x0 - eps * direction)) / (2 * eps)
        np.testing.assert_allclose(problem.jacobian(problem.x0) @ direction,
                                   numeric, atol=2e-6, rtol=1e-6)

    def test_self_calibration_with_distortion(self):
        target, xyz, poses, frames = scene(distortion=-0.10, noise=0.12, diverse=True)
        initial = Camera(895, target.cx, target.cy)
        tracks = [{i: p for i in poses} for p in range(len(xyz))]
        points = {tid: Point(xyz[tid].copy(), tuple(poses)) for tid in range(len(tracks))}
        state = Reconstruction(frames, tracks, initial, (0, 1), poses.copy(), points)
        self.assertTrue(bundle_adjust(state, initial, CONFIG, "focal", 100))
        self.assertTrue(bundle_adjust(state, initial, CONFIG, "radial", 150, fit_k1=True))
        self.assertLess(state.ba[-1]["candidate_after_px"]["rmse"], 0.22)
        self.assertLess(abs(state.camera.focal - target.focal), 30)
        self.assertLess(abs(state.camera.k1 - target.k1), 0.02)
        np.testing.assert_allclose(state.poses[0].matrix, poses[0].matrix)
        self.assertEqual(state.poses[1].t[0], poses[1].t[0])

    def test_incremental_partial_tracks_and_disconnected_view(self):
        truth, gt, poses, frames = scene(noise=0.22)
        rng = np.random.default_rng(881)
        visible = rng.random((len(frames), len(gt))) > 0.23
        pairs = []
        for i in range(len(frames) - 1):
            for j in range(i + 1, min(len(frames) - 1, i + 4)):
                good = np.flatnonzero(visible[i] & visible[j])
                ids = np.column_stack((good, good))
                ids[:8, 1] = rng.permutation(ids[8:16, 1])
                pair = Pair(i, j, ids, np.ones(len(ids)), {}, np.zeros(len(ids), dtype=bool),
                            np.full(len(ids), np.inf))
                verify_pair(pair, frames[i], frames[j], CONFIG, rng)
                pairs.append(pair)
        tracks, _ = build_tracks(pairs)
        initial = Camera(840, truth.cx, truth.cy)
        state = reconstruct(frames, pairs, tracks, initial, CONFIG)
        self.assertEqual(set(state.poses), set(range(6)))
        self.assertEqual(state.status, "partial")
        self.assertTrue(any(row["phase"] == "final_focal" and row["accepted"] for row in state.ba))
        self.assertGreater(len(state.points), 90)
        self.assertTrue(any(3 <= len(point.active) < 6 for point in state.points.values()))
        expected, recovered = zip(*[(gt[tracks[i][p.active[0]]], p.xyz)
                                     for i, p in state.points.items()], strict=True)
        self.assertLess(similarity_error(np.array(recovered), np.array(expected)), 0.12)
        expected_cameras = np.array([poses[i].center for i in state.poses])
        actual_cameras = np.array([p.center for p in state.poses.values()])
        self.assertLess(similarity_error(actual_cameras, expected_cameras), 0.05)


if __name__ == "__main__":
    unittest.main()
