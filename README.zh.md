# AI6121 课程项目：运动恢复结构

[English](README.md)

## 项目简介

本项目使用运动恢复结构（Structure from Motion，SfM）方法，从多视角照片重建「双螺旋」（Double Helix）的三维结构。[双螺旋视频](data/video/double_helix.mp4)

小组计划为「双螺旋」拍摄 25 张不同视角的照片，并在每张照片中标注同一组 8 个地标。

## 项目结构

```text
.
├── data/           # 项目数据
│   ├── figures/    # 用于三维重建的照片
│   ├── points/     # 照片之间的对应点
│   └── video/      # 双螺旋视频
├── reconstruct.py  # 命令行重建入口
├── sfm.py          # 基于手工地标的射影 SfM
├── report/         # LaTeX 报告源文件
├── .gitignore      # Git 忽略规则
├── README.md       # 英文项目说明
└── README.zh.md    # 中文项目说明
```

## 运行重建

使用 Python 3.11 或更新版本。将手工标注保存为 `data/points/tracks.csv`，每行记录一张图中的一个地标。以下是表头与一条示例记录。

```csv
image,landmark,x,y
view01.jpg,tip,935.4,410.6
```

使用原图像素坐标，原点在左上角。同一地标在所有图中使用相同 ID。至少准备两张图，每张图都要标出同一组至少 8 个地标。选择在图像和三维场景中分布较广的地标，以及存在视差的视角。程序直接读取 CSV，输出以图像 ID 标识各视角。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python reconstruct.py data/points/tracks.csv --output tmp/sfm
```

程序默认选择对所有视图的初始化重投影误差最低的种子对。要比较指定种子对，可通过 `--seed view01.jpg view15.jpg` 传入 CSV 中的两个图像 ID。

- `point_cloud.ply` 保存射影坐标下的地标点云。距离和角度会随射影坐标系改变。
- `reconstruction.npz` 保存图像和地标 ID、相机矩阵、齐次三维点、像素观测和优化前后的重投影坐标。
- `metrics.json` 保存种子对、固定的地标、优化前后的全局和逐图像素重投影 RMSE，以及束调整收敛状态。

运行 `python -m unittest discover -s tests` 可以验证合成数据上的重建。实测结果见 [SFM_VALIDATION.md](SFM_VALIDATION.md)。


## 报告协作

LaTeX 报告源文件将存放在 `report/` 目录，通过 GitHub 协作编写。组员在本地编辑后提交并推送更新。查看其他组员的修改时，拉取最新版本并在本地编译 PDF。

## 提交要求

PDF 报告的提交截止日期为 2026/11/22，提交平台为 NTULearn。报告须说明项目方法并提供详细分析与讨论，在封面列出所有组员的姓名和学号，并声明任何生成式 AI 的使用情况。
