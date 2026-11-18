# AlphaSolve Documentation Index

A guide to the documentation, feature guides, reverse engineering research, and architecture plans in this repository.

---

## 1. Feature Guides (Usage)

Guides for features integrated into `python3 -m slp2alpha render`:

| Guide | Description | Key Options |
|---|---|---|
| **[Rendering Clips](clips.md)** | Render specific frame ranges (e.g., combos) without rendering entire replays. | `--start-frame`, `--end-frame` |
| **[Static Camera](static-camera.md)** | Lock the camera in place using Melee's fixed-camera mode with screen shake disabled. | `--static-camera` |
| **[Custom Shy Guy Sprites](shy-guy-sprite.md)** | Replace Yoshi's Story Shy Guys with a custom logo or image via Dolphin custom textures. | `--shy-guy-sprite`, `--scale` |
| **[Animelee Cel-Shaded Skins](../tools/animelee/README.md)** | Render replays with Animelee's cel-shaded character models and stages. | `--animelee`, `tools/animelee/build-iso.sh` |

---

## 2. Technical Analysis & Reverse Engineering (Research)

In-depth technical writeups analyzing Super Smash Bros. Melee internals, disassembly, and Gecko code design:

| Document | Topic |
|---|---|
| **[Characters-Only Research](characters-only-research.md)** | Disassembly and discovery of the Develop Mode stage-visibility getter switch (`grDisplay_801C5DB0`), allowing stage-free renders on all legal stages without desyncs. |
| **[Stage Backgrounds Analysis](stage-backgrounds.md)** | Breakdown of how background geometry, objects (`grXX_StageCallbacks`), and particle systems interact with the flicker technique on each legal stage. |
| **[Research Probes & Spikes](../research/README.md)** | Exploratory scripts for Shy Guy texture discovery, coordinate-to-screen pixel calibration, and ISO diffing. |

---

## 3. Architecture & Implementation Plans

Design specifications and cross-platform planning:

| Document | Scope |
|---|---|
| **[macOS Implementation Plan](plan-macos-apple-silicon.md)** | Architecture, benchmarks, and current status of the native Apple Silicon unattended pipeline (`slp2alpha` + headless mainline Dolphin + Metal + FFV1). |
| **[Windows Automation Plan](plan-windows.md)** | Scoping, architecture, and effort estimate for bringing headless one-command automation to Windows. |

---

## 4. Testing & Verification

| Suite | Description |
|---|---|
| **[Render Tests](../tools/render-tests/README.md)** | Automated test harness that renders public replays from Slippi Lab across all legal stages, options, and formats, verifying black/white field pairing and transparency. |
| **[Animelee Validation Matrix](../research/animelee/README.md)** | Scripts comparing frame counts and alpha difference between vanilla and modded ISOs across diverse replays. |
