# Report: the CRT on the GPU, and the faster encoders

22 November 2026. Measurements of the work in [`plan-gpu-crt-model.md`](plan-gpu-crt-model.md) steps L1–L4:

- **L1:** `prores_aw` and NVENC as encoders, with FFmpeg 8.1 on the Linux PC;
- **L2:** CRT Royale drawn by Blender's GPU module in one process (`--runtime blender`), instead of one `librashader-cli` run per frame;
- **L3:** the matte file for transparent `.mp4`;
- **L4:** the model's EEVEE settings.

The scripts and raw results are in [`research/crt-in-blender/`](../research/crt-in-blender/README.md).

## 1. Summary

- **The CRT step is 3–4 times faster into ProRes 4444,** on both machines: 3.0–4.0× on the Linux PC, 3.8–4.4× on the Mac. Into H.264 4:4:4 it's 5.3–5.7× faster on the PC, where NVENC encodes it, and 1.5–5× on the Mac, where `libx264` sets the pace:

  | 3504×2880, frames/s | Mac M1, Blender | Mac M1, `librashader-cli` | PC, Blender | PC, `librashader-cli` | PC before L1 (`librashader-cli`, `prores_ks` / `libx264`)\* |
  |---|---|---|---|---|---|
  | Fighters only, transparent, ProRes | **19.2** | 5.1 | **8.3** | 2.1 | — |
  | Whole game, opaque, ProRes | **4.0** | 0.9 | **5.8** | 1.9 | 0.7 |
  | Fighters, H.264 4:4:4 + matte | **5.6** | 1.1 | **11.7** (NVENC) | 2.2 (NVENC) | — |
  | Whole game, H.264 4:4:4 | **1.2** | 0.8 | **12.9** (NVENC) | 2.2 (NVENC) | 1.5 |

  \* Measured on 120 frames of a 4-player clip with every pixel drawn (`research/crt-in-blender/README.md`), so comparable with the whole-game rows.

