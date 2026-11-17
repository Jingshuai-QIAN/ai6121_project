# AI6121 课程项目 · Double Helix 稀疏 SfM

[English](README.md)

从 [NTU Double Helix 视频](data/video/double_helix.mp4)自动匹配 SIFT，恢复彩色稀疏点云、相机姿态和共享内参。主实现位于 `feat/sift-calibrated-sfm`。`feat/manual-projective-sfm` 保存手工地标的射影几何基线。

## 运行

在仓库根目录使用 Python 3.11。实测平台为 Linux CPU。

```bash
python3.11 -m venv .venv-sfm
. .venv-sfm/bin/activate
pip install -r requirements.txt
export OPENBLAS_NUM_THREADS=1
export MPLCONFIGDIR=/tmp/ai6121-mpl

python -m unittest discover -s tests -v
python -m sfm inspect --video data/video/double_helix.mp4 --output outputs/inspection_demo
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --output outputs/orbit_repro
python -m sfm.audit outputs/orbit_repro --output outputs/orbit_repro/audit
```

`--source-focal-px` 与 `--focal-source` 可输入可靠来源的初值，像素单位按旋转后源图。也可通过 `--focal-factor` 调整假设初值。 `--fit-k1` 在焦距 BA 之后试拟合一个径向系数。 `--start/--end` 可限制到同一录像模式的连续片段。输出目录必须为新目录。

## 产物

- `pointcloud.ply` 是全场景彩色点云，`cameras.json` 保存逐帧注册状态和 world-to-camera 姿态，尺度任意。
- `tracks.json` 保存原始工作像素与活动标记，`reconstruction.npz` 保存可用 NumPy 读取的点、颜色、位姿和内参。
- `metrics.json`、`events.jsonl`、`pairs.json`、`per_view.csv` 记录配对、注册与过滤、BA 前后和耗时。
- `inputs.json`、`config.resolved.json`、`provenance.json` 保存输入、容器标签、尺寸变换、配置、版本、哈希和种子。使用 `--reuse-appearance <run-dir>` 可在相同抽帧、SIFT 和 RANSAC 设置下复用已验证的图对。
- `figures/` 含接触表、匹配、重投影、误差和点云相机图。 `audit/ribbon_supported.ply` 与审计叠图提供雕塑本体的独立证据。

[实测结果与复现命令](docs/SFM_RESULTS.md) · [架构和模块说明](docs/SFM_ARCHITECTURE.md) 

报告源文件在 `report/`。使用 `cd report && latexmk main.tex` 编译。封面姓名和学号待确认。
