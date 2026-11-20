#!/usr/bin/env python3
"""One command from a Slippi replay to a finished video.

    python3 tools/slp2video/slp2video.py REPLAY.slp [options] [-- slp2alpha render options]

It runs, in order, whatever the options ask for:

  1. the render (tools/slp2alpha): Dolphin plays the replay with the flicker codes and the solver makes it
     transparent; or, with --keep-background, Dolphin records the game as it looks;
  2. your 3D model in place of the stage (tools/logo-stage, Blender): as wide as the stage from ledge to ledge,
     its top on the stage's top, seen through the game's camera, still or moving (--static-camera or not);
  3. the composite: the fighters over the model, over a solid colour (--bg-color) or kept transparent;
  4. the CRT (--crt): CRT Royale's realistic pixels (tools/crt, the physical-pixels mode of its render_video.py).
     Regular Melee is then recorded at its native resolution, the console's own 640x480 picture, so that every
     row of it is one scanline; Animelee at its --scale (2).

The result is one file next to the replay (--out-dir, -o): ProRes 4444 .mov, with alpha unless it's flattened, or
H.264 .mp4. docs/slp2video.md has the details.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
SLP2ALPHA_DIR = HERE.parent / "slp2alpha"
LOGO_STAGE_DIR = HERE.parent / "logo-stage"
CRT_DIR = HERE.parent / "crt"
for _p in (CRT_DIR, LOGO_STAGE_DIR, SLP2ALPHA_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import composite  # noqa: E402
import plate  # noqa: E402
import projection  # noqa: E402
import render_video as crt  # noqa: E402
import stagedata  # noqa: E402
from slp2alpha import locate, slp, solve, stages  # noqa: E402

EXAMPLES = """examples:
  slp2video.py game.slp                                     the stage without its background, transparent
  slp2video.py game.slp --characters-only --animelee        Animelee fighters, nothing else
  slp2video.py game.slp --keep-background --crt             the game as it looks, on a CRT
  slp2video.py game.slp --model statue.glb --static-camera  the fighters on your model, sized to the stage
  slp2video.py game.slp --model logo --animelee --crt       the cel-shaded logo stage, moving camera, CRT
  slp2video.py ys.slp --shy-guy-sprite mascot.png --bg-color 00ff00 --format mp4
"""

CRT_ROWS = 2880          # output rows the CRT pass aims for: 6 per scanline of the native 480 lines
CRT_MASKS = tuple(sorted(crt.MASKS))
PLATE_CACHE = locate.cache_root() / "logo-stage" / "plates"
MOVING_SAMPLES = 16      # EEVEE samples per frame of a moving-camera plate; a still plate uses the finish's default
FORMATS = ("mov", "mp4")
PREFIXES = (("transparent", "fullTransparent - "), ("alpha_map", "alphaMap - "), ("opaque", solve.OPAQUE_PREFIX),
            ("camera", "camera - "))
HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


class UsageError(ValueError):
    pass


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text}: must be 1 or more")
    return value


@dataclass
class Plan:
    """What one run does, worked out from the options and the replay's stage before anything runs."""
    mode: str                    # "stage": the stage without its background; "characters": no stage; "game": all
    scale: int
    static_camera: bool
    transparent: bool
    background: Optional[str]    # the colour the picture is flattened onto (hex), when it isn't transparent
    model: Optional[str]         # "logo", or a model file
    style: Optional[str]         # the model's finish: metal (the logo's), original (a model's own), cel
    crt: bool
    sprite: Optional[str]
    notes: List[str] = field(default_factory=list)

    @property
    def raw(self) -> bool:
        """The CRT gets the console's unstretched picture: one row per scanline."""
        return self.crt

    @property
    def export_camera(self) -> bool:
        """A model seen through the moving camera needs the game's camera on every frame."""
        return self.model is not None and not self.static_camera

    def labels(self, args) -> List[str]:
        """What's added to the render's name for this run's own steps."""
        out = []
        if self.model:
            out.append("logo stage" if self.model == "logo" else f"{Path(self.model).stem} stage")
        if args.bg_color and self.background:
            out.append(f"on {self.background}")
        if self.crt:
            out.append("crt" if args.crt_mask == "grille" else f"crt {args.crt_mask} mask")
        return out


