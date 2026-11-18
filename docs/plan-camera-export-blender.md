# Camera export, part 2: Blender importer

Status: implemented, November 2026, as `tools/camera-export/import_melee_camera.py`; [`camera-export.md`](camera-export.md) describes it. This plan is kept for its reasoning. One of three: [reading the camera and the export file](plan-camera-export-dolphin.md), this file, [the validation](plan-camera-export-validation.md).

What changed while building it: the importer also keys `clip_start` and `clip_end` when a stage changes near and far during the export. The fighters, stage lines and logo stage in section 5 aren't built.

**Goal.** Turn `camera - NAME.json` into an animated Blender camera that sees Melee's world the way the video does. That means the same picture size and pixel shape, the same frame rate, and on every frame the same position, orientation and field of view. Anything placed in Melee's coordinates and rendered through it lines up with `fullTransparent - NAME.mov`.

Evidence tags as in part 1: **[verified]** measured or read in source, **[to test]**, **[estimate]**.

---

## 1. What it creates

| | |
|---|---|
| Camera object `Melee Camera` | location and rotation (quaternion) keyed on every frame, constant interpolation |
| Camera data | horizontal sensor fit, 36 mm sensor, focal length keyed on every frame, clip start and end from the file's near and far |
| Custom properties | animated: `slippi_frame` (the label), `shake_x`, `shake_y`, `mode`. Fixed: `replay`, `stage`, `source`, `units_per_melee_unit` |
| Scene | the scene camera, plus resolution, pixel aspect, frame rate and frame range from the file |
| Optional | the transparent video as the camera's background (viewport only), to check by eye |

## 2. The conversion

**Space.** Melee: x right, y up, z towards the camera. Blender: z up, and the front view looks along +y. A Melee point (X, Y, Z) goes to

    B = offset + s · (X, −Z, Y)

That's a rotation (determinant +1) and a uniform scale, the mapping `tools/logo-stage/blender_plate.py` uses. `s` is Blender units per Melee unit (`--scale`, default 1) and `offset` is where Melee's origin goes (default 0). A uniform scale doesn't change the picture, as long as near and far are scaled with it.

**Orientation.** Built the way the game builds its view matrix (`HSD_CObjSetupViewingMtx` → `C_MTXLookAt`), from the sample's eye, look-at point and roll:

1. `E = normalize(interest − eye)`.
2. The up hint. If the sample has `up` (CObj flags bit 0), use it. Otherwise `roll2upvec(E, roll)`, ported from `cobj.c`:
   - if `1 − |E.y| ≥ 0.0001`: `h = sqrt(E.x² + E.z²)`, `v0 = (−E.x·E.y/h, h, −E.z·E.y/h)`;
   - otherwise (looking straight up or down): `v0.x = sqrt(E.y² + E.z²)`, `v0.y = −E.y·E.x/v0.x`, `v0.z = −E.z·E.x/v0.x`;
   - rotate `v0` about `E` by `−roll` (`PSMTXRotAxisRad(m, E, −roll)`), then normalize.

   With roll 0 this is world up made perpendicular to the view direction, which is what `projection.py` assumes.
3. `look = normalize(eye − interest)`, `right = normalize(up_hint × look)`, `up = look × right`.
4. The camera's rotation in Melee space has the columns `right, up, look`. Blender cameras look along their own −z with +y up, like GameCube view space, so no extra turn is needed. The Blender rotation is `A · [right up look]`, with `A = [[1, 0, 0], [0, 0, −1], [0, 1, 0]]` (the same axis change as for points). Store it as a quaternion. Flip its sign wherever its dot product with the previous frame's is negative, so a later switch to linear interpolation doesn't spin the camera.

**Lens.** Horizontal sensor fit, 36 mm sensor, `lens = (36 / 2) / (tan(fov / 2) · aspect)`. The picture's width then spans `tan(fov / 2) · aspect` either side of the centre and its height `tan(fov / 2)`, as in the game. This is how `blender_plate.py` sets up the stage's fixed camera, and there it matches `projection.py` to 0.0002 px (`docs/logo-stage.md`). [verified]

**Picture.** Resolution is the file's `render.width × render.height`, which is the recording's own size. That is not 528 × scale tall at every scale [verified, measured on this build]:

| `--scale` | Recording | Its shape | `pixel_aspect_x` |
|---|---|---|---|
| 1 | 640 × 528 | 1.2121 | 1.0043 |
| 2 | 1280 × 1056 | 1.2121 | 1.0043 |
| 3 | 1920 × 1580 | 1.2152 | 1.0018 |
| 4 | 2560 × 2108 | 1.2144 | 1.0024 |

Dolphin stretches the game's 640 × 480 picture to the shape it thinks an NTSC TV shows it at, 1.2154 for Melee (`VideoInterfaceManager::GetAspectRatio`). It takes the nearest whole height, then rounds that up to a multiple of 4 for the video encoder (`VIDEO_ENCODER_LCM`). The game's camera is shaped 1.2173333, so in the recording each pixel covers slightly more of the world across than up. Hence `pixel_aspect_x = aspect · height / width` and `pixel_aspect_y = 1`. Blender needs both to be at least 1; if the ratio were ever below 1, its inverse would go in y instead. Resolution percentage 100. Treating the pixels as square instead would put things up to 1.4 px off at the picture's left and right edges at `--scale 1` (2.75 px at 2, 1.7 at 3, 3.1 at 4). [verified: Blender's minimum pixel aspect is 1.0]

