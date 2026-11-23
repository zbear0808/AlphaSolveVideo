"""Lay a logo plate under a transparent character video.

    python3 tools/logo-stage/composite.py PLATE FULLTRANSPARENT.mov OUT.mov [--background HEX] [--format mov|mp4|mkv]

The plate (plate.py) is the logo as the stage camera sees it, the video is `slp2alpha render --characters-only
--static-camera`, so the two have the same size and the fighters land on the logo. PLATE can also be a folder of
frames (000001.png for the video's first frame: plate.py --camera-export), for a render with the moving camera.
The result keeps its alpha (ProRes 4444) unless a background colour is given, which flattens it; --format mp4
writes H.264 (flattened, by default onto 1c2230), mkv lossless FFV1.
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
DEFAULT_BACKGROUND = "1c2230"   # what an H.264 file is flattened onto when no colour is given
FORMATS = ("mov", "mp4", "mkv")
H264 = ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def probe(ffprobe: str, video: Path) -> dict:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_frames,pix_fmt", "-of", "default=nw=1", str(video)],
                         capture_output=True, encoding="utf-8", errors="replace", check=True).stdout
    return dict(line.split("=", 1) for line in out.split() if "=" in line)


def plate_frame(plate: Path) -> Path:
    """The picture whose size a plate has: the PNG itself, or a frame folder's first frame."""
    return Path(plate) / "000001.png" if Path(plate).is_dir() else Path(plate)


def encoders(ffmpeg: str, fmt: str, alpha: bool) -> List[List[str]]:
    """The encoder arguments to try in turn for a format, with or without an alpha channel."""
    if fmt == "mp4":
        return [H264]
    if fmt == "mkv":
        return [["-c:v", "ffv1", "-pix_fmt", "bgra"] if alpha else solve.OPAQUE_ARGS["mkv"]]
    if fmt == "mov":
        # the same encoders slp2alpha writes its videos with: Apple's ProRes where there is one, prores_aw, then
        # prores_ks
        return ([spec.video_args for spec in solve.encoder_choices(ffmpeg, "mov")] if alpha
                else solve.opaque_choices(ffmpeg, "mov"))
    raise ValueError(f"unknown format {fmt!r}; choose from {', '.join(FORMATS)}")


def composite(plate: Optional[Path], video: Path, out: Path, *, background: Optional[str] = None, fmt: str = "mov",
              ffmpeg: Optional[str] = None, ffprobe: Optional[str] = None, matte: Optional[Path] = None) -> Path:
    """The video over the plate (a PNG, a folder of frames, or None for no plate), over a solid colour if
    `background` is given (always for mp4, unless `matte`). Without a background the alpha is kept (mov, mkv), or
    for mp4 written to `matte` as a grey video (white opaque), H.264 having no alpha."""
    ffmpeg = ffmpeg or locate.find_ffmpeg()
    ffprobe = ffprobe or locate.find_ffmpeg(name="ffprobe")
    info = probe(ffprobe, video)
    rate = info.get("r_frame_rate", DEFAULT_RATE)
    size = f"{info['width']}x{info['height']}"
    if matte is not None and (fmt != "mp4" or background):
        raise ValueError("a matte file is for an mp4 that keeps its transparency")
    if fmt == "mp4" and not background and matte is None:
        background = DEFAULT_BACKGROUND
    inputs: List[str] = []
    graph: List[str] = []
    picture = "[fg]"
    if plate is not None:
        plate_info = probe(ffprobe, plate_frame(plate))
        if (plate_info["width"], plate_info["height"]) != (info["width"], info["height"]):
            raise ValueError(f"the plate is {plate_info['width']}x{plate_info['height']} but the video is {size}: "
                             "render both with the same --scale")
        if Path(plate).is_dir():
            inputs += ["-framerate", rate, "-start_number", "1", "-i", str(Path(plate) / "%06d.png")]
        else:
            inputs += ["-loop", "1", "-framerate", rate, "-i", str(plate)]
        graph.append("[0:v]format=rgba[bg]")
    inputs += ["-i", str(video)]
    graph.append(f"[{1 if plate is not None else 0}:v]format=rgba[fg]")
    # RGB all the way: straight alpha in all inputs (the solver unpremultiplies, Blender writes PNG straight).
    if plate is not None:
        graph.append("[bg][fg]overlay=format=rgb:shortest=1[pic]")
        picture = "[pic]"
    if background:
        colour = background.lstrip("#")
        graph.append(f"color=c=0x{colour}:s={size}:r={rate}[solid]")
        graph.append(f"[solid]{picture}overlay=format=rgb:shortest=1" + (",format=yuv420p" if fmt == "mp4" else "")
                     + "[out]")
    elif matte is not None:
        graph.append(f"{picture}split[pc][pm];[pc]format=yuv420p[out];[pm]alphaextract,format=yuv420p[matte]")
    else:
        graph.append(f"{picture}null[out]")
    out.parent.mkdir(parents=True, exist_ok=True)
    head = [ffmpeg, "-nostdin", "-y", "-v", "error"] + inputs + ["-filter_complex", ";".join(graph), "-map", "[out]"]
    second = ["-map", "[matte]"] + H264 + [str(matte)] if matte is not None else []
    done = None
    for codec in encoders(ffmpeg, fmt, alpha=not background):
        done = subprocess.run(head + codec + [str(out)] + second, capture_output=True, encoding="utf-8",
                              errors="replace")
        if done.returncode == 0:
            break
    else:
        raise RuntimeError(f"ffmpeg failed:\n{done.stderr.strip()[-600:]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("plate", help="the plate PNG, or a folder of frames (000001.png...)")
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--background", help="flatten onto this colour (hex, e.g. 1c2230)")
    ap.add_argument("--format", choices=FORMATS, default="mov",
                    help="mov: ProRes 4444; mp4: H.264 (flattened); mkv: lossless FFV1")
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