def make_plan(args, stage_id: int) -> Plan:
    notes: List[str] = []
    stage = stages.stage_name(stage_id)
    if args.crt and not args.animelee:
        scale = args.scale or 1
        if scale != 1:
            notes.append(f"regular Melee goes on the CRT at its native resolution (--scale 1); rendering at "
                         f"{scale}x as asked, so each scanline is 1/{scale} of one of the console's")
    else:
        scale = args.scale or (2 if args.animelee else 1)

    model = args.model
    sprite = args.shy_guy_sprite
    if sprite and stage_id != 8:
        notes.append(f"{stage} has no Shy Guys, so --shy-guy-sprite does nothing here")
        sprite = None
    if args.keep_background:
        clash = [opt for on, opt in ((model, "--model"), (args.characters_only, "--characters-only"),
                                     (args.bg_color, "--bg-color"), (args.transparency, "--transparency"),
                                     (args.hide_items, "--hide-items"), (args.hide_effects, "--hide-effects")) if on]
        if clash:
            raise UsageError(f"--keep-background draws the whole game, background and all; it can't be combined "
                             f"with {', '.join(clash)}")
        mode = "game"
    elif args.characters_only or model:
        mode = "characters"
    elif stages.is_supported(stage_id):
        mode = "stage"
    else:
        mode = "characters"
        notes.append(f"{stage}'s background can't be removed with the stage drawn, so only the fighters are "
                     "(--characters-only); --keep-background draws the whole game instead")
    if mode == "stage" and (args.hide_items or args.hide_effects):
        notes.append("--hide-items and --hide-effects only work without the stage (--characters-only)")
    if model and stage_id not in stagedata.STAGE_FILES:
        raise UsageError(f"--model: {stage} is not one of the six legal stages, whose sizes are known")

    if mode == "game":
        transparent = False
    else:
        if args.transparency and (args.bg_color or args.format == "mp4"):
            why = "--bg-color fills the transparent parts" if args.bg_color else "mp4 (H.264) has no alpha channel"
            raise UsageError(f"--transparency can't be kept: {why}")
        transparent = args.transparency is not False and not args.bg_color and args.format == "mov"
    if args.bg_color and not HEX.match(args.bg_color):
        raise UsageError(f"--bg-color {args.bg_color}: give a hex colour like 1c2230 or #00ff00")
    background = None if mode == "game" or transparent else (args.bg_color or "000000").lstrip("#").lower()

    style = None
    if model:
        cel = args.model_cel if args.model_cel is not None else args.animelee
        style = "cel" if cel else ("metal" if model == "logo" else "original")
    return Plan(mode, scale, args.static_camera, transparent, background, model, style, args.crt, sprite, notes)


def slp2alpha_args(args, plan: Plan, replay: Path, out_dir: Path, passthrough: Sequence[str]) -> List[str]:
    """`slp2alpha render` for the plan. It always writes ProRes .mov: exact timestamps (Matroska's are rounded to
    the millisecond, which can pair a frame with its neighbour in a composite) and close to lossless."""
    a = ["render", str(replay), "--out-dir", str(out_dir), "--scale", str(plan.scale), "--format", "mov"]
    a += {"characters": ["--characters-only"], "game": ["--keep-background"], "stage": []}[plan.mode]
    for on, flag in ((plan.static_camera, "--static-camera"), (plan.export_camera, "--export-camera"),
                     (plan.raw, "--raw-resolution"), (args.animelee, "--animelee"),
                     (args.hide_items, "--hide-items"), (args.hide_effects, "--hide-effects")):
        if on:
            a.append(flag)
    if plan.sprite:
        a += ["--shy-guy-sprite", str(Path(plan.sprite).expanduser().resolve())]
    if args.hud is not None:
        a.append("--hud" if args.hud else "--no-hud")
    for opt, value in (("--start-frame", args.start_frame), ("--end-frame", args.end_frame),
                       ("--dolphin", args.dolphin), ("--iso", args.iso), ("--ffmpeg", args.ffmpeg)):
        if value is not None:
            a += [opt, str(value)]
    return a + list(passthrough)


