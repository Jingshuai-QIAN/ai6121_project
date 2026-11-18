# AI6121 Project on Structure from Motion

[简体中文](README.zh.md)

## Project Overview

This AI6121 course project uses structure from motion (SfM) to reconstruct the street-facing side of NTU's UOB Innovation Hub, formerly The Hive, from a handheld video. [Source video](data/video/the_hive.mp4)

The main experiment uses 49 uniformly sampled frames and automatically matches SIFT features across views. [Experiment results](report_reference/RESULTS.md)

## Project Structure

```text
.
├── data/           # Project data
│   ├── figures/    # Photographs for reconstruction
│   ├── points/     # Corresponding points across photographs
│   └── video/      # Source videos
├── report/         # LaTeX report sources
├── .gitignore      # Git ignore rules
├── README.md       # English project overview
└── README.zh.md    # Chinese project overview
```

## Report Collaboration

We will keep the LaTeX report sources in `report/` and collaborate on GitHub. Edit the report locally, then commit and push your changes. To review updates from teammates, pull the latest changes and compile the PDF locally.

## Submission

The PDF report is due on 2026/11/22 via NTULearn. It must describe the project approach, provide detailed analysis and discussion, list all group members’ names and matriculation numbers on the cover page, and disclose any use of generative AI.
