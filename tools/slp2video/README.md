# slp2video

One command from a Slippi replay to a finished video: the render, your 3D model in place of the stage, a background colour or transparency, and a CRT look. How each step works, what was checked and how fast it is: [`docs/slp2video.md`](../../docs/slp2video.md).

```sh
python3 tools/slp2video/slp2video.py game.slp                                     # stage without its background, transparent
python3 tools/slp2video/slp2video.py game.slp --keep-background --crt             # the game as it looks, on a CRT
python3 tools/slp2video/slp2video.py game.slp --model statue.glb --animelee       # Animelee fighters on your model
python3 tools/slp2video/slp2video.py game.slp --model logo --static-camera --crt  # the logo stage on a CRT
python3 tools/slp2video/slp2video.py ys.slp --shy-guy-sprite mascot.png --format mp4
python3 tools/slp2video/slp2video.py --help                                       # every option
```

Needs what `slp2alpha render` needs (the headless Dolphin build, a Melee ISO, ffmpeg); Blender for `--model`; for `--crt`, `librashader-cli` 0.12.1 (`python3 tools/crt/install_librashader.py` builds it). The CRT renderer and its shaders are in [`tools/crt`](../crt/README.md).

| File | |
|---|---|
| `slp2video.py` | the command |
| `test_slp2video.py` | unit tests for what a set of options does: `python3 tools/slp2video/test_slp2video.py` |
