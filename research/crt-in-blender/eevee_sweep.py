#!/usr/bin/env python3
"""What each EEVEE setting costs the logo plate through the moving camera, and what it changes.

    python3 research/crt-in-blender/eevee_sweep.py --out DIR [--frames 60] [--camera EXPORT.json]

Renders the first --frames frames of a camera export (default: tools/camera-export's reference, 640x528) with one
Blender process per variant: today's settings, then each change on its own. Reports the time to the first frame
(Blender starting, loading the project, compiling shaders), the median time per frame after it, and the
difference from today's frames on the logo (premultiplied colour over the pixels either plate covers: mean and
99th percentile). Needs Blender and the logo project, as plate.py finds them.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools" / "logo-stage"), str(REPO / "tools" / "slp2alpha")]
import plate  # noqa: E402
from slp2alpha import locate  # noqa: E402

REFERENCE = REPO / "tools" / "camera-export" / "reference" / "DishonestMuddyCoyote_1500-1799_characters-only_macos.json"
VARIANTS = {
    "today (16 samples)": {},
    "1 sample": {"taa_render_samples": 1},
    "no shadows": {"use_shadows": False},
    "shadows at half resolution": {"shadow_resolution_scale": 0.5},
    "shadow steps 6 -> 2": {"shadow_step_count": 2},
    "no fast GI": {"use_fast_gi": False},
    "fast GI at quarter resolution": {"fast_gi_resolution": "4"},
    "no ray tracing": {"use_raytracing": False},
    "no shadows, no ray tracing": {"use_shadows": False, "use_raytracing": False},
}
DIFF = r"""
import subprocess, sys
import numpy as np
ff, a, b = sys.argv[1:4]
def load(p):
    raw = subprocess.run([ff, "-v", "error", "-i", p, "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True,
                         check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 4).astype(np.float64)
x, y = load(a), load(b)
px, py = x[:, :3] * x[:, 3:] / 255, y[:, :3] * y[:, 3:] / 255
m = (x[:, 3] > 0) | (y[:, 3] > 0)
d = np.abs(px - py)[m]
print(f"{d.mean():.3f} {np.percentile(d, 99):.1f}")
"""
SAVED = re.compile(r"^(\d+):(\d+\.\d+)\s+render\s+\| Saved:", re.M)


def frame_times(log: Path):
    stamps = [int(m) * 60 + float(s) for m, s in SAVED.findall(log.read_text(encoding="utf-8", errors="replace"))]
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    return (stamps[0] if stamps else None), (statistics.median(gaps) if gaps else None), len(stamps)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--camera", default=str(REFERENCE))
    ap.add_argument("--only", nargs="*", help="variant names to run (default: all)")
    ap.add_argument("--style", default="metal", choices=("metal", "cel"))
    a = ap.parse_args()
    out = Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg = locate.find_ffmpeg()
    blender = plate.find_blender()
    bpy_python = subprocess.run([blender, "-b", "--factory-startup", "--python-expr",
                                 "import sys; print('BPY', sys.executable)"], capture_output=True,
                                encoding="utf-8").stdout
    bpy_python = re.search(r"^BPY (.+)$", bpy_python, re.M).group(1)
    (out / "diff.py").write_text(DIFF, encoding="utf-8")
    _, size = plate.camera_export_frames(Path(a.camera))
    project = plate.find_project()
    rows = []
    for i, (name, eevee) in enumerate(VARIANTS.items()):
        if a.only and name not in a.only and i:
            continue
        folder = out / f"v{i}"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        job = plate.make_job(2, a.style, 1, folder, size=size, camera_export=Path(a.camera), samples=16, eevee=eevee)
        log = out / f"v{i}.log"
        t0 = time.monotonic()
        plate.run_blender(dict(job, frames=[1, a.frames]), project, blender, log=log)
        wall = time.monotonic() - t0
        first, per_frame, saved = frame_times(log)
        row = dict(variant=name, eevee=eevee, frames=saved, wall=round(wall, 1), first_frame_at=first,
                   per_frame=round(per_frame, 3) if per_frame else None)
        if i:
            diffs = []
            for n in (1, a.frames // 2, a.frames):
                ref, got = out / "v0" / f"{n:06d}.png", folder / f"{n:06d}.png"
                res = subprocess.run([bpy_python, str(out / "diff.py"), ffmpeg, str(ref), str(got)],
                                     capture_output=True, encoding="utf-8", check=True).stdout.split()
                diffs.append((float(res[0]), float(res[1])))
            row["mean_on_logo"] = round(max(d[0] for d in diffs), 3)
            row["p99_on_logo"] = max(d[1] for d in diffs)
        print(json.dumps(row), flush=True)
        rows.append(row)
    (out / "eevee_sweep.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print("\n| Variant | First frame at | Per frame | Mean on the logo (worst of 3 frames) | 99th percentile |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['variant']} | {r['first_frame_at']:.1f} s | {r['per_frame'] * 1000:.0f} ms | "
              f"{r.get('mean_on_logo', 'reference')} | {r.get('p99_on_logo', '')} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
