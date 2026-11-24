# Where each step of `slp2video` runs, and how long it takes

November 2026. `slp2video REPLAY --model logo --crt` with the moving camera: the fighters made transparent, the logo in place of the stage, the CRT on top. The times are for 4 s of play (240 frames, frames 1500–1739 of the render tests' `DishonestMuddyCoyote.slp`), measured on 22–23 November ([`report-gpu-crt.md`](report-gpu-crt.md)). They include each step's start-up, which a whole game spreads over more frames.

What each step runs on:

- **CPU:** the processor;
- **GPU:** the graphics chip's 3D side;
- **GPU encoder:** the graphics chip's separate video encoder, NVENC on NVIDIA.

## macOS (Mac mini, M1)

| # | Step | Software | Runs on | Time |
|---|---|---|---|---|
| 1 | Play the replay twice over (black and white backgrounds) and record it | Headless mainline Slippi Dolphin (`tools/dolphin-build`), Metal; Gecko codes (`tools/slp2alpha`) | CPU (emulation, one thread), GPU (drawing), CPU (FFV1 recording, inside Dolphin) | 5 s, together with step 2 (2.2× real time) |
| 2 | Solve the transparency, while Dolphin records | ffmpeg 9.0 filters; Apple's ProRes encoder (`prores_videotoolbox`) | CPU (on a plain M1 Apple's ProRes encoder runs in software; M1 Pro/Max and later have a ProRes engine) | (in step 1) |
| 3 | Check the recording: field pairing, brightness | ffmpeg (decoding) | CPU | 4 s |
| 4 | Export the game's camera | Inside Dolphin (`--export-camera` patch) | CPU | none extra |
| 5 | The logo through the game's camera, one PNG per frame | Blender 5.2, EEVEE, 2 processes, 16 samples, no shadows | GPU (drawing), CPU (scene, PNG writing) | 18 s |
| 6 | Composite: the fighters over the logo | ffmpeg (`overlay`), lossless FFV1 | CPU | 1 s |
| 7a | Squeeze each frame to Melee's shape (584×480) | ffmpeg (Lanczos) | CPU | in 7b |
| 7b | CRT Royale at 3504×2880 | Blender's GPU module (`tools/crt/blender_crt.py`), Metal | GPU | 13–17 s, steps 7a–7d together |
| 7c | The alpha, scaled up to the CRT's size and merged | ffmpeg | CPU | in 7b |
| 7d | Encode: ProRes 4444 `.mov` | Apple's ProRes encoder | CPU (software on a plain M1) | in 7b; this sets 7's pace |
| | **All of it** | | | **41 s** (before this work: 120 s) |

- **With `--format mp4`,** step 7d is `libx264` 4:4:4 on the CPU. That's the Mac's slowest output: 1.2 frames/s on a fully drawn game, against ProRes's 4. A Mac has no hardware H.264 4:4:4 encoder.
- **Without Blender,** `librashader-cli` (Metal) draws the CRT, one process per frame: 58 s for step 7.

## Linux (Lenovo Legion Y720: i7-7700HQ, GTX 1060 6 GB, NVIDIA driver 580)

| # | Step | Software | Runs on | Time |
|---|---|---|---|---|
| 1 | Play the replay and record it | Headless mainline Slippi Dolphin, Vulkan; Gecko codes | CPU (emulation), GPU (drawing; the GTX 1060 with `VK_DRIVER_FILES`, else the Intel GPU), CPU (FFV1 recording) | 8 s, together with step 2 (1.3–1.5× real time) |
| 2 | Solve the transparency, while Dolphin records | ffmpeg 8.1 (BtbN's build) filters; `prores_aw` | CPU | (in step 1) |
| 3 | Check the recording | ffmpeg (decoding) | CPU | 7 s |
| 4 | Export the game's camera | Inside Dolphin | CPU | none extra |
| 5 | The logo through the game's camera | Blender 5.2, EEVEE (OpenGL backend, its own choice), 2 processes, 16 samples, no shadows | GPU (GTX 1060), CPU (scene, PNG writing) | 17 s |
| 6 | Composite | ffmpeg, lossless FFV1 | CPU | 2 s |
| 7a | Squeeze to 584×480 | ffmpeg | CPU | in 7b |
| 7b | CRT Royale at 3504×2880 | Blender's GPU module, OpenGL | GPU (GTX 1060) | 27–28 s for `.mov`, 16–17 s for `.mp4`, steps 7a–7d together |
| 7c | The alpha, scaled up and merged (`.mov`), or written as `NAME matte.mp4` | ffmpeg; for the matte NVENC | CPU; GPU encoder | in 7b |
| 7d | Encode: ProRes 4444 `.mov`, or H.264 4:4:4 `.mp4` | `prores_aw`, or NVENC (`h264_nvenc`) | CPU, or GPU encoder | in 7b; `prores_aw` sets 7's pace (6–8 frames/s), NVENC doesn't (12–13) |
| | **All of it** | | | **60 s** `.mov`, **49 s** `.mp4` (before this work: 165 s) |

- **The first run after a change of settings** spends another 10–11 s in step 5, compiling Blender's shaders. They're kept for later runs (`~/.cache/blender`).
- **Without Blender,** `librashader-cli` (wgpu on Vulkan) draws the CRT: 119 s for step 7.

## Windows

Not run end to end yet. The headless Dolphin build compiles on GitHub Actions, but hasn't rendered on a Windows machine ([`plan-windows-remaining.md`](plan-windows-remaining.md)). So these are the steps as the code sets them up, with no times.

| # | Step | Software | Runs on | Time |
|---|---|---|---|---|
| 1 | Play the replay and record it | Headless mainline Slippi Dolphin, Direct3D 11 (`--backend D3D12` or `Vulkan` if it can't record without a window) | CPU (emulation), GPU (drawing), CPU (FFV1 recording) | not measured |
| 2 | Solve the transparency | ffmpeg 9.0 (BtbN's or Gyan's build); `prores_aw` | CPU | not measured |
| 3 | Check the recording | ffmpeg | CPU | not measured |
| 4 | Export the game's camera | Inside Dolphin | CPU | none extra |
| 5 | The logo through the game's camera | Blender 5.2, EEVEE (found in Program Files or Steam; not run on Windows yet) | GPU, CPU | not measured |
| 6 | Composite | ffmpeg | CPU | not measured |
| 7a–c | Squeeze, CRT Royale, alpha | ffmpeg; **`librashader-cli`, Direct3D 11, one process per frame**. Blender's GPU module isn't used there yet: it gets its frames through inherited pipes, which Python's `subprocess` passes on macOS and Linux only | CPU; GPU | not measured. On the Linux PC the same per-frame `librashader-cli` managed about 2 frames/s |
| 7d | Encode | `prores_aw` for `.mov`; NVENC for `.mp4` with an NVIDIA GPU whose driver the FFmpeg build supports (9.0 needs driver 610 or newer), else `libx264` | CPU, or GPU encoder | not measured |

## Which part of the computer limits each run now

| | Mac M1 | Linux PC |
|---|---|---|
| Longest step | The model, on the GPU (18 s), then the CRT's ProRes encoder, on the CPU (13–17 s) | The CRT's ProRes encoder, on the CPU (27 s); as `.mp4`, the model on the GPU (17 s) |
| Next | The render (9 s): Dolphin, the solver and the checks, all on the CPU | The render (14–16 s), on the CPU: it's a 4-core laptop CPU |
| Mostly idle | The GPU, during steps 1–3 and 6 | The GPU, during steps 1–3 and 6; NVENC unless the output is `.mp4` |
