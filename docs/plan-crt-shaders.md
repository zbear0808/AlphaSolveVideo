# More CRT shaders: crt-guest-advanced and Sony Megatron

Status: plan, 23 November 2026; being built from 25 November. Section 9 lists the decisions.

Decided, 25 November:

- **guest is the new default shader**, in `render_video.py` and `slp2video --crt`. Royale stays as `--shader royale` / `--crt-shader royale`.
- **guest is drawn with its afterglow everywhere, with an option to turn it off.** Blender keeps it (4.4). Without Blender, a small persistent librashader program, `crt-stream`, keeps it too (4.5). `librashader-cli` per frame stays the last resort, with a warning. `--no-afterglow` (`--crt-no-afterglow`) draws guest without it.
- The other recommendations stand:
  - guest, then Megatron SDR, then guest-ntsc;
  - Megatron kept faithful in SDR;
  - `grille` as each shader's default look;
  - the measured numbers as the temporal reference in the tests;
  - Megatron vendored with a licence note.

  HDR10 (C9) waits.

Today `tools/crt` draws one shader, CRT Royale. The crt-royale TouchDesigner project (`~/Documents/touchdesigner/crt-royale`) has offline Python pipelines for two more, with their settings worked out and checked against the originals:

- **crt-guest-advanced** by guest(r), and its NTSC variant;
- **Sony Megatron Colour Video Monitor v2** by MajorPainTheCactus, in SDR and HDR10.

This plan brings both into `tools/crt` and `slp2video --crt` as fully as Royale is there:

- the original shaders vendored;
- drawn by Blender's GPU module on macOS and Linux, with `librashader-cli` as the fallback;
- the physical-pixels mode, alpha, ProRes and H.264 with a matte file;
- tests against librashader;
- checked on the Mac and on the PC.

Evidence tags, as in the other plans: **[verified]** measured or read in the source; **[reported]** from the TouchDesigner project's own notes, not re-checked here; **[estimate]**; **[to test]**.

---

## 1. Summary

- **What comes over is the shaders and their settings, not the TouchDesigner port.** The TouchDesigner project rewrote each shader as its own GLSL for TouchDesigner, with builders, a harness and a 1280-pixel cap. None of that is needed here. As with Royale, this repo runs the original upstream shaders, compiled by `librashader-cli` and drawn by Blender. What it takes from each pipeline is its `video.py` render profile (named masks, our defaults, the triad-pitch mapping) and what its analysis found.
- **Blender's GPU module compiles almost all of it already** [verified 23 November, Blender 5.2.3, Metal, M1]. This used `librashader-cli` 0.12.1's GLSL 330 and `blender_crt.py`'s `Pass` as it is:
  - crt-guest-advanced: **all 12 passes compile**;
  - crt-guest-advanced-ntsc: **18 of 19 compile**. Pass 6 (`ntsc-pass2`) fails: Metal can't initialise a local array with a constructor (`float a[33] = float[](...)`) that is assigned again later;
  - Megatron v2: **pass 0 compiles; pass 1 fails**. Its mask tables are constant arrays of arrays (`const uint _658[3][4][3] = uint[][][](...)`, with `#extension GL_ARB_arrays_of_arrays`), which Blender's GLSL-to-Metal translation can't parse.

  Both failures are the same kind of problem as Royale's one rewrite (a whole-array copy), and need source rewrites in `blender_crt.py` (section 4.3).
- **What `blender_crt.py` lacks is state across frames.** guest-advanced reads two of its own passes' previous frames (`AfterglowPassFeedback`, `AvgLumPassFeedback`). The NTSC variant alternates its chroma phase on odd and even frames (`FrameCount`). Today every frame is drawn with frame count 0 and nothing kept [verified: `blender_crt.py`]. That's correct for Royale only because its interlace detection is off.
- **Mip levels can probably wait.** guest's average-luminance pass reads a mip level of its input (`textureLod`), and Blender's Python can't build mips. But the TouchDesigner project found that this only feeds guest's raster bloom, which is off in every look [reported: `docs/suite-plan.md`]. `librashader-cli` doesn't build them either [reported].
- **slp2video's picture maps onto both shaders.** It sends 584×480 pictures for 3504×2880, 6 rows per scanline and 3 px triads:
  - guest draws one beam per source row by design. A 3 px aperture grille is its `shadowMask 6` at `masksize 1`, with no zoom;
  - Megatron's patterns are fixed and per output pixel. Its 3 px R G B grille is the `grille3` look (4K / 800 TVL with the BGR subpixel table) [reported: `pipelines/*/video.py`].
