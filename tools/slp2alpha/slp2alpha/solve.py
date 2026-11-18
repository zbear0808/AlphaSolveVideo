"""The alpha solver: turn a black/white flicker recording into a transparent video and an alpha map.

Same technique as Scripts/AlphaSolve.bat, with the per-pixel geq expressions replaced by
lookup-table filters (about 4x faster, output equal within 0.007/255).
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

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

# Same formats through faster encoders, used when this ffmpeg has them. Apple's ProRes encoder is about
# twice as fast as prores_ks and matches it within 2/255; allow_sw lets it run where there is no ProRes
# hardware (plain M1/M2). The alpha map is greyscale, so 4:2:2 HQ loses nothing there.
ACCELERATED: Dict[str, Tuple[str, OutputFormat]] = {
    "mov": ("prores_videotoolbox", OutputFormat(
        ".mov",
        ["-c:v", "prores_videotoolbox", "-allow_sw", "1", "-profile:v", "4444", "-pix_fmt", "bgra"],
        ["-c:v", "prores_videotoolbox", "-allow_sw", "1", "-profile:v", "hq", "-pix_fmt", "p210le"])),
}

# Dolphin records NTSC fields at 60000/1001 per second; each game frame is shown for two of them.
DEFAULT_FIELD_RATE = "60000/1001"

_PAD_EVEN = "pad=ceil(iw/2)*2:ceil(ih/2)*2"


@dataclass
class SolveOutputs:
    transparent: Path
    alpha_map: Optional[Path]
    """None for a recording without the flicker (render --keep-background): there is no alpha to map."""


def filter_graph(first_color: str, offset: int, fmt: OutputFormat, rate: str = DEFAULT_FIELD_RATE) -> str:
    """rate: the output frame rate, one frame per game frame. That's the recording's field rate unless solve()
    is given another (output_rate).

    Black and white frames are matched by their position, not their timestamps: the blend filters pair
    inputs by timestamp, and recordings with millisecond timestamps (Matroska) would otherwise sometimes
    pair a frame with the neighbouring game frame.
    """
    sel = select_exprs(first_color, offset)
    num, _, den = rate.partition("/")
    retime = f"settb={den or 1}/{num},setpts=N"  # frame N of each branch at N / rate seconds
    map_tail = f",{_PAD_EVEN}" if fmt.even_size else ""
    fg_tail = f",{_PAD_EVEN}:color=black@0" if fmt.even_size else ""
    graph = (
        f"[0]split=3[a][b][c];"
        f"[a]select={sel['black']},{retime}[blk];"
        f"[b]select={sel['white']},{retime}[wht];"
        f"[c]select={sel['black']},{retime}[blk2];"
        f"[blk]format=gbrp[v1];[wht]format=gbrp[v2];"
        # alpha (per channel) = 255 - |black - white|
        f"[v1][v2]blend=all_mode=difference:shortest=1,negate,format=yuv420p[map];"
        f"[map]split=2[alphaMapUse][mapRaw];"
        f"[mapRaw]null{map_tail}[mapOut];"
        # alpha = max over r, g, b (two lighten blends; bit-identical to the original geq)
        f"[alphaMapUse]format=gbrp,extractplanes=r+g+b[ar][ag][ab];"
        f"[ar][ag]blend=all_mode=lighten[arg];"
        f"[arg][ab]blend=all_mode=lighten,split=2[am1][am2];"
        f"[blk2]format=gbrp[dg];"
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


# Recordings without the flicker (render --keep-background): the game as it looks, no alpha to solve. The same
# formats, without an alpha channel; full chroma where the codec allows it.
OPAQUE_PREFIX = "fullOpaque - "
OPAQUE_ARGS: Dict[str, List[str]] = {
    "mov": ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuv444p10le", "-vendor", "apl0"],
    "hevc": ["-c:v", "hevc_videotoolbox", "-q:v", "80", "-tag:v", "hvc1"],
    "mkv": ["-c:v", "ffv1", "-pix_fmt", "bgr0"],
    "png": ["-f", "apng", "-plays", "0"],
    "webm": ["-c:v", "libvpx-vp9", "-lossless", "1", "-pix_fmt", "yuv444p"],
    "gif": ["-r", "50"],
}


def opaque_path(out_dir: Path, name: str, fmt_name: str) -> Path:
    return Path(out_dir) / f"{OPAQUE_PREFIX}{name}{FORMATS[fmt_name].suffix}"


def encode_opaque(ffmpeg: str, video: str, out_dir: Path, name: str, fmt: str = DEFAULT_FORMAT,
                  frames: Optional[int] = None, rate: str = DEFAULT_FIELD_RATE,
                  output_rate: Optional[str] = None) -> Path:
    """Encode a recording made without the flicker: one recorded field per game frame, so nothing is paired
    or solved. Only the first `frames` count (Melee keeps drawing after the replay's end until Dolphin stops)."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose from {', '.join(FORMATS)}")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = opaque_path(out_dir, name, fmt)
    num, _, den = (output_rate or rate).partition("/")
    # trimmed before any resampling: a GIF's -r 50 would otherwise stretch -frames:v past the clip's end
    graph = (f"[0:v]trim=end_frame={frames}," if frames else "[0:v]") + f"settb={den or 1}/{num},setpts=N"
    if FORMATS[fmt].even_size:
        graph += f",{_PAD_EVEN}"
    if FORMATS[fmt].gif:
        graph += ",split[g1][g2];[g1]palettegen[pal];[g2][pal]paletteuse=dither=none"
    graph += "[out]"
    cmd = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", video, "-filter_complex", graph, "-map", "[out]"]
    cmd += ["-r", output_rate] if output_rate and not FORMATS[fmt].gif else []
    subprocess.run(cmd + OPAQUE_ARGS[fmt] + [str(out)], check=True)
    return out


@lru_cache(maxsize=None)
def available_encoders(ffmpeg: str) -> FrozenSet[str]:
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, encoding="utf-8",
                             errors="replace", timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    return frozenset(parts[1] for parts in (line.split() for line in out.splitlines())
                     if len(parts) > 1 and len(parts[0]) == 6 and parts[0][0] in "VAS")


def encoder_choices(ffmpeg: str, fmt: str) -> List[OutputFormat]:
    """The output format through the fastest available encoder first, then the portable one."""
    choices = []
    if fmt in ACCELERATED and ACCELERATED[fmt][0] in available_encoders(ffmpeg):
        choices.append(ACCELERATED[fmt][1])
    return choices + [FORMATS[fmt]]


def missing_encoder(ffmpeg: str, fmt: str) -> Optional[str]:
    """The encoder that `--format fmt` needs and this ffmpeg lacks (e.g. hevc_videotoolbox off macOS), or None.
    None also when the encoder list can't be read: ffmpeg will say what's wrong then."""
    have = available_encoders(ffmpeg)
    needed = [spec.video_args[spec.video_args.index("-c:v") + 1]
              for spec in encoder_choices(ffmpeg, fmt) if "-c:v" in spec.video_args]
    if not have or not needed or any(name in have for name in needed):
        return None
    return needed[-1]


class GrowingFile:
    """A Matroska recording that Dolphin is still writing, streamed to ffmpeg as it grows.

    pump() copies the file into a pipe and closes the pipe once writer_done is set and everything
    written has been sent, so ffmpeg sees the end of the recording exactly when Dolphin stops.
    """

    def __init__(self, path: Path, writer_done: threading.Event, poll_seconds: float = 0.05):
        self.path = Path(path)
        self.writer_done = writer_done
        self.poll_seconds = poll_seconds

    def pump(self, out) -> None:
        try:
            with open(self.path, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        if not self.writer_done.is_set():
                            time.sleep(self.poll_seconds)
                            continue
                        chunk = f.read(1 << 20)  # whatever was written just before the writer finished
                        if not chunk:
                            break
                    out.write(chunk)
        except (BrokenPipeError, ValueError):  # ffmpeg exited early; its exit status reports why
            pass
        finally:
            try:
                out.close()
            except BrokenPipeError:
                pass


def solve(ffmpeg: str, video: str, out_dir: Path, name: str, first_color: str, offset: int,
          fmt: str = DEFAULT_FORMAT, pairs: Optional[int] = None, show_progress: bool = True,
          rate: str = DEFAULT_FIELD_RATE, source: Optional[GrowingFile] = None,
          output_rate: Optional[str] = None) -> SolveOutputs:
    """Solve a recording; with source, read it while it is still being recorded (video is ignored).

    output_rate labels the outputs with that frame rate instead of the recording's `rate`: the same frames, one
    per game frame, at other timestamps (camera exports use exactly 60/1). Not for GIF, which resamples to 50 fps.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose from {', '.join(FORMATS)}")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    outputs = output_paths(out_dir, name, fmt)
    choices = encoder_choices(ffmpeg, fmt)
    for i, spec in enumerate(choices):
        cmd: List[str] = [ffmpeg, "-nostdin", "-y", "-v", "error"] + (["-stats"] if show_progress else [])
        cmd += ["-f", "matroska", "-i", "pipe:0"] if source else ["-i", video]
        cmd += ["-filter_complex", filter_graph(first_color, offset, spec, output_rate or rate)]
        limit = ["-frames:v", str(pairs)] if pairs else []
        # Without -r, ffmpeg keeps the recording's rate as the stream's and rounds the new timestamps into it.
        relabel = ["-r", output_rate] if output_rate and not spec.gif else []
        cmd += ["-map", "[fg]"] + limit + relabel + spec.video_args + [str(outputs.transparent)]
        cmd += ["-map", "[mapGif]" if spec.gif else "[mapOut]"] + limit + relabel + spec.map_args + [str(outputs.alpha_map)]
        if source:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            feeder = threading.Thread(target=source.pump, args=(proc.stdin,), daemon=True)
            feeder.start()
            returncode = proc.wait()
            feeder.join()
        else:
            returncode = subprocess.run(cmd).returncode
        if returncode == 0:
            return outputs
        if i == len(choices) - 1:
            raise subprocess.CalledProcessError(returncode, cmd)
    return outputs


def pair_count(total_frames: int, offset: int) -> int:
    return (total_frames - offset) // 2
