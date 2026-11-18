# AI6121 课程项目 · Double Helix 稀疏 SfM

从 [NTU Double Helix 视频](data/video/double_helix.mp4)自动匹配 SIFT，恢复彩色稀疏点云、相机姿态和共享内参。主实现位于 `feat/sift-calibrated-sfm`。`feat/manual-projective-sfm` 保存手工地标的射影几何基线。

## 运行

在仓库根目录使用 Python 3.11。实测平台为 Linux CPU AMD64。

执行以下命令会在`outputs/orbit_repro`下得到由 `data/video/double_helix.mp4` 的重建结果。

`python -m sfm` 的详细参数说明见[docs/SFM_PARAMETERS.md](/docs/SFM_PARAMETERS.md)

### 1. 环境准备
```bash
python -m venv .venv-sfm
. .venv-sfm/bin/activate
pip install -r requirements.txt
export OPENBLAS_NUM_THREADS=1
export MPLCONFIGDIR=/tmp/ai6121-mpl
```
给当前终端里随后启动的 Python 进程设置环境变量。

- **`export OPENBLAS_NUM_THREADS=1`** 把 OpenBLAS 的计算线程数限制为 1。NumPy 或 SciPy 使用 OpenBLAS 时，这能减少多线程开销，也让 SfM 实验的耗时更容易比较。它只控制 OpenBLAS 的线程。
- **`export MPLCONFIGDIR=/tmp/ai6121-mpl`** 让 Matplotlib 把配置和字体缓存放到可写的临时目录。项目生成的图仍然按运行参数保存到 `outputs/` 下。

普通本地运行可以省略这两条。复现项目里记录的 `CPU 耗时` 时，应保留第一条。


### 2. 自动化测试
```bash
python -m unittest discover -s tests -v
```
顺带检查当前 Python 环境能否导入项目和测试所需的依赖。

如果输出 `Ran 6 tests`和 `OK`，则说明这些检查在当前环境中已经通过。

这个项目目前有 6 项测试，覆盖八点法、三角化、错配与退化处理、增量注册和自标定。


### 3. 视频检查和抽帧

```bash
python -m sfm inspect --video data/video/double_helix.mp4 --output outputs/inspection_demo
```
SfM 重建前的视频检查和抽帧。

从 `data/video/double_helix.mp4` 默认均匀抽取 25 帧，并把结果写到 `outputs/inspection_demo/`。

**产物不会用于重建**，仅供预览和核对：

- `figures/contact_sheet.jpg`：抽帧总览图，用来快速检查画面清晰度、相邻帧重叠和视角变化。
- `frames/`：抽出的工作图像。
- `inputs.json`：记录视频尺寸、帧率、时长，以及每张工作图对应的源帧编号、时间戳和清晰度指标。


### 4. 重建
```bash
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --output outputs/orbit_repro
```
用 `data/video/double_helix.mp4` **重新跑一遍 Double Helix 主实验**，把新结果保存到 `outputs/orbit_repro/`。

- `python -m sfm reconstruct` 启动完整重建流程，从抽帧、SIFT 匹配到相机注册、三角化和 Bundle Adjustment。
- `--video data/video/double_helix.mp4` 指定输入视频。
- `--config configs/orbit49_balanced.json` 使用主实验配置，包括 **均匀抽取 49 帧**、按图像网格分配 SIFT 特征，以及用工作图像长边的 **0.65 倍**作为初始焦距。
*注：默认的config效果不太好，建议使用 orbit49_balanced.json*
- `--output outputs/orbit_repro` 指定新的输出目录。



### 5. 结果审计
```
python -m sfm.audit outputs/orbit_repro --output outputs/orbit_repro/audit
```
复核重建结果里有多少点确实落在 **Double Helix** 的金属带上。它读取 `outputs/orbit_repro` 里已有的点云、相机和特征观测，再用仓库里的人工标注做事后检查。

判定规则：同一个三维点，在**至少两张有效图像**中，实际检测到的特征位置和三维点的重投影位置都落在标注的金属带内区，才计为一个有金属带支持的点。

结果写到 `outputs/orbit_repro/audit/`，主要看：

- `ribbon_audit.json`：通过检查的点数和对应视图。
- `ribbon_support.jpg`：在输入帧上标出审计区域和通过检查的观测。
- `ribbon_supported.ply`：从全场景点云中提取的金属带点子集。

*主实验的点云里，有 399 个点能在至少两帧中对应到雕塑的金属带。*

## 产物

- `pointcloud.ply` 是全场景彩色点云，`cameras.json` 保存逐帧注册状态和 world-to-camera 姿态，尺度任意。
- `tracks.json` 保存原始工作像素与活动标记，`reconstruction.npz` 保存可用 NumPy 读取的点、颜色、位姿和内参。
- `metrics.json`、`events.jsonl`、`pairs.json`、`per_view.csv` 记录配对、注册与过滤、BA 前后和耗时。
- `inputs.json`、`config.resolved.json`、`provenance.json` 保存输入、容器标签、尺寸变换、配置、版本、哈希和种子。使用 `--reuse-appearance <run-dir>` 可在相同抽帧、SIFT 和 RANSAC 设置下复用已验证的图对。
- `figures/` 含接触表、匹配、重投影、误差和点云相机图。 `audit/ribbon_supported.ply` 与审计叠图提供雕塑本体的独立证据。

[实测结果与复现命令](docs/SFM_RESULTS.md) · [架构和模块说明](docs/SFM_ARCHITECTURE.md) 

报告源文件在 `report/`。使用 `cd report && latexmk main.tex` 编译。封面姓名和学号待确认。