def output_name(render_name: str, plan: Plan, args) -> str:
    """The render's name (`game (characters only, animelee)`) with this run's steps added. A CRT run always records
    the raw picture, so that label goes."""
    name = render_name
    m = re.match(r"^(.*) \((.*)\)$", name)
    if plan.raw and m:
        labels = [label for label in m.group(2).split(", ") if label != "raw resolution"]
        name = m.group(1) + (f" ({', '.join(labels)})" if labels else "")
    extra = plan.labels(args)
    return name + (", " + ", ".join(extra) if extra else "")


# ---------------------------------------------------------------- running things
class Progress:
    """One line of progress for a long step: done/total, rate and time left."""

    def __init__(self, label: str, unit: str = "frames"):
        self.label, self.unit, self.t0, self.first, self.shown = label, unit, None, None, 0.0

    def __call__(self, done: int, total: int) -> None:
        now = time.monotonic()
        if self.t0 is None:
            self.t0, self.first = now, done
        if now - self.shown < 1.0 and done < total:
            return
        self.shown = now
        rate = (done - self.first) / (now - self.t0) if now - self.t0 > 1 else 0.0
        line = f"\r  {self.label}: {done}/{total} {self.unit}"
        if rate > 0 and done < total:
            left = (total - done) / rate
            line += f" ({rate:.1f}/s, {int(left // 60)}:{int(left % 60):02d} left)"
        sys.stderr.write(line + "    ")
        if done >= total:
            sys.stderr.write("\n")
        sys.stderr.flush()


def run_slp2alpha(cmd_args: List[str]) -> Dict[str, Path]:
    """Run `slp2alpha render`, showing what it prints, and pick its output files from what it prints."""
    proc = subprocess.Popen([sys.executable, "-m", "slp2alpha"] + cmd_args, cwd=SLP2ALPHA_DIR,
                            stdout=subprocess.PIPE, encoding="utf-8", errors="replace", env=locate.utf8_child_env())
    found: Dict[str, Path] = {}
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        path = Path(line.strip())
        if path.is_absolute():
            for key, prefix in PREFIXES:
                if path.name.startswith(prefix) and path.exists():
                    found[key] = path
    if proc.wait() != 0:
        raise RuntimeError(f"slp2alpha render failed (exit {proc.returncode})")
    if "transparent" not in found and "opaque" not in found:
        raise RuntimeError("slp2alpha render printed no video")
    return found


def video_info(ffprobe: str, video: Path) -> dict:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=width,height,r_frame_rate,pix_fmt,nb_read_packets", "-of", "json", str(video)],
                         capture_output=True, encoding="utf-8", errors="replace", check=True).stdout
    s = json.loads(out)["streams"][0]
    return {"width": int(s["width"]), "height": int(s["height"]), "rate": s.get("r_frame_rate", "60000/1001"),
            "pix_fmt": s.get("pix_fmt", ""), "frames": int(s.get("nb_read_packets") or 0)}


def stage_slug(stage_id: int) -> str:
    return stagedata.STAGE_FILES[stage_id][0].lower().replace(" ", "-").replace("'", "").replace("é", "e")


def model_kw(args, plan: Plan) -> dict:
    logo = plan.model == "logo"
    return dict(iso=args.iso, fit_to=args.fit, ground_line=args.ground or ("xheight" if logo else "top"),
                ground_offset=args.ground_offset, depth_shift=args.depth_shift, outline_px=args.outline_px,
                model=None if logo else plate.find_model(plan.model), model_objects=args.model_object,
                model_rotation=args.model_rotation, model_scale=args.model_scale)


