# Methodology 提纲

本提纲采用课件第 4 节的未标定透视 SfM。双视图初始化从基础矩阵恢复投影相机，随后按 Hartley 的投影重建方法逐张注册其余图像。拍摄同学只需提供照片，重建以跨视图地标对应为输入，无需预先标定或手动记录内参。［6，7］以下为拟议方案，定稿时按小组代码确认各模块的算法、参数和库调用。

## 1. Inputs and Reconstruction Pipeline

- **输入**包括 $N$ 张多视角图像和 $M$ 条跨视图地标轨迹。以统一的地标 ID $j$ 将同一地标在各图中的像素观测组成轨迹。若原始数据以图像对为单位，先按匹配关系合并轨迹，并检查同一轨迹在同一张图中最多有一次观测。
- **相机模型**为第 $i$ 张图像使用秩为 3 的 $3\times 4$ 投影矩阵 $P_i$。记 $\mathbf u_{ij}=(u_{ij},v_{ij})$ 为标注的像素坐标，波浪号表示齐次坐标，则 $\tilde{\mathbf u}_{ij}\sim P_i\tilde{\mathbf X}_j$。［3，6］拟直接使用原图像素并假设残余镜头畸变较小。
- **流程图**可用一行展示。照片与对应点 → 地标轨迹 → 基础矩阵与种子投影相机 → 初始三角化 → 增量注册与三角化 → 束调整 → 投影相机与稀疏点云。
- **实现分工**参考 OpenSfM 和 Schönberger–Frahm 的增量流程组织。［1，2］OpenSfM 的重建文件以相机模型、旋转和平移表示各视图。［1］给定对应点直接进入轨迹构建，小组实现投影相机初始化、增量注册、三角化及束调整残差，并维护投影矩阵 $P_i$。正文注明实际复用的接口。

## 2. Incremental SfM

**Algorithm 1. Incremental projective reconstruction from known correspondences**

```text
Input: images and landmark tracks in pixel coordinates
Output: projection matrices, sparse projective 3D landmarks, unregistered images

For candidate seed pairs with at least eight shared landmarks:
    Skip the pair if its eight-point system is degenerate
    Estimate rank-two F using the normalized eight-point algorithm
    Construct two projective camera matrices from F
    Triangulate shared landmarks and check conditioning and reprojection error
    If at least six valid landmarks remain in a nondegenerate configuration for DLT:
        Register the seed pair, keep its landmarks, and stop trying pairs
If no seed passes validation, return an initialization failure

Repeat until all images are registered or a full pass registers no image:
    Rank unregistered images by the number of observed reconstructed landmarks
    For each image in that order with at least six observed reconstructed landmarks:
        Build 2D–3D pairs by joining image observations and 3D landmarks by ID
        Estimate the projection matrix using DLT and validate it by reprojection
        If validation fails, leave the image unregistered for the next pass
        Otherwise, register the image and triangulate newly observable landmarks

Refine projection matrices and landmarks jointly by bundle adjustment
Export projection matrices, sparse projective landmarks, and unregistered image IDs
```

**算法 1　基于已知对应点的增量式投影重建**

```text
输入：图像及其像素坐标系中的地标轨迹
输出：相机投影矩阵、稀疏投影三维地标、未注册图像

遍历至少共享 8 个地标的候选种子图像对：
    若八点法方程组退化，则跳过该图像对
    用归一化八点法估计秩为 2 的基础矩阵 F
    由 F 构造两个投影相机矩阵
    对共享地标做三角化，检查方程的数值稳定性和重投影误差
    若至少保留 6 个几何构型满足 DLT 要求的有效地标：
        注册该种子图像对，保留其地标，结束候选图像对搜索
若所有候选图像对均未通过检验，则返回初始化失败

重复以下步骤，直至所有图像均已注册，或一整轮未注册任何新图像：
    按各未注册图像观测到的已重建地标数降序排列
    按此顺序处理至少观测到 6 个已重建地标的图像：
        按地标 ID 将图像观测与三维地标配对，建立 2D–3D 对应
        用 DLT 估计投影矩阵，并检验重投影误差
        若检验失败，则暂缓注册，留待下一轮处理
        否则，注册该图像，并对新获得足够观测的地标进行三角化

通过束调整联合优化投影矩阵和三维地标
导出投影矩阵、稀疏投影三维地标和未注册图像的 ID
```

