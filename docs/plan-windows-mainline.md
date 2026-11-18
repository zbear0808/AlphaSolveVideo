# Windows: the patched mainline Dolphin and the camera export

Status: partly implemented, November 2026. Everything that doesn't need a Windows machine is done, but nothing has run on Windows yet: no Windows PC was available, so everything that needs Windows to run is [to test] or [estimate]. [`plan-windows-remaining.md`](plan-windows-remaining.md) has the work that's left, in order. The source facts come from the pinned Dolphin checkout (`~/Library/Caches/AlphaSolveVideo/mainline`, commit `c5f6359`, with this repo's patches applied).

What was done, and what changed from this plan while doing it:

- **The build script is Python, not PowerShell:** `tools/dolphin-build/build-windows-mainline.py`. slp2alpha needs Python on Windows anyway, and the script's fetch and patch steps ran on the Mac. It loads the compiler environment itself (`vcvars64.bat`, found with `vswhere`) when `cl.exe` isn't on the PATH. Appendix A lists where each part is.
- **The workflow** is `.github/workflows/dolphin-windows.yml`. It runs only when started by hand, so a push never starts a 30-minute build.
- **The FFmpeg (F1) is pinned:** BtbN's month-end build of 31 October 2026, `ffmpeg-n8.1.3-27-g8dca1586f4-win64-lgpl-shared-8.1.zip`, SHA-256 `5cef7bc4…56ab`. Its `avformat-62.dll` has the Matroska muxer and `avcodec-62.dll` the FFV1 encoder. Its `.def` files export only functions, no data, which keeps linking with MSVC simple [verified: the zip's contents].
- **Patches.** 0004 now initializes `ok`, and 0005 adds the Ctrl+Break handler. The Mac build applies them all, and its camera export is unchanged: identical samples before and after [verified].
- **The first CI run (18 November) compiled everything** with MSVC, the patches included, then failed to link. NoGUI's CMake links the system zlib by name (`z`), and Windows has no `z.lib`; Slippi's CI never builds NoGUI, so it never met this. Patch 0006 links `z` everywhere except Windows. On the Mac the build is unchanged [verified].
- **Detecting applied patches** changed in both build scripts. A patch only reverse-checks on its own while nothing is applied on top of it. Since 0004 edits lines next to 0002's, `build-mac-mainline.sh fetch`, `configure` and `all` stopped with an error on an already-patched tree [verified]. That didn't show, because only `build` and `bundle` had run since. Both scripts now look for the last patch that reverse-checks, and apply the ones after it.
- **slp2alpha also stops Dolphin when it exits**, for example after Ctrl+C. Renders run Dolphin on a worker thread, whose clean-up doesn't run at exit, and Dolphin is in its own process group, so the Ctrl+C doesn't reach it. On the Mac it died anyway, from a broken pipe on its next progress line [verified]. On Windows a broken pipe doesn't end a program, so it would have kept running [estimate]. On the Mac, the recording now gets a clean end too [verified].
- **`render --backend`** picks the video backend: `D3D12` or `Vulkan` if Direct3D 11 can't record without a window.
- **`--format` checks the encoder first,** on every platform. `--format hevc` without VideoToolbox stops with a message, and the render tests skip it (status SKIP).
- **Ishiiruka on Windows** is stopped with WM_CLOSE to its window, because it's a window program that Ctrl+Break doesn't reach.
- **Text and paths.** Tool output is decoded as UTF-8, and Python children are told to write UTF-8. Text files are read and written as UTF-8. The render tests no longer put file paths inside ffmpeg filter strings, which a Windows drive letter's colon would break.
- **`tools/animelee/build-iso.sh` is now `build_iso.py`.** It built a byte-identical ISO on the Mac [verified], and needs only `xdelta3` besides Python.
- **One cache folder for everything:** `locate.cache_root()`, `%LOCALAPPDATA%\AlphaSolveVideo` on Windows, or `$ALPHASOLVE_CACHE`.
- **A Mac camera export to compare against** is in `tools/camera-export/reference/`.

Companion to [`plan-windows.md`](plan-windows.md), which automates Slippi's official Windows playback build (Ishiiruka 3.5.2). That route needs no build, but it can't export the camera and it opens a window. This plan brings the macOS build to Windows: Slippi's mainline playback Dolphin, headless, with this repo's patches. The patches are described in [`plan-macos-apple-silicon.md`](plan-macos-apple-silicon.md) and [`plan-camera-export-dolphin.md`](plan-camera-export-dolphin.md).

