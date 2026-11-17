# Rendering part of a replay

`python3 -m slp2alpha render REPLAY --start-frame N --end-frame M` renders only frames N to M, both included. Without either option the whole replay is rendered, as before. Either one can be left out: `--start-frame 5000` goes to the end of the replay, `--end-frame 900` starts at the beginning.

```sh
python3 -m slp2alpha info game.slp        # ... frames -123..7529 (128.1 s)
python3 -m slp2alpha render game.slp --characters-only --start-frame 3120 --end-frame 3480
```

That writes `fullTransparent - game (frames 3120 to 3480, characters only).mov` and the matching alpha map. The range is in the file name so that several clips of one replay don't overwrite each other. The output has exactly 361 frames (3120 to 3480), at the usual 60 fps.

## Frame numbers

They are the replay's own frame numbers: the ones `info` prints, and the ones slippi-js reports as `startFrame` and `endFrame` for combos and conversions. The first frame of a game is -123, and the frames before the match starts have negative numbers. A start before the first recordable frame (-122) is moved up to it, and an end past the last frame is moved back to it (with a note).

To render a combo, take its `startFrame` and `endFrame` from the stats and add some padding, for example 90 frames before and 60 after, so the clip doesn't begin on the first hit or stop on the last.

One command renders one clip of one replay. Giving several replays together with these options is an error.

## What to expect

- **A picture shows the game one frame late.** What the replay records for frame F first shows in picture F + 1. This is how Slippi's playback numbers frames (the number advances before the previous frame is drawn), not something added here. Measured on lasers and respawns: all six clean cases in clips showed up one frame after the replay's first record of them. A clip that starts at a combo's first hit therefore starts one frame before the hit lands, and the padding above covers it.
- **The same frames as a whole render.** A clip is the same pictures as the matching part of a whole-replay render. Compared on the test replay, one frame earlier or later was clearly worse (mean difference 0.12 to 1.1 out of 255 on the alpha map, against at most 0.05 for the right frame). Fighters, items and the camera are identical. A few dust and smoke puffs can differ by some pixels (up to about 2,000 of 338,000 in the clips compared), because the frames before the clip were skipped, not drawn.
- **The start of a match is special.** The first game frame (-122, during "Ready") is never recorded, in whole renders either, so a clip that begins there has one frame fewer than asked for. Clips that begin later have exactly the frames asked for.

## Speed

Dolphin has to play the replay up to the first frame of the clip. It does that without drawing anything, at roughly 4,000 game frames per second on an M1. The whole run of a 20-frame clip took 4.3 s from the start of a game, 6.2 s from frame 8,500 and 6.6 s from frame 9,200. The recording itself runs at the usual speed: a whole 156 s replay with `--characters-only` took 82 s.

While it skips ahead, Dolphin prints no progress. So the time Dolphin is given to start (`--boot-timeout`, 120 s) is extended by the number of frames skipped divided by 200, a margin of 20 times.

Clips shorter than about 5.5 s are solved after Dolphin finishes. Longer ones are solved while Dolphin is still recording, as for whole replays.

## Checks

A clip is checked like a whole render: the number of frames recorded against the number asked for, that the background alternates, and that the black and white pictures pair up. The checks cover only the clip's own frames. A clip that runs to the last frame of a replay would otherwise include the extra frames Dolphin records between the replay's end and the moment it is stopped, when the background no longer flickers, and wrongly warn that "the flicker code may not be active".

`tools/render-tests` has three clips: the middle of a match, one starting 8,500 frames in, and one running to the last frame of a replay.
