"""Render the logo plate for a stage: the logo as that stage's fixed Melee camera sees it, sized and placed to the stage.

    python3 tools/logo-stage/plate.py STAGE [--style metal|cel|original] [--scale 1] [--out FILE.png]
        [--fit bbox|letters] [--ground xheight|top] [--depth-shift 0] [--logo-project FILE.blend] [--iso ISO]
        [--model FILE [--object NAME] [--rotation DEG] [--model-scale 1]] [--raw-resolution]
        [--camera-export "camera - NAME.json" [--jobs 2]]

STAGE is a name or id (`python3 tools/logo-stage/stagedata.py` lists them). The plate is a transparent PNG the size
of a recording at that --scale (640 x 528 at 1; 640 x 480 with --raw-resolution). Layer it under a
`--characters-only --static-camera` render.

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

--model draws your own model instead, fitted the same way (its parts together; --ground top by default): a .blend
(its visible objects, or --object NAME), or a .glb/.gltf, .fbx, .obj, .stl, .ply, .usd/.usdz or .abc file. It keeps
its own materials (`original`) or gets the `cel` finish. A model without lights gets a key, a fill and a rim light.

--camera-export renders the plate through the game's moving camera instead (`slp2alpha render --export-camera`):
one PNG per video frame, 000001.png..., in the folder --out, the size of that recording.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
import projection  # noqa: E402
import stagedata  # noqa: E402
from slp2alpha import locate  # noqa: E402

DEFAULT_PROJECT = Path(os.environ.get("LOGO_STAGE_PROJECT",
                       Path.home() / "Documents" / "logo_metal_fracture" / "logo_metal_fracture.blend"))
BLENDER_APP = locate.BLENDER_APP
SCENE = "SH010_Reveal"
STYLES = ("metal", "cel", "original")
# What blender_plate.py opens or imports (blender_plate.IMPORTERS has the importers).
MODEL_FORMATS = (".blend", ".glb", ".gltf", ".fbx", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc", ".usdz", ".abc")


def find_blender(explicit: Optional[str] = None) -> str:
    return locate.find_blender(explicit)


def find_project(explicit: Optional[str] = None) -> Path:
    p = Path(explicit).expanduser() if explicit else DEFAULT_PROJECT
    if not p.exists():
        raise locate.NotFound(f"logo Blender project not found: {p} (pass --logo-project FILE.blend or set LOGO_STAGE_PROJECT)")
    return p


def find_model(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise locate.NotFound(f"model not found: {p}")
    if p.suffix.lower() not in MODEL_FORMATS:
        raise ValueError(f"{p.name}: Blender can't read {p.suffix or 'files without an extension'} here; "
                         f"use one of {', '.join(MODEL_FORMATS)}")
    return p


def check_style(style: str, model: bool) -> None:
    if style == "metal" and model:
        raise ValueError("the metal finish is the logo project's own; a model keeps its materials (original) or "
                         "gets the cel finish")
    if style == "original" and not model:
        raise ValueError("the logo's own finish is metal (or cel)")


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
             render: bool = True, report: Optional[Path] = None, size: Optional[Tuple[int, int]] = None,
             raw: bool = False, model: Optional[Path] = None, model_objects: Sequence[str] = (),
             model_rotation=0.0, model_scale: float = 1.0,
             camera_export: Optional[Path] = None) -> dict:
    """size: the recording's (width, height), by default what Dolphin records at `scale` (raw: unstretched).
    model_rotation: degrees about the vertical, or [x, y, z] Euler angles in degrees."""
    geo = stagedata.load_stage(stage, iso)
    m = geo.main_stage
    left, right = m.ledge_left[0], m.ledge_right[0]
    c = geo.camera
    width, height = size or projection.recording_size(scale, raw)
    job = {
        "out": str(Path(out).resolve()), "style": style, "scale": scale, "size": [int(width), int(height)],
        "frame": frame, "render": render,
        # the look-at point as the game computes it (its polynomial sine), which --static-camera really uses
        "camera": {"eye": list(c.eye), "fov": c.fov_deg, "vert": c.vert_angle_deg, "horz": c.horz_angle_deg,
                   "aspect": projection.ASPECT,
                   "interest": list(projection.game_interest(c.eye, c.vert_angle_deg, c.horz_angle_deg))},
        "fit": {"width": right - left, "center_x": 0.5 * (left + right), "to": fit_to, "scale": model_scale},
        "ground": {"y": m.top_y, "line": ground_line, "offset": ground_offset},
        "depth_shift": depth_shift, "outline_px": outline_px, "samples": samples,
        "probes": {k: list(v) for k, v in stage_probes(geo).items()},
        "report": str(report) if report else None,
    }
    if model:
        job["model"] = {"path": str(model), "objects": list(model_objects), "rotation": model_rotation}
    if camera_export:
        job["camera_export"] = str(Path(camera_export).resolve())
    return job


def job_key(job: dict, source: Path) -> str:
    """Everything a plate depends on: the job (camera, fit, style, size...), the logo project or model file, the code."""
    spec = {k: v for k, v in job.items() if k not in ("out", "report", "render")}
    stat = source.stat()
    code = b"".join((HERE / n).read_bytes() for n in ("blender_plate.py", "projection.py"))
    blob = json.dumps(spec, sort_keys=True).encode() + f"{source.resolve()}:{stat.st_size}:{int(stat.st_mtime)}".encode() + code
    return hashlib.sha1(blob).hexdigest()[:12]


def blender_command(exe: str, job: dict, project: Optional[Path], job_file: Path) -> List[str]:
    """How Blender starts for a job: the logo project at its scene, a model's own .blend, or the empty startup
    scene that blender_plate.py imports a model into."""
    script = ["-noaudio", "--python", str(HERE / "blender_plate.py"), "--", str(job_file)]
    model = job.get("model")
    if not model:
        return [exe, "-b", "--factory-startup", str(project), "-S", SCENE] + script
    if Path(model["path"]).suffix.lower() == ".blend":
        return [exe, "-b", "--factory-startup", model["path"]] + script
    return [exe, "-b", "--factory-startup"] + script


def check_report(report: dict, tolerance_px: float = 0.01) -> None:
    """Blender's own projection of the stage's ledges, top and origin must be where the game's camera puts them:
    otherwise the plate wouldn't line up with the fighters."""
    worst = max((abs(a - b) for name, want in report.get("probes_melee_px", {}).items()
                 for a, b in zip(want, report["probes_blender_px"][name])), default=0.0)
    if worst > tolerance_px:
        raise RuntimeError(f"Blender's camera is {worst:.3f} px off the game's ({report.get('size')}, pixel aspect "
                           f"{report.get('pixel_aspect')}): the plate wouldn't line up")


