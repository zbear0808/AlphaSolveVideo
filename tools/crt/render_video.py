#!/usr/bin/env python3
"""CRT Royale on a video: the original shader, rendered by librashader-cli, on macOS, Windows and Linux.

    python3 tools/crt/render_video.py IN OUT [options]
    python3 tools/crt/render_video.py in.mp4 out.mov --physical-pixels
    python3 tools/crt/render_video.py in.mp4 out.mov --physical-pixels --scale 8 --triads-per-pixel 1

The crt-royale TouchDesigner project's tools/render_video.py, brought into this repo with the same options and the
same settings, and:

  - the shader preset is here (slang-shaders/: libretro's at 2345ee91, the files crt-royale needs, unmodified);
  - librashader's runtime suits the platform: Metal on macOS, Direct3D 11 on Windows, wgpu on Vulkan on Linux
    (--runtime; librashader-cli's own Vulkan runtime ignores the size it's asked for);
  - the frames stream through: each goes to librashader-cli as soon as it's decoded and to the encoder as soon as
    it's drawn, so only the frames in flight are on disk, as BMP files (no PNG compression on either side).

  Standard mode (retro console emulation):
    video -> ffmpeg (fit to N x N "console signal", default 288) -> crt-royale -> ffmpeg (4:4:4) -> movie

  Physical pixel mode (--physical-pixels / --scale N):
    video -> 1:1 native frames (each video pixel is a CRT beam/scanline element) ->
    upscaled to whatever resolution is required (e.g. 6x, 8x) so each input pixel is fully
    resolved as a physical CRT pixel with beam profile, scanline gaps, and phosphor triads.

  Codecs: prores4444 (default, .mov, QuickTime-friendly, full chroma), h264-444 (.mp4, VLC/ffplay),
  png (a numbered PNG sequence in a folder).

It needs ffmpeg and librashader-cli 0.12.1 (python3 tools/crt/install_librashader.py). Python's standard library
is enough: no numpy or Pillow.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import functools
import itertools
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE.parent / "slp2alpha") not in sys.path:
    sys.path.insert(0, str(HERE.parent / "slp2alpha"))
from slp2alpha import locate, solve  # noqa: E402

PRESET = HERE / "slang-shaders" / "crt" / "crt-royale.slangp"
SHADERS_COMMIT = "2345ee91602a7404d3a1a6a5df6108d7305fdad4"   # libretro/slang-shaders
LIBRASHADER_VERSION = "0.12.1"
LIBRASHADER_PACKAGE = locate.PACKAGES / "librashader"         # install_librashader.py puts it here
MASKS = {"grille": 0, "slot": 1, "shadow": 2}
CODECS = ("prores4444", "h264-444", "png")
# librashader's runtimes to try, in this order, when none is asked for. The first that draws the first frame at
# the size asked for draws the rest. librashader-cli 0.12.1's own Vulkan runtime draws at the input's size whatever
# -d says (its render/vk/mod.rs sizes the viewport and the read-back from the input image), so Linux uses its wgpu
# runtime, which draws through Vulkan there. On macOS, wgpu fails ("Unsupported features were requested:
# PIPELINE_CACHE").
RUNTIME_ORDER = {
    "darwin": ("metal", "wgpu"),
    "win32": ("d3d11", "d3d12", "wgpu", "vulkan", "opengl4"),
    "linux": ("wgpu", "vulkan", "opengl4"),
}
RUNTIMES = ("auto", "metal", "d3d11", "d3d12", "d3d9", "vulkan", "wgpu", "opengl4", "opengl3")


class CrtError(RuntimeError):
    pass


# ---------------------------------------------------------------- librashader-cli
EXE = locate.exe("librashader-cli")


def package_exe() -> Path:
    return LIBRASHADER_PACKAGE / "bin" / EXE


def install_hint() -> str:
    return "install it with python3 tools/crt/install_librashader.py (it needs Rust), or pass --librashader PATH"


def find_librashader(explicit: Optional[str] = None) -> str:
    """librashader-cli: as given, LIBRASHADER_CLI, packages/librashader/bin, the PATH, then ~/.cargo/bin."""
    return str(locate.find_first(((explicit, "--librashader"), (os.environ.get("LIBRASHADER_CLI"), "LIBRASHADER_CLI")),
                                 (package_exe(), shutil.which("librashader-cli"), Path.home() / ".cargo" / "bin" / EXE),
                                 f"librashader-cli not found: {install_hint()}"))


_RUNTIME_VALUES = re.compile(r"--runtime <RUNTIME>.*?\[possible values: ([^\]]+)\]", re.S)


def parse_runtimes(help_text: str) -> Tuple[str, ...]:
    """The runtimes `librashader-cli render --help` lists for --runtime: the ones the program was built with."""
    found = None
    for m in _RUNTIME_VALUES.finditer(help_text):   # the last match is the option's entry, not the usage line
        found = m
    return tuple(v.strip() for v in found.group(1).split(",")) if found else ()


@functools.lru_cache(maxsize=None)
def _runtimes(exe: str, mtime: float) -> Tuple[str, ...]:
    try:
        out = subprocess.run([exe, "render", "--help"], stdin=subprocess.DEVNULL, capture_output=True,
                             encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ()
    return parse_runtimes(out.stdout + out.stderr)


def runtimes_of(exe) -> Tuple[str, ...]:
    return _runtimes(str(exe), Path(exe).stat().st_mtime)


def runtime_order(platform: str = sys.platform) -> Tuple[str, ...]:
    return RUNTIME_ORDER.get(platform, RUNTIME_ORDER["linux"])


def runtime_candidates(have: Sequence[str], requested: str = "auto", platform: str = sys.platform) -> List[str]:
    """The runtimes to try, in order: the one asked for, or this platform's that the program has. If its help
    lists none (another version's format), this platform's are all tried."""
    if requested != "auto":
        if have and requested not in have:
            raise CrtError(f"this librashader-cli has no {requested} runtime (it has {', '.join(have)})")
        return [requested]
    order = runtime_order(platform)
    return [r for r in order if r in have] or list(have) or list(order)


# ---------------------------------------------------------------- settings (as the crt-royale project's script worked them out)
@dataclass(frozen=True)
class Settings:
    width: int     # the CRT picture's size
    height: int
    params: str    # --params for librashader-cli
    triad: float
    describe: str  # for the log
    scale: int = 0


def shader_params(mask: str, triad: float, aspect_x: float, aspect_y: float, extra: str = "") -> str:
    params = (f"mask_type={MASKS[mask]},mask_triad_size_desired={triad},interlace_detect_toggle=0,"
              f"geom_aspect_ratio_x={aspect_x},geom_aspect_ratio_y={aspect_y}")
    return params + ("," + extra if extra else "")


def physical_settings(src_w: int, src_h: int, scale: int = 0, *, mask: str = "grille", triad: Optional[float] = None,
                      triads_per_pixel: float = 0.0, aspect: str = "native", params: str = "") -> Settings:
    """Each input pixel as a physical CRT pixel: native scanlines and phosphor triads, upscaled `scale` times."""
    if scale <= 0:
        # Auto-scale: choose an upscale factor so that each scanline gets at least 6 output pixels
        # while keeping total dimensions within GPU bounds (<= 8192)
        if src_h <= 288:
            scale = 6
        elif src_h <= 720:
            scale = 4
        else:
            scale = max(2, min(4, 8192 // max(src_w, src_h)))
    out_h = (src_h * scale + 1) // 2 * 2
    out_w = (src_w * scale + 1) // 2 * 2
    if aspect == "4:3":
        out_w = (int(round(out_h * 4.0 / 3.0)) + 1) // 2 * 2
        aspect_x, aspect_y = 4.0, 3.0
    elif aspect == "16:9":
        out_w = (int(round(out_h * 16.0 / 9.0)) + 1) // 2 * 2
        aspect_x, aspect_y = 16.0, 9.0
    elif aspect == "1:1":
        out_w = out_h
        aspect_x, aspect_y = 1.0, 1.0
    else:  # "native"
        aspect_x, aspect_y = round(out_w / float(out_h) * 1000) / 1000, 1.0
    if triad:
        t = triad
    elif triads_per_pixel > 0:
        t = round((scale / triads_per_pixel) * 8) / 8
    elif scale >= 6:
        # 2 triads per pixel from 6x: individual red, green and blue phosphor bars (3 px at 6x, 4 px at 8x)
        t = round((scale / 2.0) * 8) / 8
    elif scale >= 4:
        t = 3.0
    else:
        t = max(1.0, round(float(scale) * 8) / 8)
    return Settings(out_w, out_h, shader_params(mask, t, aspect_x, aspect_y, params), t,
                    f"physical pixels: {src_w}x{src_h} native ({scale}x upscale) -> {out_w}x{out_h}", scale)


def standard_settings(size: str = "1280", lines: int = 288, fit: str = "crop", *, mask: str = "grille",
                      triad: Optional[float] = None, params: str = "") -> Tuple[Settings, str]:
    """An emulated `lines` x `lines` console signal on a screen of `size`. Returns the settings and the ffmpeg
    filter that fits the video to the signal."""
    if "x" in str(size).lower():
        pw, ph = str(size).lower().split("x")
        out_w, out_h = int(pw), int(ph)
        aspect_x, aspect_y = round(out_w / float(out_h) * 1000) / 1000, 1.0
    else:
        out_w = out_h = int(size)
        aspect_x, aspect_y = 1.0, 1.0
    t = triad or round(3.0 * out_w / 1280.0 * 8) / 8
    n = lines
    vf = {"crop": f"crop='min(iw,ih)':'min(iw,ih)',scale={n}:{n}:flags=area",
          "letterbox": f"scale={n}:{n}:force_original_aspect_ratio=decrease:flags=area,pad={n}:{n}:(ow-iw)/2:(oh-ih)/2:black",
          "stretch": f"scale={n}:{n}:flags=area"}[fit]
    return (Settings(out_w, out_h, shader_params(mask, t, aspect_x, aspect_y, params), t,
                     f"standard: {lines} lines -> {out_w}x{out_h}"), vf)


# ---------------------------------------------------------------- frames
def bmp_header(width: int, height: int) -> bytes:
    """A 24-bit BMP's headers: rows bottom-up, each padded to 4 bytes."""
    stride = (width * 3 + 3) & ~3
    image = stride * height
    return (b"BM" + struct.pack("<IHHI", 54 + image, 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, image, 2835, 2835, 0, 0))


def bmp_bytes(bgr: bytes, width: int, height: int) -> bytes:
    """A top-down BGR frame (ffmpeg's bgr24) as a BMP file."""
    row = width * 3
    pad = b"\0" * (((row + 3) & ~3) - row)
    rows = [bgr[y * row:(y + 1) * row] + pad for y in range(height - 1, -1, -1)]
    return bmp_header(width, height) + b"".join(rows)


def timebase(rate: str) -> str:
    """The time base of one frame per tick at `rate` (60000/1001 -> 1001/60000)."""
    num, _, den = str(rate).partition("/")
    return f"{den}/{num}" if den else f"1/{num}"


def frame_clock(rate: str) -> str:
    """Filters that put frame N at N ticks of 1/rate, so two streams of the same frames line up exactly."""
    return f"settb={timebase(rate)},setpts=N"


@functools.lru_cache(maxsize=None)
def _alpha_formats(ffprobe: str) -> frozenset:
    out = subprocess.run([ffprobe, "-v", "error", "-show_pixel_formats", "-of", "json"], capture_output=True,
                         encoding="utf-8", errors="replace")
    try:
        return frozenset(f["name"] for f in json.loads(out.stdout)["pixel_formats"] if f["flags"].get("alpha"))
    except (ValueError, KeyError, TypeError):
        return frozenset()


def has_alpha(ffprobe: str, pix_fmt: str) -> bool:
    known = _alpha_formats(ffprobe)
    if known:
        return pix_fmt in known
    return pix_fmt.startswith(("rgba", "bgra", "argb", "abgr", "yuva", "gbrap", "ya", "ayuv"))


def video_encoder(ffmpeg: str, codec: str, alpha: bool, size: Tuple[int, int]) -> List[str]:
    """Encoder arguments: slp2alpha's ProRes 4444, through Apple's encoder where it works at this size (about ten
    times faster than prores_ks at 3504x2880; tried on a frame first), else prores_ks. H.264 in 4:4:4: subsampled
    chroma would smear the phosphor stripes."""
    if codec == "h264-444":
        return ["-c:v", "libx264", "-crf", "12", "-preset", "medium", "-pix_fmt", "yuv444p", "-movflags", "+faststart"]
    if codec != "prores4444":
        raise ValueError(f"no video encoder for {codec}")
    name, fast = solve.ACCELERATED["mov"]
    if name in solve.available_encoders(ffmpeg):
        probe = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                                f"color=c=black:s={size[0]}x{size[1]}:d=0.1", "-frames:v", "1", *fast.video_args,
                                "-f", "null", "-"], capture_output=True)
        if probe.returncode == 0:
            return fast.video_args
    return solve.FORMATS["mov"].video_args if alpha else solve.OPAQUE_ARGS["mov"]


