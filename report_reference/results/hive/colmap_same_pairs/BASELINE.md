# UOB Innovation Hub COLMAP baseline

This is an **external baseline** produced with PyCOLMAP 4.2.1. It is not part of the submitted native SfM implementation.

## Controlled input

- The same 49 PNG working images as the locked native experiment.
- The same 150 scheduled image pairs from `the_hive_test2/pairs.json`.
- One shared `SIMPLE_PINHOLE` camera.
- Initial focal length 832 px and principal point (360, 640) in the 720 × 1280 working images.
- CPU-only SIFT extraction, matching, mapping, and bundle adjustment.
- Random seed 6121; four CPU threads.

## Command

```powershell
python experiments/colmap_sparse.py `
  report_reference/results/hive/the_hive_test2 `
  outputs/hive_colmap_same_pairs `
  --same-pairs --focal 832 --threads 4
```

## Baseline result

| Metric | COLMAP |
|---|---:|
| Registered views | **49/49** |
| Sparse points | **36,948** |
| Active observations after common de-duplication | 112,145 |
| Reprojection RMSE under the common evaluator | 0.858 px |
| Estimated shared focal length | 638.13 px |
| Facade-supported points, at least two annotated views | **3,775** |
| Facade-supported points, at least three annotated views | **789** |

The run took 128.77 seconds: 17.24 seconds for feature extraction, 79.12 seconds for matching and geometric verification, and 29.97 seconds for incremental mapping. Timing is machine-dependent.

## Native comparison

| Metric | Native | COLMAP |
|---|---:|---:|
| Registered views | 49/49 | 49/49 |
| Sparse points | 13,579 | 36,948 |
| Reprojection RMSE | **0.655 px** | 0.858 px |
| Facade support, at least two annotated views | 911 | **3,775** |
| Facade support, at least three annotated views | 166 | **789** |

COLMAP recovered 2.72 times as many scene points, 4.14 times as many two-view facade-supported points, and 4.75 times as many three-view facade-supported points. The native pipeline produced the lower reprojection RMSE under the shared evaluator. These values should be interpreted as an external performance comparison, not as evidence that COLMAP code was used by the native method.

## Preserved evidence

- [Same-view aligned comparison](../colmap_comparison/aligned_comparison.png)
- [Full comparison metrics](../colmap_comparison/comparison.json)
- [Run configuration](configuration.json)
- [Run summary and timing](run_summary.json)
- [Shared camera poses](cameras_work_px.json)
- [Exact pair list](pair_list.txt)
- [COLMAP sparse point cloud](pointcloud.ply)
- [Facade annotations](../../../../data/evaluation/hive_facade_regions.json)

The 86 MB feature database and full COLMAP text model remain reproducible outputs and are intentionally excluded from the report bundle. The compact configuration, pair list, camera record, point cloud, comparison metrics, and figures are retained here.