Evidence tags:

- **[verified]**: measured, or read in source or on disk, during this investigation.
- **[reported]**: found during research (documentation, release listings); not re-checked by hand.
- **[estimate]**: needs a measurement.
- **[to test]**: needs an experiment on Windows before we rely on it.

---

## 1. Summary

- **Goal.** On a Windows PC, `py -m slp2alpha render game.slp --export-camera` works as it does on macOS: no window, the same three files, the same checks passing. Other features of the mainline build come with it: headless renders, solving while recording, `--shy-guy-sprite`.
- **Why a build is needed.** The camera patch (0004) is written for Slippi's mainline playback Dolphin (`project-slippi/dolphin`, branch `fix/mainline-playback`, pinned at `c5f6359`). Slippi's Windows release is Ishiiruka 3.5.2, a different code base. It has no `--camera-out`, and it opens a window that flashes black and white.
- **The source builds on Windows.** Slippi's own CI built this exact commit for Windows Playback, and the run passed in 26.3 minutes [verified: GitHub check runs for `c5f6359`]. That job builds the Qt program (`dolphin-emu`). We need the console program (`dolphin-nogui`) from the same tree.
- **Four things differ from macOS:**
  1. **FFmpeg.** Dolphin's bundled Windows FFmpeg can't write Matroska, the format slp2alpha records in. Link a prebuilt FFmpeg 8.1 instead (section 3.3).
  2. **Stopping Dolphin.** Windows has no SIGTERM. A one-line patch (0005) makes Ctrl+Break stop Dolphin cleanly, and slp2alpha sends it (section 3.6).
  3. **Line endings.** Git for Windows would check the patches out with CRLF line endings, and then they no longer apply (section 3.2).
  4. **Small Mac-only spots in slp2alpha and the tools:** process groups, the Metal default, paths (section 5).
