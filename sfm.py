"""Uncalibrated projective SfM from complete, manually matched landmark tracks."""

from dataclasses import dataclass
from itertools import chain, combinations

import numpy as np
from scipy.linalg import qr
from scipy.optimize import least_squares


@dataclass
class Reconstruction:
    seed: tuple[int, int]
    frame: tuple[int, ...]
    cameras: np.ndarray  # (views, 3, 4), in pixel coordinates
    points: np.ndarray  # (landmarks, 4), homogeneous with w = 1
    initial_projections: np.ndarray
    projections: np.ndarray
    converged: bool
    optimizer_message: str
    evaluations: int


def _normalize(points):
    """Center points and set the mean distance from the origin to sqrt(d)."""
    dimension = points.shape[1]
    center = points.mean(axis=0)
    centered = points - center
    distance = np.linalg.norm(centered, axis=1).mean()
    if distance == 0 or not np.isfinite(distance):
        raise ValueError("Point coordinates have no usable spatial spread.")
    scale = np.sqrt(dimension) / distance
    transform = np.eye(dimension + 1)
    transform[:dimension, :dimension] *= scale
    transform[:dimension, dimension] = -scale * center
    normalized = np.column_stack((scale * centered, np.ones(len(points))))
    return normalized, transform


def _null_vector(system, required_rank, problem):
    # For the minimal 8 x 9 system, reduced SVD omits the null vector.
    wide = system.shape[0] < system.shape[1]
    _, singular, vh = np.linalg.svd(system, full_matrices=wide)
    tolerance = singular[0] * max(system.shape) * np.finfo(float).eps
    if singular[required_rank - 1] <= tolerance:
        raise ValueError(f"Degenerate {problem}: correspondence equations lose rank.")
    return vh[-1]


def _fundamental(first, second):
    """Normalized eight-point solve in the supplied normalized image coordinates."""
    system = np.einsum("ni,nj->nij", second, first).reshape(-1, 9)
    linear = _null_vector(system, 8, "seed pair").reshape(3, 3)
    u, singular, vh = np.linalg.svd(linear)
    singular[-1] = 0
    return (u * singular) @ vh, u[:, -1]


def _skew(vector):
    x, y, z = vector
    return np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])


def _triangulate(cameras, observations):
    points = []
    for track in observations.transpose(1, 0, 2):
        rows = cameras[:, :2] - track[:, :2, None] * cameras[:, 2:3]
        points.append(_null_vector(rows.reshape(-1, 4), 3, "triangulation"))
    return np.array(points)


def _finite_chart(points):
    """Pick a projective chart with finite coordinates for every landmark."""
    directions = points / np.linalg.norm(points, axis=1, keepdims=True)
    if np.min(np.abs(directions[:, -1])) > 1e-8:
        return np.eye(4)

    normals = np.random.default_rng(0).normal(size=(128, 4))
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    margins = np.min(np.abs(directions @ normals.T), axis=0)
    best = np.argmax(margins)
    if margins[best] <= 1e-8:
        raise ValueError("Could not choose a finite projective chart for the landmarks.")
    # Put the chosen normal in the fourth row while keeping an orthogonal basis.
    _, _, basis = np.linalg.svd(normals[best, None])
    return basis[[1, 2, 3, 0]]


def _camera_dlt(points, observations):
    """Fit a camera from normalized 3D points and normalized image observations."""
    system = np.zeros((len(points), 2, 3, 4))
    system[:, 0, 0] = points
    system[:, 1, 1] = points
    system[:, :, 2] = -observations[:, :2, None] * points[:, None, :]
    camera = _null_vector(system.reshape(-1, 12), 11, "camera DLT").reshape(3, 4)
    if np.linalg.matrix_rank(camera) < 3:
        raise ValueError("Camera DLT returned a projection matrix of rank below three.")
    return camera


def _frame_indices(points):
    """Choose five points of which every four form a basis of projective 3D."""
    directions = points / np.linalg.norm(points, axis=1, keepdims=True)
    if np.linalg.matrix_rank(directions) < 4:
        raise ValueError("The landmarks do not span projective 3D.")

    _, _, pivots = qr(directions.T, pivoting=True, mode="economic")
    first_basis = tuple(sorted(pivots[:4]))
    for basis in chain([first_basis], combinations(range(len(points)), 4)):
        matrix = directions[list(basis)].T
        if np.linalg.cond(matrix) >= 1e8:
            continue
        weights = np.linalg.solve(matrix, directions.T)
        margins = np.min(np.abs(weights), axis=0)
        margins[list(basis)] = 0
        fifth = int(np.argmax(margins))
        if margins[fifth] > 1e-8:
            return tuple(sorted((*basis, fifth)))
    raise ValueError("The landmarks do not contain a usable five-point projective frame.")


def _project(cameras, points, optimizer=False):
    projected = cameras @ points.T
    depth = projected[:, 2:3]
    # Use a scale-relative threshold for near-zero homogeneous denominators.
    minimum_depth = 1e-12 * np.max(np.abs(projected), axis=1, keepdims=True)
    if optimizer:
        minimum_depth = np.maximum(minimum_depth, np.finfo(float).tiny)
        depth = np.where(np.abs(depth) < minimum_depth, np.copysign(minimum_depth, depth), depth)
    elif np.any(np.abs(depth) <= minimum_depth):
        raise ValueError("A landmark projects at infinity in at least one view.")
    return (projected[:, :2] / depth).transpose(0, 2, 1)


