"""Lay a logo plate under a transparent character video.

    python3 tools/logo-stage/composite.py PLATE.png FULLTRANSPARENT.mov OUT.mov [--background HEX] [--format mov|mp4]

The plate (plate.py) is the logo as the stage camera sees it, the video is `slp2alpha render --characters-only
--static-camera`, so the two have the same size and the fighters land on the logo. The result keeps its alpha
(ProRes 4444) unless a background colour is given, which flattens it for a quick look (H.264).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
from slp2alpha import locate, solve  # noqa: E402

DEFAULT_RATE = "60000/1001"


def probe(ffprobe: str, video: Path) -> dict:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_frames,pix_fmt", "-of", "default=nw=1", str(video)],
                         capture_output=True, encoding="utf-8", errors="replace", check=True).stdout
    return dict(line.split("=", 1) for line in out.split() if "=" in line)


def composite(plate: Path, video: Path, out: Path, *, background: Optional[str] = None, fmt: str = "mov",
              ffmpeg: Optional[str] = None, ffprobe: Optional[str] = None) -> Path:
    ffmpeg = ffmpeg or locate.find_ffmpeg()
    ffprobe = ffprobe or locate.find_ffmpeg(name="ffprobe")
    info = probe(ffprobe, video)
    rate = info.get("r_frame_rate", DEFAULT_RATE)
    size = f"{info['width']}x{info['height']}"
    plate_info = probe(ffprobe, plate)
    if (plate_info["width"], plate_info["height"]) != (info["width"], info["height"]):
        raise ValueError(f"the plate is {plate_info['width']}x{plate_info['height']} but the video is {size}: "
                         "render both with the same --scale")
    out.parent.mkdir(parents=True, exist_ok=True)
    head: List[str] = [ffmpeg, "-nostdin", "-y", "-v", "error", "-loop", "1", "-framerate", rate, "-i", str(plate),
                       "-i", str(video)]
    # RGB all the way: straight alpha in both inputs (the solver unpremultiplies, Blender writes PNG straight).
    if fmt == "mp4" or background:
        colour = (background or "1c2230").lstrip("#")
        graph = (f"color=c=0x{colour}:s={size}:r={rate}[solid];[0:v]format=rgba[bg];[1:v]format=rgba[fg];"
                 f"[solid][bg]overlay=format=rgb:shortest=0[base];[base][fg]overlay=format=rgb:shortest=1,format=yuv420p")
        attempts = [["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]]
    else:
        graph = "[0:v]format=rgba[bg];[1:v]format=rgba[fg];[bg][fg]overlay=format=rgb:shortest=1"
        # the same encoders slp2alpha writes its transparent video with: Apple's ProRes where there is one, else prores_ks
        attempts = [spec.video_args for spec in solve.encoder_choices(ffmpeg, "mov")]
    done = None
    for codec in attempts:
        done = subprocess.run(head + ["-filter_complex", graph] + codec + [str(out)], capture_output=True,
                              encoding="utf-8", errors="replace")
        if done.returncode == 0:
            break
    else:
        raise RuntimeError(f"ffmpeg failed:\n{done.stderr.strip()[-600:]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("plate")
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--background", help="flatten onto this colour (hex, e.g. 1c2230) and write H.264")
    ap.add_argument("--format", choices=("mov", "mp4"), default="mov")
    args = ap.parse_args()
    path = composite(Path(args.plate), Path(args.video), Path(args.out), background=args.background, fmt=args.format)
    print(path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (locate.NotFound, RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
