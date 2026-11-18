# The logo as the stage

`python3 tools/logo-stage/logo_stage.py REPLAY.slp` renders a replay's fighters over a 3D logo that stands in for the stage: as wide as the stage from ledge to ledge, with its top on the stage's top, seen through the stage's own camera. The fighters run along the top of the logo and grab its ends.

```sh
python3 tools/logo-stage/logo_stage.py game.slp --scale 2
python3 tools/logo-stage/logo_stage.py game.slp --animelee --scale 2 --start-frame 3120 --end-frame 3480
python3 tools/logo-stage/logo_stage.py game.slp --background 1c2230     # flat H.264 for a quick look
python3 tools/logo-stage/plate.py battlefield --style cel --scale 2     # only the logo, as a transparent PNG
```

It works for all six legal stages. The result is `<replay> (<options>), logo stage.mov` next to the replay (`--out-dir` moves it): ProRes 4444 with alpha, the same size as the render. A 2 s clip took 14 s, of which the logo took 4 s; the logo is cached per stage, finish and scale (`~/Library/Caches/AlphaSolveVideo/logo-stage/plates/`), so the next replay on that stage only needs the fighters.

Needs what `render` needs, plus Blender (tested with 5.2.3; `/Applications/Blender.app`, or `--blender` / `BLENDER`) and the Blender project the logo comes from (default `~/Documents/logo_metal_fracture/logo_metal_fracture.blend`; `--logo-project` / `LOGO_STAGE_PROJECT`). Options after a lone `--` go to `slp2alpha render`, e.g. `-- --hide-effects`.

## What it does

1. Reads the replay's stage, and that stage's camera, ledges and top surface from the ISO (`stagedata.py`).
2. Renders the logo in Blender as that camera sees it (`plate.py`, `blender_plate.py`): polished scratched metal, or with `--animelee` the flat cel finish with an ink outline. It's a transparent PNG the size of a recording at that `--scale`.
3. Runs `slp2alpha render --characters-only --static-camera` with the same `--scale` and `--animelee`.
4. Lays the logo under the fighters (`composite.py`).

## How the logo is fitted

| Stage | Ledges (x, y) | Flat top | Camera eye | Field of view, tilt | Logo width | Game units per logo metre | Logo width in the picture (1x) |
|---|---|---|---|---|---|---|---|
| Battlefield | ±68.4, 0 | ±68.4 at y 0 | (0, 100, 300) | 30°, -12° | 136.8 | 77.2 | 430 px |
| Yoshi's Story | ±56, -3.5 | ±39.2 at y 0 | (2, 64, 387) | 25°, -4° | 112 | 63.2 | 342 px |
| Dream Land | ±77.27, 0.01 | ±77.27 at y 0.01 | (0, 100, 400) | 30°, -10° | 154.54 | 87.3 | 370 px |
| Final Destination | ±85.57, 0 | ±85.57 at y 0 | (0, 45, 356) | 30°, -2° | 171.13 | 96.6 | 474 px |
| Fountain of Dreams | ±63.35, 0.62 | ±51.26 at y 0 | (0, 56, 373) | 25°, -5° | 126.7 | 71.5 | 402 px |
| Pokémon Stadium | ±87.75, 0 | ±87.75 at y 0 | (0, 91, 463) | 25°, -5° | 175.5 | 99.1 | 446 px |