- **Megatron is dark in SDR.** Its full-strength mask lets through 20–27% of the light, against 82–94% for Royale. That's how the shader is designed: it expects an HDR display to make up for it [reported: `pipelines/megatron/pipeline.md`]. HDR10 output is a separate, optional step (C9).
- **Effort:** about **6.5–8 days** for both shaders in SDR on both machines, plus 1–1.5 days for Megatron HDR10 (section 8).

## 2. What's in the TouchDesigner project, and what comes over

| | crt-royale (here now) | crt-guest-advanced | Sony Megatron v2 |
|---|---|---|---|
| Preset | `crt/crt-royale.slangp` | `crt/crt-guest-advanced.slangp`; NTSC: `crt/crt-guest-advanced-ntsc.slangp` | `hdr/crt-sony-megatron-v2-default.slangp`, which `#reference`s `hdr/shaders/crt-sony-megatron-v2.slangp`; display presets in `hdr/sony_megatron_v2_presets/` |
| Passes | 12 | 12; NTSC 19 | 2 |
| Mask | 64×64 mask images, resized | procedural, 15 types; strength trades against brightness | procedural, binary, per output pixel |
| Light kept (SDR) | 82–94% | 57–72% (`grille`) | 20–27% |
| State across frames | none (interlace off) | afterglow, average-luminance feedback; NTSC phase | none |
| Textures | 6 mask PNGs | 4 colour LUTs | none |
| Licence | GPL 2 or later | GPL 2 or later (file headers) | no licence header; slang-shaders has no top-level licence file [verified] |
| Cost on the M1, Metal, 1280² | — | 6.7 ms/frame; NTSC 7.0 [reported] | under 3 ms [reported, estimate] |

From each `pipelines/<name>/` folder, this repo takes:

- **`video.py` and `video_<variant>.py`:**
  - `MASKS` and the look defaults (`LOOK` for guest, `OURS` and `SDR_MIN_BRIGHTNESS` for Megatron);
  - `params_ex(ctx)`, which turns an output size and a triad pitch into shader parameters. That's guest's `mask_size()` and Megatron's `mask_for_pitch()` with its `PITCHES` table;
  - the `TEMPORAL` and `OUTPUT` flags.
- **Megatron's display presets** (`pvm2730`, `pvm20l4`, `pvm1910`, `mx8000`). `params.display_params()` reads them through `tools/lrs.py`. Here they'd be read from the vendored presets instead (section 4.2).
- **What was found**, for the docs and the tests: the light-kept numbers, the afterglow's behaviour, Megatron's binary mask, and which codecs keep the mask (4:4:4 only, ProRes at `-qscale:v 2`) [reported: `pipelines/megatron/test_encode.py`].

What stays in the TouchDesigner project:

- the TouchDesigner GLSL ports (`glsl/guest/`, `glsl/megatron/`) and builders (`td/`);
- the harnesses, numpy oracles, reference images (`refs/`, 1.3 GB) and probes;
- the TouchDesigner-only parameter machinery (`uGA[]`, `uMT[]`, `td_spec.json`);
- `tools/lrs-seq`, unless decision 5 brings it over as the temporal reference.

## 3. What `tools/crt` assumes today

Each of these is one place to generalise [verified: `tools/crt`, `tools/slp2video`]:

- **One preset.** `render_video.PRESET`, `vendor_shaders.PRESET`, one `blender-chain/`, and `candidates()` sends any `--preset` other than the vendored one to `librashader-cli`.
- **Royale's settings.** `MASKS = {"grille": 0, "slot": 1, "shadow": 2}`, and `shader_params()` writes `mask_type`, `mask_triad_size_desired` and `geom_aspect_ratio_x/y`. `physical_settings()` and `standard_settings()` mix the general part (output size, scale, aspect) with Royale's parameters.
- **`vendor_shaders.closure()` only finds quoted paths** (`shader0 = "..."`), and doesn't follow `#reference`. On guest's preset (unquoted paths) and Megatron's (`#reference`), it finds only the preset file itself [verified]. Megatron's shader also `#include`s `include/*.h` under `hdr/shaders/`, which it does follow.
- **`blender_crt.py`:**
  - frame count 0 on every frame;
  - no feedback or history textures;
  - no mip levels;
  - only the one Metal array-copy rewrite;
  - the last pass is always 8-bit (`RGBA8`).
