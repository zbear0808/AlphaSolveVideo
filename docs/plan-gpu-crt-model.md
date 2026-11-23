# GPU work after the render: the model and the CRT

Status: plan, November 2026. Steps L1–L4 are done and measured: the CRT drawn by Blender, the faster encoders, the matte file, and the model without shadows. [`report-gpu-crt.md`](report-gpu-crt.md) has the measurements. Dolphin and the solver are out of scope: Dolphin is at its limit for now, and the solver's fix is an encoder swap (`prores_aw`, [`plan-linux-gpu.md`](plan-linux-gpu.md) step G3), not the GPU.

Decided, 22 November:

- **Linux with the NVIDIA GPU first** (the PC in `plan-linux-gpu.md`: GTX 1060, driver 580). Then the Mac, then Windows.
- **The CRT does not run while Blender renders.** Each step finishes before the next starts. The overlapped Blender and CRT of this plan's first version is dropped.
- **Quality bar for faster settings:** a mean difference of 1/255 or less in the final CRT picture.
- **On the PC, offer GPU encoding:** NVENC H.264 or HEVC 4:4:4, with transparency as a separate matte file. ProRes 4444 with alpha stays the default.
- **Separate steps, not one Blender scene.** Blender renders the model, ffmpeg composites, Blender's GPU module draws the CRT, ffmpeg encodes. The fighters are never placed in the 3D scene (section 3.1).
- **Full-size CRT output stays the default:** 6 rows per scanline, 3504×2880 for regular Melee. `--crt-scale` stays an option for smaller videos (section 9).

Evidence tags, as in the other plans:

- **[verified]**: measured, or read in this repo's or librashader's source.
- **[reported]**: from documentation; not re-checked by hand.
- **[estimate]**: needs a measurement.
- **[to test]**: needs an experiment before we rely on it.

---

## 1. Summary

- **Today's CRT spends almost nothing on the GPU.** For every frame:
  - a new `librashader-cli` starts and compiles the 12-pass preset;
  - the frame goes through two BMP files on disk;
  - the encoder decodes the source a second time for the alpha.

  On the PC the GTX 1060 draws a frame in 12 ms, but the step manages 0.7 frames a second into ProRes [verified].
