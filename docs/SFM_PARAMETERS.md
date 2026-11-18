# SfM 命令行参数手册

当前分支的入口是 `python -m sfm`，由 [sfm/__main__.py](../sfm/__main__.py) 实现。请在仓库根目录运行。内置帮助列出命令行选项。

```bash
python -m sfm --help
```

## 子命令

| 子命令 | 用途 | 主要产物 |
|---|---|---|
| `inspect` | 读取视频、按参数抽帧、检查输入并计算焦距初值 | `frames/`、`figures/contact_sheet.jpg`、`inputs.json`、`config.resolved.json`、`provenance.json` |
| `reconstruct` | 从视频抽帧，再运行特征匹配、相机注册、三角化和 BA | 输入准备产物，以及 `pointcloud.ply`、`cameras.json`、`reconstruction.npz`、`metrics.json` 等 |

两条命令各自从原视频抽帧。把 `inspect` 生成的 `config.resolved.json` 传给 `reconstruct --config`，即可沿用已经核对的抽帧设置。选取一个新的输出目录，避免和已有实验重名。

## 命令行选项

| 选项 | 默认值 | 作用 |
|---|---|---|
| `--video PATH` | 必填 | 原视频路径，例如 `data/video/double_helix.mp4`。 |
| `--output DIR` | 必填 | 本次运行的新输出目录。 |
| `--config PATH` | 内置默认配置 | 读取 JSON 覆盖项，可只写要改的键。 |
| `--frames N` | `25` | 在选定范围内按源帧编号均匀取样，最少 2 帧。改的是抽样数量，帧率信息仍取自原视频。 |
| `--start INDEX` | `0` | 起始源帧号。 |
| `--end INDEX` | 视频最后一帧 | 结束源帧号，含该帧。帧号从 0 开始，起点必须早于终点，抽帧数须小于等于区间总帧数。 |
| `--focal-factor F` | `0.9` | 用 `F × 工作图像长边` 初始化共享焦距。 |
| `--source-focal-px F` | 由 `focal_factor` 设初值 | 提供可靠的焦距初值，单位是旋转到显示方向后的源图像像素。程序依照工作图像缩放换算。与 `--focal-source` 一起使用，优先于 `--focal-factor`。 |
| `--focal-source TEXT` | 无 | 记录源焦距的依据，例如镜头、录像模式和裁切信息。与 `--source-focal-px` 成对。 |
| `--fit-k1` | 关闭 | 当最终焦距 BA 获接受且至少注册 5 帧时，尝试加一个径向畸变参数 `k1` 再优化。 |
| `--reuse-appearance RUN_DIR` | 重新计算特征与匹配 | 复用一个已有重建运行的 `appearance.json` 和 `appearance.npz`。适合保持帧清单和匹配、几何验证配置一致，仅改焦距或 BA 做对照。仍会从视频抽帧。 |

参数覆盖顺序是 **[默认 JSON](../configs/default.json) → `--config` 指定的键 → 显式命令行选项**。JSON 键名用下划线，例如 `focal_factor`。未知配置键会报错。`--source-focal-px` 和 `--focal-source` 是命令行参数，复跑时可从 `inputs.json` 的内参来源记录中查阅。

## JSON 配置键

以下默认值来自 [configs/default.json](../configs/default.json)。涉及 **px** 的几何阈值使用工作图像像素。视差角单位是度。

### 输入、特征与配对

| 键 | 默认值 | 作用 |
|---|---:|---|
| `seed` | `6121` | 初始化几何验证与注册所用的随机数生成器，便于复现。 |
| `frames` | `25` | 均匀抽取的工作帧数量。 |
| `start` | `0` | 含起点的源帧号。 |
| `end` | `null` | 含终点的源帧号。`null` 表示视频最后一帧。 |
| `long_edge` | `1280` | 工作图像长边的上限，单位 px。视频超过该尺寸时等比例缩小。 |
| `features` | `4500` | 每帧 SIFT 特征预算。启用分格时用于计算每格配额。 |
| `grid_cell` | `0` | 分格边长，单位 px。`0` 使用整图 SIFT 配额。正值把预算分给各格，减少特征集中在少数高纹理区域。 |
| `clahe_clip` | `0.0` | SIFT 检测前的局部对比度增强剪切限制。`0` 关闭 CLAHE。 |
| `root_sift` | `false` | 是否对 SIFT 描述子做 L1 归一化后逐元素开平方。 |
| `contrast` | `0.018` | SIFT 的对比度门限。调低可保留更多低对比候选。 |
| `ratio` | `0.75` | 双向最近邻距离比门限。最近距离须小于该值乘以次近距离，随后保留相互一致的匹配。值越小，筛选越严。 |
| `window` | `4` | 常规图对的最大工作帧索引差。默认每帧与后续最多 4 张工作帧配对。 |
| `loop_window` | `3` | 额外尝试开头与结尾各多少张工作帧之间的配对。`0` 关闭这些首尾候选。 |

