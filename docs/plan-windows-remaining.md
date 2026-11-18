# Windows: the remaining work, on a Windows machine

Status: plan, November 2026. The code is prepared for Windows: [`plan-windows-mainline.md`](plan-windows-mainline.md) has what was done and why. None of it has run on Windows yet. This is what's left, in order. Step 1 needs only GitHub; the rest need a Windows PC with a GPU.

Evidence tags, as in the other plans:

- **[verified]**: measured on the Mac, or read in source, during the preparation.
- **[estimate]**: needs a measurement.
- **[to test]**: needs the experiment this plan describes.

---

## 1. At a glance

| Step | Where | Effort | Done when |
|---|---|---|---|
| 1. Build the Windows package | GitHub Actions (or the PC) | 0.5–1 day, most of it waiting for builds | The zip exists, and its `--help` lists `--camera-out` |
| 2. Set up the PC | PC | 0.5 hour | Section 3's list is installed |
| 3. First render | PC | 0.25 day | Every row of section 4's table holds |
| 4. The camera export | PC | 0.25–0.5 day | The Windows export equals the Mac's; the checks pass |
| 5. Render tests and a long game | PC | 0.25 day, plus about an hour of rendering | All entries pass, except `--format hevc` (SKIP) |
| 6. Write down the results | Anywhere | 0.25 day | The docs say what works on Windows |
| **Total** | | **1.5–2.5 days** | |

Already done on the Mac, so not repeated here [verified]:

- The Mac still builds with all five patches, and renders the same way:
  - its Dolphin config files are byte-identical to before;
  - its camera export has identical samples;
  - the render tests measure the same transparency and pairing values.
- The Windows build script's `fetch` and patch steps work. Its `configure`, `build` and `bundle` steps refuse to run off Windows.
- `tools/animelee/build_iso.py` builds a byte-identical Animelee ISO.

## 2. Step 1: build the package

### 2.1 On GitHub (recommended)

