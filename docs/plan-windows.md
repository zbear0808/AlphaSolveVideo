# Slippi replay rendering on Windows: scope and effort

Status: estimate, November 2026.
Companion to [`plan-macos-apple-silicon.md`](plan-macos-apple-silicon.md). Pieces shared by both platforms are specified there: the orchestrator, the Dolphin configuration, recording validation and the faster solver math.

This plan covers Slippi's official Windows build (Ishiiruka). [`plan-windows-mainline.md`](plan-windows-mainline.md) instead brings the macOS build to Windows: the patched mainline Dolphin. That build is needed for the camera export, and it never opens a window, so section 5's background options aren't needed with it. Option B5 becomes that plan.

Evidence tags:

- **[verified]**: measured, or read in source or on disk, during this investigation.
- **[reported]**: found during research; not re-checked by hand.
- **[estimate]**: needs a measurement.
- **[to test]**: needs an experiment before we rely on it.

---

## 1. Summary

- **No Dolphin build is needed for this route.** Slippi's official Windows playback Dolphin (3.5.2) already contains the FFV1 video encoder [verified]. The README's manual workflow is the Windows workflow. The camera export does need a build ([`plan-windows-mainline.md`](plan-windows-mainline.md)).
- **The big Mac problem doesn't apply.** On a normal x86 PC, Dolphin's fast CPU recompiler runs natively. On the Mac it only failed under Docker's x86 translator [estimate: this is Slippi's shipping setup, but it wasn't measured here].
- **What's left:** one-command automation, optional background rendering, the faster solver math, and the same stage limits as on macOS.
- **Effort:**

| Scope | If the macOS orchestrator exists | Standalone |
|---|---|---|
| Automated, window visible | ~1.25–2 days | ~2.25–3 days |
| Plus background rendering (WSL2 headless) | +0.5–1 day | +0.5–1 day |
| **Total with background** | **~1.75–3 days** | **~2.75–4 days** |

- **Expected time per 3-minute match:** roughly 2.5–8 minutes depending on the route; the timing model is in section 6 [estimate].
- **Order of work.** If a Windows PC is available, Windows is the quickest way to get real renders, because there's no build step. Most of the code carries over to the Mac.

---

## 2. What already works

- **Manual workflow** (README):
  1. Slippi Launcher's playback Dolphin, with this repo's Gecko codes enabled.
  2. `Movie → Dump Frames`, with `UseFFV1 = True` in `%AppData%\Slippi Launcher\playback\User\Config\GFX.ini`.
  3. Drag the AVI onto a `SolveTo*.bat`.
- **Solver:** `AlphaSolve.bat` runs with the bundled ffmpeg 6.0 (`packages\ffmpeg-6.0-full_build`).

## 3. What's missing

1. Rendering a `.slp` with one command: no clicking, and an automatic stop at the end of the game.
2. Leaving the user's Slippi settings untouched, by using a separate config folder.
3. Rendering in the background.
4. A faster solver.
5. Stages other than Dream Land and Battlefield. This is shared with macOS; see milestone M6 there.

---

## 4. Automating the official Windows playback build

### 4.1 Which Dolphin to use

- **The Launcher's copy:** `%AppData%\Slippi Launcher\playback\Slippi Dolphin.exe`. The Launcher updates it automatically.
- **A pinned copy (recommended):** `playback-3.5.2-Win.zip` from https://github.com/project-slippi/Ishiiruka-Playback/releases, unzipped into `packages\slippi-playback-3.5.2\`, which is already gitignored. Contents [verified]:
  - `Slippi Dolphin.exe` (23 MB). FFmpeg is linked statically: there's no "compiled without libav" message, the AVIDump and FFV1 code is present, and there are no separate `av*.dll` files.
  - `OpenAL32.dll`, `slippi_rust_extensions.dll`, `WebView2Loader.dll`, `Sys\`, `portable.txt`.
  - `FIX-VCRUNTIME140-ERROR.txt`: the Visual C++ 2015–2022 x64 runtime is required.
- Today the pinned copy is the same version as the Launcher's. Update it deliberately when Slippi releases a playback version that new replays need.

### 4.2 Video backend and recording settings

- Backends in this build, in default order: Direct3D 11 (`DX11`), Direct3D 12, Direct3D 9, OpenGL, Vulkan [verified in `VideoBackendBase.cpp`].
- Recording at internal resolution, independent of the window, is supported by DX11, DX12 and OpenGL, but not by D3D9 or Vulkan [verified backend flags]. Use DX11 (the default) or OpenGL, with `InternalResolutionFrameDumps = True`.
- Configuration: the same files as Appendix A of the macOS plan, plus `[Core] GFXBackend = DX11` (or `OGL`).
- With the spectator server off (`SlippiEnableSpectator = False`), the first launch also avoids a Windows Firewall prompt.

### 4.3 Launch, monitor, stop

```
"Slippi Dolphin.exe" -b -e "D:\Games\SSBM.iso" -i comm.json -u <userdir> ^
    --cout --hide-seekbar --output-directory <dumpdir>
