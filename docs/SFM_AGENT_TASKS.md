# 团队分工与复核

三位负责人可以分别运行合成测试，再一起复查 `README.zh.md` 中的 Double Helix 实验。方法与接口见 [架构说明](SFM_ARCHITECTURE.md)。

| 负责人 | 模块 | 需要讲清的内容 | 快速复核 |
|---|---|---|---|
| A · 数据与对应 | `data.py`、`model.py` | 抽帧与尺寸变换、ratio、互查、冲突消解、内参来源 | 核对接触表和源帧索引。对比 `ratio_ij`、`mutual`、`ransac_inliers`，检查是否由地面耗尽特征预算。 |
| B · 相机几何 | `geometry.py` | 归一化八点、Sampson、E 的四解、PnP 如何继承尺度 | 跑八点最小样本、平面与纯旋转测试。复核成功种子和失败图对的视差与内点。 |
| C · 结构与系统 | `triangulation.py`、`bundle.py`、`reconstruction.py`、`export.py`、`audit.py` | DLT、深度门限、阻尼 Schur 补、焦距与尺度规约、最终审计 | 核对同观测集 BA 前后和过滤移除数量。检查有三视图以上的点和雕塑审计图。 |

共享复核材料包括 `metrics.json`、`events.jsonl`、`per_view.csv`、`pairs.json`、课件报告源文件与 [实测交接](SFM_RESULTS.md)。以运行文件为准复核四舍五入后的报告数值。报告封面需要组员自行确认姓名和学号。
