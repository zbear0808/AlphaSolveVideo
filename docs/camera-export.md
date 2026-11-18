# Camera export

`python3 -m slp2alpha render REPLAY --export-camera` also writes `camera - NAME.json`, next to the two videos. For every frame of the video, it holds the camera the game drew that frame with: where the eye is, the point it looks at, the field of view and the screen shake, in the replay's own units. `tools/camera-export/import_melee_camera.py` turns it into an animated Blender camera that sees the world the way the video does. Anything you put in Melee's coordinates and render through it lines up with the transparent video.

```sh
cd tools/slp2alpha
python3 -m slp2alpha render game.slp --characters-only --export-camera
cd ../..
blender -b --python tools/camera-export/import_melee_camera.py -- "camera - game (characters only, 60 fps).json" \
    --save game-camera.blend
```

It works with the other options (`--characters-only`, `--static-camera`, `--start-frame`, `--scale`, `--animelee`), except `--format gif`. It needs the headless Dolphin build with the camera patch: `render` says so when the build is too old, and `tools/dolphin-build/build-mac-mainline.sh` builds it. On Windows, `tools/dolphin-build/build-windows-mainline.py` (run by the "Windows playback Dolphin" GitHub Actions workflow) builds it, but it hasn't rendered there yet: [`plan-windows-remaining.md`](plan-windows-remaining.md).

## Only when asked

Nothing changes for renders without `--export-camera`:

- **Dolphin** reads the camera only when it's given `--camera-out`, which `render` passes only for camera exports. Without it the patch's one check per frame returns at once.
- **The video** is the same either way: with and without the export, the raw recordings and the solved frames were identical (`validate_camera.py readonly`).
- **Only camera exports are labelled 60 fps.** The videos of a camera export are labelled exactly 60 fps, frame N at N/60 s, so they match the camera file and Blender. Other renders keep the recording's NTSC rate, 60000/1001 (59.94, the console's real rate). The frames are the same, one per game frame; a 3-minute game just plays 0.18 s shorter at 60.
- **"60 fps" is in the file names** of a camera export, so a later render without the export can't overwrite its videos with 59.94 ones.

## The file

```jsonc
{
  "format": "alphasolve-camera", "version": 1,
  "replay": "game.slp", "stage": {"id": 31, "name": "Battlefield"},
  "render": {"width": 640, "height": 528, "scale": 1, "fps": "60/1",
             "transparent": "fullTransparent - game (characters only, 60 fps).mov", "alpha_map": "...",
             "iso": "vanilla", "codes": ["..."]},
  "projection": {"type": "perspective", "fov_axis": "vertical", "aspect": 1.2173333,
                 "viewport": [0.0, 640.0, 0.0, 480.0], "near": 0.1, "far": 16384.0},
  "space": {"units": "replay", "x": "right", "y": "up", "z": "towards the camera"},
  "frames": {"first": 1500, "last": 1799, "count": 300, "video": 300, "replay_last": 7529, "replay_frame_offset": -1},
  "shake": "included",
  "samples": [
    {"frame": 1500, "eye": [4.662885, 51.36137, 169.25928], "interest": [5.3171034, 24.503584, 0.0],
     "fov": 30.0, "roll": 0.0, "shake": [0.0, 0.0], "mode": 0, "view": [/* 12 numbers */]}
  ]
}
```

- **`samples[i]` is video frame `i`.** `frame` is the frame number that `--start-frame`, `--end-frame` and the file name use. The fighters in that picture are at the replay's frame `frame - 1` (`replay_frame_offset`): a picture shows the game one frame late (`docs/clips.md`).
- **The ends.** A render from the start of a match begins at frame -121, because the picture for -122 is never recorded. A render that runs to the end of a replay that ends on stocks or time has one more video frame than frame numbers: the game's last frame, drawn after the replay's last frame request. The game asks for no frame after that, so there's no moment to read its camera, and that video frame has no sample. `count` is then one less than `video`, `last` is `replay_last`, and the importer holds the previous camera on it. Clips, and replays that end in a quit-out, have a sample for every frame.
- **Space.** Positions are in the replay's units and axes, the space the fighters' x and y are in. The stage's collision is on z = 0.
- **Exact numbers.** They are the game's float32s, unchanged: each parses back to the same bits.
- **Shake.** `eye` and `interest` include the screen shake, as drawn. Subtract `shake` from the x and y of both for the camera without it. `--static-camera` turns shake off, so it's 0 there.
- **The view matrix.** `view` is the game's own view matrix, 3 x 4, row-major: `C_MTXLookAt` of `eye`, `interest` and the up vector the roll gives. With roll 0, that's world up made perpendicular to the view.
- **Mode.** `mode` is 0 for the normal camera and 4 for the fixed one.
- **Near and far.** These are the same on every frame, except where a sample has its own `near` and `far`. Final Destination uses 1 and 30000 instead of 0.1 and 16384. They only clip depth; the picture doesn't depend on them.
- **The picture.** The game draws 640 x 480 through a camera whose width is 1.2173333 times its height. The recording stretches that to `render.width` x `render.height`, which isn't 528 x scale tall at every scale:

