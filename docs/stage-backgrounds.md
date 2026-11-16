# Stage backgrounds: what each legal stage needs

Analysis of the Gecko codes in `Resources/`, Melee's stage code (doldecomp/melee symbols and source for NTSC 1.02), and test recordings with the headless native build. November 2026.

Legal stages: Battlefield, Dream Land, Final Destination, Yoshi's Story, Fountain of Dreams, Pokémon Stadium. Only the first two are supported today.

## How the technique meets the stage

The flicker code toggles the camera's clear colour (`game_camera.background_color`, 0x80452C70) between black and white before every render. Anything the stage draws in front of the clear colour is the same in both renders, so the solver makes it opaque. "Supporting a stage" therefore means stopping it from drawing its background, so that only the playable stage, the fighters, effects and HUD stay opaque.

Each stage's objects are listed in a table (`grXX_StageCallbacks`). The stage's init function creates them by index (`grBattle_80219D84(id)`, `grLast_8021A7F4(id)` and so on). Stage objects are drawn through `grDisplay_801C5DB0` (a few through a small wrapper around it). It draws an object only during the camera pass that matches the object's layer (`Ground.x11_flags.b012`). The camera draws layer 2 first (the far background), then layers 1 and 0, then 3.

## What the existing codes do

| Code | Patch | Effect |
|---|---|---|
| Disable Battlefield Background + Particles | NOPs 3 calls in `grBattle_OnInit` | Objects 1 and 3 (background, layer 2) and the alternate stage 5 are never created |
| Disable Dreamland Background | NOP at `grOldPupupu_802107E0+0x50` | Object 3 (background, layer 2) is never created |
| Disable Yoshi's Background (optional) | NOP in `grStory_801E3030` | Object 1, the cardboard sky (layer 2), is never created |
| Disable Shy Guys (optional) | NOP of `bl grStory_801E3418` | Shy Guy spawning (items, RNG) is skipped |
| Disable FoD tree, halos, background coloring (optional) | NOPs in `grIzumi_801CBB88` and `grIzumi_801CBE64` | Object 1 (tree/pillars, layer 1) and the starfield (layer 2) are never created |
| Disable FD Background Transitions (optional) | NOP of `bl grLast_8021B2E8` | The FD background stops changing (it is still drawn) |

All of these remove objects or skip their logic, rather than just not drawing them.

## Sync safety

Several of the removed pieces call the game's single global random number generator (`HSD_Randi`/`HSD_Randf`). Examples: Battlefield's background transitions (`grBattle_BG_Callback2`), FD's background (`grLast_8021B2E8` and others), and Yoshi's Shy Guy spawns (`grStory_801E3418`). The particle system uses the same generator.

Removing them changes the random sequence for the rest of that frame. Slippi playback restores the seed at the start of every frame, which limits the effect. Most online FoD replays are recorded with "Lagless FoD" (on by default for netplay) and Slippi's playback runs them without it, so in practice this is safe, though it isn't strictly guaranteed.

A render-only alternative avoids the question entirely: keep every object and its logic, and just don't draw it.

## A generic render-only code

Tested and working:

```
$Hide Stage Background Layer [AlphaSolveVideo]
*Skips drawing stage objects on render layer 2 (the far-background pass) on every stage.
*Render only: the objects still exist and run their per-frame logic, so replays stay in sync.
C21C5DD8 00000003
2C000002 41820008
48000008 38000007
7C001800 00000000
```

It hooks `grDisplay_801C5DB0`'s layer comparison (`cmpw r0, r3` at 0x801C5DD8). If the object's layer is 2, it compares as layer 7, which no camera pass uses. The same hook can also hide chosen object ids (load `map_id` from `Ground+0x14`). A small generator for both kinds of code is in the analysis scratch files (`hidegobj.py`).

## Per-stage findings

Tests: short no-flicker recordings that hid one object at a time, then flicker recordings solved to transparent video, checking the alpha channel.