### 几何验证、相机注册与三角化

| 键 | 默认值 | 作用 |
|---|---:|---|
| `sampson_px` | `1.5` | 基础矩阵 RANSAC 的 Sampson 距离门限，单位 px。种子相对位姿细化也用该值作损失尺度。 |
| `ransac_trials` | `2000` | 每图对的八点 RANSAC 最大抽样次数。程序可按当前内点率提早结束。 |
| `min_pair_inliers` | `30` | 图对通过验证的最少几何内点数，也用于种子阶段的最少有效三维点数。 |
| `seed_candidates` | `20` | 在主匹配连通分量中，最多尝试多少个高内点数图对作为初始化候选。 |
| `min_seed_angle` | `2.0` | 种子图对的一致观测须达到的中位视差角。 |
| `min_angle` | `1.0` | 一个点须至少有一对有效视线达到该夹角，避免保留低视差点。 |
| `pixel_gate` | `4.0` | 种子、PnP 及增量加点时的重投影误差门限，单位 px。 |
| `final_pixel_gate` | `3.0` | 最终点和观测的重投影过滤门限，单位 px，不能高于 `pixel_gate`。 |
| `min_pnp_inliers` | `20` | 单帧 PnP 所需的最少 3D–2D 对应数和最少内点数，也用于检查最终逐帧支撑。 |
| `min_pnp_ratio` | `0.35` | PnP 细化后的最小内点比例。 |
| `max_attempts` | `4` | 每个未注册视图最多执行多少次满足最低对应数的 PnP 尝试。地图有变化后才重试。 |

### Bundle Adjustment 与共享内参

| 键 | 默认值 | 作用 |
|---|---:|---|
| `ba_every` | `5` | 每增加这么多张注册图就执行一次增量 BA。注册停滞时也可触发一次。 |
| `ba_evaluations` | `30` | 每次增量 BA 的求解步预算。 |
| `ba_final_evaluations` | `100` | 最终 BA 或过滤后再优化时，每次调用的求解步预算。 |
| `focal_factor` | `0.9` | 初始共享焦距相对工作图像长边的倍率。 |
| `focal_bounds` | `[0.45, 2.0]` | 焦距下界和上界，以工作图像长边为单位。这两个界也用于检查初始值。 |
| `log_focal_prior_sigma` | `0.35` | 对初始对数焦距的先验尺度。值越小，向初值的约束越强。 |
| `fit_k1` | `false` | 是否在最终焦距 BA 获接受、且注册至少 5 帧后尝试拟合 `k1`。 |
| `k1_bound` | `0.18` | 启用 `fit_k1` 时，径向畸变系数绝对值的上界。 |
| `k1_prior_sigma` | `0.08` | 启用 `fit_k1` 时，对 `k1 = 0` 的先验尺度。 |

同一段视频共享一个焦距，`fx = fy`。主点固定为 `((W-1)/2, (H-1)/2)`，斜切设为零。默认使用零畸变针孔模型。BA 会联合优化焦距、相机姿态与三维点。

## 常用命令

### 先检查 40 帧，再沿用参数重建

```bash
python -m sfm inspect --video data/video/double_helix.mp4 \
  --frames 40 --output outputs/inspection_40

python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config outputs/inspection_40/config.resolved.json \
  --output outputs/helix_40
```

如果还要改工作图像尺寸，可在自定义 JSON 里写 `{"frames": 40, "long_edge": 960}`，再用 `--config` 读取。

### 复现 Double Helix 主实验

```bash
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json \
  --output outputs/helix_repro
```

[主实验配置](../configs/orbit49_balanced.json)抽取 49 帧，使用 5000 个特征预算、96 px 分格、CLAHE、RootSIFT 和 3 帧匹配窗口。焦距倍率为 0.65，工作图像长边为 1280 px，因此初始焦距为 832 px。主实验最终估计为 619.24 px。[实测记录](SFM_RESULTS.md)

### 用同一组匹配比较不同焦距初值

```bash
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --focal-factor 0.9 \
  --reuse-appearance outputs/helix_repro \
  --output outputs/helix_repro_f090
```

如需测试径向畸变，可以在同样命令上加入 `--fit-k1`，为这次运行另设输出目录。