def model_plate(args, plan: Plan, stage_id: int, size: Tuple[int, int], camera_json: Optional[Path],
                work: Path) -> Path:
    """The model as the game's camera sees it: one PNG for the fixed camera (cached, like the logo stage's), or a
    folder with a PNG per video frame for the moving one."""
    kw = model_kw(args, plan)
    source = kw["model"] or plate.find_project(args.logo_project)
    t0 = time.monotonic()
    if plan.static_camera:
        job = plate.make_job(stage_id, plan.style, plan.scale, Path("plate.png"), size=size,
                             samples=args.model_samples, **kw)
        what = "logo" if plan.model == "logo" else Path(plan.model).stem
        path = PLATE_CACHE / f"{stage_slug(stage_id)}-{what}-{plan.style}-{size[0]}x{size[1]}-{plate.job_key(job, source)}.png"
        if path.exists():
            print(f"model: {path.name} (cached)")
            return path
        plate.render_plate(stage_id, plan.style, plan.scale, path, size=size, samples=args.model_samples,
                           blender=args.blender, logo_project=args.logo_project, **kw)
        print(f"model: {path.name} rendered in {time.monotonic() - t0:.0f} s")
        return path
    if camera_json is None:
        raise RuntimeError("slp2alpha wrote no camera export, which the moving camera needs")
    folder = work / "plate"
    frames, _ = plate.camera_export_frames(camera_json)
    print(f"model: {frames} frames through the game's camera, {args.model_jobs} Blender process"
          f"{'es' if args.model_jobs > 1 else ''}")
    plate.render_sequence(stage_id, plan.style, plan.scale, folder, camera_json, jobs=args.model_jobs,
                          on_progress=Progress("Blender"), samples=args.model_samples or MOVING_SAMPLES,
                          blender=args.blender, logo_project=args.logo_project, **kw)
    print(f"model: rendered in {time.monotonic() - t0:.0f} s")
    return folder


# ---------------------------------------------------------------- the CRT
def crt_width(height: int) -> int:
    """The picture's width on the tube: Melee draws for a screen 1.2173 times as wide as tall (its camera's
    aspect), which its 640 pixels per line are stretched or squeezed to fill. Even, for the encoders."""
    return 2 * round(height * projection.ASPECT / 2)


def crt_settings(args, lines: int) -> "crt.Settings":
    """render_video.py --physical-pixels for a picture `lines` tall, squeezed to Melee's aspect."""
    return crt.physical_settings(crt_width(lines), lines, args.crt_scale or max(1, round(CRT_ROWS / lines)),
                                 mask=args.crt_mask, triads_per_pixel=args.crt_triads_per_pixel or 0.0,
                                 params=args.crt_params or "")


