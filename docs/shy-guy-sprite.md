# Shy Guy sprite

`python3 -m slp2alpha render REPLAY --characters-only --shy-guy-sprite IMAGE` draws Yoshi's Story's Shy Guys with your image instead of the game's art. The image is sized to fit the Shy Guy, and appears wherever the game puts a Shy Guy.

```sh
python3 -m slp2alpha render game.slp --characters-only --static-camera --scale 2 --shy-guy-sprite mascot.png
```

The output name gets "shy guy sprite". The replay has to be on Yoshi's Story: on another stage the option prints a note and does nothing. It needs `--characters-only`, or `--keep-background` to draw the whole stage with your Shy Guys in an opaque video (Yoshi's Story's background can't be removed with its stage showing, see `docs/stage-backgrounds.md`), can't be combined with `--hide-items` (Shy Guys are items), and needs the headless mainline build. It works with `--animelee`.

## The image

Any picture ffmpeg reads. PNG or WebP with transparency works best: the transparent parts stay transparent in the output, and soft edges come out as partial alpha.

- **Size and shape.** The image is scaled to the largest size that fits a Shy Guy's square (76:72), keeping its shape and centred, with transparent padding around it. A wide logo ends up small and centred; give it padding of your own to place it differently. The picture can't be bigger than that square.
- **Resolution.** The image is resampled to about the size a Shy Guy has on screen: 38 pixels wide per `--scale` step with `--static-camera` (the square is 35 px wide at `--scale 1`), 76 without it (the game's camera zooms; the square is 40 to 115 px wide at `--scale 1`). A larger picture would shimmer, because Dolphin doesn't mipmap custom textures. For more detail, use a higher `--scale`.
- **Mirrored when it faces left.** A Shy Guy turns by rotating its square, so it shows your image back to front when it walks left. Text and one-way art read backwards half the time. Symmetric art is fine.
- **One image for all of them.** Every Shy Guy, and all three frames of its walk cycle, use the same picture.

Everything else about a Shy Guy is the game's own: its path, the turn at the wall, how it's knocked away. Nothing in the game changes except what is drawn, so replays stay in sync.

## How it works

A Shy Guy is a flat square textured with three images (RGB5A3, 76x72, 76x72 and 76x73) from `GrSt.dat`, the Yoshi's Story stage file. Dolphin replaces a texture when a PNG named after it, `tex1_<width>x<height>_<hash of the pixels>_<format>.png`, is in `Load/Textures/GALE01` under its user folder. `slp2alpha/shyguy.py` fits your image to the square, writes it under the three names and turns on `HiresTextures`, and `render` no longer uses the "Hide Shy Guys" code.

- **Which names?** The names depend on the disc. `shyguy.py` hashes the textures in the ISO's `GrSt.dat` (`slp2alpha/disc.py`) and picks the set it knows: vanilla NTSC 1.02, or Animelee Complete Edition, whose Shy Guys are 152x144. Another disc stops with an error. `research/shyguy-probe/textures.py diff` finds the names for a new one by comparing two Dolphin texture dumps, with and without Shy Guys.
- **Edges.** Scaling is done with the colours multiplied by the alpha, and the transparent texels next to the sprite are given the colours of its edge. Otherwise Dolphin's filtering would pull the black of the transparent texels into the edge, and every sprite would get a dark outline.
- **Measured** (`research/shyguy-probe`, vanilla disc, Yoshi's Story): only these three textures differ with and without Shy Guys, over a whole replay. The recording pairs black and white fields as usual. Of 626 samples where the replay says a Shy Guy faces left, 626 were mirrored, and 0 of 944 where it faces right.

## Checked

`tools/render-tests` has a clip with the option (frames 1500 to 1800 of the Yoshi's Story replay, fixed camera): 301 frames, no warnings, and the same clip with `--keep-background`. The sprite was also checked by eye over light and dark backgrounds with no outline, on the vanilla disc and on Animelee, at `--scale 1` and `2`.