- **Where to build.** GitHub Actions in the fork is the recommended route. It needs no Windows development setup, and the result is a zip to unpack into `packages\`. A Python script does the build (`tools/dolphin-build/build-windows-mainline.py`), so a local build on a Windows PC runs the same steps (section 4).
- **Effort.** About 2.5–3.5 days, plus waiting for CI runs (about 30 minutes each). A Windows PC is needed only for the last day: the first real renders and the checks (section 9).

## 2. What changes from macOS

| Piece | macOS (works today) | Windows |
|---|---|---|
| Dolphin source | `c5f6359` plus patches 0001–0004 | The same, plus 0005 and 0006 |
| Compiler | AppleClang | MSVC 2022 with `/W4 /WX`, so every warning is an error (section 3.7) |
| Rust | 1.88.0 | 1.88.0, `x86_64-pc-windows-msvc` |
| FFmpeg inside Dolphin | Our FFmpeg 8.1.3 dylibs (AVI, Matroska and MOV muxers) | The bundled FFmpeg has no Matroska, so BtbN's FFmpeg 8.1 DLLs instead |
| Video backend | Metal, with no layer | Direct3D 11 (`GFXBackend = D3D`), with no swap chain |
| Window | None (`-p headless`) | None (`-p headless`; a console program) |
| Stopping Dolphin | SIGTERM to its process group | Ctrl+Break to its process group (patch 0005) |
| Package | `Slippi Dolphin.app` with its dylibs, ad-hoc signed | A folder: the program, its DLLs, `Sys\` |
| slp2alpha, camera tools | As they are | Small changes (section 5) |
| Blender importer | As it is | As it is: it only uses `bpy` and `pathlib` |

## 3. The Dolphin build

### 3.1 Toolchain

- **Compiler.** Visual Studio 2022 or its Build Tools, with the C++ workload and a Windows SDK. Slippi's CI uses the `windows-2022` image, and `egor-tensin/vs-shell@v2` to load the compiler environment [verified in `.github/workflows/main.yml`].
- **Rust 1.88.0,** from `Externals/SlippiRustExtensions/rust-toolchain.toml` [verified]. If the build uses `actions-rust-lang/setup-rust-toolchain`, set `rustflags: ""` as Slippi's CI does. Otherwise that action turns Rust warnings into errors [verified: the comment in `main.yml`].
- **CMake 3.31 and Ninja,** both from pip in a venv, as on macOS. CMake 4 rejects the `cmake_minimum_required` of some submodules, so also pass `-DCMAKE_POLICY_VERSION_MINIMUM=3.5`, as the Mac script does [verified on macOS].
- **Git,** with `core.autocrlf=false` and `core.longpaths=true` in the Dolphin checkout (section 3.2).
- **Disk.**
  - The Mac checkout with its build takes 2.0 GB: 811 MB in `Externals`, 806 MB in `build` (642 MB of that is Rust), and 331 MB of git history [verified]. Expect about the same on Windows [estimate].
  - The `Externals/Qt` submodule (378 MB of Windows Qt binaries) isn't needed for NoGUI and can be skipped.

### 3.2 Source, patches and line endings

- **Fetch** the same way as `build-mac-mainline.sh`:
  1. `git init`.
  2. Fetch `c5f6359` at depth 1.
  3. `submodule update --init --recursive --depth 1`.
- **Line endings.** Dolphin's sources use LF. Its `.gitattributes` only forces CRLF for `*.sln` [verified: no CR bytes in `EXI_DeviceSlippi.cpp`]. This repo's `.gitattributes` is `* text=auto` [verified]. Git for Windows' installer defaults to `core.autocrlf=true` [reported], so it would check the `.patch` files out with CRLF, and `git apply` would then find no matching lines [estimate]. The fix:
  - **In this repo,** add `*.patch text eol=lf` and `*.sh text eol=lf` to `.gitattributes`.
  - **In the Dolphin checkout,** set `core.autocrlf=false`, for the submodules too (`git -c core.autocrlf=false submodule update ...`). Patch 0003 edits a file inside the fmt submodule.
- **Patches.** The same loop as on macOS: skip a patch that `git apply --reverse --check` finds already applied, and apply the rest.
- **Patches 0001 and 0003** fix building with clang (0001 for imgui, 0003 for fmt under clang 20). Under MSVC they're harmless [verified: diffs read]:
  - 0001 stops passing the GCC-only flag `-fno-ipa-sra` to `cl`.
  - 0003 hands fmt's checker the same string under another name.

### 3.3 FFmpeg with Matroska

slp2alpha records FFV1 video in Matroska (`DumpFormat = mkv`, `config.py:127`). A Matroska file can be read while it's still being written, which lets the solver run alongside Dolphin [verified on macOS].

- **Dolphin's bundled FFmpeg can't write Matroska.**
  - **What it is.** On Windows, Dolphin links the static FFmpeg in the `Externals/FFmpeg-bin` submodule: FFmpeg git `28d0115` (2022, avcodec 59). It's configured with `--disable-everything`, then only the AVI muxer and the FFV1, MPEG-4 and Ut Video encoders turned back on [verified: `dolphin-build-x64.sh`].
  - **What's missing.** Its `avformat.lib` has the AVI and MPEG-TS muxers and no Matroska [verified: symbol names in the `.lib`].
  - **What happens.** Dolphin looks the container up by name, logs "Invalid format" when it's missing, and records nothing (`FrameDumpFFMpeg.cpp:196–210`) [verified in source].
- **A different FFmpeg goes in through the environment.** `CMakeLists.txt:552–558` sets `FFMPEG_DIR` to the bundled folder on Windows, which overrides a `-DFFMPEG_DIR` given on the command line. But `FindFFmpeg.cmake:50–51` replaces it with the `FFMPEG_DIR` environment variable when that's set, and then looks in its `include\` and `lib\` [verified].

| Option | How | For | Against |
|---|---|---|---|
| **F1** Prebuilt FFmpeg 8.1 DLLs (recommended first) | BtbN's `win64-lgpl-shared-8.1` zip; `FFMPEG_DIR` points at it; five DLLs ship next to the program | Nothing to build. The same FFmpeg version as the Mac build, 8.1 with avcodec 62 [verified: the zip has `avcodec-62.dll`; the Mac app links `libavcodec.62.dylib`] | About 150 MB of DLLs: the five are 156 MB in the GPL zip [verified], a little less in the LGPL one [estimate]. MSVC must link against import libraries built with MinGW [to test] |
| **F2** Dolphin's own FFmpeg recipe, plus Matroska | Run `Externals/FFmpeg-bin/dolphin-build-x64.sh` with `--enable-muxer=avi,matroska`, in MSYS2 with the MSVC environment | Static and small. The same FFmpeg and link requirements as Slippi's release | An MSYS2 build in CI. Known snags: MSYS2's own `link.exe` hides MSVC's on the PATH, and nasm is needed [reported] |
| **F3** Dolphin's bundled FFmpeg, recording AVI | `DumpFormat = avi`, and no solving while recording | Nothing to build or download | Slower renders, because the solver waits for Dolphin. slp2alpha would need an AVI mode for the mainline build |

Recommendation: try F1 first. It's three steps in the build script, and it gets a working build fastest. Fall back to F2 if MSVC rejects the import libraries or the headers. Use F3 only for a first smoke test if both fail.

- **Pinning F1.** BtbN's "latest" files change daily. Dated builds are kept for 14 days, and the last build of each month for two years [reported: BtbN README]. Take a month-end build, record its SHA-256 in the build script, and keep a copy as a release asset in the fork.
- **Headers.** `FrameDumpFFMpeg.cpp` is the only file that uses FFmpeg. Clang compiles it against FFmpeg 8.1.3's headers with `-Wall` and no warnings, deprecation warnings included [verified]. So MSVC's deprecation warning C4996, which `/WX` would make an error, shouldn't fire there [estimate].

### 3.4 Configure and build

Run this from a shell with the MSVC environment loaded and `FFMPEG_DIR` set:

```bat
cmake -S %SRC% -B %SRC%\build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ^
  -DSLIPPI_PLAYBACK=ON -DENABLE_QT=OFF -DENABLE_NOGUI=ON -DENABLE_SDL=OFF -DENABLE_TESTS=OFF ^
  -DENABLE_LLVM=OFF -DENABLE_ANALYTICS=OFF -DENABLE_AUTOUPDATE=OFF -DUSE_DISCORD_PRESENCE=OFF ^
  -DUSE_SYSTEM_LIBS=OFF -DRust_TOOLCHAIN=1.88.0
