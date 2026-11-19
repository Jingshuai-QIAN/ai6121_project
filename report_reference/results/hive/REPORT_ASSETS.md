# UOB Innovation Hub report assets

This page is the hand-off index for the final report. UOB Innovation Hub is the only main scene; Boxes and Double Helix are retained elsewhere as historical experiments.

## Main claim

**中文：** 本项目从一段约 35.76 秒的单目步行视频中，重建了 UOB Innovation Hub 临街一侧的稀疏三维结构。全部 49 张工作图均成功注册，所得 13,579 个场景点中，有 911 个点在至少两张人工标注图中得到建筑立面支持，其中 166 个点得到至少三张标注图支持。

**English:** We reconstructed the sparse 3D structure of the street-facing side of UOB Innovation Hub from a single approximately 35.76-second monocular walking video. All 49 working images were registered. Of the 13,579 reconstructed scene points, 911 were supported by conservative facade regions in at least two annotated views, including 166 supported in at least three annotated views.

## Result table

| Metric | Value |
|---|---:|
| Source video | 35.76 s, 1,074 frames |
| Working images | 49 at 720 × 1280 |
| Registered views | **49/49** |
| Sparse scene points | **13,579** |
| Points with at least five active views | **1,412** |
| Active observations | 38,223 |
| Final reprojection RMSE | **0.655 px** |
| Shared focal length | 832 px initial → 647.53 px estimated |
| Annotated representative frames | 9 |
| Facade-supported points, at least two views | **911** |
| Facade-supported points, at least three views | **166** |

## External COLMAP baseline

The external baseline used the same 49 PNGs, the same 150 scheduled image pairs, one shared `SIMPLE_PINHOLE` camera, and the same 832 px focal-length initialization. PyCOLMAP 4.2.1 was run on CPU and is disclosed as an external baseline rather than part of the native implementation.

| Metric | Native | COLMAP |
|---|---:|---:|
| Registered views | 49/49 | 49/49 |
| Sparse points | 13,579 | 36,948 |
| Reprojection RMSE | **0.655 px** | 0.858 px |
| Facade support, at least two annotated views | 911 | **3,775** |
| Facade support, at least three annotated views | 166 | **789** |

## Recommended figures and captions

### Figure 1 — Input coverage

[Open contact sheet](the_hive_test2/figures/contact_sheet.jpg)

**中文图注：** 从约 35.76 秒临街视频中均匀抽取的 49 张工作图。连续视角覆盖 UOB Innovation Hub 正面的多个圆筒楼体。

**English caption:** Forty-nine working images sampled uniformly from the approximately 35.76-second street-facing video. The sequential views cover multiple cylindrical blocks on the facade of UOB Innovation Hub.

### Figure 2 — Seed matching

[Open seed matches](the_hive_test2/figures/matches_seed_04_05.jpg)

**中文图注：** 工作帧 4 和 5（源帧 89 和 112）之间用于初始化的几何验证匹配。

**English caption:** Geometrically verified correspondences between working frames 4 and 5 (source frames 89 and 112), used to initialize the incremental reconstruction.

### Figure 3 — Reprojection check

[Open frame-24 reprojection](the_hive_test2/figures/reprojection_024.jpg)

**中文图注：** 工作帧 24（源帧 536）的原始特征观测与最终 BA 投影。全局最终重投影 RMSE 为 0.655 px。

**English caption:** Original feature observations and final bundle-adjusted projections in working frame 24 (source frame 536). The final global reprojection RMSE is 0.655 pixels.

### Figure 4 — Sparse scene and cameras

[Open scene and cameras](the_hive_test2/figures/scene_and_cameras.png)

**中文图注：** 13,579 个彩色稀疏场景点和 49 个已注册相机。点云与相机轨迹均为任意尺度。

**English caption:** The complete sparse reconstruction with 13,579 colored scene points and 49 registered cameras. The reconstruction and camera trajectory are expressed at an arbitrary scale.

### Figure 5 — Multi-view facade audit

[Open facade support overlay](the_hive_test2/facade_audit/facade_support.jpg)

**中文图注：** 前、中、后段 9 张代表帧中的保守圆筒立面标注（绿色）和至少在两张标注图中得到确认的观测。道路、树木、车辆、支柱和黑色电梯井均被排除。

**English caption:** Conservative cylindrical-facade annotations (green) in nine representative early, middle, and late views, with observations confirmed in at least two annotated views. Roads, vegetation, vehicles, columns, and the dark elevator cores were excluded.

### Figure 6 — Facade-supported 3D points

[Open 2+ view close-up](the_hive_test2/facade_audit/facade_closeup.png) · [Open 3+ view close-up](the_hive_test2/facade_audit/facade_closeup_3plus.png)

**中文图注：** 左：911 个至少两视图支持的建筑立面点。右：其中更严格的 166 个至少三视图支持点。视图用于显示空间分布，尺度任意。