def run_blender(job: dict, project: Optional[Path], blender: Optional[str] = None, log: Optional[Path] = None) -> dict:
    """Run blender_plate.py for one job; returns the report the script prints. project: the logo's Blender
    project (not used for a job with a model)."""
    exe = find_blender(blender)
    with tempfile.TemporaryDirectory(prefix="logo-plate-") as tmp:
        job_file = Path(tmp) / "job.json"
        job_file.write_text(json.dumps(job), encoding="utf-8")
        done = subprocess.run(blender_command(exe, job, project, job_file), capture_output=True, encoding="utf-8",
                              errors="replace")
    if log:
        log.write_text(done.stdout + "\n--- stderr ---\n" + done.stderr, encoding="utf-8")
    report = None
    for line in done.stdout.splitlines():
        if line.startswith("PLATE_REPORT "):
            report = json.loads(line[len("PLATE_REPORT "):])
    if done.returncode != 0 or report is None:
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-25:])
        raise RuntimeError(f"Blender failed (exit {done.returncode}, no report printed):\n{tail}")
    check_report(report)
    return report


def render_plate(stage: int, style: str, scale: int, out: Path, **kw) -> dict:
    blender, logo_project = kw.pop("blender", None), kw.pop("logo_project", None)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    job = make_job(stage, style, scale, out, **kw)
    project = None if job.get("model") else find_project(logo_project)
    report = run_blender(job, project, blender)
    if job["render"] and not out.exists():
        raise RuntimeError(f"Blender did not write {out}")
    return report