```

- **Isolation.** `-u` should override the zip's portable mode, so the user's Slippi settings stay untouched [to test in the first run].
- **Progress.** Progress markers (`[CURRENT_FRAME] n` and others) arrive on stdout when the process is started with redirected pipes. slp2mp4 relies on this on Windows [reported]. Each marker line ends with `std::endl`, so it's flushed immediately [verified].
- **Stopping.**
  - When the last frame is reached, call `CloseMainWindow()`. It sends WM_CLOSE for a clean shutdown that finalizes the AVI [to test].
  - Fallback: `Kill()`, then remux with `ffmpeg -c copy`. The macOS run showed that recovers everything except the damaged final packet [verified].
- **ISO.** Use `--iso`, otherwise `settings.isoPath` from `%AppData%\Slippi Launcher\Settings` (the same JSON layout as on macOS [estimate]).

### 4.4 Orchestrator

- **Recommended: the same Python tool as on macOS** (`tools\slp2alpha`), plus a Windows launch adapter of about 150–250 lines:
  - finds `Slippi Dolphin.exe`;
  - starts ffmpeg child processes with `CREATE_NO_WINDOW`, so no console windows flash;
  - closes Dolphin gracefully;
  - adds the background options from section 5.
- Python isn't preinstalled on Windows. Either install it (`winget install Python.Python.3.12`) or ship the ~10 MB embeddable Python in the release zip.
- **Alternative:** PowerShell 5.1, which is preinstalled. It would be a second implementation of the same steps: about one more day, and two codebases to keep in sync.

### 4.5 Solver changes

- Keep `AlphaSolve.bat`, but replace its two `geq` stages with the lookup-table graph (macOS plan, Appendix C).
  - That was 4.4× faster on the Mac and matched the original within 0.007/255 [verified with ffmpeg 9].
  - `lut2` and `extractplanes` also exist in ffmpeg 6.0 [to test].
- **Optional:**
  - Replace `Brightest.bat`'s scene-score parsing with a mean-luma check.
  - Accept `--first-color` and `--pair-offset`, so the orchestrator can skip detection.
- Keep `fifo` in the GIF graph while the bundled ffmpeg is 6.0. Current ffmpeg no longer has it (9.0.2 lacks it [verified]).

---

## 5. Background rendering on Windows

### 5.1 Constraints from Dolphin's code

These are [verified]; it's the same source as on macOS:

- **Dolphin raises its own window.** It calls `main_frame->Raise()` at startup and `RaiseRenderWindow()` again after the game boots (`DolphinWX/Main.cpp`).
- **Off-screen positions are rejected.** Windows placed more than 1000 px outside the desktop are moved back on screen (`WxUtils::SetWindowSizeAndFitToScreen`).
- **The recording doesn't depend on the window.** With internal-resolution recording, output doesn't depend on the window's size or visibility. The OpenGL path was read in source; DX11 and DX12 advertise the same capability.

### 5.2 Options

| Option | How it works | Added effort | Risk | Window visible? |
|---|---|---|---|---|
| **B1** WSL2 or Docker, headless | Run the Linux playback build under Xvfb inside WSL2, or the Docker image from the macOS prototype | 0.5–1 day | Medium: speed of CPU rendering hasn't been measured on x86 | Never |
| **B2** Hidden Windows desktop | Create a second desktop (`CreateDesktop`) and start Dolphin on it (`STARTUPINFO.lpDesktop`) | 0.5–1 day | Medium: GPU rendering on a desktop you're not viewing is unverified | Never |
| **B3** Virtual monitor | Install a virtual display driver, then place Dolphin's window on that monitor with `MainWindowPosX` / `MainWindowPosY` | 0.25–0.5 day | Low–medium: third-party driver | Yes, but on the virtual monitor. It may still grab focus at launch |
| **B4** Start minimized | `start /min` | ~0 | High: Dolphin raises itself again | Pops up |
| **B5** Patched Windows build | Same idea as macOS patch P3: never raise, no taskbar button, invisible window. Build on GitHub Actions (`windows-2022`, `msbuild Source\Dolphin.sln /p:Configuration=ReleasePlayback /p:Platform=x64`, as upstream's CI does [verified]) | ~1–2 days | Low once built | Never |

### 5.3 Recommendation

1. **Try B1 first.** It reuses the macOS prototype almost unchanged and is completely invisible. On real x86 hardware the recompiler should work, and that was the only blocker on the Mac.
2. **If CPU rendering is too slow on that PC,** use the native build with B3 (simplest) or B2 (no driver install).
3. **B5 is the polished option** if this will be handed to other people.

### 5.4 B1 details (WSL2 or Docker)

- **WSL2:** `wsl --install -d Ubuntu-22.04` (24.04 also works). Docker Desktop with the same image is an alternative.
- **Packages:** the same list as Appendix G of the macOS plan (Xvfb, Mesa, GTK and X11 libraries).
- **Dolphin:** take the AppImage from `playback-3.5.2-Linux.zip` and run `Slippi_Playback-x86_64.AppImage --appimage-extract`. On the Mac this step needed `unsquashfs` because of the translator; on real x86 it should just work [estimate].
- **ISO location:** copy the ISO into the Linux filesystem (`~/`) rather than reading it from `/mnt/c`, for faster disk access.
- **Shared memory:** `/dev/shm` is large enough in WSL2. In Docker, pass `--shm-size=4g`; without it Slippi's first savestate crashed on the Mac [verified].
- **CPU setting:** keep the default JIT (`CPUCore` unset). `CPUCore = 0` was only for the Mac's translator.
- **Rendering:** Mesa's CPU rasterizer (llvmpipe) at 1×, 643×528. A GPU path through WSLg's Direct3D 12 Mesa driver is optional [to test].
- **First test:** the Battlefield test replay, measuring game frames per second to get S.

### 5.5 B2 and B3 details

- **B2:** a small helper, about 50 lines of PowerShell (`Add-Type` with C# P/Invoke):
  1. `CreateDesktop("slp2alpha")`
  2. `CreateProcess` with `lpDesktop = "WinSta0\slp2alpha"`
  3. Wait for the render, then `CloseDesktop`.

  Test both DX11 and OpenGL: some GPU drivers may refuse to render on a desktop that isn't being displayed [to test].
- **B3:** install a virtual display driver (an IddCx-based "virtual display" driver) and place the virtual monitor to the right of the main one. Then set `[Interface] MainWindowPosX` and `MainWindowPosY` to a point inside it, with `RenderToMain = True`. Focus may still jump to Dolphin at launch.

---

## 6. Performance expectations

- **Timing model** (same as macOS): Dolphin time ≈ game frames × 2 ÷ (60 × S), where S is the unthrottled emulation speed. The flicker technique renders every game frame twice.
- **Native x86 with a GPU:** S is perhaps 2–5 at 1× [estimate], so 1.2–3 minutes of Dolphin time per 3-minute match.
- **The README's warning about recording.** It says recording frames can "tank FPS", but it was recording at window resolution. FFV1 at 1× internal resolution is far cheaper: about 620 frames/s on a single Apple core [verified].
- **WSL2 with CPU rendering:** unknown until measured. If S < 1, prefer the native build with B2 or B3.
- **Solver:** about 1–2 minutes per 3-minute match, depending on the CPU.

---

## 7. Effort breakdown

| Task | Effort |
|---|---|
| Pin the playback build; run one replay from the command line with the isolated config | 0.25 day |
| Windows adapter for the shared orchestrator (or a full tool if standalone) | 0.5–1 day (1.5–2 standalone) |
| Lookup-table math in `AlphaSolve.bat`, plus tests | 0.25 day |
| Background: B1 (WSL2 or Docker) | 0.5–1 day |
| Background alternatives: B3 / B2 / B5 | 0.25–0.5 / 0.5–1 / 1–2 days |
| Packaging: release zip, docs, embeddable Python | 0.25–0.5 day |
| **Total with the macOS orchestrator, using B1** | **~1.75–3 days** |
| **Total standalone, using B1** | **~2.75–4 days** |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| The Launcher updates its playback build underneath us | Use a pinned copy |
| Visual C++ runtime missing | Check at startup and link to the redistributable |
| SmartScreen or PowerShell execution-policy prompts | Document `Unblock-File`, or use the Python tool |
| Firewall prompt on first launch | Spectator server off in the isolated config |
| stdout isn't delivered from the GUI app | Works for slp2mp4 [reported]. Fallback: read Dolphin's log via `Logger.ini` |
| Dolphin steals focus | Background options B1, B2 or B5 |
| WSL2 renders too slowly | Native build with B2 or B3 |
| Stage coverage | Shared with macOS (M6) |
| Antivirus scanning slows writes of the large recordings | Exclude the temporary recording folder |
| Windows on ARM PCs | Out of scope: x86 emulation there raises the same questions as on the Mac |

---

## 9. Test plan

- **Test replays:** `unranked_game1.slp` (Battlefield) and `unranked_game2.slp` (Dream Land) from the slippi-js test fixtures.
- **Checks:**
  - recording validation (macOS plan, Appendix D);
  - solved output compared with the macOS/Docker reference within tolerance;
  - repeated for each background option;
  - one long match (3 minutes or more) for stability and disk use.

---

## Appendix A: Windows configuration changes

Relative to Appendix A of the macOS plan:

```ini
; user\Config\Dolphin.ini additions
[Core]
GFXBackend = DX11        ; or OGL
; Only for option B3 (coordinates inside the virtual monitor):
[Interface]
MainWindowPosX = 3000
MainWindowPosY = 0
```

## Appendix B: Launch sketch (PowerShell)

```powershell
$psi = [System.Diagnostics.ProcessStartInfo]::new($dolphin)
$psi.Arguments = "-b -e `"$iso`" -i `"$comm`" -u `"$user`" --cout --hide-seekbar --output-directory `"$dump`""
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$p = [System.Diagnostics.Process]::Start($psi)
$errTask = $p.StandardError.ReadToEndAsync()     # drain stderr so Dolphin never blocks
$end = $null
while (($line = $p.StandardOutput.ReadLine()) -ne $null) {
  if ($line -match '^\[GAME_END_FRAME\] (-?\d+)') { $end = [int]$Matches[1] }
  if ($line -match '^\[CURRENT_FRAME\] (-?\d+)' -and $end -ne $null -and [int]$Matches[1] -ge $end) { break }
}
$null = $p.CloseMainWindow()
if (-not $p.WaitForExit(5000)) { $p.Kill() }
```