- **Width.** The logo's width, hearts included, is the distance between the ledges (`--fit letters` uses the letters g to i only, so the hearts stick out past the ledges). In the picture the logo's edges end 1 to 2 px beyond the ledges (at `--scale 1`): its front face is a little nearer the camera than the plane the ledge is in, and the bevel adds a little.
- **Height.** The logo's ground line sits on the stage's top surface. By default that line is the tops of the x-height letters, which is what the fighters stand on (`--ground top` uses the highest points, the d and the dot of the i, so the letters sit lower). The hearts at the ends are lower than the letters (about 2 to 4 units at Battlefield's size), so a fighter hanging on the ledge hangs just above a heart. `--ground-offset` raises (or, negative, sinks) the logo by game units.
- **Depth.** The plane the fighters move in cuts the logo's thickness in the middle (`--depth-shift 1` puts it along the front face). The camera looks down on the stage, so the top of the letters shows as a thin strip behind the fighters' feet.
- **Camera.** The stage's own fixed camera, so a fighter's position in the replay and the logo agree. The logo keeps its size in Blender (1.77 m wide, so its lights, scratches and bevel stay as built) and the camera is placed where the game's camera would be after the same scaling. It looks at the point the game itself works out from the stage's tilt (`projection.game_interest`, with the game's polynomial sine), which `--static-camera` really uses.
- **Size.** The plate is the size Dolphin records at that `--scale`: 640x528 and 1280x1056, and 1920x1580 and 2560x2108 at 3 and 4 (`projection.recording_size`); `plate.py --raw-resolution` gives the unstretched 640x480 per step of `render --raw-resolution`.

Yoshi's Story's ledges are 3.5 below the flat top (its sides slope down to them) and Fountain of Dreams's 0.6 above it. The logo's ground line is level with the flat top, so its ends reach the ledges' x but not their height; at Yoshi's size the hearts' tops are about 2 to 3 units below the letters, close to its ledge.

## The two finishes

- **metal** is the project's `MAT_Metal_Scratched` steel under its studio lights and HDRI. The project's front shot looks at the logo from 2.6 degrees above; the stage cameras look from 2 to 18 degrees above (Battlefield is the steepest), which would put the studio's floor in the mirror and turn the front white. The lights and the HDRI are turned about the logo by the difference so the reflections stay what the project had.
- **cel** is the flat finish of `~/Documents/kitty_logo_crash` (hard colour bands, a hard glint, a white horizon line, diagonal gleams) with an ink outline of 0.6 px per `--scale` step, at least 1 (`--outline-px`). Animelee's own outlines are about 1 px at `--scale 2`. `--animelee` picks cel; `--style` overrides either way.

## How the math was checked

- **Camera.** Each stage file has the eye, vertical field of view and tilt (`grGroundParam`). The decomp (`Stage_80224CAC`, `Camera_8002DDC4`, `Camera_8002AF68`, aspect 1.2173333 in `cm_803BCB64`) turns them into a look-at point and a perspective camera; the picture is the 640x480 render stretched to 640x528. That is `projection.py`. The six stages' numbers are identical on the vanilla and the Animelee disc.
- **Blender.** Its camera (lens, pixel aspect, orientation) gives the same pixel as `projection.py` to 0.0002 px on every probe point (both ledges, both ends of the flat top, the origin), in all six stages. The rendered picture agrees too, now that EEVEE's overscan is off: a flat card's top edge lands within 0.1 px of the model. With overscan on (as the plates were first made), EEVEE moved the picture up to 0.5 px away from its own camera's projection at 640x528, more towards the top and bottom.
- **Ledges and top.** `stagedata.py` reads the collision data. The values agree with the community's numbers to 0.004, and with the 14 test replays: grounded fighters never get more than 0.1 beyond the end of the flat top, and a fighter hanging on a ledge is 1.6 to 2.9 outside the ledge point (4.7 for Jigglypuff), with the same offset per character on every stage (`validate_stagedata.py`). Drawn on a real Battlefield frame (`overlay_check.py`), the projected floors run through the middle of the top face of the main stage and all three platforms.
- **Fighters.** `check_projection.py` finds fighters standing still on the flat top (12 of the test replays have enough of them) and measures their silhouette against the model.
  - Across the picture the model's scale is off by -1.1 to +0.1 % on the replays with the most frames and widest spread (-0.06, -1.13, +0.05, -0.17, -0.11 %); the others, with fewer frames, scatter within ±3 %.
  - The lowest row of a standing fighter is 1 to 7 px *below* the row the model gives for the stage top (at `--scale 1`): 7 to 8 px on Battlefield, 2 to 5 on Yoshi's Story, Dream Land, Fountain of Dreams and Stadium, 1 to 2 on Final Destination. It grows with the camera's tilt, as it should if the lowest pixel is the near edge of a foot (a fighter's body reaches a few units towards the camera), but this wasn't separated from other causes. With the logo's own top strip the fighters' feet overlap the front lip of the letters by a few pixels, which reads as standing on them. `--ground-offset` moves the logo if you want them higher or lower.

## Your own model, and the moving camera

`plate.py --model FILE` fits any model instead of the logo, the same way (all its visible objects together; its highest point on the stage top unless `--ground xheight`): a `.blend` (`--object NAME` to pick objects), or a `.glb`/`.gltf`, `.fbx`, `.obj`, `.stl`, `.ply`, `.usd`/`.usdz` or `.abc` file imported into an empty scene. It keeps its own materials (`--style original`), with a key, fill and rim light if it brings no lights, or gets the cel finish (`--style cel`). `--model-scale` sizes it in stage widths and `--rotation` turns it first. The metal finish is the logo project's own.

`plate.py --camera-export "camera - NAME.json" --out FOLDER` renders the plate through the game's moving camera instead, one PNG per video frame (`000001.png` is the video's first), and `composite.py FOLDER video.mov out.mov` lays the video over them. `--jobs 2` shares the frames between two Blender processes. The camera is the one in the export, so with `--static-camera` it's the fixed camera again: the first frame matched the still plate (alpha within 3/255, centroid within 0.002 px). Through a moving camera, a flat card's top edge stayed within 0.16 px of the stage top the game's camera gives, on all 300 frames of a clip.

[`tools/slp2video`](slp2video.md) runs all of this from one command (`--model FILE` or `--model logo`, with or without `--static-camera`).

## What it doesn't do

- **Platforms.** With the stage hidden, nothing draws the floating platforms (Battlefield's three, Dream Land's three, Yoshi's Story's two, Fountain's three, Stadium's two): fighters stand on nothing there. `stagedata.py` has their positions for the stages where they stay put (Battlefield, Dream Land, Yoshi's Story's sides); drawing them as metal bars isn't built.
- **Camera moves in `logo_stage.py`.** It keeps the stage's fixed camera for the whole replay (`--static-camera`); the moving camera is `plate.py --camera-export` or `tools/slp2video`.
- **Shadows and the stage's moving parts.** Fighter shadows disappear with the stage (see `docs/characters-only-research.md`), and nothing of the stage's hazards or transformations is drawn.
- **The logo comes from the metal project.** Its `SM_Logo_Hero` is used for both finishes; the cel finish is the kitty project's look written into `blender_plate.py`, so only the metal project has to exist.

## Files

`tools/logo-stage`:

| File | What it is |
|---|---|
| `logo_stage.py` | the whole pipeline for one replay |
| `plate.py`, `blender_plate.py` | the logo, or your model, as one stage's camera sees it (Blender, headless); every frame of a camera export with `--camera-export` |
| `projection.py` | the stage camera as a pinhole model: world point to pixel and back |
| `stagedata.py` | each stage's camera, ledges, top surface and platforms from the ISO (`python3 stagedata.py` prints a table) |
| `composite.py` | the logo (a PNG, or a folder of frames) under a transparent video |
| `check_projection.py`, `overlay_check.py`, `validate_stagedata.py` | the checks above; `dolphin_frames.py` and `replay_events.py` support them |
| `test_projection.py`, `test_stagedata.py` | unit tests (`python3 test_projection.py`); the ones that need your ISO skip without it |
