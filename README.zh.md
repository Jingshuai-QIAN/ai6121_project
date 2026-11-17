# AI6121 课程项目：运动恢复结构

[English](README.md)

## 项目简介

本项目使用运动恢复结构（Structure from Motion，SfM）方法，从多视角照片重建「双螺旋」（Double Helix）的三维结构。[双螺旋视频](data/video/double_helix.mp4)

当前确定的路线（2026-11-18）是：相机标定、SIFT 自动特征匹配、增量式稀疏 SfM 与 Bundle Adjustment。先用少量视图验证，再以约 25 张清晰、具有重叠与平移视差的图像完成主要实验。项目采用 CPU 上的 NumPy、OpenCV 和 SciPy，不需要 PyTorch。

实现前请阅读[架构与接口设计](docs/SFM_ARCHITECTURE.md)和[Agent 任务与启动说明](docs/SFM_AGENT_TASKS.md)。目前仓库尚无 SfM 实现；`report/main.tex` 中的“8 个手工地标 + 射影重建”是旧方案，须按新实现更新，不能当作当前已完成的方法。

## 项目结构

```text
.
├── data/           # 项目数据
│   ├── figures/    # 用于三维重建的照片
│   ├── points/     # 照片之间的对应点
│   └── video/      # 双螺旋视频
├── report/         # LaTeX 报告源文件
├── .gitignore      # Git 忽略规则
├── README.md       # 英文项目说明
└── README.zh.md    # 中文项目说明
```

## 报告协作

LaTeX 报告源文件将存放在 `report/` 目录，通过 GitHub 协作编写。组员在本地编辑后提交并推送更新。查看其他组员的修改时，拉取最新版本并在本地编译 PDF。

## 提交要求

PDF 报告的提交截止日期为 2026/11/22，提交平台为 NTULearn。报告须说明项目方法并提供详细分析与讨论，在封面列出所有组员的姓名和学号，并声明任何生成式 AI 的使用情况。
