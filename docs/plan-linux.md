# Linux: the patched mainline Dolphin, slp2alpha and a GitHub Actions build

Status: plan, November 2026. Nothing here is implemented yet. It covers bringing the headless mainline Dolphin and slp2alpha to Linux, as [`plan-windows-mainline.md`](plan-windows-mainline.md) did for Windows, and a GitHub Actions workflow that builds the Linux package. The source facts come from the pinned Dolphin checkout (`~/Library/Caches/AlphaSolveVideo/mainline`, commit `c5f6359`, with this repo's patches 0001–0006 applied). The Docker facts were measured on this Mac.

Evidence tags:

- **[verified]**: read in source, or measured on this Mac or on GitHub, during this investigation.
- **[reported]**: found in documentation or release listings; not re-checked by hand.
- **[estimate]**: needs a measurement.
- **[to test]**: needs an experiment on Linux before we rely on it.

---

## 1. Summary

- **Goal.** On Linux, `python3 -m slp2alpha render game.slp --export-camera` works as it does on macOS: no window, the same three files, the same checks passing. Both x86_64, which most Linux PCs are, and arm64, which Docker runs natively on this Mac.
- **The source already builds on Linux.** Slippi's CI built this exact commit for Linux on `ubuntu-22.04`, and its Playback job passed in 19 minutes [verified: GitHub check runs for `c5f6359`]. That job builds the Qt program (`dolphin-emu`). We need the console program (`dolphin-nogui`) from the same tree, as on Windows.
- **Linux is closer to macOS than Windows is:**
  - slp2alpha's macOS code already does what Linux needs: it starts Dolphin in its own session, and stops it with SIGTERM, then SIGKILL [verified: `runner.py`].
  - NoGUI handles SIGTERM on Linux the same way as on macOS (`MainNoGUI.cpp:350–355`) [verified].
  - Dolphin's GCC builds don't turn warnings into errors, unlike MSVC's `/WX` [verified: its compiler flags].
- **What differs from macOS:**
  1. **The video backend.** Vulkan without a surface instead of Metal, with OpenGL through EGL as the fallback (section 3.5).
  2. **FFmpeg.** The Mac's minimal FFmpeg 8.1.3, built by the same script with a few Linux changes (section 3.3).
  3. **The package.** A folder with the program, its libraries (found through `$ORIGIN`) and `Sys/`. It ships as a `.tar.gz`, because GitHub's artifacts lose the executable bit (section 3.6).
  4. **The oldest Linux it runs on.** That's set by the glibc it's built against. Building in an Ubuntu 22.04 container gives glibc 2.35 (section 3.1).
  5. **slp2alpha.** Small changes: find the Linux build, default to Vulkan, give Linux install hints (section 5).
- **No Linux PC is needed to test it.**
  - Docker on this Mac runs arm64 Linux natively [verified: Docker Desktop's VM is `linux/arm64`]. There, Dolphin would run the same ARM64 recompiler as the Mac build, and Mesa would render on the CPU.
  - The whole pipeline can run in a container, including the camera comparison against the Mac's export (section 6).
  - A Linux PC with a GPU only adds real GPU drivers and x86_64 speed (section 7).
- **GitHub Actions.** A new workflow, `.github/workflows/dolphin-linux.yml`, started by hand like the Windows one (section 4). It:
  - builds x86_64 and arm64 packages;
  - checks their libraries and `--help`;
  - checks that they start on six distributions.
- **What it adds:**
  - `tools/dolphin-build/build-linux-mainline.py`, sharing its fetch and patch code with the Windows script;
  - Linux branches in `build-ffmpeg.sh`;
  - the workflow;
  - `tools/dolphin-build/linux.Dockerfile`, for testing;
  - the slp2alpha changes.
- **Effort.** About 3–4 days. Everything except section 7 can be done from this Mac.

## 2. What changes from macOS and Windows

| Piece | macOS (works today) | Windows (builds on CI) | Linux |
|---|---|---|---|
| Dolphin source | `c5f6359` plus patches 0001–0006 | The same | The same; no new patch expected |
| Compiler | AppleClang | MSVC 2022 with `/W4 /WX` | GCC 11 (Ubuntu 22.04's); warnings aren't errors |
| Rust | 1.88.0 | 1.88.0 | 1.88.0, `x86_64-` or `aarch64-unknown-linux-gnu` |
| FFmpeg inside Dolphin | Our FFmpeg 8.1.3 (`build-ffmpeg.sh`) | BtbN's FFmpeg 8.1 DLLs | Our FFmpeg 8.1.3, as on macOS |
| Video backend | Metal, with no layer | Direct3D 11, with no swap chain | Vulkan, with no surface; OpenGL through EGL as the fallback |
| Window | None (`-p headless`) | None | None |
| Stopping Dolphin | SIGTERM to its process group | Ctrl+Break (patch 0005) | SIGTERM, as on macOS |
| `Sys` | Inside the app | Next to the program | Next to the program (`LINUX_LOCAL_DEV`) |
| Package | `Slippi Dolphin.app` | A folder, in a zip artifact | A folder, in a `.tar.gz` |
| Needed from the system | Nothing extra | Nothing extra (the VC++ runtime ships in the folder) | glibc 2.35 or newer, `libEGL.so.1`, `libasound.so.2`, a Vulkan driver |
| slp2alpha | As it is | Done | Small changes (section 5) |

## 3. The Dolphin build

### 3.1 Base system and toolchain

- **Build on Ubuntu 22.04,** in a container:
  - It's what Slippi's CI builds this commit on [verified: `.github/workflows/main.yml`]. Dolphin needs GCC 11 or Clang 14 (`CMakeLists.txt:59–60`) [verified]. GCC 11 is Ubuntu 22.04's compiler [reported].
  - A program built there needs glibc 2.35 or newer [verified: `ldd --version` in `ubuntu:22.04` gives 2.35]. That covers Ubuntu 22.04 and later, Debian 12 and later, and current Fedora and Arch [reported].
  - GitHub's `ubuntu-22.04` runners have been deprecated since 17 September 2026, and stop on 17 April 2027 [reported: actions/runner-images issue 14254]. So CI runs an `ubuntu:22.04` *container* on an `ubuntu-24.04` runner. The container image doesn't depend on the runner's lifetime.
  - When 22.04 is too old to keep, `debian:12` (glibc 2.36, GCC 12) is the next base [reported].
- **Packages** (Ubuntu names): `build-essential git pkg-config curl ca-certificates xz-utils python3 python3-venv nasm zlib1g-dev libasound2-dev libegl-dev`. The less obvious ones:
  - **`zlib1g-dev`:** NoGUI links `z` by name, and patch 0006 drops it only on Windows [verified]. Without it, the link fails as Windows' first CI run did.
  - **`libasound2-dev`:** the Rust extensions' jukebox plays music through rodio, cpal and `alsa-sys`. At build time, `alsa-sys` finds ALSA through pkg-config [verified: `Cargo.lock`]. Without it, the Rust build stops.
  - **`libegl-dev`:** for the OpenGL fallback. The `common` library links libEGL (`Source/Core/Common/CMakeLists.txt:304`) [verified].
  - **`python3-venv`:** Ubuntu ships `venv` as a separate package [reported]. The script installs CMake 3.31, Ninja and patchelf into a venv, as the other build scripts do with CMake and Ninja.
- **Not needed with this build's switches** (section 3.4): X11, libudev, libevdev, Qt, PulseAudio, BlueZ.
  - Slippi's CI installs 37 packages [verified].
  - Most are for Qt, X11 and the AppImage, or are system copies of libraries. `USE_SYSTEM_LIBS=OFF` takes those from Dolphin's bundled copies instead.
- **No OpenSSL.** The Rust extensions use rustls (`ureq` 2.12 with `rustls` and `ring`) [verified: `Cargo.lock`], so there's no OpenSSL version to match.
- **Rust 1.88.0** through rustup [verified: `rust-toolchain.toml`]. **CMake 3.31** with `-DCMAKE_POLICY_VERSION_MINIMUM=3.5`, as on macOS and Windows.
- **Disk and memory.**
  - The build needs about 2 GB, as on the Mac [estimate]. Skip the `Externals/Qt` submodule (378 MB), as Windows does [verified: its size].
  - Docker on this Mac has 7.9 GB of memory [verified], so build there with `JOBS=4`, not 8 [estimate].

### 3.2 Source and patches

- **Fetch and patch as on Windows:**
  1. Fetch `c5f6359` at depth 1.
  2. Fetch the submodules.
  3. Run the patch loop that finds the last patch already applied.
- **The six patches on Linux** [verified: diffs read]:
  - 0001 still passes `-fno-ipa-sra` to GCC, as upstream does.
  - 0002 and 0004 have no platform-specific code. They've compiled with AppleClang and MSVC; GCC 11 is [to test].
  - 0003 is a fmt change that's harmless under GCC.
  - 0005 is Windows-only code (`_WIN32`).
  - 0006 keeps linking `z` on Linux, hence `zlib1g-dev`.
- **No new patch is expected.** If GCC rejects something, CI gives the file and line, and the fix goes into a patch, as before.

### 3.3 FFmpeg

slp2alpha records FFV1 video in Matroska (`DumpFormat = mkv`), so Dolphin's FFmpeg needs the Matroska muxer [verified: `config.py`].

| Option | How | For | Against |
|---|---|---|---|
| **L-F1** Our minimal FFmpeg 8.1.3 (recommended) | `build-ffmpeg.sh`, the Mac's script, with Linux branches | The same FFmpeg as the Mac; small [estimate: under 10 MB]; a few minutes to build [estimate] | One more build step |
| **L-F2** BtbN's `lgpl-shared-8.1` build | As on Windows | Nothing to compile. Their 31 October build has `linux64` and `linuxarm64` versions [verified: the release listing] | About 130 MB unpacked [estimate: Windows' five DLLs are 128 MB]; another download to pin |
| **L-F3** The distribution's FFmpeg | `libavcodec-dev` and the rest, as Slippi's CI does | Nothing to build | The program then needs that release's FFmpeg libraries, so it only suits a build for the same machine |

- **What L-F1 contains** [verified: `build-ffmpeg.sh`]:
  - the FFV1, Ut Video and MPEG-4 encoders;
  - the AVI, Matroska and MOV muxers;
  - only the `file` protocol;
  - no GPL parts (it doesn't pass `--enable-gpl`).
- **Changes to `build-ffmpeg.sh`:**
  - On Linux, drop `-arch` and `-mmacosx-version-min`, count the cores with `nproc` instead of `sysctl`, and skip `lipo`.
  - Keep FFmpeg's x86 assembly, using `nasm`. On Intel Macs the script turns it off (`--disable-x86asm`) to avoid needing nasm, but on Linux nasm is one package.
  - Pin the source tarball's SHA-256, as the Windows script pins BtbN's zip. The Mac gets the check too.
- **How CMake finds it.**
  - `-DFFMPEG_DIR` works on Linux; only Windows overrides it (`CMakeLists.txt:552–558`) [verified].
  - With `FFMPEG_DIR` set, `FindFFmpeg.cmake` looks only there and skips pkg-config [verified].
- **Don't restrict pkg-config to our FFmpeg, unlike the Mac script.** `alsa-sys` and CMake's `FindEGL` find their libraries through pkg-config [verified: `Cargo.lock`, `FindEGL.cmake:36`].

### 3.4 Configure and build

```sh
cmake -S "$SRC" -B "$SRC/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DFFMPEG_DIR="$FFMPEG" -DSLIPPI_PLAYBACK=ON -DLINUX_LOCAL_DEV=ON \
  -DENABLE_QT=OFF -DENABLE_NOGUI=ON -DENABLE_SDL=OFF -DENABLE_TESTS=OFF -DENABLE_LLVM=OFF \
  -DENABLE_ANALYTICS=OFF -DENABLE_AUTOUPDATE=OFF -DUSE_DISCORD_PRESENCE=OFF -DUSE_SYSTEM_LIBS=OFF \
  -DENABLE_X11=OFF -DENABLE_EVDEV=OFF -DENABLE_HWDB=OFF -DENABLE_BLUEZ=OFF \
  -DENABLE_ALSA=OFF -DENABLE_PULSEAUDIO=OFF -DRust_TOOLCHAIN=1.88.0
cmake --build "$SRC/build" --target dolphin-nogui
```

- **Switches.** The macOS and Windows switches, minus the platform-only ones, plus these:
  - **`LINUX_LOCAL_DEV=ON`:** Dolphin looks for `Sys` next to the program. Without it, this Slippi tree looks in `~/.config/SlippiOnline/Sys` (`FileUtil.cpp:853–882`, `CommonPaths.h:22`) [verified]. Slippi's own Linux build sets it too [verified: `build-linux.sh`].
  - **`ENABLE_X11=OFF`:** no window is ever opened. Every X11 include is behind `HAVE_X11` or a CMake check [verified], so the build should work without X11. Slippi's CI always builds with X11, so this is still [to test].
  - **`ENABLE_EVDEV=OFF`, `ENABLE_HWDB=OFF`:** when on, they *require* libevdev and libudev (`CMakeLists.txt:591–611`) [verified], and renders need no controllers. Without libudev, the bundled hidapi and libusb use their other back ends [verified: their `CMakeLists.txt`].
  - **ALSA, PulseAudio and BlueZ off:** renders have no audio (`Backend = No Audio Output`) [verified: `config.py`]. Turning them off keeps the package from depending on whatever the build machine happens to have installed. ALSA is still needed, through the Rust library (section 3.1).
  - **Vulkan and EGL stay on** (the defaults).
- **Configure checks:**
  - "libav/ffmpeg found, enabling AVI frame dumps", and the `avcodec` it found is ours, as on Windows.
  - "EGL OpenGL interface enabled". Without it there's no OpenGL fallback.
- **Output:**
  - The program is `build/Binaries/dolphin-emu-nogui`, as on the Mac (`CMakeLists.txt:206`) [verified].
  - The Rust library is `build/cargo/build/<target>/release/libslippi_rust_extensions.so` [estimate: the Windows path, with Linux names].
- **If a bundled library doesn't build on Linux:**
  - Use the system's copy of just that one, with `USE_SYSTEM_<NAME>=ON` [verified: `DolphinLibraryTools.cmake`].
  - Slippi's CI uses system copies of several libraries, so the bundled ones are less tried on Linux.
  - The likeliest candidate is iconv, which glibc provides (`USE_SYSTEM_ICONV=ON`) [estimate].
- **Time.** Slippi's Linux Playback job took 19 minutes, including Qt and the AppImage [verified]. Expect:
  - about 15 minutes per architecture on CI [estimate];
  - 30–60 minutes in Docker on this Mac [estimate].

### 3.5 Rendering without a window

- **Vulkan (the default)** [verified in source]:
  - With `-p headless`, Dolphin creates no surface (`VKMain.cpp:109, 146–156`) and no swap chain, so `IsHeadless()` is true (`VKGfx.cpp:50–53`).
  - The presenter then never draws to a backbuffer (`Present.cpp:139, 858`).
  - Frame dumps draw the picture into their own framebuffer and read it back (`FrameDumper.cpp:58–108`). It's the path Metal takes on the Mac.
  - Dolphin loads `libvulkan.so.1` itself (`VulkanLoader.cpp:87–93`), so Vulkan isn't a link-time dependency.
  - Slippi orders the Linux backends Vulkan, OpenGL, Software (`VideoBackendBase.cpp:186–212`), so Vulkan is Dolphin's default too.
  - **Which GPU:** `[Hardware] Adapter` in `GFX.ini`, index 0 by default (`VKMain.cpp:158–165`) [verified]. On a PC with both a GPU and Mesa's lavapipe (Vulkan on the CPU), check which comes first [to test].
- **OpenGL (the fallback):**
  - In headless mode, Dolphin's EGL code opens the default display, `EGL_DEFAULT_DISPLAY` (`EGL.cpp:131–133`) [verified].
  - It then uses a surfaceless context, or a pbuffer where that isn't supported (`EGL.cpp:291–328`) [verified].
  - Mesa ties the default display to X11 or Wayland unless `EGL_PLATFORM` says otherwise [reported: Mesa's EGL documentation]. So without a display server it needs `EGL_PLATFORM=surfaceless`.
- **Precedent.** Dolphin's own FifoCI runs `dolphin-emu-nogui -p headless` on Linux, with frame dumping on and `EGL_PLATFORM=surfaceless` set [verified: `fifoci/runner/linux/run_fifo_test.sh` and its configs].
  - Its results include Vulkan and OpenGL configurations on Mesa (`vk-lin-mesa`, `ogl-lin-mesa`) [reported].
  - That's the same path as here, minus Slippi's playback code.
- **FIFO logs can't stand in for the game in CI.** Patch 0002 records frames only during Slippi playback (`Present.cpp:37–45, 258`) [verified].

### 3.6 The package

The package goes in `packages/slippi-playback-mainline/`, as on Windows:

| File | From |
|---|---|
| `dolphin-emu-nogui` | `build/Binaries/` |
| `libslippi_rust_extensions.so` | `build/cargo/build/<target>/release/` |
| `libavcodec.so.62`, `libavformat.so.62`, `libavutil.so.60`, `libswscale.so.9`, and whatever else the program needs | Our FFmpeg's `lib/`, each copied under its SONAME |
| `Sys/` | `Data/Sys`, plus the playback `GALE01r2.ini`, as on macOS and Windows |
| `COPYING`, `Licenses/`, `BUILD.txt` | As on Windows. `BUILD.txt` also records the glibc version the package needs |

- **Finding the libraries.** The bundle step gives the program and every library in the folder the run path `$ORIGIN` (with patchelf). It has to go on each library, because a run path only applies to the object's own dependencies [reported: `ld.so(8)`], and libavformat needs libavcodec.
- **The Rust library has no SONAME,** because Corrosion sets `IMPORTED_NO_SONAME` (`Corrosion.cmake:486`) [verified]. Check that the program asks for `libslippi_rust_extensions.so` by name, not by its build path [to test].
- **Copy what the program needs, not a fixed list,** as the Mac's `bundle_dylibs` does: follow `readelf -d` from the program through its libraries. For example, the Mac app doesn't link libswresample [verified: `otool -L`].
- **Checks in the bundle step:**
  - Every library needed is in the folder, or on a short list of system libraries:
    - glibc's: `libc`, `libm` and the loader;
    - `libstdc++.so.6` and `libgcc_s.so.1`;
    - `libz.so.1`, `libEGL.so.1` and `libasound.so.2`.
  - The newest `GLIBC_` symbol version used is 2.35 or older (`objdump -T`).
  - `--help` lists `--cout`, `--camera-out` and `--hide-seekbar`, as on Windows.
- **Only replace its own files.** The Windows bundle step deletes the whole output folder first. On Linux, the step should replace only the files it puts there, because two platforms can share one checkout: Docker on this Mac mounts the repo, and WSL2 can use a Windows checkout.
- **What the machine running it needs:**
  - glibc 2.35 or newer;
  - `libegl1` and `libasound2` (`libasound2t64` on Ubuntu 24.04). Desktop installs have them [estimate]; a plain `ubuntu:24.04` image has neither [verified];
  - for Vulkan, `libvulkan1` and a driver: the GPU's, or `mesa-vulkan-drivers` for lavapipe;
  - for OpenGL, Mesa's or NVIDIA's EGL.

## 4. GitHub Actions

A new workflow, `.github/workflows/dolphin-linux.yml`, started by hand like the Windows one (Appendix B).

- **Build job,** once per architecture:
  - x86_64 on `ubuntu-24.04`, and arm64 on `ubuntu-24.04-arm`. The arm64 runners are free for public repositories [reported: GitHub changelog, August 2025].
  - Both run in an `ubuntu:22.04` container (section 3.1). Container jobs on the arm64 runner are [to test]. If they don't work, build arm64 directly on the runner, which raises its glibc floor to 2.39.
  - Steps:
    1. Install section 3.1's packages.
    2. Check out the repo.
    3. Install Rust 1.88.0 with rustup.
    4. Run `python3 tools/dolphin-build/build-linux-mainline.py all`.
    5. Pack the folder as a tarball, then upload it and the build logs.
- **Portability job.** It unpacks the x86_64 tarball in clean images of six distributions, installs only the runtime libraries, and runs `--help`:
  - `ubuntu:22.04` and `ubuntu:24.04`;
  - `debian:12` and `debian:13`;
  - `fedora:latest` and `archlinux:latest`.

  That catches a missing library, or a too-new glibc symbol, before a user does.
- **What CI can't test:** renders, as on Windows, because the ISO can't go into CI.
- **Why a tarball.** Artifacts are zips that don't keep file permissions [verified: upload-artifact's README], and the program must stay executable.
  - GitHub still serves the artifact zipped, so a download is a zip with the tarball inside.
  - Artifacts are kept for 90 days. The tarballs can also go on a release.
- **Container details:**
  - Run steps in a container use `sh` unless told otherwise [reported: GitHub's documentation], so the workflow sets `bash`.
  - `download-artifact` runs on Node 24 only from v7 [verified], and `upload-artifact` from v6, as in the Windows workflow.

## 5. slp2alpha and the tools on Linux

| Where | Today | Change |
|---|---|---|
| `locate.find_dolphin` | Only macOS and Windows have candidates, so on Linux it always says no build was found [verified] | Look for `mainline_package()` on Linux too |
| `locate.build_hint` | "there is no build script for this platform yet" | Name `build-linux-mainline.py` and the CI tarball |
| `config.default_video_backend` | `None` on Linux, which leaves Dolphin's default (Vulkan) | `Vulkan`, explicitly, as `Metal` and `D3D` are |
| `runner.run_dolphin` | Passes the environment through | With `--backend OGL`, set `EGL_PLATFORM=surfaceless` unless it's already set, as FifoCI does |
| `locate.find_ffmpeg`, `build_iso.py`, `__main__.py` help texts | macOS and Windows hints and defaults | Add Linux ones (`apt install ffmpeg xdelta3`; "Vulkan on Linux") |
| Docstrings that name `~/Library/Caches` (`build_iso.py`, `logo_stage.py`) | macOS and Windows folders | Add `~/.cache` |

- **Works unchanged** [verified by reading]:
  - **Stopping Dolphin:**
    - Dolphin runs in its own session (`start_new_session`).
    - slp2alpha sends SIGTERM to the group, then SIGKILL after 20 s, and stops any Dolphin still running at exit.
    - Dolphin's handler resets itself, so a second signal still kills it (`MainNoGUI.cpp:350–355`).
  - **Folders.** The cache is `$XDG_CACHE_HOME/AlphaSolveVideo`, or `~/.cache/AlphaSolveVideo`. The ISO comes from `--iso`, or from the Slippi Launcher's settings, which slp2alpha looks for in `~/.config/Slippi Launcher/Settings` [estimate: that's where the Linux Launcher keeps them].
  - **The program's name,** `dolphin-emu-nogui`, which `engine_of` already recognises.
  - **Blender,** through `$BLENDER` or the PATH (`plate.find_blender`).
  - **The render tests.** Their cache (`locate.cache_root`), and SKIP for `--format hevc`. `mov` falls back to `prores_ks`, as on Windows.
- **The solver's ffmpeg:**
  - Distributions ship different versions: 4.4 on Ubuntu 22.04, 6.1 on 24.04 [reported].
  - The solver only uses long-standing filters, such as `select`, `blend`, `lut2`, `alphamerge` and `palettegen` [verified: `solve.filter_graph`]. But only 9.0 has been tried [verified on macOS].
  - Recommend BtbN's static FFmpeg 9.0, `linux64-gpl-9.0` or `linuxarm64-gpl-9.0` [verified: both are in the 31 October build]. Point `ALPHASOLVE_FFMPEG_DIR` at it.
  - Don't unpack it into `packages/ffmpeg/` in a checkout the Mac also uses. The Mac looks there first, and would find a Linux program.
- **Not ported:**
  - `slp2alpha bench`'s CPU sampling. It reads macOS's `ps -M`; Linux would read `ps -L`.
  - `research/`, as on Windows.

## 6. Testing on this Mac, in Docker

Docker Desktop on this Mac runs an arm64 Linux VM [verified]: engine 29.9.2, 8 CPUs, 7.9 GB of memory, 4 KB pages, and a 64 MB `/dev/shm` by default. It can stand in for a Linux PC without a GPU:

- **The emulation runs natively.** An arm64 container runs Dolphin's ARM64 recompiler, the same one the Mac build uses.
  - The earlier amd64 Docker prototype ran under Rosetta, where Dolphin's x86 recompilers crashed.
  - Only its interpreter worked, at 40–95 minutes per game [verified: `plan-macos-apple-silicon.md`].
- **The rendering runs on the CPU.** Docker passes no GPU through, so Mesa renders on the CPU: lavapipe for Vulkan, llvmpipe for OpenGL. At 1× (640×528), that should roughly keep up with the emulation [estimate]. Step 7 below measures it.
- **Shared memory.** Dolphin keeps the emulated memory in `/dev/shm` (`MemArenaUnix.cpp:34`) [verified]. For a GameCube game that's 64.25 MB (`Memmap.cpp:86–124`) [verified]:
  - 32 MB for the 24 MB of RAM, rounded up;
  - 256 KB of L1 cache;
  - 32 MB of fake VMEM.

  That's just over Docker's 64 MB, so run with `--shm-size=1g`. The Ishiiruka prototype crashed without it [verified].
- **Keep the Mac's files apart.**
  - Mount the repo at `/repo`, with named volumes over `/repo/packages` and the cache. Otherwise the Linux build and the Mac app would share `packages/slippi-playback-mainline/`.
  - Mount the ISO and the test replays read-only.
  - Appendix C has the image and the command.

Steps, in order. Each is [to test]:

1. **Build** the arm64 package in the container: `JOBS=4 python3 tools/dolphin-build/build-linux-mainline.py`.
2. **First render,** of the clip the Windows plan uses, from `tools/slp2alpha`:

   ```sh
   python3 -m slp2alpha render /asv/test-replays/DishonestMuddyCoyote.slp --iso /iso/melee.iso --characters-only --start-frame 1500 --end-frame 1799 --keep --out-dir /out
   ```

   Then check:
   - The recording has 600 fields.
   - `logs/dolphin.stderr` ends with "A signal was received. A second signal will force Dolphin to stop.", so Dolphin stopped cleanly. Dolphin writes it to stderr on Linux and macOS (`MainNoGUI.cpp:51`), and to stdout on Windows.
   - The summary says "Dolphin and solver together".
   - `fullTransparent - ... .mov` has transparency.
3. **The camera against the Mac's.** Render the clip again with `--export-camera`, then, from the repo root, compare it with the Mac's export:

   ```sh
   python3 tools/camera-export/validate_camera.py compare tools/camera-export/reference/DishonestMuddyCoyote_1500-1799_characters-only_macos.json "/out/camera - DishonestMuddyCoyote (frames 1500 to 1799, characters only, 60 fps).json"
   ```

   It should report 0 differing frames [estimate]. The container runs the same recompiler as the Mac, and the camera comes from the game's own maths.
4. **The camera checks** from [`camera-export.md`](camera-export.md):
   - In the container: `readonly`, `static` on the six legal stages, `check --raw`, `compare` of a clip against the whole game, and `track` on the Battlefield game.
   - On the Mac: `blender`, on the container's export. Blender has no official arm64 Linux build [reported], and this check doesn't depend on where the export was made.
5. **The OpenGL fallback:** the same clip with `--backend OGL`.
6. **Render tests:** `python3 tools/render-tests/run.py`. Every entry should pass, with `--format hevc` as SKIP. They take longer on the CPU renderer; note how long.
7. **Speed:** the "x real time" figure for a whole game, against the Mac's 0.52× [verified on macOS].

What Docker can't show: x86_64 (Dolphin's other recompiler, Jit64), real GPU drivers, and GPU speed.

## 7. On a Linux PC (x86_64, with a GPU)

This section is optional, but it's the setup most Linux users have. Each step is [to test]:

1. **Install:**
   - the CI tarball: unzip the artifact, then `tar -xzf slippi-playback-mainline-linux-x86_64.tar.gz -C packages`;
   - Python 3.9 or newer;
   - FFmpeg 9.0 (section 5);
   - `libvulkan1` and the GPU's Vulkan driver: Mesa's for AMD and Intel, or NVIDIA's.
2. **First render,** as in section 6. Then check:
   - which GPU Dolphin used: its log names the Vulkan device [to test: which line];
   - that it works the same from an X11 session, from a Wayland session, and from an SSH login with no display.
3. **The camera on x86_64,** against the Mac's export. It should give 0 differences, as expected for Windows [estimate]. Windows runs the same recompiler (Jit64), so this result also predicts Windows.
4. **The render tests, and a long game** for speed.

- **No Linux PC?** WSL2 on a Windows PC can run the x86_64 package. Its GPU access goes through Mesa's Direct3D 12 drivers [reported], so treat its speed as a lower bound.

## 8. Risks

| Risk | Mitigation |
|---|---|
| GCC 11 rejects something in a patch, or in NoGUI without X11 | CI gives the file and line; fix it in a patch. Or build with X11, which adds `libx11-dev libxrandr-dev libxi-dev` to the build and those libraries at run time |
| A bundled library doesn't build on Linux | `USE_SYSTEM_<NAME>=ON` for that library |
| The Rust build can't find ALSA, or the link can't find `-lz` | `libasound2-dev`, `zlib1g-dev` |
| The program can't find its libraries | `$ORIGIN` on every library. The bundle step runs `--help`, which loads them all |
| The package needs a newer glibc than the user has | It's built on Ubuntu 22.04, and the portability job checks six distributions |
| Vulkan doesn't record without a surface on some driver | `--backend OGL` |
| Vulkan picks lavapipe on a PC with a GPU | The adapter index (a new slp2alpha option), or `VK_DRIVER_FILES` to leave lavapipe out [reported] |
| `/dev/shm` is too small in Docker | `--shm-size=1g` |
| 7.9 GB isn't enough for an 8-job build in Docker | `JOBS=4` |
| The distribution's ffmpeg is too old for the solver | FFmpeg 9.0 through `ALPHASOLVE_FFMPEG_DIR` |
| GitHub retires the `ubuntu-22.04` runners (April 2027) | The container provides Ubuntu 22.04, not the runner |

## 9. Effort and order of work

| Step | Effort | Where |
|---|---|---|
| L1. `build-linux-mainline.py`, and `build-ffmpeg.sh` on Linux | 0.5–1 day | This Mac |
| L2. The first arm64 build in Docker, until it links and bundles | 0.5 day, plus 30–60-minute builds | This Mac |
| L3. The workflow and its portability job (about 20 minutes per run) | 0.5 day | GitHub |
| L4. slp2alpha and the tools (section 5) | 0.25 day | This Mac |
| L5. Section 6: the renders, the camera against the Mac's, the checks, the render tests | 0.5–1 day | This Mac |
| L6. Section 7, on an x86_64 PC with a GPU | 0.5 day | A Linux PC (optional) |
| L7. Docs: a Linux line in `camera-export.md`, a Linux quick start in the README, this plan's status | 0.25 day | Anywhere |
| **Total** | **3–4 days** (2.5–3.5 without L6) | |

- **Share the build code with Windows.**
  - Five parts would be the same in both scripts: `fetch`, `apply_patches`, the downloads and their checksums, the CMake venv, and the Rust check. The Windows script's fetch and patch steps already run on the Mac [verified].
  - Moving them into a module both scripts import, such as `tools/dolphin-build/mainline_common.py`, keeps one copy of the patch detection. That code once had to be fixed in two places [verified: `plan-windows-mainline.md`].
  - One run of the Windows workflow checks the move.
  - The alternative is a standalone Linux script with its own copy.
- **The Mac script stays as it is.**

---

## Appendix A: `build-linux-mainline.py`

The same steps as the Windows script: `fetch`, `configure`, `build`, `bundle` and `all`.

| Step | What it does |
|---|---|
| `fetch` | Shared with Windows: the source, the submodules except `Externals/Qt`, and the patches |
| `configure` | Checks the packages, and prints the `apt install` line if any are missing. Builds FFmpeg (`build-ffmpeg.sh 8.1.3 <arch> <cache>/ffmpeg8-linux-<arch>`). Installs Rust 1.88.0, and CMake, Ninja and patchelf into the venv. Runs section 3.4's CMake and checks its output |
| `build` | `cmake --build ... --target dolphin-nogui -j $JOBS` |
| `bundle` | Section 3.6, then copies the result into `OUTPUT_DIR`, replacing only its own files |

Environment variables:

- `ALPHASOLVE_CACHE`: the work folder (default `~/.cache/AlphaSolveVideo`).
- `OUTPUT_DIR`: where the package goes (default `packages/slippi-playback-mainline`).
- `JOBS`: build parallelism (default: all cores).

## Appendix B: the workflow (sketch)

```yaml
name: Linux playback Dolphin

on:
  workflow_dispatch:

defaults:
  run:
    shell: bash

jobs:
  build:
    name: Build the Linux package (${{ matrix.arch }})
    strategy:
      fail-fast: false
      matrix:
        include:
          - { arch: x86_64, runner: ubuntu-24.04 }
          - { arch: aarch64, runner: ubuntu-24.04-arm }
    runs-on: ${{ matrix.runner }}
    container: ubuntu:22.04
    timeout-minutes: 120
    env:
      ALPHASOLVE_CACHE: /asv
    steps:
      - name: Install the build packages
        run: |
          apt-get update
          DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends build-essential git pkg-config \
            curl ca-certificates xz-utils python3 python3-venv nasm zlib1g-dev libasound2-dev libegl-dev
      - uses: actions/checkout@v5
      - name: Install Rust 1.88.0
        run: |
          curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain 1.88.0 --component rustfmt
          echo "$HOME/.cargo/bin" >> "$GITHUB_PATH"
      - name: Build
        run: python3 tools/dolphin-build/build-linux-mainline.py all
      - name: Pack (a tarball keeps the executable bit)
        run: tar -C packages -czf slippi-playback-mainline-linux-${{ matrix.arch }}.tar.gz slippi-playback-mainline
      - uses: actions/upload-artifact@v6
        with:
          name: slippi-playback-mainline-linux-${{ matrix.arch }}
          path: slippi-playback-mainline-linux-${{ matrix.arch }}.tar.gz
          if-no-files-found: error
      - uses: actions/upload-artifact@v6
        if: always()
        with:
          name: build-logs-${{ matrix.arch }}
          path: /asv/*.log
          if-no-files-found: ignore

  portability:
    name: Starts on ${{ matrix.image }}
    needs: build
    strategy:
      fail-fast: false
      matrix:
        image: [ubuntu:22.04, ubuntu:24.04, debian:12, debian:13, fedora:latest, archlinux:latest]
    runs-on: ubuntu-24.04
    container: ${{ matrix.image }}
    steps:
      - uses: actions/download-artifact@v7
        with:
          name: slippi-playback-mainline-linux-x86_64
      - name: Install only the runtime libraries
        run: |
          . /etc/os-release
          case "$ID" in
            ubuntu|debian) apt-get update && apt-get install -y libegl1 libasound2 ;;
            fedora) dnf install -y tar gzip libglvnd-egl alsa-lib ;;
            arch) pacman -Sy --noconfirm libglvnd alsa-lib ;;
          esac
      - name: Run --help
        run: |
          tar -xzf slippi-playback-mainline-linux-x86_64.tar.gz
          slippi-playback-mainline/dolphin-emu-nogui --help > help.txt 2>&1 || true
          cat help.txt
          grep -q -- --camera-out help.txt
```

## Appendix C: the Docker image for section 6 (sketch)

`tools/dolphin-build/linux.Dockerfile` builds the package and runs the tests. On this Mac it's arm64:

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential git pkg-config curl ca-certificates xz-utils python3 python3-venv python3-pip nasm \
      zlib1g-dev libasound2-dev libegl-dev \
      libvulkan1 mesa-vulkan-drivers libegl-mesa0 libgl1-mesa-dri xdelta3 \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain 1.88.0 --component rustfmt
RUN python3 -m pip install --no-cache-dir numpy pillow
# FFmpeg 9.0 for the solver, outside the repo: BtbN's static linuxarm64-gpl-9.0 (or linux64-gpl-9.0) build.
ARG FFMPEG_URL
ARG FFMPEG_SHA256
RUN curl -fL -o /tmp/ffmpeg.tar.xz "$FFMPEG_URL" && echo "$FFMPEG_SHA256  /tmp/ffmpeg.tar.xz" | sha256sum -c - \
    && mkdir -p /opt/ffmpeg && tar -xJf /tmp/ffmpeg.tar.xz -C /opt/ffmpeg --strip-components 1 && rm /tmp/ffmpeg.tar.xz
ENV PATH=/root/.cargo/bin:$PATH ALPHASOLVE_CACHE=/asv ALPHASOLVE_FFMPEG_DIR=/opt/ffmpeg/bin PYTHONDONTWRITEBYTECODE=1
WORKDIR /repo
```

Run it from the repo root:

```sh
docker build -t asv-linux -f tools/dolphin-build/linux.Dockerfile \
  --build-arg FFMPEG_URL=... --build-arg FFMPEG_SHA256=... tools/dolphin-build
docker run --rm -it --shm-size=1g \
  -v "$PWD":/repo -v asv-linux-packages:/repo/packages -v asv-linux-cache:/asv \
  -v ~/Library/Caches/AlphaSolveVideo/test-replays:/asv/test-replays:ro \
  -v "/path/to/Melee.iso":/iso/melee.iso:ro -v "$TMPDIR/linux-out":/out \
  asv-linux bash
```

- **Mesa version.** If Ubuntu 22.04's Mesa is too old for lavapipe [estimate], run the renders in an `ubuntu:24.04` image instead. The package runs there too, since its glibc is newer.
- **A wrapper script** could find the ISO the way slp2alpha does on the Mac (the Slippi Launcher's setting) and fill in these mounts.

## References

- Pinned Dolphin source: https://github.com/project-slippi/dolphin/tree/c5f635948ed43f4d14a72069343e0cecdc117391
  - `.github/workflows/main.yml` (the Linux job), `build-linux.sh`, `build-appimage.sh`.
  - `CMakeLists.txt`: options, `LINUX_LOCAL_DEV`, the output folder, `FFMPEG_DIR`.
  - `CMake/`: `FindFFmpeg.cmake`, `FindEGL.cmake`, `DolphinLibraryTools.cmake`.
  - `Source/Core/DolphinNoGUI/`: `MainNoGUI.cpp`, `PlatformHeadless.cpp`, `CMakeLists.txt`.
  - Headless rendering:
    - `Source/Core/VideoBackends/Vulkan/`: `VKMain.cpp`, `VKGfx.cpp`, `VulkanLoader.cpp`;
    - `Source/Core/Common/GL/GLInterface/EGL.cpp`;
    - `Source/Core/VideoCommon/`: `Present.cpp`, `FrameDumper.cpp`, `VideoBackendBase.cpp`.
  - `Source/Core/Common/FileUtil.cpp` and `MemArenaUnix.cpp`; `Source/Core/Core/HW/Memmap.cpp`.
  - `Externals/`:
    - `SlippiRustExtensions/Cargo.lock`;
    - `corrosion/cmake/Corrosion.cmake`;
    - `hidapi/CMakeLists.txt` and `libusb/CMakeLists.txt`.
- Slippi's CI results for the commit: https://api.github.com/repos/project-slippi/dolphin/commits/c5f635948ed43f4d14a72069343e0cecdc117391/check-runs
- FifoCI's Linux runner: https://github.com/dolphin-emu/fifoci/blob/master/fifoci/runner/linux/run_fifo_test.sh
- GitHub:
  - the `ubuntu-22.04` deprecation: https://github.com/actions/runner-images/issues/14254;
  - arm64 runners: https://github.blog/changelog/2025-08-07-arm64-hosted-runners-for-public-repositories-are-now-generally-available;
  - running jobs in a container;
  - the "Permission Loss" section of upload-artifact's README.
- Mesa:
  - EGL and `EGL_PLATFORM`: https://docs.mesa3d.org/egl.html;
  - lavapipe and llvmpipe: https://docs.mesa3d.org/drivers/llvmpipe.html.
- FFmpeg builds: https://github.com/BtbN/FFmpeg-Builds. The `autobuild-2026-10-31-12-59` release has the Linux variants.
- `ld.so(8)`: `DT_RUNPATH` and `$ORIGIN`.
