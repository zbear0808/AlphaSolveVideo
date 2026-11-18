# Render tests

`run.py` renders a set of public replays from [Slippi Lab](https://slippilab.com) and checks the results. The replays are listed in `replays.json` and downloaded on first use to `test-replays/` in the cache folder (about 30 MB; see below).

```sh
python3 tools/render-tests/run.py                 # everything (about an hour on an M1)
python3 tools/render-tests/run.py --only PS FoD   # replays whose file name or label contains PS or FoD
python3 tools/render-tests/run.py --quick         # skip the whole-recording pairing check
```

Each replay is rendered once per entry in its `"renders"` list, e.g. `[]` for a default render or `["--characters-only", "--static-camera"]`. `{tests}` in an argument stands for this folder, so a render can use a file kept next to `run.py` (`shy-guy-sprite.png`, a test image for `--shy-guy-sprite`). For each render, the harness checks that:

- the render succeeds and prints no warnings;
- the transparent video and the alpha map have one frame per game frame. The match's first frame (during "Ready") never reaches Dolphin's recording, so one frame fewer is expected.
- over the whole recording, every 5 s block pairs each black field with the white field of the same game frame (`--quick` skips this);
- the background alternates on nearly every field;
- enough of a typical frame is transparent: over 80% with `--characters-only`, over 15% with the stage visible;
- with `--export-camera`: the camera file passes `tools/camera-export/validate_camera.py check` (also against Dolphin's raw rows), has a sample for every video frame (except the game's last frame of a replay that ends on stocks or time), and both videos are labelled exactly 60 fps.

Results go to `render-test-results/` in the cache folder (`~/Library/Caches/AlphaSolveVideo` on macOS, `%LOCALAPPDATA%\AlphaSolveVideo` on Windows):

- `summary.md`: one row per render;
- per render, `result.json`, `render.log` and `sheet.png`. The sheet has eight frames composited over magenta, with their alpha below.

Renders that already have a result are skipped on the next run unless `--force` is given; `--recheck` only re-evaluates the saved results with the current checks. The videos (about 1.6 GB per minute of gameplay) are deleted after checking unless `--keep-videos` is given.

Status per render:

- **PASS**: no problems;
- **CHECK**: it finished, but something needs a look (listed in the summary);
- **FAIL**: the render failed;
- **SKIP**: this ffmpeg has no encoder for the render's format (`--format hevc` needs macOS). Nothing is saved, so it runs once an ffmpeg that can is found.

The replays were picked to cover:

- all six legal stages;
- doubles;
- projectile and item characters (Samus, Link, Peach, Pikachu, Falco);
- Ice Climbers and Game & Watch;
- online replays and console (Nintendont) replays;
- Pokémon Stadium with and without transformations (console tournament setups freeze it);
- a 12-second quit-out, rendered in every output format;
- clips: a slice from the middle of a match, one that starts 8,500 frames in (Dolphin fast-forwards to it), and one that runs to the replay's last frame (`--start-frame`, `--end-frame`);
- camera exports (`--export-camera`): a whole match with the stage drawn, a clip that Dolphin skips ahead to, the fixed camera, and the quit-out;
- the game as it looks (`--keep-background`): the quit-out, a Final Destination clip and Yoshi's Story with the Shy Guy sprite. These are opaque, recorded without the flicker, so the transparency and pairing checks don't apply; the frame count does;
- unstretched recordings (`--raw-resolution`, 640x480): a characters-only clip and the quit-out with the camera export.

Adding a replay means adding an entry with its Slippi Lab file name (shown in the address bar or in `https://slippilab.com/api/replays`).
