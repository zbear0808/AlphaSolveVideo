# Camera export, part 1: Dolphin patch and export file

Status: plan, November 2026. One of three: this file (reading the camera, writing the export), [the Blender importer](plan-camera-export-blender.md), [the validation](plan-camera-export-validation.md).

**Goal.** `python3 -m slp2alpha render REPLAY --export-camera` writes `camera - NAME.json` next to `fullTransparent - NAME.mov`. For every frame of the video it holds the camera the game drew that frame with: eye, look-at point, vertical field of view, roll and screen shake, in the replay's own units. The camera is only read. The game, the replay's sync and the video stay exactly as they are.

**Not in scope.** Changing the camera. The Ishiiruka build. GIF output (the solver resamples GIFs to 50 fps, so their frames are no longer game frames).

Evidence tags, as in the other plans:

- **[verified]**: measured, or read in source during this investigation. Sources: the Melee decomp (doldecomp/melee: `src/melee/cm/camera.c`, `cm/camera.h`, `cm/types.h`, `gm/gmscene.c`, `src/sysdolphin/baselib/cobj.c`, `cobj.h`, `wobj.h`, `gobj.h`), Slippi's playback code (project-slippi/slippi-ssbm-asm: `Playback/Core/FetchGameFrame.asm`, `Playback/Core/FastForward/FastForward.asm`, `Common/FastForward/FunctionMacros.s`), and the pinned Dolphin source in `~/Library/Caches/AlphaSolveVideo/mainline`.
- **[to test]**: needs an experiment. The [validation plan](plan-camera-export-validation.md) says which one.
- **[estimate]**: needs a measurement.

---

## 1. Where the camera comes from

1. **Every logic frame**, the camera's proc (`fn_8002F360`) runs the update for the current mode: `Camera_8002B3D4` for the normal following camera, `Camera_8002DDC4` for the fixed camera that `--static-camera` turns on. The update eases `game_camera.transform` (look-at point, eye, field of view) towards its targets. Screen shake is stored separately, as an x, y offset in `game_camera.translation` (`Camera_ApplyQuake` → `Camera_80030DE4`). [verified]
2. **Every draw**, the main camera's render callback `fn_800301D0` first calls `Camera_8002A4AC`. That copies the transform into the main camera object (CObj) through `Camera_8002AF68`:
   - the field of view, as it is;
   - the look-at point plus (shake x, shake y, 0);
   - the eye plus (shake x, shake y, 0). On six stages, none of them legal, the eye's y is also kept above a floor: GrKind `Castle`, `Corneria`, `Zebes`, `Garden`, `KinokoRoute`, `Homerun`;
   - near and far.

   `HSD_CObjSetCurrent` then builds the projection, `MTXPerspective(fov, aspect, near, far)`, and the view matrix, `C_MTXLookAt(eye, up, look-at)`. The `up` vector comes from the CObj's roll (`roll2upvec`). The view matrix is kept in the CObj. [verified]
3. **Fixed settings.** The CObj is made from `cm_803BCB64`: perspective, viewport and scissor 0–640 × 0–480, roll 0, no up vector, near 0.1, far 16384, field of view 30, aspect 1.2173333 (float bits `3F9BD194`). These are the numbers `tools/logo-stage/projection.py` already uses. [verified]
4. **Shake.** "Disable Screen Shake" (`04030E44 4E800020`) makes `Camera_RequestQuake` return at once, so the shake stays 0. Only `--static-camera` turns that code on (`config.STATIC_CAMERA_CODES`). A default render shakes, so the export has to include the shake to match the video. [verified]
5. **When to read it.** Logic and drawing take turns: the game loop (`gm_801A4D34`) runs the pending logic frames, then draws. Slippi's playback code asks Dolphin for frame L from `SceneThink_VSMode` during logic frame L (`FetchGameFrame.asm`, injected at 0x8016D298). In Dolphin that's `CEXISlippi::prepareFrameData`, on the CPU thread. That request falls between the draw of frame L−1 and the draw of frame L. Only the draw writes the CObj (and fast-forward, item 6), so at that moment it holds exactly what the draw of frame L−1 used. With the flicker code, frame L−1 is drawn twice, once over black and once over white, with no logic in between, so both draws use the same camera. The scene's think runs before `HSD_GObj_RunProcs`, so `game_camera.transform` should still be frame L−1's too. [verified in source; to test: the validation's `CObj = transform + shake` check]
6. **Clips.** While Dolphin skips ahead to a clip's start, nothing is drawn. Slippi's `FastForward.asm` calls `Camera_8002A4AC` itself after every skipped frame (`FN_ExecCameraTasks`), so the CObj stays current. [verified]
7. **Which picture.** The frame dump labels each picture with `current_playback_frame` (patch 0002), and picture L shows the replay's frame L−1 (`docs/clips.md`, measured on lasers and respawns). So the camera read at `prepareFrameData(L)` is the camera of picture L: the same label, with the same one-frame lag. [to test: the validation's `track`]

