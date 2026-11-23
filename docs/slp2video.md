# One command, replay to finished video

`python3 tools/slp2video/slp2video.py REPLAY.slp [options]` takes a Slippi replay to a finished video in one go. Each option switches a step on or off. The render is `slp2alpha render`; your 3D model in place of the stage is the logo stage's Blender plate; then the composite; then the CRT pass from the crt-royale project.

```sh
python3 tools/slp2video/slp2video.py game.slp                                     # the stage without its background, transparent
python3 tools/slp2video/slp2video.py game.slp --keep-background --crt             # the game as it looks, on a CRT
python3 tools/slp2video/slp2video.py game.slp --model statue.glb --animelee       # Animelee fighters on your model, the game's camera
python3 tools/slp2video/slp2video.py game.slp --model logo --static-camera --crt  # the logo stage, fixed camera, on a CRT
python3 tools/slp2video/slp2video.py ys.slp --shy-guy-sprite mascot.png --bg-color 00ff00 --format mp4
```

The result is one file next to the replay (`--out-dir DIR`, or `-o FILE`), named after the replay and the options, for example `game (frames 3120 to 3480, characters only, animelee, 60 fps), statue stage, crt.mov`. It's ProRes 4444 (`.mov`), with alpha unless something fills the background, or H.264 (`--format mp4`, or `-o NAME.mp4`). H.264 has no alpha, so an `.mp4` is flattened, unless `--transparency` asks for a second file: `NAME matte.mp4`, the alpha as a grey video, white where the picture is opaque. Resolve, Premiere and Final Cut can use it as a luma matte.

## What you can ask for

| You want | Option | |
|---|---|---|
| A logo or sprite for the Shy Guys | `--shy-guy-sprite IMAGE` | Yoshi's Story. A PNG with transparency works best ([shy-guy-sprite.md](shy-guy-sprite.md)) |
| A 3D model in place of the stage | `--model FILE` | `.blend`, `.glb`/`.gltf`, `.fbx`, `.obj`, `.stl`, `.ply`, `.usd`/`.usdz`, `.abc`; `--model logo` for the [logo stage](logo-stage.md)'s logo |
| The background kept or removed | `--keep-background` | Default: removed. Kept: the game exactly as it looks, an ordinary opaque video |
| Transparency | on by default | `--no-transparency` flattens onto black, `--bg-color HEX` onto a colour; `--format mp4` flattens, or with `--transparency` writes a matte file beside it |
| A static or a moving camera | `--static-camera` | Default: the game's own moving camera |
| Regular Melee or Animelee | `--animelee` | The cel-shaded skins ([tools/animelee](../tools/animelee/README.md)) |
| A CRT | `--crt` | CRT Royale's realistic pixels, at the console's native resolution for regular Melee |

Also: `--start-frame` and `--end-frame` ([clips.md](clips.md)), `--characters-only`, `--hud`/`--no-hud`, `--hide-items`, `--hide-effects`, `--scale`, and the tool locations (`--dolphin`, `--iso`, `--ffmpeg`, `--blender`, `--librashader`). Options after a lone `--` go to `slp2alpha render` unchanged. `--keep-intermediates` keeps the work folder: the render, its alpha map, the camera export, the composite. After a failure the work folder is always kept, and its path printed.

## What's drawn

| | Stage | Background | Transparent | Stages |
|---|---|---|---|---|
| default | yes | removed | yes | Battlefield and Dream Land; elsewhere only the fighters, with a note |
| `--characters-only` | no | no | yes | all |
| `--model FILE` | your model instead | no | yes, around the model | the six legal stages |
| `--keep-background` | yes | yes | no | all |

`--keep-background` records without the flicker codes, so there's nothing to solve: Dolphin's recording is the video (`slp2alpha render --keep-background`, which writes `fullOpaque - NAME`). Its frames are the same as a transparent render's, except that a render to the end of a replay stops one frame short ([clips.md](clips.md)). It's also the only way to see Yoshi's Story with its stage and your Shy Guys together, because its background can't be removed.

