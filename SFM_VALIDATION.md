# Manual Projective SfM

## Implementation

The pipeline takes complete manually annotated landmark tracks in pixels. It normalizes each view's coordinates, estimates the seed fundamental matrix with the normalized eight-point algorithm, enforces rank two, and constructs the canonical projective camera pair from the fundamental matrix and epipole. It triangulates the seed tracks by SVD, normalizes the resulting 3D points in a finite projective chart, and fits each remaining camera by normalized DLT.

By default, the solver selects the seed pair with the lowest initial reprojection RMSE over all views. `--seed` lets an experiment fix the pair. Bundle adjustment uses Levenberg–Marquardt to minimize the sum of squared pixel residuals. It fixes five landmarks that form a projective frame and fixes one scale entry per camera and per movable landmark. NumPy supplies the matrix operations and SciPy supplies the least-squares optimizer. The code implements the SfM stages directly. [Hartley's normalized eight-point algorithm](https://users.cecs.anu.edu.au/~hartley/Papers/fundamental/fundamental.pdf) · [SciPy least-squares documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)

## Synthetic validation

Run `python -m unittest discover -s tests` after installing `requirements.txt`. The test scene contains eight spatially dispersed landmarks viewed by 25 synthetic cameras. The noisy case adds independent zero-mean Gaussian noise with a 0.6 px standard deviation to each image coordinate. Reprojection RMSE is the square root of the mean squared 2D pixel distance between observed and projected points.

| Case | Initial RMSE (px) | Refined RMSE (px) |
| --- | ---: | ---: |
| 25 views, automatic seed selection | 0.7664 | 0.4911 |
| 25 views, first and last cameras as seeds | 2.0292 | 0.4911 |

In this scene, selecting the seed pair across all views reduced initialization error. Both starts converged to nearly identical residuals. The noiseless two-view test recovered all eight landmarks within a coordinate tolerance of $10^{-8}$ after alignment by a 3D projectivity. An identical-view pair was rejected because its correspondence equations lost rank.

The repository has a Double Helix video and currently has no manually annotated tracks. The measurements above come from synthetic data. Once the manual tracks are available, `metrics.json` provides per-view errors for checking which views fit poorly, and `point_cloud.ply` provides the projective reconstruction for qualitative inspection. Distances and angles depend on the chosen projective coordinates.

## Generative AI disclosure

OpenAI Codex assisted with the Python SfM implementation, command-line interface and documentation, and the design and execution of the synthetic validation.
