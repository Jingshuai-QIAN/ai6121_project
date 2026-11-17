import unittest

import numpy as np

from sfm import reconstruct


def synthetic_scene():
    rng = np.random.default_rng(6121)
    points = np.column_stack((rng.uniform(-1.2, 1.2, size=(8, 3)), np.ones(8)))
    intrinsics = np.array([[1400, 0, 960], [0, 1400, 540], [0, 0, 1]])
    cameras = []
    for angle in np.linspace(-0.9, 0.9, 25):
        cosine, sine = np.cos(angle), np.sin(angle)
        rotation = np.array([[cosine, 0, sine], [0, 1, 0], [-sine, 0, cosine]])
        cameras.append(intrinsics @ np.column_stack((rotation, [0, 0, 5])))
    projected = np.array(cameras) @ points.T
    exact = (projected[:, :2] / projected[:, 2:3]).transpose(0, 2, 1)
    noisy = exact + rng.normal(0, 0.6, exact.shape)
    return points, exact, noisy


def frame_matrix(points):
    basis = points[:4].T
    return basis * np.linalg.solve(basis, points[4])


def rmse(projections, observations):
    return np.sqrt(np.mean(np.sum((projections - observations) ** 2, axis=2)))


class ProjectiveSfMTests(unittest.TestCase):
    def test_minimal_seed_recovers_landmarks_up_to_projectivity(self):
        truth, exact, _ = synthetic_scene()
        observations = exact[[0, -1]]
        result = reconstruct(observations, seed=(0, 1))
        self.assertLess(rmse(result.projections, observations), 1e-8)

        frame = list(result.frame)
        canonical = np.linalg.solve(frame_matrix(result.points[frame]), result.points.T)
        aligned = frame_matrix(truth[frame]) @ canonical
        np.testing.assert_allclose((aligned / aligned[3]).T, truth, atol=1e-8, rtol=0)

    def test_bundle_adjustment_improves_noisy_25_view_initialization(self):
        _, _, observations = synthetic_scene()
        result = reconstruct(observations)
        self.assertTrue(result.converged)
        self.assertEqual(result.cameras.shape, (25, 3, 4))
        self.assertLess(rmse(result.projections, observations), 0.6)
        self.assertLess(
            rmse(result.projections, observations), rmse(result.initial_projections, observations)
        )

    def test_identical_views_cannot_initialize_a_seed(self):
        _, exact, _ = synthetic_scene()
        with self.assertRaisesRegex(ValueError, "Degenerate seed pair"):
            reconstruct(exact[[0, 0]])
