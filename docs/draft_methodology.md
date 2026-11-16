# Methodology 提纲

本提纲按标定后的增量式 SfM 起草。项目仓库目前只有数据采集计划和报告骨架，以下自研模块及求解器属于拟议方案。定稿时按小组代码确认每个模块的算法、参数和库调用。

## 1. Inputs and Reconstruction Pipeline

- **输入**包括 UOB Innovation Hub 的多视角照片与对应点。按当前计划采集 25 张照片、标识 8 个跨视图地标。以统一的地标 ID $j$ 将同一地标在各图中的像素观测组成轨迹。若原始数据以图像对为单位，先按匹配关系合并轨迹，并检查同一轨迹在同一张图中最多有一次观测。
- **相机模型**采用针孔投影。说明每张图使用的内参 $K_i$、畸变参数来源及是否共享内参。下文假设内参已知或可从标定获得，$\mathbf u_{ij}=(u_{ij},v_{ij})$ 表示去畸变后的像素观测，波浪号表示齐次坐标。令 $R_i,t_i$ 为世界坐标到相机坐标的变换，则 $\tilde{\mathbf u}_{ij}\sim K_i(R_i\mathbf X_j+t_i)$，相机中心为 $\mathbf C_i=-R_i^\top t_i$。［3］
- **流程图**可用一行展示。照片与对应点 → 点轨迹与相机参数 → 双视图初始化与初始三角化 → 增量注册与三角化 → 束调整 → 相机位姿与稀疏三维点云。
- **实现分工**沿用 OpenSfM 的流程组织。给定对应点直接进入轨迹构建，小组负责增量循环及几何求解，正文注明实际复用的底层接口。OpenSfM 源码中的双视图初始化会尝试五点法和平面模型。本文拟议方案使用归一化八点法。［1–4］

## 2. Incremental SfM

**Algorithm 1. Incremental sparse reconstruction from known correspondences**

```text
Input: images, landmark tracks, camera intrinsics, distortion parameters
Output: registered camera poses, sparse 3D landmarks, unregistered images

Undistort tracked observations using the camera model
For candidate seed pairs with at least eight shared landmarks:
    Skip the pair if its eight-point system is degenerate
    Estimate rank-two F using the normalized eight-point algorithm
    Form E = K_b^T F K_a and project E onto the essential matrix constraints
    Decompose E into four relative pose candidates
    For each candidate, triangulate seed landmarks with poses (I, 0) and (R, t)
    Choose the pose with the most points of positive depth in both cameras
    Keep only points with sufficient triangulation angle and low reprojection error
    If enough valid landmarks remain for PnP:
        Register the seed pair, keep its landmarks, and stop trying pairs
If no seed passes validation, return an initialization failure

Repeat until all images are registered or a full pass registers no image:
    Rank unregistered images by the number of observed reconstructed landmarks
    For each eligible image in that order:
        Build 2D–3D pairs by joining image observations and 3D landmarks by ID
        Estimate the pose using PnP and validate depth and reprojection errors
        If validation fails, leave the image unregistered for the next pass
        Otherwise, register the image and triangulate newly observable landmarks

Refine registered poses and landmarks jointly by bundle adjustment
Export registered poses, sparse landmarks, and unregistered image IDs
```

**算法 1　基于已知对应点的增量式稀疏重建**

```text
输入：图像、地标轨迹、相机内参、畸变参数
输出：已注册图像的相机位姿、稀疏三维地标、未注册图像

使用相机模型对轨迹中的像素观测去畸变
遍历至少共享 8 个地标的候选种子图像对：
    若八点法方程组退化，则跳过该图像对
    用归一化八点法估计秩为 2 的基础矩阵 F
    计算 E = K_b^T F K_a，并将 E 投影到满足本质矩阵约束的矩阵集合
    将 E 分解为四组候选相对位姿
    对每组候选位姿，使用 (I, 0) 和 (R, t) 对种子图像对中的地标进行三角化
    选择使最多地标在两台相机中均具有正深度的位姿
    仅保留三角化夹角足够大且重投影误差足够小的地标
    若保留的有效地标数满足 PnP 的要求：
        注册该种子图像对，保留其地标，结束候选图像对搜索
若所有候选图像对均未通过检验，则返回初始化失败

重复以下步骤，直至所有图像均已注册，或一整轮未注册任何新图像：
    按各未注册图像观测到的已重建地标数降序排列
    按此顺序处理每张符合条件的图像：
        按地标 ID 将图像观测与三维地标配对，建立 2D–3D 对应
        用 PnP 估计位姿，并检验深度和重投影误差
        若检验失败，则暂缓注册，留待下一轮处理
        否则，注册该图像，并对新获得足够观测的地标进行三角化

通过束调整联合优化已注册图像的相机位姿和三维地标
导出已注册图像的相机位姿、稀疏三维地标和未注册图像的 ID
```

### 2.1 Two-view initialization