def _tail(path: Path, lines: int = 12) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-lines:])
    except OSError:
        return ""


def _drop(path: Path) -> None:
    try:
        path.unlink()
    except OSError:  # e.g. briefly held by a virus scanner on Windows; the work folder goes at the end anyway
        pass


def image_size_of(head: bytes) -> Optional[Tuple[int, int]]:
    """A BMP's or PNG's width and height, from the start of the file."""
    if head[:2] == b"BM" and len(head) >= 26:
        width, height = struct.unpack("<ii", head[18:26])
        return width, abs(height)
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        return struct.unpack(">II", head[16:24])
    return None


def image_size(path: Path) -> Optional[Tuple[int, int]]:
    with open(path, "rb") as f:
        return image_size_of(f.read(26))


def draw(exe: str, runtime: str, preset: Path, settings: Settings, src: Path, dst: Path) -> Path:
    """One frame through the shader. Its frame number stays 0, as in the crt-royale project's script: crt-royale
    only uses it to detect interlacing, which is off."""
    p = subprocess.run([exe, "render", "-p", str(preset), "-i", str(src), "-o", str(dst), "-r", runtime,
                        "-d", f"{settings.width}x{settings.height}", "--params", settings.params],
                       stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not dst.exists():
        msg = (p.stderr or p.stdout).strip().splitlines()
        raise CrtError(f"librashader-cli ({runtime}) failed on {src.name}: {' | '.join(msg[-4:]) or 'no output'}")
    size = image_size(dst)
    if size != (settings.width, settings.height):
        _drop(dst)
        got = f"{size[0]}x{size[1]}" if size else "an image of unknown size"
        raise CrtError(f"librashader-cli ({runtime}) drew {src.name} as {got}, not {settings.width}x{settings.height}")
    _drop(src)
    return dst


def pick_runtime(exe: str, preset: Path, settings: Settings, src: Path, dst: Path,
                 candidates: Sequence[str]) -> str:
    """Draw `src` with each runtime in turn; the first that draws it at the right size is the one to use."""
    failures = []
    for name in candidates:
        try:
            draw(exe, name, preset, settings, src, dst)
            return name
        except CrtError as e:
            failures.append(str(e))
    raise CrtError("no librashader runtime could draw the first frame:\n  " + "\n  ".join(failures))


def render(src: Path, out: Path, settings: Settings, *, ffmpeg: str, librashader: str, input_size: Tuple[int, int],
           rate: str, prefilter: str = "", start: Optional[float] = None, duration: Optional[float] = None,
           alpha: bool = False, codec: str = "prores4444", audio: bool = False, runtime: str = "auto",
           jobs: int = 4, preset: Path = PRESET, total: Optional[int] = None,
           on_progress: Optional[Callable[[int, Optional[int]], None]] = None, work: Optional[Path] = None,
           keep: bool = False) -> Tuple[int, str]:
    """The video through CRT Royale into `out` (a folder of PNGs with codec png). Returns (frames, runtime).

    ffmpeg decodes `src` through `prefilter` into frames of `input_size`, which librashader-cli draws at the
    settings' size, `jobs` at a time. The encoding ffmpeg takes them in order. With `alpha`, it scales the
    alpha of `src` (through the same `prefilter`) up to the CRT's size and merges it back (bilinear), as the
    crt-royale project's script did; with `audio`, it copies the source's audio in (AAC)."""
    if codec not in CODECS:
        raise ValueError(f"unknown codec {codec!r}; choose from {', '.join(CODECS)}")
    candidates = runtime_candidates(runtimes_of(librashader), runtime)
    folder = Path(work) if work else Path(tempfile.mkdtemp(prefix="crt-"))
    frames_in, frames_out = folder / "in", folder / "out"
    for d in (frames_in, frames_out):
        d.mkdir(parents=True, exist_ok=True)
    # PNGs without alpha to merge come straight from librashader-cli, which compresses them `jobs` at a time
    # (ffmpeg's PNG encoder would do them one by one). Everything else goes to the encoder as BMPs.
    direct = codec == "png" and not alpha
    if codec == "png":
        Path(out).mkdir(parents=True, exist_ok=True)

    def drawn_path(i: int) -> Path:
        return Path(out) / f"{i + 1:06d}.png" if direct else frames_out / f"{i:06d}.bmp"

    def log(name: str) -> str:
        return _tail(folder / f"{name}.log")

    width, height = input_size
    frame_size = width * height * 3
    src_in = (["-ss", str(start)] if start else []) + ["-i", str(src)]
    limit = ["-t", str(duration)] if duration else []
    chain = ",".join(f for f in (prefilter, "format=bgr24") if f)
    dec_log, enc_log = (folder / "decode.log").open("wb"), (folder / "encode.log").open("wb")
    decoder = subprocess.Popen([ffmpeg, "-nostdin", "-v", "error"] + src_in + limit
                               + ["-vf", chain, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=dec_log)
    encoder = None
    pool = cf.ThreadPoolExecutor(max_workers=max(1, jobs))
    done = 0
    ok = False
    try:
        def decoded() -> Iterator[Path]:
            for i in itertools.count():
                data = decoder.stdout.read(frame_size)
                if len(data) < frame_size:
                    return
                path = frames_in / f"{i:06d}.bmp"
                path.write_bytes(bmp_bytes(data, width, height))
                yield path

        frames = decoded()
        first = next(frames, None)
        if first is None:
            raise CrtError(f"ffmpeg decoded no frames from {src}: {log('decode')}")
        chosen = pick_runtime(librashader, preset, settings, first, drawn_path(0), candidates)

        if not direct:
            size = (settings.width, settings.height)
            head = [ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "image2pipe", "-c:v", "bmp", "-framerate", rate,
                    "-i", "-"]
            maps: List[str] = []
            if alpha or (audio and codec != "png"):
                head += src_in
            if alpha:
                alpha_chain = ",".join(f for f in (prefilter, frame_clock(rate), "alphaextract",
                                                   f"scale={size[0]}:{size[1]}:flags=bilinear") if f)
                head += ["-filter_complex",
                         f"[1:v]{alpha_chain}[a];[0:v]{frame_clock(rate)}[c];[c][a]alphamerge[v]"]
                maps += ["-map", "[v]"]
            else:
                maps += ["-map", "0:v"]
            if codec == "png":
                tail = ["-f", "image2", "-start_number", "1", str(Path(out) / "%06d.png")]
            else:
                if audio:
                    maps += ["-map", "1:a?", "-c:a", "aac", "-b:a", "256k"]
                tail = ["-r", rate] + video_encoder(ffmpeg, codec, alpha, size) + [str(out)]
            encoder = subprocess.Popen(head + maps + limit + tail, stdin=subprocess.PIPE,
                                       stdout=subprocess.DEVNULL, stderr=enc_log)

        def finish(path: Path) -> None:
            nonlocal done
            if encoder is not None:  # else a PNG of the sequence: it stays
                try:
                    encoder.stdin.write(path.read_bytes())
                except (BrokenPipeError, OSError):
                    raise CrtError(f"ffmpeg stopped encoding (exit {encoder.wait()}): {log('encode')}")
                _drop(path)
            done += 1
            if on_progress:
                on_progress(done, total)

        finish(drawn_path(0))
        inflight: collections.deque = collections.deque()
        for i, path in enumerate(frames, 1):   # up to 2 * jobs frames decoded or drawing at once
            inflight.append(pool.submit(draw, librashader, chosen, preset, settings, path, drawn_path(i)))
            if len(inflight) >= 2 * jobs:
                finish(inflight.popleft().result())
        while inflight:
            finish(inflight.popleft().result())
        if encoder is not None:
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise CrtError(f"ffmpeg couldn't encode the CRT frames (exit {encoder.returncode}): {log('encode')}")
        if decoder.wait() != 0:
            raise CrtError(f"ffmpeg couldn't decode {src} (exit {decoder.returncode}): {log('decode')}")
        ok = True
        return done, chosen
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        for proc in (decoder, encoder):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
        dec_log.close()
        enc_log.close()
        if ok and not keep:
            shutil.rmtree(folder, ignore_errors=True)
        elif not ok:
            print(f"  CRT work folder left for a look: {folder}", file=sys.stderr)


# ---------------------------------------------------------------- the command
def probe_video(ffprobe: str, path: str) -> dict:
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,avg_frame_rate,r_frame_rate,pix_fmt,nb_frames",
                          "-of", "json", path], capture_output=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise CrtError(f"ffprobe can't read {path}: {out.stderr.strip()[-300:]}")
    streams = json.loads(out.stdout).get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise CrtError(f"{path} has no video")
    rate = next((r for r in (video.get("avg_frame_rate"), video.get("r_frame_rate"))
                 if r and not r.startswith("0/") and r != "0"), "30/1")
    frames = video.get("nb_frames")
    return {"width": int(video["width"]), "height": int(video["height"]), "rate": rate,
            "pix_fmt": video.get("pix_fmt", ""), "frames": int(frames) if frames and frames.isdigit() else None,
            "audio": any(s.get("codec_type") == "audio" for s in streams)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--physical-pixels", action="store_true",
                    help="render each input video pixel 1:1 as a realistic physical CRT pixel (native scanlines and phosphor triads, upscaled to fit)")
    ap.add_argument("--scale", "--pixel-scale", type=int, default=0, dest="scale",
                    help="upscale multiplier per input pixel in physical-pixels mode (e.g. 4, 6, 8; implies --physical-pixels)")
    ap.add_argument("--triads-per-pixel", type=float, default=0.0,
                    help="phosphor triads per input pixel in physical-pixels mode (e.g. 2.0 for broadcast monitor, 1.0 for 1:1 triad mapping)")
    ap.add_argument("--aspect", choices=["native", "4:3", "16:9", "1:1"], default="native",
                    help="screen aspect ratio in physical-pixels mode (default: native source pixel aspect; or 4:3 / 16:9 for CRT display geometry)")
    ap.add_argument("--alpha", action="store_true", default=None,
                    help="preserve input video's alpha transparency in output (default: auto if input has alpha)")
    ap.add_argument("--no-alpha", action="store_false", dest="alpha",
                    help="do not preserve alpha (composite characters over black CRT background)")
    ap.add_argument("--size", default="1280",
                    help="output size in standard mode: WxH (e.g. 1920x1080) or single integer for square (default 1280)")
    ap.add_argument("--lines", type=int, default=288,
                    help="emulated scanlines in standard mode (default: 288)")
    ap.add_argument("--fit", default="crop", choices=["crop", "letterbox", "stretch"],
                    help="framing mode in standard mode: crop, letterbox, or stretch (default: crop)")
    ap.add_argument("--mask", default="grille", choices=sorted(MASKS),
                    help="phosphor mask type: grille (aperture grille), slot (slot mask), shadow (EDP shadow mask)")
    ap.add_argument("--triad", type=float,
                    help="phosphor triad size in output pixels (default: calculated automatically from scale / mode)")
    ap.add_argument("--start", type=float, default=0.0, help="start timestamp in seconds")
    ap.add_argument("--duration", type=float, help="seconds to render (default: all)")
    ap.add_argument("--fps", help="output frame rate (default: input frame rate)")
    ap.add_argument("--jobs", type=int, default=4, help="frames drawn at once (default: 4)")
    ap.add_argument("--codec", default="prores4444", choices=CODECS,
                    help="output video codec: prores4444, h264-444, or png sequence (default: prores4444)")
    ap.add_argument("--params", default="", help="extra shader parameters, e.g. crt_gamma=2.2,halation_weight=0.1")
    ap.add_argument("--runtime", default="auto", choices=RUNTIMES,
                    help="librashader's runtime (default: the platform's: metal on macOS, d3d11 on Windows, wgpu "
                         "(on Vulkan) on Linux, falling back to the others the program has)")
    ap.add_argument("--librashader", help="librashader-cli (default: packages/librashader, the PATH or ~/.cargo/bin)")
    ap.add_argument("--preset", default=str(PRESET), help="the shader preset (default: crt-royale, in this folder)")
    ap.add_argument("--ffmpeg", help="ffmpeg (ffprobe is expected next to it)")
    ap.add_argument("--keep", action="store_true", help="keep the work folder")
    a = ap.parse_args(argv)

    ffmpeg = locate.find_ffmpeg(a.ffmpeg)
    ffprobe = locate.find_ffmpeg(a.ffmpeg, name="ffprobe")
    exe = find_librashader(a.librashader)
    info = probe_video(ffprobe, a.input)
    rate = a.fps or info["rate"]
    use_alpha = has_alpha(ffprobe, info["pix_fmt"]) if a.alpha is None else a.alpha
    if a.physical_pixels or a.scale > 0:
        settings = physical_settings(info["width"], info["height"], a.scale, mask=a.mask, triad=a.triad,
                                     triads_per_pixel=a.triads_per_pixel, aspect=a.aspect, params=a.params)
        vf, size = f"fps={rate}", (info["width"], info["height"])
    else:
        settings, fit = standard_settings(a.size, a.lines, a.fit, mask=a.mask, triad=a.triad, params=a.params)
        vf, size = f"fps={rate},{fit}", (a.lines, a.lines)
    total = info["frames"] if not a.start and not a.duration else None
    alpha_str = ", alpha preserved" if use_alpha else ""
    print(f"{total if total else 'all'} frames, {rate} fps, {settings.describe}, {a.mask} mask, triad "
          f"{settings.triad:g} px{alpha_str}", flush=True)

    def progress(done: int, of: Optional[int]) -> None:
        if done % 10 == 0 or (of and done == of):
            print(f"  rendered {done}" + (f"/{of}" if of else ""), flush=True)

    t0 = time.monotonic()
    frames, runtime = render(Path(a.input), Path(a.output), settings, ffmpeg=ffmpeg, librashader=exe,
                             input_size=size, rate=rate, prefilter=vf, start=a.start or None, duration=a.duration,
                             alpha=use_alpha, codec=a.codec, audio=info["audio"], runtime=a.runtime, jobs=a.jobs,
                             preset=Path(a.preset), total=total, on_progress=progress, keep=a.keep)
    print(f"{frames} frames in {time.monotonic() - t0:.0f} s, with librashader's {runtime} runtime")
    print("wrote", a.output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CrtError, locate.NotFound, ValueError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
