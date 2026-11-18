# AlphaSolve Documentation Index

A guide to the documentation, feature guides, reverse engineering research, and architecture plans in this repository.

---

## 1. Feature Guides (Usage)

Guides for features integrated into `python3 -m slp2alpha render`:

| Guide | Description | Key Options |
|---|---|---|
| **[One Command: Replay to Video](slp2video.md)** | `tools/slp2video`: the render, your 3D model as the stage, transparency or a colour, and a CRT look, in one command. | `--model`, `--keep-background`, `--crt` |
| **[Rendering Clips](clips.md)** | Render specific frame ranges (e.g., combos) without rendering entire replays. | `--start-frame`, `--end-frame` |
| **[Static Camera](static-camera.md)** | Lock the camera in place using Melee's fixed-camera mode with screen shake disabled. | `--static-camera` |
| **[Custom Shy Guy Sprites](shy-guy-sprite.md)** | Replace Yoshi's Story Shy Guys with a custom logo or image via Dolphin custom textures. | `--shy-guy-sprite`, `--scale` |
| **[Animelee Cel-Shaded Skins](../tools/animelee/README.md)** | Render replays with Animelee's cel-shaded character models and stages. | `--animelee`, `tools/animelee/build_iso.py` |
| **[Logo as the Stage](logo-stage.md)** | Fighters over a 3D logo, or any model, sized to the stage, seen through Melee's own camera. | `tools/logo-stage/logo_stage.py`, `plate.py --model` |
| **[Camera Export](camera-export.md)** | Melee's camera on every frame of a render, and an importer that turns it into a Blender camera. | `--export-camera`, `tools/camera-export` |

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
| **[Windows Automation Plan](plan-windows.md)** | Scoping, architecture, and effort estimate for one-command automation on Windows with Slippi's official (Ishiiruka) playback build. |
| **[Windows: Mainline Build and Camera Export](plan-windows-mainline.md)** | Building the patched headless mainline Dolphin for Windows (GitHub Actions or locally), and the slp2alpha changes, so `--export-camera` and window-free renders work there. Partly implemented. |
| **[Windows: Remaining Work](plan-windows-remaining.md)** | What's left to do on a Windows machine, in order: build the package, the first render, the camera export against the Mac's, the render tests. |
| **[Camera Export: Dolphin Patch](plan-camera-export-dolphin.md)** | Reading the game camera in Dolphin on every recorded frame and writing `camera - NAME.json` (`render --export-camera`). |
| **[Camera Export: Blender Importer](plan-camera-export-blender.md)** | An animated Blender camera that matches the rendered video frame for frame. |
| **[Camera Export: Validation](plan-camera-export-validation.md)** | Checks that the exported camera is what the game drew with, on the right frames, and that Blender reproduces it. |

---

## 4. Testing & Verification

| Suite | Description |
|---|---|
| **[Render Tests](../tools/render-tests/README.md)** | Automated test harness that renders public replays from Slippi Lab across all legal stages, options, and formats, verifying black/white field pairing and transparency. |
| **[Animelee Validation Matrix](../research/animelee/README.md)** | Scripts comparing frame counts and alpha difference between vanilla and modded ISOs across diverse replays. |