### 2.1 Two-view initialization

- **估计基础矩阵**时，先在各图中平移、缩放点坐标，再用 SVD 解极线约束 $\tilde{\mathbf u}_{bj}^{\top}F\tilde{\mathbf u}_{aj}=0$，施加秩为 2 的约束后反归一化。［4］小基线、近纯旋转或地标近共面都可能使估计不稳定。［3］若候选对恰有 8 个对应点，应从完整 SVD 取得 $8\times 9$ 方程的右零空间。此时只有一组八点样本，应核对地标标注并结合其他视图验证。
- **构造种子投影相机**时，从 $F^\top\mathbf e_b=0$ 求第二幅图的齐次极点 $\mathbf e_b$，并令 $\|\mathbf e_b\|_2=1$。取 $P_a=[I\mid\mathbf 0]$、$P_b=[-[\mathbf e_b]_\times F\mid\mathbf e_b]$，其中 $[\mathbf e_b]_\times$ 表示叉积矩阵。用两台相机三角化共同地标。［3，6］若方程退化或可用于后续注册的地标不足，则尝试下一对。

### 2.2 Camera registration and triangulation

- **注册新相机**时，用已三角化的地标 ID 建立至少 6 组非退化的 2D–3D 对应，对像素和三维点做坐标归一化，再用直接线性变换（DLT）估计 $P_i$。每组对应从 $\tilde{\mathbf u}_{ij}\times(P_i\tilde{\mathbf X}_j)=0$ 提供两个独立线性约束。［3，7］SVD 求解后反归一化，检查相机矩阵的秩及像素重投影误差。对应不足或方程病态的图像暂缓。
- **线性三角化**使用同一约束，将各已注册视图的 $P_i$ 视为已知，对 $\tilde{\mathbf X}_j$ 求解。堆叠至少两个视图的约束，用 SVD 求齐次三维点。［3，6］检查数值稳定性及像素重投影误差。若种子图像对已恢复全部 $M$ 个地标，后续注册的图像将为这些地标提供更多观测。

### 2.3 Bundle adjustment

- **目标函数**在成功注册且通过几何检验的观测集合 $\Omega$ 上联合优化相机投影矩阵和三维地标。令 $\pi$ 表示透视除法，使用像素重投影残差。［3，6，7］采用普通最小二乘时 $\rho(s)=s$。若采用稳健损失，注明其形式和参数。［5］

  $$
  \min_{\{P_i\},\{\tilde{\mathbf X}_j\}}
  \sum_{(i,j)\in\Omega}
  \rho\!\left(\left\|\mathbf u_{ij}-\pi\!\left(P_i\tilde{\mathbf X}_j\right)\right\|_2^2\right).
  $$

- **优化约束**需要固定投影坐标系。任意可逆 $4\times 4$ 矩阵 $H$ 都能将相机和点变换为 $P_iH^{-1}$ 和 $H\tilde{\mathbf X}_j$，而像素投影保持相同。［3，5］参考 Mohr 等人的方法，拟选取并固定 5 个初始地标作为投影参考系，要求任意 4 个均不共面。［3，8］对每个待优化的相机矩阵和三维点，各选一个非零分量归一化为 1 并固定，以确定各自的齐次尺度。定稿时记录实际约束、求解器及触发时机。

## 3. Reconstruction Output