- **slp2video** has `--crt-mask {grille,slot,shadow}` and `--crt-params "more CRT Royale parameters"`, and its file names say "crt" or "crt slot mask".
- **The tests** (`test_crt.py`) check Royale's settings, its 38 vendored files, its chain, and Blender against `librashader-cli` on frames of Royale.

## 4. Design

### 4.1 One renderer, a shader option

`render_video.py --shader royale|guest|guest-ntsc|megatron` (default `royale`) and `slp2video --crt-shader ...` (same default). Nothing changes for existing commands: their output stays byte-for-byte the same as today's.

A shader is a small profile in a new `tools/crt/shaders.py`, standard library only, like the rest of `tools/crt`. It holds:

- `name` and `preset`: the vendored `.slangp`;
- `chain`: its `blender-chain/` folder;
- `masks`: named looks, first is the default. `--mask` and `--crt-mask` are checked against the chosen shader's;
- `params(ctx)`: ported from the pipeline's `params_ex`. `ctx` holds the output size, the source size, the triad pitch, the aspect, and whether this is physical-pixels mode;
- `temporal`: whether it needs one persistent chain (guest, guest-ntsc);
- `output`: `sdr` or `hdr10` (`megatron-hdr10`, step C9).

`physical_settings()` and `standard_settings()` keep working out the output size, scale and triad pitch, as now, and ask the profile for the parameters. `--params` and `--crt-params` stay "more parameters of this shader". `--list-masks` prints each shader's looks, as the TouchDesigner project's script does.

### 4.2 The shaders, vendored

One tree, `tools/crt/slang-shaders/`, at the same commit `2345ee91`, with one `MANIFEST` for all presets:

- `vendor_shaders.py` gets a list of presets instead of one. `closure()` learns:
  - unquoted paths (`shader0 = shaders/guest/advanced/stock.slang`);
  - `textures = "A;B"` with each `A = path`;
  - `#reference "..."`, followed recursively.
- The extra files to vendor: guest's `crt/shaders/guest/advanced/` (and `guest/hd/` where the NTSC preset uses it), its 4 LUTs, its `README_old`. Megatron's `hdr/shaders/` passes, `hdr/shaders/include/`, the v2 default and SDR presets, and the 4 display presets. That's a few hundred KB [estimate]; Royale's 38 files are about 1 MB.
- `.gitattributes` already keeps `tools/crt/slang-shaders/**` byte for byte.
- `slang-shaders/README.md` gets each shader's licence. Megatron has no licence header (decision 7).
- **Megatron's display looks** need their parameter values without librashader. `vendor_chain.py` already runs `librashader-cli parse`, which resolves `#reference`. It writes each look's resolved parameters into that chain's `chain.json`, so `shaders.py` reads them from there at run time, and `vendor_chain.py check` checks them.

### 4.3 Each preset as Blender draws it