def crt_pass(args, plan: Plan, video: Path, out: Path, work: Path, ffmpeg: str, ffprobe: str,
             librashader: str) -> Path:
    """The picture on the CRT (tools/crt): squeezed to Melee's shape, then each row drawn as one scanline."""
    info = video_info(ffprobe, video)
    lines, rate = info["height"], info["rate"]
    width = crt_width(lines)
    settings = crt_settings(args, lines)
    squeeze = f"scale={width}:{lines}:flags=lanczos+accurate_rnd+full_chroma_int"
    if plan.transparent:  # resample colour weighted by alpha, so transparent pixels don't darken the edges
        squeeze = f"format=gbrap16le,premultiply=inplace=1,{squeeze},unpremultiply=inplace=1,format=bgra"
    else:
        squeeze = f"format=gbrp16le,{squeeze},format=bgr0"
    print(f"CRT: {info['frames']} frames of {width}x{lines} -> {settings.width}x{settings.height} "
          f"({settings.scale} px per scanline, {args.crt_mask} mask)")
    out.parent.mkdir(parents=True, exist_ok=True)
    _, runtime = crt.render(video, out, settings, ffmpeg=ffmpeg, librashader=librashader, input_size=(width, lines),
                            rate=rate, prefilter=f"{crt.frame_clock(rate)},{squeeze}", alpha=plan.transparent,
                            codec="h264-444" if args.format == "mp4" else "prores4444", runtime=args.crt_runtime,
                            jobs=args.crt_jobs, total=info["frames"], on_progress=Progress("CRT"),
                            work=work / "crt")
    print(f"CRT: drawn with librashader's {runtime} runtime")
    got = video_info(ffprobe, out)["frames"]
    if got != info["frames"]:
        print(f"  warning: the CRT video has {got} frames, the picture {info['frames']}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- the command
def parse(argv: Sequence[str]):
    argv = list(argv)
    passthrough: List[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, passthrough = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="slp2video", description=__doc__.split("\n\n")[0], epilog=EXAMPLES,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay", help="the Slippi replay (.slp)")

    g = ap.add_argument_group("what's drawn")
    g.add_argument("--keep-background", action="store_true",
                   help="the game as it looks: stage, background and HUD, an ordinary opaque video (every stage). "
                        "Default: the stage with its background removed (Battlefield, Dream Land), else just the "
                        "fighters")
    g.add_argument("--characters-only", action="store_true", help="no stage, just the fighters (every stage)")
    g.add_argument("--model", metavar="FILE",
                   help="a 3D model in place of the stage, as wide as the stage from ledge to ledge with its top on "
                        "the stage's top: .blend, .glb/.gltf, .fbx, .obj, .stl, .ply, .usd/.usdz or .abc; `logo` for "
                        "the logo of tools/logo-stage. Implies --characters-only; needs Blender")
    g.add_argument("--shy-guy-sprite", metavar="IMAGE",
                   help="Yoshi's Story: draw the Shy Guys with your logo or sprite (PNG with transparency works "
                        "best); with the stage drawn too if --keep-background")
    g.add_argument("--hud", action=argparse.BooleanOptionalAction, default=None,
                   help="percents, stocks and timer (default: on with the stage, off without)")
    g.add_argument("--hide-items", action="store_true", help="without the stage: also hide items and projectiles")
    g.add_argument("--hide-effects", action="store_true", help="without the stage: also hide hit sparks, dust...")

    g = ap.add_argument_group("look and camera")
    g.add_argument("--animelee", action="store_true", help="the Animelee cel-shaded skins (tools/animelee)")
    g.add_argument("--static-camera", action="store_true",
                   help="Melee's fixed camera, which shows the whole stage, without shake. Default: the game's own "
                        "moving camera (with --model, Blender then renders the model on every frame)")
    g.add_argument("--scale", type=int, choices=(1, 2, 3, 4),
                   help="internal resolution (1: 640x528). Default 1, 2 with --animelee")
    g.add_argument("--start-frame", type=int, metavar="FRAME", help="render from this game frame on (as in "
                                                                    "`slp2alpha info`)")
    g.add_argument("--end-frame", type=int, metavar="FRAME", help="render up to and including this game frame")

    g = ap.add_argument_group("output")
    g.add_argument("--transparency", action=argparse.BooleanOptionalAction, default=None,
                   help="keep the alpha channel where nothing is drawn (default: yes, unless --keep-background, "
                        "--bg-color or --format mp4); --no-transparency flattens onto black")
    g.add_argument("--bg-color", metavar="HEX", help="flatten onto this colour instead, e.g. 00ff00")
    g.add_argument("--format", choices=FORMATS,
                   help="mov: ProRes 4444, with alpha when transparent (default); mp4: H.264 (default with "
                        "-o NAME.mp4)")
    g.add_argument("--out-dir", metavar="DIR", help="where the video goes (default: next to the replay)")
    g.add_argument("-o", "--output", metavar="FILE", help="the video's file name (default: the replay's, with the options)")
    g.add_argument("--keep-intermediates", action="store_true",
                   help="keep the work folder: the render, alpha map, camera export, model frames")

    g = ap.add_argument_group("CRT")
    g.add_argument("--crt", action="store_true",
                   help="finish with CRT Royale's realistic pixels (tools/crt, its --physical-pixels mode): "
                        "every row of the picture is one scanline. Regular Melee is recorded at its native "
                        "resolution for it, the console's own 640x480 picture")
    g.add_argument("--crt-mask", choices=CRT_MASKS, default="grille",
                   help="phosphor mask: aperture grille (default), slot mask or shadow mask")
    g.add_argument("--crt-scale", type=positive, metavar="PX",
                   help=f"output pixels per scanline (default: {CRT_ROWS} rows in all: 6 per line at native "
                        "resolution, 3504x2880)")
    g.add_argument("--crt-triads-per-pixel", type=float, metavar="N", help="phosphor triads per picture pixel")
    g.add_argument("--crt-params", metavar="K=V,...", help="more CRT Royale parameters, e.g. halation_weight=0.1")
    g.add_argument("--crt-jobs", type=positive, default=4, metavar="N", help="frames the CRT renders at once (default 4)")
    g.add_argument("--crt-runtime", choices=crt.RUNTIMES, default="auto",
                   help="librashader's runtime (default: metal on macOS, d3d11 on Windows, wgpu on Linux, then "
                        "the others the program has)")

    g = ap.add_argument_group("the model (--model)")
    g.add_argument("--model-object", action="append", default=[], metavar="NAME",
                   help="with a .blend: draw this object only (repeat for more; default: every one that renders)")
    g.add_argument("--model-cel", action=argparse.BooleanOptionalAction, default=None,
                   help="the flat cel finish with an ink outline (default: with --animelee). Without it a model keeps "
                        "its own materials and the logo is metal")
    g.add_argument("--model-scale", type=float, default=1.0, metavar="F",
                   help="the model's width in stage widths (default 1: ledge to ledge)")
    g.add_argument("--model-rotation", type=plate.rotation, default=0.0, metavar="DEG",
                   help="turn the model first, if it doesn't face the camera: DEG about the vertical, or X,Y,Z "
                        "degrees (90,0,0 stands up a model lying on its back)")
    g.add_argument("--ground", choices=("top", "xheight"),
                   help="the model's line that is the stage's top: its highest point (top, a model's default) or "
                        "the median top of its pieces (xheight: a logo's lowercase letters, the logo's default)")
    g.add_argument("--ground-offset", type=float, default=0.0, metavar="UNITS",
                   help="raise the model by this many game units (negative: sink it)")
    g.add_argument("--depth-shift", type=float, default=0.0, metavar="F",
                   help="where the fighters' plane cuts the model: 0 its middle, 1 its front, -1 its back")
    g.add_argument("--fit", choices=("bbox", "letters"), default="bbox",
                   help="the logo only: its whole width between the ledges, or only the letters g to i")
    g.add_argument("--outline-px", type=float, metavar="PX", help="the cel outline's width in pixels")
    g.add_argument("--model-samples", type=positive, metavar="N",
                   help=f"EEVEE samples (default: 64, 32 cel; {MOVING_SAMPLES} per frame with the moving camera)")
    g.add_argument("--model-jobs", type=positive, default=2, metavar="N",
                   help="Blender processes rendering the moving camera's frames together (default 2)")
    g.add_argument("--logo-project", metavar="FILE", help="the logo's Blender project (default: ~/Documents/logo_metal_fracture/...)")

    g = ap.add_argument_group("tools")
    g.add_argument("--dolphin", help="the headless playback Dolphin (default: the build in packages/)")
    g.add_argument("--iso", help="Melee NTSC 1.02 ISO (default: the Slippi Launcher's)")
    g.add_argument("--ffmpeg", help="ffmpeg (ffprobe is expected next to it)")
    g.add_argument("--blender", help="Blender (default: the usual install places, $BLENDER or the PATH)")
    g.add_argument("--librashader", metavar="PATH",
                   help="librashader-cli, for --crt (default: packages/librashader from "
                        "tools/crt/install_librashader.py, the PATH or ~/.cargo/bin)")
    args = ap.parse_args(argv)
    suffix = Path(args.output).suffix.lower().lstrip(".") if args.output else ""
    if args.format is None:
        args.format = suffix if suffix in FORMATS else "mov"
    elif suffix in FORMATS and suffix != args.format:
        ap.error(f"-o {args.output} is a .{suffix} file, but --format is {args.format}")
    return args, passthrough


def preflight(args, plan: Plan) -> Optional[str]:
    """Everything the later steps need, found before the render starts. Returns librashader-cli for --crt."""
    if plan.model:
        plate.find_blender(args.blender)
        if plan.model == "logo":
            plate.find_project(args.logo_project)
        else:
            plate.find_model(plan.model)
        plate.check_style(plan.style, plan.model != "logo")
    if plan.sprite and not Path(plan.sprite).expanduser().is_file():
        raise locate.NotFound(f"--shy-guy-sprite: no such file: {plan.sprite}")
    if not plan.crt:
        return None
    exe = crt.find_librashader(args.librashader)
    crt.runtime_candidates(crt.runtimes_of(exe), args.crt_runtime)   # it has the runtime asked for
    return exe


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace", line_buffering=True)
    args, passthrough = parse(sys.argv[1:] if argv is None else argv)
    replay = Path(args.replay).expanduser().resolve()
    if not replay.is_file():
        raise locate.NotFound(f"replay not found: {replay}")
    info = slp.read_replay(replay)
    plan = make_plan(args, info.stage_id)
    for note in plan.notes:
        print(f"note: {note}", file=sys.stderr)
    ffmpeg = locate.find_ffmpeg(args.ffmpeg)
    ffprobe = locate.find_ffmpeg(args.ffmpeg, name="ffprobe")
    librashader = preflight(args, plan)
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else replay.parent

    t0 = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix="slp2video-"))
    ok = False
    try:
        found = run_slp2alpha(slp2alpha_args(args, plan, replay, work, passthrough))
        video = found.get("transparent") or found["opaque"]
        prefix = dict(PREFIXES)["transparent" if "transparent" in found else "opaque"]
        name = output_name(video.stem[len(prefix):], plan, args)
        final = Path(args.output).expanduser() if args.output else out_dir / f"{name}.{args.format}"
        if final.suffix.lower() != f".{args.format}":
            final = final.with_name(final.name + f".{args.format}")

        size = video_info(ffprobe, video)
        picture = video
        if plan.model:
            plate_path = model_plate(args, plan, info.stage_id, (size["width"], size["height"]), found.get("camera"),
                                     work)
        else:
            plate_path = None
        if plate_path is not None or plan.background or (not plan.crt and args.format != "mov"):
            t = time.monotonic()
            # for the CRT: lossless, in NUT, which keeps the exact frame times (Matroska rounds them to the ms)
            target = work / "composite.nut" if plan.crt else final
            picture = composite.composite(plate_path, video, target, background=plan.background,
                                          fmt="mkv" if plan.crt else args.format, ffmpeg=ffmpeg, ffprobe=ffprobe)
            print(f"composited in {time.monotonic() - t:.0f} s")
        if plan.crt:
            crt_pass(args, plan, picture, final, work, ffmpeg, ffprobe, librashader)
        elif picture == video:
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(video), str(final))
        ok = True
        print(f"done in {time.monotonic() - t0:.0f} s\n  {final}")
    finally:
        if args.keep_intermediates or not ok:
            print(f"  work folder {'kept' if ok else 'left for a look'}: {work}", file=sys.stderr)
        else:
            shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        sys.exit(130)
    except (UsageError, locate.NotFound, RuntimeError, KeyError, ValueError, slp.ReplayError,
            subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
