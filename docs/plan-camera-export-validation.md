# Camera export, part 3: validation

Status: plan, November 2026. One of three: [reading the camera and the export file](plan-camera-export-dolphin.md), [the Blender importer](plan-camera-export-blender.md), this file.

The export is only worth having if it's exact. The validation has to show five things:

1. **The numbers are the ones the game drew with**, read at the right moment.
2. **Each sample belongs to its own video frame**, not the one before or after.
3. **The numbers put things on the right pixels** of the video.
4. **Blender reproduces them.**
5. **The export changes nothing**, and gives the same numbers every time.

The tool is one script, `tools/camera-export/validate_camera.py`, with a subcommand per check. It uses `tools/logo-stage/projection.py`, `stagedata.py`, `replay_events.py` and `slp2alpha` the way the other tools do (`sys.path`). `check` needs only the standard library. The picture checks need numpy and Pillow (`pip install numpy pillow`), like `check_projection.py`.

Evidence tags as in part 1: **[verified]**, **[to test]**, **[estimate]**.

---

## 1. `projection.py`: a camera given by eye and look-at point

`projection.Camera` is defined by a stage's eye and angles. Add `LookAtCamera(eye, interest, fov_deg, roll=0.0, aspect=ASPECT, up=None)` with the same `project`, `unproject`, `size` and `pixels_per_unit`. Its axes are built as the game builds them (`roll2upvec`, then `C_MTXLookAt`; part 2, section 2). The shared code moves into a base class, so both cameras use the same projection.

Both cameras must take the picture's real size, the file's `render.width` and `render.height`, instead of computing 640 · scale × 528 · scale. At `--scale 3` and `4` the recording is 1920 × 1580 and 2560 × 2108, not 1920 × 1584 and 2560 × 2112 (part 2, section 2) [verified]. Today `projection.py` assumes the latter, so `logo_stage.py` and the checks are only right at scales 1 and 2.

New tests in `test_projection.py`:

- `LookAtCamera(cam.eye, cam.interest, cam.fov_deg)` projects every test point like `cam`, to 1e-9 px, for the Battlefield and Yoshi's Story cameras already in the file.
- Roll 0 gives the world-up basis. A non-zero roll matches an independent Rodrigues rotation of `v0` by −roll about the view direction.
- `unproject(project(p))` gives `p` back.
- After the first real export: the view matrix built from one sample equals that sample's `view`.

## 2. `check FILE.json`: the numbers

Offline, a few seconds. It reads the JSON, or with `--raw` the CSV from the work folder (`render --keep`), which also has the `t_*` columns. slp2alpha runs the same checks on every export (part 1, section 5).

| Check | Pass |
|---|---|
| `format` and `version`; `count` = number of samples; labels consecutive; `count` = `video`, or one less for a quit-out | exact |
| `ok = 1` on every row | exact |
| Projection on every row: type 1, aspect bits `3F9BD194`, viewport 0, 640, 0, 480, near 0.1, far 16384 | exact |
| Roll 0, flags bit 0 clear | exact; anything else is reported |
| CObj = game camera + shake (`--raw`): `eye = t_eye + (shake_x, shake_y, 0)`, `interest = t_interest + (shake_x, shake_y, 0)`, `fov = t_fov`, computed in float32 | bit-exact. On GrKind `Castle`, `Corneria`, `Zebes`, `Garden`, `KinokoRoute` and `Homerun` the eye's y may be larger (the floor clamp) |
| View matrix: `C_MTXLookAt(eye, up(roll), interest)` in float64 against `view` | rotation within 1e-5, translation within 1e-3 |
| Modes | 0 on every frame, or 4 on every frame with `--static-camera`. Anything else is listed with its frame ranges |
| Shake | 0 on every frame with `--static-camera`. Otherwise reported: how many frames shake, and the largest offset |

The CObj = game camera + shake check is also the runtime test of part 1, section 1, item 5. If Dolphin read after the camera's proc instead of before it, the check would fail on every frame where the camera moves. It also fails on frames after a game lag (two logic frames before one draw), and lists them.

## 3. `static REPLAY.slp`: the fixed camera against the stage files

Renders frames 600–900 with `--static-camera --export-camera`. It then compares every sample with the stage's fixed camera from the ISO (`stagedata.load_stage(...).camera` through `projection.from_ground_param`): eye, look-at point and field of view, each within 1e-3 [to test]. That camera already matches recordings (`docs/logo-stage.md`), so this ties the memory offsets and the export to something measured. Run once per legal stage, and once on Animelee.

## 4. `track REPLAY.slp`: which frame each sample belongs to

The main alignment test, with the camera moving.

1. **Render** with `--characters-only --hide-effects --hide-items --export-camera`, so the alpha map holds only the fighters. Or reuse a render: `--camera FILE --alpha-map FILE`.
2. **Pick fighters** standing on the main stage's flat top, with the `check_projection.py` rules: grounded, y on the top, not shielding, no other fighter within 45 units, well inside the picture. Unlike `check_projection.py`, they may move.
3. **Measure** each one's silhouette in the alpha map around the predicted point: the lowest row and the middle (`check_projection.measure`). The search window is in replay units, converted with `pixels_per_unit` at that point, because the camera zooms.
4. **Predict** with sample `i + dc` and the fighter's replay position at frame `samples[i].frame + df`, for `dc` from −2 to +2 and `df` from −2 to 0. Two residuals, in replay units:
   - feet: `(v_measured − v_predicted) / pixels per unit`;
   - across: the middle's offset, minus the median for that character and facing (fighters aren't centred on their origin; `check_projection.py` does the same).