- **Blender's frames are librashader's.** On the PC, on the same GPU, they're 0.0002/255 apart on average for every mask, frame and input. On the Mac they're 0.005/255 apart. The agreed bar was 1/255.
- **The model (Blender's EEVEE) was then the slowest step,** so step L4 measured it (section 6):
  - **16 samples stay.** After the CRT, 16 samples are 0.8–0.9/255 from 64 on the logo itself, inside the bar. 8 samples are 1.2–1.3/255, outside it.
  - **Shadows go,** for the logo and the cel finish. They cost more than half of each frame on the Mac and a third on the PC, and change the logo by 0.1/255 after the CRT (the cel finish not at all).
  - **The moving camera's frames are cached,** so a rerun of the same clip skips Blender.
- **A whole `slp2video --model logo --crt` run** of 4 s of play, before this work and now:
  - PC: **165 s → 60 s** (ProRes), **49 s** as `.mp4`;
  - Mac: **120 s → 41 s**.
- **For a 3-minute game** (10,800 frames), the CRT step on the PC goes from about 4.3 hours (before L1) to 22–31 minutes in ProRes, or 14–15 minutes in `.mp4`.
- **The Mac's `.mp4` is its slowest output** (1.2 frames/s on whole-game frames). `libx264` 4:4:4 does the encoding, and there's no hardware H.264 4:4:4 encoder on a Mac. Prefer ProRes there.

## 2. What was measured

| | Mac | Linux PC |
|---|---|---|
| Machine | Mac mini, M1, macOS | Lenovo Legion Y720: i7-7700HQ (4 cores), GTX 1060 6 GB on NVIDIA's driver 580, Pop!_OS 24.04 |
| Blender | 5.2.3, Metal | 5.2.3, OpenGL (`--gpu-backend opengl`) |
| `librashader-cli` | 0.12.1, Metal | 0.12.1, wgpu on Vulkan, on the GTX 1060 (`VK_DRIVER_FILES`) |
| FFmpeg | 9.0.2 (Homebrew) | BtbN's 8.1.3 (31 October build) |
| ProRes encoder | Apple's (`prores_videotoolbox`, software on a plain M1) | `prores_aw` |
| H.264 4:4:4 encoder | `libx264`, CRF 12 | `h264_nvenc`, constant QP 12 |

- **The clip:** frames 1500–1739 (240 frames, 4 s) of the render tests' `DishonestMuddyCoyote.slp` (Battlefield, Fox vs Falco). It was recorded at the console's 640×480 (`--raw-resolution`), as `slp2video --crt` records regular Melee, in two ways:
  - **fighters:** `--characters-only`, transparent, about 94% of each frame empty;
  - **game:** `--keep-background`, every pixel drawn. This is the hardest picture for the encoders.
- **The CRT step** is `slp2video.crt_pass`: the squeeze to 584×480, CRT Royale at 3504×2880 (6 px per scanline, grille mask), and the encoder. Wall time and the CPU time of every child process were measured. Video memory is the peak `nvidia-smi` saw.
- **Accuracy:** frames 0, 120 and 239 of each input, drawn with each mask by Blender and by `librashader-cli` on the same machine, as PNG.
- **Scripts:**
  - `bench.py` for all of the above;
  - `e2e.sh` for whole `slp2video` runs;
  - `samples.sh` and `model_diff.py` for the model's samples, `eevee_sweep.py` for its other settings.

## 3. The CRT step

### 3.1 Speed

The full tables, with file sizes, are in `research/crt-in-blender/results/`.

**Mac M1**

| Input, format | Blender: s, frames/s, CPU s/frame | `librashader-cli` (Metal): s, frames/s, CPU s/frame | Faster |
|---|---|---|---|
| Fighters, ProRes 4444 | 12.5 s, 19.2, 0.12 | 47.6 s, 5.1, 0.73 | 3.8× |
| Game, ProRes 4444 | 60.8 s, 4.0, 0.13 | 265.7 s, 0.9, 1.18 | 4.4× |
| Fighters, H.264 + matte | 43.2 s, 5.6, 0.67 | 222.4 s, 1.1, 1.70 | 5.1× |
| Game, H.264 | 198.7 s, 1.2, 1.13 | 297.8 s, 0.8, 2.16 | 1.5× |

**Linux PC, GTX 1060**

| Input, format | Blender: s, frames/s, CPU s/frame, video memory | `librashader-cli` (wgpu): s, frames/s, CPU s/frame, video memory | Faster |
|---|---|---|---|
| Fighters, ProRes 4444 | 29.0 s, 8.3, 0.66, 439 MiB | 114.8 s, 2.1, 2.44, 1526 MiB | 4.0× |
| Game, ProRes 4444 | 41.6 s, 5.8, 1.06, 439 MiB | 125.9 s, 1.9, 2.90, 1270 MiB | 3.0× |
| Fighters, H.264 + matte (NVENC) | 20.5 s, 11.7, 0.31, 2423 MiB | 108.6 s, 2.2, 2.04, 3515 MiB | 5.3× |
| Game, H.264 (NVENC) | 18.7 s, 12.9, 0.22, 1698 MiB | 107.1 s, 2.2, 1.97, 2790 MiB | 5.7× |

What the numbers say:

- **`librashader-cli` was limited by starting up**, not by drawing or encoding:
  - on the PC it manages about 2 frames/s whatever the input or the encoder;
  - each frame costs it 2–3 s of CPU, against Blender's 0.2–1.1, which is mostly the encoder's.
- **With Blender, the encoder sets the pace.**
  - On the PC, NVENC (12–13 frames/s) is faster than `prores_aw` (6–8). ProRes is faster on mostly empty frames (8.3) than on full ones (5.8).
  - On the Mac, Apple's ProRes encoder runs in software on a plain M1. It's fast on mostly empty frames (19 frames/s) and slow on full ones (4.0). `libx264` 4:4:4 is the slowest encoder of all on full frames (1.2).
- **L1 alone tripled the PC's old speed into ProRes,** before Blender: 0.7 → 1.9–2.1 frames/s, from `prores_aw` in place of `prores_ks`.
- **Video memory:**
  - Blender's CRT holds 439 MiB at 3504×2880, against 1.3–1.5 GiB for 4 `librashader-cli` runs at once.
  - NVENC adds about 1.3–2 GiB for its frames at this size. With the matte's second encoder it reaches 2.4 GiB, well inside the GTX 1060's 6 GB.
  - The CRT never runs alongside Blender's model render (decided 22 November), so they don't add up.

### 3.2 Accuracy

Blender's frames against `librashader-cli`'s on the same machine. Each row is 3 frames × 3 masks:

| | Mean difference | Largest | Pixels that differ at all |
|---|---|---|---|
| PC, fighters (OpenGL against wgpu, same GPU) | 0.0000/255 | 6–11 | 0.001–0.003% |
| PC, game | 0.0001–0.0002/255 | 6–13 | 0.009–0.017% |
| Mac, fighters (Metal against Metal) | 0.0000–0.0023/255 | 6–41 | 0.001–0.11% |
| Mac, game | 0.0003–0.0045/255 | 9–39 | 0.02–0.27% |

- The few pixels that differ sit at sharp edges, where one rounding step changes which side of a threshold a value falls on.
- `test_crt.py` checks the bar (1/255) on every run where both Blender and `librashader-cli` are installed. It passes on both machines.

### 3.3 The matte

- **What's written:** a transparent `.mp4` gives `NAME.mp4` (H.264 4:4:4) and `NAME matte.mp4` (the alpha as H.264 4:2:0, white where opaque). Both come from one ffmpeg, so the frames line up.
- **Accuracy:** on the Mac, the CRT's matte of a 30-frame clip is 0.024/255 from the ProRes alpha of the same frames.
- **Size:** the matte adds little, because the alpha is smooth: on the PC the fighters' `.mp4` plus matte was 89 MB for 240 frames.
- **Still to do:** checking the two files in an editor (Resolve or Premiere).

## 4. The whole of `slp2video`

`slp2video --model logo --crt`: frames 1500–1739 with the logo through the moving camera, `.mov` unless marked (`e2e.sh`). This is after L1–L3 and before L4; section 6 has the runs after it.

| Step | Mac, Blender CRT | Mac, `librashader-cli` CRT | PC, Blender CRT | PC, `librashader-cli` CRT | PC, Blender CRT, `.mp4` |
|---|---|---|---|---|---|
| Render (Dolphin, solver, checks) | 9 s | 9 s | 16 s | 17 s | 14 s |
| Model (EEVEE, 2 processes, 16 samples) | 54 s | 52 s | 26 s | 25 s | 25 s |
| Composite | 1 s | 1 s | 2 s | 2 s | 1 s |
| CRT | **17 s** | 58 s | **28 s** | 119 s | **16 s** |
| **Total** | **82 s** | 120 s | **72 s** | 165 s | **58 s** |
| Output | 1.2 GB | 1.2 GB | 918 MB | 918 MB | 110 MB |

- **The model was then the longest step,** before L4 (section 6). On the PC with NVIDIA's driver it was twice the Mac's speed: 26 s against 54 s for 240 frames. The PC's first run with this driver, on 20 November, took 58 s for 120 frames. Most of that was likely Blender compiling its shaders for the first time: a first run after a settings change took 10–11 s longer than the next (section 6).
- **The render** (Dolphin and the solver) is slower on the PC than on the Mac. That's the CPU, which this work doesn't touch.
- The PC's ProRes file is smaller than the Mac's for the same frames: `prores_aw` against Apple's encoder.

## 5. The model's samples

`samples.sh`: frames 1500–1559 with the logo through the moving camera, at 64, 16, 8 and 4 EEVEE samples. The CRT is redrawn losslessly from each run's composite. The differences are measured on the logo only, since it covers about a sixth of the plate (`model_diff.py`). Frame 30 shown, from the Mac; frames 0 and 59 are within 0.2/255 of it, and the PC's within 0.03/255 of the Mac's.

| Samples | Model time, Mac (60 frames) | Model time, PC | Plate, on the logo: mean / 99th percentile | After the CRT, on the logo: mean / 99th percentile |
|---|---|---|---|---|
| 64 | 45 s | 21 s | reference | reference |
| **16** (default) | 17 s | 9 s | 0.64 / 8 | **0.84** / 12 |
| 8 | 12 s | 8 s | 1.07 / 15 | 1.23 / 20 |
| 4 | 10 s | 7 s | 1.99 / 26 | 1.76 / 30 |

- **The CRT doesn't hide the noise.** The difference after it is about what it was on the plate: its beam and mask spread each pixel, but keep its brightness.
- **16 samples is the fewest inside the 1/255 bar.** The default stays.
- **Fewer samples would save little on the PC anyway** (9 s → 7 s). At 640×480, what's left is EEVEE's fixed cost per frame, which section 6 looks into. The cost of starting each Blender process is part of it too: for 60 frames the 64-sample run at 21 s is mostly not sampling.

## 6. The model's other settings (L4)

`eevee_sweep.py`: 40 frames of the metal logo through the reference camera export, at 16 samples. Each setting is changed on its own against today's. Time per frame is the median after the first frame; the difference is from today's frames, on the logo, worst of 3 frames.

| Variant | Per frame, Mac | Per frame, PC | On the logo: mean / 99th percentile |
|---|---|---|---|
| Today (the project's shadows, fast GI) | 237 ms | 137 ms | reference |
| **No shadows** | **103 ms** | **89 ms** | 0.21 / 6 |
| Shadows at half resolution | 236 ms | 135 ms | 0.20 / 5 |
| Shadow steps 6 → 2 | 234 ms | 133 ms | 0.03 / 1 |
| No fast GI | 233 ms | 134 ms | 0.00 / 0 |
| Fast GI at a quarter resolution | 234 ms | 136 ms | 0.00 / 0 |
| No ray tracing (the project's own setting; plate.py turns it on for metal) | 199 ms | 120 ms | 2.95 / 77 |
| No shadows, no ray tracing | 69 ms | 74 ms | 2.84 / 73 |
| 1 sample | 76 ms | 67 ms | 7.5 / 98 |
| Cel finish: today | 206 ms | 114 ms | reference |
| **Cel finish: no shadows** | **67 ms** | **65 ms** | 0.00 / 0 (identical) |

- **Shadows cost more than half of each metal frame on the Mac, and a third on the PC.** Making them cheaper (resolution, steps) saves nothing: it's having them at all that costs.
- **Without them, the logo hardly changes.** The project's area lights barely shadow the letters onto each other: 0.21/255 on the plate. After the CRT, flattened onto black, it's 0.08–0.14/255 in the logo's box, far inside the bar.
- **The cel finish is emission only,** so shadows change none of its pixels: 40 frames identical.
- **Fast GI costs nothing measurable** here.
- **Ray tracing stays on for the metal logo.** Its polished faces mirror the studio through it: without it they're 3/255 off on average, 77 at the 99th percentile, a visibly different metal. With shadows already off it costs little: 87 → 69 ms on the Mac, and nothing on the PC (90 → 74 ms with OpenGL, 75 → 74 with Vulkan).
- **It's EEVEE throughout,** never Cycles: `blender_plate.py` sets the engine for every plate. On the Mac Blender draws with Metal. On the PC it chooses its OpenGL backend by itself, on the GTX 1060.
  - Its Vulkan backend (`--gpu-backend vulkan`) drew a frame without shadows in 75 ms against OpenGL's 90. But a whole model step of 240 frames took 16 s against 17, and its frames are 0.07–0.30/255 from OpenGL's.
  - So OpenGL stays the default. With shadows on, Vulkan was slower: 167 ms against 135.
- **What it changed** [committed]:
  - the cel finish is drawn without shadows;
  - the logo through the moving camera is too, unless `--model-shadows`;
  - other models keep theirs, since they weren't measured, unless `--no-model-shadows`.
- **Frames whose camera hasn't moved** were to be skipped. But in a whole game's camera export (7,651 frames) only 3 repeat the frame before, at the very start, so there's nothing to skip. Melee's camera is always moving a little.
- **The moving camera's frames are cached now** (`logo-stage/sequences/`), keyed on the camera export's contents and everything else they depend on. The same clip with another mask, colour or format skips Blender: 18 s → 10 s for 60 cel frames on the Mac. The last 3 clips are kept (`--model-cache`).
- **The first run after a change of settings** spends 10–11 s compiling Blender's shaders for them. Blender then keeps them in its cache (`~/.cache/blender`), so later runs don't.

Whole runs again, 240 frames, `--model logo --crt`, without the cache:

| | Mac M1 | PC, `.mov` | PC, `.mp4` |
|---|---|---|---|
| Before this work: `librashader-cli`, the project's shadows | 120 s | 165 s | — |
| After L1–L3 (section 4) | 82 s | 72 s | 58 s |
| **After L4: model** | **18 s** (was 54) | **17 s** (was 26) | **16 s** (was 25) |
| **After L4: all of it** | **41 s** | **60 s** | **49 s** |

On the PC, the CRT into `prores_aw` (27 s) is now the longest step of a `.mov` run, and the render (Dolphin and the solver, 14 s) the next.

## 7. What changes because of this

- **`--runtime blender` stays the default on macOS and Linux,** as committed. The measurements confirm both its speed and its accuracy.
- **NVENC's settings stay:** constant QP 12, H.264 4:4:4. On real CRT frames it beat `libx264` CRF 12 in quality at 7 times the speed (section 4 of the plan).
- **On the Mac, prefer ProRes to `.mp4` for long CRT renders.** Both docs now say so.
- **The model keeps 16 samples, but drops shadows** for the logo and the cel finish (section 6).
- **On the PC, `.mp4` is the fastest way through:** NVENC keeps the CRT at 12–13 frames/s, against `prores_aw`'s 6–8.

## 8. Not measured

- Windows, which still draws with `librashader-cli`.
- Whole games, rather than 4 s clips. A clip's numbers include each step's start-up: Blender's 0.1–0.9 s and the preset's compile, and Dolphin's start. A whole game should run a little faster per frame.
- The matte in an editor.
