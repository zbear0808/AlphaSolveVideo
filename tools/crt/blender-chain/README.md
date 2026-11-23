# crt-royale for Blender's GPU module

What `render_video.py --runtime blender` draws: the vendored preset `../slang-shaders/crt/crt-royale.slangp` compiled by librashader-cli 0.12.1, as its own runtimes compile it. Each pass's vertex and fragment shader as GLSL 330 (`p0.vertex.glsl` ... `p11.fragment.glsl`), and `chain.json`: each pass's filter, wrap mode, framebuffer format and scaling, the mask textures (in `../slang-shaders/`), and every parameter's default.

`blender_crt.py` runs them inside Blender, so this runtime needs Blender but not librashader. The files are written by `python3 tools/crt/vendor_chain.py write`, never by hand. `vendor_chain.py check` (which `test_crt.py` runs when librashader-cli is installed) compares them byte for byte with what librashader-cli writes now. They're derived from crt-royale, so its licence applies (`../slang-shaders/crt/shaders/crt-royale/LICENSE.TXT`, GPL 2 or later).
