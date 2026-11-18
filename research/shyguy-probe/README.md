# Shy Guy probes

Rerunnable experiments behind one question: can Yoshi's Story's Shy Guys be drawn with your own sprite in a transparent render, and where on screen does a position from the replay land? They use the repo's own pipeline (`slp2alpha`'s headless Dolphin runner, flicker codes and solver) and write everything to a work folder outside the repo.

> **Status:** Custom sprite replacement was integrated into `slp2alpha render --shy-guy-sprite` (see [`docs/shy-guy-sprite.md`](../../docs/shy-guy-sprite.md)). These scripts are preserved for research, static-camera coordinate calibration (`calibrate.py`), and discovering texture hashes for new disc variants (`textures.py diff`).

Needs the headless mainline build in `packages/` (`tools/dolphin-build/build-mac-mainline.sh`), a Melee NTSC 1.02 ISO and ffmpeg, as for `render`. The commands that look at pictures also need numpy and Pillow (`pip install numpy pillow`). The default replay is the Yoshi's Story one from `tools/render-tests/replays.json` (`RichAuthenticGull.slp`, 156 s, 18 Shy Guys); it is downloaded to the same cache. `--replay FILE` uses another one, `--out DIR` picks the work folder (default: a new temporary one).

| Command (under `research/shyguy-probe/`) | Time | What it shows |
|---|---|---|
| `items.py summary / tracks / window` | 1 s, no Dolphin | what the `.slp` records about Shy Guys (item type 210): position, facing, state and damage on every frame |
| `textures.py diff` | 7 s (`--full`: 2.5 min) | the textures Shy Guys draw, by diffing Dolphin texture dumps with and without the "Hide Shy Guys" code |
| `textures.py iso [--compare DIR]` | 1 s, no Dolphin | the same texture names, worked out from `GrSt.dat` on your ISO; `--compare` also checks the decoded pixels against a dump |
| `sprites.py make DIR` | instant | writes replacement PNGs (`badge`, `solid` or `halves`) under the right names |
| `sprites.py demo` | 15 s | the full pipeline with the replacement sprites, laid over a mock logo (`demo-sheet.png`) |
| `sprites.py markers` | 10 s | the flip-book order and the mirroring, checked frame by frame against the replay |
| `calibrate.py fit` | 10 s | replay position to pixel, fitted from the Shy Guys, with the static camera |
| `calibrate.py fighters` | 15 s | the same mapping checked on fighters standing on the main platform |

Times are from an Apple Silicon Mac with other work running.

## What they found (Yoshi's Story, NTSC 1.02, mainline build)

- **A Shy Guy is a flat quad with three textures**, RGB5A3, 76x72, 76x72 and 76x73. Only these three differ between the two dumps, over a 90-frame window and over the whole replay, and `iso` finds the same three in `GrSt.dat` with pixels identical to Dolphin's dump. Their names are in `common.py` (`SHY_GUY_TEXTURES`). They are a hash of the texture bytes, so the same on every machine.
- **Dolphin's custom textures replace them.** PNGs with those names in `<user dir>/Load/Textures/GALE01/`, plus `HiresTextures = True` in GFX.ini (`run_variant` does both). A replacement can be any size with the same aspect ratio. It only changes what is drawn, so the game, the flicker pairing and the solver are unaffected: `demo` records 600 game frames as 1200 fields, pairing detected, no problems, and soft edges in the art come out as partial alpha. The "Hide Shy Guys" code has to be off, or nothing is drawn.
- **The sprite is a flip-book.** The three textures cycle 7f15, 49a3, d55c (the start of their hashes), six frames each: median of 245 whole runs, range 4 to 11. 3 of 255 changes go the other way; not investigated.
- **It is mirrored when the Shy Guy faces left**: in every sample where the replay says left (626 of 626 in the last run) and in none where it says right (0 of 944). Text or one-way art reads backwards half the time. The art is also shared by every Shy Guy, and clipped to the quad (about 11 units square, 34 px at `--scale 1` with the fixed camera).
- **Replay position to pixel**, with `--static-camera` at `--scale 1` (640x528), from 69 Shy Guys: `u = 3.0757 x + 313.16`, `v = -3.0813 y + 378.81`, rms error 0.47 and 0.32 px, worst 1.35 px (`YS_STATIC_FIT` in `common.py`). Fighters standing on the main platform sit within about 1.5 px of it (46 samples; the vertical check is rough because dust and other effects reach below the feet).

Counts (samples, runs) change by a few from run to run: Dolphin sometimes skips a frame under load, which shifts what is sampled. The conclusions don't.

## Caveats

- Mainline build only: custom texture names depend on its hashing. They are also specific to NTSC 1.02 (`render` checks the ISO).
- `YS_STATIC_FIT` is for Yoshi's Story with the fixed camera. Replays don't record the camera, so with a following camera nothing can be placed on screen from the replay. Re-run `calibrate.py fit` if the camera code changes: it exits 1 if the stored numbers have drifted by a pixel or more.
- `sprites.py markers` and the calibration look at walking Shy Guys that have finished turning, so they skip hits, flights and the 20-frame turn at a wall.
- The scripts import `slp2alpha` from this checkout and use its runner, so a change to `config.write_user_dir` or to the codes affects them.
