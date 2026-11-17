# AI6121 · 相同工作帧下的稀疏重建对照

本记录比较自主实现与明确标记的 **外部诊断基线 PyCOLMAP 4.0.1**。工作帧直接来自既有结果，两个视频均未重新抽帧。结果是不同估计管线间的一致性证据。没有真值或实测尺度，区域审计只提供物体归属的保守证据。

## 实验设置

| 场景 | 工作帧 | 工作尺寸 | 主初值 f | 自主配对数 | 穷举配对数 |
|---|---:|---:|---:|---:|---:|
| Double Helix | 49 | 720 × 1280 | 832 px | 150 | 1,176 |
| Boxes | 25 | 1280 × 720 | 1,152 px | 99 | 300 |

每个 COLMAP 运行直接读取参考结果的 `frames/`。使用清单核对帧名、源帧号、大小和 SHA-256，并在匹配后再计算，统一评估时再核一次。SIFT 在 CPU 运行，保留原分辨率，使用包内默认 8,192 特征上限。所有图像共享一台 SIMPLE_PINHOLE 相机，零畸变，固定中心主点，优化焦距。初始焦距取参考运行的初始 K。OpenCV 像素中心坐标转换到 COLMAP 时主点各加 0.5 px，导出观测和相机参数各减 0.5 px。COLMAP 显式允许两视图点，关闭无结构注册回退。保留其增量三角化与几何验证设置，例如最终 4 px 误差门限、1.5° 最小三角化角。自主最终门限为 3 px 和 1°。因此穷举和同配对试验均为整条管线比较，两者的阈值、前端、优化方式和硬件线程数有区别。[COLMAP 相机模型](https://colmap.github.io/legacy/4.0/cameras.html) · [PyCOLMAP 4.0.1 接口](https://colmap.github.io/legacy/4.0/pycolmap/pycolmap.html) · [像素坐标约定](https://colmap.github.io/faq.html)

统一评估用 OpenCV `projectPoints` 重算工作像素误差。COLMAP 部分点在同一张图关联多个关键点。原始数据和原始误差完整保留，统一表按每点每图保留最小残差观测，tracks 按不同图像计数。另按同一个 3 px 正深度和 1° 规则核对支持点。两套地图用同名相机中心做定向相似配准。显示共享朝向、角度、坐标范围和同类点大小，另外保留不裁剪的图和完整 PLY。

沿用原标注与原预览变换 `round((u_work + .5) * preview_size / work_size - .5)`，以及两个预览像素的腐蚀内缩。每个物体支持点要求在至少两张标注图中，工作像素测量及其投影都落入同一物体类别的有效区域。雕塑有 49 张标注图，盒子有 8 张，两场景之间的审计点数不直接比较。表中的「物体点且 track ≥3」可以包含第三张未标注图，严格三张标注图也在 JSON 逐类统计。「32 px 格」是已支持观测在标注视图中占据的二维图格计数，提供区别于点数的覆盖代理。图格集中于有纹理部分时仍可能明显碎片化。

## 运行方法与数据

在仓库根目录执行。现有算法环境使用 Python 3.11.17，满足项目 `requirements.txt`。独立安装 CPU 基线的实跑命令如下。PyCOLMAP 未加入自主依赖或调用路径。

```bash
UV_CACHE_DIR=/tmp/ai6121-uv uv venv --python 3.11 /tmp/ai6121-colmap
UV_CACHE_DIR=/tmp/ai6121-uv uv pip install --python /tmp/ai6121-colmap/bin/python \
  'pycolmap==4.0.1' 'numpy==2.4.6'
export MPLCONFIGDIR=/tmp/ai6121-mpl OPENBLAS_NUM_THREADS=1
mkdir -p outputs/colmap_diagnosis
```

外部运行用 `/tmp/ai6121-colmap/bin/python -u experiments/colmap_sparse.py REFERENCE OUTPUT`。自主和评估用 `/tmp/ai6121-venv/bin/python`。重跑时使用新目录。下表中的路径均相对仓库根目录，具体命令、版本、配置、模型、阶段时间和输入哈希逐运行保存。

| 参考 | 外部运行子目录，位于 `outputs/colmap_diagnosis/` | 参数 |
|---|---|---|
| `outputs/double_helix_final` | `helix_pinhole` | 默认穷举 |
| `outputs/boxes_25` | `boxes_pinhole` | 默认穷举 |
| `outputs/double_helix_final` | `helix_same_pairs` | `--same-pairs` |
| `outputs/boxes_25` | `boxes_same_pairs` | `--same-pairs` |
| `outputs/double_helix_final` | `helix_same_pairs_init1152` | `--same-pairs --focal 1152` |
| `outputs/boxes_25` | `boxes_same_pairs_init832` | `--same-pairs --focal 832` |

运行标准输出与标准错误保存为实验根目录下的同名 `.log`。每个外部目录有 `database.db`、`configuration.json`、`run_summary.json`、所有模型原始文件、选定模型的文本、`cameras_work_px.json`、`observations_work_px.npz` 与 `pointcloud.ply`。

统一评估命令如下。`runs` 中首个模型是对齐参考，`--metrics-only` 可跳过绘图。Boxes 复用 `outputs/boxes_25/box_audit/surface_audit.json`。所有显示范围和窗口外点数在 `comparison.json` 的 `display`。独立区域标签不会进入重建。

```bash
python -m experiments.compare_sparse outputs/double_helix_final \
  data/evaluation/double_helix_ribbon_regions.json outputs/colmap_diagnosis/helix_eval_repro \
  Native=outputs/double_helix_final \
  COLMAP-exhaustive=outputs/colmap_diagnosis/helix_pinhole \
  COLMAP-same-pairs=outputs/colmap_diagnosis/helix_same_pairs
```

本次代码由 OpenAI Codex 辅助实现并运行对照与诊断。PyCOLMAP 仅为外部基线。课程项目的核心自实现继续单独评估。

## 基线结果

| 场景和管线 | 注册 | 场景点 | 两视图点 | 场景误差 RMSE / 中位 / P95，px | 最大视线夹角中位 | 物体支持点 | 物体点且 track ≥3 | f，工作 px |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Helix · 自主 | 49/49 | 12,609 | 70.6% | .430 / .226 / .890 | 8.04° | 399 | 145 | 619.24 |
| Helix · COLMAP 穷举 | 49/49 | 35,133 | 64.8% | .585 / .264 / 1.231 | 9.37° | 359 | 170 | 618.60 |
| Helix · COLMAP 同配对 | 49/49 | 34,003 | 66.1% | .545 / .246 / 1.127 | 9.30° | 341 | 160 | 617.78 |
| Boxes · 自主 | 25/25 | 16,746 | 54.2% | .461 / .255 / .937 | 9.50° | 706 | 546 | 1,187.35 |
| Boxes · COLMAP 穷举 | 25/25 | 22,900 | 39.1% | .664 / .393 / 1.328 | 12.29° | 1,082 | 1,019 | 1,186.52 |
| Boxes · COLMAP 同配对 | 25/25 | 23,565 | 46.8% | .572 / .312 / 1.147 | 10.41° | 1,055 | 904 | 1,187.56 |

Helix 的 COLMAP 稀疏图有 2.79 倍场景点。两套图的雕塑内区都只恢复到断续片段。COLMAP 的严格三标注视图支持为 147 点，自主为 117 点。已支持观测的二维覆盖格分别为 422 和 581，COLMAP 的额外场景点并未带来更多雕塑局部覆盖。统一裁剪和完整场景图分别见 [Helix 成对图](../outputs/colmap_diagnosis/helix_initial/aligned_comparison.png) 与 [未裁剪图](../outputs/colmap_diagnosis/helix_initial/aligned_unclipped.png)。

Boxes 的 COLMAP 穷举盒身支持 1,082 点，较原自主实现多 53%。立盒 977 对 633，扁盒 105 对 73。严格三张标注图支持为 312 对 42，立盒的印刷面与棱附近更连贯。扁盒素色大面在两套图里仍稀疏。改为同配对后仍有 1,055 个支持点。盒身上的差别不能用穷举配对单独解释，穷举对该场景主要额外改善了长轨迹。可见区域和未裁剪对照分别见 [Boxes 成对图](../outputs/colmap_diagnosis/boxes_initial/aligned_comparison.png) 与 [未裁剪图](../outputs/colmap_diagnosis/boxes_initial/aligned_unclipped.png)。

两场景的基线均无未注册图像或非正深度活动观测。COLMAP 穷举输出分别有 86 和 477 个同点同图重复观测。统一计算超过 3 px 的代表观测分别有 218 和 132 个。共同质量门限下 Helix 保留 35,081 个场景点、358 个物体支持点，Boxes 保留 22,893 个场景点、1,082 个物体支持点。自主原始结果在最终两次门控共移除 172 和 9 个场景点。完整 track 长度分布、正深度、误差分布、逐视图和图对验证记录留在各 JSON、DB 和日志中。

相对自主地图，COLMAP 穷举相似对齐后的相机中心中位差分别为轨迹 RMS 半径的 0.214% 和 0.145%，姿态中位差分别为 0.114° 和 0.104°。COLMAP 的同配对焦距复跑，Helix 从 832 / 1,152 px 收敛到 617.78 / 617.89 px，Boxes 从 1,152 / 832 px 收敛到 1,187.56 / 1,187.54 px，两组复跑的相机中心中位差分别为 0.0115% 和 0.0021%。已有自主对照在这两档初值也接近，Helix 的 1,536 px 高初值有收敛预算限制。当前针孔模型的跨工具一致性不支持把相机模型作为首要瓶颈，因此本轮保持 SIMPLE_PINHOLE。防抖、畸变和小幅模型偏差仍未有独立标定验证。详见 [Helix 初值对照](../outputs/colmap_diagnosis/helix_focal/comparison.json) 和 [Boxes 初值对照](../outputs/colmap_diagnosis/boxes_focal/comparison.json)。

## 瓶颈证据

| 区域及前端 | 内区检测到的关键点 | 原配对范围内同类物体两端均入区的原始匹配 | 该范围验证后匹配 |
|---|---:|---:|---:|
| Helix · 自主 | 9,583 | 1,003 | 808 |
| Helix · COLMAP 同配对 | 6,273 | 878 | 864 |
| Boxes 立盒 · 自主 | 4,114 | 648 | 616 |
| Boxes 立盒 · COLMAP 同配对 | 5,145 | 929 | 908 |
| Boxes 扁盒 · 自主 | 663 | 74 | 71 |
| Boxes 扁盒 · COLMAP 同配对 | 802 | 99 | 98 |

Boxes 差距在检测与原始匹配时已经出现。立盒中自主的 669 条、扁盒中 75 条候选轨迹已有两张标注图观测，最终分别有 633 和 73 个物体支持点，说明自身这个阶段的损失较小。COLMAP 的验证、补全和合并也会改变轨迹长度。仅凭这组整管线对照，无法把剩余差距分配到描述子匹配、track 完成和重三角化各自的贡献；需要共同对应关系的受控试验才能进一步分开。两组末端 BA 和注册都没有出现足以解释盒身差距的异常。

Helix 在已有配对内有较多关键点和原始双向对应，较大比例流失于独立图对几何验证。不同姿态间可重复纹理不足也是约束。按标注内中位灰度排序，最暗 12 个视图的中位值为 39.5，最亮 12 个为 98.5。自主在两组分别支持 110 和 202 个 32 px 视图格，COLMAP 分别为 21 和 201。视角、照明和可见面积同时变化，描述统计只说明这些暗面更少被支持，无法单独区分反光、曝光、运动模糊与缺少物理纹理。

## 自主改动、前后指标与结论

每次只改变一个控制项。特征实验保持框架、配对和几何设置。窗口实验保留旧图对的特征、匹配与内点掩码，仅给原窗外候选运行同一验证器。位姿引导实验相对扩窗结果只改变新增图对的验证，使用自主扩窗地图的相机姿态为已有双向匹配复核。沿用 1.5 px 极线门限，并检查双视图正深度、1° 视差与 3 px 原像素误差。之后仍由自主增量式地图从原初始焦距重建、优化和过滤。三次均使用相同工作 PNG 和独立的事后审计，配置和命令在各运行内保存。

| 自主实验 | 注册 | 场景点 | 审计物体点 | 物体且 track ≥3 | 严格 ≥3 标注图物体点 | 32 px 视图格 | 场景 RMSE，px | 时间，秒 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Boxes 原始 | 25/25 | 16,746 | 706 | 546 | 42 | 402 | .461 | 85.2 |
| Boxes 特征上限 4,500 → 8,192 | 25/25 | 23,138 | 739 | 566 | 36 | 416 | .457 | 164.7 |
| Helix 原始 | 49/49 | 12,609 | 399 | 145 | 117 | 581 | .430 | 135.7 |
| Helix 配对窗 3 → 6 | 49/49 | 12,620 | 401 | 145 | 117 | 584 | .441 | 132.3 + 原窗缓存 |
| Helix 扩窗及新增图对位姿复核 | 49/49 | 12,906 | 405 | 149 | 124 | 600 | .449 | 35.1 + 扩窗全流程 |

- **Boxes**：提高特征上限使立盒内区检测从 4,114 增至 4,787，双向匹配从 648 增至 691。两张标注图支持点增加 33 个，覆盖格增加 14 个，都只是小幅增加。扁盒支持点从 73 到 78，但覆盖格仍为 59，严格 ≥3 标注图支持点只有 1 个。整体严格三标注图证据下降，时间接近翻倍。它不能重现 COLMAP 的盒身结构改善，也不适合设为全局默认值。建议下一次代码实验固定特征与 3D 初值，单独比较描述子重匹配和 track 跨视图补全的贡献，优先看盒身视差、严格三视图与覆盖格。
- **Helix**：扩窗增加 132 个候选图对，仅 7 对独立验证通过。新增范围有 175 条双向匹配的两端均位于金属带内区，仅 6 条通过独立图对验证。用原自主地图的位姿复核，其中 155 条满足 1.5 px 极线约束。单独增加位姿复核后，全场景新增 1,392 条验证边，区域验证边由 814 增至 963。严格三标注图点增加 7 个，覆盖格从 581 增至 600。其代价是额外重建，且对齐图仍保留同样的大面积缺口。建议保留自主原版作为主结果，并优先补拍雕塑暗面和薄边交叠处。补拍时让这些区域占据更多像素，采用柔和光和较短曝光，在连续近邻视角之外加入低、高角度的环绕，减少帧间反光突变。若限制为现有视频，应把完整雕塑形状标记为稀疏覆盖不足。
- 这三次实验都完成最终 BA，注册分母一致。自主改动后与原图在相似对齐下的相机中心中位差小于轨迹 RMS 半径的 0.07%。这只说明地图内部变化小。两种场景都没有验证到明显的自主整体结构改善。COLMAP 在 Boxes 的可靠覆盖差距仍是下一轮代码工作的依据。

[Helix 全部对齐比较](../outputs/colmap_diagnosis/helix_with_guidance/aligned_comparison.png) · [Helix 未裁剪](../outputs/colmap_diagnosis/helix_with_guidance/aligned_unclipped.png) · [Helix 指标、覆盖格和裁剪记录](../outputs/colmap_diagnosis/helix_with_guidance/comparison.json)

[Boxes 全部对齐比较](../outputs/colmap_diagnosis/boxes_final_comparison/aligned_comparison.png) · [Boxes 未裁剪](../outputs/colmap_diagnosis/boxes_final_comparison/aligned_unclipped.png) · [Boxes 指标、覆盖格和裁剪记录](../outputs/colmap_diagnosis/boxes_final_comparison/comparison.json)

外部穷举运行分别用时 67.8 秒和 29.4 秒，COLMAP 用四个线程，自主用一个线程，时间用作复现和相对同管线成本分析。自主改动运行如下，`--match-only` 和 `--finish` 可把各自的一次运行分成匹配与重建两段。

```bash
python -m experiments.native_ablation outputs/boxes_25 \
  outputs/colmap_diagnosis/boxes_native_features8192 --features 8192 --match-only
python -m experiments.native_ablation outputs/boxes_25 \
  outputs/colmap_diagnosis/boxes_native_features8192 --features 8192 --finish

python -m experiments.native_ablation outputs/double_helix_final \
  outputs/colmap_diagnosis/helix_native_window6 --window 6 --match-only
python -m experiments.native_ablation outputs/double_helix_final \
  outputs/colmap_diagnosis/helix_native_window6 --window 6 --finish
python -m experiments.map_guided_pairs outputs/double_helix_final \
  outputs/colmap_diagnosis/helix_native_window6 outputs/colmap_diagnosis/helix_native_guided_v2
```

6 项原有合成测试通过。位姿引导试验的两次运行导出相同的重建数组。原结果、审阅、课件与报告源文件保留在各自目录。
