# Linux: the whole pipeline on a PC with an NVIDIA GPU

Status: plan, November 2026. Most of it isn't implemented yet; step 6's code is (section 9.1: the CRT, in `tools/crt`, checked on the Mac and in Docker). It builds on [`plan-linux.md`](plan-linux.md), which is implemented (`427c950`) and runs on the PC in section 2. The measurements were made on that PC in November 2026, with the GTX 1060 still on the nouveau driver. Section 5 repeats them on NVIDIA's driver. The scripts behind them are in [`research/linux-gpu/`](../research/linux-gpu/README.md).

Evidence tags:

- **[verified]**: measured on the PC or on this Mac, or read in source, during this investigation.
- **[reported]**: found in documentation, specifications or bug reports; not re-checked by hand.
- **[estimate]**: needs a measurement.
- **[to test]**: needs an experiment before we rely on it.

---

## 1. Summary

- **Goal.** On a Linux PC with an NVIDIA GPU, `slp2video` runs every step it runs on the Mac: the render, the camera export, a model in Blender, the composite and the CRT. It starts from a terminal, a script or an SSH command, and each step runs on the hardware that's fastest for it.
- **What already works on the PC** [verified]:
  - `slp2alpha render`, with and without `--export-camera`. The camera export is byte-identical to the Mac's.
  - All the camera checks, and the render tests: 38 pass, and 1 is skipped (`--format hevc`, which needs Apple's encoder).
  - Blender 5.2.3 renders the logo plate, still and through the moving camera, and the camera import check passes.
- **What's missing** [verified]:
  - The CRT on the PC: `librashader-cli` isn't installed there yet. The renderer and the shaders it needs are now in this repo (`tools/crt`, section 9.1), and choose Vulkan on Linux.
  - A full `slp2video` run. The composite and the CRT haven't run on the PC yet.
- **What limits each step today** (section 3):
  - **Blender** is limited by the GPU, and the GTX 1060 runs at a fraction of its speed: nouveau can't raise its clocks. NVIDIA's driver is installed and loads at the next reboot [verified].
  - **Dolphin** draws on the Intel GPU by default. On the GTX 1060 it's half as fast again, even at nouveau's clocks: 71 game fps against 47 [verified].
  - **The checks and the solver** are limited by the CPU. In a streamed render, the solver's two ProRes encoders take more CPU than everything else together. At `--scale 3`, the checks after Dolphin take almost three times Dolphin's CPU [verified: per-thread CPU].
  - **The CRT** is limited by starting `librashader-cli` for every frame, then by the ProRes encoder [verified on the Mac; to test on the PC].
- **Findings that change the plan** [verified on the PC]:
  - **The solver's ProRes encoder holds renders back.** With FFmpeg's other ProRes encoder, `prores_aw`, in its place, a streamed render of 40 s of a game at `--scale 1` took 56 s instead of 83: 0.72× real time instead of 0.48×. The solver's CPU time fell from 350 s to 113 s.
  - `prores_aw` is 2.2 times as fast as `prores_ks` at 640×528, and 3.9 times at the CRT's 3504×2880, with the alpha within 1/255.
  - FFmpeg's new Vulkan ProRes encoder, `prores_ks_vulkan`, is slower than `prores_ks` on the Intel GPU, gets the colours wrong, and writes files that don't decode at 3504×2880. There's no usable ProRes encoder on the GPU.
  - NVENC in the PC's FFmpeg 9.0 build needs NVIDIA's driver 610 or newer, which GTX 10-series cards will never get. BtbN's FFmpeg 8.1 build needs only 570.
- **The plan, in order** (section 14):
  1. Reboot into NVIDIA's driver, and check that each program can use the GTX 1060 (section 4).
  2. Repeat the measurements (section 5).
  3. Encoders: `prores_aw` for ProRes, and NVENC for H.264 through FFmpeg 8.1 (section 6).
  4. Cheaper checks after Dolphin (section 7).
  5. One `--gpu` option that puts every step on the chosen GPU (section 8).
  6. The CRT on Linux: one `librashader-cli` run per frame, through wgpu on Vulkan (the code is done; it needs a run on the PC). Then a renderer that stays running for the whole video (section 9).
  7. Overlapping the CPU-bound and GPU-bound steps when rendering several replays (section 10).
  8. Running it all from scripts and over SSH (section 11).
- **Effort.** About 5.5–7 days. Steps 1–6, without the renderer that stays running, take about 3. Steps 3 and 4 don't need the GPU or the reboot, so they can come first; they also speed up Windows, and step 4 the Mac.

## 2. The PC

| | |
|---|---|
| Machine | Lenovo Legion Y720-15IKB laptop, on mains power with its lid closed [verified] |
| System | Pop!_OS 24.04, kernel 7.0.11, COSMIC desktop, Mesa 26.1.6 [verified] |
| CPU | Intel Core i7-7700HQ: 4 cores, 8 threads, 2.8–3.8 GHz [verified] |
| Memory | 15 GB [verified] |
| GPUs | Intel HD Graphics 630, which drives the built-in screen [verified]. NVIDIA GeForce GTX 1060 Mobile (GP106, PCI ID `10de:1c20`) [verified], with 6 GB [reported: the laptop's specification] |
| Disk | 512 GB SATA SSD, 66 GB free [verified] |
| Also running | 23 home-service containers. None uses the NVIDIA GPU. Jellyfin has `/dev/dri`, with hardware transcoding off [verified] |

What's installed for this project [verified]:

- The Dolphin package from the Docker build, in `packages/slippi-playback-mainline/`.
- The solver's FFmpeg: BtbN's static 9.0 build, in `packages/ffmpeg/`. It has NVENC (`h264_nvenc`, `hevc_nvenc`), but too new for this GPU's driver (6.3). It also has the Vulkan encoders and filters, and the OpenCL and CUDA filters.
- Blender 5.2.3, in `~/.local/opt`, run as `~/.local/bin/blender`.
- The logo project, in `~/Documents/logo_metal_fracture` (90 MB, without its renders).
- NVIDIA's driver 580.178.04, installed on 18 November and waiting for a reboot (section 4).

## 3. What limits each step

### 3.1 Overview

| Step | Runs on | What limits it on the PC | What the GPU can do |
|---|---|---|---|
| Dolphin: emulation | One CPU thread (replays play single-core) | Not the limit: busy a quarter to a half of the time (3.2) [verified] | Nothing |
| Dolphin: drawing | The GPU, through Vulkan; the Intel GPU by default [verified] | Partly, even at `--scale 1`: 71 game fps on the GTX 1060 (NVK, at nouveau's clocks), 47 on the Intel GPU [verified]. [to test] at `--scale 3` | The GTX 1060, through `--gpu` (section 8) |
| Dolphin: recording | FFV1 on 4 CPU threads | 54 of Dolphin's 66 CPU seconds at `--scale 3` [verified] | Not without changing Dolphin (section 12) |
| Checks after Dolphin | ffmpeg, on the CPU | 185 CPU seconds at `--scale 3`, almost three times Dolphin's 66 [verified] | No; they can be made cheaper (section 7) |
| Solver | ffmpeg's filters and two `prores_ks` encoders, on the CPU | On a whole game, the encoders: they took at least two thirds of the solver's CPU (3.2) [verified]. 395 CPU seconds at `--scale 3` on the 300-frame clip [verified] | No usable ProRes encoder on the GPU (6.2); `prores_aw` instead |
| Camera export | Inside Dolphin | Negligible | Nothing |
| Blender | EEVEE, on the GTX 1060 through OpenGL | The GPU, at nouveau's clocks [verified] | NVIDIA's driver, about twice as fast [estimate] |
| Composite | ffmpeg's `overlay` and `prores_ks` or `libx264`, on the CPU | The encoder [estimate] | NVENC for `.mp4` |
| CRT | `librashader-cli` once per frame (`tools/crt`): Metal on macOS, Vulkan on Linux; BMP files | Starting a process for each frame [verified on the Mac]; then the encoder: `prores_ks` writes 3.7 frames/s at 3504×2880 [verified] | One process for all frames; NVENC for `.mp4` |

### 3.2 Where the CPU goes in a render

A 300-frame clip (frames 1500–1799 of `DishonestMuddyCoyote.slp`, characters only, Vulkan on the Intel GPU), with each process's and thread's CPU time read from `/proc` (`cpu_profile.sh`) [verified]:

| | `--scale 1` | `--scale 3` |
|---|---|---|
| Total time | 29 s | 119 s |
| Dolphin | 17 s, reaching 42 game fps | 31 s, 13 game fps |
| Checks and solve, after Dolphin | 13 s | 88 s |
| Dolphin, CPU | 20 s, of which the emulation thread 7.6 s and the recording 7.7 s | 66 s, of which the emulation thread 7.8 s and the recording 54 s |
| Pairing check (two passes), CPU | 15 s | 152 s |
| Brightness check, CPU | 4.5 s | 33 s |
| Solver, CPU | 41 s | 395 s |

- **This clip doesn't stream.** The solver starts during Dolphin's run once 330 frames are recorded (`STREAM_LEAD_FRAMES`) [verified: `__main__.py`], more than this clip has. So here it runs after Dolphin, and the summary's "then checks" includes it. A whole game streams.
- **Dolphin waits.** Its emulation thread is busy less than half the time at `--scale 1`, and a quarter at `--scale 3` [verified].
  - At `--scale 1` it probably waits for each frame to come back from the GPU [estimate]. That fits the GTX 1060 making it half as fast again, even at nouveau's clocks [verified: 71 game fps against 47, in `gpu_check.sh`].
  - At `--scale 3` it may also wait for the recording threads. They need about 90 ms of CPU per field [verified: 54 s for 600 fields], and 4 threads share it.
- **At `--scale 3`, the work after Dolphin is three times Dolphin's.**
  - The checks decode the recording three times at full size [verified: `validate.quick_check`].
  - The solver encodes two ProRes 4444 videos at 1920×1584. From the encoder measurements in 6.2, the encoders account for most of its 395 CPU seconds [estimate].
- **For a whole game, the checks cost the same,** since they read at most the first 1200 fields [verified: `validate.quick_check`]. But the pairing check then runs twice on the same frames: once while Dolphin records, to start the streaming solve, and again afterwards [verified: `__main__.py:305, 334`].
- **In a streamed render, the solver's encoders hold everything back.** 40 s of the same game at `--scale 1`, streamed as whole games are, with Vulkan on the GTX 1060 (`solver_encoder.sh`) [verified]:

  | | `prores_ks` (today) | `prores_aw` swapped in |
  |---|---|---|
  | Time | 83 s: 0.48× real time | 56 s: 0.72× real time |
  | Solver, CPU | 350 s: 4.2 cores busy on average | 113 s: 2.0 cores |
  | Dolphin, CPU | 132 s | 97 s |

  - With `prores_ks`, the solver and Dolphin together keep about 6 of the CPU's 8 threads busy, on its 4 cores. Dolphin then runs at 31 game fps, against 71 on its own [verified].
  - The render tests' whole games run at 0.5× real time [verified], the same as here with `prores_ks`.

### 3.3 Blender

The logo plate over 40 frames of the camera export, one Blender process (`sample_sweep.sh`) [verified]:

| Seconds per frame | 1 sample | 16 samples | 64 samples |
|---|---|---|---|
| Mac M1 | 0.075 | 0.228 | 0.743 |
| GTX 1060, nouveau | 0.110 | 0.448 | 1.514 |
| Intel HD 630 | 0.275 | 0.803 | 2.511 |

- **The GPU is the limit.** The time grows with the samples, and Blender uses about half a CPU core [verified]. On the 300-frame plate with 2 Blender processes and 16 samples, the moving camera's settings: Mac 52 s, GTX 1060 123 s, Intel GPU 200 s [verified].
- **With NVIDIA's driver:**
  - At full clocks, the GTX 1060 has about 1.6 times the M1's compute and 2.8 times its memory bandwidth [reported: specifications]. So expect at least the M1's speed.
  - That's 0.15–0.25 s per frame at 16 samples, and 45–70 s for the 300-frame plate [estimate].
- **What isn't GPU work:** most of the 1-sample time. For each frame, Blender updates the scene and writes a 16-bit PNG [estimate].

## 4. Step 1: NVIDIA's driver

**Where it stands** [verified]:

- `nvidia-driver-580` (580.178.04) was installed on 18 November.
- Its kernel module is built for the running kernel (DKMS), nouveau is blacklisted, and the initramfs was rebuilt.
- Secure Boot is off, so the unsigned module will load.
- The PC is waiting for a reboot (`/var/run/reboot-required`).
- 580 is the last driver branch for GTX 10-series cards. 595 dropped them, so don't install `system76-driver-nvidia`, which brings it in [reported].

**What the reboot changes:**

- The GTX 1060 runs at full clocks. Its Vulkan, OpenGL, CUDA and NVENC come from NVIDIA's driver, and Mesa's drivers for it (NVK, and nouveau's OpenGL) stop working.
- The Intel GPU keeps the screen, and is still available through Mesa.
- The device numbers under `/dev/dri` may change [to test]. Nothing depends on them: Jellyfin gets the whole folder [verified].
- The graphics mode stays as system76-power has it: `nvidia`, which keeps the GTX 1060 powered [verified: `system76-power graphics`].
  - `hybrid` would let it sleep when idle, but then each program has to ask for it (section 8).
  - Try `hybrid` later [to test].

**Checks after the reboot** (`gpu_check.sh`, Appendix A):

1. `nvidia-smi` names the card and the driver.
2. `vulkaninfo --summary` lists the GTX 1060 from NVIDIA's driver, the Intel GPU, and llvmpipe.
3. Blender names NVIDIA as its OpenGL renderer, and renders the probe scene.
4. ffmpeg opens NVENC, and a Vulkan device on the GTX 1060.
5. Dolphin renders the 5 s clip with Vulkan on each GPU, and with OpenGL. Each camera export matches the Mac's.

**Heat.** The laptop runs with its lid closed [verified]. Watch the GPU during the first long render, with `nvidia-smi --query-gpu=temperature.gpu,clocks.sm,power.draw --format=csv -l 5` [to test].

**If the desktop doesn't start** with the new driver:

- Docker, Tailscale and SSH over Tailscale are system services, and start without it [verified: enabled].
- Removing the driver package and rebooting brings nouveau back [reported].

## 5. Step 2: measure again

The same scripts, before and after the driver:

| Measurement | Today | Question |
|---|---|---|
| Blender, 1/16/64 samples (`sample_sweep.sh`) | 3.3 | How much faster with the driver? Is Blender's OpenGL or Vulkan backend faster? |
| Blender, the 300-frame plate | 123 s | Are 1, 2 or 3 Blender processes fastest? |
| Dolphin, the 5 s clip at `--scale 1` and `3`, on each GPU (`gpu_check.sh`, `cpu_profile.sh`) | 3.2; at `--scale 1`, 47 game fps on the Intel GPU and 71 on the GTX 1060 | How much faster on NVIDIA's driver? Does the GTX 1060 speed up `--scale 3`? |
| 40 s of a game, streamed (`solver_encoder.sh`) | 0.48× real time with `prores_ks`, 0.72× with `prores_aw` | How much faster on NVIDIA's driver? |
| ProRes encoders (`prores_test.sh`) | 6.2 | Does `prores_ks_vulkan` work on NVIDIA? |
| NVENC H.264 4:4:4 at 3504×2880, with BtbN's FFmpeg 8.1 | — | Its speed, and its quality against `libx264` |
| The CRT: one frame with `librashader-cli -r vulkan` | — | Time per frame on each GPU (after 9.1) |

These decide:

- which GPU Dolphin uses by default (section 8);
- whether Blender's Vulkan backend becomes the default on Linux;
- whether `prores_ks_vulkan` deserves another look.

## 6. Step 3: encoders

### 6.1 What encodes what today

| Output | On macOS | On Linux and Windows |
|---|---|---|
| Dolphin's recording | FFV1, inside Dolphin | The same |
| The solver's `fullTransparent` and `alphaMap` (`--format mov`) | `prores_videotoolbox` | `prores_ks` |
| The composite, `.mov` | `prores_videotoolbox`, else `prores_ks` | `prores_ks` |
| The composite, `.mp4` | `libx264`, 4:2:0, CRF 16 | The same |
| The CRT, `.mov` | `prores_videotoolbox`: 10 times `prores_ks`'s speed at this size | `prores_ks` |
| The CRT, `.mp4` | `libx264`, 4:4:4, CRF 12 | The same |

[verified: `solve.py`, `composite.py`, `slp2video.py`]

### 6.2 ProRes 4444 with alpha

Measured on the PC, from a real transparent render, with all 8 threads (`prores_test.sh`) [verified]:

| | 640×528, frames/s | 3504×2880, frames/s | Against the source, 640×528 |
|---|---|---|---|
| `prores_ks` (used today) | 86.5 | 3.7 | 77.8 dB |
| `prores_aw` | 186 | 14.3 | 66.8 dB; the alpha within 1/255 of `prores_ks`'s |
| `prores_ks_vulkan`, on the Intel GPU | 27.2 | 1.2 | 19.4 dB: wrong colours |

- **`prores_aw` is 2.2 to 3.9 times as fast,** with files about 15% smaller [verified].
  - In the solver, it takes 40 s of a game at `--scale 1` from 0.48× real time to 0.72× (3.2) [verified].
  - Its 66.8 dB is still far beyond what anyone can see, and its alpha matches `prores_ks`'s within 1/255 [verified].
  - It needs the profile as a number, `-profile:v 4`; it refuses `4444` [verified].
  - FFmpeg has a report of it failing on large frames with alpha (ticket 11536) [reported]. At 3504×2880 it worked, and its output decoded [verified].
  - **Use it on Linux and Windows wherever `prores_ks` is used now,** with `prores_ks` as the fallback.
  - Check that its files open with transparency in DaVinci Resolve, Premiere and Final Cut [to test].
- **`prores_ks_vulkan` isn't usable.**
  - It came with FFmpeg 8.1, from a 2025 Google Summer of Code project [reported: the Khronos blog].
  - On the Intel GPU its colours are wrong, and its 3504×2880 files don't decode ("slice out of bounds") [verified]. Others report malformed output too [reported].
  - Try it once on NVIDIA (step 2), but don't plan on it.
- **There's no other GPU path.** NVENC has no ProRes and no alpha [reported], and Apple's encoder is macOS-only.

### 6.3 NVENC for H.264 and HEVC

- **The GTX 1060's encoder** [reported: NVIDIA's support matrix]:
  - H.264 and HEVC, including 4:4:4 and lossless.
  - H.264 up to 4096×4096, so the CRT's 3504×2880 fits. HEVC up to 8192×8192, without B-frames.
- **Which FFmpeg.** NVENC isn't in FFmpeg itself: FFmpeg loads NVIDIA's library and asks for an API version.
  - BtbN's 9.0 build, the one in `packages/ffmpeg/`, asks for version 13.1, which needs driver 610 or newer. With driver 580's library it stops: "Driver does not support the required nvenc API version. Required: 13.1 Found: 13.0" [verified].
  - GTX 10-series cards stay on 580 (section 4), so that build's NVENC will never work on this PC.
  - BtbN's 8.1 build uses the 13.0 headers, which need driver 570 or newer [verified: their `scripts.d/50-ffnvcodec.sh`]. It's in the same release as the 9.0 build: `ffmpeg-n8.1.3-27-g8dca1586f4-linux64-gpl-8.1.tar.xz`, SHA-256 `41e9c565594c390622cf968d82fa4135d9e9a11d06c1515644288cbc844e3380` [verified: the release listing].
  - So either the 8.1 build becomes the PC's FFmpeg, after a run of the render tests with it, or it's kept beside the 9.0 build for the NVENC encodes only [to test].
- **What it's for:** the `.mp4` outputs.
  - The composite, in 4:2:0.
  - The CRT, in 4:4:4, which keeps the phosphor stripes sharp. That's where `libx264` is slowest.
- **What to test,** against `libx264` at the same file size, with SSIM [to test]:
  - `-c:v h264_nvenc -preset p7 -tune hq -rc vbr -cq 16 -b:v 0`;
  - for the CRT, also `-profile:v high444p -pix_fmt yuv444p`;
  - its speed in 4:4:4 at 3504×2880.
- **The fallback.** Try the encoder on one frame first, and use `libx264` if it fails. `render_video.video_encoder` (`tools/crt`) already does that for Apple's ProRes encoder [verified].
- **Limits.** Consumer cards run only a few encodes at once (8 with current drivers) [reported]. One render needs at most two.

### 6.4 Where the changes go

- **`solve.ACCELERATED`** holds one faster encoder per format [verified]. It becomes an ordered list per platform: `prores_videotoolbox` on macOS, `prores_aw` elsewhere, then `prores_ks`. The composite already takes its encoders from `solve.encoder_choices` [verified], so it follows.
- **`render_video.video_encoder`** (`tools/crt`), which encodes the CRT, gets the same order for `.mov`, and NVENC before `libx264` for `.mp4`. So does `composite.H264`.
- **Nothing else changes.** The output names stay the same. Run the render tests with each encoder: they check the solver's transparency.

## 7. Step 4: cheaper checks after Dolphin

This isn't GPU work, but on the PC it's the largest single cost at `--scale 3` (3.2). The checks run on every platform, so the Mac gains too.

- **Decode once.** The two pairing passes and the brightness series each decode the recording again [verified: `validate.py`]. One ffmpeg run with three branches can measure all three.
- **Sample the picture down first** at `--scale` 2 to 4.
  - `pair_violations` compares every pixel of 600 fields at full size [verified].
  - Taking every third pixel in each direction at `--scale 3` (`scale=iw/3:ih/3:flags=neighbor`) keeps each sampled pixel's exact value. So it measures the same share of pixels that break the pairing, from a ninth of them [estimate: the same decisions].
  - `luma_series` already scales the picture down by 4 [verified].
- **Don't detect the pairing twice.** When the streaming solve has already detected it, `quick_check` can reuse that result instead of decoding the same frames again [verified: both use the first `PAIRING_PAIRS` pairs].
- **Check** that the render tests, and a few renders at `--scale 3` and `4`, find the same pairing and give the same warnings as before.
- **Expected:**
  - At `--scale 3`, the checks from 185 CPU seconds to about 30–40. The single decode is most of what's left: about 40 ms of CPU per field at 1920×1584 [estimate: 92 s of FFV1 decoding over four passes].
  - With `prores_aw` in the solver too, the 300-frame clip at `--scale 3` from 119 s to about 60 s [estimate].

## 8. Step 5: one `--gpu` option

How each program picks its GPU [verified on the PC unless marked]:

| Program | API | The GTX 1060 | The Intel GPU |
|---|---|---|---|
| Dolphin | Vulkan | `MESA_VK_DEVICE_SELECT=10de:1c20` with `MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE=1` (Mesa's device-select layer). With NVK: 71 game fps against the default's 47 [verified]. With NVIDIA's driver [to test]. Or `[Hardware] Adapter` in `GFX.ini` | `MESA_VK_DEVICE_SELECT=8086:591b`. The default today [verified] |
| Dolphin | OpenGL (EGL) | `__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json` [reported: libglvnd] | `DRI_PRIME=pci-0000_00_02_0` [verified], with Mesa's vendor file |
| Blender | OpenGL, its default | It takes the first EGL device: today nouveau's, even with only Mesa's vendor file [verified]. NVIDIA's vendor file comes first [verified: `10_nvidia.json`], so after the reboot probably the GTX 1060 [to test] | `DRI_PRIME=pci-0000_00_02_0` [verified] |
| Blender | Vulkan (`--gpu-backend vulkan`) | Picks the discrete GPU itself, even when told otherwise [verified with NVK] | `VK_DRIVER_FILES=/usr/share/vulkan/icd.d/intel_icd.json` [reported] |
| `librashader-cli` | wgpu, on Vulkan (its own Vulkan runtime ignores the output size, 9.1) | No device option [verified: its help]. wgpu picks its adapter itself; whether the Vulkan variables above steer it is [to test] | The same |
| ffmpeg | Vulkan | `-init_hw_device vulkan=vk:NVIDIA`, a part of the device's name [verified] | `vulkan=vk:Intel` [verified] |
| ffmpeg | NVENC | The only NVIDIA GPU; needs the FFmpeg 8.1 build (6.3) | — |

The option:

- **`--gpu auto|nvidia|intel|amd|N`** on `slp2alpha render`, `plate.py` and `slp2video`. `auto` is the discrete GPU when its driver is loaded, else the system's default.
- **Finding the GPUs.** `/sys/class/drm/renderD*/device` gives each one's vendor, device, PCI slot and kernel driver (`nvidia`, `i915`, `nouveau`, `amdgpu`). No extra tools are needed.
- **Where it goes.** A small module, for example `slp2alpha/gpu.py`, turns the choice into each API's environment variables.
  - `runner.run_dolphin` already takes `extra_env` [verified].
  - `plate.run_blender` needs an `env` argument.
- **Each step names the GPU it used.**
  - Blender's plate report can include `gpu.platform.renderer_get()`.
  - Dolphin's logs don't name its Vulkan device [verified: not in the logs of `gpu_check.sh`'s renders]. slp2alpha can print the one it asked for.
- **Other platforms.** On macOS there's one GPU, so `--gpu` does nothing. On Windows it can set `[Hardware] Adapter` later.

## 9. Step 6: the CRT on Linux

### 9.1 As on the Mac: one `librashader-cli` run per frame

Done on the Mac and in Docker, November 2026; what's left needs the PC.

1. **The CRT is in this repo now**, [`tools/crt`](../tools/crt/README.md) [verified]:
   - `render_video.py`, the crt-royale project's script with the same options and settings. On the Mac it gives the original's frames exactly.
   - The 38 shader files the preset needs (libretro's slang-shaders at `2345ee91`), unmodified, with a manifest of their git blob ids. So the PC doesn't need the crt-royale project.
2. **Building `librashader-cli` 0.12.1:** `python3 tools/crt/install_librashader.py`, into `packages/librashader/`.
   - The command planned here, `--no-default-features --features vulkan`, doesn't compile: librashader-cli's `main.rs` imports `librashader::reflect::naga`, which only the wgpu feature turns on [verified: Ubuntu 22.04, Rust 1.88]. So Linux builds `wgpu,vulkan`: 4.5 minutes in Docker on the M1, with `build-essential` only (no X11 packages) [verified].
   - Rust 1.88, the `asv-linux` image's, is new enough [verified].
   - The program loads `libvulkan.so.1` itself when it runs [verified: it runs with only `libvulkan1` and a driver installed].
3. **The runtime.** `render_video.py --runtime auto` uses Metal on macOS and **wgpu**, on Vulkan, on Linux [verified]:
   - librashader-cli's own Vulkan runtime draws at the input's size, whatever `-d` asks: 640x480 instead of 3840x2880. Its viewport and read-back are sized from the input image (`src/render/vk/mod.rs`) [verified in Docker].
   - wgpu draws at the right size. On lavapipe its frames are on average 1.0/255 from the Mac's Metal frames (at most 36) [verified].
   - `render_video.py` checks every frame's size, so a runtime that gets it wrong is skipped, or stops the render.
   - `tools/crt/linux.Dockerfile` builds and tests all of it on lavapipe; `test_crt.py` includes a real render [verified].
4. **On the PC** [to test]:
   - `install_librashader.py`, then `test_crt.py`;
   - one clip with `slp2video --crt`, on each GPU. wgpu picks its own adapter; whether the Vulkan variables of section 8 steer it is [to test];
   - the time per frame, and the best `--crt-jobs` on 8 threads (it's 4 by default).
5. **Use the faster encoders:** `prores_aw` for `.mov`, 3.9 times `prores_ks`'s speed at this size [verified], and NVENC for `.mp4` (6.3). Both go in `render_video.video_encoder`.

### 9.2 A renderer that stays running

- **Why.**
  - On the Mac a frame takes 0.52 s at 3504×2880, and 0.42 s at 584×480 [verified]. So most of each frame's time is spent starting `librashader-cli` and loading the preset, not drawing.
  - Each frame is also written as a 40 MB BMP, which ffmpeg reads back before it's deleted [verified: `tools/crt/render_video.py`].
- **How.** One process loads the preset once:
  1. ffmpeg decodes the composite, and pipes raw frames to the process.
  2. The process draws each frame with librashader's Vulkan runtime, and reads it back.
  3. It pipes the result to the ffmpeg that encodes the video.
- **Details:**
  - It passes each frame's number to the shader, as `librashader-cli --frame` does.
  - It reads one frame back while the next one draws.
  - It takes `render_video.Settings`: the mask, the triad size, the aspect and any extra parameters.
  - Alpha works as in `render_video.py`: the encoding ffmpeg scales up the input's alpha and merges it back (`alphaextract`, `alphamerge`).
  - It sizes its viewport and read-back from the output, which `librashader-cli`'s Vulkan runtime doesn't (9.1).
- **Language and place.**
  - Rust, with the `librashader` crate (its `runtime-vk` feature) and `ash`, built like `librashader-cli` [estimate: 300–500 lines].
  - In this repo, next to `tools/crt`, which would call it in place of `librashader-cli`.
  - With librashader's Metal runtime, the same program would speed up the Mac too [estimate].
- **Check:** its frames against `librashader-cli`'s, for each mask, with and without alpha. They should be identical, or within 1/255.
- **Expected speed.**
  - Drawing and reading back each 40 MB frame takes a few tens of milliseconds on the GTX 1060 [estimate].
  - The encoder then sets the pace: about 14 frames/s with `prores_aw` [verified: the encoder on its own], and NVENC faster [to test].

## 10. Step 7: overlapping replays

- **Two kinds of step.** Blender is limited by the GPU, and uses about half a CPU core [verified]. The checks and the solver use only the CPU, and Dolphin mostly the CPU [verified at `--scale 1`].
- **So run them at the same time.** When several replays get a model, the next replay's `slp2alpha render` can run while Blender draws the previous replay's model. The total then tends towards the longer of the two steps, instead of their sum [estimate].
- **For example,** `slp2video.py A.slp B.slp C.slp`, with two workers one replay apart:
  1. the render and the camera export;
  2. the model, the composite and the CRT.
- **Sharing the GTX 1060.** If both want it, Dolphin can use the Intel GPU (`--gpu intel`), but it runs a third slower there [verified: 47 game fps against 71]. Which is faster overall is [to test].

## 11. Step 8: running it from scripts and over SSH

- **Commands.** `slp2video.py` and `slp2alpha render` run without a window. From the Mac: `ssh 100.97.182.94 'bash -lc "..."'` [verified].
  - `bash -lc` puts `~/.local/bin`, where Blender is, on the PATH. A plain SSH command doesn't [verified].
  - Better: let `plate.find_blender` also look in `~/.local/bin`.
  - The PC's Slippi Launcher has no ISO set, so pass `--iso`, or set `SLP2ALPHA_ISO` [verified].
- **Long renders.** Start them as user services, so a dropped SSH connection doesn't stop them: `systemd-run --user --unit asv-NAME --same-dir ...`. Follow one with `journalctl --user -u asv-NAME -f`. tmux isn't installed [verified].
  - User services keep running after logging out only with lingering on: `sudo loginctl enable-linger zubair` [reported]. It's off today [verified].
- **Sharing the machine with the home services.**
  - Start renders with `nice -n 10`, so the services stay responsive. No container uses the GTX 1060 [verified].
  - Jellyfin transcodes on the CPU, with hardware acceleration off [verified]. Giving it the Intel GPU's encoder would keep its transcodes from slowing renders. That's a Jellyfin setting, outside this repo [to test].
  - `system76-power profile performance` may speed up the CPU-bound steps [to test]. The profile is `Balanced` today [verified].
- **A wrapper script,** for example `tools/linux/asv-render`: it sets the ISO, `--gpu` and `nice`, starts the user service, and prints where the video will be.

## 12. Not in this plan

- **Dolphin's recording on the GPU.** FFmpeg 8.1 has an FFV1 encoder on Vulkan (`ffv1_vulkan`) [reported]. But Dolphin's FFmpeg would need Vulkan, and Dolphin a patch to hand it frames on the GPU. That's worth it only if step 2 shows the recording holding back `--scale 3` on the GTX 1060.
- **The solver on the GPU,** for example as an OpenCL kernel through ffmpeg's `program_opencl`. The encoders cost more than its filters [estimate], and `prores_aw` is the cheaper fix.
- **Dual core** (`CPUThread`). It might stop Dolphin from waiting, but replays play single-core [verified: the playback codes]. It would need its own test that the camera export still matches.
- **Cycles and CUDA.** The logo is made for EEVEE, which draws through OpenGL or Vulkan. Cycles would take far longer per frame [estimate].
- AMD GPUs, Windows' GPUs, and GPUs inside Docker.

## 13. Risks

| Risk | Mitigation |
|---|---|
| The desktop doesn't start on NVIDIA's driver | Rendering, Docker and SSH don't need it [verified]. Removing the driver goes back to nouveau |
| A program picks the other GPU | `--gpu`, and each step names its GPU |
| Headless OpenGL (EGL) doesn't work for Dolphin on NVIDIA's driver | Vulkan is the default; OpenGL is only the fallback [to test] |
| `prores_aw`'s files don't open with transparency in some program | `prores_ks` stays as the fallback, with an option to choose it |
| NVENC looks worse than `libx264` at the same size | Compare first (6.3). If so, `libx264` stays the default for `.mp4` |
| The solver behaves differently with FFmpeg 8.1, needed for NVENC | Run the render tests with it first, or keep it for the NVENC encodes only (6.3) |
| The GTX 1060 gets too hot with the lid closed | Watch `nvidia-smi`. Open the lid, or lower its power limit (`nvidia-smi -pl`) [to test] |
| 6 GB of video memory isn't enough for two Blender processes, the CRT at 3504×2880 and Dolphin at `--scale 4` at once | Measure the peak in step 2. Use one Blender process while the CRT runs [to test] |
| Driver 580 is the last branch for this GPU | It still gets fixes [reported], and nothing here needs a newer one |

## 14. Effort and order of work

| # | Step | Effort | Where |
|---|---|---|---|
| G1 | Reboot, then run `gpu_check.sh` (section 4) | 0.1 day | The PC; the reboot needs its owner |
| G2 | Measure again (section 5) | 0.5 day | The PC |
| G3 | `prores_aw`, and NVENC for `.mp4` (section 6) | 0.5 day | Anywhere; NVENC on the PC |
| G4 | Cheaper checks (section 7) | 0.5 day | Anywhere |
| G5 | `--gpu` (section 8) | 0.5–1 day | The PC |
| G6 | The CRT, one run per frame (9.1): code done, `tools/crt`; on the PC, the install, the tests and a clip on each GPU | 0.25 day | The PC |
| G7 | The CRT renderer that stays running (9.2) | 1.5–2 days | The PC; the Mac for Metal |
| G8 | Overlapping replays (section 10) | 1 day | Anywhere |
| G9 | Scripts and SSH (section 11) | 0.25 day | The PC |
| G10 | Docs: `slp2video.md`, a Linux quick start in the README, `plan-linux.md`'s results, this plan's status | 0.25 day | Anywhere |
| **Total** | | **5.5–7 days** (G1–G6: about 3) | |

---

## Appendix A: checks after the reboot

`research/linux-gpu/gpu_check.sh` runs these and prints a line for each:

```sh
nvidia-smi --query-gpu=name,driver_version,memory.total,clocks.max.sm,temperature.gpu,pstate --format=csv
vulkaninfo --summary | grep -E 'deviceName|deviceType|driverName'
env -u DISPLAY -u WAYLAND_DISPLAY eglinfo -B | grep -E 'platform:$|OpenGL core profile renderer'
blender -b --factory-startup --python research/linux-gpu/eevee_probe.py -- 3 /tmp/probe   # and with each EGL vendor file, and Vulkan
ffmpeg -f lavfi -i testsrc2=s=1280x720 -frames:v 120 -c:v h264_nvenc -f null -              # and in 4:4:4; FFmpeg 8.1 (6.3)
ffmpeg -v verbose -init_hw_device vulkan=vk:NVIDIA -f lavfi -i testsrc2 -frames:v 1 -filter_hw_device vk -vf format=yuv420p,hwupload,hwdownload,format=yuv420p -f null -
```

Then Dolphin renders frames 1500–1799 of `DishonestMuddyCoyote.slp` with `--export-camera`, with Vulkan on each GPU and with OpenGL. Each camera export is compared with the Mac's:

```sh
python3 tools/camera-export/validate_camera.py compare \
  tools/camera-export/reference/DishonestMuddyCoyote_1500-1799_characters-only_macos.json "OUT/camera - ....json"
```

## Appendix B: the measurement scripts

In [`research/linux-gpu/`](../research/linux-gpu/README.md):

| Script | Measures |
|---|---|
| `gpu_check.sh` | Appendix A |
| `eevee_probe.py` | Which GPU Blender draws on, and its time per frame on its startup scene |
| `sample_sweep.sh` | The logo plate on 40 frames, at 1, 16 and 64 samples (3.3) |
| `frame_times.py` | The time per frame in Blender's logs |
| `cpu_profile.sh`, `thread_sampler.py` | The CPU time of each process and thread in a render (3.2) |
| `solver_encoder.sh` | 40 s of a game, streamed, with `prores_ks` and with `prores_aw` in the solver (3.2) |
| `prores_test.sh` | The ProRes encoders' speed and quality (6.2) |

## References

- NVIDIA:
  - the Video Encode and Decode GPU Support Matrix: https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new;
  - PRIME render offload and `__VK_LAYER_NV_optimus`: the driver's README, chapter "PRIME Render Offload".
- FFmpeg:
  - the Vulkan encoders and decoders (FFV1, ProRes): https://www.khronos.org/blog/video-encoding-and-decoding-with-vulkan-compute-shaders-in-ffmpeg;
  - the ProRes Vulkan encoder's project report: https://gist.github.com/raphaelthegreat/32854d68d2d64cb330d56545e58d9c97;
  - `prores_aw` with alpha at high resolution: https://trac.ffmpeg.org/ticket/11536.
- Mesa: the device-select layer's variables (`MESA_VK_DEVICE_SELECT`), and `DRI_PRIME`: https://docs.mesa3d.org/envvars.html.
- libglvnd: `__EGL_VENDOR_LIBRARY_FILENAMES`: https://github.com/NVIDIA/libglvnd.
- librashader: https://github.com/SnowflakePowered/librashader (the `librashader-cli` crate's features, and the `runtime-vk` runtime).
- This repo: `tools/slp2alpha/slp2alpha/` (`__main__.py`, `validate.py`, `solve.py`, `runner.py`), `tools/logo-stage/` (`plate.py`, `blender_plate.py`, `composite.py`), `tools/slp2video/slp2video.py`.