5. **Compare** the spread of the residuals (median absolute deviation) for every (dc, df), on two sets of samples:
   - samples where the camera moved at least 1 px since the previous frame, measured by projecting the same point with both cameras. This decides `dc`;
   - samples where the fighter moved at least 0.5 units since the previous frame. This decides `df`.

**Pass:** `dc = 0, df = −1` (part 1, section 1, item 7) has the smallest spread, its neighbours' spread is at least 1.5 times larger, and each set has at least 200 samples. With fewer samples the result is "inconclusive", not a pass. The thresholds will be tuned on the first runs [to test]. The tool prints the table and saves it as JSON, as `docs/clips.md` did for clips.

Also reported, with no threshold yet:

- The median feet residual per stage. It should be below the stage top, as with the fixed camera: 1 to 7 px at `--scale 1` in `docs/logo-stage.md`.
- The spread at the best (dc, df), next to what `check_projection.py` measures with the fixed camera. A much larger spread would mean the moving camera adds error.

## 5. `stage REPLAY.slp` (optional): the stage stays put

A second alignment signal that doesn't depend on fighters, for renders with the stage drawn (Battlefield, Dream Land).

- The stage is opaque in the alpha map. A few units below the stage top, only the main platform is drawn. On that row, find where the opaque region starts and ends, and compare with the projected ledges.
- The gap between the model's edge and the collision ledge is fixed in replay units, so at the right alignment it doesn't move when the camera does.
- Same `dc` comparison as `track`. Frames with a fighter within 10 units of a ledge are skipped.

## 6. `blender FILE.json`: the import

1. Run Blender headless with `import_melee_camera.py` and a probe script, `tools/camera-export/blender_probe.py`.
2. Sample frames: every 60th, the first and the last, and the 10 where the camera moved most.
3. Probe points on each: the look-at point, the look-at point ±20 units along x, y and z, and, with the ISO, both ledges and both ends of the flat top.
4. Compare Blender's pixel (`world_to_camera_view`, as in `blender_plate.world_to_pixel`) with `LookAtCamera.project` for the same sample.

**Pass:** within 0.01 px everywhere, and the look-at point at the exact centre, within 1e-4 px. Then again with `--scale 0.1 --offset 3 −2 1`, with the probe points mapped the same way. Also checked: resolution, pixel aspect, fps (exactly 60, base 1), frame range, and `slippi_frame` against the samples.

## 7. `overlay REPLAY.slp FILE.json`: by eye

Draws over frames of the transparent video, composited on grey, using that frame's camera:

- the stage's floors in magenta;
- the ledges in cyan;
- each fighter's position at `frame − 1` in yellow.

Output is a contact sheet (`--every 30`) or a video (`--video out.mp4`). With the stage drawn, the lines should stay on the stage through every pan and zoom, and grounded fighters' feet should stay on the lines.

## 8. Read-only and repeatable

| Test | Pass |
|---|---|
| A 300-frame clip with and without `--export-camera` (`--keep`): `ffmpeg -f framemd5` of both raw recordings, and the hash column of both solved videos | identical frames. `ffprobe`: `60/1` with the export, `60000/1001` without |
| The same clip twice | identical samples |
| A clip that Dolphin skips ahead to (Yoshi's Story, 8500–8800) against the whole replay | identical samples on the same frames |
| A whole replay, a mid-match clip, a clip to the last frame | as many samples as video frames (one fewer for a quit-out) |

## 9. Matrix

From `tools/render-tests/replays.json`:

| Replay | Render | Tests |
|---|---|---|
| BF, Fox vs Falco (`DishonestMuddyCoyote`, 127 s) | default: stage drawn, shake on | check, stage, overlay, blender |
| BF, Fox vs Falco | `--characters-only` | check, track |
| DL, 12 s quit-out (`SpectacularScalyFlamingo`) | default, whole replay | check, samples vs frames (the quit-out's last frame). Too short for `track` |
| YS, Falco vs Jigglypuff (`RichAuthenticGull`, 156 s) | `--characters-only`, whole and 8500–8800 | check, track (whole: from the match start; clip: after skipping ahead), clip vs whole |
| FD, Sheik vs Samus (`RundownSparklingBuffalo`, 144 s) | `--characters-only --scale 3` (1920 × 1580: not 528 × scale tall) | check, track, blender (size and pixel aspect) |
| PS, Fox vs Falco (`EqualPresentCockroach`) | `--characters-only --static-camera` | check, static |
| every legal stage | `--static-camera`, 600–900 | static |
| one replay | `--animelee --characters-only` | check, static |

## 10. Render tests

- `replays.json`: add `--export-camera` to some of the renders above: BF default, the YS clip 8500–8800, PS with the static camera, the DL quit-out.
- `run.py`: leave `.json` paths out of the video list. For renders with `--export-camera`, check that the file exists and has a sample per output frame, that both videos report `60/1`, and run `check` (imported as a module). Problems go into the summary like the other checks.

## 11. Effort

- `projection.py` and its tests, `check`, `static`: half a day.
- `track` and `stage`: a day. Measuring silhouettes under a zooming camera is most of the work.
- `blender`, `overlay`, the read-only tests and the render-test entries: half a day.

[estimate]