**Time.** Sample `i` goes on Blender frame `frame_start + i` (`--frame-start`, default 1). Renders with `--export-camera` label their videos exactly 60 fps (part 1, section 5), so the file's `fps` is `60/1` and the scene gets `fps = 60`, `fps_base = 1`. The console really runs at NTSC's 59.94; the frames are the same, only the label differs. The importer still turns any fraction in `fps` into `fps` and `fps_base`, so the rate is decided in one place, slp2alpha. The scene's rate has to match the video's: Blender's Video Sequencer retimes a movie strip whose rate differs from the scene's, and the camera, keyed per frame, would drift against it. The frame range covers the samples. If the video has a frame without a sample (`frames.count < frames.video`, the game's last frame at the end of a replay; see part 1), the range still covers the video, and the camera holds its last key.

**Shake.** Included by default, as in the video. `--no-shake` subtracts `shake` from the x and y of both eye and look-at point.

## 3. Blender 5 animation API

[verified on Blender 5.2.3, the version the repo's other Blender tools use]

`Action.fcurves` no longer exists. Keys go into the channel bag of an action slot:

```python
import bpy
from bpy_extras import anim_utils

CONSTANT = 0   # Keyframe.interpolation as an integer

def channelbag(id_block):
    ad = id_block.animation_data or id_block.animation_data_create()
    action = bpy.data.actions.new(f"{id_block.name} Action")
    slot = action.slots.new(id_type=id_block.id_type, name=id_block.name)
    ad.action, ad.action_slot = action, slot
    return anim_utils.action_ensure_channelbag_for_slot(action, slot)

def key(bag, path, index, frames, values, interpolation=CONSTANT):
    fc = bag.fcurves.new(path, index=index)
    fc.keyframe_points.add(len(frames))
    fc.keyframe_points.foreach_set("co", [c for fv in zip(frames, values) for c in fv])
    fc.keyframe_points.foreach_set("interpolation", [interpolation] * len(frames))
    fc.update()
```

- The object and the camera data get one action each. The object's has location, rotation and the custom properties; the data's has `lens`.
- Animated custom properties use paths like `'["slippi_frame"]'`.
- `foreach_set` keeps a 3-minute game fast: about 10,800 frames × 12 curves [estimate].

## 4. The script: `tools/camera-export/import_melee_camera.py`

One file, needing nothing beyond Blender. Three ways to run it:

- **Command line:**

  ```sh
  blender -b [scene.blend] --python tools/camera-export/import_melee_camera.py -- "camera - game.json" \
      [--scale 0.1] [--offset X Y Z] [--frame-start 1] [--no-shake] [--no-scene] [--linear] \
      [--background-video] [--save out.blend]
  ```

- **Text Editor:** open the file and Run Script. That registers the operator and opens the file browser.
- **Menu:** `File → Import → Melee Camera (.json)` (`import_scene.melee_camera`, an `ImportHelper` operator), once the file is installed as an add-on or extension. [to test: whether Blender 5.2 still installs a legacy `bl_info` add-on from disk, or this needs a `blender_manifest.toml`]

Options, the same on the command line and in the operator:

| Option | Default | |
|---|---|---|
| scale | 1.0 | Blender units per Melee unit |
| offset | 0, 0, 0 | where Melee's origin goes |
| frame start | 1 | the Blender frame of the first sample |
| shake | on | off: the camera without shake |
| set scene | on | resolution, pixel aspect, fps, frame range, scene camera |
| interpolation | constant | or linear |
| background video | off | the transparent video named in `render.transparent`, looked up next to the JSON, as the camera's background (`frame_method` stretch) |

Importing the same file again replaces that camera: it's named `Melee Camera` plus the replay's file name.

Structure:

- `load(path)`: reads the JSON and checks `format`, `version` and that `samples` has `frames.count` entries.
- `melee_point`, `camera_rotation`, `lens_mm`: section 2, with `mathutils`.
- `build(scene, data, options)`: the object, the data and the keys.
- `channelbag`, `key`: section 3.
- `setup_scene`, `add_background`.
- `register`, `unregister`, and `main()` for the command line.

Errors: an unknown version, a sample count that doesn't match, or a missing field stop the import with a message. Samples whose `mode` isn't 0 or 4 are imported as they are and counted in the report printed at the end.

## 5. Later, optional

- **Fighters** as empties keyed per frame, if part 1 adds fighter positions to the export (from the replay's post-frame events, at `frame − 1`). Useful for attaching things to fighters, and for checking by eye.
- **Stage collision lines** as a mesh at z = 0, from `tools/logo-stage/stagedata.py` (needs the ISO), to watch the camera hold the stage in place.
- **The logo stage with a moving camera.** `blender_plate.py`, with these keys instead of the stage's fixed camera, rendering one plate per frame. Its mapping is this conversion with `s = 1 / scale_melee_per_m` and an offset.

## 6. Tests

- **Projection:** `validate_camera.py blender` (validation plan, section 6) imports real exports headless and compares Blender's `world_to_camera_view` with `projection.LookAtCamera` on probe points. They must agree to 0.01 px, and the look-at point must land at the exact centre. Repeated with `--scale 0.1 --offset 3 −2 1`.
- **Static camera:** a file built from a stage's fixed camera (`projection.from_ground_param`) gives the same pixels as the camera `blender_plate.py` makes for that stage.
- **Timing:** at Blender frame `f`, `slippi_frame` equals `samples[f − frame_start].frame`. Resolution and pixel aspect are what the file says, and the scene runs at exactly 60 fps (`fps = 60`, `fps_base = 1`).
- **Size:** a 10,800-frame file imports in under 5 s [estimate].

## 7. Effort

Half a day to a day. Most of it goes to the operator, the options and the tests [estimate].
