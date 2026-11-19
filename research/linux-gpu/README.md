# Linux GPU measurements

Scripts behind the measurements in [`docs/plan-linux-gpu.md`](../../docs/plan-linux-gpu.md): which GPU each program of the pipeline draws on, how fast Blender renders the logo plate, where the CPU goes in a render, and how fast FFmpeg's ProRes encoders are. They were written for the Linux PC that plan describes, but take their paths from the repo and the environment. Each script's header has its options.

| Script | What it measures |
|---|---|
| `gpu_check.sh` | The GPUs and their drivers; which GPU Vulkan, EGL, Blender, ffmpeg (NVENC, Vulkan) and Dolphin use; Dolphin's camera export on each GPU against the Mac's reference. Run it after a driver change |
| `eevee_probe.py` | Inside Blender (`blender -b --factory-startup --python eevee_probe.py -- FRAMES OUT_DIR`): the GPU EEVEE draws on, and its time per frame on the startup scene |
| `sample_sweep.sh` | The logo plate on 40 frames of the reference camera export at 1, 16 and 64 EEVEE samples: what's GPU work, what isn't |
| `frame_times.py` | The time per frame in Blender's logs (`plate.py` keeps one per process) |
| `cpu_profile.sh`, `thread_sampler.py` | One clip through `slp2alpha render`, with the CPU seconds of every Dolphin and ffmpeg process and thread, from `/proc` |
| `prores_test.sh` | `prores_ks`, `prores_aw` and `prores_ks_vulkan` on a transparent render, at its size and at the CRT's 3504x2880: speed, and quality against `prores_ks` |
| `solver_encoder.sh` | 40 s of a game through `slp2alpha render`, streamed, with the solver's `prores_ks` and with `prores_aw` swapped in: the time, and each process's CPU seconds |

The GPU is chosen through the environment, which the scripts pass on: `DRI_PRIME=pci-0000_00_02_0` or `__EGL_VENDOR_LIBRARY_FILENAMES=...` for OpenGL, `MESA_VK_DEVICE_SELECT=VENDOR:DEVICE` for Vulkan. Section 8 of the plan has the table.
