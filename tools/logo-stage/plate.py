"""Render the logo plate for a stage: the logo as that stage's fixed Melee camera sees it, sized and placed to the stage.

    python3 tools/logo-stage/plate.py STAGE [--style metal|cel] [--scale 1] [--out FILE.png]
        [--fit bbox|letters] [--ground xheight|top] [--depth-shift 0] [--logo-project FILE.blend] [--iso ISO]

STAGE is a name or id (`python3 tools/logo-stage/stagedata.py` lists them). The plate is a transparent PNG the size
of a recording at that --scale (640 x 528 at 1). Layer it under a `--characters-only --static-camera` render.

How the logo is fitted to the stage (everything comes from the stage's .dat file, see stagedata.py):

  width    the logo's width is the stage's width from ledge to ledge (hearts included: --fit bbox), or the width of
           the letters g..i only (--fit letters, the hearts then stick out past the ledges)
  height   the logo's ground line sits on the stage's top surface. --ground xheight (default) puts the tops of the
           x-height letters there, the line fighters will stand on; --ground top uses the highest point (the d and
           the dot of the i), so the letters sit lower
  depth    the middle of the logo's thickness is the plane the fighters move in (z = 0); --depth-shift 1 puts its
           front face there instead (-1 the back)
  camera   the stage's own fixed camera (eye, field of view, tilt), looking at the logo the way it looks at the stage

The look comes from the user's Blender project (default ~/Documents/logo_metal_fracture/logo_metal_fracture.blend,
scene SH010_Reveal): `metal` is its polished scratched steel under the studio lights, `cel` is the flat toon finish
from ~/Documents/kitty_logo_crash (hard colour bands, an ink outline) that matches Animelee's flat style.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
import projection  # noqa: E402
import stagedata  # noqa: E402
from slp2alpha import locate  # noqa: E402

DEFAULT_PROJECT = Path(os.environ.get("LOGO_STAGE_PROJECT",
                       Path.home() / "Documents" / "logo_metal_fracture" / "logo_metal_fracture.blend"))
BLENDER_APP = Path("/Applications/Blender.app/Contents/MacOS/Blender")
SCENE = "SH010_Reveal"
STYLES = ("metal", "cel")


def _windows_blenders() -> list:
    """Blender's Windows installs (C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe), newest first."""
    if os.name != "nt":
        return []
    root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    found = [p for p in root.glob("Blender*/blender.exe") if p.is_file()]

    def version(p: Path):
        digits = p.parent.name.replace("Blender", "").strip().split(".")
        return [int(d) if d.isdigit() else 0 for d in digits]

    return [str(p) for p in sorted(found, key=version, reverse=True)]


def find_blender(explicit: Optional[str] = None) -> str:
    for c in (explicit, os.environ.get("BLENDER"), str(BLENDER_APP), *_windows_blenders(), shutil.which("blender")):
        if c and Path(c).exists():
            return str(c)
    raise locate.NotFound("Blender not found: install it, or pass --blender PATH / set BLENDER")


def find_project(explicit: Optional[str] = None) -> Path:
    p = Path(explicit).expanduser() if explicit else DEFAULT_PROJECT
    if not p.exists():
        raise locate.NotFound(f"logo Blender project not found: {p} (pass --logo-project FILE.blend or set LOGO_STAGE_PROJECT)")
    return p


def camera_of(geo: "stagedata.StageGeometry") -> projection.Camera:
    c = geo.camera
    return projection.from_ground_param(c.eye, c.fov_deg, c.vert_angle_deg, c.horz_angle_deg)


def stage_probes(geo: "stagedata.StageGeometry") -> Dict[str, Tuple[float, float, float]]:
    m = geo.main_stage
    return {"ledge_left": (m.ledge_left[0], m.ledge_left[1], 0.0), "ledge_right": (m.ledge_right[0], m.ledge_right[1], 0.0),
            "top_left": (m.top_x[0], m.top_y, 0.0), "top_right": (m.top_x[1], m.top_y, 0.0),
            "origin": (0.0, 0.0, 0.0)}


