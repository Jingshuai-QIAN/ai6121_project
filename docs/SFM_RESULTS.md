# Double Helix 实测交接

主分支 `feat/sift-calibrated-sfm` 包含 A/B/C 模块、CLI、合成验证、配置、视频后验审计和 LaTeX 报告。手工射影基线位于 `feat/manual-projective-sfm`。

## 输入检查

OpenCV 读到 996 帧，平均约 30.035 fps。H.264 视频轨为 33.161 秒，带音频的容器为 33.237 秒。码流是 1280×720，容器含 90° 朝向，解码出的工作图为 720×1280。本实验未缩放、未裁切。PyAV 检查容器和视频流标签后未找到可解释为实测焦距的字段。SHA-256 为 `6435c20fb546a0e8a922ee12ded4165e4570c889684f85ff5be9be76cc4debaa`。

接触表显示相机绕行一周，地面、雕塑和远处建筑间有相对视差。小步进图像重叠较好，首尾有回环。49 帧的灰度 Laplacian 方差为 309–1225，作为纹理与相对清晰度指标。抽样图里没有明显的跳切或突变式变焦。容器无法确认镜头型号、电子防抖、滚动快门补偿或动态裁切。所有结果基于一个共享模型。

## 分层结果

| 实验 | 注册 | 场景点 | 多视图金属带审计 | 重投影中位数 | 估计焦距 |
|---|---:|---:|---:|---:|---:|
| 247、332 两视图失败 | 0/2 | 0 | — | — | — |
| 248、290 两视图 | 2/2 | 77 | — | 0.369 px | 792.48 px |
| 25 帧，全局 SIFT | 8/25 | 1,728 | 0 | 0.162 px | 647.23 px |
| **49 帧，832 px 初值** | **49/49** | **12,609** | **399** | **0.226 px** | **619.24 px** |
| 49 帧，1152 px 初值 | 49/49 | 12,581 | 400 | 0.226 px | 619.11 px |
| 49 帧，1536 px 初值 | 49/49 | 13,695 | 366 | 0.258 px | 654.31 px |
| 49 帧，832 px 初值，再拟合 k1 | 49/49 | 12,421 | 399 | 0.210 px | 616.93 px |

247/332 图对有 23 个双向 ratio 后匹配和 11 个几何内点，低于 30 的阈值。25 帧的 17 张未注册图像都缺少足够的现有 3D–2D 支持。源帧如下所列，均保留在分母和 CSV 中。

```text
207 249 290 332 373 415 456 498 539 580 622 663 705 746 788 829 871
```

49 帧方案保留上述 25 张并插入 24 张中间帧，同时修改特征分布策略。帧密度和特征策略都发生了变化。场景注册成功的判据为有限位姿、正深度、活动观测误差和视差通过门限、三视图以上 tracks，以及最后的 BA。它验证场景覆盖。金属带另按图像区域验证，避免以地面和建筑点替代雕塑证据。

## 主结果的质量检查