| Stage | Background pieces | With the layer-2 code | Still needed | Effort |
|---|---|---|---|---|
| Battlefield | Background objects 1–4 (layer 2), shooting-star particles | Background gone; particles remain | Nothing: keep the existing code, which also removes the particles | done |
| Dream Land | Background objects (layer 2) | Background gone | Nothing (existing code works) | done |
| Final Destination | Six background objects (4–9, layer 2) that change over the match, colour/fog transitions, small star particles | Background gone through every transition (95 s test, pairs stay intact) | Suppress the small background star particles (faint specks in the alpha) | small |
| Yoshi's Story | Cardboard sky (object 1, layer 2), sea and side islands (inside the main stage model, object 3), Shy Guys (items) | Sky gone; sea, islands, Shy Guys remain | Hide the sea/island joints of object 3; hide Shy Guy items when drawn | medium |
| Fountain of Dreams | Starfield (layer 2), tree and pillars (object 1, layer 1), fountain, big star, pillar (inside the main stage model, object 3), spray particles, floor reflection | Stars gone | Hide object 1; Slippi's "Lagless FoD" (removes particles and reflection); hide the fountain/star/pillar joints of object 3 | medium |
| Pokémon Stadium | Big screen and machines (object 1, layer 1), stadium walls (in an object not yet identified), sparkles, four transformations | No change (nothing on layer 2) | Hide object 1; find and hide the wall joints; test fire/grass/rock/water transformations (not yet covered: the 15 s test ended before the first one) | large |

Notes:

- Skipping the creation of Pokémon Stadium's object 1 stops the replay from starting at all. Render-only hiding has no such problem.
- Hiding individual joints (setting `JOBJ_HIDDEN` after the stage loads) is **not** automatically safe: `mpLib_80055E9C` turns off a collision joint's lines when its JObj is hidden. It's only safe for purely decorative joints, set on that joint alone (not with `HSD_JObjSetFlagsAll`, which also flags the children). A draw-level skip for those joints would be safer still. Finding the joints means one recording per joint, or reading the stage `.dat` files.
- On stages with moving hazards (FoD platforms, Stadium transformations, Randall), the flicker mode may drift from normal play. Slippi's resync pins fighters every frame but not hazards. Check that fighters line up with platforms before supporting these stages with the stage visible. With the stage hidden (characters-only mode), this doesn't matter.
- FD's colour transitions call `Camera_SetBackgroundColor`, but the flicker code runs after game logic each frame. The pairs stayed black/white throughout the 95 s FD test.
- The HUD (timer, percent, stock icons) is opaque on every stage. A render-only "Hide HUD and Overlays" code exists (see characters-only mode below).

## Characters-only mode (stage hidden entirely)

Melee has a built-in "stage visible" switch (Develop Mode's X + D-pad down), read only by `grDisplay_801C5DB0` and the main camera's collision-debug overlay. Making its getter return false hides every stage model on every stage, including moving parts. Fighters, items and effects still draw. The tested codes (all render-only) are in `Resources/Characters Only Codes.txt`, used by `python3 -m slp2alpha render --characters-only` (details in `docs/characters-only-research.md`):

- Hide Stage - Characters Only
- Hide Stage Particles
- Hide HUD and Overlays
- Hide Screen Flash
- Hide Shy Guys
- Optional: Hide Items and Projectiles, Hide Effects

The flicker technique works unchanged: pure black/white background, no gaps, a pair-violation score of 0 on Battlefield, and about 1.4× faster recording. Fighter shadows disappear with the stage, because Melee draws them onto it. No stage-specific codes are needed, so all six stages work in this mode.

## Suggested order

1. Final Destination: add the layer-2 code plus a particle fix. Smallest change, and the most played stage after Battlefield.
2. Fountain of Dreams: layer-2 code + object 1 + Lagless FoD, then the joint hiding for the fountain.
3. Yoshi's Story: layer-2 code, the sea/island joints, Shy Guys.
4. Pokémon Stadium: object 1, wall joints, then each transformation.

For each stage, check a full match with the flicker recording and the alpha channel before adding it to `slp2alpha/stages.py`.