## 2. Memory map (NTSC 1.02)

| What | Where | Type |
|---|---|---|
| `game_camera` | `0x80452C68`. Its clear colour at +0x08, `0x80452C70`, is what the flicker code toggles. | `Camera`, 0x39C bytes |
| `.gobj` | +0x000 | `HSD_GObj*` |
| `.mode` | +0x004 | `CameraType`, s32: 0 normal, 1 pause, 2 training menu, 3 clear, 4 fixed, 5 free, 6 boss intro, 7 and 8 debug |
| `.transform.interest` | +0x014 | Vec3, look-at point before shake |
| `.transform.position` | +0x02C | Vec3, eye before shake |
| `.transform.fov` | +0x044 | f32, degrees |
| `.translation` | +0x084 | Vec2, the shake |
| `HSD_GObj.hsd_obj` | gobj + 0x28 | `HSD_CObj*`, the main CObj |
| `CObj.flags` | +0x08 | u32. Bit 0 set: `u` is an up vector, not a roll |
| `CObj.viewport` | +0x0C | 4 × f32: x min, x max, y min, y max |
| `CObj.eyepos`, `CObj.interest` | +0x24, +0x28 | `HSD_WObj*`. The position is at WObj + 0x0C, a Vec3 |
| `CObj.u` | +0x2C | f32 roll in radians, or Vec3 up |
| `CObj.near`, `CObj.far` | +0x38, +0x3C | f32 |
| `CObj.fov`, `CObj.aspect` | +0x40, +0x44 | f32 degrees, f32 |
| `CObj.projection_type` | +0x50 | u8, 1 = perspective |
| `CObj.view_mtx` | +0x54 | 3 × 4 f32, row-major |

[verified in the decomp's headers. At runtime, the validation's `check` and `static` confirm them.]

## 3. Design choices

**Read in `prepareFrameData`, when the frame number advances.** That's the block that prints `[CURRENT_FRAME]`. Read only for labels strictly between the comm file's `startFrame` and `endFrame`, the same window the frame dump records (`IsPlaybackFrameDumpable`). That gives exactly one row per recorded label, in order, read at a fixed point of the game loop on the CPU thread. It needs no JIT hooks and no new threads.

Rejected:

| Option | Why not |
|---|---|
| HLE hook on `fn_800301D0` or `HSD_CObjSetCurrent` | Exact per draw, but it needs a JIT-level hook, and the flicker code draws each frame twice with the same values. Reading in `prepareFrameData` gets the same numbers. |
| Dolphin's built-in MemoryWatcher (`User/MemoryWatcher/Locations.txt`, Unix socket; compiled into this build) | No code change, but it samples at the end of each VI field, which isn't tied to the game loop. It sends only values that changed, over a datagram socket, with no frame number. |
| Read when the picture is dumped | By then the CPU may already have drawn the next frame. |
| Rebuild the camera from the `.slp` | The camera's easing, framing logic and shake aren't in the replay. |

**Read the CObj, and the game camera too.** The CObj is what the draw used, with the shake added and the eye clamped. `game_camera.transform` and the shake are written as well. They let the export drop the shake, and let the validation check `CObj = transform + shake`. That check also catches game lag. If the game runs two logic frames before one draw, the CObj at the second request is one draw old, and the check fails on that frame. That's the situation the existing "Dolphin skipped N field(s)" warning is about.