| `--scale` | Recording | Pixel aspect (width : height) |
|---|---|---|
| 1 | 640 x 528 | 1.0043 |
| 2 | 1280 x 1056 | 1.0043 |
| 3 | 1920 x 1580 | 1.0018 |
| 4 | 2560 x 2108 | 1.0024 |

To project a point yourself, `tools/logo-stage/projection.py` has it: `projection.from_sample(sample).project((x, y, z), size=(width, height))`.

## Blender

`import_melee_camera.py` runs three ways:

- **On the command line**, as above. Options: `--scale` (Blender units per Melee unit, default 1), `--offset X Y Z` (where Melee's origin goes), `--frame-start` (default 1), `--no-shake`, `--linear`, `--no-scene`, `--background-video`, `--save`.
- **From the Text Editor**: Run Script. That adds File > Import > Melee Camera (.json) and opens the file browser.
- **As an add-on**: Edit > Preferences > Add-ons > Install from Disk, then File > Import > Melee Camera (.json).

It needs Blender 4.4 or later (it uses action slots) and was tested with 5.2.3. It creates:

| | |
|---|---|
| Camera object | location and rotation keyed on every frame, held between frames (or linear with `--linear`). A Melee point (X, Y, Z) is at `offset + scale * (X, -Z, Y)`: Blender's z is up and its front view looks along +y |
| Camera data | horizontal sensor fit, 36 mm sensor, focal length keyed on every frame (`18 / (tan(fov / 2) * 1.2173333)`), clip start and end from near and far |
| Custom properties | `slippi_frame`, `shake_x`, `shake_y`, `mode` on every frame; `replay`, `stage`, `source`, `units_per_melee_unit` |
| Scene | the camera, the video's resolution and pixel aspect (table above), exactly 60 fps, the video's frame range |
| Background (`--background-video`) | the transparent video behind the camera in the viewport, to check by eye |

The orientation is built the way the game builds its view matrix (`roll2upvec`, then `C_MTXLookAt`), so it matches `view`. Keep the scene at the video's rate: Blender's Video Sequencer retimes a movie at another rate, and the camera, keyed per frame, would drift against it.

## How it works

`tools/dolphin-build/patches-mainline/0004-camera-export.patch` adds `--camera-out FILE` to the headless Dolphin.

- **The game's camera.** Each logic frame, Melee's camera code eases `game_camera` (at `0x80452C68`) towards its targets, and the screen shake goes in as an x, y offset. Each draw, the main camera's render callback copies that, plus the shake, into the camera object it renders with, which builds the projection and the view matrix from it.
- **When it's read.** Slippi's playback code asks Dolphin for frame L between the draws of frames L-1 and L. At that moment the camera object holds exactly what the draw of frame L-1 used, which is the picture the frame dump labels L. Dolphin reads it then, for exactly the frames it records, and writes one CSV row per frame.
- **What's in a row.** The camera object's eye, look-at point, field of view, aspect, near, far, roll, viewport and view matrix, and `game_camera`'s mode, shake and pre-shake values.
- **slp2alpha's part.** It checks the rows, picks the one for each video frame, and writes the JSON (`slp2alpha/camera.py`).

The research behind it, with the decomp references: [`plan-camera-export-dolphin.md`](plan-camera-export-dolphin.md).

## Checks

`tools/camera-export/validate_camera.py`, run on the test replays from `tools/render-tests` (vanilla disc unless noted):

| Check | What | Result |
|---|---|---|
| `check` | Each view matrix against the game's look-at of its eye and look-at point; the drawn camera against the game camera plus the shake (raw rows); counts, frame numbers, projection, modes | Matrices within 4e-7 (rotation) and 9e-5 (translation). The drawn camera was the game camera plus the shake, bit for bit, on every frame of whole Yoshi's Story (9357) and Battlefield (7651) games, a Final Destination clip at `--scale 3` (4001) and a Battlefield clip (300) |
| `static` | `--static-camera` against the stage's fixed camera from the ISO | All six legal stages within 1e-5, and Battlefield on the Animelee disc |
| `track` | Which video frame each sample belongs to (below) | The export's alignment is right to within a fraction of a frame |
| `blender` | Blender's pixels against `projection.LookAtCamera` on probe points, also with `--scale 0.1 --offset 3 -2 1` | Within 0.0002 px at 640 x 528 (165 probes on 15 frames), 0.0008 px at 1920 x 1580 (`--scale 3`, 858 probes on 78 frames); resolution, pixel aspect, 60 fps, frame range and `slippi_frame` as the file says |
| `compare` | A clip that Dolphin skips ahead to (Yoshi's Story, 8500 to 8800) against the whole game | All 301 frames identical |
| `readonly` | The same Battlefield clip with and without `--export-camera` | Raw recordings (600 fields) and solved videos (300 frames) identical when decoded; 60/1 fps with the export, 60000/1001 without |
| render tests | `--export-camera` entries in `tools/render-tests` | A whole match with the stage drawn (7652 video frames, 7651 samples: the game's last frame has none), the 12 s quit-out (743, 743), a clip after skipping ahead (301, 301), and the fixed camera over a whole match |

`track` renders with `--characters-only --hide-effects --hide-items`, so the alpha map is just the fighters. It measures fighters standing on the main stage's flat top: the lowest row and the middle of the silhouette. Then it compares them with the camera samples shifted by -2 to +2 frames and the fighters' positions shifted by -2 to 0.

- **The spread.** At the export's own alignment (camera offset 0, fighters at `frame - 1`) the residuals spread least on Yoshi's Story and Battlefield, but the neighbours were only 1.1 to 1.25 times worse: a fighter's animation is most of the spread. On Final Destination the fighters' positions at `frame - 2` spread a little less than at `frame - 1`.
- **The slope.** So the decision is a fit: how far the measured fighters follow a one-frame shift. About 0 means the alignment is right, about ±1 that it's a frame off. A fit must be within half a frame of 0, and the camera offset with the smallest spread must be 0.
- **Camera shifts** are fitted on fighters standing still, because a running fighter leans with its motion and the camera follows that motion. Residuals are grouped by character, facing, and whether the fighter moves.

| Replay | Measured fighter frames | Camera one frame later / earlier | Fighters one frame later |
|---|---|---|---|
| Yoshi's Story, whole game (9357 frames) | 575 | -0.02 ± 0.09 / +0.03 ± 0.09 | +0.20 ± 0.08 |
| Battlefield, whole game (7651 frames) | 824 | +0.15 ± 0.13 / -0.19 ± 0.13 | -0.31 ± 0.07 |
| Final Destination, frames 2000 to 6000 at `--scale 3` | 840 | -0.16 ± 0.18 / +0.13 ± 0.17 | -0.22 ± 0.06 |

The camera rows are on the right frames: shifting them by a frame doesn't explain anything. The fighters fit within a third of a frame of `frame - 1`, on one side or the other depending on the replay. That's what `docs/clips.md` found on lasers and respawns, and the rest is how a fighter's silhouette sits around its position, which this measurement can't separate from timing.

## Found along the way

- **The fixed camera looks slightly higher than the stage files suggest.** The game turns the stage's tilt into a look-at point with its own polynomial sine and cosine (`lbvector_sin`), and `projection.game_interest` now does the same. `projection.Camera.interest`, which `tools/logo-stage` uses, works with the true sine. Its look-at point is 0.2 to 1 unit too low, which puts the stage top 0.5 to 2.7 px too high at `--scale 1` (2.65 px on Battlefield, 2.3 on Dream Land, 1.3 to 1.6 on Yoshi's Story, Fountain of Dreams and Stadium, 0.5 on Final Destination). That is part of the 1 to 7 px between fighters' feet and the model's stage top in `docs/logo-stage.md`. The logo stage still uses `Camera.interest`.
- **Recording sizes at `--scale` 3 and 4** are 1920 x 1580 and 2560 x 2108, not 528 x scale tall (Dolphin rounds the stretched height up to a multiple of 4). `projection.py` takes a real `size` now; the logo stage still assumes 528 x scale, so it's only right at scales 1 and 2.
- **Dust and smoke aren't repeatable.** Two renders of the same clip with nothing changed differ in a few fields: 6 of 600 on the Battlefield clip, by at most 6/255, in dust and smoke. `readonly` hides effects for that reason.

## What it doesn't do

- **Lag frames.** If the game runs two logic frames before one draw (the case the "Dolphin skipped N field(s)" warning reports), that frame's camera is one draw old. The raw rows' check flags it, and `render` prints a warning.
- **The game's last frame** of a replay that ends on stocks or time has no sample (see "The ends").
- **GIF output**: refused, because the GIF is resampled to 50 fps.
- **`--dual-core`**: untested. The frame dump then reads the frame number on another thread.
- **Fighters and stage geometry in Blender** aren't imported. `validate_camera.py overlay` draws them on the video instead.
