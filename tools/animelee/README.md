# Animelee renders

[Animelee](https://www.animelee.xyz) is a cosmetic Melee mod: cel-shaded character models (flat colours, a black
outline with a white inner stroke) and remade legal stages. The look is in the models and textures, so
Dolphin draws it with no special shader.

```sh
brew install xdelta                              # Windows: xdelta3.exe from github.com/jmacd/xdelta-gpl/releases
python3 tools/animelee/build_iso.py              # once: patches your Melee ISO (Launcher's, or --iso PATH)
cd tools/slp2alpha
python3 -m slp2alpha render REPLAY.slp --animelee --characters-only --scale 2
```

`--animelee` uses the ISO in `animelee/` under the cache folder (`~/Library/Caches/AlphaSolveVideo` on macOS, `%LOCALAPPDATA%\AlphaSolveVideo` on Windows) and adds "animelee" to the output name.

## Findings (November 2026, Complete Edition patch 1.0)

- The patch changes 144 of 1209 files and **not the DOL**, so every Gecko code in `Resources/` still applies.
  Changed: character costumes (`Pl*.dat`), the six legal stages, `IfAll.usd` (HUD), `MnSlChr.usd` (CSS), `EfCoData.dat`.
- Characters Animelee doesn't cover stay vanilla (for example Mr. Game & Watch).
- Frame counts and fighter silhouettes match a vanilla render on all six legal stages
  (`--characters-only`; mean alpha difference 0.2 to 0.6 out of 255), so playback stays in sync.
- Stage-visible renders work on Dream Land (the background code still clears the sky); other stages are untested.
- At `--scale 1` the 1 to 2 px outlines look jagged; use `--scale 2` or `3`.
- The m-ex based Animelee builds use a modified DOL and are not covered.

## Tools

- `build_iso.py`: downloads the patch and builds the ISO needed by `slp2alpha render --animelee` (it needs `xdelta3`).
- Research & comparison scripts are located in [`research/animelee/`](../../research/animelee/README.md):
  - `isodiff.py`: compares DOL sections and FST files between vanilla and modded ISOs.
  - `compare.py`: renders both and reports frame counts, alpha difference and a contact sheet.
  - `run-matrix.sh`: runs `compare.py` over test replays from the cache.
