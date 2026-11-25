# CRT

A CRT on a video: the original shaders, drawn by Blender's GPU module or by [librashader](https://github.com/SnowflakePowered/librashader), on macOS, Linux and Windows. crt-guest-advanced by default, or its NTSC version, Sony Megatron v2 or CRT Royale. [`slp2video --crt`](../../docs/slp2video.md#the-crt) runs it; it also works on any video by itself.

```sh
python3 tools/crt/render_video.py in.mov out.mov --physical-pixels             # each pixel a physical CRT pixel
python3 tools/crt/render_video.py in.mov out.mov --physical-pixels --scale 8 --triads-per-pixel 1
python3 tools/crt/render_video.py in.mp4 out.mov --size 1920x1080 --lines 240  # an emulated 240-line signal
python3 tools/crt/render_video.py in.mov out.mov --shader royale --mask slot   # another shader, another look
python3 tools/crt/render_video.py --list-masks                                 # each shader's looks
python3 tools/crt/install_librashader.py                                       # librashader-cli, for Windows and the tests (needs Rust)
python3 tools/crt/test_crt.py                                                  # includes real renders, with what's installed
```

## The shaders

`--shader` picks one, `--mask` one of its looks. Each shader's default look is `grille`, an aperture grille. `--params` adds more of the shader's own parameters after the look's, and replaces any of the look's it names.

| `--shader` | Shader | Looks (`--mask`) | Light kept | Across frames |
|---|---|---|---|---|
| `guest` (default) | crt-guest-advanced, by guest(r) | 12: `grille`, `grille-soft`, `grille-strong`, `grille-wide`, `slot`, `shadow`, `cgwg`, `lottes-grille`, `lottes-shadow`, `rgbx`, `rrggbbx`, `none` | 57–72% (`grille`) | afterglow |
| `guest-ntsc` | its NTSC version: a composite signal in front of the same CRT, with its colour fringes and bleed | the same 12 | about guest's | afterglow, and the chroma phase alternates every frame |
| `megatron` | Sony Megatron Colour Video Monitor v2, by MajorPainTheCactus, in SDR | `grille`, `slot`, `shadow`, `grille3`, and 4 real monitors: `pvm2730`, `pvm20l4`, `pvm1910`, `mx8000` | 19–20% (`grille`), 25–27% (`grille3`, `shadow`) | nothing |
| `royale` | CRT Royale, by TroggleMonkey: this folder's only shader before 25 November 2026 | `grille`, `slot`, `shadow` | 83–94% | nothing |

- **Where the settings come from.** [`shaders.py`](shaders.py) has a profile for each shader: its preset, its Blender chain, its looks, and the parameters a look takes at a given size. They are the crt-royale TouchDesigner project's render profiles (`pipelines/<name>/video.py`), which worked them out against the original shaders. For every look, in five sizes (slp2video's, the standard 1280, 1920x1080, 8x physical pixels and a 2.5 px triad), `shaders.py` writes the same parameter string as the project's own modules [verified: `test_shaders.py`]. Royale's are exactly what `render_video.py` wrote before: on the same clip, `--shader royale` gives the same frames as the previous version, decoded from ProRes, with Blender and with `librashader-cli`'s Metal [verified, 25 November].
- **The light kept** is the picture's mean light against the source's, linear, on the TouchDesigner project's test card, jellybeans and movie frame [reported: its `pipelines/*/README.md`]. guest's looks keep from 45–51% (`grille-strong`) to 86–91% (`cgwg`), and 99% with no mask. guest adds its blurred picture back through the mask (`bloom 0.5`, `bmask1 1`), which brightens it without washing out the stripes.
- **Megatron is dark in SDR, on purpose.** Its mask is binary and at full strength: each output pixel lights one primary, so about three quarters of the light is gone. The shader expects an HDR display to make up for it. It's kept faithful here: a neutral 2.2 transfer (`hcrt_colour_space 2`, as upstream's SDR preset) and `hcrt_brightness` at least 0.2, which keeps the tone curve neutral, nothing more. Turn the display up. Its mask is drawn per output pixel, so play its videos at 100% or an integer zoom; ProRes 4444 at `-qscale:v 2` keeps it, 4:2:0 codecs don't [reported].
- **The triad pitch.** Royale's triad is 3 px at 1280 px wide, scaled with the width, or the pitch asked for. guest's mask period follows the smaller side (3 px at 1280), or matches the pitch asked for exactly (`masksize`, `mask_zoom`). Megatron's patterns are fixed: a pitch picks the nearest of the look's screen type (grille 3, 4, 5, 7 or 13 px; shadow mask 6 or 12; slot mask 3, 4, 5 or 7). At slp2video's 3 px, its `grille` (4 px R G B X) becomes the 3 px R G B grille, `grille3`'s.
- **Scanlines and aspect.** guest and Megatron draw one beam per source row by design, and have no aspect parameter: the picture fills the CRT, so `--aspect` only changes the output size. Royale gets the aspect.

