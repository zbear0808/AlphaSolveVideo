# Animelee research & validation tools

Exploratory and verification scripts used to validate [Animelee](https://www.animelee.xyz) compatibility with the AlphaSolve pipeline.

The ISO build script needed for end-user renders lives at [`tools/animelee/build_iso.py`](../../tools/animelee/build_iso.py).

## Tools

- **`isodiff.py VANILLA.iso MODDED.iso`**:
  Compares GameCube ISO headers, DOL executable sections, and file systems (FST). Used to verify whether Animelee modifies Melee's executable code (it does not: 0 DOL changes, only data file replacements).
- **`compare.py REPLAY --vanilla V.iso --animelee A.iso [-- render options]`**:
  Renders a replay under both vanilla and Animelee ISOs, checks that frame counts match exactly, calculates alpha map differences, and generates a composite contact sheet (`sheet.png`).
- **`run-matrix.sh VANILLA.iso ANIMELEE.iso OUT_DIR`**:
  Runs `compare.py` across six diverse cached test replays (all legal stages, ICs, projectiles) to verify lack of desyncs across the board.