- **选种子图像对**时，从共享至少 8 个地标的图像对开始。对候选图像对，检查八点法方程的可解性、双相机正深度及三角化夹角。小基线、近纯旋转或地标近共面都可能使估计不稳定。候选失败时尝试下一对。［2–4］
- **恢复相对位姿**时，分别平移、缩放两图的点坐标以改善条件数，用 SVD 解极线约束 $\tilde{\mathbf u}_{bj}^{\top}F\tilde{\mathbf u}_{aj}=0$，约束秩为 2 后反归一化。用 $E=K_b^\top F K_a$ 转到标定坐标，将其奇异值投影为 $(s,s,0)$，分解得到四组 $(R,t)$，用正深度检验选解。设首相机为 $(I,0)$，第二相机平移的模长取 1 作为初始尺度。若候选对恰有 8 个对应点，八点法只有一组最小样本，单靠该对无法用八点 RANSAC 获得独立的内点支持。［3，4］

### 2.2 Camera registration and triangulation

- **注册新相机**时，用已三角化的地标 ID 建立新图的 2D–3D 对应。拟用线性法实现 PnP。对至少 6 个构型非退化的 2D–3D 对应，用 $K_i^{-1}$ 得到归一化图像坐标，构建 DLT 方程求投影矩阵。统一矩阵的符号和尺度后，将左侧 $3\times 3$ 块投影到 $SO(3)$ 得到旋转，以最右一列作为平移。检查正深度与重投影误差后接受位姿。对应不足或几何退化的图像暂缓。定稿时填写实际 PnP 求解器和验收阈值。［2，3］
- **线性三角化**用于初始化和增量阶段。给定已注册图像的 $P_i=K_i[R_i\mid t_i]$，对同一轨迹堆叠各视图中 $\tilde{\mathbf u}_{ij}\times(P_i\tilde{\mathbf X}_j)=0$ 的独立约束，SVD 求齐次三维点，再以正深度、视线夹角和像素重投影误差验收。若 8 个地标都已由种子图像对恢复，此后加入视图主要增加观测并约束已有地标。［2，3］

### 2.3 Bundle adjustment

- **目标函数**在成功注册且通过几何检验的观测集合 $\Omega$ 上联合优化相机位姿和三维地标。令 $\pi$ 表示透视除法，使用与去畸变观测一致的像素残差。采用普通最小二乘时 $\rho(s)=s$，采用稳健损失时注明其形式和参数。［5］

  $$
  \min_{\{R_i,t_i\},\{\mathbf X_j\}}
  \sum_{(i,j)\in\Omega}
  \rho\!\left(\left\|\mathbf u_{ij}-\pi\!\left(K_i(R_i\mathbf X_j+t_i)\right)\right\|_2^2\right).
  $$

- **优化约束**固定首相机位姿和种子相机间的基线长度以去除相似变换自由度，示例中固定已知内参。正文简述实际旋转参数化、求解器，以及优化是在增量过程中触发还是在末尾统一执行。说明小组自行构造的观测残差与约束，以及实际调用的通用数值优化接口。［3，5］

## 3. Reconstruction Output

- 导出已注册图像的位姿和按地标 ID 索引的三维坐标。用稀疏点云叠加相机视锥展示结果，并记录未注册图像。沿用 OpenSfM 的输出习惯时，可用 JSON 存储位姿和点，用 PLY 展示点云。［1］
- 若有效输入为 8 条地标轨迹，最终稀疏点云最多有 8 个重建地标。无已知距离或控制点时使用相对尺度。注册率、保留地标数及束调整前后的像素重投影误差可放入 Experiments。［2，3］

## References

1. OpenSfM contributors. *OpenSfM*. 软件仓库及官方文档。定稿时填写小组实际采用的版本或 commit。 [增量重建文档](https://github.com/OpenSfM/OpenSfM/blob/master/doc/reconstruction.md) · [重建源码](https://github.com/OpenSfM/OpenSfM/blob/master/opensfm/reconstruction.py) · [命令与导出](https://github.com/OpenSfM/OpenSfM/blob/master/doc/using.md)
2. J. L. Schönberger and J.-M. Frahm. Structure-from-Motion Revisited. *CVPR*, pp. 4104–4113, 2016. [论文](https://openaccess.thecvf.com/content_cvpr_2016/html/Schonberger_Structure-From-Motion_Revisited_CVPR_2016_paper.html)
3. R. Hartley and A. Zisserman. *Multiple View Geometry in Computer Vision*. 2nd ed., Cambridge University Press, 2004. 参见第 6–7 章的相机模型与位姿估计、第 9–12 章的双视图重建与三角化。 [出版社页面](https://www.cambridge.org/core/books/multiple-view-geometry-in-computer-vision/0B6F289C78B2B23F596CAA76D3D43F7A)
4. R. I. Hartley. In Defense of the Eight-Point Algorithm. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 19(6), pp. 580–593, 1997. [DOI](https://doi.org/10.1109/34.601246)
5. B. Triggs, P. F. McLauchlan, R. I. Hartley, and A. W. Fitzgibbon. Bundle Adjustment — A Modern Synthesis. In *Vision Algorithms: Theory and Practice*, LNCS 1883, pp. 298–372, Springer, 2000. [出版社页面](https://link.springer.com/chapter/10.1007/3-540-44480-7_21)
