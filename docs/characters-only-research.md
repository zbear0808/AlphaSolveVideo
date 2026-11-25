# Characters-only renders: hiding the stage in Slippi replays

Research and experiments for an slp2alpha option that hides the stage, so the transparent video holds
only the fighters, plus their items and effects.

> Integrated as `python3 -m slp2alpha render --characters-only`; the codes are in
> `Resources/Characters Only Codes.txt`. The example frames, sync-test outputs and scripts referenced
> below were produced during the research (November 2026) and are not part of the repository.


- **How it was run**: everything ran on the headless mainline playback build through
  `slp2alpha.runner.run_dolphin`. No other Dolphin was started and no video was played.
- **How the code was read**: Melee's NTSC 1.02 code from the doldecomp/melee sources, checked against
  the DOL in the ISO (capstone disassembly, and a call-site scan of every `b`/`bl` in the DOL).

Deliverables: [`codes.txt`](codes.txt) (same format as `Resources/*.txt`), example frames under
`frames/`, sync-test results under `sync/`, scripts under `tools/` (section 9).

## 1. Answers in short

- **Yes, the stage can be hidden on every stage while fighters render normally.**
  - One generic two-line Gecko code does it; no stage-specific code is needed.
  - Melee already has a "stage visible" switch that only the stage's draw callback reads. Develop
    Mode's X + D-pad down toggle uses it, together with "hide HUD" and a white/black background, so HAL
    had a characters-on-flat-colour capture mode built in.
  - The code makes the switch's getter always answer "hidden". The stage background codes become
    unnecessary.
- **Three more generic codes give a clean result**:
  - **Hide Stage Particles**: Battlefield sparkles, Stadium fireworks and other stage particles are drawn
    by the shared particle system, not by the stage.
  - **Hide HUD and Overlays**: percents, stocks, timer, Ready/GO/GAME!, P1/CP indicators,
    magnifying-glass bubbles, name tags.
  - **Hide Screen Flash**: strong hits tint the whole screen for about 10 frames, which would become a
    semi-transparent veil over the entire video.

  A fourth one, **Hide Shy Guys**, covers Yoshi's Story.
- **Fighter shadows disappear** with the stage. Melee projects them onto stage geometry, so nothing is
  left to receive them.
- **Kept by default**, because I think the user wants them (they belong to the fighters):
  - fighters, sword trails, respawn platforms;
  - items and projectiles;
  - all effects: hit sparks, dust, smoke, shields, KO blasts, entry beams.

  Two tested optional codes remove them: **Hide Items and Projectiles** and **Hide Effects**.
- **The flicker technique works unchanged.**
  - With the stage hidden, the whole background alternates pure black / pure white.
  - Pairing is unambiguous, alternation is 100%, there are no gaps, and the pair-violation score is
    exactly 0. That is cleaner than with the stage visible: the HUD was what made pairs slightly
    inconsistent.
  - The background solves to alpha 0, fighters to 255.
  - Recording is about 1.4× faster on Battlefield, because far fewer draw calls are made.
- **Sync-safe.** Every patch is display code: render callbacks, getters that only render callbacks call,
  or a render function pointer. No game state is written. Playback comparisons with Slippi's per-frame
  resync turned **off** back this up:
  - without flicker, fighters stay pixel-identical to normal playback through a whole 199 s Stadium
    match, and on Final Destination and Fountain of Dreams;
  - with flicker, flicker + codes stays identical to flicker alone (Fountain of Dreams, 60 s);
  - a deliberate one-instruction logic change desyncs within seconds in the same test.
- **Side finding, not caused by these codes:** the flicker setup diverges from normal 60 fps play when
  resync is off. It happened on Fountain of Dreams after about 21 s, with or without the display codes.
  slp2alpha keeps resync on (section 6.4).

## 2. How Melee draws a match (the parts that matter)

Melee (HSD/sysdolphin) renders through **camera GObjs**. Each camera's render callback picks which
**GX links** (draw lists) it draws; every drawable GObj sits on one link.