**Write floats exactly.** Each float32 is printed in its shortest exact form (`fmt::format("{}", value)`), so parsing it back gives the same bits.

## 4. The Dolphin patch: `tools/dolphin-build/patches-mainline/0004-camera-export.patch`

### 4.1 Files

| File | Change |
|---|---|
| `Source/Core/UICommon/CommandLineParse.cpp` | under `IS_PLAYBACK`, next to `--cout`: `--camera-out <file>` (`.action("store").type("string")`) |
| `Source/Core/DolphinNoGUI/MainNoGUI.cpp` | next to `cout_enabled`: if `options.is_set("camera_out")`, call `SlippiCameraExport::SetPath(options.get("camera_out"))` |
| `Source/Core/Core/Slippi/SlippiCameraExport.h`, `.cpp` (new) | `SetPath(path)`, `WriteFrame(system, frame)` and `Close()`; the path is a static in the `.cpp` |
| `Source/Core/Core/CMakeLists.txt` | the two new files, next to `Slippi/SlippiPlayback.cpp` |
| `Source/Core/Core/HW/EXI/EXI_DeviceSlippi.cpp` | call `WriteFrame` in `prepareFrameData`, before `[CURRENT_FRAME]` is printed; `Close()` in `endPlaybackOutput` and in `~CEXISlippi` |

The new code goes in new files, so the changes to Slippi's own files stay at a few lines. The path doesn't go into `Slippi::Config` (`SlippiConfig.h`), where patch 0002 put `cout_enabled`. That header comes in through `ConfigManager.h` and `Config/MainSettings.h`, which 134 and 144 source files include directly, so changing it rebuilds most of Core. This way only the files above recompile [verified: include counts in the pinned tree]. The patch is made against the pinned commit with 0001–0003 applied, since the build applies them in order and 0002 already changes `prepareFrameData`.

### 4.2 `WriteFrame`

In `prepareFrameData`, inside `if (frame_idx > g_playback_status->current_playback_frame)`:

```cpp
if (watch_settings.start_frame < frame_idx && frame_idx < watch_settings.end_frame)
  SlippiCameraExport::WriteFrame(system, frame_idx);  // before the [CURRENT_FRAME] line
```

`system` is the device's `Core::System`, the one `DMAWrite` uses.

```cpp
void WriteFrame(Core::System& system, s32 frame)
{
  if (!EnsureOpen())  // opens the SetPath() file on first use (truncates); no-op if none
    return;
  const Core::CPUThreadGuard guard(system);  // already on the CPU thread (EXI DMA)
  Row r;
  const bool ok = Read(guard, &r);  // PowerPC::MMU::HostRead_U32 / HostRead_F32 / HostRead_U8
  fmt::print(s_file.GetHandle(), "{},{},{},...\n", frame, ok ? 1 : 0, r.mode, r.eye[0], ...);
  std::fflush(s_file.GetHandle());
}
```

- `Read` follows `game_camera.gobj → hsd_obj → eyepos / interest`. It checks every pointer with `PowerPC::MMU::HostIsRAMAddress` before using it.
- If a pointer isn't valid, the row is still written, with `ok = 0` and empty camera fields, and a warning is logged once. That keeps one row per label.
- Rows are flushed one at a time. The runner stops Dolphin with SIGTERM about a second after the last `[CURRENT_FRAME]` marker, and each frame's row is written just before its marker.

### 4.3 Checks inside the patch

- Write only when `SConfig::GetInstance().GetGameID()` is `GALE01` and `GetRevision()` is 2: the addresses are for 1.02. Otherwise log an error once and write nothing.
- `ok` also needs `projection_type == 1`. Python checks the rest (aspect bits, viewport), so a wrong offset shows up as a failed check, not as plausible-looking numbers.

### 4.4 Output: CSV

Line 1 is `# alphasolve-camera 1`, line 2 the column names, then one row per label:

