"""Put the logo in place of the stage: render a replay's fighters and lay them over the logo, sized to the stage.

    python3 tools/logo-stage/logo_stage.py REPLAY.slp [--animelee] [--scale 2] [--start-frame N --end-frame M]
        [--out-dir DIR] [--format mov|mp4] [--background HEX] [--keep-intermediates] [-- slp2alpha options]

What it does, for any of the six legal stages:

  1. reads the replay's stage and that stage's fixed camera, ledges and top surface from the ISO (stagedata.py);
  2. renders the logo as that camera sees it, its width ledge to ledge and its ground line on the stage top
     (plate.py + Blender): polished scratched metal normally, the flat cel finish with an ink outline with --animelee;
  3. renders the fighters with `slp2alpha render --characters-only --static-camera` (same --scale, --animelee);
  4. composites the two (composite.py): the plate under the fighters, the alpha kept (ProRes 4444).

The plate is cached (~/Library/Caches/AlphaSolveVideo/logo-stage/), so a second replay on the same stage at the same
scale only needs step 3. Options after a lone `--` go to `slp2alpha render` (e.g. `-- --hide-effects`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
import composite  # noqa: E402
import plate  # noqa: E402
import stagedata  # noqa: E402
from slp2alpha import locate, slp  # noqa: E402

SLP2ALPHA_DIR = HERE.parent / "slp2alpha"
_BASE = (Path.home() / "Library" / "Caches" if sys.platform == "darwin"
         else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")))
CACHE = _BASE / "AlphaSolveVideo" / "logo-stage" / "plates"


def plate_key(job: dict, project: Path) -> str:
    """Everything the picture depends on: the job (camera, fit, style, scale...), the look in the Blender project, the code."""
    spec = {k: v for k, v in job.items() if k not in ("out", "report", "render")}
    stat = project.stat()
    code = b"".join((HERE / n).read_bytes() for n in ("blender_plate.py", "projection.py"))
    blob = json.dumps(spec, sort_keys=True).encode() + f"{project.resolve()}:{stat.st_size}:{int(stat.st_mtime)}".encode() + code
    return hashlib.sha1(blob).hexdigest()[:12]


def get_plate(stage: int, style: str, scale: int, *, iso: Optional[str], logo_project: Optional[str], blender: Optional[str],
              use_cache: bool = True, **options) -> Path:
    project = plate.find_project(logo_project)
    job = plate.make_job(stage, style, scale, Path("plate.png"), iso=iso, **options)
    name = stagedata.STAGE_FILES[stage][0].lower().replace(" ", "-").replace("'", "").replace("é", "e")
    path = CACHE / f"{name}-{style}-{scale}x-{plate_key(job, project)}.png"
    if use_cache and path.exists():
        print(f"plate: {path.name} (cached)")
        return path
    t0 = time.monotonic()
    plate.render_plate(stage, style, scale, path, iso=iso, blender=blender, logo_project=logo_project, **options)
    print(f"plate: {path.name} rendered in {time.monotonic() - t0:.0f} s")
    return path


def run_slp2alpha(replay: Path, out_dir: Path, args: argparse.Namespace, passthrough: List[str]) -> Path:
    cmd = [sys.executable, "-m", "slp2alpha", "render", str(replay), "--characters-only", "--static-camera",
           "--scale", str(args.scale), "--format", "mov", "--out-dir", str(out_dir)]
    if args.animelee:
        cmd.append("--animelee")
    if args.start_frame is not None:
        cmd += ["--start-frame", str(args.start_frame)]
    if args.end_frame is not None:
        cmd += ["--end-frame", str(args.end_frame)]
    for opt, value in (("--dolphin", args.dolphin), ("--iso", args.iso), ("--ffmpeg", args.ffmpeg)):
        if value:
            cmd += [opt, value]
    cmd += passthrough
    proc = subprocess.run(cmd, cwd=SLP2ALPHA_DIR, stdout=subprocess.PIPE, text=True)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        raise RuntimeError(f"slp2alpha render failed (exit {proc.returncode})")
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("/") and Path(line).name.startswith("fullTransparent - ") and Path(line).exists():
            return Path(line)
    found = sorted(out_dir.glob("fullTransparent - *.mov"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise RuntimeError("slp2alpha render wrote no transparent video")
    return found[-1]


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    passthrough: List[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, passthrough = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay")
    ap.add_argument("--animelee", action="store_true", help="Animelee skins for the fighters and the cel-shaded logo")
    ap.add_argument("--scale", type=int, default=1, choices=(1, 2, 3, 4), help="recording scale (1 = 640x528)")
    ap.add_argument("--start-frame", type=int)
    ap.add_argument("--end-frame", type=int)
    ap.add_argument("--out-dir", help="where the result goes (default: next to the replay)")
    ap.add_argument("--format", choices=("mov", "mp4"), default="mov", help="mov: ProRes 4444 with alpha; mp4: H.264")
    ap.add_argument("--background", help="flatten onto this colour (hex) and write H.264, e.g. 1c2230")
    ap.add_argument("--style", choices=plate.STYLES, help="logo finish (default: metal, or cel with --animelee)")
    ap.add_argument("--fit", choices=("bbox", "letters"), default="bbox", help="logo width = ledge to ledge: all of it (bbox) or g..i")
    ap.add_argument("--ground", choices=("xheight", "top"), default="xheight", help="which line of the logo is the stage top")
    ap.add_argument("--ground-offset", type=float, default=0.0, help="Melee units to raise the logo above the stage top (negative: sink it)")
    ap.add_argument("--depth-shift", type=float, default=0.0, help="0: fighters walk through the middle of the logo's thickness, 1: along its front face")
    ap.add_argument("--outline-px", type=float, help="width of the cel outline in pixels (default 0.6 per scale step, at least 1)")
    ap.add_argument("--keep-intermediates", action="store_true", help="keep the characters-only video and its alpha map")
    ap.add_argument("--no-cache", action="store_true", help="render the plate again")
    ap.add_argument("--logo-project", help="Blender file with the logo (default: ~/Documents/logo_metal_fracture/...)")
    ap.add_argument("--blender")
    ap.add_argument("--dolphin")
    ap.add_argument("--iso")
    ap.add_argument("--ffmpeg")
    args = ap.parse_args(argv)

    replay = Path(args.replay).expanduser()
    info = slp.read_replay(replay)
    if info.stage_id not in stagedata.STAGE_FILES:
        raise KeyError(f"{replay.name}: stage {info.stage_id} is not one of the six legal stages")
    style = args.style or ("cel" if args.animelee else "metal")
    geo = stagedata.load_stage(info.stage_id, args.iso)
    m = geo.main_stage
    print(f"{replay.name}: {geo.name}; logo {m.ledge_right[0] - m.ledge_left[0]:.1f} units wide on the stage top "
          f"(y {m.top_y:g}), {style} finish, scale {args.scale}")

    plate_png = get_plate(info.stage_id, style, args.scale, iso=args.iso, logo_project=args.logo_project,
                          blender=args.blender, use_cache=not args.no_cache, fit_to=args.fit, ground_line=args.ground,
                          ground_offset=args.ground_offset, depth_shift=args.depth_shift, outline_px=args.outline_px)

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else replay.resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="logo-stage-"))
    try:
        transparent = run_slp2alpha(replay, work if not args.keep_intermediates else out_dir, args, passthrough)
        tag = transparent.stem.replace("fullTransparent - ", "")
        flat = args.format == "mp4" or bool(args.background)
        final = out_dir / f"{tag}, logo stage.{'mp4' if flat else 'mov'}"
        t0 = time.monotonic()
        composite.composite(plate_png, transparent, final, background=args.background, fmt=args.format,
                            ffmpeg=args.ffmpeg, ffprobe=None)
        print(f"composited in {time.monotonic() - t0:.0f} s\n  {final}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (locate.NotFound, RuntimeError, KeyError, ValueError, slp.ReplayError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
