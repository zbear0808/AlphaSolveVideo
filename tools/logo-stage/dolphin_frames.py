"""Record plain frames (no flicker) of a replay window in the headless Dolphin build, and save some as PNG.

Used to check the camera math against what the game really draws, and to look at stages:

    python3 tools/logo-stage/dolphin_frames.py REPLAY.slp --start 1500 --end 1560 --out DIR [--every 20]
        [--animelee] [--scale 1] [--no-static-camera] [--stage-hidden] [--keep-video]

Everything is written to --out (default: a new temporary folder). The codes are display-only, so the replay
stays in sync: the fixed camera ("Static Camera"), no screen shake, no HUD.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
from slp2alpha import config, gecko, locate, runner  # noqa: E402


def record(replay: Path, start: int, end: int, work: Path, *, animelee: bool = False, scale: int = 1,
           static_camera: bool = True, stage_hidden: bool = False, hud: bool = False,
           extra_codes: Optional[List[str]] = None, dolphin: Optional[str] = None, iso: Optional[str] = None) -> Path:
    """Play frames start..end (Slippi frame numbers) and return the raw recording (FFV1 in Matroska)."""
    dolphin_app = locate.find_dolphin(dolphin)
    engine = runner.engine_of(dolphin_app)
    if engine != config.MAINLINE:
        raise locate.NotFound(f"{dolphin_app} is not the headless mainline build (tools/dolphin-build)")
    iso_path = locate.find_animelee_iso() if animelee else locate.find_iso(iso)
    locate.check_iso(iso_path)
    codes = gecko.load_codes(*(locate.RESOURCES / f for f in config.CODE_FILES))
    enabled: List[str] = []
    if static_camera:
        enabled += config.STATIC_CAMERA_CODES
    else:
        enabled.append("Disable Screen Shake")
    if stage_hidden:
        enabled += config.HIDE_STAGE_CODES
    if not hud:
        enabled.append(config.HIDE_HUD_CODE)
    enabled += extra_codes or []

    work = Path(work)
    if work.exists():
        shutil.rmtree(work)
    user, logs = work / "user", work / "logs"
    dump = config.dump_dir_for(engine, user, work / "dump")
    config.write_user_dir(user, codes, enabled=enabled, scale=scale, engine=engine)
    comm = work / "comm.json"
    config.write_comm(comm, replay, start_frame=start, end_frame=end + 1)  # Dolphin records strictly between
    res = runner.run_dolphin(dolphin_app, iso_path, comm, user, dump, logs, stop_at_frame=end,
                             boot_timeout=180 + max(0, start) / 200.0, grace_seconds=1.0)
    if res.reason != "finished":
        raise RuntimeError(f"Dolphin did not finish ({res.reason}); logs in {logs}")
    videos = sorted(dump.rglob("*.mkv"))
    if not videos:
        raise RuntimeError(f"Dolphin wrote no recording; logs in {logs}")
    return videos[0]


def save_frames(video: Path, out: Path, prefix: str, every: int = 20, ffmpeg: Optional[str] = None) -> List[Path]:
    """Every Nth recorded frame as PNG. Returns the files, named <prefix>_<n>.png (n = recorded frame number)."""
    ffmpeg = ffmpeg or locate.find_ffmpeg()
    out.mkdir(parents=True, exist_ok=True)
    pattern = out / f"{prefix}_%04d.png"
    select = ["-vf", f"select='not(mod(n,{every}))'"]
    for sync in (["-fps_mode", "passthrough"], ["-vsync", "0"]):  # ffmpeg 5.1+, then older builds
        done = subprocess.run([ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(video)] + select + sync
                              + [str(pattern)], capture_output=True)
        if done.returncode == 0:
            break
    else:
        raise RuntimeError(f"ffmpeg could not extract frames: {done.stderr.decode(errors='replace')[-300:]}")
    return sorted(out.glob(f"{prefix}_*.png"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("replay")
    ap.add_argument("--start", type=int, default=1500)
    ap.add_argument("--end", type=int, default=1560)
    ap.add_argument("--out")
    ap.add_argument("--prefix", default="frame")
    ap.add_argument("--every", type=int, default=20)
    ap.add_argument("--scale", type=int, default=1, choices=sorted(config.EFB_SCALE_FOR))
    ap.add_argument("--animelee", action="store_true")
    ap.add_argument("--no-static-camera", action="store_true", help="use the normal following camera")
    ap.add_argument("--stage-hidden", action="store_true", help="characters only (no stage drawn)")
    ap.add_argument("--hud", action="store_true")
    ap.add_argument("--dolphin")
    ap.add_argument("--iso")
    ap.add_argument("--keep-video", action="store_true")
    args = ap.parse_args()

    out = Path(args.out).expanduser() if args.out else Path(tempfile.mkdtemp(prefix="logo-stage-frames-"))
    out.mkdir(parents=True, exist_ok=True)
    video = record(Path(args.replay), args.start, args.end, out / "work", animelee=args.animelee, scale=args.scale,
                   static_camera=not args.no_static_camera, stage_hidden=args.stage_hidden, hud=args.hud,
                   dolphin=args.dolphin, iso=args.iso)
    files = save_frames(video, out, args.prefix, args.every)
    if args.keep_video:
        shutil.copy(video, out / f"{args.prefix}.mkv")
    shutil.rmtree(out / "work", ignore_errors=True)
    print(f"{len(files)} frames in {out}")
    for f in files:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (locate.NotFound, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
