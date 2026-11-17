"""Shared data and pixel/camera conventions."""

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Camera:
    focal: float
    cx: float
    cy: float
    k1: float = 0.0

    @property
    def K(self):
        return np.array([[self.focal, 0, self.cx], [0, self.focal, self.cy], [0, 0, 1]])

    @property
    def distortion(self):
        return np.array([self.k1, 0, 0, 0, 0])

    @property
    def principal(self):
        return np.array([self.cx, self.cy])

    def normalize(self, pixels):
        pixels = np.asarray(pixels, dtype=float).reshape(-1, 2)
        distorted = (pixels - self.principal) / self.focal
        if not len(pixels) or self.k1 == 0:
            return distorted
        # Invert r_d = r(1 + k1*r²) on the increasing, physical branch.
        distorted_radius = np.linalg.norm(distorted, axis=1)
        radius = distorted_radius.copy()
        for _ in range(15):
            radius -= (radius * (1 + self.k1 * radius ** 2) - distorted_radius) / (
                1 + 3 * self.k1 * radius ** 2
            )
        return distorted / (1 + self.k1 * radius[:, None] ** 2)

    def project_camera(self, xyz_camera):
        depth = xyz_camera[..., 2]
        # Keep trial residuals finite near the camera plane.
        safe_depth = np.copysign(np.maximum(np.abs(depth), 1e-8), depth)
        xy = xyz_camera[..., :2] / safe_depth[..., None]
        radius2 = np.sum(xy ** 2, axis=-1, keepdims=True)
        return self.focal * xy * (1 + self.k1 * radius2) + self.principal, depth

    def monotone_at_corners(self):
        radius = np.hypot(self.cx, self.cy) / self.focal
        return self.k1 >= 0 or radius < 0.98 * (2 / 3) / np.sqrt(-3 * self.k1)


@dataclass(frozen=True)
class Pose:
    R: np.ndarray
    t: np.ndarray

    @property
    def center(self):
        return -self.R.T @ self.t

    @property
    def matrix(self):
        return np.column_stack((self.R, self.t))

    def transform(self, xyz):
        return xyz @ self.R.T + self.t


@dataclass
class Frame:
    id: int
    record: dict
    image: np.ndarray
    xy: np.ndarray = field(default_factory=lambda: np.empty((0, 2), dtype=float))
    descriptors: np.ndarray | None = None
    rgb: np.ndarray = field(default_factory=lambda: np.empty((0, 3), dtype=np.uint8))


@dataclass
class Pair:
    i: int
    j: int
    indices: np.ndarray
    distances: np.ndarray
    counts: dict
    inliers: np.ndarray
    errors: np.ndarray
    F: np.ndarray | None = None


@dataclass
class Point:
    xyz: np.ndarray
    active: tuple[int, ...]


@dataclass
class Reconstruction:
    frames: list[Frame]
    tracks: list[dict[int, int]]
    camera: Camera
    seed: tuple[int, int]
    poses: dict[int, Pose]
    points: dict[int, Point] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    ba: list[dict] = field(default_factory=list)
    status: str = "running"