def _initialize(observations, seed):
    first, second = seed
    fundamental, epipole = _fundamental(observations[first], observations[second])
    cameras = np.empty((len(observations), 3, 4))
    cameras[first] = np.eye(3, 4)
    cameras[second] = np.column_stack((-_skew(epipole) @ fundamental, epipole))
    points = _triangulate(cameras[list(seed)], observations[list(seed)])

    # Transform the 3D points and both seed cameras into the same normalized chart.
    chart = _finite_chart(points)
    finite = points @ chart.T
    points, transform = _normalize(finite[:, :3] / finite[:, 3:])
    cameras[list(seed)] = cameras[list(seed)] @ np.linalg.inv(transform @ chart)

    for index, view in enumerate(observations):
        if index not in seed:
            cameras[index] = _camera_dlt(points, view)
    return cameras, points


def _fix_scale(vectors):
    """Set each vector's largest-magnitude entry to one and mark its free entries."""
    rows = np.arange(len(vectors))
    pivots = np.argmax(np.abs(vectors), axis=1)
    free = np.ones(vectors.shape, dtype=bool)
    free[rows, pivots] = False
    return vectors / vectors[rows, pivots, None], free


def _bundle_adjust(cameras, points, observations, scales, frame, max_nfev):
    camera_values, free_cameras = _fix_scale(cameras.reshape(-1, 12))
    point_values = points.copy()
    moving = np.ones(len(points), dtype=bool)
    moving[list(frame)] = False
    free_points = np.zeros(points.shape, dtype=bool)
    point_values[moving], free_points[moving] = _fix_scale(points[moving])
    camera_count = np.count_nonzero(free_cameras)

    def unpack(parameters):
        camera_values[free_cameras] = parameters[:camera_count]
        point_values[free_points] = parameters[camera_count:]
        return camera_values.reshape(-1, 3, 4), point_values

    def residuals(parameters):
        current_cameras, current_points = unpack(parameters)
        residual = _project(current_cameras, current_points, optimizer=True) - observations[..., :2]
        return (residual / scales[:, None, None]).ravel()

    initial = np.concatenate((camera_values[free_cameras], point_values[free_points]))
    solution = least_squares(
        residuals, initial, method="lm", x_scale="jac", max_nfev=max_nfev
    )
    refined_cameras, refined_points = unpack(solution.x)
    if any(np.linalg.matrix_rank(camera) < 3 for camera in refined_cameras):
        raise ValueError("Bundle adjustment produced a rank-deficient camera.")
    return refined_cameras, refined_points, solution


def reconstruct(observations, seed=None, max_nfev=2000):
    """Solve for cameras and landmarks from a (views, landmarks, 2) pixel array.

    Each landmark must appear in every view. If omitted, the seed pair is
    selected by all-view initialization reprojection error before refinement.
    """
    observations = np.asarray(observations, dtype=float)
    if observations.ndim != 3 or observations.shape[2] != 2:
        raise ValueError("Expected pixel coordinates shaped (views, landmarks, 2).")
    views, landmarks, _ = observations.shape
    if views < 2 or landmarks < 8 or not np.isfinite(observations).all():
        raise ValueError("Provide at least two views and eight complete, finite landmark tracks.")
    if max_nfev < 1:
        raise ValueError("max_nfev must be positive.")
    if seed is not None and (len(seed) != 2 or len(set(seed)) != 2 or not all(
        isinstance(i, (int, np.integer)) and 0 <= i < views for i in seed
    )):
        raise ValueError("The seed must contain two distinct, valid view indices.")

    normalized, transforms = map(np.array, zip(*map(_normalize, observations)))
    scales = transforms[:, 0, 0]
    pairs = combinations(range(views), 2) if seed is None else [tuple(seed)]
    best = None
    best_error = np.inf
    last_error = None
    for pair in pairs:
        try:
            cameras, points = _initialize(normalized, pair)
            initial = _project(np.linalg.solve(transforms, cameras), points)
            error = np.mean(np.sum((initial - observations) ** 2, axis=2))
            if error < best_error:
                frame = _frame_indices(points)
                best = cameras, points, initial, pair, frame
                best_error = error
        except (ValueError, np.linalg.LinAlgError) as exc:
            last_error = exc
    if best is None:
        detail = f" {last_error}" if last_error else ""
        raise ValueError(f"No usable seed reconstruction.{detail}") from last_error

    cameras, points, initial, pair, frame = best
    cameras, points, solution = _bundle_adjust(
        cameras, points, normalized, scales, frame, max_nfev
    )
    cameras = np.linalg.solve(transforms, cameras)
    chart = _finite_chart(points)
    cameras = cameras @ chart.T
    points = points @ chart.T
    points /= points[:, 3:]
    return Reconstruction(
        pair, frame, cameras, points, initial, _project(cameras, points),
        bool(solution.success), solution.message, solution.nfev,
    )