- **The CRT can run inside Blender.** librashader's own GLSL for crt-royale compiles in Blender's `gpu` module on Metal, OpenGL and Vulkan, with one small rewrite. A prototype draws 23 frames/s at 3504×2880 on the GTX 1060 and 37 on the M1, read-back included [verified: section 3].
- **What that saves isn't re-encoding.** The files between the steps are 640×480 and cost about 2 ms a frame altogether. The 3504×2880 encode at the end can't be avoided, and Blender's own FFmpeg has no NVENC and no VideoToolbox. What it saves is the per-frame startup, and it needs no Rust toolchain. With the frames piped to an external ffmpeg [verified, 120 frames at 3504×2880]:

  | | Mac M1 | PC, GTX 1060 |
  |---|---|---|
  | Today, ProRes 4444 | 4.3 frames/s (Apple's encoder) | **0.7** (`prores_ks`) |
  | Today, H.264 4:4:4 | 2.7 (`libx264`) | 1.5 (`libx264`) |
  | CRT in Blender, no encoder | 36.6 | 23.3 |
  | CRT in Blender → ProRes 4444 | **12.5** (Apple's encoder) | **6.4** (`prores_aw`) |
  | CRT in Blender → NVENC H.264 4:4:4 | — | **9.7** |
  | CRT in Blender → NVENC HEVC 4:4:4, with and without a matte file | — | 8.3–8.4 |

  For a 3-minute game (10,800 frames), the PC's CRT goes from about **4.3 hours** in ProRes to **28 minutes** (ProRes) or **19 minutes** (NVENC). The Mac's goes from about 42 to 14 minutes. These are the prototype's numbers. `tools/crt`'s, measured on real renders, are in [`report-gpu-crt.md`](report-gpu-crt.md): 22–31 and 14–15 minutes on the PC, and 10–45 minutes on the Mac depending on the picture.
- **Its frames match librashader's:** 0.003/255 apart on average on the Mac, and 0.0002/255 on the PC, far inside the 1/255 bar. That's closer than librashader's own runtimes are to each other (0.4–1.0/255). A first version was 0.8–1.7/255 off because it flipped the frames upside down (3.4). A small Rust program on librashader itself stays the fallback (3.6).
- **The plan, in order** (section 7):
  1. NVENC and `prores_aw` on the PC.
  2. The CRT in Blender, as `tools/crt`'s renderer.
  3. The matte file for NVENC.
  4. Cheaper model frames.
  5. Fewer files between steps, still one step after another.

## 2. What runs after the render today

For `slp2video --model ... --crt` with the moving camera [verified: `slp2video.py`, `plate.py`, `composite.py`, `render_video.py`]:

1. **Blender:** 2 processes (`--model-jobs`), each loading the project and rendering a contiguous run of frames to 8-bit PNG, at 16 EEVEE samples.
2. **Composite:** ffmpeg lays the fighters over the PNG frames and writes lossless FFV1 to a `.nut` file.
3. **CRT:**
   1. ffmpeg decodes the `.nut` file, squeezes each frame to 584×480 and pipes it to Python, which writes a BMP.
   2. A new `librashader-cli` process for each frame compiles the preset, draws, and writes a 30 MB BMP at 3504×2880. Python reads it back and pipes it to a second ffmpeg.
   3. That ffmpeg decodes the source again, scales the alpha up on the CPU, merges it, converts to YUV, and encodes.

What each part costs, measured on its own [verified]:

| Part | Mac M1 | PC |
|---|---|---|
| The files between steps at 640×480 (PNG plate written and read, FFV1 composite written and read, the squeeze) | About 0.5 s per 240 frames, all together: about 2 ms a frame | — |
| `librashader-cli` startup and compiling the preset | 0.42 s a run, even at 584×480 | About 1 s of CPU a run |
| Drawing one frame | — | 12 ms (GTX 1060) |
| The alpha path: second decode, upscale, `alphamerge` | About 15 ms a frame | — |
| RGBA to `yuva444p10le` (swscale) | About 4 ms a frame | About 15 ms a frame |
| Encoders alone, 3504×2880 (one repeated frame), frames/s | Apple's ProRes 27, `prores_aw` 15.5, `prores_ks` 4.4, `libx264` 13, `hevc_videotoolbox` with alpha 19.5 | `prores_aw` 6.4, `prores_ks` 1.7, `libx264` 3.9, `h264_nvenc` 4:4:4 14, `hevc_nvenc` 4:4:4 17 |

A repeated frame flatters `libx264` and NVENC, which predict from the previous frame; ProRes encodes each frame on its own. The NVENC numbers are from BtbN's FFmpeg 8.1 build: it works with driver 580, as `plan-linux-gpu.md` 6.3 expected [verified]. The 9.0 build in `packages/ffmpeg/` doesn't [verified].

## 3. The CRT inside Blender: what the investigation found

### 3.1 The options

| Way | Verdict |
|---|---|
| **Blender's compositor** | Not possible faithfully. It has 90 nodes and none of them runs a custom shader [verified: Blender 5.2.3's `CompositorNode*` types]. crt-royale would have to be rebuilt out of blur, map-UV and math nodes: a different shader, not CRT Royale |
| **Blender's own video output** | Slower than today's ffmpeg. Its bundled FFmpeg has ProRes (`prores_ks`, `prores_aw`), but is built with `--disable-nvenc --disable-videotoolbox` on both Linux and macOS [verified: the build flags in both binaries] |
| **Blender's `gpu` Python module, in the background** | **Works.** In Blender 5.2, `gpu.init()` starts the GPU module in `-b` mode [verified]. Offscreen framebuffers, custom shaders from `GPUShaderCreateInfo`, uniform blocks, sRGB and float textures, and per-texture filter and wrap modes all work there. The frames are then piped to an external ffmpeg |
| **In the same Blender process as the EEVEE render**, frame by frame | Possible, but that interleaves the CRT with the model's rendering on the GPU, which we decided against. It would save only the 2 ms a frame of files between the steps. Not pursued |
| **The fighters' video in the 3D scene**, on a plane | Wrong for this picture. The fighters are already a finished, pixel-exact screen image. A textured plane would be resampled by the camera, softened by EEVEE's pixel filter, and passed through Blender's colour management, and the CRT shows every pixel. If the model should ever cover the fighters where it's in front of them, the way to do it is a 2D composite using the plate's depth, not a plane. Not pursued |

### 3.2 How the prototype works

It's in [`research/crt-in-blender/`](../research/crt-in-blender/README.md):

- **`prep_chain.py`** asks `librashader-cli` for everything once:
  - each pass compiled to GLSL 330 (`transpile`, through SPIR-V, as its own runtimes do);
  - the passes' filter, wrap mode, framebuffer format and scaling (`parse`, `preprocess`);
  - the parameters' defaults, and the six mask textures as raw RGBA.
- **`blender_crt.py`** (runs inside Blender) rebuilds librashader's filter chain:
  - it turns each pass's uniform block and push constants into a Blender uniform block;
  - it sizes each pass's framebuffer as librashader's `scaling.rs` does;
  - it binds Source, Original, the aliases and the mask textures as librashader's GL runtime does (`filter_chain/chain.rs`).

  It reads raw frames from a file or pipe and writes raw frames to one.
- **One rewrite** is needed, for Metal only: Blender's GLSL-to-Metal translation can't copy a whole array (`vec3 a[9] = b;`, in crt-royale's last pass). OpenGL and Vulkan compile all 12 passes as they are [verified].
- **Rows go through in the order they come,** top row first, as ffmpeg's raw frames have them. librashader puts an image's top row at v = 0 and reads the output back from there, and so does Blender's GPU module with a buffer's first row [verified: 3.4]. No flip is needed anywhere.

### 3.3 Speed

All [verified], 120 frames of 584×480 drawn at 3504×2880, grille mask (`compare.sh`). In these runs the frames were flipped upside down by ffmpeg on the way in and out, which cost nothing, so the speeds stand without the flip:

- **Compiling the preset** takes 0.07–0.25 s, once per video. Today that cost is paid on every frame.
- **Each frame:** upload and draw 3–5 ms, read-back 24–38 ms.
- **The backend matters on the PC.** Blender's OpenGL backend: 26 ms a frame and 1.3 s to compile. Its Vulkan backend: 43 ms a frame and 4.8 s to compile. So use OpenGL on Linux.
- **Into an encoder,** the loop is serial: read back, then write to the pipe. That gives 8–12 frames/s against the encoder's 14–27 alone. Writing from a second thread while the next frame draws should get closer to the encoder's own rate [estimate].

### 3.4 Accuracy

Against `librashader-cli` on the same machine, frames 0, 60 and 119 of a clip, each mask [verified]:

| | Mean difference | Largest | Pixels that differ at all | PSNR |
|---|---|---|---|---|
| **Mac: Metal, against `librashader-cli`'s Metal** | **0.003/255** | 15–34 | 0.36% (0.01% by more than 4/255) | 66–70 dB |
| **PC: OpenGL on the GTX 1060, against `librashader-cli`'s wgpu** | **0.0000–0.0002/255** | 6–13 | 0.001–0.017% | — |
| For reference: `librashader-cli`, the PC's wgpu against the Mac's Metal | 0.42/255 (one frame); 0.80–1.0 on a 30-frame clip (`tools/crt/README.md`) | 31 | | 49 dB |

- **The bar is met** on the Mac, by a wide margin: 0.003/255 against the agreed 1/255. Blender's frames are closer to librashader's than librashader's own runtimes are to each other.
- **What it took.** The first version flipped every frame and the mask textures upside down, assuming GPU textures are bottom-up. crt-royale isn't symmetric top to bottom (its scanlines and mask start from the top edge), so the flip moved them: 0.8–1.7/255. Cutting the preset to its first N passes in both renderers found the first difference at the bloom pass's resize, where the flipped sample positions fell on different texels.
- **Mip levels don't matter here.** crt-royale's last pass reads its input with mipmaps, and Blender's Python can't build them. But at this size that pass samples at full resolution, so the mip levels are never read [verified: the 0.003/255].
- **The bar to keep:** a mean of 1/255 or less on every test frame and mask, against `librashader-cli` on the same machine. The tests in L2 check it.

### 3.5 What else moves to the GPU there

- **The alpha.** A last pass samples the 584×480 input's alpha bilinearly at the output size, as ffmpeg's `scale=...:flags=bilinear` does today. That removes the second decode and the CPU upscale. It must match ffmpeg's to 1/255 [to test].
- **The matte file** for NVENC (decision 4): the same alpha, written as a second grey video.
- **RGB to YUV,** optionally: saves about 15 ms a frame of swscale on the PC [verified: the cost], which matters with NVENC and little with ProRes.

### 3.6 The fallback: a Rust program on librashader

If the Blender CRT ever can't keep within the bar (a later Blender, another GPU), the other way to keep the preset loaded is `crt-stream`: a small Rust program on the `librashader` crate (runtime-vk on Linux, runtime-mtl on the Mac), with the same pipes in and out.

- **For:** it would give librashader's own frames.
- **Against:** it needs Rust to build. The PC has none; it would build in the `asv-linux` container, as `librashader-cli` is [verified]. It's also 2–3 days instead of 1–1.5.
- **Its speed** would be about the same, since the encoder sets the pace either way [estimate].

### 3.7 What it costs

- **`--crt` then needs Blender,** even without a model. `librashader-cli` stays as the fallback when there's no Blender, and as the reference in the tests.
- **We maintain the chain's logic,** about 300 lines. It follows librashader 0.12.1. The shaders themselves still come from librashader's compiler, so they don't drift.

## 4. Encoders on the PC (L1: done, 22 November)

- **FFmpeg 8.1.** BtbN's month-end build `ffmpeg-n8.1.3-27-g8dca1586f4-linux64-gpl-8.1.tar.xz` (SHA-256 `41e9c565…3380`, as pinned in `plan-linux-gpu.md` 6.3) is the PC's `packages/ffmpeg/` now. Its NVENC runs on driver 580 [verified]. The 9.0 build is kept in `packages/ffmpeg-9.0/`.
- **The encoder order** (`solve.ACCELERATED`, `solve.OPAQUE_ACCELERATED`, `render_video.video_encoder`) [verified: unit tests in `test_crt.py`; on the PC and the Mac]:
  - `.mov`: Apple's ProRes, then `prores_aw`, then `prores_ks`, for the solver, `--keep-background`, the composite and the CRT;
  - the CRT's `.mp4`: `h264_nvenc` 4:4:4, then `libx264`.

  Each faster encoder is tried on one frame of the real size first. So on the PC a frame wider than NVENC's 4096 pixels (`--crt-scale 8` and up) falls back to `libx264` [verified].
- **NVENC's settings,** from 60 real CRT frames at 3504×2880 on the GTX 1060, against the drawn frames [verified]:

  | Encoder | Frames/s | Size | SSIM | PSNR |
  |---|---|---|---|---|
  | `libx264 -crf 12 -preset medium` (today) | 2.6 | 41 MB | 0.985 | 40.4 dB |
  | `h264_nvenc -rc vbr -cq 10…16 -b:v 0` | 20 | 20 MB, whatever the CQ | 0.911 | 33.9 dB |
  | `h264_nvenc -rc constqp -qp 16` | 20.3 | 109 MB | 0.977 | 41.7 dB |
  | `h264_nvenc -rc constqp -qp 13` | 18.5 | 147 MB | 0.984 | 43.8 dB |
  | **`h264_nvenc -rc constqp -qp 12`** (chosen) | 18.6 | 170 MB | 0.988 | 44.8 dB |
  | `hevc_nvenc -rc constqp -qp 16` | 27.1 | 101 MB | 0.990 | 44.2 dB |

  - NVENC's VBR mode stops at a bit rate of its own, whatever the CQ asks for, and loses the stripes. Constant QP doesn't.
  - QP 12 is the lightest setting at least as good as `libx264` on both measures. It's seven times `libx264`'s speed, in files four times the size: about 10 GB a minute, against ProRes's 23.
  - `hevc_nvenc` at QP 16 would be better again, faster, and smaller. But `.mp4` has always been H.264, so it stays H.264 for now. HEVC could be an option later [to decide].
- **Not changed:** the composite's own `.mp4` (640×528, 4:2:0, `libx264`). At that size `libx264` is fast, and the composite is a small part of a run.
- **The render tests on the PC** with FFmpeg 8.1, `prores_aw` in the solver and the composite, and the encoder order above: 38 pass, 1 skipped (`--format hevc`, which needs macOS), as before with 9.0 and `prores_ks` [verified, 22 November]. Their speeds aren't compared here, because another render shared the PC during the run.
- **The matte (decision 4)** is step L3: with `--format mp4` and transparency, write `NAME.mp4` and `NAME matte.mp4`, the alpha as a grey video. NVENC manages 8.4 frames/s for both together, behind the Blender CRT [verified].
  - Resolve, Premiere and Final Cut can use a luma matte [reported].
  - Check that the two files line up frame for frame in one editor [to test].

## 5. The model, without new tools

Unchanged from the first version of this plan. Each change is checked against the plate's alignment check (`check_report`, 0.01 px) and against the 1/255 bar after the CRT.

- **Skip identical camera frames.** Render the first frame of each run of identical cameras and hard-link it to the others. This is exact.
- **Cache moving-camera plates** under `PLATE_CACHE`, keyed on the job and the camera export. Rendering again with another mask, colour or format then skips Blender.
- **EEVEE settings for a 640×480 plate that goes through a CRT.** Each one is tried against the bar:
  - samples: 4 and 8, against 16 today;
  - soft shadows (each light's `use_shadow_jitter`) off;
  - lower shadow resolution and ray counts;
  - ray tracing at half resolution;
  - for the cel finish, which is emission only: shadows off, and samples only for anti-aliasing;
  - PNG compression 0.
- **Freeze the scene:** drop the animation of everything but the camera. Check whether `SH010_Reveal`'s own animation plays during a clip, which would be a bug as well [to test].
- **1, 2 or 3 Blender processes,** OpenGL against Vulkan on the PC (`plan-linux-gpu.md` G2).
- **Expected:** 1.5–3 times faster for the metal logo, more for the cel finish [estimate].

## 6. Fewer files between the steps, one step after another

Still one step after another, with no step overlapping another:

1. Blender renders every plate frame to PNG, as today.
2. **One ffmpeg** reads the PNGs and the fighters, composites, squeezes, and pipes raw frames to the CRT. The `.nut` file and its encode and decode go away.
3. **The CRT in Blender** pipes its frames to the encoding ffmpeg.

This saves about 2 ms a frame and a temporary file, so it's tidying more than speed. It comes almost free with the pipes of section 3.

## 7. Order of work: Linux with NVIDIA first

| # | Step | Effort | Where |
|---|---|---|---|
| L1 | FFmpeg 8.1 on the PC; `prores_aw` and NVENC in `video_encoder` and `composite`; render tests with them. **Done** 22 November | 0.5 day | The PC |
| L2 | The CRT in Blender, in `tools/crt`. **Done on the Mac** 22 November: <br>- `render_video.render` uses it (`--runtime blender`, first in `auto` on macOS and Linux) when Blender is there, `librashader-cli` otherwise, and falls back if Blender can't draw; <br>- `blender-chain/`, written and checked by `vendor_chain.py`; <br>- the frames through inherited pipes, and a writer thread; <br>- tests against `librashader-cli` (`test_crt.py`). <br>**Done on the PC** 22 November: tests pass, 0.0002/255 from `librashader-cli`, 3–6 times its speed ([`report-gpu-crt.md`](report-gpu-crt.md)). <br>Left: alpha on the GPU (the ffmpeg alpha path stays meanwhile) | 1.5–2 days | The PC, then the Mac |
| L3 | The matte file with `.mp4` (`--format mp4 --transparency`). **Done** 22 November: `NAME matte.mp4` beside `NAME.mp4`, from the CRT (NVENC where it works) and from the composite without it; on the Mac the CRT's matte is 0.024/255 from the ProRes alpha of the same frames. Left: check the two files line up in one editor | 0.5 day | The PC |
| L4 | The model. **Done** 22 November ([`report-gpu-crt.md`](report-gpu-crt.md) sections 5–6): <br>- no shadows for the cel finish (identical pixels) and the logo through the moving camera (0.1/255 after the CRT): the model's time 54 → 18 s on the Mac, 26 → 17 s on the PC, for 240 frames; <br>- the moving camera's frames cached; <br>- 16 samples kept (8 miss the bar). <br>Dropped: skipping frames whose camera hasn't moved (3 of 7,651 in a whole game); freezing the scene (only the camera and one glint light move in the view layer, and the glint is off) | 1–1.5 days | The PC, then the Mac |
| L5 | One ffmpeg from the plates and fighters to the CRT (section 6) | 0.5 day | Anywhere |
| L6 | Docs: `slp2video.md`'s speed table, `tools/crt/README.md`, this plan's status | 0.25 day | Anywhere |
| **Total** | | **4.25–5.25 days** | |

If a platform's Blender CRT can't be kept within 1/255, swap in `crt-stream` (3.6) there: 2–3 days.

## 8. Risks

| Risk | Mitigation |
|---|---|
| The Blender CRT can't be brought within 1/255 of librashader's | `crt-stream` on librashader itself (3.6). `librashader-cli` stays the reference in the tests |
| A later librashader or Blender changes behaviour | Pin librashader 0.12.1 (already pinned) and check the Blender version. The tests compare against `librashader-cli` on every platform |
| Blender's OpenGL backend in the background needs a display on some Linux setups | It ran with `DISPLAY` and `WAYLAND_DISPLAY` unset, over SSH [verified]. Blender's Vulkan backend works too, slower |
| NVENC's 4:4:4 looks worse than `libx264` at the same size | Compare first (section 4). ProRes stays the default |
| The two files of the matte option drift apart in an editor | Same frame count and timestamps. Check in one editor first |
| 6 GB of video memory | The CRT runs alone now: its framebuffers at 3504×2880 are about 0.5 GB [estimate] |

## 9. The CRT's size: full size stays the default

Decided 22 November: the CRT keeps drawing at full size, **6 output rows per scanline: 3504×2880** for regular Melee and for Animelee's 960 rows. Every speed in this plan is measured at that size.

- That's taller than a 4K frame (2160 rows). A 4K upload or timeline scales it down, which is fine for a master that's edited at full size.
- For smaller videos, `--crt-scale` stays an option. At 4 (2336×1920) it has 44% of the pixels and encodes about twice as fast. The phosphor triads stay 3 px wide [verified: `physical_settings`], so each picture pixel gets 1.3 triads instead of 2.
- Full size matters for the plan in three places:
  - **Memory:** the CRT's framebuffers at 3504×2880, about 0.5 GB [estimate], fit the GTX 1060's 6 GB, since the CRT runs alone.
  - **Disk:** ProRes 4444 at this size is about 23 GB a minute [verified: `slp2video.md`]. NVENC HEVC 4:4:4 was 14 MB for 120 frames of a busy clip [verified], about 0.4 GB a minute.
  - **NVENC's limits:** H.264 goes up to 4096×4096 and HEVC up to 8192×8192 on the GTX 1060 [reported: `plan-linux-gpu.md` 6.3], so 3504×2880 fits both. A larger `--crt-scale` (8 or more: 4672×3840 and up) needs HEVC. `video_encoder` should check that before it picks H.264.

## References

- [`research/crt-in-blender/`](../research/crt-in-blender/README.md): the prototype and its measurements.
- This repo:
  - `tools/crt/render_video.py`: `render`, `draw`, `video_encoder`, `physical_settings`;
  - `tools/slp2video/slp2video.py`: `model_plate`, `crt_pass`;
  - `tools/logo-stage/plate.py` and `blender_plate.py`;
  - `tools/logo-stage/composite.py`.
- [`plan-linux-gpu.md`](plan-linux-gpu.md): the PC, its encoders (section 6), `--gpu` (section 8), the CRT on Linux (section 9).
- librashader 0.12.1: `librashader-runtime/src/scaling.rs` and `binding.rs`, and `librashader-runtime-gl/src/filter_chain/chain.rs`, for how passes are sized and their textures bound.
- Blender 5.2's Python API: `gpu.init`, `gpu.types.GPUShaderCreateInfo`, `GPUFrameBuffer.read_color`, `GPUTexture.filter_mode`, `extend_mode`.