1. **Turn on Actions** in the fork's Actions tab, if they're off. Forks start with them off.
2. **Start the build:** Actions, then "Windows playback Dolphin", then Run workflow. From a terminal: `gh workflow run dolphin-windows.yml`, then `gh run watch`. It takes about 30 minutes [estimate: Slippi's own Windows build of this commit took 26.3 minutes].
3. **Get the result:** download the `slippi-playback-mainline-windows` artifact from the run's page, or run `gh run download --name slippi-playback-mainline-windows --dir packages/slippi-playback-mainline` on the PC.

If it fails, the `build-logs` artifact has `mainline-configure.log` and `mainline-build.log`. The likely failures, in the order the build meets them:

| Where | Symptom | What to do |
|---|---|---|
| Patches | "doesn't apply", or "has Windows (CRLF) line endings" | On a fresh runner neither should happen; the message says how to reset the checkout |
| Configure | "CMake did not find FFmpeg", or "found another FFmpeg" | `FFMPEG_DIR` isn't reaching CMake's `FindFFmpeg.cmake` |
| Compile | An MSVC warning in a patch, which `/WX` makes an error (file and line in the log) | Fix it in the patch (below), then run the workflow again |
| Compile | FFmpeg 8.1's headers under MSVC | Use option F2 instead (plan-windows-mainline.md, section 3.3) |
| Link | Unresolved `av_*` symbols, from the MinGW-built import libraries | F2 as well |
| Bundle | "DLLs that are neither in the package nor in Windows", or `--help` fails | The message names the DLL or the missing option |

**Fixing a patch from the Mac:**

1. Edit the file in `~/Library/Caches/AlphaSolveVideo/mainline`.
2. Regenerate the patch from a worktree of the pinned commit. Apply the patches before it, copy in the edited files, and `git diff`: the same steps that made 0004 and 0005.
3. Check the Mac still builds: `build-mac-mainline.sh build` and `bundle`.
4. Push, and run the workflow again.

### 2.2 On the PC itself

Install Visual Studio 2022 or its Build Tools with the "Desktop development with C++" workload, Git, Python 3.9 or newer, and Rust (rustup). Then, from any terminal:

```bat
set ALPHASOLVE_CACHE=C:\asv
py tools\dolphin-build\build-windows-mainline.py
```

A short `ALPHASOLVE_CACHE` keeps the Rust build's paths under Windows' 260-character limit. The script finds Visual Studio itself. The first build takes about 20–40 minutes [estimate], and the package lands in `packages\slippi-playback-mainline\`.

## 3. Step 2: set up the PC

- **Python 3.9 or newer** (`winget install Python.Python.3.12`). numpy and Pillow, only for `track` and `overlay`: `py -m pip install numpy pillow`.
- **FFmpeg for the solver**, version 9.0 as on the Mac. Either `winget install Gyan.FFmpeg`, or the contents of the `bin\` folder of BtbN's `win64-gpl-9.0` zip in `packages\ffmpeg\`.
- **The package** in `packages\slippi-playback-mainline\`. If Windows marks the downloaded files as blocked: `Get-ChildItem -Recurse packages | Unblock-File`.
- **A Melee NTSC 1.02 ISO.** The Slippi Launcher's setting is used, or pass `--iso`.
- **Blender 4.4 or newer**, for the import and for `validate_camera.py blender`.
- **The test replays:** `py tools\render-tests\run.py --fetch-only` downloads them to `%LOCALAPPDATA%\AlphaSolveVideo\test-replays`.
- **Optional:** `xdelta3.exe` for `--animelee`, then `py tools\animelee\build_iso.py --xdelta3 PATH`.

## 4. Step 3: the first render

From `tools\slp2alpha`, in a terminal (not `pythonw`):

```bat
py -m slp2alpha render %LOCALAPPDATA%\AlphaSolveVideo\test-replays\DishonestMuddyCoyote.slp --characters-only --start-frame 1500 --end-frame 1799 --keep
```

On the Mac this takes about 11 seconds [verified]. Each row of the table is [to test]:

| What | How to tell | If it doesn't |
|---|---|---|
| No window opens | Nothing appears on screen | It's not the headless build: check what `--dolphin` or `packages\` points at |
| Direct3D 11 records without a window | The render finishes, and the kept work folder has `user\Dump\Frames\*.mkv` with 600 fields | Try `--backend D3D12`, then `--backend Vulkan` |
| Progress arrives | The progress line counts frames | Look at `logs\dolphin.stdout` in the work folder |
| Dolphin stops cleanly (Ctrl+Break, patch 0005) | `logs\dolphin.stdout` ends with "A signal was received. A second signal will force Dolphin to stop.", and `ffprobe -show_entries format=duration` gives the `.mkv` a duration | The hard stop takes over after 20 s: renders take 20 s longer. Check slp2alpha runs in a terminal |
| Solving while recording | The summary says "Dolphin and solver together" | `--no-stream` works around it. The cause would be the growing `.mkv` not being readable while Dolphin writes it |
| The output | `fullTransparent - ... .mov` plays with transparency | |
| Ctrl+C during a longer render | slp2alpha exits, and no `dolphin-emu-nogui.exe` is left in Task Manager | |

Then a path with a space and a non-ASCII character: copy the replay to, for example, `C:\Tmp\Zoë test\a.slp` and render it with `--out-dir "C:\Tmp\Zoë test"` [to test].

## 5. Step 4: the camera export

1. **Against the Mac.** Render the same clip with `--export-camera`, then compare it with the Mac's export, which is in the repo:

   ```bat
   py -m slp2alpha render %LOCALAPPDATA%\AlphaSolveVideo\test-replays\DishonestMuddyCoyote.slp --characters-only --export-camera --start-frame 1500 --end-frame 1799 --out-dir C:\Tmp\cam
   cd ..\..
   py tools\camera-export\validate_camera.py compare tools\camera-export\reference\DishonestMuddyCoyote_1500-1799_characters-only_macos.json "C:\Tmp\cam\camera - DishonestMuddyCoyote (frames 1500 to 1799, characters only, 60 fps).json"
   ```

   It should report 0 differing frames [estimate]. The camera comes from the game's own float32 maths, and Slippi netplay keeps Mac and Windows players in sync, which needs that maths to be the same on both. How any difference looks tells what it is:
   - every sample shifted by one frame: an alignment problem;
   - tiny differences in some numbers: the two CPU recompilers disagree.
2. **The checks** from [`camera-export.md`](camera-export.md), with the Mac's results there to compare against:
   - `check --raw`, on a render kept with `--keep`;
   - `readonly`;
   - `static` on each of the six legal stages;
   - `compare` of a Yoshi's Story clip from 8500 to 8800 against the whole game;
   - `blender`;
   - `track` on the whole Battlefield game.

## 6. Step 5: render tests and a long game

- **`py tools\render-tests\run.py`.** Every entry should pass; `--format hevc` shows SKIP, because VideoToolbox is macOS-only. Results go to `%LOCALAPPDATA%\AlphaSolveVideo\render-test-results\summary.md`.
- **A whole game of 3 minutes or more:**
  - Note its speed ("x real time") against the Mac's, about 0.5x for the 128 s Battlefield game [verified on macOS].
  - Watch disk use. A 3-minute game is several GB of recording.
  - If writes are slow, exclude the temporary folder and the cache folder from Windows Defender.

## 7. Step 6: write down the results

- **`docs/camera-export.md`:** a Windows line in the checks, and drop "macOS-only for now".
- **`README.md`:** a Windows quick start, in place of "nothing has run there yet".
- **`docs/plan-windows-mainline.md`:** mark steps W2, W3 and W5 done, and resolve its [to test] items.
- **Optionally,** attach the zip to a GitHub release, because artifacts expire after 90 days.

## 8. Not covered

| Piece | State |
|---|---|
| `research/` probes | Not ported. `shyguy-probe/sprites.py` uses macOS font paths; `animelee/run-matrix.sh` is a shell script |
| The logo stage on Windows | Its Blender lookup now finds Windows installs, but it's untested there, and its own open findings remain |
| `slp2alpha bench` | Its CPU sampling is macOS-only and is skipped elsewhere |
| Ishiiruka (Slippi's official build) through slp2alpha | Its stop by WM_CLOSE is written but untested. It opens a flashing window, so it needs `--allow-window` |
| Windows on ARM, Linux | No build script |
