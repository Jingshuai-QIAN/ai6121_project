# AI6121 Project on Structure from Motion

[简体中文](README.zh.md)

## Project Overview

This AI6121 course project uses structure from motion (SfM) to reconstruct the 3D structure of an object we call Double Helix from multi-view photographs. [Video of Double Helix](data/video/double_helix.mp4)

The selected approach (2026-11-18) is camera calibration, automatic SIFT matching, incremental sparse SfM, and bundle adjustment. Start with a small image set, then target approximately 25 clear images with overlap and translational parallax for the main experiment. The CPU implementation will use NumPy, OpenCV, and SciPy; PyTorch is not required.

Before implementation, read the [architecture and interface design](docs/SFM_ARCHITECTURE.md) and [agent tasks and launch instructions](docs/SFM_AGENT_TASKS.md) (Chinese). The repository does not yet contain an SfM implementation. The eight-manual-landmark projective reconstruction in `report/main.tex` is an older design and must be updated to match the implementation.

## Project Structure

```text
.
├── data/           # Project data
│   ├── figures/    # Photographs for reconstruction
│   ├── points/     # Corresponding points across photographs
│   └── video/      # Video of Double Helix
├── report/         # LaTeX report sources
├── .gitignore      # Git ignore rules
├── README.md       # English project overview
└── README.zh.md    # Chinese project overview
```

## Report Collaboration

We will keep the LaTeX report sources in `report/` and collaborate on GitHub. Edit the report locally, then commit and push your changes. To review updates from teammates, pull the latest changes and compile the PDF locally.

## Submission

The PDF report is due on 2026/11/22 via NTULearn. It must describe the project approach, provide detailed analysis and discussion, list all group members’ names and matriculation numbers on the cover page, and disclose any use of generative AI.