- 项目拟用自定义 JSON 导出投影矩阵及按地标 ID 索引的齐次三维坐标，并记录未注册图像。需要展示时，将当前坐标系中的有限点转为非齐次坐标后导出 PLY。由 $M$ 条输入轨迹最多重建 $M$ 个地标。
- 结果属于投影重建，未知的三维投影变换可能改变距离、角度和平行关系。建筑尺寸和真实相机姿态需要额外的度量约束。［3，6，7］点云可用于可视化和重投影检验。Experiments 可报告注册率、保留地标数及束调整前后的像素重投影误差。

## References

1. OpenSfM contributors. *OpenSfM*. 软件仓库及官方文档。定稿时填写小组实际采用的版本或 commit。 [增量重建文档](https://github.com/OpenSfM/OpenSfM/blob/master/doc/reconstruction.md) · [重建源码](https://github.com/OpenSfM/OpenSfM/blob/master/opensfm/reconstruction.py) · [数据格式](https://github.com/OpenSfM/OpenSfM/blob/master/doc/dataset.md)
2. J. L. Schönberger and J.-M. Frahm. Structure-from-Motion Revisited. *CVPR*, pp. 4104–4113, 2016. 参见第 2 节和图 2 的增量 SfM 流程。 [论文 PDF](https://openaccess.thecvf.com/content_cvpr_2016/papers/Schonberger_Structure-From-Motion_Revisited_CVPR_2016_paper.pdf)
3. R. Hartley and A. Zisserman. *Multiple View Geometry in Computer Vision*. 2nd ed., Cambridge University Press, 2004. 参见第 4.1.4 节（三维投影变换的约束）、第 6.2 和 7.1 节（投影相机及 DLT）、第 9.3、9.5 和 10.2–10.4 节（特殊运动、由 $F$ 恢复相机及投影歧义）、第 11.2、11.9 和 12.2 节（八点法、退化和线性三角化）及第 18.1 节（投影束调整）。 [出版社目录](https://assets.cambridge.org/97805215/40513/toc/9780521540513_toc.pdf) · [作者主页与样章](https://www.robots.ox.ac.uk/~vgg/hzbook/)
4. R. I. Hartley. In Defense of the Eight-Point Algorithm. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 19(6), pp. 580–593, 1997. 参见第 2.3、5.1 和 7.1.2 节的秩约束及坐标归一化。 [DOI](https://doi.org/10.1109/34.601246) · [论文 PDF](https://www.cs.ucf.edu/courses/cap6938-02/refs/hartley.pdf)
5. B. Triggs, P. F. McLauchlan, R. I. Hartley, and A. W. Fitzgibbon. Bundle Adjustment — A Modern Synthesis. In *Vision Algorithms: Theory and Practice*, LNCS 1883, pp. 298–372, Springer, 2000. 参见第 3 和 9 节的误差模型及坐标系自由度。 [出版社页面](https://link.springer.com/chapter/10.1007/3-540-44480-7_21) · [作者提供的论文](https://lear.inrialpes.fr/people/triggs/pubs/Triggs-va99.pdf)
6. AI6121 课程课件。第 4 节 *Perspective SFM*，PDF 第 33–35 页（投影模型与歧义）、第 37–46 页（双视图代数法与三角化）和第 52–53 页（束调整）。 [本地课件](slides_sfm.pdf)
7. R. I. Hartley. Euclidean Reconstruction from Uncalibrated Views. In *Applications of Invariance in Computer Vision*, pp. 235–256, Springer, 1994. 参见第 6 节的投影重建及六点 DLT 注册，以及第 7 节的度量升级条件。 [出版社页面](https://link.springer.com/chapter/10.1007/3-540-58240-1_13) · [作者提供的论文](https://users.cecs.anu.edu.au/~hartley/Papers/reconstruction/springer/reconstruction.pdf)
8. R. Mohr, B. Boufama, and P. Brand. Accurate Projective Reconstruction. In *Applications of Invariance in Computer Vision*, pp. 257–276, Springer, 1994. 用于固定投影参考系的五点约束。 [出版社页面](https://link.springer.com/chapter/10.1007/3-540-58240-1_14)