cmake --build %SRC%\build --target dolphin-nogui
```

- **Switches.** These are the Mac build's switches, minus the macOS-only ones. Vulkan stays at its default (on). It's a second backend that runs without a window, in case Direct3D 11 can't record headless.
- **Configure check.** The configure log must say "libav/ffmpeg found, enabling AVI frame dumps", and the `avcodec` it found must be ours. The Mac script checks the first.
- **Output.** Windows builds put their programs in the *source* tree, `Binary\x64\` (`CMakeLists.txt:208–215`), not in `build\`. The program is `dolphin-emu-nogui.exe` [verified].
- **The Rust DLL.** `slippi_rust_extensions` is a `cdylib` [verified], so the program needs `slippi_rust_extensions.dll` next to it. The `copy_rust_dll` target copies it from `build\cargo\build\x86_64-pc-windows-msvc\release\` (`CMakeLists.txt:636–647`) [verified]. Either build that target too, or copy the DLL in the bundle step.
- **Time.** Slippi's Qt build took 26.3 minutes on a CI runner, checkout included [verified]. NoGUI has less GUI code to compile [estimate: 20–30 minutes in CI, 10–20 minutes locally on 8 or more cores].

### 3.5 The package

The package goes in `packages\slippi-playback-mainline\`, the folder that holds `Slippi Dolphin.app` on macOS:

| File | From |
|---|---|
| `dolphin-emu-nogui.exe` | `Binary\x64\` |
| `slippi_rust_extensions.dll` | `build\cargo\build\x86_64-pc-windows-msvc\release\` |
| `avcodec-62.dll`, `avformat-62.dll`, `avutil-60.dll`, `swresample-6.dll`, `swscale-9.dll` | The FFmpeg zip's `bin\` (F1 only) [verified: names in the 8.1 zip] |
| `Sys\` | `Data\Sys`, plus `Data\PlaybackGeckoCodes\GALE01r2.ini` copied into `Sys\GameSettings\`, as Slippi's CI and the Mac bundle do. Remove the placeholder `Replace GALE01r2.ini ... .txt` [verified] |
| `COPYING`, `Licenses\` | The source tree (Dolphin is GPL) |
| `BUILD.txt` | The commit, the patch list, and the FFmpeg zip with its SHA-256 |

- **Sys.** On Windows, Dolphin looks for `Sys` next to the program (`FileUtil.cpp:851–868`, `GetExeDirectory()` plus `Sys`) [verified].
- **User folder.** slp2alpha always passes `-u`, which takes precedence over `portable.txt` and the default Documents folder (`UICommon.cpp:295–300`). So the package needs no `portable.txt` [verified in source].
- **Visual C++ runtime.** Dolphin and the Rust DLL need the VC++ 2015–2022 x64 runtime (`MSVCP140.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`). Most PCs with Slippi already have it. The three DLLs can also be copied next to the program from `%VCToolsRedistDir%x64\Microsoft.VC143.CRT\` [reported].
- **Checks in the bundle step,** like the Mac script's `otool` checks:
  - `dolphin-emu-nogui.exe --help` lists `--cout` and `--camera-out`.
  - `dumpbin /dependents` names only Windows DLLs, the VC++ runtime and files in the folder.

### 3.6 Patch changes

Both are in the repo, and the Mac builds and runs with them.

- **0004: initialize `ok`.**
  - **Why.** `bool ok;` (`SlippiCameraExport.cpp:177`) is assigned on every path before it's used. But MSVC's C4701 warning ("potentially uninitialized") is level 4, which `/WX` turns into an error, and `bool ok = false;` rules it out.
  - **Then:**
    1. Regenerate 0004.
    2. Rebuild on the Mac.
    3. Re-run `validate_camera.py readonly` and `static`.
- **0005 (new): stop on Ctrl+Break.**
  - **What NoGUI handles now.** On Windows, NoGUI handles only SIGINT and SIGTERM, through the C runtime's `signal()` (`MainNoGUI.cpp:342–344`) [verified].
  - **Why SIGTERM doesn't help.** Nothing on Windows sends SIGTERM to another process, and Python's `terminate()` there is `TerminateProcess`, a hard kill [reported: Python docs].
  - **Why Ctrl+Break.** It's the console signal that can be aimed at one process group; Ctrl+C can't be [reported: `GenerateConsoleCtrlEvent` docs]. The C runtime turns Ctrl+Break into SIGBREAK. NoGUI doesn't handle SIGBREAK, so today its default action kills Dolphin [reported].
  - **The change.** One line under `#ifdef _WIN32`: `signal(SIGBREAK, signal_handler);`. Ctrl+Break then takes the same path as SIGTERM on the Mac [verified in source]:
    1. `RequestShutdown()` (`Platform.cpp:48–50`).
    2. NoGUI's main loop ends.
    3. `Core::Stop()` closes the recording (`MainNoGUI.cpp:368`).
  - **A second Ctrl+Break** still kills Dolphin, because the C runtime resets the handler before calling it [reported].
  - **On macOS** the patch changes nothing: `_WIN32` code isn't compiled there.

