# The CRT presets for Blender's GPU module

What `render_video.py --runtime blender` draws: each vendored preset compiled by librashader-cli 0.12.1, as its own runtimes compile it, one folder per shader:

| Folder | Preset (in `../slang-shaders/`) | Passes |
| --- | --- | --- |
| `royale/` | `crt/crt-royale.slangp` | 12 |
| `guest/` | `crt/crt-guest-advanced.slangp` | 12 |
| `guest-ntsc/` | `crt/crt-guest-advanced-ntsc.slangp` | 19 |
| `megatron/` | `hdr/crt-sony-megatron-v2-default.slangp` | 2 |

Each folder has every pass's vertex and fragment shader as GLSL 330 (`p0.vertex.glsl`, `p0.fragment.glsl`, ...), and `chain.json`: each pass's filter, wrap mode, framebuffer format, scaling and `frame_count_mod`, the LUT textures (in `../slang-shaders/`, relative to the preset's folder), and every parameter's value in the preset. A pass whose output is read again on the next frame (guest's afterglow and average-luminance passes, as `AfterglowPassFeedback` and `AvgLumPassFeedback`) has `"feedback": true`. Megatron's `chain.json` also has `"looks"`: the parameters of its four display presets (`pvm2730`, `pvm20l4`, `pvm1910`, `mx8000`), to set on top of the default preset. They're the values the crt-royale TouchDesigner project's `display_params()` gives.

`blender_crt.py` runs them inside Blender, so this runtime needs Blender but not librashader. The files are written by `python3 tools/crt/vendor_chain.py write`, never by hand. `vendor_chain.py check` (which `test_crt.py` runs when librashader-cli is installed) compares them byte for byte with what librashader-cli writes now. Each folder is derived from its shader, so that shader's licence applies (`../slang-shaders/README.md`): GPL 2 or later for crt-royale and crt-guest-advanced; Megatron's files carry no licence.