`blender-chain/` becomes one folder per preset: `blender-chain/royale/` (today's files, moved), `guest/`, `guest-ntsc/` and `megatron/`. `vendor_chain.py write` and `check` loop over them. `chain.json` gains what the new presets use: feedback aliases, `OriginalHistory` use, `frame_count_mod`, float formats, and Megatron's looks.

The GLSL files stay exactly as `librashader-cli` writes them, so `vendor_chain.py check` stays a byte-for-byte check. The rewrites happen in `blender_crt.py`'s `split()`, as the array-copy rewrite does now, and each one is listed in its docstring:

1. **Local arrays initialised by a constructor** (guest-ntsc pass 6): `float a[33] = float[](x0, x1, ...);` becomes `float a[33]; a[0] = x0; a[1] = x1; ...`. Making the array `const` doesn't work: the pass assigns to it later [verified: Metal error "cannot assign to variable ... with const-qualified type"].
2. **Constant arrays of arrays** (Megatron pass 1): `const uint _658[3][4][3] = uint[][][](...)` becomes a flat `const uint _658[36] = uint[](...)`. Each index `_658[a][b][c]` becomes `_658[((a) * 4 + (b)) * 3 + (c)]`, and the `#extension GL_ARB_arrays_of_arrays` line goes. This needs a small bracket-matching parser rather than one regex, because the indices are expressions [to test: also on Linux OpenGL, where Blender adds its own `#version`].
3. Anything else the Linux OpenGL and Vulkan backends turn up [to test: on the PC].

[verified 25 November, Blender 5.2.3]: with rewrites 1 and 2 (and `a = b;` between whole arrays, also in ntsc-pass2, as a loop), all 45 passes of the four presets compile on Metal (the Mac) and on OpenGL (the PC). Linux OpenGL needed nothing more. One more rewrite is for speed: Blender's Metal backend turns the shader's global constant arrays into members of a class that every pixel builds, so Megatron's last pass took 280 ms a 3504×2880 frame. Each constant array is now a function with a `switch` (`k[i]` becomes `k(int(i))`): 32 ms. crt-royale has no such arrays, so its source is unchanged.

The quality bar is the one the Royale chain met. Blender's frames should be within 1/255 of `librashader-cli`'s on the same machine, and the goal is the same 0.003/255 [verified for Royale: `report-gpu-crt.md`].

[verified 25 November] Frame 0, Blender against `librashader-cli` on the same machine: 3 real pictures (the crt-royale project's movie, test card and jellybeans, scaled to 584×480) drawn at 3504×2880 with the crt-royale project's `params_ex` for slp2video's geometry (triad 3 px). Mean difference per channel, /255; the largest single difference in brackets:

| Preset, look | Mac (Metal against metal) | PC (OpenGL against wgpu) |
|---|---|---|
| guest grille, slot, shadow | 0.00001–0.00003 (1) | 0.036–0.050 (11) |
| guest-ntsc grille | 0.0001–0.0003 (2) | 0.058–0.082 (11) |
| Megatron grille (= grille3 at 3 px), slot, shadow, pvm2730, 4 px grille | 0.000000–0.000005 (1) | 0.002–0.011 (5) |

All within the 1/255 bar. On the PC, guest's difference is one pass, `bloom_horizontal`: it samples the source row at `floor(480 × v)`, and every fifth of its 600 rows lands exactly on a row boundary, where the two drivers round the other way. Blender's OpenGL and Vulkan backends agree with each other (0.0001), and the quad's vertex order, a single triangle and `noperspective` change nothing. The Mac's Blender frame is 0.010/255 from the PC's `wgpu` one. crt-royale's frames, through `main`'s `blender_crt.py` and this one, are byte for byte the same on both machines (3 masks, 5 frames each).

### 4.4 State across frames in `blender_crt.py`

These follow librashader 0.12.1's runtime (`filter_chain/chain.rs`, `binding.rs`), as the rest of `blender_crt.py` does:

- **Frame count:** frame *n* of the video is drawn with `FrameCount = n`, or `n % frame_count_mod` where the pass sets one. Royale doesn't read it with interlacing off, so its frames don't change [to test: Royale's chain stays byte-identical].
- **Feedback:** a pass whose alias `X` is read as `XFeedback` gets two targets, swapped after each frame. The feedback texture is the pass's previous output, and black on the first frame, as librashader starts it.
- **`OriginalHistoryN`:** guest only reads `OriginalHistory0`, which is the current frame (`binding.rs` binds Original) [reported]. Generalising this to N ≥ 1 is a ring of input textures; it's only needed if a later preset uses it.
- **Float targets:** guest's passes 5–10 and Megatron's pass 0 are `R16G16B16A16Sfloat`. `FORMATS` already maps that to `RGBA16F`, and these passes use it. The last pass stays 8-bit for SDR.
- **Mip levels:** none, as now and as in `librashader-cli`. Step C4 first checks that guest's average luminance only reaches the picture through raster bloom (`textureLod` in `avg-lum.slang`), and that bloom is off in our looks. If either is wrong, `blender_crt.py` builds the levels itself. The TouchDesigner project did that with 9 half-size passes, each a single 1/256-weighted bilinear sample at the texel centre, which matched Metal's `generateMipmaps` for this pass [reported: `pipelines/guest_advanced/td-plan.md` 4]. It also needs `textureLod(Source, uv, lod)` rewritten to sample those levels [estimate: +1 day].
- **`--warmup N`:** draw the first frame N extra times before the video, so the afterglow and luminance start settled. This is optional: the TouchDesigner project found frame 0 already in steady state, apart from near-black gradients [reported].

[verified 25 November] as built (`blender_crt.py`, following librashader 0.12.1's `binding.rs` and Metal `filter_chain.rs`):

- **Feedback:** two targets per feedback pass (guest's 2 and 4, guest-ntsc's 2 and 10), swapped before each frame as librashader does, cleared to zero first. `OriginalHistory0` is bound to the Original. The host's values are `librashader-cli`'s defaults: FrameDirection 1, OriginalFPS 1, FrameTimeDelta 0, HDRMode 0, BrightnessNits 200. A scalar no parameter declares (guest's `LUTLOW`, shadowed by a `#define`) is 0, as librashader binds it. `--warmup N` draws frame 0 as frames 0 to N − 1 first, then the video from frame count N, as the crt-royale project's `lrs-seq` does.
- **Afterglow:** the white-then-black step (288×288 at 1280×1280, guest's defaults, mean inside a 48 px margin) gives 222.4 → 35.7, 28.8, 22.6, 18.3, 14.8, 12.1, 9.5, 6.9, … and under 1 after 15 frames, on both machines. The largest difference from `temporal_results.json` is 0.0005 levels on the Mac and 0.06 on the PC.
- **guest-ntsc's phase:** on a still 584×480 card, frames 1 and 3 differ from frame 0 by 10.1/255 on average, frame 2 by 0.014.
- **Mip levels aren't needed for our looks.** `librashader` does build them (Metal `filter_chain.rs` calls `generate_mipmaps` on the output of a pass whose next pass has `mipmap_input`: guest's passes 2 and 3). Only `avg-lum.slang` reads them (`textureLod`, lines 93–96), into the alpha channel of `AvgLumPass` (line 113). That alpha is read only as `lum` (`crt-guest-advanced.slang` 295, `deconvergence.slang` 679), and `lum` only in `factor = 1.00 + (1.0-0.5*OS)*BLOOM/100.0 - lum*BLOOM/100.0` (lines 329 and 699; the NTSC versions alike). That's raster bloom, `BLOOM`, 0 by default (`crt-guest-advanced.slang` 181), and neither `video.py`'s `LOOK` nor its `MASKS` sets it (its `bloom` is another parameter, the bloom strength). With `BLOOM` 0 the factor is 1 whatever `lum` is. The frame-0 numbers above agree.
- **librashader-cli `-f N` isn't a reference for later frames on the Mac:** Blender's frames 1 and 3 of a still card are 0.03 and 0.07/255 from `librashader-cli -f 1` and `-f 3` with guest (0.012 with guest-ntsc), while its decay matches `lrs-seq`'s. That fits the crt-royale project's finding that the unpatched Metal runtime loses a mip-mapped pass's history [reported].

Per frame at 3504×2880 from 584×480, drawn and read back, no encoder (median of 20 frames; the Mac's vary from run to run) [verified 25 November]:

| | Royale | guest | guest-ntsc | Megatron |
|---|---|---|---|---|
| Mac (M1, Metal; medians of 3 runs) | 21–29 ms | 25–29 ms | 25–31 ms | 23–32 ms |
| PC (GTX 1060, OpenGL) | 18.5 ms | 20.6 ms | 19.4 ms | 14.4 ms |

### 4.5 The `librashader-cli` fallback (Windows, and no Blender)

`librashader-cli` draws each frame in a new process, so state across frames can't carry over:

- **Megatron** has none, so the fallback is exact.
- **guest:** each frame is drawn as frame 0 of a fresh chain. The afterglow is lost, but it only acts below 8/255, and a real clip came out bit-identical with and without it [reported: `pipelines/guest_advanced/README.md`]. `render_video` says so once and goes on.
- **guest-ntsc:** the chroma phase needs the frame's parity. `librashader-cli render -f N` sets the frame count, but by drawing the same image N times [reported]. `-f (n % 2)` gives the right phase at no more than twice the cost [to test].
- **HDR10** can't use the fallback at all: `librashader-cli` 0.12.1 never passes `--color-space` to the shader [reported]. `megatron-hdr10` needs Blender.

`candidates()` sends each vendored preset to Blender, not only Royale. Any other `--preset` still goes to `librashader-cli`.

**`crt-stream` (decided 25 November):** a small Rust program in `tools/crt/crt-stream/`, built like `librashader-cli` (`install_librashader.py`). It runs on the `librashader` crate: Metal on macOS, wgpu (Vulkan, Direct3D 12) on Linux and Windows. One filter chain lives for the whole video, with raw RGBA frames in on stdin and out on stdout, as `blender_crt.py` takes them. So the feedback and the frame count are right without Blender. It sits between Blender and `librashader-cli` in `auto`. On Metal it needs the TouchDesigner project's fix to `librashader-runtime-mtl` 0.12.1 (`tools/lrs-seq/vendor/`). Without the fix, the runtime re-creates a mip-mapped pass's input target every frame, so guest's afterglow history is lost [reported].

### 4.6 slp2video

- `--crt-shader royale|guest|guest-ntsc|megatron`, with `--crt-mask` taking that shader's looks. `--crt-mask` keeps its default of `grille` for each shader:
  - guest's `grille` is a 3 px R | G | B aperture grille at strength 0.5;
  - Megatron's `grille` is the 4 px R G B X grille, so its physical-pixels mapping picks `grille3` at slp2video's 3 px pitch.
- **The settings stay** at 584×480 → 3504×2880, 6 rows per scanline, triad 3 px. Each profile's `params(ctx)` turns that into its parameters:
  - guest: `shadowMask 6`, `masksize 1`, no zoom. Its scanlines follow the source rows by themselves, and it has no aspect parameter. The squeezed 584×480 already has the picture's shape, so nothing is needed there;
  - Megatron: `mask_for_pitch(screen, 3)` gives the nearest pattern of the look's screen type. That's 3 px for the grille and slot looks, 6 px dots for the shadow mask.
- **File names:** `crt` stays Royale's grille. Others say what they are: `crt guest`, `crt megatron slot mask`, and so on.
- **Transparency** works as now: ffmpeg merges the source's alpha back after the CRT. With guest, any afterglow over transparent areas is cut off by that alpha, so it only shows where the picture is opaque (`--keep-background`, a model, or a background colour).
- **Speed** should be close to Royale's or better [estimate]. guest costs about as much per frame as Royale on Metal, and Megatron much less. The encoder sets the pace anyway [verified for Royale: `report-gpu-crt.md`].

## 5. Tests

Each test gets the shader as a parameter where it applies:

- **Vendoring:** `vendor_shaders.py check` for all presets. The closure follows unquoted paths, textures and `#reference` (unit tests on small preset strings). Each preset's files are present and unchanged.
- **Chains:** `vendor_chain.py check` for each preset, byte for byte, where `librashader-cli` is installed. Megatron's looks in `chain.json` match its display presets.
- **Settings:** each profile's parameters for slp2video's 584×480 → 3504×2880. For example, guest gets `masksize 1, mask_zoom 0`, and Megatron's `grille` at 3 px gets the 4K / 800 TVL / BGR table. Also `--mask` checking, and the old Royale strings unchanged.
- **The rewrites** (4.3), on small GLSL snippets. Each produced pass also compiles in Blender, on each backend.
- **Blender against `librashader-cli`**, per shader and per look, on a few frames at frame 0, as for Royale now: mean difference within 1/255, aiming for 0.01/255.
- **State across frames:**
  - a white-then-black clip through guest. The afterglow decays as the TouchDesigner project measured it: 222.4 → 35.7, 28.8, 22.6, … and gone after 15 frames [reported: `temporal_results.json`];
  - guest-ntsc's frames alternate their phase.

  The reference is either those numbers or `tools/lrs-seq` on the Mac (decision 5).
- **Royale is unchanged:** after the refactor, `render_video.py` and `slp2video --crt` give the same frames as before, on a clip and on the test frames.
- **CI:** `.github/workflows/crt.yml` runs the new checks and one real render per shader with `librashader-cli` on the three runners.

## 6. Where each part runs

- **The Mac (M1, Metal):** everything first. That includes the Metal rewrites (4.3), and `tools/lrs-seq` as a temporal reference if wanted.
- **The PC (Pop!_OS, GTX 1060, Blender on OpenGL):** the same tests, the OpenGL compile of every pass, and speed with NVENC and `prores_aw`.
- **Windows:** the `librashader-cli` fallback through CI only, as for Royale now. Blender on Windows still waits on the pipe handover (`subprocess` passes inherited pipes on macOS and Linux only).

## 7. Out of scope

- The TouchDesigner side: ports, builders, the suite component, the 1280 cap.
- guest's other variants: `-hd`, `-fast`, `-fastest` and `-pal`. Once the plumbing exists, each is one more preset [estimate: 0.5 day each].
- Curvature and screen shapes. guest has them built in, so they'd come with its parameters through `--crt-params`, untested.
- Megatron v1, and the other `hdr/` presets (Adamant).

## 8. Steps

| Step | What | Estimate | Where |
|---|---|---|---|
| C1 | **Vendor the shaders:** `vendor_shaders.py` for several presets (unquoted paths, textures, `#reference`), guest, guest-ntsc and Megatron's files, `MANIFEST`, licences in the README | 0.5 day | Mac |
| C2 | **Shader profiles:** `shaders.py` with Royale's current settings moved in, unchanged, and guest's and Megatron's from their `video.py`. `--shader`, `--mask` per shader, `--list-masks`. Royale's output byte-identical | 1 day | Mac |
| C3 | **Chains per preset:** `blender-chain/<shader>/`, `vendor_chain.py` for several presets, Megatron's looks in `chain.json`. The two Metal rewrites in `blender_crt.py` (4.3) | 1–1.5 days | Mac |
| C4 | **State in `blender_crt.py`:** frame count, feedback, float targets, `--warmup`. Check that guest's raster bloom is off in our looks, and if not, the mip levels (+1 day) | 1–1.5 days | Mac |
| C5 | **The fallback:** each shader through `librashader-cli`, the temporal warning, guest-ntsc's frame parity, `candidates()` for every vendored preset | 0.5 day | Mac, then CI |
| C6 | **slp2video:** `--crt-shader`, `--crt-mask` per shader, file names, tests | 0.5 day | Mac |
| C7 | **Tests and the PC:** section 5, the OpenGL compile and any rewrite it needs, speed on the GTX 1060, CI | 1–1.5 days | PC, then Mac |
| C8 | **Docs:** `tools/crt/README.md`, `docs/slp2video.md` (the CRT section, speed table, platform table), this plan's status, `docs/README.md` | 0.5 day | Anywhere |
| C9 | *Optional:* **Megatron in HDR10** (section 8.1) | 1–1.5 days | Mac with an XDR screen |

About **6.5–8 days** for C1–C8.

### 8.1 Megatron HDR10 (C9)

The shader as its author meant it: the host's HDR mode set to HDR10, paper white 700 nits, peak 1000. Its last pass then writes PQ code values in BT.2020 [reported: `pipelines/megatron/video_hdr10.py`].

- `blender_crt.py` sets the `HDRMode` and `BrightnessNits` uniforms. Today it leaves host values at the chain's defaults.
- The last target becomes `RGBA16F`, read back as floats, and piped to ffmpeg as 16-bit (`rgba64le`). 8 bits bands the PQ curve: 1.9% mean error against 0.35% at 10 bits [reported].
- The encoder tags the video BT.2020 / SMPTE ST 2084, with a `setparams` filter as the TouchDesigner project's script does. ProRes 4444 is 10 to 12 bits. HEVC 4:4:4 10-bit at CRF 4 is the `.mp4` option, with NVENC's HEVC 4:4:4 10-bit on the PC.
- The test: decode one frame back and compare it with the drawn one. The TouchDesigner project's `test_encode.py` numbers are the target (RMSE about 1.7 in 10-bit code units for ProRes at `-qscale:v 2`).
- Only worth doing if the videos are watched on an HDR screen (decision 3).

## 9. Decisions for you

1. **Which shaders, in which order.** Recommended: guest first (brighter, more looks, and it shakes out the state across frames), then Megatron SDR, then guest-ntsc. Royale stays the default.
2. **Megatron's brightness in SDR.** Keep it faithful (20–27% of the light: turn the display up), or allow a non-original lift? guest's `grille` uses mask strength 0.5 (its own default is 0.3, our `grille-soft`).
3. **HDR10 (C9):** is there an HDR screen to watch on (a MacBook Pro's XDR display)? If not, leave it out.
4. **slp2video defaults per shader.** `grille` everywhere, as in 4.6? For Megatron, `grille` at 3 px means its `grille3` pattern (R G B, no black column). Its 4 px R G B X grille can't be had at a 3 px pitch.
5. **The reference for state across frames.** Either the TouchDesigner project's measured numbers in the tests (simplest), or `tools/lrs-seq` brought into `research/` as a Mac-only tool (249 lines of Rust, plus a patched librashader Metal runtime).
6. **guest's afterglow on Windows / without Blender:** accept that it's lost, with a warning (recommended: it only acts below 8/255), or refuse guest there?
7. **Megatron's licence.** Its files carry no licence and slang-shaders has none at the top level. Vendor it anyway with a note, as `include/compat_macros.inc` is, or ask the author first?