### The afterglow

guest's phosphors glow on for a few frames after the beam has gone: a white field turned black falls 222.4 → 35.7, 28.8, 22.6, … and is gone after 15 frames. It only shows below 8/255, on dark trails behind bright things [reported: the TouchDesigner project's `temporal_results.json`]. Blender keeps it from frame to frame. `--no-afterglow` draws guest and guest-ntsc without it: `AS=0`, the afterglow's strength in `pre-shaders-afterglow.slang`. Each frame is then drawn as if it were the first. The other shaders have no afterglow, so it changes nothing there.

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
- **Only the vendored presets,** each with its chain in `blender-chain/<shader>/`. `--preset` with any other goes to `librashader-cli`, with `--shader`'s parameters. So does Windows for now: Blender gets the frames through inherited pipes, which `subprocess` passes on macOS and Linux only.

`render_video.py` is the crt-royale TouchDesigner project's `tools/render_video.py`, brought into this repo. It has the same options and works out the same settings (mask, triad size, aspect, output size). On the same input and settings it gave exactly the same pixels on the Mac: physical pixels with and without alpha, and standard mode. What changed:

- **The shaders are here**, in [`slang-shaders/`](slang-shaders/README.md): the files of libretro's slang-shaders (commit `2345ee91`) that the four presets need, unmodified, with their licences. A frame rendered with them is identical to one rendered with the project's full checkout.
- **guest is the default.** The project's script drew Royale unless told otherwise. Its other profiles came over as `--shader` (above).
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
- **Each frame is drawn in a fresh chain,** so nothing carries over from one frame to the next:
  - **guest** loses its afterglow. `render_video.py` says so once and goes on. Without Blender, that's the price; it only shows below 8/255.
  - **guest-ntsc** needs the frame's parity for its chroma phase. `librashader-cli render -f N` draws the same frame N + 1 times, the last with frame count N, so odd frames are drawn with `-f 1`. That alternates the phase as one chain does: on a still picture 584 wide, frames 0 and 2 come out identical, 0 and 1 apart (24.7 dB PSNR), and a 3504x2880 frame took 0.35 s instead of 0.32 on an M1 [verified, 25 November]. Below 301 source pixels the NTSC passes use 3 phases and merge both fields, so the frames don't alternate at all.
  - **Megatron and Royale** keep nothing, so they come out as they would in one chain.

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
| `shaders.py` | the shaders: each one's preset, chain, looks and parameters (`--shader`, `--mask`, `--list-masks`) |
| `blender_crt.py` | runs inside Blender: the preset's passes drawn with Blender's `gpu` module, frames through pipes |
| `blender-chain/` | each vendored preset as `librashader-cli` 0.12.1 compiles it (`royale/`, `guest/`, `guest-ntsc/`, `megatron/`), for `blender_crt.py` |
| `vendor_chain.py` | writes `blender-chain/` with `librashader-cli` (`write`), or checks it (`check`), for one shader or all |
| `install_librashader.py` | builds `librashader-cli` for this platform into `packages/librashader/` |
| `slang-shaders/` | the vendored shaders, `MANIFEST` (each file's git blob id) and their README |
| `vendor_shaders.py` | copies the shaders from a slang-shaders checkout (`copy DIR`), or checks the copy (`check`) |
| `test_crt.py` | unit tests: the settings, the runtime order, the encoders, the shader copy and the chain, the BMP frames, and real renders with Blender and with `librashader-cli`, against each other. It runs `test_shaders.py` too |
| `test_shaders.py` | the profiles against the TouchDesigner project's parameters, the looks checked per shader, `--no-afterglow`, the chain per shader, and guest-ntsc's phase through `librashader-cli` |
| `linux.Dockerfile` | the Linux build and test container |