def make_job(stage: int, style: str, scale: int, out: Path, *, iso: Optional[str] = None, fit_to: str = "bbox",
             ground_line: str = "xheight", ground_offset: float = 0.0, depth_shift: float = 0.0,
             outline_px: Optional[float] = None, samples: Optional[int] = None, frame: int = 1,
             render: bool = True, report: Optional[Path] = None) -> dict:
    geo = stagedata.load_stage(stage, iso)
    m = geo.main_stage
    left, right = m.ledge_left[0], m.ledge_right[0]
    c = geo.camera
    return {
        "out": str(out), "style": style, "scale": scale, "frame": frame, "render": render,
        "camera": {"eye": list(c.eye), "fov": c.fov_deg, "vert": c.vert_angle_deg, "horz": c.horz_angle_deg,
                   "aspect": projection.ASPECT},
        "fit": {"width": right - left, "center_x": 0.5 * (left + right), "to": fit_to},
        "ground": {"y": m.top_y, "line": ground_line, "offset": ground_offset},
        "depth_shift": depth_shift, "outline_px": outline_px, "samples": samples,
        "probes": {k: list(v) for k, v in stage_probes(geo).items()},
        "report": str(report) if report else None,
    }


def run_blender(job: dict, project: Path, blender: Optional[str] = None, log: Optional[Path] = None) -> dict:
    """Run blender_plate.py on the project for one job; returns the report the script prints."""
    exe = find_blender(blender)
    with tempfile.TemporaryDirectory(prefix="logo-plate-") as tmp:
        job_file = Path(tmp) / "job.json"
        job_file.write_text(json.dumps(job), encoding="utf-8")
        cmd = [exe, "-b", "--factory-startup", str(project), "-S", SCENE, "-noaudio", "--python",
               str(HERE / "blender_plate.py"), "--", str(job_file)]
        done = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if log:
        log.write_text(done.stdout + "\n--- stderr ---\n" + done.stderr, encoding="utf-8")
    report = None
    for line in done.stdout.splitlines():
        if line.startswith("PLATE_REPORT "):
            report = json.loads(line[len("PLATE_REPORT "):])
    if done.returncode != 0 or report is None:
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-25:])
        raise RuntimeError(f"Blender failed (exit {done.returncode}, no report printed):\n{tail}")
    return report


def render_plate(stage: int, style: str, scale: int, out: Path, **kw) -> dict:
    blender, project = kw.pop("blender", None), find_project(kw.pop("logo_project", None))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    job = make_job(stage, style, scale, out, **kw)
    report = run_blender(job, project, blender)
    if job["render"] and not out.exists():
        raise RuntimeError(f"Blender did not write {out}")
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stage", help="stage name or id")
    ap.add_argument("--style", choices=STYLES, default="metal")
    ap.add_argument("--scale", type=int, default=1, help="recording scale (--scale of slp2alpha): 640x528 at 1")
    ap.add_argument("--out", help="PNG to write (default: plate-<stage>-<style>-<scale>x.png here)")
    ap.add_argument("--fit", choices=("bbox", "letters"), default="bbox")
    ap.add_argument("--ground", choices=("xheight", "top"), default="xheight")
    ap.add_argument("--ground-offset", type=float, default=0.0, help="Melee units to raise the logo above the stage top (negative: sink it)")
    ap.add_argument("--depth-shift", type=float, default=0.0,
                    help="where the fighters' plane cuts the logo's thickness: 0 middle, 1 front face, -1 back")
    ap.add_argument("--outline-px", type=float, help="cel outline width in pixels (default: 1 per scale step)")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--no-render", action="store_true", help="only report the camera mapping")
    ap.add_argument("--logo-project")
    ap.add_argument("--blender")
    ap.add_argument("--iso")
    args = ap.parse_args(argv)
    stage = stagedata.find_stage(args.stage)
    name = stagedata.STAGE_FILES[stage][0].lower().replace(" ", "-").replace("'", "").replace("é", "e")
    out = Path(args.out) if args.out else Path.cwd() / f"plate-{name}-{args.style}-{args.scale}x.png"
    report = render_plate(stage, args.style, args.scale, out, iso=args.iso, fit_to=args.fit, ground_line=args.ground,
                          ground_offset=args.ground_offset, depth_shift=args.depth_shift, outline_px=args.outline_px,
                          samples=args.samples, render=not args.no_render, blender=args.blender,
                          logo_project=args.logo_project)
    print(json.dumps(report, indent=1))
    if not args.no_render:
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (locate.NotFound, RuntimeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
