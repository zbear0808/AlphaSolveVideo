# AlphaSolveVideo

This repo holds scripts that, when combined with high quality recordings and special gecko codes in SSBM, can extract high quality transparent foreground content from the game.

![Animated gif example of Battlefield](Resources/Readme%20Examples/sideBySide.gif)

To apply the technique to images instead of video recordings, see [PdnAlphaSolve](https://github.com/NeilHarbin0/PdnAlphaSolve).

**EPILEPSY WARNING: Included example videos within the Resources folder as well as videos required for this technique contain constant black and white strobing at 30Hz and may present risks to individuals with epilepsy.**

## Automated Replay Rendering (`slp2alpha`, `slp2video`)

An unattended CLI pipeline that renders Slippi replays (`.slp`) directly to transparent video (ProRes 4444 `.mov` with alpha), with a headless Dolphin build: Apple Silicon Macs and Linux PCs today, Windows in progress. [Install](#install) has the steps for each platform.

```sh
cd tools/slp2alpha
python3 -m slp2alpha render replay.slp --characters-only
```

- **One command for everything:** [`tools/slp2video`](tools/slp2video/README.md) takes a replay to a finished video: your logo or sprite on the Shy Guys, your 3D model in place of the stage (fixed or moving camera), the background kept or removed, transparency or a colour, regular Melee or Animelee, and a CRT finish at the console's native resolution ([guide](docs/slp2video.md)). The CRT is [`tools/crt`](tools/crt/README.md): crt-guest-advanced (or its NTSC version, Sony Megatron v2 or CRT Royale, `--crt-shader`), the original shaders in this repo, drawn by Blender or librashader on Metal, Direct3D 11 or Vulkan:

  ```sh
  python3 tools/slp2video/slp2video.py replay.slp --model statue.glb --animelee --crt
  ```

- **Features:**
  - `--characters-only`: hides the stage and particles; works across all legal stages.
  - `--keep-background`: records the game as it looks, background and all, as an ordinary opaque video; works on every stage.
  - `--static-camera`: locks the camera in fixed mode for still framing.
  - `--start-frame N --end-frame M`: renders combo clips directly from Slippi frame numbers.
  - `--shy-guy-sprite IMAGE`: draws Yoshi's Story Shy Guys with your own image or logo.
  - `--nametag P1=TEXT`, `--no-nametags`: changes what players' name tags say, or hides them ([guide](docs/nametags.md)).
  - `--animelee`: renders with Animelee cel-shaded skins.
  - `--export-camera`: also writes Melee's camera on every frame, for Blender ([`tools/camera-export`](tools/camera-export/README.md)).
  - `--raw-resolution`: records the console's unstretched 640x480 picture, one row per scanline (for CRT effects).
- **Documentation & Research:** See the [**Documentation Index**](docs/README.md) for feature guides, reverse engineering research, and architecture plans.
- **Testing:** See [`tools/render-tests/`](tools/render-tests/README.md) for the regression test harness.
- **Reverse Engineering & Probes:** See [`research/`](research/README.md) for calibration and probe tools.
- **Windows:** the Windows build of the headless Dolphin works: [`tools/dolphin-build/build-windows-mainline.py`](tools/dolphin-build/build-windows-mainline.py), run by the "Windows playback Dolphin" GitHub Actions workflow. Nothing has rendered on Windows yet; [`docs/plan-windows-remaining.md`](docs/plan-windows-remaining.md) lists what's left to try on a Windows PC.

## Install

### Platforms

| | Render (`slp2alpha`) | Model (`--model`, Blender) | CRT (`--crt`) | `slp2video`, whole |
|---|---|---|---|---|
| **macOS, Apple Silicon** | Verified | Verified | Verified: Blender (Metal), `crt-stream`, `librashader-cli` | Verified |
| **Linux x86_64** (checked on Pop!_OS 24.04, GTX 1060, NVIDIA driver 580) | Verified (Vulkan) | Verified (Blender 5.2.3) | Verified: Blender (OpenGL), `crt-stream` (wgpu on Vulkan), `librashader-cli` | Verified |
| **Linux arm64** | Dolphin's build is in the "Linux playback Dolphin" workflow, which hasn't been run yet; not rendered | No: Blender has no official arm64 Linux build | Verified in Docker (Ubuntu 22.04, Mesa's lavapipe) | Not run |
| **Windows x86_64** | Dolphin builds on GitHub Actions (run 44375644193, 18 November); not rendered yet | Not run | Not run: `crt-stream`, then `librashader-cli` (built and tested by `.github/workflows/crt.yml` when run by hand) | Not run |

### Every platform

- **Python 3.9 or newer.** The render, the model, the composite and the CRT need only Python's standard library. numpy and Pillow are needed only for the camera checks (`pip install numpy pillow`).
- **A Melee NTSC 1.02 ISO** (`GALE01`, revision 2). It's found as given with `--iso PATH`, then `$SLP2ALPHA_ISO`, then the Slippi Launcher's setting (its `Settings` file, `settings.isoPath`).
- **The repo, with LF line endings.** Dolphin's patches don't apply with CRLF, so on Windows set `git config --global core.autocrlf false` first.

  ```sh
  git clone https://github.com/zbear0808/AlphaSolveVideo.git
  cd AlphaSolveVideo
  ```
- **Where things go:**
  - Programs go in `packages/` (gitignored): Dolphin in `packages/slippi-playback-mainline/`, and the CRT's `librashader-cli` and `crt-stream` in `packages/librashader/bin/`.
  - Builds and downloads go in the cache folder: `~/Library/Caches/AlphaSolveVideo` on macOS, `~/.cache/AlphaSolveVideo` on Linux, `%LOCALAPPDATA%\AlphaSolveVideo` on Windows. `$ALPHASOLVE_CACHE` moves it.
- **Each program is found** as given (`--dolphin`, `--ffmpeg`, `--blender`, `--librashader`, `--crt-stream`), then through an environment variable (`SLP2ALPHA_DOLPHIN`, `ALPHASOLVE_FFMPEG_DIR`, `BLENDER`, `LIBRASHADER_CLI`, `CRT_STREAM`), then in `packages/`, then on the PATH.

### macOS (Apple Silicon)

1. **Tools:** Xcode (the build was checked with Xcode 27.1), [Homebrew](https://brew.sh), and Rust:

   ```sh
   xcode-select --install
   brew install ffmpeg pkgconf
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```

   ffmpeg 9.0 is the version checked; it's found in `/opt/homebrew/bin`.
2. **The headless Dolphin**, built from source. It takes about 7 minutes on an M1. The script installs Rust 1.88.0, CMake 3.31 and its own FFmpeg libraries:

   ```sh
   tools/dolphin-build/build-mac-mainline.sh
   ```

   It writes `packages/slippi-playback-mainline/Slippi Dolphin.app`.
3. **Blender 5.2** from [blender.org](https://www.blender.org/download/), in `/Applications` or `~/Applications`. It's needed for `--model`, and it draws the CRT (`gpu.init` in the background is new in 5.2).
4. **The CRT's librashader programs:** `crt-stream`, and `librashader-cli` 0.12.1. They're needed without Blender, and for the CRT's tests. Building them takes about 3 minutes on an M1:

   ```sh
   python3 tools/crt/install_librashader.py
   ```
5. **The ISO:** set it in the Slippi Launcher, or `export SLP2ALPHA_ISO=/path/to/melee.iso`.

### Linux (x86_64)

1. **Build tools** (Debian or Ubuntu) and Rust:

   ```sh
   sudo apt install build-essential git curl ca-certificates xz-utils pkg-config python3 python3-venv nasm \
       zlib1g-dev libasound2-dev libegl-dev libvulkan1
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```

   To run, Dolphin needs glibc 2.35 or newer, `libegl1`, `libasound2` (`libasound2t64` on Ubuntu 24.04) and a Vulkan driver: the GPU's, or Mesa's (`mesa-vulkan-drivers`). The NVIDIA PC uses driver 580.
2. **ffmpeg for the solver:** a static build from [BtbN's FFmpeg builds](https://github.com/BtbN/FFmpeg-Builds/releases), `linux64-gpl-9.0`. Unpack it and point `ALPHASOLVE_FFMPEG_DIR` at the folder with `ffmpeg` and `ffprobe` in it, or put the two programs straight into `packages/ffmpeg/`. Distributions' own ffmpeg (4.4, 6.1) isn't tested.
   - With an NVIDIA GTX 10-series card, use BtbN's 8.1 build instead (`linux64-gpl-8.1`). FFmpeg 9.0's NVENC needs driver 610, and those cards stop at 580.
   - Don't use `packages/ffmpeg/` in a checkout a Mac also uses: the Mac looks there first, and would find a Linux program.
3. **The headless Dolphin.** Any one of these:
   - **In Docker**, no root needed. This is how the PC's package was built:

     ```sh
     docker build -t asv-linux -f tools/dolphin-build/linux.Dockerfile tools/dolphin-build
     mkdir -p ~/.cache/AlphaSolveVideo-docker
     docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/repo -v ~/.cache/AlphaSolveVideo-docker:/asv asv-linux \
         python3 tools/dolphin-build/build-linux-mainline.py
     ```
   - **On the machine itself:** `python3 tools/dolphin-build/build-linux-mainline.py`. CMake, Ninja and patchelf come from pip, into a venv.
   - **From GitHub Actions** (the workflow is written but hasn't been run yet):
     1. Run "Linux playback Dolphin" (`gh workflow run dolphin-linux.yml`).
     2. Download the `slippi-playback-mainline-linux-x86_64` artifact and unzip it.
     3. Unpack it: `tar -xzf slippi-playback-mainline-linux-x86_64.tar.gz -C packages`.

   Each way writes `packages/slippi-playback-mainline/dolphin-emu-nogui` with its libraries. Without a display it runs on EGL's surfaceless platform, on Vulkan; `--backend OGL` is the fallback.
4. **Blender 5.2** from [blender.org](https://www.blender.org/download/): unpack it, for example into `~/.local/opt`, and link it as `~/.local/bin/blender`, which is searched even when a plain SSH command doesn't put it on the PATH. The CRT runs on its OpenGL backend, without a display.
5. **The CRT's librashader programs** (about 4 minutes each on the PC):

   ```sh
   python3 tools/crt/install_librashader.py
   ```
6. **The ISO:** `export SLP2ALPHA_ISO=/path/to/melee.iso`, or the Slippi Launcher's setting.
7. **On a laptop with two GPUs,** Vulkan programs take the first one listed. `VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json` leaves them only NVIDIA's.

### Linux (arm64)

The same as x86_64, except:

- **ffmpeg:** BtbN's `linuxarm64-gpl-9.0`.
- **Dolphin:** the Actions artifact is `slippi-playback-mainline-linux-aarch64`.
- **No Blender**, so no `--model`. The CRT is drawn by `crt-stream` or `librashader-cli`.

A render on arm64 hasn't been tried yet.

### Windows (x86_64)

Nothing has rendered on Windows yet. These are the steps the code and [`docs/plan-windows-remaining.md`](docs/plan-windows-remaining.md) expect:

1. **Tools:**
   - Visual Studio 2022 or its Build Tools, with "Desktop development with C++";
   - Git, with `git config --global core.autocrlf false` set before cloning;
   - Python (`winget install Python.Python.3.12`);
   - Rust from [rustup.rs](https://rustup.rs) (the MSVC toolchain).
2. **ffmpeg 9.0:** `winget install Gyan.FFmpeg`, or the contents of the `bin\` folder of BtbN's `win64-gpl-9.0` zip in `packages\ffmpeg\`.
3. **The headless Dolphin.** Either way it lands in `packages\slippi-playback-mainline\`:
   - **From GitHub Actions** (about 15 minutes): run "Windows playback Dolphin" (`gh workflow run dolphin-windows.yml`), then

     ```bat
     gh run download --name slippi-playback-mainline-windows --dir packages/slippi-playback-mainline
     ```
   - **On the PC** (about 20–40 minutes). A short `ALPHASOLVE_CACHE` keeps the Rust build's paths under Windows' 260-character limit:

     ```bat
     set ALPHASOLVE_CACHE=C:\asv
     py tools\dolphin-build\build-windows-mainline.py
     ```

   If Windows marks the downloaded files as blocked: `Get-ChildItem -Recurse packages | Unblock-File`.
4. **The CRT's librashader programs:** `py tools\crt\install_librashader.py`. Blender doesn't draw the CRT on Windows yet: it gets its frames through inherited pipes, which Python passes on macOS and Linux only. So `crt-stream` draws it there, with guest's afterglow, then `librashader-cli`.
5. **Blender 5.2** (for `--model`) is found in Program Files or Steam.

The `gh` commands act on the repo `gh` picks, which in a fork's checkout may be upstream's. Add `-R YOUR_NAME/AlphaSolveVideo` to run a workflow in your fork, where Actions must be turned on first.

### Check it works

```sh
python3 tools/slp2alpha/test_slp.py                       # the render's logic; no Dolphin needed
python3 tools/slp2video/test_slp2video.py                 # what each option does; nothing else needed
python3 tools/crt/test_crt.py                             # the CRT, with real renders by whatever is installed
python3 tools/render-tests/run.py --fetch-only            # download the test replays into the cache folder
cd tools/slp2alpha && python3 -m slp2alpha render ~/Library/Caches/AlphaSolveVideo/test-replays/DishonestMuddyCoyote.slp \
    --characters-only --start-frame 1500 --end-frame 1799  # about 11 s on an M1 (use your platform's cache folder)
```

Then the whole chain: `python3 tools/slp2video/slp2video.py REPLAY.slp --keep-background --crt`. [`docs/slp2video.md`](docs/slp2video.md) has the rest of its options. Once the "CRT renderer" workflow (`.github/workflows/crt.yml`) has been run, its artifacts (`librashader-cli-<platform>`) can go in `packages/librashader/bin/` instead of building the programs. It hasn't been run yet. Artifacts don't keep file permissions, so on macOS and Linux run `chmod +x packages/librashader/bin/*` after unpacking.

## Classic Manual Workflow (Windows Batch Scripts)
Download the latest release zip from the [releases page](https://github.com/NeilHarbin0/AlphaSolveVideo/releases). Extract the zip to preferably a dedicated folder. 

1. You will need Dolphin emulator that supports lossless .avi output via framedump. Tested and working with Dolphin 5.0-17995. Find output path under `Options` -> `Configuration` -> `Paths` -> `Dump Path`.

2. Set up your SSBM gecko codes to include and enable all required codes (only Dreamland and BF background disabling codes included by default). [Required codes](Resources/Required%20Codes.txt) can be found in the Resources folder.

    - `Increase Input Timing Accuracy` will ensure black->white frame pairs always stay in the same order
    - `(EPILEPSY WARNING) Flicker Background Black/White` will flash the screen black/white each physics frame to enable the alpha solving technique
      - This code includes a modified 120 FPS mode code to allow two separate frames with different background colors without physics advancing, as the normal 120 FPS code doesn't work with Slippi playback
    - Disable background codes are required so that the flickering background can be seen
    - `Reduce Debug Develop` lag code ensures accurate frame information in rare situations
    - [Optional codes](Resources/Optional%20Codes.txt) that can help or improve quality of documented content are also available in the same Resources folder.

3. Record gameplay via `Dolphin Movie` -> `Dump Frames`, selecting it again when you want to stop recording. The quality offered by this feature is important as the solver is sensitive to small artifacts that may appear with other recording techniques, especially when the recording is not perfectly synchronized, and frames are skipped.

   - `Use Lossless Codec (FFV1)` or similar should be enabled in `Options` -> `Graphics Settings` -> `Advanced` -> `Frame Dumping` if it is not already checked by default
     - If using Slippi Dolphin, you can enable FFV1 in the `GFX.ini` located in the applications config folder `%AppData%\Slippi Launcher\playback\User\Config` like `UseFFV1 = True`
   - Ensure the first few frames show at least a miniscule physics change visible to the naked eye. Do not begin the recording in frame advance mode, paused, or in a near motionless animation.
   - Ensure the first two frames contain at least a small portion of background color visible. Do not begin the recording in menus, or extremely zoomed into to stage/character geometry.

4. Drag and drop the recording on one of the various `SolveTo???.bat` scripts depending on the type of output file you desire (default animated png). This will generate several files in the directory of the dragged video file for the alpha map and transparent outputs. Several intermediate files will also be created and deleted in the same location during the process.

    - Small example videos are available in the Resources folder which can be used to drag and drop

5. Hopefully wherever you plan to use the output files supports transparency for that specific file.

    - Animated png is recommended for high quality short content like documentation, though browser support varies.
    - Discord has some support for embedded webm, though the quality of the webm output often has worse artifacts than other formats.
    - Other formats are to hopefully cover various video editing software for content creators.
  
## Optional

1. Set Dolphin `Options` -> `Configuration` -> `General` -> `Speed Limit` to 200%. This will allow the game to run at seemingly normal speed aside from audio, and can help reduce the harshness of the strobing effect to the eye as long as your monitor supports the higher fps. Unfortunately, dumping frames will likely tank FPS back down substantially.
2. Reduce Dolphin window size to a smaller reasonable resolution, or dump at a smaller internal resolution via `Options` -> `Graphics Settings` -> `Enhancements`-> `Internal Resolutions` and `Options` -> `Graphics Settings` -> `Advanced` -> `Frame Dumping` -> `Dump at Internal Resolution`. A 30 second 720p frame dumped video can be around 250MB, with higher resolutions costing even more. Large resolutions will work, it will just make large files that take much longer to process.

## The Technique
The following process is applied to each frame pair in the video.

Two source frames with black and white backgrounds are used to solve for the proper transparency of the subject.

<img src='Resources/Readme%20Examples/ExSourceBlack.png?raw=true' width='400'><img src='Resources/Readme%20Examples/ExSourceWhite.png?raw=true' width='400'>

The technique can produce an alpha map and the fully transparent subject.

<img src='Resources/Readme%20Examples/MethodAlphaSolveMap.png?raw=true' width='400'><img src='Resources/Readme%20Examples/MethodAlphaSolve.png?raw=true' width='400'>

For the video solving script, there is a bit of detection in seeing if the first frame is black or white, followed by detection of black->white or white->black pairs. With this information, the specific frames that need to be compared are known, extracted from the video, and used to generate the outputs.

![Solved Transparency](Resources/Readme%20Examples/Demo.png?raw=true)

*Warning: It is possible that pair detection fails, leading to strange chromatic edged outputs or ghosting. Please ensure the first 3 frames of the video contain at least a tiny bit of visible physics change. Otherwise you can try temporarily swapping swapping :firstPair and :secondPair labels in AlphaSolve.bat.*

*Warning: It is possible that background color detection can fail. This can lead to strange white outlines around subject content, and certain particle effects losing all of their color. If this happens to you, please let me know. Otherwise you can try temporarily swapping swapping :isBlack and :isWhite labels in AlphaSolve.bat.*

## Other "Worse" Approaches
Below are images of other approaches which generally miss partial transparency, leading to the inability to place your transparent image onto any background with accurate color. They also tend to break down at low resolutions around the edges.

*Note: Images are displayed with a checkered background for demonstration purposes, normally they would be transparent.*

### Greenscreen

![Greenscreen Method](Resources/Readme%20Examples/MethodGreenScreen.png?raw=true)
- Green edge glow
- Innacurate or missing partial transparency

### Magic Wand

![Magic Wand Method](Resources/Readme%20Examples/MethodWand.png?raw=true)

- Innacurate and sometimes jagged edges
- No partial transparency
