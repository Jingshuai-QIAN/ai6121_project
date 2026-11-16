# AI6121 课程项目：运动恢复结构

[English](README.md)

## 项目简介

本项目使用运动恢复结构（Structure from Motion，SfM）方法，从多视角照片重建「双螺旋」（Double Helix）的三维结构。[双螺旋视频](data/video/double_helix.mp4)

小组计划为「双螺旋」拍摄 25 张不同视角的照片，并使用图像间的 8 个对应点。

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
