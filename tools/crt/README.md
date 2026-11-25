# CRT

CRT Royale on a video: TroggleMonkey's original shader, drawn by Blender's GPU module or by [librashader](https://github.com/SnowflakePowered/librashader), on macOS, Linux and Windows. [`slp2video --crt`](../../docs/slp2video.md#the-crt) runs it; it also works on any video by itself.

```sh
python3 tools/crt/render_video.py in.mov out.mov --physical-pixels             # each pixel a physical CRT pixel
python3 tools/crt/render_video.py in.mov out.mov --physical-pixels --scale 8 --triads-per-pixel 1
python3 tools/crt/render_video.py in.mp4 out.mov --size 1920x1080 --lines 240  # an emulated 240-line signal
python3 tools/crt/install_librashader.py                                       # librashader-cli and crt-stream (needs Rust)
python3 tools/crt/test_crt.py                                                  # includes real renders, with what's installed
```

## Blender draws it, on macOS and Linux

Where Blender (5.2) is found, it draws the CRT: `--runtime blender`, which `auto` tries first on macOS and Linux.

- **One process for the whole video.** `blender_crt.py` runs inside Blender, in the background. It compiles the preset once, and draws every frame with Blender's `gpu` module.
  - ffmpeg's decoded frames come in through one pipe and the drawn frames go out to the encoding ffmpeg through another. The frames never pass through Python or the disk.
  - `librashader-cli` instead starts again for every frame, and compiles the preset each time: about 0.5 s a frame on an M1, 1 s of CPU on the Linux PC.
- **The shaders are librashader's.** [`blender-chain/`](blender-chain/README.md) is the vendored preset as `librashader-cli` 0.12.1 compiles it: each pass as GLSL, with its filter, wrap mode, framebuffer format and scaling. `blender_crt.py` sizes and binds the passes as librashader's runtime does.
  - Against `librashader-cli`'s Metal on the same Mac, its frames are 0.003/255 apart on average, for every mask: 0.36% of pixels differ at all. librashader's own runtimes are 0.4–1.0/255 from each other.
  - `vendor_chain.py write` writes `blender-chain/`, and `vendor_chain.py check` checks it.
- **Speed,** 3504x2880 from 584x480 ([`docs/report-gpu-crt.md`](../../docs/report-gpu-crt.md)). With nothing to encode, Blender draws 37 frames a second on an M1 and 23 on the Linux PC's GTX 1060. With an encoder, the encoder sets the pace:
  - **M1 into Apple's ProRes:** 4–19 frames a second, against 0.9–5 with `librashader-cli`;
  - **PC into `prores_aw`:** 6–8, against 2;
  - **PC into NVENC:** 12–13, against 2.

  The ranges run from a whole drawn game to fighters alone.
- **On Linux it uses Blender's OpenGL backend,** which drew a frame in 26 ms there against its Vulkan backend's 43. Blender takes the first GPU EGL lists (the NVIDIA GPU on the PC). It runs without a display, over SSH.
- **If Blender can't draw** (no GPU, no `gpu.init` in an older Blender), `auto` says why and goes on with `librashader-cli`.
- **Only the vendored preset.** `--preset` with any other goes to `librashader-cli`. So does Windows for now: Blender gets the frames through inherited pipes, which `subprocess` passes on macOS and Linux only.

## crt-stream: one librashader chain, without Blender

[`crt-stream/`](crt-stream/) is a small Rust program on the `librashader` 0.12.1 crate: `--runtime stream`, which `auto` tries after Blender and before `librashader-cli`. It keeps one filter chain for the whole video, so state across frames carries over: guest's afterglow, frame counts, history. `librashader-cli` draws every frame as the first of a new chain, so it loses them.

```sh
crt-stream --preset P.slangp --input 584x480 --output 3504x2880 [--params k=v,...] [--runtime metal|wgpu] [--warmup N]
```

- **Pipes, as Blender's.** Raw RGBA frames come in on stdin and go out on stdout, top row first. `CRT_READY`, `CRT_FRAMES n` and `CRT_DONE` go to stderr, as `blender_crt.py` writes them. `render_video.py` hands it the decoding ffmpeg's output and the encoding ffmpeg's input as its stdin and stdout, which works on Windows too. If it stops before its first frame, `auto` goes on to `librashader-cli`.
- **Frame *n* is drawn with frame count *n*,** with librashader's other defaults. `--warmup N` draws the first frame N times first; the video's frames then count on from N.
- **Runtimes:** Metal on macOS; wgpu on Linux (Vulkan) and Windows (Direct3D 12 or Vulkan). wgpu is in the macOS build too, on Metal (`--runtime wgpu`). wgpu takes the fast GPU (`HighPerformance`, the GTX 1060 on the PC), unlike `librashader-cli`; `WGPU_ADAPTER_NAME` or `WGPU_POWER_PREF` choose another. There's no Vulkan or Direct3D 11 runtime of its own: wgpu covers them.
- **Two of librashader's runtimes are patched** ([`crt-stream/vendor/`](crt-stream/vendor/README.md)). Metal and wgpu 0.12.1 make a pass's target again on every frame when the next pass reads its mip levels. That erases guest's afterglow, whose pass is followed by a `mipmap_input` pass: without the patch, a white-then-black clip went from 222.4 to 0.0 on its first black frame. Vulkan, Direct3D and OpenGL don't have the bug.
- **Its frames are `librashader-cli`'s.** Frame 0 of a 584x480 test picture at 3504x2880 is identical to `librashader-cli`'s, every pixel, for Royale (grille) and guest, on the M1 (Metal) and on the GTX 1060 (wgpu, Vulkan). wgpu on the Mac is 0.0004/255 from Metal. The frame's size is the one asked for: the output texture is made at that size and read back whole.
- **The afterglow decays as measured.** 10 white frames then black, guest's defaults: 222.4, then 35.7, 28.8, 22.6, … and gone after 15 frames, as the crt-royale TouchDesigner project measured it (`temporal_results.json`): the same to 0.001 on the M1, within 0.06 on the GTX 1060.
- **Speed,** 3504x2880 from 584x480, the next frame drawing while the last is read back. With nothing to encode, 12.5 ms a frame on the PC's GTX 1060 for Royale and guest alike (80 frames a second; Blender 18.5–20.6 ms), and 13–29 ms on the M1 (34–78 frames a second, varying with what else was running; Blender 21–32 ms). Into an encoder, the encoder sets the pace (120 frames of a test picture): 12 frames a second into Apple's ProRes on the M1 (Blender 8.6); 13 into NVENC and 6 into `prores_aw` on the PC, as Blender.
- **Build:** `install_librashader.py` builds it after `librashader-cli`, from its `Cargo.lock`, into `packages/librashader/bin/`; the build folder is `crt-stream-build` in the cache folder. 1.5 min on the M1, 4 min on the PC. **Found:** `--crt-stream PATH` or `CRT_STREAM`, then `packages/librashader/bin` and the PATH.
- **Windows** isn't tried yet: `.github/workflows/crt.yml` builds and tests it there when run by hand.

`render_video.py` is the crt-royale TouchDesigner project's `tools/render_video.py`, brought into this repo. It has the same options and works out the same settings (mask, triad size, aspect, output size). On the same input and settings it gave exactly the same pixels on the Mac: physical pixels with and without alpha, and standard mode. What changed:

- **The shaders are here**, in [`slang-shaders/`](slang-shaders/README.md): the 38 files of libretro's slang-shaders (commit `2345ee91`) that `crt/crt-royale.slangp` needs, unmodified, with their licences. A frame rendered with them is identical to one rendered with the project's full checkout.
- **The runtime suits the platform.** `--runtime auto` (the default) tries Blender first on macOS and Linux (above). Then it tries this platform's librashader runtimes in order on the first frame, and keeps the first that draws it at the size asked for: Metal on macOS; Direct3D 11, then 12, wgpu, Vulkan, OpenGL on Windows; wgpu, then Vulkan, OpenGL on Linux. The original always asked for Metal.
- **Frames stream through.** One ffmpeg decodes the video, and a second encodes the frames in order as they're drawn. With `librashader-cli` the frames go to it as they come, 4 at a time (`--jobs`), and only the frames in flight are on disk, as BMP files: no PNG compression, which made each frame 0.1 s slower to write and slower again to read back. 150 frames at 3504x2880 with alpha took 30 s instead of 50 on an M1, with identical output.
- **Alpha follows the picture's framing.** The alpha goes through the same filters as the colour. The original took it from the unframed input, which only mattered in standard mode.
- **Only Python's standard library.** ffmpeg is found the way slp2alpha finds it.
- **H.264** (`--codec h264-444`): NVENC where it works (`h264_nvenc` 4:4:4 at a constant QP of 12), else `libx264` at CRF 12, medium preset, as `slp2video` writes it (the original: CRF 10, slow). **ProRes**: Apple's encoder, then `prores_aw`, then `prores_ks`. Each faster encoder is tried on one frame of the real size first, so a missing driver or a frame too wide for it (H.264 on NVENC stops at 4096 pixels) falls through to the next.

## librashader-cli

`install_librashader.py` builds `librashader-cli` 0.12.1, the version all of this was checked with, with Rust's cargo into `packages/librashader/`. The build folder stays in the cache folder. Where Blender draws the CRT it isn't needed to render, only to write and check `blender-chain/` and as the tests' reference.

| Platform | Runtimes built | Build time | Also needs |
|---|---|---|---|
| macOS | metal, wgpu | 1.5 min (M1) | Xcode's command line tools |
| Linux | wgpu, vulkan | 4.5 min (M1, in Docker) | `build-essential`; to run, `libvulkan1` and a Vulkan driver: the GPU's, or Mesa's lavapipe |
| Windows | d3d11, wgpu | not built yet | Visual Studio's C++ build tools, with rustup's MSVC toolchain |

- **wgpu is in every build** because librashader-cli 0.12.1 doesn't compile without it: its `transpile` command imports wgpu's shader translator (naga) whatever the features. With `--features vulkan` alone, cargo stops at `use librashader::reflect::naga` [tried in Ubuntu 22.04].
- **Linux draws through wgpu, on Vulkan.** librashader-cli's own Vulkan runtime ignores the size it's asked for (`-d`): it draws and reads back at the input's size (`src/render/vk/mod.rs`). Asked for 3840x2880 from a 640x480 frame, it wrote 640x480. Its wgpu runtime draws at the right size, through Vulkan. `render_video.py` checks every frame's size, so a runtime that gets it wrong is skipped (`auto`) or stops the render.
- **On macOS, wgpu can't draw this preset** (`Unsupported features were requested: PIPELINE_CACHE`), so `auto` uses Metal.
- **Which GPU, on Linux.** wgpu takes the first GPU Vulkan lists: on a laptop with Intel graphics and an NVIDIA card, the Intel one. To draw on the other, leave Vulkan only its driver, e.g. `VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json` (Dolphin follows it too). On the Linux PC the GTX 1060 drew a 3504x2880 frame in 12 ms, the Intel HD 630 in about 60 ms and lavapipe in 760 ms.
- **What a frame costs on Linux.** Each `librashader-cli` run takes about 1 s of CPU on the PC before it draws anything, even for a 64x48 frame: starting up, and compiling the preset's 12 passes. librashader keeps compiled shaders on disk for Metal (`~/Library/Caches/librashader`), but on the PC its cache folder stayed empty. So a frame takes about 1.7 s there on any of its GPUs, against 0.5 s on the Mac, with 4 at a time. The encoder is the other limit. On CRT frames of a full stage, the PC's `prores_ks` manages about 0.4 frames a second (`prores_aw` 2.7, `libx264` 1.9); mostly transparent frames go much faster.
- **Left out:** Direct3D 12, which downloads a prebuilt DXC while building; OpenGL, which needs X11's development packages to build on Linux, and a window to run; Direct3D 9.
- **Found:** `--librashader PATH` or `LIBRASHADER_CLI`, then `packages/librashader/bin`, the PATH and `~/.cargo/bin`.

## What was checked

| | Result |
|---|---|
| The Mac, against the crt-royale project's script | Identical frames: physical pixels (grille), physical pixels with alpha (slot), standard mode (shadow, letterbox) |
| The Mac, `slp2video --crt` against its previous version | Identical videos (opaque, transparent, 150 frames) |
| The Mac, this installer's build against a full `cargo install` | Identical frames |
| Linux (Ubuntu 22.04 arm64 in Docker, wgpu on lavapipe), against the Mac's Metal | The same picture: PNG frames on average 1.0/255 apart (at most 36), spread evenly over scanlines and triads, so floating point rather than a different shader. The alpha, which ffmpeg scales, was within 1/255 with `slp2video`'s settings; in `render_video.py`'s own 6x mode, Ubuntu's FFmpeg 4.4 and the Mac's FFmpeg 8 scaled it up to 20/255 apart at edges |
| Linux, `test_crt.py` | All pass, including the render: scanlines and phosphor stripes from a grey frame |
| The Linux PC (Pop!_OS 24.04), natively, against the Mac's Metal | `test_crt.py` passes. A 30-frame clip's PNG frames are on average 0.80/255 from the Mac's on the GTX 1060 (NVIDIA 580), 0.95/255 on the Intel HD 630, 1.0/255 on lavapipe. `slp2video --model logo --crt` on a 2 s clip: 150 s, with Dolphin, Blender and the CRT on the GTX 1060 |
| Windows | Not yet. `.github/workflows/crt.yml` builds and tests on Windows, Linux and macOS runners when run by hand |
| The Mac, `--runtime blender` against `librashader-cli`'s Metal | Frames 0.003/255 apart on average, for each mask (3 frames of a real clip). Alpha, which ffmpeg merges in either way, identical. `slp2video --crt` on a 60-frame clip: the same video after ProRes, frame for frame |
| The Linux PC, `--runtime blender` | `test_crt.py` passes, Blender's render against `librashader-cli`'s included. On real 3504x2880 CRT frames, OpenGL on the GTX 1060 is 0.0002/255 from `librashader-cli`'s wgpu on the same GPU, every mask ([`docs/report-gpu-crt.md`](../../docs/report-gpu-crt.md)) |

## Linux in Docker

`linux.Dockerfile` is Ubuntu 22.04 with Rust 1.88, Mesa's lavapipe (Vulkan on the CPU) and ffmpeg, to build `librashader-cli` and run the CRT without a GPU:

```sh
docker build -t asv-crt -f tools/crt/linux.Dockerfile tools/crt
docker run --rm -v "$PWD":/repo -v asv-crt-packages:/repo/packages -v asv-crt-cache:/asv asv-crt \
    python3 tools/crt/install_librashader.py
docker run --rm -v "$PWD":/repo -v asv-crt-packages:/repo/packages -v asv-crt-cache:/asv asv-crt \
    python3 tools/crt/test_crt.py
```

On lavapipe, 10 frames at 3840x2880 took 28 s with 4 at a time on 8 CPU threads: fine for tests, slow for whole games.

## Files

| File | |
|---|---|
| `render_video.py` | the renderer: the command, and the functions `slp2video` calls |
| `blender_crt.py` | runs inside Blender: the preset's passes drawn with Blender's `gpu` module, frames through pipes |
| `blender-chain/` | each vendored preset as `librashader-cli` 0.12.1 compiles it (`royale/`, `guest/`, `guest-ntsc/`, `megatron/`), for `blender_crt.py` |
| `vendor_chain.py` | writes `blender-chain/` with `librashader-cli` (`write`), or checks it (`check`), for one shader or all |
| `install_librashader.py` | builds `librashader-cli` and `crt-stream` for this platform into `packages/librashader/` |
| `crt-stream/` | the video through one librashader chain, stdin to stdout (Rust), with two patched librashader runtimes in `vendor/` |
| `slang-shaders/` | the vendored shaders, `MANIFEST` (each file's git blob id) and their README |
| `vendor_shaders.py` | copies the shaders from a slang-shaders checkout (`copy DIR`), or checks the copy (`check`) |
| `test_crt.py` | unit tests: the settings, the runtime order, the encoders, the shader copy and the chain, the BMP frames, and real renders with Blender and with `librashader-cli`, against each other |
| `linux.Dockerfile` | the Linux build and test container |