- 尝试 150 对，验证 133 对，形成 14,670 条候选 tracks，拒绝 9 条同图冲突合并边。全部 47 次新增相机的 PnP 都成功。种子为工作帧 19/20，对应源帧 394/415。
- 最终 12,609 个点有 31,641 个活动观测。8,903 个点恰好两视图可见，3,706 个点至少三视图可见，最长 15 视图。逐长度分布见 `metrics.json`。三角化最大视线夹角的跨点中位数为 8.04°。
- 最终焦距 BA 在同一观测集上把 RMSE 从 0.485 px 降到 0.441 px，Huber 总成本从 3692.68 降到 3089.36。3 px 与 1° 质量门控、重优化及再检查共移除 172 个点，同时记录逐轮移除与重新激活的观测。最后的 RMSE 为 0.430 px，P95 为 0.890 px，最大值为 2.990 px。
- 用最终 K 和位姿重算极线几何，25,184 个初始 RANSAC 内点中有 24,756 个仍在 1.5 近似像素的 Sampson 阈值内。该数保留原图对的分母。
- 雕塑审计对原始工作像素与当前模型预测像素分别做多视图检查。399 条轨迹在两个或更多活动视图同时落在保守的金属带内区，其中 117 条满足三个或更多视图。审计区域覆盖 49 个源帧，48 个视图包含合格观测。区域用于评估，点云本身由自动匹配产生。可看到多个金属带局部，高反光、低纹理及较暗区域仍有明显空缺。计数是符合规则的 tracks，重复尺度或方向的 SIFT 特征可能指向相邻位置。
- 49 帧无缓存重跑耗时 135.73 秒。抽帧和接触表 1.90 秒，SIFT 14.69 秒，匹配与几何验证 86.45 秒，增量与 BA 31.05 秒，导出 1.30 秒。无缓存和使用对应缓存的重跑逐数组一致。对导出的 NPZ 和 PLY 另用 OpenCV 投影复核，31,641 个活动观测全部正深度，最小三角化角 1.0004°，所有位姿通过 SO(3) 检查。

## 自标定对照

以 832 px 主结果为参考，用公共相机中心做相似对齐，并将差异除以参考轨迹 RMS 半径。1152 px 初值的相机中心与共同点的中位差分别为 0.019% 和 0.030%，姿态中位差为 0.014°。1536 px 初值两项差异扩大到 5.80% 和 7.55%，姿态差约 5.81°。这次高初值运行达到评估预算上限，保留了有限且降低了目标的解。此对照说明配准数和低残差不足以判断三维稳定性。

可选径向 BA 得到 k1 = −0.01255，同一观测集 RMSE 从 0.441 px 降为 0.421 px。相似对齐后，它相对主结果的相机中心和共同点中位差为 0.203% 和 0.543%。主交付采用焦距模型。估计内参属于联合优化结果，世界尺度任意。若要独立确认焦距和畸变，请提供原拍摄镜头和同录像模式的棋盘格视频或帧，或可靠的焦距、传感器有效成像区域与裁切信息。

## 复现实验

在仓库根目录，以 Python 3.11.17、NumPy 2.4.6、SciPy 1.17.1、OpenCV 5.1.0.95 wheel、Matplotlib 3.11.2、PyAV 18.1.0 执行。包含无噪 DLT、20% 错配、共面、纯旋转、部分 tracks、断连、径向及 Jacobian 的 6 项合成测试通过。以下给出等价复现命令。每个运行的 `provenance.json` 保留实跑命令与缓存来源。重跑时换用新目录。

```bash
export OPENBLAS_NUM_THREADS=1
export MPLCONFIGDIR=/tmp/ai6121-mpl

python -m unittest discover -s tests -v
python -m sfm inspect --video data/video/double_helix.mp4 --output outputs/video_inspection
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --frames 2 --start 247 --end 332 --output outputs/two_view
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --frames 2 --start 248 --end 290 --output outputs/final2
python -m sfm reconstruct --video data/video/double_helix.mp4 --output outputs/final25
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --output outputs/double_helix_final
python -m sfm.audit outputs/double_helix_final --output outputs/double_helix_final/audit

python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --reuse-appearance outputs/double_helix_final \
  --focal-factor 0.9 --output outputs/final49_f090
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --reuse-appearance outputs/double_helix_final \
  --focal-factor 1.2 --output outputs/final49_f120
python -m sfm reconstruct --video data/video/double_helix.mp4 \
  --config configs/orbit49_balanced.json --reuse-appearance outputs/double_helix_final \
  --fit-k1 --output outputs/final49_radial
python -m sfm.compare outputs/double_helix_final \
  outputs/final49_f090 outputs/final49_f120 outputs/final49_radial \
  --output outputs/final49_comparison.json

cd report && latexmk main.tex
```

失败两视图和部分 25 帧按预期返回退出码 2 与 3。源码里记录了报告生成式 AI 与外部软件披露。封面组员姓名和学号待填写。