| Columns | From |
|---|---|
| `frame` | the label, `current_playback_frame` |
| `ok` | 1 if every pointer was valid |
| `mode` | `game_camera.mode` |
| `eye_x, eye_y, eye_z` | the CObj's eye position |
| `interest_x, interest_y, interest_z` | the CObj's look-at position |
| `fov, aspect, near, far` | CObj |
| `flags, u0, u1, u2` | CObj flags; `u` as stored (the roll is `u0` unless flags bit 0 is set) |
| `proj, vp_x0, vp_x1, vp_y0, vp_y1` | CObj projection type and viewport |
| `shake_x, shake_y` | `game_camera.translation` |
| `t_eye_x, t_eye_y, t_eye_z, t_interest_x, t_interest_y, t_interest_z, t_fov` | `game_camera.transform`, before shake |
| `m00` … `m23` | the CObj's `view_mtx`, 12 values, row-major |

That's 45 columns, about 450 bytes per row, 5 MB for a 3-minute game.

### 4.5 Build

`tools/dolphin-build/build-mac-mainline.sh` applies every patch in `patches-mainline/` in name order (in its `fetch`, `configure` and `all` steps), so it picks up `0004` [verified]. A full build takes about 7 minutes on an M1 (`docs/plan-macos-apple-silicon.md`). The local tree is already configured and built (Ninja, `~/Library/Caches/AlphaSolveVideo/mainline/build`). After `build-mac-mainline.sh fetch` applies the new patch, `build` and `bundle` recompile only the files in 4.1 and relink: a minute or two [estimate]. CMake re-runs itself because the patch edits `CMakeLists.txt`. `dolphin-emu-nogui --help` lists the build's options (today's prints `--cout`) [verified]. That lets slp2alpha tell an old build from a patched one before starting it.

## 5. slp2alpha

- **60 fps for camera exports.** With `--export-camera`, both videos are labelled exactly 60 fps, frame N at N/60 s, so they match the camera file and Blender's own renders. Without it, nothing changes: the videos keep the recording's rate, Dolphin's NTSC 60000/1001 (59.94, the console's real rate). Either way the frames are the same, one per game frame; only the timestamps differ, so a 3-minute game plays 0.18 s shorter at 60. Changes:
  - `solve.solve` and `solve.filter_graph` get an `output_rate`, by default the recording's rate as now. `_render_one` passes `"60/1"` with `--export-camera`, to both calls (the streaming solve and the one after Dolphin finishes).
  - When `output_rate` isn't the recording's rate, the outputs also get `-r <output_rate>`. Without it, ffmpeg keeps the input's 59.94 as the stream rate and rounds the new timestamps into it: a test wrote a 59.94 file with a 1/19001 time base. With it, the test kept 600 of 600 frames, identical when decoded, with the stream at `60/1` [verified with the ffmpeg slp2alpha uses, on a synthetic 59.94 input].
  - The recording keeps Dolphin's real rate, which `validate.timestamp_gaps` needs to find skipped fields.
- **`render --export-camera`.** Needs the headless mainline build with the patch, and a format other than `gif`. Otherwise it stops with an error before Dolphin starts, as `--shy-guy-sprite` does.
- **`runner.dolphin_options(dolphin)`**: the option names from `--help`, cached. Without `--camera-out` the error says to rebuild with `tools/dolphin-build/build-mac-mainline.sh`.
- **`_render_one`** passes `--camera-out <work>/camera.csv` through `run_dolphin(extra_args=…)`, and builds the export after solving.
- **`slp2alpha/camera.py`** (new, standard library only):
  - `read_csv(path)`: the rows.
  - `align(rows, first, video_frames)`: picks the row for each video frame.
    - The video has `min(expected_pairs, solve.pair_count(report.probe.frames, report.pairing.offset))` frames, the number the solver writes.
    - Video frame `i` shows label `first + i`. The exception is a render from the match's start: the picture for −122 is never recorded (`docs/clips.md`), so there video frame `i` shows label `−121 + i`.
    - A video frame with no row gets no sample. A replay that ends in a quit-out (LRAS) can have one, its last frame: the pause screen, drawn after the replay's last frame with the pause camera. `frames.count` is then one less than `frames.video`. Any other gap is a warning.
  - `check_rows(rows)`: while converting, check `CObj = transform + shake` and the projection constants (validation plan, `check`). A failure is a warning, with the frames it happens on.
  - `write_export(path, rows, meta)` and `load(path)`.
