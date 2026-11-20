# CRT

CRT Royale on a video: TroggleMonkey's original shader, rendered by [librashader](https://github.com/SnowflakePowered/librashader), on macOS, Linux and Windows. [`slp2video --crt`](../../docs/slp2video.md#the-crt) runs it; it also works on any video by itself.

```sh
python3 tools/crt/install_librashader.py                                       # once: builds librashader-cli (needs Rust)
python3 tools/crt/render_video.py in.mov out.mov --physical-pixels             # each pixel a physical CRT pixel
python3 tools/crt/render_video.py in.mov out.mov --physical-pixels --scale 8 --triads-per-pixel 1
python3 tools/crt/render_video.py in.mp4 out.mov --size 1920x1080 --lines 240  # an emulated 240-line signal
python3 tools/crt/test_crt.py                                                  # includes a real render, if librashader-cli is there
```

`render_video.py` is the crt-royale TouchDesigner project's `tools/render_video.py`, brought into this repo. It has the same options and works out the same settings (mask, triad size, aspect, output size). On the same input and settings it gave exactly the same pixels on the Mac: physical pixels with and without alpha, and standard mode. What changed:

- **The shaders are here**, in [`slang-shaders/`](slang-shaders/README.md): the 38 files of libretro's slang-shaders (commit `2345ee91`) that `crt/crt-royale.slangp` needs, unmodified, with their licences. A frame rendered with them is identical to one rendered with the project's full checkout.
- **The runtime suits the platform.** `--runtime auto` (the default) tries this platform's runtimes in order on the first frame, and keeps the first that draws it at the size asked for: Metal on macOS; Direct3D 11, then 12, wgpu, Vulkan, OpenGL on Windows; wgpu, then Vulkan, OpenGL on Linux. The original always asked for Metal.
- **Frames stream through.** One ffmpeg decodes the video, and the frames go to `librashader-cli` as they come, 4 at a time (`--jobs`). A second ffmpeg encodes them in order as they're drawn. Only the frames in flight are on disk, as BMP files: no PNG compression, which made each frame 0.1 s slower to write and slower again to read back. 150 frames at 3504x2880 with alpha took 30 s instead of 50 on an M1, with identical output.
- **Alpha follows the picture's framing.** The alpha goes through the same filters as the colour. The original took it from the unframed input, which only mattered in standard mode.
- **Only Python's standard library.** ffmpeg is found the way slp2alpha finds it.
- **H.264** (`--codec h264-444`) is CRF 12 at the medium preset, as `slp2video` writes it (the original: CRF 10, slow). ProRes uses Apple's encoder where it works (tried on one frame first), else `prores_ks`.

## librashader-cli

`install_librashader.py` builds `librashader-cli` 0.12.1, the version all of this was checked with, with Rust's cargo into `packages/librashader/`. The build folder stays in the cache folder.

| Platform | Runtimes built | Build time | Also needs |
|---|---|---|---|
| macOS | metal, wgpu | 1.5 min (M1) | Xcode's command line tools |
| Linux | wgpu, vulkan | 4.5 min (M1, in Docker) | `build-essential`; to run, `libvulkan1` and a Vulkan driver: the GPU's, or Mesa's lavapipe |
| Windows | d3d11, wgpu | not built yet | Visual Studio's C++ build tools, with rustup's MSVC toolchain |

- **wgpu is in every build** because librashader-cli 0.12.1 doesn't compile without it: its `transpile` command imports wgpu's shader translator (naga) whatever the features. With `--features vulkan` alone, cargo stops at `use librashader::reflect::naga` [tried in Ubuntu 22.04].
- **Linux draws through wgpu, on Vulkan.** librashader-cli's own Vulkan runtime ignores the size it's asked for (`-d`): it draws and reads back at the input's size (`src/render/vk/mod.rs`). Asked for 3840x2880 from a 640x480 frame, it wrote 640x480. Its wgpu runtime draws at the right size, through Vulkan. `render_video.py` checks every frame's size, so a runtime that gets it wrong is skipped (`auto`) or stops the render.
- **On macOS, wgpu can't draw this preset** (`Unsupported features were requested: PIPELINE_CACHE`), so `auto` uses Metal.
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
| Windows | Not yet. `.github/workflows/crt.yml` builds and tests on Windows, Linux and macOS runners when run by hand |

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
| `install_librashader.py` | builds `librashader-cli` for this platform into `packages/librashader/` |
| `slang-shaders/` | the vendored shaders, `MANIFEST` (each file's git blob id) and their README |
| `vendor_shaders.py` | copies the shaders from a slang-shaders checkout (`copy DIR`), or checks the copy (`check`) |
| `test_crt.py` | unit tests: the settings, the runtime order, the shader copy, the BMP frames, and a real render |
| `linux.Dockerfile` | the Linux build and test container |