**English caption:** Left: 911 facade points supported in at least two annotated views. Right: the stricter subset of 166 points supported in at least three annotated views. Views show spatial distribution at an arbitrary scale.

### Figure 7 — Native and COLMAP comparison

[Open aligned comparison](colmap_comparison/aligned_comparison.png)

**中文图注：** 相同49张工作图、150个图对和832 px焦距初值下的自主实现（上排）与COLMAP外部基线（下排）。从左到右为完整场景、至少两张标注图支持的立面点和至少三张标注图支持的立面点。两套地图用全部49个同名相机做相似对齐，并采用相同显示窗口。

**English caption:** Native reconstruction (top) and the external COLMAP baseline (bottom) using the same 49 working images, 150 image pairs, and 832 px focal initialization. Columns show the full scene, facade points supported in at least two annotated views, and facade points supported in at least three annotated views. The maps were similarity-aligned using all 49 shared cameras and displayed with identical limits.

## Suggested results paragraph

**中文：** 主实验使用 `orbit49_balanced.json` 从 1,074 帧视频中均匀选取 49 张 720 × 1280 工作图。增量式 SfM 成功注册全部 49 个视图并恢复 13,579 个彩色稀疏点，其中 1,412 个点具有至少五个活动观测。共享焦距从 832 px 初值优化为 647.53 px，最终重投影 RMSE 为 0.655 px。为确认点云中的建筑主体而非道路或植被，我们在前、中、后段的 9 张代表帧中保守标注圆筒立面。事后审计要求同一三维点的实测位置和预测位置同时位于标注内区，最终得到 911 个至少两视图支持的立面点，其中 166 个得到至少三视图支持。

**English:** The main experiment used `orbit49_balanced.json` to sample 49 working images at 720 × 1280 from the 1,074-frame video. Incremental SfM registered all 49 views and recovered 13,579 colored sparse points, including 1,412 points with at least five active observations. The shared focal length was refined from an initial 832 pixels to 647.53 pixels, and the final reprojection RMSE was 0.655 pixels. To verify that the reconstruction supported the building rather than roads or vegetation, we conservatively annotated cylindrical facade regions in nine representative early, middle, and late frames. The post-hoc audit required both the measured and predicted positions of a 3D point to lie inside the annotated interior, yielding 911 facade points supported in at least two views, including 166 supported in at least three views.

**COLMAP comparison, 中文：** 在相同49张PNG、150个图对、共享针孔相机和832 px焦距初值下，COLMAP外部基线同样注册了全部49个视图，并得到36,948个场景点、3,775个两视图立面点和789个三视图立面点。相较之下，自主实现分别得到13,579、911和166个点，但共享评估器下的重投影RMSE更低（0.655 px 对 0.858 px）。

**COLMAP comparison, English:** With the same 49 PNGs, 150 image pairs, shared pinhole camera, and 832 px focal initialization, the external COLMAP baseline also registered all 49 views and recovered 36,948 scene points, 3,775 two-view facade points, and 789 three-view facade points. The native method recovered 13,579, 911, and 166 points respectively, while achieving the lower reprojection RMSE under the common evaluator (0.655 px versus 0.858 px).

## Reproduction

Main reconstruction:

```bash
python -m sfm reconstruct --video data/video/the_hive.mp4 \
  --config configs/orbit49_balanced.json \
  --output outputs/hive_repro
```

Facade audit on the locked result:

```bash
python -m sfm.facade_audit \
  report_reference/results/hive/the_hive_test2 \
  --regions data/evaluation/hive_facade_regions.json \
  --output report_reference/results/hive/the_hive_test2/facade_audit
```

## Interpretation and limitations

- The facade regions are evaluation-only labels; they do not influence matching, pose estimation, triangulation, or bundle adjustment.
- The result is a sparse, arbitrarily scaled reconstruction, not a dense textured building model.
- Street-facing motion provides limited baseline and does not cover the rear of the building.
- Trees, vehicles, lamp posts, and self-occlusion reduce usable facade coverage.
- The 911- and 166-point counts are conservative evidence tied to the nine annotated views; they are not the total number of building points in the scene.

## Source records

- [Main metrics](the_hive_test2/metrics.json)
- [Resolved configuration](the_hive_test2/config.resolved.json)
- [Input and frame manifest](the_hive_test2/inputs.json)
- [Provenance and source hashes](the_hive_test2/provenance.json)
- [Facade audit metrics](the_hive_test2/facade_audit/facade_audit.json)
- [Facade annotation JSON](../../../data/evaluation/hive_facade_regions.json)
- [Python 3.11 unit-test evidence](../../test_logs/unit_tests_python311.md)
- [COLMAP baseline record](colmap_same_pairs/BASELINE.md)
- [Native/COLMAP comparison metrics](colmap_comparison/comparison.json)
