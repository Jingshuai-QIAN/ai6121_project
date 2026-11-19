# Unit Test Evidence — Python 3.11

**Result: PASS (6/6 tests)**

This record documents a clean execution of the repository's automated unit tests.

## Test environment

| Item | Value |
|---|---|
| Test time | 2026-11-19 22:05:27 +08:00 (Asia/Shanghai) |
| Project | `C:\Users\zhangjiayang\Desktop\ai6121_project-main` |
| Python | 3.11.18 |
| NumPy | 2.4.6 |
| SciPy | 1.17.1 |
| OpenCV | 5.1.0 |
| Matplotlib | 3.11.2 |
| PyAV | 18.1.0 |
| `requirements.txt` SHA-256 | `128e5ad5e498cd220c71730795e13b81596e92bacbfa5717737b1730b1567376` |

## Command

```powershell
python -m unittest discover -s tests -v
```

## Test results

| Test | Result |
|---|---|
| Eight-point minimal solver and triangulation | PASS |
| Incremental reconstruction with partial tracks and a disconnected view | PASS |
| Empty matching and track-conflict handling | PASS |
| Projection and Jacobian with distortion | PASS |
| RANSAC outliers and pure-rotation handling | PASS |
| Self-calibration with distortion | PASS |

## Raw output

```text
test_eight_point_minimal_and_triangulation (test_sfm.GeometryTests.test_eight_point_minimal_and_triangulation) ... ok
test_incremental_partial_tracks_and_disconnected_view (test_sfm.GeometryTests.test_incremental_partial_tracks_and_disconnected_view) ... ok
test_match_empty_and_track_conflict (test_sfm.GeometryTests.test_match_empty_and_track_conflict) ... ok
test_projection_and_jacobian_with_distortion (test_sfm.GeometryTests.test_projection_and_jacobian_with_distortion) ... ok
test_ransac_outliers_and_pure_rotation (test_sfm.GeometryTests.test_ransac_outliers_and_pure_rotation) ... ok
test_self_calibration_with_distortion (test_sfm.GeometryTests.test_self_calibration_with_distortion) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.586s

OK
```