- **Output.** `camera - NAME.json` in the output folder, with NAME as for the videos, so clips and options are in the name. It's printed after the two video paths. `tools/render-tests/run.py` collects printed paths as videos, so it has to leave `.json` out (validation plan, section 10). `--keep` keeps the raw CSV in the work folder.
- **Warnings**, printed like the other checks: rows with `ok = 0`, modes other than 0 or 4, frames without a sample, failed consistency checks.

## 6. The export file: `camera - NAME.json`, version 1

```jsonc
{
  "format": "alphasolve-camera",
  "version": 1,
  "replay": "game.slp",
  "stage": {"id": 31, "name": "Battlefield"},
  "render": {"width": 640, "height": 528, "scale": 1, "fps": "60/1",
             "transparent": "fullTransparent - game.mov", "alpha_map": "alphaMap - game.mov",
             "iso": "vanilla", "codes": ["Increase Input Timing Accuracy", "..."]},
  "projection": {"type": "perspective", "fov_axis": "vertical", "aspect": 1.2173333,
                 "viewport": [0, 640, 0, 480], "near": 0.1, "far": 16384},
  "space": {"units": "replay", "x": "right", "y": "up", "z": "towards the camera"},
  "frames": {"first": 3120, "last": 3480, "count": 361, "video": 361, "replay_frame_offset": -1},
  "shake": "included",
  "samples": [
    {"frame": 3120, "eye": [/* x, y, z */], "interest": [/* x, y, z */], "fov": 30.0, "roll": 0.0,
     "shake": [/* x, y */], "mode": 0, "view": [/* 12 numbers, row-major 3 × 4 */]}
    // ... one per video frame
  ]
}
```

- `samples[i]` is video frame `i`. `frame` is the label that `--start-frame`, `--end-frame` and the file name use. The fighters in that picture are at the replay's frame `frame + replay_frame_offset`, i.e. `frame − 1`.
- Positions are in the replay's units and axes, the space the fighters' x and y are in. The stage's collision is on z = 0.
- The numbers are the game's float32s, unchanged: each one parses back to the same bits.
- `eye` and `interest` include the shake, as drawn. Subtracting `shake` from the x and y of both gives the camera without it.
- `up` appears in a sample only if CObj flags bit 0 is ever set (not expected).
- The projection values are the same on every frame. If Dolphin ever reports different ones, `check` fails.

## 7. Done when

- The validation plan's `check`, `static`, `track`, `blender` and read-only tests pass on its matrix.
- `tools/render-tests` has the `--export-camera` renders and they pass.
- A feature guide, `docs/camera-export.md`, exists, and the docs index, the README and `docs/logo-stage.md` ("Camera moves") point to it.

## 8. Risks

| Risk | What shows it, and what to do |
|---|---|
| A decomp offset is wrong | `check` fails (aspect bits, viewport, `CObj = transform + shake`), and so does `static` against the stage files. |
| The read happens later than designed | `CObj = transform + shake` fails on frames where the camera moves; `track` finds the wrong frame offset. |
| Animelee's DOL differs from vanilla | The game ID check passes but offsets could move. Run `check` and `static` on one Animelee render. |
| `--dual-core` | The frame dump then reads the label from the GPU thread. Untested for alignment; validate with the default (single core). |
| Dolphin skips a field | The video's black/white pairs are already off after it (existing warning). The camera export follows the video's frames and can't fix that. |
| Which picture is missing at the match start | `docs/clips.md` says the first; `track` on a whole render (Yoshi's Story, 156 s) confirms it. |

## 9. Effort

- Patch and build: half a day, about 150 lines of C++ [estimate].
- slp2alpha (60 fps for camera exports, `--export-camera`, `camera.py`, warnings): half a day [estimate].
