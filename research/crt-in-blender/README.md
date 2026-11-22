# CRT Royale inside Blender

Can CRT Royale run inside Blender, so that `slp2video --crt` keeps the preset loaded for a whole video instead of starting `librashader-cli` for every frame? Yes, through Blender's `gpu` module in the background. The findings, and what they mean for the pipeline, are in [`docs/plan-gpu-crt-model.md`](../../docs/plan-gpu-crt-model.md) section 3.

| File | |
|---|---|
| `prep_chain.py` | Asks `librashader-cli` for the preset once: each pass as GLSL 330, the passes' filters, wrap modes, formats and scaling, the parameters' defaults, the mask textures as raw RGBA. Writes a folder for `blender_crt.py` |
| `blender_crt.py` | Inside Blender (`blender -b --python blender_crt.py -- ...`): librashader's filter chain rebuilt on `gpu.types` (shaders, uniform blocks, framebuffers). Raw RGBA frames in, raw RGBA frames out (a file, a pipe to ffmpeg, or `/dev/null`). Prints the time each part takes |
| `frame_diff.py` | How far apart two raw frames are: mean, largest, PSNR |
| `compare.sh` | Everything at once on a clip: Blender's frames against `librashader-cli`'s for each mask, then the frames per second alone, into each encoder there is, and of today's `render_video.render` |

```sh
research/crt-in-blender/compare.sh CLIP.mp4 120                     # the Mac
GPU_BACKEND=opengl FFMPEG=.../ffmpeg-8.1/bin/ffmpeg \
  VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json \
  research/crt-in-blender/compare.sh CLIP.mp4 120                     # the Linux PC: NVENC needs FFmpeg 8.1
```

On a Linux machine without a desktop session, unset `DISPLAY` and `WAYLAND_DISPLAY`; Blender's OpenGL backend then runs through EGL.

## Results, 22 November 2026

120 frames of a 4-player clip, squeezed to 584x480 and drawn at 3504x2880 (`slp2video --crt`'s size for regular Melee):

| | Mac M1, Blender 5.2.3 on Metal | Linux PC, GTX 1060, driver 580, Blender 5.2.3 on OpenGL |
|---|---|---|
| Compiling the preset (once) | 0.07 s | 0.12 s |
| A frame: upload and draw, read-back | 3 ms, 24 ms | 5 ms, 38 ms |
| Frames/s, no encoder | 36.6 | 23.3 |
| Frames/s into ProRes 4444 | 12.5 (Apple's encoder) | 6.4 (`prores_aw`) |
| Frames/s into NVENC 4:4:4 | — | 9.7 (H.264), 8.3 (HEVC), 8.4 (HEVC and a matte file) |
| Today's `render_video.render`, ProRes 4444 | 4.3 | 0.7 (`prores_ks`) |
| Today's `render_video.render`, H.264 4:4:4 (`libx264`) | 2.7 | 1.5 |
| Mean difference from `librashader-cli`, 3 frames by 3 masks | 0.82–1.71/255 (against Metal) | 1.02–1.68/255 (against wgpu, same GPU) |

On the PC, Blender's Vulkan backend drew a frame in 43 ms instead of 26, and compiled in 4.8 s instead of 1.3. All 12 passes compile on OpenGL and Vulkan as librashader writes them. On Metal, one line of the last pass needs a rewrite (copying a whole array), which `blender_crt.py` does.

Not done yet: mip levels (Blender's Python can't build them; crt-royale's last pass reads its input with them), alpha, and writing frames from a second thread.
