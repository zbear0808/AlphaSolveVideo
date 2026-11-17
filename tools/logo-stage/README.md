# Logo as the stage

Renders a replay's fighters over a 3D logo that takes the place of the stage, sized to the stage's ledges and seen through its fixed camera. How it works, what was checked and what it doesn't do: [`docs/logo-stage.md`](../../docs/logo-stage.md).

```sh
python3 tools/logo-stage/logo_stage.py game.slp --scale 2                # metal logo
python3 tools/logo-stage/logo_stage.py game.slp --animelee --scale 2     # Animelee skins, cel-shaded logo
python3 tools/logo-stage/plate.py battlefield --style cel --scale 2      # only the logo, as a PNG
python3 tools/logo-stage/stagedata.py                                    # each stage's camera, ledges, top
```

Needs the headless Dolphin build, a Melee ISO and ffmpeg (as `slp2alpha render` does), Blender, and the Blender project with the logo (`~/Documents/logo_metal_fracture/logo_metal_fracture.blend`, or `--logo-project` / `LOGO_STAGE_PROJECT`).

| File | |
|---|---|
| `logo_stage.py` | the whole pipeline for one replay |
| `plate.py`, `blender_plate.py` | the logo as one stage's camera sees it |
| `projection.py` | the stage camera as a pinhole model |
| `stagedata.py` | camera, ledges, top surface and platforms of the six stages, from the ISO |
| `composite.py` | the logo under a transparent video |
| `check_projection.py` | fighters standing on the stage against the model (plays a replay in Dolphin) |
| `overlay_check.py` | draws the projected collision lines on a recorded frame |
| `validate_stagedata.py` | the ledges and floors against the test replays |
| `dolphin_frames.py`, `replay_events.py` | record plain frames of a replay window; read fighter positions from a `.slp` |
| `test_projection.py`, `test_stagedata.py` | unit tests; the ones that need your ISO skip without it |

```sh
python3 tools/logo-stage/test_projection.py && python3 tools/logo-stage/test_stagedata.py
```