The HUD (percents, stocks, timer) is drawn when the stage is, unless `--no-hud`.

## The model

Your model stands in for the stage, fitted the way the [logo stage](logo-stage.md) fits its logo, from the stage's own data on the ISO:

- **Width.** All of the model's objects together are as wide as the stage from ledge to ledge. `--model-scale 0.5` makes it half that, `2` twice.
- **Height.** Its highest point is the stage's top, where the fighters stand. `--ground xheight` uses the median top of its separate pieces instead, like a logo's lowercase letters (the logo's default). `--ground-offset 5` raises it 5 game units, `-5` sinks it.
- **Depth.** The plane the fighters move in cuts the model's depth in the middle; `--depth-shift 1` puts its front face there, `-1` its back.
- **Facing.** The model's front faces the camera the way Blender's front view sees it (glTF's +Z front, OBJ and FBX by their own axes). `--model-rotation 180` turns it around, `--model-rotation 90,0,0` stands up one lying on its back.
- **Objects.** In a `.blend`, every object with geometry that renders (meshes, curves, text; collection instances aren't measured), or `--model-object NAME` (repeatable). A `.blend` keeps its own lights, world and colour management. Other files are imported into an empty scene; one with no lights gets a key, a fill and a rim light around the camera and a dim grey world, and is shown with Blender's Standard view, so its colours look as authored.
- **Finish.** Its own materials, or with `--model-cel` (the default with `--animelee`) the logo stage's flat cel bands and ink outline, which match Animelee's look. `--model logo` is metal or cel.

With `--static-camera` the model is rendered once, as the stage's fixed camera sees it, and cached (`~/Library/Caches/AlphaSolveVideo/logo-stage/plates/`), so the next replay on that stage only needs the fighters.

The moving camera's frames are cached too (`logo-stage/sequences/`), by everything they depend on: the camera export's contents, the model, its finish, fit and samples, and the code. Rendering the same clip again with another CRT mask, colour or format then skips Blender. The last 3 clips are kept, about 1.8 GB each for a 3-minute game; `--model-cache N` keeps N, and 0 none.

With the moving camera, `render --export-camera` writes the game's camera on every frame ([camera-export.md](camera-export.md)), and Blender renders the model through it, one picture per video frame. Two Blender processes share the frames (`--model-jobs`), with 16 samples per frame (`--model-samples`): about 4.4 frames a second at 640x480 on an M1 and 9 on a GTX 1060, so a 4 s clip takes 54 s and 26 s. The cel finish (`--model-cel`, the default with `--animelee`) is about three times as fast: it's emission only, so it's drawn without shadows, which changed none of its pixels. Fewer samples would show: after the CRT, 8 samples are 1.2/255 from 64 on the model, 16 samples 0.8 ([`report-gpu-crt.md`](report-gpu-crt.md)). A camera export labels its videos exactly 60 fps, and so does the result.

Checked with a flat card fitted to Battlefield, through the moving camera: its top edge was where the game's camera puts the stage's top to within -0.03 ± 0.06 px (worst 0.16 px) on all 300 frames of a clip at 640x528, and -0.02 ± 0.06 px (worst 0.14 px) on 120 frames of a raw 640x480 recording, and the fighters stand on it. A still plate and the first frame of a moving one from the fixed camera's export are the same picture (alpha differs by at most 3/255, centroid within 0.002 px). The plates are rendered without EEVEE's overscan, which moved the picture off the camera's projection: by up to 0.5 px at 640x528 and 1.6 px with a raw recording's non-square pixels.

## The CRT

`--crt` finishes with CRT Royale, the original shader rendered by librashader, in its physical-pixels mode: every pixel of the picture is drawn as a real CRT draws it, with the beam's profile, the gaps between scanlines and the phosphor triads.

- **Regular Melee is recorded at its native resolution**: `--scale 1` and `render --raw-resolution`, the console's own 640x480 picture, one row for each of the 480 lines it sends to the TV. Dolphin's usual 640x528 stretches those 480 rows to the TV's shape by blending neighbouring rows, which would put 528 scanlines on the tube, some of them a mix of two. `--scale 2` is allowed (with a note); its scanlines are then half as tall.
- **Animelee** is recorded at its `--scale` (2 by default), also unstretched: 960 rows, each one a scanline, a sharper high-resolution set.
- **The shape.** The picture is squeezed sideways to the shape Melee draws it for, 1.2173 times as wide as tall (its camera's aspect): 584x480, or 1168x960. The analog signal has no columns, so this loses nothing a tube would show. Then each row becomes a scanline 6 px tall at native resolution (3 px for Animelee's 960 rows): 3504x2880 either way, with 3 px triads. `--crt-scale` sets the pixels per scanline.
- **The mask.** `--crt-mask grille` (aperture grille, the default), `slot` or `shadow`. `--crt-triads-per-pixel` and `--crt-params` (e.g. `halation_weight=0.1`) go to the renderer.
- **Transparency** survives: the renderer keeps the alpha. The model and the background colour are composited before the CRT, so they're on the tube too.
- **Speed and disk.** Where Blender is found (macOS, Linux), Blender's GPU module draws the CRT in one process for the whole video, and the encoder sets the pace ([`report-gpu-crt.md`](report-gpu-crt.md)).
  - **On an M1,** 3504x2880 frames go into Apple's ProRes at 19 a second when the fighters are alone, and 4 when every pixel is drawn. That's about 4 times `librashader-cli`'s speed. `--format mp4` is slower there (1.2–5.6 a second), because `libx264` encodes it.
  - **On a Linux PC with a GTX 1060,** they go 6–8 a second into `prores_aw` and 12–13 into NVENC: 3–6 times `librashader-cli`'s speed.
  - **A 3-minute game's CRT** takes 14–31 minutes on the PC, and 10–45 on the M1, depending on the picture and the format.
  - **Disk:** frames stream from one ffmpeg through the renderer into another, so nothing but the few frames in flight touches the disk. The encoder is Apple's ProRes where it works (ten times faster than `prores_ks` at this size), else `prores_aw` (about four times), else `prores_ks`. A minute of 3504x2880 ProRes 4444 is about 23 GB; `--format mp4` is H.264 4:4:4 (chroma subsampling would smear the phosphor stripes), which VLC and editors play but QuickTime doesn't. With an NVIDIA GPU it's encoded by NVENC, about seven times `libx264`'s speed on a GTX 1060, at least as close to the drawn frames, in files about four times as big (about 10 GB a minute).

The renderer is [`tools/crt`](../tools/crt/README.md): the crt-royale TouchDesigner project's `render_video.py`, brought into this repo with the shaders it needs (libretro's slang-shaders at `2345ee91`, the 38 files the preset uses). Blender draws them, from the preset as `librashader-cli` 0.12.1 compiles it (`tools/crt/blender-chain/`): its frames are 0.003/255 from `librashader-cli`'s. Without Blender, or on Windows, `librashader-cli` draws them: `python3 tools/crt/install_librashader.py` builds it with Rust into `packages/librashader/` (or `--librashader PATH`), and its runtime is the platform's: Metal on macOS, Direct3D 11 on Windows, wgpu on Vulkan on Linux. `--crt-runtime` picks one (default `auto`). On the same picture and settings `librashader-cli` gives exactly the frames the crt-royale project's script gave.

- **Encoding loses some of the finest detail.** Phosphor stripes and scanline gaps are about the hardest picture there is to compress. Against the drawn frames, ProRes 4444 through Apple's encoder came to 31.7 dB (on average 4.9/255 off), the XQ profile 36.4 dB at 1.5 times the size, and the H.264 4:4:4 of `--format mp4` 35.3 dB at a sixth of ProRes's size [measured on 10 frames at 3840x2880].

## Platforms

Everything `slp2video` runs is in this repo: the render (`tools/slp2alpha`), the model (`tools/logo-stage`, Blender's side included), the camera (`tools/camera-export`), the composite, and the CRT with its shaders (`tools/crt`). What it starts comes from elsewhere: the headless Dolphin build (`tools/dolphin-build`), ffmpeg, Blender and `librashader-cli` (`tools/crt/install_librashader.py`). So do your own files: the ISO, models, sprites, and the logo's Blender project for `--model logo`.

| Step | macOS | Linux | Windows |
|---|---|---|---|
| Render and camera export | Verified | Verified on a PC: Vulkan; the camera export byte-identical to the Mac's ([`plan-linux.md`](plan-linux.md)) | The Dolphin build compiles on GitHub Actions; not run yet |
| The model in Blender, fixed and moving camera | Verified | Verified on the PC, Blender 5.2.3 on the GTX 1060 | Blender found in Program Files or Steam; not run |
| Composite | Verified | Verified on the PC | Not run |
| CRT | Verified: Blender's GPU module (Metal), and `librashader-cli`'s Metal | Verified on the PC: Blender's GPU module (OpenGL) on the GTX 1060, 0.0002/255 from `librashader-cli`'s frames there; `librashader-cli` with wgpu on Vulkan, on the GTX 1060 and the Intel GPU, 0.8 to 0.95/255 from the Mac's frames on average; also in Docker on Mesa's lavapipe | Not run. `librashader-cli`: Direct3D 11 first, then wgpu |
| `slp2video` itself | Verified | Verified on the PC: a clip with the logo through the moving camera and the CRT | Not run |

Blender is found as given (`--blender`, `$BLENDER`), then in `/Applications` or `~/Applications`, in Program Files or Steam on Windows, on the PATH, in `~/.local/bin` (where a Linux download is often linked, and which an SSH command doesn't put on the PATH) and in `/snap/bin`.

What's left: on Linux, the model's speed (Blender's EEVEE is now the longest step; [`plan-gpu-crt-model.md`](plan-gpu-crt-model.md) step L4), and choosing the GPU with one option (`--gpu`, [`plan-linux-gpu.md`](plan-linux-gpu.md) step G5). On Windows, everything after the Dolphin build ([`plan-windows-remaining.md`](plan-windows-remaining.md), step 7 for `slp2video`), and the CRT is still drawn by `librashader-cli` there. `.github/workflows/crt.yml` builds `librashader-cli` and tests the CRT, including a real render, on Windows, Linux and macOS runners, when it's run by hand from the Actions tab.

## Speed

For a 4 s clip (240 frames) with the logo through the moving camera and the CRT, `.mov` ([`report-gpu-crt.md`](report-gpu-crt.md)):

| Step | Mac M1 | Linux PC, GTX 1060 |
|---|---|---|
| Render (flicker and solve) | 9 s | 16 s |
| Render with `--keep-background` | about 5 s | — |
| Model, fixed camera | 2 to 3 s, once per stage, finish and size | — |
| Model, moving camera (2 Blender processes, 16 samples) | 54 s | 26 s |
| Composite | 1 s | 2 s |
| CRT, Blender's GPU module | 17 s (ProRes) | 28 s (ProRes), 16 s (`.mp4`, NVENC) |
| CRT, `librashader-cli` | 58 s | 119 s |
| All of it | 82 s | 72 s (`.mp4`: 58 s) |

## Files

`tools/slp2video`:

| File | |
|---|---|
| `slp2video.py` | the command |
| `test_slp2video.py` | unit tests for what a set of options does (`python3 tools/slp2video/test_slp2video.py`) |

It uses `tools/slp2alpha` for the render, `tools/logo-stage` (`plate.py`, `blender_plate.py`, `composite.py`) for the model and the composite, and `tools/crt` for the CRT.
