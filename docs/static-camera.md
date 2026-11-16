# Static camera

`python3 -m slp2alpha render --static-camera` keeps the camera still for the whole replay. It works with the stage visible or with `--characters-only`. With characters-only renders, the fighters then move over a fixed frame, so they can be laid over a still image of the stage, or any other background, without matching camera moves.

## How it works

Melee already has a fixed camera, used by Special Melee's Fixed-Camera mode and by some single-player stages. Each stage defines a fixed camera position, target and field of view that show the whole stage (`Stage_SetVecToFixedCamPos`, `Stage_GetCamFixedFov`). At the start of a match, `Ground_EnableMatchCamera` picks the fixed camera if the stage's parameters ask for it, otherwise the normal following camera.

- **Static Camera - Fixed Camera Mode** (`Resources/Camera Codes.txt`, `041C5820 60000000`) removes that check, so the fixed camera is used on every stage.
- **Disable Screen Shake** (already in `Resources/Required Codes.txt`) stops hits and stage events from shaking the camera.

The camera is in place from the first frame, and the framing doesn't change.

## Effect on game logic

The camera is mostly display state, but not entirely. Inspecting the callers of the camera functions in the game binary (doldecomp symbols, NTSC 1.02) shows three ways it can reach game logic:

1. **Off-screen flag.** Each fighter's "off-screen" flag (`ftLib_UpdateScreenVisibility`) is computed while drawing. It's read only by the magnifier HUD, and it's also what the replay's post-frame "is offscreen" bit records.
2. **Off-screen damage.** `Fighter_procAnim` damages a fighter that stays in a magnifying glass, but only when a per-player flag (`Player_GetMoreFlagsBit3`) is set. Only two game-mode functions set that flag. In versus play it stays off.
3. **Dream Land's leaf/apple spawns.** These read the camera's visible edges (`Camera_800307D0` in `grOldPupupu_80210D10`) to place leaves just outside the view. It's a visual stage effect, not something fighters interact with.

## Measured

Each replay was played twice with Slippi's per-frame resync **off**, normal camera vs `--static-camera`, with Slippi Recording writing out what was played. Every fighter's post-frame state was then compared frame by frame: position, action state, percent, shield, stocks, velocities and the rest.

| Replay | Length | Fighter records compared | Differences |
|---|---|---|---|
| Battlefield | 15 s | 1,804 | only the "is offscreen" flag (150 records) |
| Dream Land | 170 s | 20,404 | only the offscreen flag (1,353) |
| Final Destination | 95 s | 11,404 | only the offscreen flag (113) |
| Yoshi's Story | 36 s | 4,324 | only the offscreen flag (33) |
| Fountain of Dreams | 120 s | 10,187 | only the offscreen flag (185) |
| Pokémon Stadium | 195 s | 20,110 | the offscreen flag (1,120), plus position in 128 records, all during screen KOs (action states 6 and 7, DeadUpFall / DeadUpFallHitCamera) |

So the static camera changes no gameplay. Two things do differ, both expected:

- **The "is offscreen" flag in the replay data.** It changes because the view changed.
- **Screen KOs.** Melee places a fighter KO'd towards the camera relative to the camera itself. In normal renders, Slippi's resync then sets that position from the replay, so during those few frames the falling fighter is drawn where it was relative to the original camera. This is cosmetic, and only happens to a fighter who is already KO'd.

Other notes:

- Fighters are smaller in the whole-stage view. Use `--scale 2` (or more) for detailed output.
- With the stage visible, the flicker technique works unchanged (checked on Battlefield). With `--characters-only`, the fighters are small against a large transparent background. That's why pairing detection now counts clearly brighter pixels (`validate.VIOLATION_LEVEL`): averaging the brightness over the whole frame let dithering noise win when the fighters were so small.
