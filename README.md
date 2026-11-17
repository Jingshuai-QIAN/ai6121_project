# AI6121 Project on Structure from Motion

[简体中文](README.zh.md)

## Project Overview

This AI6121 course project uses structure from motion (SfM) to reconstruct the 3D structure of an object we call Double Helix from multi-view photographs. [Video of Double Helix](data/video/double_helix.mp4)

We plan to take 25 photographs of Double Helix and mark the same eight landmarks in every photograph.

## Project Structure

```text
.
├── data/           # Project data
│   ├── figures/    # Photographs for reconstruction
│   ├── points/     # Corresponding points across photographs
│   └── video/      # Video of Double Helix
├── reconstruct.py  # Command-line reconstruction
├── sfm.py          # Projective SfM from manual landmarks
├── report/         # LaTeX report sources
├── .gitignore      # Git ignore rules
├── README.md       # English project overview
└── README.zh.md    # Chinese project overview
```

## Run the reconstruction

Use Python 3.11 or later. Save the manual annotations to `data/points/tracks.csv` with one row per image and landmark. For example, the first two lines could be:

```csv
image,landmark,x,y
view01.jpg,tip,935.4,410.6
```

Use the original image pixel coordinates, with the origin at the upper left, and keep each landmark ID consistent across all views. Provide at least two views with the same eight or more landmarks visible in every view. Choose landmarks spread across the image and the 3D scene, and use viewpoints with parallax. The solver uses the CSV coordinates directly. The image IDs identify the views in the output.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python reconstruct.py data/points/tracks.csv --output tmp/sfm
```

The solver selects the seed pair with the lowest all-view initialization error. To compare a specific pair, pass `--seed view01.jpg view15.jpg` using IDs from the CSV.

- `point_cloud.ply` contains the reconstructed landmarks in projective coordinates. Their distances and angles depend on the chosen projective frame.
- `reconstruction.npz` contains image and landmark IDs, camera matrices, homogeneous 3D points, observations, and initial and refined pixel projections.
- `metrics.json` reports the chosen seed and frame, global and per-view pixel reprojection RMSE before and after bundle adjustment, and optimizer convergence.

Run the synthetic checks with `python -m unittest discover -s tests`. See [SFM_VALIDATION.md](SFM_VALIDATION.md) for the measured results.

## Report Collaboration

We will keep the LaTeX report sources in `report/` and collaborate on GitHub. Edit the report locally, then commit and push your changes. To review updates from teammates, pull the latest changes and compile the PDF locally.

## Submission

The PDF report is due on 2026/11/22 via NTULearn. It must describe the project approach, provide detailed analysis and discussion, list all group members’ names and matriculation numbers on the cover page, and disclose any use of generative AI.