## Appendix C: WSL2 headless sketch (option B1)

```sh
sudo apt-get install -y xvfb xauth libgl1 libglx0 libopengl0 libegl1 libgl1-mesa-dri libglx-mesa0 \
  libsm6 libx11-6 libxcb1 libxext6 libxrandr2 libxi6 libasound2 libgtk-3-0 unzip
unzip playback-3.5.2-Linux.zip && ./Slippi_Playback-x86_64.AppImage --appimage-extract
xvfb-run -a -s "-screen 0 1280x1024x24" ./squashfs-root/AppRun \
  -b -e ~/ssbm.iso -i comm.json -u ./user --cout --hide-seekbar --output-directory ./dump
```

The AppImage bundles most of its own libraries. In the Mac's Docker run, the package list in Appendix G of the macOS plan was sufficient on Ubuntu 22.04 [verified]. The shorter list above relies on `libgtk-3-0` pulling in the rest [to test].

## References

- Playback releases: https://github.com/project-slippi/Ishiiruka-Playback/releases
- Ishiiruka source at `bffe989d`: https://github.com/project-slippi/Ishiiruka/tree/bffe989d
  - `Source/Core/VideoCommon/VideoBackendBase.cpp`
  - `Source/Core/VideoBackends/DX11/main.cpp`, `D3D12/main.cpp`, `OGL/main.cpp`
  - `Source/Core/DolphinWX/Main.cpp`, `WxUtils.cpp`
  - `.github/workflows/pr-build.yml` (the Windows job uses MSBuild on `windows-2022`)
- Prior art (Windows and Linux replay-to-video automation): https://github.com/davisdude/slp2mp4
