# AI6121 SfM 报告素材

最终报告以 **UOB Innovation Hub** 为唯一主场景。Boxes 与 Double Helix 目录保留为历史实验材料，不纳入当前主结论。

[主实验目录](results/hive/the_hive_test2/) · [报告图与图注](results/hive/REPORT_ASSETS.md) · [主实验指标](results/hive/the_hive_test2/metrics.json) · [立面审计数据](results/hive/the_hive_test2/facade_audit/facade_audit.json)

## UOB Innovation Hub

主实验从 UOB Innovation Hub（原名 The Hive）的临街视频中均匀抽取 49 帧，注册了全部 49 个视图，恢复了 13,579 个彩色场景点。最终重投影 RMSE 为 0.655 px，共享焦距从 832 px 初值优化为 647.53 px。9 张前、中、后段代表帧的保守立面审计进一步确认了 911 个至少由两张标注图支持的建筑立面点，其中 166 个得到至少三张标注图支持。

[输入视频](../data/video/the_hive.mp4) · [全场景与相机](results/hive/the_hive_test2/figures/scene_and_cameras.png) · [主实验指标](results/hive/the_hive_test2/metrics.json) · [运行配置](results/hive/the_hive_test2/config.resolved.json) · [复现命令](../docs/SFM_PARAMETERS.md#复现-uob-innovation-hub-主实验)

### 主结果表

| 指标 | 结果 |
|---|---:|
| 视频长度 / 原始帧数 | 35.76 s / 1,074 |
| 工作图像 | 49 张，720 × 1280 |
| 注册视图 | **49/49** |
| 彩色稀疏场景点 | **13,579** |
| 至少五视图支持的场景点 | **1,412** |
| 活动观测 | 38,223 |
| 最终重投影 RMSE | **0.655 px** |
| 最终共享焦距 | 647.53 px |
| 至少两张标注图支持的立面点 | **911** |
| 至少三张标注图支持的立面点 | **166** |

立面区域只用于事后评估，不参与特征匹配、位姿估计、三角化或 BA。审计同时要求原始特征观测和最终模型的预测像素落在经腐蚀的立面内区，因此点数是圆筒楼体结构的保守多视图证据。

### 主报告素材

| 代表图 | 图注参考 |
|---|---|
| [49 帧接触表](results/hive/the_hive_test2/figures/contact_sheet.jpg) | 从约 35.76 秒临街视频中均匀抽取的 49 张工作图，展示相机沿建筑正面移动时的视角覆盖。 |
| [种子匹配](results/hive/the_hive_test2/figures/matches_seed_04_05.jpg) | 用于初始化的工作帧 4 和 5，对应原视频第 89 和 112 帧；通过几何验证的对应点为初始两视图重建提供约束。 |
| [第 24 帧重投影](results/hive/the_hive_test2/figures/reprojection_024.jpg) | 工作帧 24（源帧 536）的特征观测与 BA 后投影位置；最终全局重投影 RMSE 为 0.655 px。 |
| [全场景与相机轨迹](results/hive/the_hive_test2/figures/scene_and_cameras.png) | 13,579 个彩色稀疏点与 49 个已注册相机，展示临街拍摄覆盖及任意尺度下的相机轨迹。 |
| [立面审计叠图](results/hive/the_hive_test2/facade_audit/facade_support.jpg) | 9 张代表帧中的保守圆筒立面区域（绿色）以及得到至少两视图确认的观测。 |
| [两视图立面点云近景](results/hive/the_hive_test2/facade_audit/facade_closeup.png) | 911 个至少由两张标注图支持的建筑立面点，从两个三维视角展示。 |
| [三视图立面点云近景](results/hive/the_hive_test2/facade_audit/facade_closeup_3plus.png) | 更严格的 166 个至少由三张标注图支持的建筑立面点。 |

[完整点云](results/hive/the_hive_test2/pointcloud.ply) · [两视图立面点云](results/hive/the_hive_test2/facade_audit/facade_supported_2plus.ply) · [三视图立面点云](results/hive/the_hive_test2/facade_audit/facade_supported_3plus.ply) · [立面标注](../data/evaluation/hive_facade_regions.json)

### UOB Innovation Hub COLMAP 外部基线

COLMAP 基线复用主实验保存的同一组 49 张 PNG、相同的 150 个图对、单一共享 `SIMPLE_PINHOLE` 相机以及 832 px 焦距初值。PyCOLMAP 4.2.1 在 CPU 上运行，结果仅作为外部基线，不属于自主 SfM 实现。

| 指标 | 自主实现 | COLMAP 外部基线 |
|---|---:|---:|
| 注册视图 | 49/49 | 49/49 |
| 彩色稀疏点 | 13,579 | 36,948 |
| 活动观测 | 38,223 | 112,145 |
| 共享评估器重投影 RMSE | **0.655 px** | 0.858 px |
| 最终共享焦距 | 647.53 px | 638.13 px |
| 至少两张标注图支持的立面点 | 911 | **3,775** |
| 至少三张标注图支持的立面点 | 166 | **789** |

COLMAP 得到约 2.72 倍的场景点、4.14 倍的两视图立面点和 4.75 倍的三视图立面点；自主实现的共享评估重投影 RMSE 更低。两套地图使用全部 49 个同名相机做相似对齐，下图采用相同显示窗口。

[同视角对照图](results/hive/colmap_comparison/aligned_comparison.png) · [完整比较指标](results/hive/colmap_comparison/comparison.json) · [基线配置、命令与披露](results/hive/colmap_same_pairs/BASELINE.md) · [COLMAP 点云](results/hive/colmap_same_pairs/pointcloud.ply)

## 历史补充场景数据（不作为当前主结果）

| 自主主实验 | 注册视图 | 彩色稀疏点 | 重投影 RMSE（px） | ≥2 张标注图支持的物体点 |
|---|---:|---:|---:|---:|
| Boxes | 25/25 | 16,746 | 0.461 | 706 |
| NTU Double Helix | 49/49 | 12,609 | 0.430 | 399 |

区域审计验证实测与重投影位置在多张图中均落在物体标注内区。盒子用了 8 张标注图，雕塑用了 49 张。点数表示保守的物体归属证据，适合在同一场景和同一组标注内比较。点云使用任意尺度。

## Boxes

| 代表图 | 图注参考 |
|---|---|
| [盒身审计叠图](results/boxes/box_surface_overlays.jpg) | 八张审计图上的已确认观测。竖盒 633 个点，扁盒 73 个点。有印刷图案和标签的位置覆盖较多。 |
| [盒身三维近景](results/boxes/boxes_closeup.png) | 在至少两张标注图中得到盒身支持的 706 个自主重建点，从两个角度展示。 |

[完整点云](results/boxes/pointcloud.ply) · [盒身子集](results/boxes/boxes_supported.ply) · [相机姿态](results/boxes/cameras.json) · [指标](results/boxes/metrics.json) · [运行配置](results/boxes/config.resolved.json)

## Double Helix

| 代表图 | 图注参考 |
|---|---|
| [种子匹配](results/helix/matches_seed_19_20.jpg) | 用于初始化的工作帧 19 和 20，对应原视频第 394 和 415 帧。 |
| [重投影叠图](results/helix/reprojection_019.jpg) | 工作帧 19 的原始特征观测（青色圆圈）与 BA 后的投影（品红十字）。 |
| [金属带审计节选](results/helix/ribbon_support.jpg) | 四张代表帧中的金属带审计内区（绿色）与已确认观测（青色）。 |
| [金属带与相机](results/helix/ribbon_and_cameras.png) | 399 个金属带支持点与 49 个相机位置及朝向。金属带的若干局部可见，暗面和低纹理区域仍有缺口。 |
| [场景与相机](results/helix/scene_and_cameras.png) | 自主重建的完整稀疏场景，包含雕塑、背景及 49 个相机。 |

[完整点云](results/helix/pointcloud.ply) · [雕塑子集](results/helix/ribbon_supported.ply) · [相机姿态](results/helix/cameras.json) · [指标](results/helix/metrics.json) · [运行配置](results/helix/config.resolved.json)

## COLMAP 外部对照

对照图每组上排为自主主实验，下排为 COLMAP 稀疏穷举匹配基线。从左到右依次为场景与相机、物体支持子集、其中至少有三个有效视图的 tracks。两套地图用同名相机做相似对齐，使用同一显示窗口。图内显示了可见点数及对应总数。

| 代表图 | 可引用的观察 |
|---|---|
| [Boxes 同视角对照](results/colmap_comparison/boxes_aligned_comparison.png) | COLMAP 确认了 1,082 个盒身点，自主实现确认了 706 个。固定原图对范围后，COLMAP 仍确认 1,055 个。 |
| [Double Helix 同视角对照](results/colmap_comparison/helix_aligned_comparison.png) | COLMAP 有 35,133 个全场景点，其中 359 个有金属带支持。自主实现分别为 12,609 和 399。两套雕塑子集均有大面积缺口。 |

[Boxes 完整比较指标](results/colmap_comparison/boxes_comparison.json) · [Double Helix 完整比较指标](results/colmap_comparison/helix_comparison.json)

完整比较指标另含同配对范围复跑和自主改动。提高 SIFT 上限后，盒身支持点增至 739。扩窗加位姿引导后，金属带支持点增至 405。引用时可从 [实测与复现说明](../docs/SFM_RESULTS.md) 及 [COLMAP 诊断记录](../experiments/COLMAP_DIAGNOSIS.md) 查到各运行条件和成本。COLMAP 结果属于外部基线，表中的自主主实验可独立运行。
