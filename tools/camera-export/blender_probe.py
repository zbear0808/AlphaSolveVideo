"""Runs inside Blender for `validate_camera.py blender`: import a camera export, then report where Blender's
camera puts probe points, frame by frame.

    blender -b --factory-startup --python blender_probe.py -- JOB.json

JOB: {"camera": path, "options": {scale, offset, frame_start, shake}, "probes": [[blender_frame, [x, y, z]], ...],
"out": path}. Points are in Melee's space; this script maps them the way the importer maps the camera.
"""

import json
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_melee_camera as imc  # noqa: E402


def main():
    job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    o = job.get("options", {})
    opts = imc.Options(scale=o.get("scale", 1.0), offset=tuple(o.get("offset", (0.0, 0.0, 0.0))),
                       frame_start=o.get("frame_start", 1), shake=o.get("shake", True))
    scene = bpy.context.scene
    report = imc.import_file(job["camera"], opts, scene)
    cam = bpy.data.objects[report["object"]]
    r = scene.render
    out = {"report": report,
           "scene": {"resolution": [r.resolution_x, r.resolution_y], "percentage": r.resolution_percentage,
                     "pixel_aspect": [r.pixel_aspect_x, r.pixel_aspect_y], "fps": r.fps, "fps_base": r.fps_base,
                     "frame_start": scene.frame_start, "frame_end": scene.frame_end},
           "pixels": [], "slippi_frame": {}}
    by_frame = {}
    for i, (frame, point) in enumerate(job["probes"]):
        by_frame.setdefault(frame, []).append((i, point))
    pixels = [None] * len(job["probes"])
    for frame in sorted(by_frame):
        scene.frame_set(frame)
        out["slippi_frame"][str(frame)] = int(cam["slippi_frame"])
        for i, point in by_frame[frame]:
            c = world_to_camera_view(scene, cam, imc.melee_point(point, opts))
            pixels[i] = [c.x * r.resolution_x, (1.0 - c.y) * r.resolution_y, c.z]
    out["pixels"] = pixels
    Path(job["out"]).write_text(json.dumps(out), encoding="utf-8")
    print("PROBE_DONE", len(pixels))


if __name__ == "__main__":
    main()
