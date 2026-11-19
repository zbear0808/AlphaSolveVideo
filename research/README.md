# Research & Reverse Engineering

This directory contains exploratory scripts, experiments, and calibration tools developed while reverse-engineering Super Smash Bros. Melee mechanics and validating custom rendering features.

## Contents

- **[`shyguy-probe/`](shyguy-probe/README.md)**:
  Reverse-engineering Yoshi's Story Shy Guy rendering. Includes texture dump diffing, custom texture extraction from `GrSt.dat`, replay coordinate to screen pixel fitting (`calibrate.py`), and sprite replacement demos.
  *(The production custom sprite feature is integrated into `slp2alpha render --shy-guy-sprite`)*.
- **[`animelee/`](animelee/README.md)**:
  Validation tools for Animelee cel-shaded skins. Includes ISO binary diffing (`isodiff.py`), side-by-side vanilla vs. modded render comparison (`compare.py`), and a multi-replay test matrix (`run-matrix.sh`).
- **[`linux-gpu/`](linux-gpu/README.md)**:
  Measurements on a Linux PC with two GPUs: which GPU each program draws on (`gpu_check.sh`), Blender's speed on the logo plate, where the CPU goes in a render, and FFmpeg's ProRes encoders.
  *(The findings are in [`docs/plan-linux-gpu.md`](../docs/plan-linux-gpu.md))*.

For technical analysis and research write-ups on Melee stage internals and Gecko codes, see the [Documentation Index](../docs/README.md).
