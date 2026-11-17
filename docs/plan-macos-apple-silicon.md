# Slippi replays to transparent video on Apple Silicon Macs: implementation plan

Status: first version working (native build), November 2026. Section 0 describes what exists and what it measures; the rest of this document is the original plan, kept for its findings and reasoning.
Scope: turn a Slippi replay (`.slp`) into the transparent outputs this repo produces, on an Apple Silicon Mac, unattended, and without taking over the screen.

Evidence tags used throughout:

- **[verified]**: measured, or read in source or on disk, during this investigation.
- **[reported]**: found during research (sources in Appendix H); not re-checked by hand.
- **[estimate]**: a reasoned guess that still needs a measurement.
- **[to test]**: a design choice that needs an experiment before we rely on it.

---

## 0. Current state (November 2026)

What exists:

- **`tools/dolphin-build/build-mac-mainline.sh`** builds Slippi's mainline-based playback Dolphin (`project-slippi/dolphin`, branch `fix/mainline-playback`, pinned commit) natively for Apple Silicon. It uses Dolphin's ARM64 JIT and the Metal backend, and the headless frontend: no window, no Dock icon. FFmpeg 8 handles recording. The build takes about 7 minutes on an M1. Source patches are in `tools/dolphin-build/patches-mainline/`. They add `--cout` progress markers, record only the replay's own frames, use multi-threaded FFV1, and fix two build problems with clang.
- **`python3 -m slp2alpha render REPLAY...`** (run from `tools/slp2alpha`). It refuses stages without background-removal codes. It records lossless FFV1 in Matroska and solves while Dolphin is still recording. It writes `fullTransparent - NAME.mov` (ProRes 4444 with alpha) and `alphaMap - NAME.mov` next to the replay, or into `--out-dir`.
- **`render --characters-only`** doesn't draw the stage (or its particles, the HUD and screen flashes), so it works on every stage and leaves just the fighters, their items and effects. `--hud`, `--hide-items` and `--hide-effects` adjust what's kept. See `docs/characters-only-research.md`, and `docs/stage-backgrounds.md` for what the other legal stages need with the stage visible.
- **`render --static-camera`** keeps the camera still (Melee's fixed camera, which shows the whole stage, and no screen shake). It can be combined with `--characters-only`. See `docs/static-camera.md`.
- **`render --start-frame N --end-frame M`** renders only those frames of a replay (Slippi's frame numbers, as in slippi-js combos), for example one combo. Dolphin skips ahead to the start without drawing, about 4,000 game frames per second. See `docs/clips.md`.
- **`render --shy-guy-sprite IMAGE`** draws Yoshi's Story's Shy Guys with your picture, fitted to the Shy Guy and moving with it (custom textures in Dolphin; replays stay in sync). With `--characters-only`. See `docs/shy-guy-sprite.md`.

Measured on this Mac (M1, 16 GB, other apps running, load average 3–9) [verified]:

| | Old x86 build under Rosetta | Native build |
|---|---|---|
| Playback only | 50 game fps | 232 game fps |
| Playback + recording | 27 game fps | 156 game fps |
| Playback + recording + flicker code | about 9 game fps (one run) | 87–108 game fps (1.45–1.8× real time) |
| Full render, 32 s replay (Battlefield) | – | 31 s (1.03× real time) |
| Full render, 173 s replay (Dream Land) | – | 191 s (0.90× real time) |

Space: about 1.8 GB of temporary recording per minute of gameplay (deleted afterwards). Output: about 1.4 GB per minute for the transparent video and 0.25 GB for the alpha map.

Findings since the plan was written [verified]:

- Mainline's ForceMelee aspect mode assumes the netplay lag-reduction code. On replays it squashes the recording to 640×580. AspectMode::Auto with the aspect-corrected XFB gives the correct 640×528.
- Without "Increase Input Timing Accuracy" (listed as required in the README), the native build skips about one field in 60, which breaks the black/white pairs. `render` always enables it.
- Matroska stores millisecond timestamps, so the solver now pairs frames by position. Pairing by timestamp put about 31 % of frames with the neighbouring game frame.
- Dual-core mode isn't faster (110.6 vs 107.7 game fps), so Slippi's single-core setting stays.
- Apple's ProRes encoder (`prores_videotoolbox`, software on a plain M1) is about twice as fast as `prores_ks` and matches it within 2/255.
- Now that Dolphin runs well above real time, the solver is the limit. Overlapping the two steps gave 1.03× / 0.90× real time on this loaded machine.

Not done yet: stage-visible renders of stages other than Battlefield and Dream Land (M6, see `docs/stage-backgrounds.md`; `--characters-only` already works on every stage), the Windows path, and a double-clickable wrapper (M5). The x86 Ishiiruka build still works, but it opens a flashing window, so `render` refuses it unless given `--allow-window`.

---

## 1. Summary

- **Approach.** Build Slippi's current playback Dolphin (Ishiiruka 3.5.2) for macOS with its video encoder enabled, and run it natively (x86_64 under Rosetta 2) in a hidden background mode. A script feeds it the replay and this repo's Gecko codes, then runs a macOS port of the solver.
- **Why not the Mac app the Slippi Launcher installs?** It was compiled without FFmpeg, so it can't record frames at all [verified].
- **Why not Docker?** A Docker prototype works end to end [verified], but needs about 40–95 minutes per 3-minute match. Dolphin's fast CPU recompiler crashes under Docker's x86 translator, so only the slow interpreter works [verified].
- **Expected speed.** Roughly 3.5–7.5 minutes per 3-minute match, depending on how fast native Dolphin runs on this Mac [estimate]. Milestone M0 measures this before anything is built.
- **Effort.** About 3.5–6 working days to a first version that renders in the background (M0–M5) if the Dolphin build runs on GitHub Actions, or 4–8 days if built locally. Supporting stages other than Dream Land and Battlefield is a separate track (M6).
- **Shelf life.** The build is x86_64 and depends on Rosetta. Apple supports Rosetta for general apps only through macOS 27 [verified]. Move to an Apple Silicon-native build (M7) before upgrading the rendering Mac to macOS 28.

---

## 2. Background

### 2.1 How the technique works

The Gecko code `(EPILEPSY WARNING) Flicker Background Black/White asm v5` paints the stage background black or white on alternate rendered frames. It also switches the game into a "120 fps" mode, so game logic advances only every other rendered frame. Each game frame is therefore rendered twice: once over white, once over black. The stage-specific codes remove the stage background so the flicker color shows through.

The solver compares each pair:

- Where the two renders are identical, the pixel is opaque.
- Where they differ by the full black-to-white range, it is transparent.
- Partial differences give partial alpha.

Color is recovered by dividing the black render by alpha.

### 2.2 The timing consequence

Emulated time runs at half speed. Each game frame costs two video fields, which is 1/30 s of emulated time. Evidence [verified]:

- A replay of 168 game frames produced 336 strictly alternating recorded frames.
- The recording's time base is 1/60 s, and Dolphin drops any frame whose timestamp doesn't advance.

The recording is a 60 fps file that strobes at 30 Hz.

Dolphin's time per replay is therefore:

```
dolphin_seconds ≈ (game_frames × 2) / (60 × S)
```

`S` is Dolphin's unthrottled emulation speed, where 1.0 = 100 %. A 3-minute match is 10,800 game frames. It takes 6 minutes of Dolphin time at S = 1, 3 minutes at S = 2, and 2 minutes at S = 3.

---

## 3. Findings so far

### 3.1 This Mac

| Item | Value |
|---|---|
| CPU | 8-core Apple Silicon (4 performance + 4 efficiency cores) |
| OS and toolchain | macOS 27.2, Xcode 27.1, Apple clang 21, macOS SDK 27.2 |
| Tools | Homebrew ffmpeg 9.0.2; CMake; Ninja; rustup (stable 1.99, with the `x86_64-apple-darwin` target); Docker Desktop (engine 29.9.2, runs amd64 through Rosetta) |
| Slippi | Launcher installed. Playback Dolphin 3.5.2 (x86_64) at `~/Library/Application Support/Slippi Launcher/playback/Slippi Dolphin.app` |
| Melee ISO | NTSC 1.02 (`GALE01`, revision 2); its path is stored in the Launcher settings under `settings.isoPath` [verified] |

### 3.2 What works and what doesn't

| Component | Status | Evidence |
|---|---|---|
| Solver filter graphs on ffmpeg 9 | APNG, MKV, MOV, AVI and WEBM work unchanged. GIF needs the `fifo` filter removed, because current ffmpeg no longer has it | [verified] |
| `Brightest.bat` brightness check | Replaced with a mean-luma check (`signalstats`) | [verified] |
| Solver accuracy | Alpha error 0.13/255 and color error 0.5/255 against synthetic ground truth | [verified] |
| Faster solver math (lookup table) | 4.4× faster; matches the original within 0.007/255 | [verified] |
| Installed Mac playback app | Can't record frames: no FFmpeg linked, and `Renderer::IsFrameDumping()` ignores `DumpFrames` without it | [verified] |
| Linux playback build (3.5.2) in Docker | Records FFV1 at native resolution; whole pipeline works | [verified] |
| Dolphin's recompilers (JIT64, JITIL) in Docker | Crash within seconds | [verified] |
| Old Mac playback build v2.3.7 (2021) | Links FFmpeg 4.4; has FFV1 recording and the `--cout` progress markers | [verified]. Likely too old for current replays [estimate] |
| Windows playback build 3.5.2 | Encoder built in | [verified], see the Windows plan |
| Slippi "mainline" Dolphin (Apple Silicon-native) | No replay playback yet; playback PR #40 is open and its macOS build fails | [reported] |

### 3.3 Why the Docker prototype is slow

- Slippi's playback settings force single-core mode (`CPUThread = False` in the bundled `Sys/GameSettings/GALE01r2.ini`). One thread therefore runs both the emulated CPU and the GPU front end [verified].
- In Docker that thread is pegged at 100 %, while the eight software-rasterizer threads sit at 10–23 % each [verified]. Pixels are not the bottleneck, so lowering the resolution would not help. The run was already at native resolution: 643×528 at 1× with a 73:60 aspect ratio.
- Only the interpreters work under Rosetta for Linux. The cached interpreter is about 1.4× faster than the plain one [verified].
- Measured speed was 1.9–4.4 game frames/s depending on host load, plus 30–60 s of boot [verified]. That is S ≈ 0.06–0.15.

### 3.4 Prototype artifacts

Working prototypes are in a temporary folder (`$TMPDIR/opencode/`), which macOS may clean up:

- `asv/proto.sh`: bash port of `AlphaSolve.bat`.
- `asv/mkfixture.sh`, `asv/cmp.sh`: synthetic ground-truth recordings, and a script that compares outputs against them.
- `dock/`: Dockerfile, config generator (`mkuser.py`), and a container runner with progress and per-thread profiling.
- `linuxpb/`: the extracted Linux playback AppImage.
- `research2/`: the v2.3.7 and mainline DMGs.

The configurations they proved are copied into the appendices of this document. The scripts should be moved into the repo (for example `tools/prototypes/`) before that folder disappears.

---

## 4. Target design

### 4.1 Data flow

```
slp2alpha replay.slp --format png
  │
  ├─ preflight: find the Dolphin build, the ISO (Launcher settings) and ffmpeg;
  │             parse the .slp (stage, last frame)
  ├─ create a temporary Dolphin user folder:
  │             Dolphin.ini, GFX.ini, GameSettings/GALE01.ini (Gecko codes)
  ├─ write comm.json (replay path, start frame, end frame)
  ├─ run Slippi Dolphin (frame-dump build) in background mode
  │             ──► dump/framedump0.avi (FFV1, lossless)
  │             progress comes from --cout markers; stop at the last frame
  ├─ validate the recording (frame count, black/white alternation, pairing);
  │             abort with diagnostics on failure
  ├─ remux and trim (no re-encode)
  └─ alphasolve.sh (lookup-table math)
                ──► "fullTransparent - replay.png", "alphaMap - replay.png"
```

### 4.2 Proposed repository layout

```
Scripts/               existing Windows .bat solver (kept)
Scripts/mac/           alphasolve.sh, SolveTo*.command, droplet build script
tools/slp2alpha/       orchestrator: Python 3, standard library only, shared with Windows
tools/dolphin-build/   CI workflow, patches and local build script for the macOS Dolphin build
tools/docker/          headless Linux fallback (Dockerfile + runner), also usable on Windows
packages/              already gitignored: built Dolphin app, pinned ffmpeg, test fixtures
docs/                  this plan and the Windows plan
```

### 4.3 Per-run working folder

```
$TMPDIR/slp2alpha-XXXX/
  user/Config/Dolphin.ini
  user/Config/GFX.ini
  user/Config/Logger.ini          (only with --debug)
  user/GameSettings/GALE01.ini
  comm.json
  dump/framedump0.avi
  logs/dolphin.stdout
  logs/dolphin.stderr
```

The folder is deleted after a successful run unless `--keep-dump` or `--debug` is given. Your normal Slippi settings are never read or written.

---

## 5. Milestones

### M0: Measure native speed first (gate; about 0.5 day)

**Goal.** Replace the [estimate] figures in section 6 with real numbers before investing in a build.

**Steps.**

1. Copy the v2.3.7 app out of its DMG into `packages/bench/`. It can record; its replay support is older, but that doesn't matter for timing.
2. Generate an isolated user folder (Appendix A) with `EmulationSpeed = 0`, frame dumping on, FFV1, and 1× internal resolution.
3. Play the Battlefield test replay without the flicker code, so nothing strobes. Read game frames per second from the `[CURRENT_FRAME]` markers. In this run, S = game_fps / 60.
4. Optionally repeat with the flicker code. The window strobes, so keep it covered. In this run, S = 2 × game_fps / 60.
5. Repeat step 3 with the installed 3.5.2 app (it can't record) to compare raw speed between the two versions.
6. Note the CPU use of the emulation thread and the frame-dump thread.

**Needs your OK.** It opens a Dolphin window for about a minute.

**Decision.**

- If S ≥ 1.5 with recording on, continue as planned.
- If S is lower, first add the FFV1 threading patch (P4), then check whether the GPU front end is the bottleneck.

### M1: macOS solver (about 0.5–1 day)

**Deliverable.** `Scripts/mac/alphasolve.sh <video> [format]`, plus entry points in Finder.

**Requirements.**

- Runs on macOS's bundled bash 3.2, so no bash 4 features.
- ffmpeg lookup order: `$ALPHASOLVE_FFMPEG`, then `../ffmpeg` next to the scripts, then `packages/ffmpeg/`, then `PATH`, then `/opt/homebrew/bin` and `/usr/local/bin`.
- Uses a private temp folder (`mktemp -d`, removed on exit). The Windows script writes its temporary files into the current folder; this one never does.
- Uses the same output names as the Windows script: `fullTransparent - <name>.<ext>` and `alphaMap - <name>.<ext>`.
- Optional flags:
  - `--first-color black|white` and `--pair-offset 0|1` skip detection; the orchestrator passes known values.
  - `--out DIR`.

**Algorithm.**

1. **Start color.** Compare the mean luma (`signalstats` YAVG) of frames 0 and 1. The brighter one is white.
2. **Pair alignment.**
   - For the pairings (0,1) and (1,2), measure "black brighter than white" violations over the first ~20 pairs with `blend=all_mode=subtract`. A true pair shows the same game frame, and its white-background render is never darker than its black one, so it has zero violations.
   - Pick the pairing that scores about 0. If both score about 0 (a motionless start), use the default and print the warning the README already describes.
   - On the real Slippi recording this test scored 0.0000 for the right pairing and 1.1139 for the wrong one [verified].
3. **Solve** with the lookup-table graph in Appendix C:
   - alpha = the maximum channel of (255 − |white − black|);
   - color = black × 255 / alpha, computed with `lut2` instead of per-pixel `geq` expressions.
4. **Encode** for the requested format:

| Format | Encoder | Notes |
|---|---|---|
| `png` (default) | APNG, `-plays 0` | as today |
| `mkv`, `mov`, `avi` | FFV1, `yuva420p` | as today |
| `webm` | VP9 lossless, `yuva420p` | as today |
| `gif` | `palettegen`/`paletteuse`, alpha threshold 64 | `fifo` removed |
| `prores` (new) | ProRes 4444, `yuva444p10le` | For Final Cut and Premiere. Encoding [verified]; import into editors [to test] |
| `hevc` (new) | VideoToolbox HEVC with alpha (`-alpha_quality`, `-tag:v hvc1`) | Small files for Apple players. Encoding [verified]; playback [to test] |

**Finder integration.**

- `SolveTo*.command` files that call the script.
- A small droplet app built locally with `osacompile`. It was verified to receive dropped files whose names contain spaces and parentheses. The droplet must add `/opt/homebrew/bin` to `PATH` itself.

**Tests.**

- **Smoke:** both sample AVIs in `Resources/`.
- **Ground truth:** synthetic recordings that start on black, start on white, or start one frame late. Pass if the alpha error is ≤ 0.2/255.
- **Regression:** the real Battlefield recording. The lookup-table output must stay within 0.01/255 of the original math.

### M2: Frame-dump-capable playback Dolphin for macOS (about 0.5–1 day on CI, 1–3 days locally)

**Base.** `project-slippi/Ishiiruka` at commit `bffe989d` ("release: v3.5.2"), the same version the Launcher installs [verified].

**What has to change.** CMake has to find FFmpeg 4.4 or older:

- `Source/Core/VideoCommon/AVIDump.cpp` uses `av_register_all`, `stream->codec` with `avcodec_copy_context`, and `avcodec_encode_video2`. All of these were removed in FFmpeg 5 [verified].
- `CMakeTests/CheckLib.cmake` (`check_libav`) asks pkg-config for `libavcodec>=54.35.0 libavformat>=54.20.4 libswscale>=2.1.1 libavutil>=52.3.0` [verified].
- Slippi's macOS CI installed a keg-only FFmpeg but never pointed pkg-config at it, so the encoder was silently left out [reported].
- Version 3.5.2 predates commit `7181c23` (April 2026), which turned macOS frame dumping off outright with `AND NOT APPLE` [reported]. 3.5.2 therefore needs no CMake change.

**Minimal FFmpeg 4.4.** Build it as shared libraries, which `Tools/deploy-mac.py` copies into the app's `Frameworks/` folder. `deploy-mac.py` runs as a post-build step in `Source/Core/DolphinWX/CMakeLists.txt` [verified]. Homebrew's `ffmpeg@4` is 4.4.8 [verified].

```sh
./configure --prefix="$FFMPEG44" \
  --enable-shared --disable-static --disable-programs --disable-doc \
  --disable-autodetect --disable-everything \
  --enable-encoder=ffv1,mpeg4 --enable-muxer=avi,matroska --enable-protocol=file \
  --extra-cflags="-mmacosx-version-min=10.13" --extra-ldflags="-mmacosx-version-min=10.13"
# For a cross-build on Apple Silicon, also pass:
#   --arch=x86_64 --enable-cross-compile --cc="clang -arch x86_64"
```

[to test] `--disable-everything` requires every needed component to be listed. Extend the list if CMake's link test or a recording fails.

#### Option A: GitHub Actions on `macos-15-intel` (recommended)

**Why.**

- Upstream's own macOS playback job runs on `macos-15-intel` (`.github/workflows/pr-build.yml` at `bffe989d`) [verified]. That job still passed in November 2026 [reported].
- GitHub keeps this runner until August 2027 [reported].

**Checklist.**

1. Fork `project-slippi/Ishiiruka` and create a branch `alphasolve-framedump` from `bffe989d`.
2. Add `.github/workflows/mac-playback-framedump.yml` (sketch in Appendix E). It installs upstream's dependency list without `ffmpeg@2.8`, builds FFmpeg 4.4 (cached), sets `PKG_CONFIG_PATH`, and runs `./build-mac.sh playback`.
3. Make the job fail unless the build log contains `libav/ffmpeg found, enabling AVI frame dumps` and `otool -L` lists `libavcodec`.
4. Upload the `.app`, zipped with `ditto -c -k --keepParent`.
5. On the Mac:
   1. Unzip into `packages/slippi-playback-framedump/`.
   2. Run `xattr -dr com.apple.quarantine`.
   3. Ad-hoc sign it: `codesign --force --deep -s -`.

**Needs from you.** A GitHub fork with Actions enabled. macOS runners are free for public repositories.

#### Option B: Local cross-compile on this Mac (no account needed)

Requirements below are [reported] unless marked otherwise:

- CMake flags: `-DIS_PLAYBACK=true -DCMAKE_OSX_ARCHITECTURES=x86_64 -DCMAKE_SYSTEM_PROCESSOR=x86_64 -DCMAKE_OSX_SYSROOT=macosx -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DRust_CARGO_TARGET=x86_64-apple-darwin`.
- Raise the hard-coded deployment target from 10.13 to 11.0. The current libc++ warns that older targets are unsupported.
- Rust: `rustup toolchain install 1.88.0 --target x86_64-apple-darwin`. This is the version pinned by `Externals/SlippiRustExtensions`.
- Install `pkg-config` (`brew install pkgconf`).
- Build x86_64 copies of FFmpeg 4.4 and of any dependency that `Externals/` doesn't provide. Homebrew no longer ships Intel bottles for current macOS.
- The macOS 27.2 SDK still links x86_64, including the `-pagezero_size` flags this build uses.
- **Risk:** 2017-era code and the bundled wxWidgets 3.1.4 meet clang 21 and the macOS 27 SDK. The number of compile fixes needed is unknown.

#### Source patches

| ID | Patch | Needed? | Size |
|---|---|---|---|
| P1 | None for 3.5.2. Only point pkg-config at FFmpeg 4.4 | required | CI configuration only |
| P2 | Give the app its own bundle id and name (for example `…slippi-playback-framedump`) in `Source/Core/DolphinWX/Info.plist.in`. Its preferences and App Nap setting then never collide with the Launcher's app | recommended | a few lines |
| P3 | Background mode (M4, sketch in Appendix F) | recommended | ~30–60 lines |
| P4 | FFV1 slices and threads in `AVIDump.cpp` | only if M0 shows encoding limits speed, or for 2× resolution and above | ~5 lines |
| P5 | Exit at `endFrame`: stop emulation once playback passes `endFrame`. With `-b`, Dolphin then quits cleanly and writes the AVI index | optional. Fallback is kill + remux, which is verified | ~10 lines |

#### Acceptance tests

1. The configure log says `libav/ffmpeg found, enabling AVI frame dumps`.
2. `otool -L` lists `@executable_path/../Frameworks/libavcodec.58…`, and `strings` no longer finds "compiled without libav".
3. The Battlefield test replay produces an FFV1 `bgra` 643×528 AVI with about 336 strictly alternating frames and zero pairing violations (Appendix D).
4. Alpha maps match the Docker reference recording within a small tolerance. Rendering runs on a different GPU, so the output isn't bit-identical.

### M3: Orchestrator `slp2alpha` (about 1–2 days)

**Language.** Python 3, standard library only, shared with Windows. macOS ships `/usr/bin/python3` with the Command Line Tools; this Mac has 3.9.6 [verified].

**Command line.**

```
slp2alpha REPLAY.slp [REPLAY2.slp ...]
  --format png|mkv|mov|avi|webm|gif|prores|hevc   default png
  --out DIR                 default: next to each replay
  --start N --end N         game frames; default: the whole game
  --scale 1|2|3             internal resolution; default 1 (native)
  --background | --windowed default --background
  --hud | --no-hud          bundled "Optional: Hide HUD" code
  --keep-dump --debug
  --jobs N                  replays rendered in parallel
  --dolphin PATH --iso PATH --ffmpeg PATH
  --allow-uncovered-stage
```

**Steps.**

1. **Preflight.**
   - **Dolphin:** `--dolphin`, otherwise `packages/slippi-playback-framedump/`. Check once that the build can record (the "compiled without libav" string must be absent).
   - **ISO:** `--iso`, otherwise `settings.isoPath` from `~/Library/Application Support/Slippi Launcher/Settings` [verified key]. Check that the disc header is `GALE01` with revision byte 2, because the codes target version 1.02.
   - **ffmpeg and ffprobe:** present.
2. **Parse the replay.**
   - `.slp` is UBJSON: `{U\x03raw[$U#l`, a 4-byte length, the event stream, then `metadata` [verified].
   - Event 0x35 lists payload sizes. Game Start (0x36) holds the stage id as a big-endian u16 at offset 0x13 [verified: 31 = Battlefield on the test replay].
   - Last frame: `metadata.lastFrame` [verified present], otherwise the last frame event.
   - Refuse stages without background codes (see M6) unless `--allow-uncovered-stage` is given.
3. **User folder.** Write the files in Appendix A. `--scale` sets `EFBScale` (2 = 1×, 4 = 2×, 6 = 3×) [verified enum].
4. **comm.json** (Appendix B).
   - Dolphin records only frames strictly between `startFrame` and `endFrame`, and never records fast-forwarded frames [verified in `AVIDump.cpp`].
   - Use `startFrame = start − 1` (default −123) and `endFrame = last + 1`.
5. **Launch** the app's binary directly rather than with `open`, so stdout can be read:
   ```
   ".../Slippi Dolphin.app/Contents/MacOS/Slippi Dolphin" -b -e ISO -i comm.json -u USERDIR \
       --cout --hide-seekbar --output-directory DUMPDIR
   ```
   - Set the environment variable `SLIPPI_BACKGROUND=1` (patch P3).
   - Read stdout and stderr continuously. Slippi's Launcher notes that undrained pipes can deadlock Dolphin's renderer on macOS [reported].
6. **Progress.**
   - Parse `[FILE_PATH]`, `[PLAYBACK_START_FRAME]`, `[GAME_END_FRAME]`, `[PLAYBACK_END_FRAME]` and `[CURRENT_FRAME] n` [verified].
   - Show the percentage done and the current speed.
   - Abort if no replay frame appears within ~90 s, or if progress stalls for 30 s.
7. **Stop.**
   - When `[CURRENT_FRAME] ≥ endFrame − 1`, wait ~1 s and ask the app to quit (P5, or an Apple Event quit).
   - Send SIGTERM after 5 s, then SIGKILL.
   - A killed run leaves an AVI without an index and a damaged last packet. `ffmpeg -c copy` recovers everything before it [verified].
8. **Validate** (Appendix D):
   - codec `ffv1`, pixel format `bgra`, expected size;
   - frame count ≈ 2 × recorded game frames, ±2 at the edges;
   - black/white alternation;
   - pairing check.

   On failure, keep the recording and logs and explain what went wrong.
9. **Remux and trim** to MKV with `-c copy`. Then **solve**, passing the known start color and pair offset.
10. **Clean up**, unless `--keep-dump` or `--debug` is given.

**Gecko codes.**

- Paste `Resources/Required Codes.txt` into `[Gecko]` verbatim.
- Enable codes by name without the `[Author]` tag, and disable Slippi's bundled `Optional: Show Player Names` [verified working].
- Known-good set: the flicker code, both stage codes, and Disable Screen Shake [verified].
- A/B-test "Increase Input Timing Accuracy" and "Reduce Debug Develop Animation Info Display Lag" before enabling them by default. In playback the inputs come from the replay, and pairs alternated cleanly without these codes [verified].
- Expose the bundled `Optional: Hide HUD` and `Optional: Hide Waiting For Game` codes as flags.

**Parallel rendering.**

- Each job gets its own user folder, with the spectator server off. That avoids port clashes and the macOS firewall and Local Network prompts.
- Each instance mostly uses one core (single-core mode), so 2–4 jobs suit this 8-core Mac [estimate].

### M4: Background rendering on macOS (about 0.5–1 day on top of M2)

**Goal.** Renders never take focus, never show the strobing window, and keep full speed while you work. Never showing the strobe is also a photosensitivity safeguard.

**What Dolphin does today** [verified in source]:

- `DolphinApp::AfterInit` calls `main_frame->Raise()`. After booting the game it calls `main_frame->RaiseRenderWindow()` (`Source/Core/DolphinWX/Main.cpp`).
- The OpenGL context setup calls `[window makeKeyAndOrderFront:nil]` (`Source/Core/Common/GL/GLInterface/AGL.mm`).
- `WxUtils::SetWindowSizeAndFitToScreen` moves any window placed more than 1000 px outside the screens back on screen, so placing the window off-screen doesn't work.
- With `InternalResolutionFrameDumps = True` on OpenGL, recordings come from an offscreen framebuffer at internal resolution (`DumpFrameUsingFBO` in `VideoBackends/OGL/Render.cpp`), not from the window. The window's size and visibility don't affect the output.
- Playback builds use OpenGL by default on macOS (`VideoBackendBase.cpp`).

**Tiers.**

| Tier | How | Added work | Notes |
|---|---|---|---|
| 0 | Windowed (not fullscreen); App Nap off for the app (`defaults write <bundle-id> NSAppSleepDisabled -bool YES`); move the window to another Space | none | Still jumps to the front and strobes at launch. Fallback only |
| 1 (recommended) | Patch P3: background mode behind `SLIPPI_BACKGROUND=1` | ~0.5–1 day | Never visible, no Dock icon, never changes focus |
| 2 | Docker headless (works today) | none | No window at all, but 40–95 minutes per match. Fine for overnight batches |

**What patch P3 does** (sketch in Appendix F):

1. **At startup.**
   - Switch to `NSApplicationActivationPolicyAccessory`, so there's no Dock icon or menu bar.
   - Hold an `NSProcessInfo` activity (`NSActivityUserInitiatedAllowingIdleSystemSleep | NSActivityLatencyCritical`), so App Nap and timer throttling stay off.
2. **No raising.** Skip `Raise()` and `RaiseRenderWindow()`, and replace `makeKeyAndOrderFront:` with an order-back that doesn't activate the app.
3. **Invisible window.** As soon as the main window exists, make it invisible but keep it alive: alpha 0, ignores mouse events, excluded from window cycling and Mission Control.
   - Hiding it completely (`orderOut:`) is the alternative.
   - Test both, because an OpenGL context whose view isn't on screen may report an invalid drawable [to test].
4. **No idle sleep.** Wrap batch runs in `caffeinate -i` so the Mac doesn't sleep in the middle of a render.

**Verification.**

- Render the test replay windowed and in background mode. Frame counts, alternation and speed must match.
- Repeat with the display asleep and with another app fullscreen [to test].

### M5: Packaging and user experience (about 0.5 day)

- **Release zip for macOS:** `Scripts/mac/`, `tools/slp2alpha/`, the docs and the code lists.
  - Dolphin is GPL, so a built app may be shared together with the fork's source.
  - Melee ISOs are never shipped.
- **Finder:** a Quick Action or droplet ("Render with AlphaSolve") for `.slp` files, and a `.command` wrapper so Terminal isn't needed.
- **First-run check:** prints anything that's missing (ffmpeg, the Dolphin build, the ISO).

### M6: Stage coverage (separate track)

| Stage | Internal id | Background removal |
|---|---|---|
| Battlefield | 31 | Yes (Required codes) |
| Dream Land | 28 | Yes (Required codes) |
| Yoshi's Story | 8 | Partial (Optional: removes the box; waves and islands remain) |
| Fountain of Dreams | 2 | Partial (Optional codes) |
| Final Destination | 32 | No (only "disable background transitions") |
| Pokémon Stadium | 3 | No |
| All other stages | – | No |

Stage ids are [reported]; coverage comes from `Resources/*.txt` [verified].

**Work per stage.**

1. Find the background draw calls, using Dolphin's debugger and symbols from the Melee decompilation.
2. Write `04xxxxxx 60000000`-style patches like the existing ones.
3. Confirm that the solved alpha is clean while the platforms remain.

This takes about 0.5–2 days per stage [estimate]. Until it's done, `slp2alpha` refuses uncovered stages, or renders them with a warning when `--allow-uncovered-stage` is given.

### M7: Apple Silicon-native build (before macOS 28)

**Why.**

- Rosetta stays general-purpose only through macOS 27 [verified, Apple support article].
- The last Intel macOS runner on GitHub retires in August 2027 [reported].

**Target.** Slippi's mainline Dolphin (`project-slippi/dolphin`), once replay playback lands in PR #40. Today that PR [reported]:

- fails to build on macOS;
- has no `--cout` markers;
- has seeking disabled;
- doesn't pass `-DSLIPPI_PLAYBACK=true` on macOS (PR #39 fixes this).

Mainline's macOS builds already link FFmpeg 8 and can record FFV1 with `-C Graphics.Settings.DumpCodec=ffv1` [reported].

**Work if we do it before upstream finishes.**

- Build for arm64 with the PR #39 fix.
- Drop the GCC-only `-fno-ipa-sra` flag when building with clang.
- Bundle the playback Gecko codes.
- Port the `--cout` markers (~20 lines).
- Carry the background patch over.
- Validate replay sync and flicker pairing against 3.5.2 output.

This is about 1–2 weeks, mostly validation [estimate]. The orchestrator only needs a new launch adapter.

---

## 6. Performance model and expected timings

| Setup | S (emulation speed) | Dolphin time, 3-min match | Plus solver | Total |
|---|---|---|---|---|
| Docker, interpreter (measured) | 0.06–0.15 | 41–95 min | ~1.5 min | ~40–95 min |
| Docker, cached interpreter (measured, 1.4×) | 0.09–0.21 | 29–68 min | ~1.5 min | ~30–70 min |
| Native, if S = 1 | 1 | 6 min | ~1.5 min | ~7.5 min |
| Native, if S = 2 | 2 | 3 min | ~1.5 min | ~4.5 min |
| Native, if S = 3 | 3 | 2 min | ~1.5 min | ~3.5 min |

**Encoder ceiling.**

- Single-threaded FFV1 encodes 643×528 frames at about 620 frames/s natively [verified], and perhaps about 450 under Rosetta [estimate].
- That caps S at about 7 at 1× resolution, but only about 2 at 2× resolution, which is where patch P4 matters.
- Dolphin's non-FFV1 recording path converts to `yuv420p`, which is lossy for this technique. Other codecs would need a patch too [verified].

**Solver.** About 80 s per 3-minute match at 1× with the lookup-table math [verified on the test replay, extrapolated].

**Disk.** About 116 KB per recorded frame at 1×, so about 2.5 GB of temporary recording per 3-minute match. Solved FFV1 MKVs come to about 1.4 GB [verified per-frame sizes, extrapolated].

**Resolution.** Stay at 1×. 2× and 3× multiply encode, disk and solve costs by 4× and 9×.

---

## 7. Schedule and effort

| Milestone | Depends on | Effort |
|---|---|---|
| M0 Speed check | your OK to open a window | 0.5 day |
| M1 macOS solver | – | 0.5–1 day |
| M2 Dolphin build | – | 0.5–1 day on CI, 1–3 days locally |
| M3 Orchestrator | M1, M2 | 1–2 days |
| M4 Background mode | M2 | 0.5–1 day |
| M5 Packaging | M3, M4 | 0.5 day |
| **First version (M0–M5)** | | **~3.5–6 days on CI, ~4–8 days locally** |
| M6 Stage codes | – | 0.5–2 days per stage |
| M7 Apple Silicon-native | upstream PR #40 | 1–2 weeks |

M1 and M2 can run in parallel, since CI time is mostly waiting.

---

## 8. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Local build hits many compile errors with clang 21 and the macOS 27 SDK | medium | Use Option A: CI on the toolchain Slippi itself uses |
| Native speed is lower than expected | low–medium | M0 measures first; FFV1 threading patch; profile the GPU front end |
| The hidden window gets throttled, or the GL context rejects a hidden view | medium | Alpha-0 window variant; activity assertion; speed-parity test |
| Dropped or duplicated frames break the pairing | low | Validation aborts with diagnostics. By design, Dolphin skips frames whose timestamp doesn't advance [verified]. Nothing fast-forwards inside the recorded range |
| macOS 28 limits Rosetta; Intel CI runner retires August 2027 | certain (it's a date) | Keep the built app; don't upgrade the rendering Mac until M7 is done |
| New replay formats need a newer playback version | medium | The patch set is small; rebase onto the next Ishiiruka playback tag |
| Uncovered stages produce opaque backgrounds | certain until M6 | Refuse or warn; M6 |
| The strobing window is visible | – | Background mode is the default |
| A killed process leaves an unfinished AVI | – | P5 clean exit; remux fallback (verified) |
| GPL and ISO distribution | – | Publish the fork alongside any shared app; never ship ISOs |

---

## 9. Decisions needed

1. May M0 open a Dolphin window for about a minute? The first run doesn't strobe.
2. For M2, use a GitHub fork with Actions (Option A, recommended) or a local build (Option B)?
3. Write the orchestrator in Python and share it with Windows (recommended), or in bash for macOS only?
4. Default output: APNG as today, or MKV or ProRes for video editors?
5. Uncovered stages: refuse them (recommended), or warn and render anyway?

---

## Appendix A: Isolated Dolphin configuration

These files worked in the Docker run [verified].

`user/Config/Dolphin.ini`

```ini
[Core]
SlippiEnableSpectator = False
SlippiJukeboxEnabled = False
EmulationSpeed = 0
; Docker only: CPUCore = 0 (interpreter) or 5 (cached interpreter).
; Natively, keep the default (the JIT recompiler).
[Movie]
DumpFrames = True
DumpFramesSilent = True
[DSP]
Backend = No audio output
[Display]
Fullscreen = False
RenderToMain = True
RenderWindowAutoSize = True
[Interface]
ConfirmStop = False
UsePanicHandlers = False
```

`user/Config/GFX.ini`

```ini
[Settings]
UseFFV1 = True
InternalResolutionFrameDumps = True
AspectRatio = 5      ; 73:60, which gives 643×528 recordings at 1×
EFBScale = 2         ; 2 = 1×, 3 = 1.5×, 4 = 2×, 6 = 3×, 7 = 4×
[Hardware]
VSync = False
```

`user/GameSettings/GALE01.ini` (`GALE01r2.ini` is also loaded; the verified run used `GALE01.ini`)

```ini
[Gecko]
; contents of Resources/Required Codes.txt, verbatim
[Gecko_Enabled]
$(EPILEPSY WARNING) Flicker Background Black/White asm v5
$Disable Dreamland Background
$Disable Battlefield Background + Particles
$Disable Screen Shake
[Gecko_Disabled]
$Optional: Show Player Names
```

Slippi's own playback codes (`Required: General Codes`, `Required: Slippi Playback`, `Recommended: Slippi Recording`) stay enabled from the app's `Sys` folder [verified].

## Appendix B: `comm.json`

```json
{
  "mode": "normal",
  "replay": "/absolute/path/to/replay.slp",
  "startFrame": -123,
  "endFrame": 46,
  "isRealTimeMode": false,
  "shouldResync": true,
  "rollbackDisplayMethod": "off",
  "commandId": "5f0c2a52-0d1e-4c43-9a51-0c3b8d1f7e10"
}
```

- Keys and defaults come from `Source/Core/Core/Slippi/SlippiReplayComm.cpp` [verified].
- `rollbackDisplayMethod` must stay `off`, because the other modes rewind with savestates [reported].
- A `startFrame` above −123 makes playback fast-forward to it, and fast-forwarded frames aren't recorded [verified].

## Appendix C: Solver filter graph (lookup-table version)

`SEL_B` and `SEL_W` select the black and the white frame of each pair. They are the same expressions `AlphaSolve.bat` builds. The real Slippi recording was "starts black, offset 1".

| Start color | Pair offset | `SEL_B` | `SEL_W` |
|---|---|---|---|
| black | 0 | `mod(n-1\,2)` | `mod(n\,2)` |
| black | 1 | `gt(n\,0)*mod(n-1\,2)` | `gt(n\,0)*mod(n\,2)` |
| white | 0 | `mod(n\,2)` | `mod(n-1\,2)` |
| white | 1 | `gt(n\,0)*mod(n\,2)` | `gt(n\,0)*mod(n-1\,2)` |

```
[0]split=3[a][b][c];
[a]select=SEL_B,setpts=PTS-STARTPTS[blk];
[b]select=SEL_W,setpts=PTS-STARTPTS[wht];
[c]select=SEL_B,setpts=PTS-STARTPTS[blk2];
[blk]format=gbrp[v1];[wht]format=gbrp[v2];
[v1][v2]blend=all_mode=difference,negate,format=yuv420p[map];
[map]setpts=0.5*PTS[alphaMap];
[alphaMap]split=2[alphaMapUse][out2];
[alphaMapUse]format=gbrp,extractplanes=r+g+b[ar][ag][ab];
[ar][ag]blend=all_mode=lighten[arg];
[arg][ab]blend=all_mode=lighten,split=2[am1][am2];
[blk2]setpts=0.5*PTS,format=gbrp[dg];
[am2]format=gbrp[ag3];
[dg][ag3]lut2=c0='if(y,min(255,x*255/y),0)':c1='if(y,min(255,x*255/y),0)':c2='if(y,min(255,x*255/y),0)'[unp];
[unp][am1]alphamerge,format=argb[out1]
```

- `[out1]` is the transparent video and `[out2]` is the alpha map.
- The `max(r,g,b)` step (two `lighten` blends) is bit-identical to the original `geq` expression. The `lut2` division matches the original within 0.007/255 [verified].

## Appendix D: Recording validation

Black/white alternation (mean luma of each frame):

```sh
ffmpeg -v error -i framedump0.avi \
  -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=yavg.txt" -f null -
```

Values should alternate between dark and bright. Whole-screen flashes such as "GO!" can blur this, so the pairing test below is the deciding check.

Pairing: the mean of "black brighter than white" violations over all pairs. It is about 0 for the right pairing:

```sh
ffmpeg -v error -i framedump0.avi -filter_complex \
  "[0:v]format=gbrp,split[a][b];
   [a]select=SEL_B,setpts=N/TB/60[blk];
   [b]select=SEL_W,setpts=N/TB/60[wht];
   [blk][wht]blend=all_mode=subtract:shortest=1,format=gray,
     signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-[o]" \
  -map "[o]" -f null -
```

On the real recording this scored 0.0000 for the right pairing and 1.1139 for the wrong one [verified].

Recovering a killed recording (`N` = number of good frames):

```sh
ffmpeg -v error -i framedump0.avi -c copy -frames:v N recording.mkv
```

## Appendix E: CI workflow sketch (Option A)

This is a sketch adapted from upstream's macOS job; adjust it to match `.github/workflows/pr-build.yml` at `bffe989d`.

```yaml
name: macOS playback with frame dumping
on: workflow_dispatch
jobs:
  build:
    runs-on: macos-15-intel
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
          fetch-depth: 0              # upstream reads git tags for the version string
      - name: Dependencies (upstream list without ffmpeg@2.8)
        run: |
          brew install libpng pkgconfig libao sound-touch hidapi
          brew uninstall cmake || true
          brew install performous/pinned_cmake3/cmake@3.31.7
      - name: Rust (version pinned by Externals/SlippiRustExtensions/rust-toolchain.toml)
        run: |
          ver=$(sed -rn 's/^channel = "(.*)"/\1/p' Externals/SlippiRustExtensions/rust-toolchain.toml)
          rustup toolchain install "$ver"
      - uses: actions/cache@v4
        id: ffcache
        with:
          path: ~/ffmpeg44
          key: ffmpeg-4.4.8-min-macos15-x86_64-v1
      - name: Minimal FFmpeg 4.4
        if: steps.ffcache.outputs.cache-hit != 'true'
        run: |
          curl -L -o ff.tar.xz https://ffmpeg.org/releases/ffmpeg-4.4.8.tar.xz
          tar xf ff.tar.xz && cd ffmpeg-4.4.8
          ./configure --prefix="$HOME/ffmpeg44" --enable-shared --disable-static \
            --disable-programs --disable-doc --disable-autodetect --disable-everything \
            --enable-encoder=ffv1,mpeg4 --enable-muxer=avi,matroska --enable-protocol=file \
            --extra-cflags=-mmacosx-version-min=10.13 --extra-ldflags=-mmacosx-version-min=10.13
          make -j"$(sysctl -n hw.ncpu)" && make install
      - name: Build playback
        run: |
          export PKG_CONFIG_PATH="$HOME/ffmpeg44/lib/pkgconfig"
          export LIBRARY_PATH="$LIBRARY_PATH:/usr/local/lib"
          ./build-mac.sh playback 2>&1 | tee build.log
          grep -q "libav/ffmpeg found, enabling AVI frame dumps" build.log
          otool -L "build/Binaries/Slippi Dolphin.app/Contents/MacOS/Slippi Dolphin" | grep -q libavcodec
      - name: Package
        run: ditto -c -k --keepParent "build/Binaries/Slippi Dolphin.app" slippi-playback-framedump-mac.zip
      - uses: actions/upload-artifact@v4
        with:
          name: slippi-playback-framedump-mac
          path: slippi-playback-framedump-mac.zip
```

## Appendix F: Background-mode patch sketch (P3)

This adds a new macOS-only file. Dolphin's `.mm` files use manual reference counting, hence the `retain`.

```objc
// Source/Core/DolphinWX/BackgroundMode.mm
#import <AppKit/AppKit.h>
#include <cstdlib>
#include "DolphinWX/BackgroundMode.h"

static id s_activity = nil;

bool BackgroundMode::Enabled() { return std::getenv("SLIPPI_BACKGROUND") != nullptr; }

// Call first thing in DolphinApp::OnInit.
void BackgroundMode::OnAppStart()
{
  if (!Enabled()) return;
  [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];   // no Dock icon, no menu bar
  s_activity = [[[NSProcessInfo processInfo]
      beginActivityWithOptions:(NSActivityUserInitiatedAllowingIdleSystemSleep | NSActivityLatencyCritical)
                        reason:@"Rendering Slippi replay"] retain];      // keeps App Nap and timer throttling off
}

// Call after the main frame's Show() and in cInterfaceAGL::Create instead of makeKeyAndOrderFront:.
void BackgroundMode::Conceal(NSWindow* window)
{
  if (!Enabled() || window == nil) return;
  [window setAlphaValue:0.0];
  [window setIgnoresMouseEvents:YES];
  [window setCollectionBehavior:NSWindowCollectionBehaviorTransient | NSWindowCollectionBehaviorIgnoresCycle];
  [window orderBack:nil];   // variant to test: [window orderOut:nil]
}
```

Call sites:

- `DolphinApp::OnInit`: `BackgroundMode::OnAppStart()`.
- `DolphinApp::AfterInit`: skip `main_frame->Raise()` and `RaiseRenderWindow()` when `Enabled()`.
- `CFrame` constructor, right after `Show()`: `Conceal(...)` on the frame's `NSWindow`. On macOS, wxWidgets' `GetWXWindow()` returns it [to test].
- `cInterfaceAGL::Create`: call `Conceal(window)` instead of `[window makeKeyAndOrderFront:nil]` when `Enabled()`.

## Appendix G: Docker fallback recipe (works today, slow)

- **Image:** `ubuntu:22.04` for `linux/amd64` with these packages:
  - X and OpenGL: `xvfb xauth libgl1 libglx0 libopengl0 libegl1 libgl1-mesa-dri libglx-mesa0 libsm6 libice6 libx11-6 libxcb1 libxext6 libxrandr2 libxi6 libxcursor1 libxinerama1 libxxf86vm1 libdrm2`
  - Audio, USB and fonts: `libasound2 libusb-1.0-0 libudev1 libfontconfig1 libfreetype6 libfribidi0 libharfbuzz0b fonts-dejavu-core`
  - GTK dependencies: `libgdk-pixbuf-2.0-0 libglib2.0-0 libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 librsvg2-2 shared-mime-info adwaita-icon-theme hicolor-icon-theme`
- **Dolphin:** `playback-3.5.2-Linux.zip` contains the AppImage. The AppImage's own `--appimage-extract` fails under Rosetta. Instead, extract its SquashFS with `unsquashfs -o 944632` (for 3.5.2: the offset is the end of the ELF section headers) [verified].
- **Run:**
  - `docker run --platform linux/amd64 --shm-size=4g --network none`, mounting the app and the ISO read-only;
  - then `xvfb-run -a -s "-screen 0 1280x1024x24" /app/usr/bin/dolphin-emu …` with `LD_LIBRARY_PATH=/app/usr/lib` and `LIBGL_ALWAYS_SOFTWARE=1`;
  - with `CPUCore = 0` or `5` in `Dolphin.ini`.
- **`--shm-size` is required.** With Docker's default 64 MB, Slippi's first savestate crashes in `Memory::DoState` [verified].

## Appendix H: References

- **Ishiiruka source at `bffe989d` (v3.5.2):** https://github.com/project-slippi/Ishiiruka/tree/bffe989d
  - `Source/Core/VideoCommon/AVIDump.cpp`, `RenderBase.cpp`, `VideoBackendBase.cpp`, `VideoConfig.h`
  - `Source/Core/VideoBackends/OGL/main.cpp`, `Render.cpp`
  - `Source/Core/Common/GL/GLInterface/AGL.mm`
  - `Source/Core/DolphinWX/Main.cpp`, `Frame.cpp`, `FrameTools.cpp`, `WxUtils.cpp`, `Info.plist.in`, `CMakeLists.txt`
  - `Source/Core/Core/Slippi/SlippiReplayComm.cpp`, `SlippiPlayback.cpp`
  - `CMakeTests/CheckLib.cmake`, `build-mac.sh`, `.github/workflows/pr-build.yml`, `Tools/deploy-mac.py`
- **Playback releases** (3.5.2 for Mac, Windows and Linux; 2.3.7 for Mac): https://github.com/project-slippi/Ishiiruka-Playback/releases
- **Mainline playback work:** https://github.com/project-slippi/dolphin/pull/40 , https://github.com/project-slippi/dolphin/pull/39 , and the frame-dumping CI change https://github.com/project-slippi/dolphin/pull/34
- **Intel macOS runner timeline:** https://github.com/actions/runner-images/issues/13045
- **Rosetta timeline:** https://support.apple.com/en-us/102527
- **Prior art for replay-to-video automation:** https://github.com/davisdude/slp2mp4