### 3.7 MSVC strictness: what was checked

- **Flags.** `/W4 /WX /GR- /EHsc /utf-8`, with warnings 4100, 4121, 4127, 4200, 4201, 4244, 4245, 4324, 4351 and 4714 turned off (`CMakeLists.txt:262–300`) [verified].
- **Windows macros.**
  - Every `core` source on Windows force-includes `Source/PCH/pch.h` (`/FI`), and `pch.h` includes `<Windows.h>` (lines 96–97) [verified]. So `near`, `far` and `ERROR` are macros in those files.
  - Patch 0004's names avoid them: its struct fields are `near_z` and `far_z`, and "near,far" only appears inside a string [verified].
- **Unused functions.** C4505 is a level-4 warning about internal functions that are never called. Every internal function in 0002 and 0004 is called in the configurations that compile it [verified by reading].
- **fmt.** In the bundled fmt 10.2.1, `fmt::format_to` isn't marked `[[nodiscard]]` (`core.h:2861`), so 0004 can ignore its result [verified].
- **The camera file.** Dolphin's `IOFile` opens files through `_tfopen_s` unless asked to share them (`IOFile.cpp:70–80`) [verified]. No other program can open a file opened that way until it's closed [reported: Microsoft docs]. slp2alpha only reads the camera CSV after Dolphin has exited, so that's fine.
- **Everything else** is [to test]. The first CI run is the test, and any failure there is a compile error with a file and a line.

## 4. GitHub Actions

A workflow in this repo, `.github/workflows/dolphin-windows.yml`, builds the package and uploads it as a zip (Appendix A).

- **Runner.** `windows-2022`, as Slippi's CI. Started by hand only (`workflow_dispatch`).
- **Steps:**
  1. `git config --global core.autocrlf false`, then check out this repo.
  2. Load the MSVC environment (`egor-tensin/vs-shell@v2`) and install Rust 1.88.0.
  3. Run `python tools/dolphin-build/build-windows-mainline.py all` (Appendix A). The script makes its own CMake 3.31 venv, as the Mac script does.
  4. Upload `packages\slippi-playback-mainline` as an artifact, and the build logs.