def camera_export_frames(path: Path) -> Tuple[int, Tuple[int, int]]:
    """The video frames a camera export is for (one more than its samples when the game's last frame has none),
    and the recording's size."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    frames = max(int(doc["frames"]["count"]), int(doc["frames"].get("video") or 0))
    return frames, (int(doc["render"]["width"]), int(doc["render"]["height"]))


def chunks(total: int, jobs: int) -> List[Tuple[int, int]]:
    """Frames 1..total in `jobs` runs of consecutive frames, as (first, last)."""
    jobs = max(1, min(jobs, total))
    bounds = [1 + round(i * total / jobs) for i in range(jobs + 1)]
    return [(bounds[i], bounds[i + 1] - 1) for i in range(jobs)]


def render_sequence(stage: int, style: str, scale: int, folder: Path, camera_export: Path, *, jobs: int = 1,
                    on_progress: Optional[Callable[[int, int], None]] = None, **kw) -> int:
    """The plate through the game's moving camera: folder/000001.png for the first video frame of the camera
    export, and so on. `jobs` Blender processes share the frames. Returns the number of frames."""
    blender, logo_project = kw.pop("blender", None), kw.pop("logo_project", None)
    total, size = camera_export_frames(camera_export)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    job = make_job(stage, style, scale, folder, size=size, camera_export=camera_export, **kw)
    project = None if job.get("model") else find_project(logo_project)
    errors: List[BaseException] = []

    def run(first: int, last: int, n: int) -> None:
        try:
            run_blender(dict(job, frames=[first, last]), project, blender, log=folder.parent / f"blender-{n}.log")
        except BaseException as e:  # reported once every process has stopped
            errors.append(e)

    threads = [threading.Thread(target=run, args=(a, b, n), daemon=True)
               for n, (a, b) in enumerate(chunks(total, jobs))]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        time.sleep(1.0)
        if on_progress:
            on_progress(len(list(folder.glob("*.png"))), total)
    if errors:
        raise errors[0]
    missing = [f for f in range(1, total + 1) if not (folder / f"{f:06d}.png").exists()]
    if missing:
        raise RuntimeError(f"Blender left {len(missing)} of {total} frames unrendered (first: {missing[0]})")
    if on_progress:
        on_progress(total, total)
    return total


def rotation(text: str):
    """--rotation: DEG about the vertical, or X,Y,Z Euler angles in degrees."""
    parts = [float(p) for p in str(text).split(",")]
    if len(parts) not in (1, 3):
        raise argparse.ArgumentTypeError("give DEG, or X,Y,Z in degrees")
    return parts[0] if len(parts) == 1 else parts


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stage", help="stage name or id")
    ap.add_argument("--style", choices=STYLES, help="metal (the logo's default), original (a model's default) or cel")
    ap.add_argument("--scale", type=int, default=1, help="recording scale (--scale of slp2alpha): 640x528 at 1")
    ap.add_argument("--raw-resolution", action="store_true", help="the size of a --raw-resolution recording (640x480 at 1)")
    ap.add_argument("--out", help="PNG to write (default: plate-<stage>-<style>-<scale>x.png here); a folder with "
                                  "--camera-export")
    ap.add_argument("--fit", choices=("bbox", "letters"), default="bbox")
    ap.add_argument("--ground", choices=("xheight", "top"),
                    help="the line that is the stage's top (default: xheight for the logo, top for a model)")
    ap.add_argument("--ground-offset", type=float, default=0.0, help="Melee units to raise the logo above the stage top (negative: sink it)")
    ap.add_argument("--depth-shift", type=float, default=0.0,
                    help="where the fighters' plane cuts the logo's thickness: 0 middle, 1 front face, -1 back")
    ap.add_argument("--outline-px", type=float, help="cel outline width in pixels (default: 1 per scale step)")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--no-render", action="store_true", help="only report the camera mapping")
    ap.add_argument("--model", help="your own model instead of the logo (.blend, .glb, .fbx, .obj, ...)")
    ap.add_argument("--object", action="append", default=[], help="with a .blend model: draw only this object "
                                                                  "(repeat for more)")
    ap.add_argument("--rotation", type=rotation, default=0.0,
                    help="turn the model first: DEG about the vertical, or X,Y,Z degrees (e.g. 90,0,0 stands up a "
                         "model lying on its back)")
    ap.add_argument("--model-scale", type=float, default=1.0, help="the model's width in stage widths (ledge to ledge)")
    ap.add_argument("--camera-export", help="camera - NAME.json: render every frame through the game's moving camera")
    ap.add_argument("--jobs", type=int, default=1, help="Blender processes sharing a --camera-export's frames")
    ap.add_argument("--logo-project")
    ap.add_argument("--blender")
    ap.add_argument("--iso")
    args = ap.parse_args(argv)
    stage = stagedata.find_stage(args.stage)
    model = find_model(args.model) if args.model else None
    style = args.style or ("original" if model else "metal")
    check_style(style, model is not None)
    name = stagedata.STAGE_FILES[stage][0].lower().replace(" ", "-").replace("'", "").replace("é", "e")
    kw = dict(iso=args.iso, fit_to=args.fit, ground_line=args.ground or ("top" if model else "xheight"),
              ground_offset=args.ground_offset, depth_shift=args.depth_shift, outline_px=args.outline_px,
              samples=args.samples, blender=args.blender, logo_project=args.logo_project, model=model,
              model_objects=args.object, model_rotation=args.rotation, model_scale=args.model_scale)
    if args.camera_export:
        folder = Path(args.out) if args.out else Path.cwd() / f"plate-{name}-{style}-frames"

        def progress(done: int, total: int) -> None:
            sys.stderr.write(f"\r  Blender: {done}/{total} frames   ")

        total = render_sequence(stage, style, args.scale, folder, Path(args.camera_export), jobs=args.jobs,
                                on_progress=progress, **kw)
        print(f"\nwrote {total} frames to {folder}")
        return 0
    out = Path(args.out) if args.out else Path.cwd() / f"plate-{name}-{style}-{args.scale}x.png"
    report = render_plate(stage, style, args.scale, out, render=not args.no_render, raw=args.raw_resolution, **kw)
    print(json.dumps(report, indent=1))
    if not args.no_render:
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (locate.NotFound, RuntimeError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
