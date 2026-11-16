"""The alpha solver: turn a black/white flicker recording into a transparent video and an alpha map.

Same technique as Scripts/AlphaSolve.bat, with the per-pixel geq expressions replaced by
lookup-table filters (about 4x faster, output equal within 0.007/255).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .validate import select_exprs


@dataclass(frozen=True)
class OutputFormat:
    suffix: str
    video_args: List[str] = field(default_factory=list)
    map_args: List[str] = field(default_factory=list)
    even_size: bool = False  # pad by one transparent row/column when the encoder needs even dimensions
    gif: bool = False


FORMATS: Dict[str, OutputFormat] = {
    # Default. ProRes 4444 with alpha: opens with transparency in Final Cut, Premiere, Resolve, After Effects.
    "mov": OutputFormat(".mov",
                        ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
                         "-alpha_bits", "16", "-vendor", "apl0"],
                        ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuv444p10le", "-vendor", "apl0"]),
    # Much smaller transparent .mov for Apple apps (HEVC with alpha through VideoToolbox; macOS only).
    "hevc": OutputFormat(" (HEVC).mov",
                         ["-c:v", "hevc_videotoolbox", "-alpha_quality", "0.9", "-q:v", "80", "-tag:v", "hvc1",
                          "-pix_fmt", "bgra"],
                         ["-c:v", "hevc_videotoolbox", "-q:v", "80", "-tag:v", "hvc1"], even_size=True),
    # Lossless archival.
    "mkv": OutputFormat(".mkv", ["-c:v", "ffv1", "-pix_fmt", "bgra"], ["-c:v", "ffv1", "-pix_fmt", "gray"]),
    "png": OutputFormat(".png", ["-f", "apng", "-plays", "0"], ["-f", "apng", "-plays", "0"]),
    "webm": OutputFormat(".webm", ["-c:v", "libvpx-vp9", "-lossless", "1", "-pix_fmt", "yuva420p"],
                         ["-c:v", "libvpx-vp9", "-lossless", "1", "-pix_fmt", "yuv420p"]),
    "gif": OutputFormat(".gif", ["-r", "50"], ["-r", "50"], gif=True),
}
DEFAULT_FORMAT = "mov"

_PAD_EVEN = "pad=ceil(iw/2)*2:ceil(ih/2)*2"


@dataclass
class SolveOutputs:
    transparent: Path
    alpha_map: Path


def filter_graph(first_color: str, offset: int, fmt: OutputFormat) -> str:
    sel = select_exprs(first_color, offset)
    map_tail = f",{_PAD_EVEN}" if fmt.even_size else ""
    fg_tail = f",{_PAD_EVEN}:color=black@0" if fmt.even_size else ""
    graph = (
        f"[0]split=3[a][b][c];"
        f"[a]select={sel['black']},setpts=PTS-STARTPTS[blk];"
        f"[b]select={sel['white']},setpts=PTS-STARTPTS[wht];"
        f"[c]select={sel['black']},setpts=PTS-STARTPTS[blk2];"
        f"[blk]format=gbrp[v1];[wht]format=gbrp[v2];"
        # alpha (per channel) = 255 - |black - white|
        f"[v1][v2]blend=all_mode=difference:shortest=1,negate,format=yuv420p[map];"
        f"[map]setpts=0.5*PTS[alphaMap];"
        f"[alphaMap]split=2[alphaMapUse][mapRaw];"
        f"[mapRaw]null{map_tail}[mapOut];"
        # alpha = max over r, g, b (two lighten blends; bit-identical to the original geq)
        f"[alphaMapUse]format=gbrp,extractplanes=r+g+b[ar][ag][ab];"
        f"[ar][ag]blend=all_mode=lighten[arg];"
        f"[arg][ab]blend=all_mode=lighten,split=2[am1][am2];"
        f"[blk2]setpts=0.5*PTS,format=gbrp[dg];"
    )
    if not fmt.gif:
        # colour = black * 255 / alpha (lookup table instead of a per-pixel expression)
        graph += (
            f"[am2]format=gbrp[ag3];"
            f"[dg][ag3]lut2=c0='if(y,min(255,x*255/y),0)':c1='if(y,min(255,x*255/y),0)'"
            f":c2='if(y,min(255,x*255/y),0)'[unp];"
            f"[unp][am1]alphamerge,format=argb{fg_tail}[fg]"
        )
    else:
        # GIF has 1-bit alpha: like AlphaSolve.bat, skip the colour boost and threshold the alpha instead.
        graph += (
            "[am2]nullsink;[dg][am1]alphamerge,split[g1][g2];[g1]palettegen=reserve_transparent=1[pal1];"
            "[g2][pal1]paletteuse=dither=none:alpha_threshold=64[fg];"
            "[mapOut]split[m1][m2];[m1]palettegen[pal2];[m2][pal2]paletteuse=dither=none[mapGif]"
        )
    return graph


def output_paths(out_dir: Path, name: str, fmt_name: str) -> SolveOutputs:
    fmt = FORMATS[fmt_name]
    return SolveOutputs(Path(out_dir) / f"fullTransparent - {name}{fmt.suffix}",
                        Path(out_dir) / f"alphaMap - {name}{fmt.suffix}")


def solve(ffmpeg: str, video: str, out_dir: Path, name: str, first_color: str, offset: int,
          fmt: str = DEFAULT_FORMAT, pairs: Optional[int] = None, show_progress: bool = True) -> SolveOutputs:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose from {', '.join(FORMATS)}")
    spec = FORMATS[fmt]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    outputs = output_paths(out_dir, name, fmt)

    cmd: List[str] = [ffmpeg, "-y", "-v", "error"] + (["-stats"] if show_progress else [])
    cmd += ["-i", video, "-filter_complex", filter_graph(first_color, offset, spec)]
    limit = ["-frames:v", str(pairs)] if pairs else []
    cmd += ["-map", "[fg]"] + limit + spec.video_args + [str(outputs.transparent)]
    cmd += ["-map", "[mapGif]" if spec.gif else "[mapOut]"] + limit + spec.map_args + [str(outputs.alpha_map)]
    subprocess.run(cmd, check=True)
    return outputs


def pair_count(total_frames: int, offset: int) -> int:
    return (total_frames - offset) // 2