| GX link | Contents | Drawn by |
|---|---|---|
| 0 | stage lights and fog setup (`Ground_801C4640`, `Ground_801C1E2C`) | main camera |
| 3 | **every stage model**: Ground GObjs, render callback `grDisplay_801C5DB0` (FoD's wrappers call it too) | main camera (layers 2/1/0 behind fighters, layer 3 in front), stage sub-cameras |
| 4 | sword trails (`ftCo_8009F54C`) | main camera |
| 5 | fighters (`ftDrawCommon_80080E18`), incl. the respawn platform (a fighter "accessory") | main camera, magnifier, FoD reflection |
| 6 | items and projectiles (`Item_8026862C`), incl. Shy Guys | main camera |
| 7 | effects and all in-world particles (`efLib_render_callback` → `psDispParticles`) | main camera |
| 8, 10, 11 | HUD particles, HUD lights, HUD (percents, stocks, timer, countdown, GAME!, P1/CP, bubble frames) | HUD camera `fn_802F36B8` |
| 9 | name tags | name-tag camera `fn_802FCAC4` |
| 16 | full-screen flash/fade quad (`fn_8001FEC4`) | flash camera (lbBgFlash, priority 6) |

The main camera's callback, `fn_800301D0`, works in two steps:

1. It clears the screen with `game_camera.background_color` (0x80452C70). That's the colour the
   flicker code toggles on every render.
2. It draws the links above. Whatever isn't drawn shows the clear colour.

`grDisplay_801C5DB0` draws a Ground GObj only if `Camera_80030AC4()` is true. That getter returns the
"stage visible" bit (`x399_b5` of `game_camera`). Fighter shadows are drawn inside the same callback
(`lbShadow_8000EEE0`; `lbShadow_8000EFEC` for ground models flagged to receive shadows), so they go
away with the stage.

## 3. Options compared

| Option | Covers | Sync risk | Effort | Verdict |
|---|---|---|---|---|
| **A. Stage-visible flag**: `Camera_80030AC4` → `li r3,0; blr` | every stage model on every stage: backgrounds, platforms, moving parts | none: 2 callers in the DOL, both render callbacks; no memory written | 2 lines | **chosen** |
| B. Make `grDisplay_801C5DB0` return at once | same as A | none | 1 line | equivalent; A reuses HAL's own debug path |
| C. Drop link 3 from the main camera's link masks (the camera has per-link "off" bits `x398_b0..b4`) | same, main camera only | none | ~6 patched instructions, or a per-frame RAM write into a byte that also holds the render pass | no advantage |
| D. Set `JOBJ_HIDDEN` on stage joints after load | models | **unsafe**: `mpLib_80055E9C` hides a collision joint whose JObj is hidden, so platforms would lose collision. Stage code also toggles these flags itself (FoD, Stadium) | per stage | rejected |
| E. Don't create the stage's Ground GObjs (today's BF/DL/YS/FoD codes) | pure backgrounds only | **unsafe for anything with collision or logic**. Even backgrounds call the RNG: Battlefield's background object calls `HSD_Randi` at init and on each transition; the YS Shy Guy spawner rolls random patterns and spawns hittable items. Slippi's resync re-sets the seed every frame, which limits the effect but doesn't remove it | per stage | rejected; not needed with A |
| F. Dolphin Graphics Mods (`draw_started` target + `skip` action; mainline has them in `VideoCommon/GraphicsModSystem`, enabled with `EnableGraphicMods` + `User/Config/GraphicMods/GALE01.json`) | draws matched by texture hash | none (renderer only) | a texture list per stage and per stage state (Stadium forms, FD backgrounds); untextured geometry can't be targeted; textures shared with fighters/effects would vanish too | possible surgical fallback for one leftover element; not tested |

## 4. The codes (`codes.txt`)

| Code | Lines | What it does |
|---|---|---|
| **Hide Stage - Characters Only** | `04030AC4 38600000` `04030AC8 4E800020` | `Camera_80030AC4` ("is the stage visible?") returns false |
| **Hide Stage Particles** | `C23A02B4 00000005` + 5 lines | in `psDispParticles`' per-particle loop, a particle with `bank == 30` jumps to "next particle". `Ground` loads the stage's `map_ptcl` into bank 30, and `efLib_Cb_SPtcl/DPtcl` route bank 30 to the stage. Fighter and common banks are 0–21 and 31–49 |
| **Hide HUD and Overlays** | `042F36D4 48000024` `042F36B0 38600001` | the HUD camera's `if (!hidden)` becomes an unconditional skip, and `ifAll_IsHUDHidden` returns true (magnifier camera, bubble frames, name tags) |
| **Hide Screen Flash** | `0401FEC4 4E800020` | `fn_8001FEC4`, the render callback of the link-16 flash/fade quad, returns at once |
| **Hide Shy Guys (Yoshi's Story)** | `043F4CB0 8021A114` | Shy Guys' entry in the item render-callback table `it_803F4CA8` points at an empty function (`grBattle_GObj0_Callback2`, a lone `blr`) |
| Hide Items and Projectiles (optional) | `04031238 38600000` `040312E4 39000000` `040313A0 39600000` | removes the link 6 bit from the main camera's link masks (`Camera_800311EC`, `Camera_80031328`) |
| Hide Effects (optional) | `04030434 38600000` | removes the link 7 bit from `fn_800301D0`'s mask: all effects and particles |

None of the patched addresses overlap Slippi's bundled codes (`Sys/GameSettings/GALE01r2.ini`) or the
repo's codes. The final names were verified in a last Battlefield run (`frames/final_bf/`) with the
recommended set:

- Increase Input Timing Accuracy and the flicker code;
- Hide Stage - Characters Only, Hide Stage Particles, Hide HUD and Overlays, Hide Screen Flash, Hide Shy
  Guys;
- **no** stage background codes.

## 5. What is hidden, what remains

Checked on all six test stages, both without flicker (raw frames over the stage's background colour)
and with flicker + solve.

| Element | Default | Mechanism | Tested |
|---|---|---|---|
| Stage models: main stage, platforms, backgrounds, FD's transitions, FoD platforms/fountain/reflections, Stadium transformations and big screen, YS box and Randall, DL Whispy | hidden | Hide Stage | BF, DL, FD, YS, FoD, PS (`frames/*_survey*/sheet_00.png`) |
| Fighter shadows | hidden (can't be kept without the stage) | follows Hide Stage | BF, FoD |
| Stage particles: BF background sparkles and streaks, Stadium fireworks, FoD/DL particles | hidden | Hide Stage Particles | BF (visible in `frames/bf_hide_hud_nobg/`, run without the code), PS (fireworks in `frames/ps_survey/n08700.png` without the code, gone in `frames/ps_survey3/n08700.png` with it) |
| HUD: percents, stocks, timer | hidden | Hide HUD and Overlays | all stages |
| Ready/GO, GAME!, P1/CP/P2 indicators | hidden | same | BF start (`frames/bf_hide/` shows them with the stage-only code); Stadium GAME! appears in normal playback, not with the code (`sync/ps_sync2/B1/worst_11980…png`) |
| Magnifying-glass bubble (off-screen fighter) | hidden | same | BF (`frames/bf_hide/`, frames 7–8) |
| Name tags | hidden | same | BF (`DishonestMuddyCoyote.slp`, [nametags.md](nametags.md)) |
| Screen flash on strong hits | hidden | Hide Screen Flash | Stadium final hit: background alpha 29 → 6 over ~10 frames without the code, 0 with it (`frames/ps_end_hidden/n11870.png` vs `frames/ps_end_noflash/n11870.png`, `frames/ps_flash/alpha_0028.png` vs `frames/ps_noflash/alpha_0028.png`) |
| Shy Guys | hidden | Hide Shy Guys | **not observed**: the only YS replay (38 s) spawns none |
| Fighters, sword trails, respawn platform | kept | — | all |
| Held/thrown items, projectiles (missiles, charge shot, lasers, turnips) | kept | optional Hide Items and Projectiles hides the models; their flames/trails are effects | BF item replay (`frames/bfitems_noitems/cmp_n00540.png`, `cmp_n01020.png`: left with, right without) |
| Effects: hit sparks, dust, smoke, shields, KO blast, entry beams and the dark disc under fighters at the start | kept | optional Hide Effects | BF item replay (`frames/bfitems_hidden/sheet_00.png` vs `frames/bfitems_noeffects/sheet_00.png`) |

Notes:

- The fighters keep the stage's lights and fog (link 0), so they look exactly as on that stage.
- A KO blast covers most of the screen with semi-transparent light for ~15 frames, with mean alpha up to
  170/255 (`frames/bf_ko/sheet_magenta.png`). It's a fighter effect, so it stays unless Hide Effects is
  on.

## 6. Sync safety

### 6.1 Why these codes cannot change game logic

- **Hide Stage**
  - It writes no memory. It only changes what `Camera_80030AC4` returns.
  - That function has exactly two call sites in the DOL, both display code: `grDisplay_801C5DB0` (stage
    draw) and `fn_800301D0` (main camera, which gates the collision-debug overlay with it).
  - Every access to that flag byte (`game_camera+0x399`) is in camera accessors or render code.
- **Skipping stage drawing changes no input to game logic.**
  - Collision (mpLib) sets up joint matrices itself (`HSD_JObjSetupMatrix` before reading).
  - `HSD_JObjMakeMatrix` refreshes the parent first. So world matrices depend only on the joints'
    transforms, not on whether a draw computed them earlier.
  - Stage animations and hazards run in procs, not in render callbacks.
  - The skipped render path calls no RNG.
- **Hide HUD**
  - The HUD-hidden byte (0x804D6D58) is read only by `fn_802F36B8` (HUD camera render callback) and by
    `ifAll_IsHUDHidden`.
  - The getter's callers are the bubble render callback, the magnifier camera callback, the name-tag
    camera callback and the Develop Mode toggle.
  - The HUD itself keeps running. Its percent "shake" calls the game RNG (`HSD_Randf` in
    `ifStatus_802F4B84`) from a proc, and that proc still runs.
  - Slippi's bundled `Optional: Hide HUD` instead skips creating the timer and percent HUD, so those
    RNG calls disappear. That's a small logic change, papered over by resync.
- **Hide Stage Particles** changes only the draw loop of `psDispParticles`, whose only callers are the
  two calls in `efLib_render_callback`. Particles are still spawned and simulated by procs.
- **Hide Screen Flash**: `fn_8001FEC4` is only a render callback (link 16). The flash state machine runs
  in procs.
- **Hide Shy Guys**
  - `it_803F4CA8` is read only by `Item_8026862C`, when it registers an item's render callback.
  - Shy Guys still exist, collide, can be hit and drop items.
  - The render-only flags their callback would set (`xDCF` b4/b5/b7) are read only by item draw and
    material code.
- **Hide Items / Hide Effects** change link masks inside camera render callbacks only.

### 6.2 Playback comparisons with resync OFF

**Why resync is off for these tests.** Slippi's playback normally overwrites each fighter's position,
facing, action state and percent, plus the RNG seed, every frame (`RestoreGameFrame.asm`,
"shouldResync"). That would hide a desync, so these tests set `"shouldResync": false` in the comm file.
Any change to game logic then accumulates.

**Method.**

1. Play the replay twice: once as the reference, once with the codes.
2. In the run with the stage hidden, mark the fighter pixels: everything that isn't the flat background
   colour or, with flicker, the pixels whose black and white renders match exactly.
3. On those pixels, compare the two runs, frame by frame. Each sampled frame is compared with the
   reference frames around it, because recordings occasionally drop a field.

In sync, the best match is ~0 % differing pixels. After a desync, fighters are elsewhere or in other
poses, and nothing matches again.

| Test (resync off) | Result |
|---|---|
| Determinism: normal vs normal, FoD 40 s | identical: 220/220 samples 0 % (`sync/fod_bisect/B1`) |
| Determinism: flicker vs flicker, FoD 60 s (resync on) | identical: 297/297 samples 0 % (`sync/fod_flicker_vs_flicker`) |
| **Control**: display codes + `ftCo_Damage_CalcVel` → `blr` (no knockback; one instruction), FD 25 s | **desync**: median 94 % of fighter pixels differ (no flicker), 97 % (flicker); persistent (`sync/fd_sync/B2`, `sync/fd_sync3/B2`) |
| Display codes vs normal, FD 25 s, no flicker | in sync: median 0.08 %, frame offset 0 in 126 of 129 samples. The few samples above 20 % are semi-transparent effects over the stage vs over black; fighters identical (`sync/fd_sync/B1/worst_00850…png`) |
| HUD code alone vs normal, FoD 40 s | identical: median 0 %, all samples < 2 % |
| Display codes vs normal, FoD 40 s (moving platforms), no flicker | in sync: median 0.08 %, pixel-identical stretches up to the end; the rest is transient (smoke) (`sync/fod_bisect/B5`) |
| **Display codes vs normal, Pokémon Stadium, whole 199 s match (transformations), no flicker** | in sync: in every 1000-frame block, 20–47 % of samples are pixel-identical (< 0.1 %), up to the end (frames 11000–11800: 21 %). After a desync no sample matches exactly again. The non-exact samples are effect transparency (`sync/ps_sync2`) |
| Flicker + display codes vs normal, FD 25 s | in sync: median 0 %, 86 % of samples < 0.5 %, last 20 samples 0 % (`sync/fd_sync3/B1`) |
| **Flicker + display codes vs flicker alone, FoD 60 s** | in sync: constant frame offset (no drift), median 0.07 %, 59 % of samples exact and 74 % < 2 %, matching to the end (last 50: 70 % < 2 %). The misses are small fighters (≈200 px masks) and the stage/HUD covering them in the stage-visible reference (`sync/fod_flicker_vs_flickercodes_resync_off`) |

### 6.3 Production configuration (resync on)

- **Flicker + display codes vs flicker alone, FoD 60 s, resync on:** constant offset, median 0 %, 61 %
  exact, 71 % < 2 % (`sync/fod_flicker_vs_flickercodes_resync_on`). That matches the resync-off result,
  so the display codes don't change what resync has to correct.
- **Flicker + codes vs normal play (resync on), FoD 40 s:** the frames line up with no drift (median 0 %,
  65 % exact; `sync/fod_resync_on/B2`). There are some multi-second mismatch stretches, for example around
  a respawn (`worst_pair01520…png`). Positions agree there, so they're probably colour-flash timing in the
  120 fps mode. They aren't caused by the display codes (6.4).

### 6.4 Side finding: the flicker mode itself drifts from normal play

On Fountain of Dreams with resync **off**, every flicker variant diverges from normal 60 fps playback,
and nothing matches afterwards:

| Variant (resync off, FoD) | Diverges after |
|---|---|
| Input Timing + flicker (no display codes) | ~1290 frames (≈21 s) (`sync/fod_flicker40/B1`) |
| Input Timing + flicker + display codes | ~1500 frames (`sync/fod_flicker40/B2`) |
| Flicker code without Input Timing | diverges (`sync/fod_flickercode_only`) |

Without flicker, the display codes stayed identical to normal play (6.2), and flicker + codes stays
identical to flicker alone. So it's the 120 fps mode that isn't perfectly logic-neutral.

In one 90 s resync-off run, flicker playback also stopped advancing at frame 4362 and was stopped by the
runner's stall timeout.

slp2alpha plays with resync on. That re-sets position, facing, action state, percent and RNG every
frame, so fighters stay where the replay says. Other state isn't restored: animation phase, velocities,
and hazard positions such as FoD platforms. This affects today's stage-visible flicker renders as much
as characters-only ones. It deserves its own look on stages with moving hazards (FoD, Stadium,
Yoshi's Story), e.g. checking whether fighters ever float above or sink into platforms.

## 7. Flicker technique with the stage hidden

| Run | Fields | Alternation | Pairing (violation true / other) | Gaps | slp2alpha checks |
|---|---|---|---|---|---|
| BF, stage hidden only (HUD visible), 15 s | 1798 | 1.000 | white/0 (0.118 / 0.444) | 0 | ok |
| BF, stage + HUD hidden, no BF code, 15 s | 1798 | 1.000 | white/0 (0.000002 / 0.368) | 0 | ok |
| **BF, recommended set, whole 32 s replay** (`frames/bf_full`, `frames/final_bf`) | 3838 | 1.000 | white/0 (**0.0** / 0.368) | 0 | **no problems** |
| **FoD, 3 core codes, 40 s** (`frames/fod_full`) | 4798 | 1.000 | white/0 (0.099 / 0.227) | 0 | **no problems** |
| FoD, first 122 pairs, per-pixel check | — | — | 0 pixels where black > white | 0 | — |
| PS final hit, 60-frame window (seeked) | — | 1.000 | white/0 (0.0008 / 0.819) | 0 | ok |

- The whole screen alternates between pure black and pure white: 86–93 % of each raw frame is exactly the
  clear colour (`frames/final_bf/raw_01.png` white, `raw_02.png` black).
- The solved alpha is 0 on the background and 255 on fighters. Edges and effects are partial, as with
  the stage version.
- Median frame alpha is 12/255 on BF (fighters fill ~5 % of the frame).
- The only big alpha spike in the BF match is DK's KO blast (frames 870–886).
- Hiding the HUD removes the small pair inconsistency seen with the stage visible (0.118 → 0).
- FoD's 0.099 over the first 60 pairs didn't reproduce: a later per-pixel check of a new recording of the
  same segment found 0 violating pixels. It was probably transient, under heavy load from the other jobs on the machine.
- Speed, BF, same machine, back to back: stage visible (BF background code) took 19.6 s and 21.1 s;
  characters-only took 14.5 s and 13.4 s for the same 3838 fields.

## 8. Example frames

All paths are relative to this folder. "magenta" = solved transparent frame composited over magenta;
"alpha" = alpha map; "raw" = recorded flicker field (static PNG).

| What | Path |
|---|---|
| Final result, BF, recommended set (7 frames) | `frames/final_bf/sheet_magenta.png`, `sheet_alpha.png` |
| A black/white pair with the stage hidden | `frames/final_bf/raw_01.png` (white), `raw_02.png` (black) |
| BF whole match, 3 core codes (13 frames, full-res frame 600) | `frames/bf_full/sheet_magenta.png`, `sheet_alpha.png`, `t_magenta_05.png`, `t_alpha_05.png` |
| Transparent clip, BF output frames 600–720 (animated PNG with alpha) | `frames/bf_full/clip_600_720.png` |
| FoD, 3 core codes | `frames/fod_full/sheet_magenta.png`, `sheet_alpha.png` |
| Stage hidden but HUD, Ready, P1/CP and magnifier bubble still there | `frames/bf_hide/sheet_magenta.png` |
| Stage + HUD hidden, but BF background particles still there (no particle code) | `frames/bf_hide_hud_nobg/sheet_alpha.png` |
| Surveys, no flicker, 3 core codes: BF, DL, FD, YS, FoD, PS | `frames/{bf_survey3,dl_survey,fd_survey,ys_survey,fod_survey,ps_survey3}/sheet_00.png` |
| Stadium fireworks without vs with Hide Stage Particles | `frames/ps_survey/n08700.png` vs `frames/ps_survey3/n08700.png` |
| Screen flash without vs with Hide Screen Flash | `frames/ps_end_hidden/n11870.png` vs `frames/ps_end_noflash/n11870.png` |
| KO blast effect (kept by default) | `frames/bf_ko/sheet_magenta.png` |
| Items kept / items hidden (crops) / effects hidden | `frames/bfitems_hidden/sheet_00.png`, `frames/bfitems_noitems/cmp_*.png`, `frames/bfitems_noeffects/sheet_00.png` |

## 9. Suggested integration in slp2alpha

1. **Add the codes.** Put the codes from `codes.txt` in `Resources/` (e.g. append them to
   `Required Codes.txt`). `cmd_render` loads only `Required Codes.txt` today.
2. **Add a `--characters-only` mode** to `render`:
   - `enabled = FLICKER_CODES + ["Hide Stage - Characters Only", "Hide Stage Particles", "Hide HUD and Overlays", "Hide Screen Flash", "Hide Shy Guys (Yoshi's Story)"]`;
   - add **no** `stages.BACKGROUND_CODES`;
   - skip the `stages.is_supported` check, since every stage works in this mode.
3. **Optional flags**: `--keep-hud` (drop the HUD code), `--hide-items`, `--hide-effects`,
   `--keep-flash`.
4. **Keep `shouldResync: true`**, as now (section 6.4).
5. **Possible follow-up for the stage-visible mode.** The same render-side idea could replace today's
   creation-skipping background codes with sync-safe ones. For example, a small hook in
   `grDisplay_801C5DB0` could skip drawing Ground GObjs whose `map_id` is in a per-stage background list.
   That would make Yoshi's Story, FoD, FD and Stadium backgrounds removable without touching game logic.

Scripts in `tools/`, all using the headless build through `runner.run_dolphin`:

| Script | What it does |
|---|---|
| `exp.py` | harness |
| `survey.py` | no-flicker stills |
| `fullrun.py`, `window.py` | flicker + solve + stills |
| `violations.py` | per-pixel pair check |
| `synctest2.py`, `synctest4.py` | sync tests |
| `dol.py`, `callers.py` | DOL disassembly and call-site scan; `dol.py` re-extracts `main.dol` from the ISO on first use |
| `experimental_codes.txt` | the same codes under their test names (`CO …`), plus the two desync controls (`CTRL …`, not display-only) |

## 10. Open questions and risks

1. **Stages beyond the six tested.**
   - The mechanism is generic: in the decomp, every Ground render callback goes through
     `grDisplay_801C5DB0`. The only other ground-related callbacks are the Stadium/FoD render-to-texture
     cameras, the light/fog setup and the Home-Run Contest text camera. One stage file (Big Blue) still
     has unmatched asm in the decomp.
   - Stage-spawned **items and enemies** on non-legal stages would stay visible: Klaptraps, Tingle,
     Birdo, Arwing lasers, Flat Zone tools, Whispy's apples, Goombas/Koopas, etc. The Shy Guy patch
     extends to the other entries of `it_803F4CA8`, but some of those items can be picked up by players.
2. **Shy Guys untested on screen.** The only YS replay has none. The patch is a single render-pointer
   swap, but should be checked on a YS replay that has them.
3. **Screen flash code.** Verified only on one strong hit (Stadium). It also skips the match fade-in/out
   quads, which is harmless for transparent output.
4. **Shadows** can't be kept. If wanted, they would need a separate shadow-catcher pass, which is out of
   scope.
5. **Effects are part of the output by default.** KO blasts and some hit effects briefly cover large
   parts of the frame with semi-transparent light. Users who want only bodies can add Hide Effects.
6. **Drift of the flicker mode** (6.4) is a pre-existing property of the technique, now more visible
   because the stage no longer hides it. Recommended as a separate investigation.
7. **Recording gaps under load.** Some no-flicker runs on this heavily loaded machine skipped fields. All
   flicker runs with the Input Timing code had 0 gaps; without it there were 60 gaps in 40 s, as the
   README warns.
8. **Particle bank 64.** `grDatFiles` also loads stage particle data into bank 64 (0x40), apparently as a
   staging copy. No stage particle drawn from bank 64 was seen; if one ever shows up, add a second
   compare to the particle hook.
