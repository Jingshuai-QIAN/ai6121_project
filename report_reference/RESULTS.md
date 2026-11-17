# AI6121 SfM 报告素材

[盒子](results/boxes/) · [双螺旋](results/helix/) · [COLMAP 对照](results/colmap_comparison/)

## 可以引用的数据

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