- **Cache.** None yet: the FFmpeg zip takes seconds to download on a runner. Caching the build folder would make a rebuild after a patch change take minutes instead of half an hour [estimate].
- **What CI can't test.** It can't run Melee, because the ISO can't go into CI. CI stops at `--help` and the dependency check. Renders need a Windows PC (section 7).
- **Practicalities** [reported]:
  - A fork has Actions turned off until they're enabled in its Actions tab.
  - Public repositories get standard runner minutes for free.
  - Artifacts are kept for 90 days by default. A tag can also attach the zip to a release.

## 5. slp2alpha and the tools on Windows

All of these are done (Appendix A). The table keeps what each spot did before the change.

| Where | Today | Change |
|---|---|---|
| `runner.py:138–139` | `start_new_session=True`, which is POSIX only; Python ignores it on Windows [reported] | On Windows: `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` |
| `runner.py:220–232` (`_stop`) | `os.killpg` with SIGTERM, then SIGKILL. Windows has neither `os.killpg` nor `signal.SIGKILL`, so the first stop raises `AttributeError` and leaves Dolphin running [reported: Python docs] | On Windows: `send_signal(signal.CTRL_BREAK_EVENT)`, wait up to 20 s, then `kill()` (Appendix A) |
| `locate.py:43–45` | On Windows, only Ishiiruka is looked for | Look for `packages\slippi-playback-mainline\dolphin-emu-nogui.exe` first. `engine_of()` already recognises the name, `.exe` included [verified] |
| `locate.py:49–50`, `__main__.py:358, 365` | The messages name the Mac build scripts | Name the right script for the platform; on Windows, also the CI zip |
| `config.py:104` | `GFXBackend` defaults to `Metal` | `D3D` on Windows. The backend names are `D3D` (Direct3D 11), `D3D12`, `Vulkan` and `OGL` [verified] |
| `solve.py:36–39` | `--format hevc` uses `hevc_videotoolbox`, which only exists on macOS | Refuse it on Windows with a clear message, and have the render tests skip it there. `mov` already falls back from `prores_videotoolbox` to `prores_ks` (`encoder_choices`) [verified] |
| `locate.py:117` | Says "brew install ffmpeg" | Also name a Windows download. `find_ffmpeg` already checks `ALPHASOLVE_FFMPEG_DIR`, `packages\ffmpeg\` and the PATH [verified]. Use FFmpeg 9.0, as the Mac does (9.0.2) [verified on macOS] |
| `validate_camera.py:163`, `logo_stage.py:89` | Output paths are recognised by `line.startswith("/")`, which a `C:\...` path fails | `Path(line).is_absolute()` |
| `plate.py:46–55` | Blender from `/Applications`, `$BLENDER` or the PATH | Also `%ProgramFiles%\Blender Foundation\Blender *\blender.exe`, newest first |
| `locate.py:77`, `logo_stage.py:41`, `validate_stagedata.py:289` | Caches in `~/.cache` on anything but macOS | Works as is. Using `%LOCALAPPDATA%`, as `render-tests/run.py:48–49` already does, would be tidier |

- **Expected to work unchanged** [estimate]:
  - **The `--cout` progress markers over a pipe.** Each ends with `std::endl`, which flushes it, and the runner strips the `\r` that Windows adds to each line.
  - **The comm file's Windows paths,** which `json` escapes.
  - **Paths with spaces or non-ASCII characters,** for `--camera-out` and the rest. NoGUI's `wmain` converts the command line to UTF-8 (`MainNoGUI.cpp:376–386`), and Dolphin opens files through UTF-16 names (`IOFile.cpp:70–80`) [verified in source].
- **No console windows.** When slp2alpha runs in a terminal, Dolphin and ffmpeg share its console, so no window opens. Ctrl+Break also needs that shared console, so run slp2alpha from a terminal, not with `pythonw` [reported].
- **Reading the recording while it grows.** The streaming solver opens the `.mkv` while Dolphin is writing it. That works only if Dolphin's FFmpeg opens the file without blocking other readers. FFmpeg's file code opens files that way [reported], but it's [to test]. If it fails, `--no-stream` solves after recording instead.
- **Out of scope:**
  - `tools/animelee/build_iso.py` (formerly `build-iso.sh`) needs `xdelta3.exe` on Windows; nothing else.
  - The logo stage's open findings.

## 6. Running it on Windows

1. **Install the prerequisites:**
   - Python 3.9 or newer (the Mac runs 3.9.6) [verified on macOS].
   - numpy and Pillow, only for `track` and `overlay`.
   - Blender 4.4 or newer, for the import.
2. **Unpack:**
   - The CI zip into `packages\slippi-playback-mainline\`.
   - The contents of FFmpeg 9.0's `bin\` folder into `packages\ffmpeg\`. BtbN's static `win64-gpl-9.0` zip works [verified: it's in the release listing]. Alternatively, point `ALPHASOLVE_FFMPEG_DIR` at the `bin\` folder or put FFmpeg on the PATH.
   - If Windows marks the downloaded files as blocked: `Get-ChildItem -Recurse packages | Unblock-File`.
3. **Render,** from `tools\slp2alpha` in a terminal:

   ```bat
   py -m slp2alpha render game.slp --characters-only --export-camera
   ```

4. **The ISO** comes from the Slippi Launcher's settings (`%APPDATA%\Slippi Launcher\Settings`), or from `--iso` [verified: `locate.py:22–27, 64–66`].

- **Your own Slippi install isn't touched.** The build lives in `packages\`, and its settings live in slp2alpha's work folder (`-u`).
- **Defender.** If recordings write slowly, exclude the temporary folder from Windows Defender. A 3-minute game is several GB of FFV1 video [estimate].

## 7. Test plan on Windows

Run these in order. Each step is [to test].

1. **Smoke test.** `dolphin-emu-nogui.exe --help` lists `--camera-out`. Then render a 300-frame clip without the export (`--characters-only --start-frame 1500 --end-frame 1799 --keep`) and check:
   - no window appears;
   - the recording is Matroska with 600 fields;
   - Dolphin stopped cleanly, so the `.mkv` is complete, and Dolphin's log has no "Frame dump failed".
2. **Hard-kill fallback.** Render the same clip, stopping Dolphin with `kill()` instead (temporarily). The solved video should still have all 300 frames [estimate: Dolphin keeps recording for a second after the last frame slp2alpha needs, so those frames should already be on disk].
3. **The camera checks** from [`camera-export.md`](camera-export.md):
   - `readonly`: identical recordings with and without the export.
   - `static` on the six legal stages.
   - `check` with `--raw`.
   - `compare` of a clip against the whole game.
   - `blender` with Windows Blender.
   - `track` on a whole Battlefield game.
4. **Mac against Windows.** `validate_camera.py compare` on a Mac export and a Windows export of the same clip should find no differences [estimate]. The camera comes from the game's own float32 maths. Slippi netplay keeps Mac and Windows players in sync, which requires that maths to give the same results on both [reported]. The videos may differ slightly between Metal and Direct3D; the camera numbers shouldn't.
5. **Render tests.** `tools\render-tests\run.py`, every entry except `--format hevc`.
6. **One long game** (3 minutes or more), for speed, disk use and Defender. On the Mac, whole games render at about half real time, solver included [verified on macOS: 0.52x for the 128 s Battlefield game]. Windows is unmeasured.

If Direct3D 11 records nothing without a window, try `D3D12`, then `Vulkan`, before anything else.

## 8. Risks

| Risk | Mitigation |
|---|---|
| MSVC rejects something in the patches (`/WX`) | CI reports the file and line. Fix it in the patch, then re-check on the Mac |
| NoGUI doesn't compile or link on Windows at this commit (Slippi's CI only builds the Qt program) | The code handles Windows throughout: `_WIN32` sections at `MainNoGUI.cpp:14, 48, 201, 216, 237, 342, 376`, and `PlatformWin32.cpp` [verified]. Fix anything else in a patch |
| CRLF line endings break `git apply` | `.gitattributes` and `core.autocrlf=false` (section 3.2) |
| The prebuilt FFmpeg doesn't link with MSVC | F2: Dolphin's recipe with Matroska added |
| Direct3D 11 doesn't record without a window | `D3D12`, then `Vulkan` |
| Ctrl+Break doesn't reach Dolphin (no shared console) | The `kill()` fallback; run from a terminal |
| The solver can't read the growing `.mkv` | `--no-stream` |
| Paths longer than 260 characters in the Rust build | A short work folder (`ALPHASOLVE_CACHE=C:\asv`) and `core.longpaths` |
| Antivirus slows the build and the recordings | Exclude the work and temporary folders |
| BtbN deletes the pinned FFmpeg build | A copy as a release asset in the fork |
| SmartScreen warns about the unsigned program | It only warns when the program is started from Explorer, not from Python [reported]; or `Unblock-File` |
| Windows on ARM | Out of scope |

## 9. Effort and order of work

| Step | Effort | Windows PC needed? | Status |
|---|---|---|---|
| W1. Initialize `ok` in 0004, add 0005, update `.gitattributes`; rebuild and re-check on the Mac | 0.25 day | No | Done |
| W2. `build-windows-mainline.py` with the F1 FFmpeg | 0.5 day | No: CI runs it | Written; not run on Windows |
| W3. The workflow, iterated until the zip builds (about 30 minutes per run) | 0.5–1 day | No | Written; not run yet |
| W4. slp2alpha and the tools (section 5) | 0.5 day | Only to test | Done; Windows paths untested |
| W5. First renders and the checks (section 7) | 0.5–1 day | Yes | [`plan-windows-remaining.md`](plan-windows-remaining.md) |
| W6. Docs: a Windows section in `camera-export.md` and the README; plan statuses | 0.25 day | No | Pointers done; the Windows section waits for results |
| F2 instead of F1, if needed | +0.5–1 day | No | Only if F1 fails |

- **W5** needs a Windows PC with a GPU, an NTSC 1.02 ISO, and the test replays. `run.py` downloads the replays into `%LOCALAPPDATA%\AlphaSolveVideo\test-replays` (`locate.cache_root()`).
- **What this changes in [`plan-windows.md`](plan-windows.md):**
  - Its Ishiiruka route stays as the no-build option, for plain renders with a window.
  - The background options in its section 5 aren't needed with this build, which never opens a window.
  - Its option B5, a patched Windows build, becomes this plan, built with CMake and Ninja instead of MSBuild.

---

## Appendix A: where it's implemented

The sketches that were here are now real files:

| Plan | File |
|---|---|
| The build (sections 3.1 to 3.5) | `tools/dolphin-build/build-windows-mainline.py` (`fetch`, `configure`, `build`, `bundle`, `all`) |
| Patch changes (section 3.6) | `tools/dolphin-build/patches-mainline/0004-camera-export.patch`, `0005-nogui-windows-ctrl-break.patch` |
| Line endings (section 3.2) | `.gitattributes` (`*.patch` and `*.sh` LF, `*.bat` CRLF) |
| GitHub Actions (section 4) | `.github/workflows/dolphin-windows.yml` |
| Stopping Dolphin (section 3.6, section 5) | `tools/slp2alpha/slp2alpha/runner.py`: `_own_process_group`, `_ask_to_quit`, `_close_windows`, `_stop` |
| The other slp2alpha and tool changes (section 5) | `locate.py` (`cache_root`, `mainline_package`, `build_hint`, `utf8_child_env`), `config.py` (`default_video_backend`), `solve.py` (`missing_encoder`), `__main__.py`, `tools/render-tests/run.py`, `tools/camera-export/validate_camera.py`, `tools/logo-stage/` |

## References

- Pinned Dolphin source: https://github.com/project-slippi/dolphin/tree/c5f635948ed43f4d14a72069343e0cecdc117391
  - `.github/workflows/main.yml`: the Windows job.
  - `CMakeLists.txt`: MSVC flags, `Binary/x64`, `FFMPEG_DIR`, `copy_rust_dll`.
  - `CMake/FindFFmpeg.cmake`.
  - `Externals/FFmpeg-bin/dolphin-build-x64.sh` and `dolphin-readme.txt`.
  - `Source/Core/DolphinNoGUI/`: `MainNoGUI.cpp`, `Platform.cpp`, `PlatformHeadless.cpp`, `CMakeLists.txt`.
  - Headless rendering: `Source/Core/VideoBackends/D3D/D3DMain.cpp`, `D3D12/VideoBackend.cpp`, `Source/Core/VideoCommon/Present.cpp`.
  - `Source/PCH/pch.h`, `Source/Core/Common/IOFile.cpp`, `Source/Core/Common/FileUtil.cpp`.
- Slippi's CI results for the commit: https://api.github.com/repos/project-slippi/dolphin/commits/c5f635948ed43f4d14a72069343e0cecdc117391/check-runs
- FFmpeg builds for Windows: https://github.com/BtbN/FFmpeg-Builds (variants and retention in the README).
- Python: `subprocess` (`CREATE_NEW_PROCESS_GROUP`; `send_signal` and `terminate` on Windows) and `signal.CTRL_BREAK_EVENT`.
- Microsoft: the C runtime's `signal` (`SIGBREAK`; the handler reset), `GenerateConsoleCtrlEvent`, and `fopen_s` (no sharing).
