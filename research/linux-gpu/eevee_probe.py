"""EEVEE probe: which GPU Blender renders on, and how fast, in the background.

    blender -b --factory-startup --python eevee_probe.py -- FRAMES OUT_DIR [WIDTH HEIGHT SAMPLES]

Renders the startup scene (a cube, a light, a camera) with the cube turning, as RGBA PNGs at 640x528 and 16 EEVEE
samples by default, the moving-camera plate's settings. Prints the GPU and the time per frame after the first.
"""
import sys
import time

import bpy
import gpu

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
frames = int(argv[0]) if argv else 10
out_dir = argv[1] if len(argv) > 1 else "/tmp/eevee-probe"
width, height, samples = (int(v) for v in argv[2:5]) if len(argv) >= 5 else (640, 528, 16)


def gpu_info() -> str:
    try:
        return (f"{gpu.platform.backend_type_get()} | {gpu.platform.vendor_get()} | {gpu.platform.renderer_get()} | "
                f"{gpu.platform.version_get()} | device {gpu.platform.device_type_get()}")
    except SystemError as e:  # in the background the GPU starts with the first render
        return f"not started yet ({e})"


scene = bpy.context.scene
for name in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
    try:
        scene.render.engine = name
        break
    except TypeError:
        continue
scene.eevee.taa_render_samples = samples
r = scene.render
r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, 100
r.film_transparent = True
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"
r.filepath = f"{out_dir}/frame_####"
scene.frame_start, scene.frame_end = 1, frames

cube = bpy.data.objects["Cube"]
cube.rotation_euler = (0.0, 0.0, 0.0)
cube.keyframe_insert("rotation_euler", frame=1)
cube.rotation_euler = (0.0, 0.0, 3.14159)
cube.keyframe_insert("rotation_euler", frame=frames)

stamps = []
bpy.app.handlers.render_post.append(lambda *_: stamps.append(time.monotonic()))
t0 = time.monotonic()
bpy.ops.render.render(animation=True)
total = time.monotonic() - t0
after_first = (stamps[-1] - stamps[0]) / (len(stamps) - 1) if len(stamps) > 1 else float("nan")
print(f"GPU: {gpu_info()}", flush=True)
print(f"RESULT: {scene.render.engine}, {width}x{height}, {samples} samples: {len(stamps)} frames in {total:.1f} s; "
      f"first frame {stamps[0] - t0:.1f} s, then {after_first:.3f} s a frame ({1 / after_first:.1f} frames/s)",
      flush=True)
