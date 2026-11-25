# AlphaSolve Documentation Index

A guide to the documentation, feature guides, reverse engineering research, and architecture plans in this repository.

---

## 1. Feature Guides (Usage)

Guides for features integrated into `python3 -m slp2alpha render`:

| Guide | Description | Key Options |
|---|---|---|
| **[One Command: Replay to Video](slp2video.md)** | `tools/slp2video`: the render, your 3D model as the stage, transparency or a colour, and a CRT look, in one command. | `--model`, `--keep-background`, `--crt` |
| **[CRT](../tools/crt/README.md)** | `tools/crt`: CRT Royale on any video through librashader, with the shaders vendored, on macOS, Linux and Windows. | `render_video.py --physical-pixels`, `install_librashader.py` |
| **[Rendering Clips](clips.md)** | Render specific frame ranges (e.g., combos) without rendering entire replays. | `--start-frame`, `--end-frame` |
| **[Static Camera](static-camera.md)** | Lock the camera in place using Melee's fixed-camera mode with screen shake disabled. | `--static-camera` |
| **[Custom Shy Guy Sprites](shy-guy-sprite.md)** | Replace Yoshi's Story Shy Guys with a custom logo or image via Dolphin custom textures. | `--shy-guy-sprite`, `--scale` |
| **[Name Tags](nametags.md)** | Change what players' name tags say, or hide them, and when they're drawn at all. | `--nametag P1=TEXT`, `--no-nametags` |
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
| **[Linux: Mainline Build and GitHub Actions](plan-linux.md)** | Building the headless mainline Dolphin for Linux (x86_64 and arm64) on GitHub Actions, the slp2alpha changes, and testing it all in Docker on a Mac. Implemented; runs on an x86_64 PC. |
| **[Linux: the Whole Pipeline with a GPU](plan-linux-gpu.md)** | The rest of `slp2video` on a Linux PC with an NVIDIA GPU: NVIDIA's driver, what limits each step, faster encoders, cheaper checks, a `--gpu` option, the CRT on Vulkan, and running renders from scripts. Plan. |
| **[GPU Work After the Render: Model and CRT](plan-gpu-crt-model.md)** | Making the 3D model and the CRT faster, Linux with NVIDIA first: CRT Royale drawn by Blender's GPU module, NVENC with a matte file for transparency, cheaper Blender frames. Steps L1–L3 done. |
| **[Report: the CRT on the GPU](report-gpu-crt.md)** | Measured on an M1 and a GTX 1060: the CRT step 3–6 times faster, frames within 0.005/255 of librashader's, the model twice as fast without shadows, whole `slp2video --model logo --crt` runs from 120–165 s to 41–60 s. |
| **[Where Each Step Runs](pipeline-hardware.md)** | Every step of `slp2video --model logo --crt` on macOS, Linux and Windows: its software, the CPU, GPU or GPU encoder it runs on, and its time. |
| **[Camera Export: Dolphin Patch](plan-camera-export-dolphin.md)** | Reading the game camera in Dolphin on every recorded frame and writing `camera - NAME.json` (`render --export-camera`). |
| **[Camera Export: Blender Importer](plan-camera-export-blender.md)** | An animated Blender camera that matches the rendered video frame for frame. |
| **[Camera Export: Validation](plan-camera-export-validation.md)** | Checks that the exported camera is what the game drew with, on the right frames, and that Blender reproduces it. |

---

## 4. Testing & Verification

| Suite | Description |
|---|---|
| **[Render Tests](../tools/render-tests/README.md)** | Automated test harness that renders public replays from Slippi Lab across all legal stages, options, and formats, verifying black/white field pairing and transparency. |
| **[Animelee Validation Matrix](../research/animelee/README.md)** | Scripts comparing frame counts and alpha difference between vanilla and modded ISOs across diverse replays. |
