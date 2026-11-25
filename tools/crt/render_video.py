#!/usr/bin/env python3
"""A CRT on a video: the original shaders (crt-guest-advanced, its NTSC variant, Sony Megatron v2, CRT Royale),
drawn by Blender's GPU module, by crt-stream or by librashader-cli, on macOS, Windows and Linux.

    python3 tools/crt/render_video.py IN OUT [options]
    python3 tools/crt/render_video.py in.mp4 out.mov --physical-pixels
    python3 tools/crt/render_video.py in.mp4 out.mov --physical-pixels --scale 8 --triads-per-pixel 1
    python3 tools/crt/render_video.py in.mp4 out.mov --shader royale --mask slot
    python3 tools/crt/render_video.py --list-masks

The crt-royale TouchDesigner project's tools/render_video.py, brought into this repo with the same options and the
same settings, and:

  - the shader presets are here (slang-shaders/: libretro's at 2345ee91, the files they need, unmodified), each with
    its looks and settings in shaders.py (--shader, --mask, --list-masks). guest is the default;
  - on macOS and Linux, Blender draws it where Blender is found (--runtime blender, blender_crt.py): the preset as
    librashader-cli compiles it (blender-chain/<shader>/), in one process for the whole video, so guest's afterglow
    carries from frame to frame. ffmpeg's decoded frames go to it, and its drawn frames to the encoding ffmpeg,
    through pipes;
  - otherwise crt-stream draws it where it's built (--runtime stream, crt-stream/): one librashader chain for the
    whole video, the frames through its stdin and stdout, so the afterglow carries over there too, on any platform;
  - otherwise librashader-cli draws each frame, in a runtime that suits the platform: Metal on macOS, Direct3D 11
    on Windows, wgpu on Vulkan on Linux (librashader-cli's own Vulkan runtime ignores the size it's asked for). The
    frames stream through: each goes to librashader-cli as soon as it's decoded and to the encoder as soon as it's
    drawn, so only the frames in flight are on disk, as BMP files. Each frame is drawn on its own there, so guest
    loses its afterglow (it says so).

  Standard mode (retro console emulation):
    video -> ffmpeg (fit to N x N "console signal", default 288) -> the shader -> ffmpeg (4:4:4) -> movie

  Physical pixel mode (--physical-pixels / --scale N):
    video -> 1:1 native frames (each video pixel is a CRT beam/scanline element) ->
    upscaled to whatever resolution is required (e.g. 6x, 8x) so each input pixel is fully
    resolved as a physical CRT pixel with beam profile, scanline gaps, and phosphor triads.

  Codecs: prores4444 (default, .mov, QuickTime-friendly, full chroma), h264-444 (.mp4, VLC/ffplay; with alpha,
  the alpha goes to NAME matte.mp4, a grey video), png (a numbered PNG sequence in a folder).

It needs ffmpeg, and Blender 5.2 (macOS, Linux), crt-stream or librashader-cli 0.12.1 (python3
tools/crt/install_librashader.py builds both).
Python's standard library is enough here: no numpy or Pillow (blender_crt.py uses Blender's own numpy).
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
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import shaders  # noqa: E402

PRESET = HERE / "slang-shaders" / "crt" / "crt-royale.slangp"   # CRT Royale's; each shader's: shaders.SHADERS
SHADERS_COMMIT = "2345ee91602a7404d3a1a6a5df6108d7305fdad4"   # libretro/slang-shaders
LIBRASHADER_VERSION = "0.12.1"
LIBRASHADER_PACKAGE = locate.PACKAGES / "librashader"         # install_librashader.py puts it here
MASKS = shaders.ROYALE_MASKS
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
# A CRT drawn by Blender's GPU module (blender_crt.py, blender-chain/): one process for the whole video, which
# compiles the preset once, where librashader-cli starts and compiles it again for every frame. 3504x2880 frames
# go 3 to 9 times as fast into the same encoder (research/crt-in-blender), 0.003/255 from librashader-cli's on a
# Mac. Tried before librashader's runtimes where Blender is found: on macOS and Linux, which hand it the frames
# through inherited pipes. Only for the vendored presets, which blender-chain/<shader>/ are compiled from.
BLENDER_PLATFORMS = ("darwin", "linux")
BLENDER_SCRIPT = HERE / "blender_crt.py"
BLENDER_CHAIN = HERE / "blender-chain" / "royale"   # CRT Royale's; each shader's: shaders.Shader.chain
# crt-stream (crt-stream/, built by install_librashader.py): one librashader filter chain for the whole video, raw
# frames on stdin and stdout, so feedback (guest's afterglow) and the frame count carry over without Blender, on
# every platform and for any preset. Tried after Blender, before librashader-cli.
STREAM_EXE = locate.exe("crt-stream")
RUNTIMES = ("auto", "blender", "stream", "metal", "d3d11", "d3d12", "d3d9", "vulkan", "wgpu", "opengl4", "opengl3")


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


def blender_platform(platform: str = sys.platform) -> bool:
    return platform.startswith(BLENDER_PLATFORMS)


def find_blender(explicit: Optional[str] = None) -> Optional[str]:
    """Blender for --runtime blender, or None when there's none (an explicit one must exist)."""
    try:
        return locate.find_blender(explicit)
    except locate.NotFound:
        if explicit or os.environ.get("BLENDER"):
            raise
        return None


def find_librashader_or_none(explicit: Optional[str] = None) -> Optional[str]:
    try:
        return find_librashader(explicit)
    except locate.NotFound:
        if explicit or os.environ.get("LIBRASHADER_CLI"):
            raise
        return None


def find_stream(explicit: Optional[str] = None) -> Optional[str]:
    """crt-stream: as given, CRT_STREAM, packages/librashader/bin, then the PATH; None when there's none (an
    explicit one must exist)."""
    try:
        return str(locate.find_first(((explicit, "--crt-stream"), (os.environ.get("CRT_STREAM"), "CRT_STREAM")),
                                     (LIBRASHADER_PACKAGE / "bin" / STREAM_EXE, shutil.which("crt-stream")),
                                     f"crt-stream not found: {install_hint()}"))
    except locate.NotFound:
        if explicit or os.environ.get("CRT_STREAM"):
            raise
        return None


def blender_chain(preset: Path) -> Optional[Path]:
    """The Blender chain of a vendored preset, if it has one."""
    shader = shaders.by_preset(preset)
    return shader.chain if shader and (shader.chain / "chain.json").is_file() else None


def candidates(librashader: Optional[str], blender: Optional[str], requested: str = "auto",
               platform: str = sys.platform, preset: Optional[Path] = None, stream: Optional[str] = None) -> List[str]:
    """The runtimes to try, in order: Blender's first where it can draw (blender_platform, a vendored preset with its
    chain; the default shader's without one), then crt-stream, then librashader-cli's (runtime_candidates).
    `stream` None looks for crt-stream (find_stream), "" leaves it out."""
    stream = find_stream() if stream is None else stream
    preset = Path(preset) if preset else shaders.get(None).preset
    blender_ok = bool(blender) and blender_platform(platform) and blender_chain(preset) is not None
    if requested == "blender":
        if not blender_ok:
            why = ("Blender wasn't found" if not blender else "it draws only the vendored presets"
                   if blender_platform(platform) else "it runs on macOS and Linux only, so far")
            raise CrtError(f"--runtime blender: {why}")
        return ["blender"]
    if requested == "stream":
        if not stream:
            raise CrtError(f"--runtime stream: crt-stream wasn't found: {install_hint()}")
        return ["stream"]
    found = runtime_candidates(runtimes_of(librashader), requested, platform) if librashader else []
    if requested != "auto" and not librashader:
        raise CrtError(f"--runtime {requested} needs librashader-cli: {install_hint()}")
    first = (["blender"] if blender_ok else []) + (["stream"] if stream else []) if requested == "auto" else []
    out = first + found
    if not out:
        raise CrtError(f"nothing to draw the CRT with: install Blender, or crt-stream and librashader-cli "
                       f"({install_hint()})")
    return out


# ---------------------------------------------------------------- settings (as the crt-royale project's script worked them out)
@dataclass(frozen=True)
class Settings:
    width: int     # the CRT picture's size
    height: int
    params: str    # --params for librashader-cli
    triad: float   # the triad pitch asked for, or the shader's own (0: the look's own size)
    describe: str  # for the log
    scale: int = 0
    shader: str = shaders.DEFAULT
    mask: str = "grille"
    afterglow: bool = True   # False: drawn without it (--no-afterglow)


def shader_params(mask: str, triad: float, aspect_x: float, aspect_y: float, extra: str = "") -> str:
    """CRT Royale's parameters, as render_video.py has always written them."""
    ctx = shaders.Context(0, 0, 0, 0, mask, triad, aspect_x, aspect_y)
    return shaders.format_params(shaders.royale_params(ctx), extra)


def profile_settings(shader: str, mask: Optional[str], ctx_args: dict, extra: str, afterglow: bool
                     ) -> Tuple[shaders.Shader, str, str]:
    """(the shader, the look, its parameters) for a picture: the look's parameters at this size, then, without the
    afterglow, what turns it off, then `extra`."""
    profile = shaders.get(shader)
    mask = profile.check_mask(mask)
    params = profile.params(shaders.Context(mask=mask, **ctx_args))
    if not afterglow:
        params.update(profile.afterglow_off)
    return profile, mask, shaders.format_params(params, extra)


def physical_settings(src_w: int, src_h: int, scale: int = 0, *, mask: Optional[str] = None,
                      triad: Optional[float] = None, triads_per_pixel: float = 0.0, aspect: str = "native",
                      params: str = "", shader: Optional[str] = None, afterglow: bool = True) -> Settings:
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
    profile, mask, text = profile_settings(shader, mask, dict(out_w=out_w, out_h=out_h, src_w=src_w, src_h=src_h,
                                                              triad_px=t, aspect_x=aspect_x, aspect_y=aspect_y,
                                                              physical=True, scale=scale), params, afterglow)
    return Settings(out_w, out_h, text, t, f"physical pixels: {src_w}x{src_h} native ({scale}x upscale) -> "
                    f"{out_w}x{out_h}", scale, profile.id, mask, afterglow)


def standard_settings(size: str = "1280", lines: int = 288, fit: str = "crop", *, mask: Optional[str] = None,
                      triad: Optional[float] = None, params: str = "", shader: Optional[str] = None,
                      afterglow: bool = True) -> Tuple[Settings, str]:
    """An emulated `lines` x `lines` console signal on a screen of `size`. Returns the settings and the ffmpeg
    filter that fits the video to the signal. Without a triad pitch, each shader sizes its mask itself: Royale's
    triad is 3 px at 1280 px wide, guest's period follows the smaller side, Megatron's patterns are fixed."""
    if "x" in str(size).lower():
        pw, ph = str(size).lower().split("x")
        out_w, out_h = int(pw), int(ph)
        aspect_x, aspect_y = round(out_w / float(out_h) * 1000) / 1000, 1.0
    else:
        out_w = out_h = int(size)
        aspect_x, aspect_y = 1.0, 1.0
    n = lines
    vf = {"crop": f"crop='min(iw,ih)':'min(iw,ih)',scale={n}:{n}:flags=area",
          "letterbox": f"scale={n}:{n}:force_original_aspect_ratio=decrease:flags=area,pad={n}:{n}:(ow-iw)/2:(oh-ih)/2:black",
          "stretch": f"scale={n}:{n}:flags=area"}[fit]
    profile, mask, text = profile_settings(shader, mask, dict(out_w=out_w, out_h=out_h, src_w=n, src_h=n,
                                                              triad_px=triad, aspect_x=aspect_x, aspect_y=aspect_y),
                                           params, afterglow)
    t = triad or (profile.default_triad(out_w, out_h) if profile.default_triad else 0.0)
    return (Settings(out_w, out_h, text, t, f"standard: {lines} lines -> {out_w}x{out_h}", 0, profile.id, mask,
                     afterglow), vf)


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


# H.264 4:4:4 for .mp4: subsampled chroma would smear the phosphor stripes. NVENC first, where it works (NVIDIA's
# driver, and an FFmpeg whose NVENC API it supports): on a GTX 1060, CRT frames at 3504x2880 went 18.6 frames/s
# against libx264's 2.6, with a constant QP of 12 scoring at least libx264 CRF 12's quality (SSIM 0.988 against
# 0.985, PSNR 44.8 dB against 40.4) in files about four times the size (research/crt-in-blender). NVENC's VBR mode
# capped those files at a fifth of that size and lost detail (SSIM 0.91). H.264 is up to 4096 pixels wide there;
# the probe on a frame of the real size finds that out.
H264_444 = [
    ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-profile:v", "high444p", "-pix_fmt", "yuv444p",
     "-rc", "constqp", "-qp", "12"],
    ["-c:v", "libx264", "-crf", "12", "-preset", "medium", "-pix_fmt", "yuv444p"],
]
# The alpha of an .mp4 with transparency, as a grey video of its own: H.264 has no alpha channel. White is opaque,
# as a luma matte has it in Resolve, Premiere and Final Cut. 4:2:0 loses nothing in a grey picture.
H264_MATTE = [
    ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-profile:v", "high", "-pix_fmt", "yuv420p",
     "-rc", "constqp", "-qp", "12"],
    ["-c:v", "libx264", "-crf", "12", "-preset", "medium", "-pix_fmt", "yuv420p"],
]
MATTE_SUFFIX = " matte"


def matte_path(out: Path) -> Path:
    """Where the matte of an .mp4 goes: `NAME matte.mp4` next to `NAME.mp4`."""
    out = Path(out)
    return out.with_name(f"{out.stem}{MATTE_SUFFIX}{out.suffix}")


def first_working(ffmpeg: str, choices: List[List[str]], size: Tuple[int, int]) -> List[str]:
    """The first encoder arguments that are listed and encode a frame of this size here; the last ones otherwise."""
    have = solve.available_encoders(ffmpeg)
    for args in choices[:-1]:
        if args[args.index("-c:v") + 1] in have and solve.encoder_works(ffmpeg, tuple(args), tuple(size)):
            return args
    return choices[-1]


def video_encoder(ffmpeg: str, codec: str, alpha: bool, size: Tuple[int, int]) -> List[str]:
    """Encoder arguments: the first that encodes a frame of this size here. ProRes 4444 as slp2alpha writes it:
    Apple's encoder (about ten times prores_ks's speed at 3504x2880), prores_aw (about four times), prores_ks.
    H.264 4:4:4: NVENC, then libx264."""
    if codec == "h264-444":
        return first_working(ffmpeg, H264_444, size) + ["-movflags", "+faststart"]
    if codec == "prores4444":
        return first_working(ffmpeg, [spec.video_args for spec in solve.encoder_choices(ffmpeg, "mov")] if alpha
                             else solve.opaque_choices(ffmpeg, "mov"), size)
    raise ValueError(f"no video encoder for {codec}")


def matte_encoder(ffmpeg: str, size: Tuple[int, int]) -> List[str]:
    return first_working(ffmpeg, H264_MATTE, size) + ["-movflags", "+faststart"]


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


def draw(exe: str, runtime: str, preset: Path, settings: Settings, src: Path, dst: Path, frame: int = 0) -> Path:
    """One frame through the shader, in a fresh chain: what the shader keeps from frame to frame starts from black.
    `frame` > 0 draws it frame + 1 times, the last with that frame count (librashader-cli's -f): guest-ntsc's chroma
    phase alternates with the frame count's parity."""
    p = subprocess.run([exe, "render", "-p", str(preset), "-i", str(src), "-o", str(dst), "-r", runtime,
                        "-d", f"{settings.width}x{settings.height}", "--params", settings.params]
                       + (["-f", str(frame)] if frame else []),
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


def encoder_command(ffmpeg: str, frames_in: List[str], out: Path, size: Tuple[int, int], *, codec: str, rate: str,
                    src_in: List[str], limit: List[str], prefilter: str, alpha: bool, audio: bool) -> List[str]:
    """The ffmpeg that encodes the drawn frames (`frames_in`: their input options, ending in -i -). With alpha it
    scales the alpha of the source (through the same prefilter) up to the CRT's size and merges it back, or, for
    H.264, which has no alpha, writes it as a matte of its own (matte_path)."""
    head = [ffmpeg, "-nostdin", "-y", "-v", "error"] + frames_in
    maps: List[str] = []
    matte: List[str] = []
    if alpha or (audio and codec != "png"):
        head += src_in
    if alpha:
        alpha_chain = ",".join(f for f in (prefilter, frame_clock(rate), "alphaextract",
                                           f"scale={size[0]}:{size[1]}:flags=bilinear") if f)
        if codec == "h264-444":
            head += ["-filter_complex", f"[1:v]{alpha_chain}[a];[0:v]{frame_clock(rate)}[v]"]
            matte = ["-map", "[a]", *limit, "-r", rate, *matte_encoder(ffmpeg, size), str(matte_path(out))]
        else:
            head += ["-filter_complex", f"[1:v]{alpha_chain}[a];[0:v]{frame_clock(rate)}[c];[c][a]alphamerge[v]"]
        maps += ["-map", "[v]"]
    else:
        maps += ["-map", "0:v"]
    if codec == "png":
        tail = ["-f", "image2", "-start_number", "1", str(Path(out) / "%06d.png")]
    else:
        if audio:
            maps += ["-map", "1:a?", "-c:a", "aac", "-b:a", "256k"]
        tail = ["-r", rate] + video_encoder(ffmpeg, codec, alpha, size) + [str(out)]
    return head + maps + limit + tail + matte


class DrawerUnavailable(CrtError):
    """A drawer that takes the whole video through pipes (render_piped) stopped before its first frame: the next
    runtime gets the video."""


class BlenderUnavailable(DrawerUnavailable):
    """Blender couldn't draw the first frame."""


class StreamUnavailable(DrawerUnavailable):
    """crt-stream couldn't draw the first frame."""


def lut_folder(folder: Path, ffmpeg: str, chain: Path = BLENDER_CHAIN) -> Path:
    """The chain's textures (masks, colour LUTs) as raw RGBA, and luts.json with their sizes, for blender_crt.py."""
    doc = json.loads((chain / "chain.json").read_text(encoding="utf-8"))
    preset_dir = (HERE / doc["preset"]).parent
    luts = folder / "luts"
    luts.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for lut in doc["luts"]:
        png = preset_dir / lut["path"]
        raw = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(png), "-f", "rawvideo", "-pix_fmt", "rgba",
                              "-"], capture_output=True, check=True).stdout
        size = image_size(png)
        if not size or len(raw) != size[0] * size[1] * 4:
            raise CrtError(f"couldn't read the mask texture {png}")
        (luts / f"{lut['name']}.rgba").write_bytes(raw)
        sizes[lut["name"]] = list(size)
    (luts / "luts.json").write_text(json.dumps(sizes), encoding="utf-8")
    return luts


def blender_command(blender: str, luts: Path, in_fd: int, out_fd: int, input_size: Tuple[int, int],
                    settings: Settings, platform: str = sys.platform, chain: Optional[Path] = None,
                    warmup: int = 0) -> List[str]:
    # On Linux Blender's OpenGL backend drew a 3504x2880 frame in 26 ms on a GTX 1060, its Vulkan backend in 43
    backend = ["--gpu-backend", "opengl"] if platform.startswith("linux") else []
    chain = chain or shaders.get(settings.shader).chain
    return [blender, "-b", "--factory-startup", "-noaudio", *backend, "--python-exit-code", "1",
            "--python", str(BLENDER_SCRIPT), "--", str(chain), str(luts), str(in_fd), str(out_fd),
            str(input_size[0]), str(input_size[1]), str(settings.width), str(settings.height), settings.params,
            *(["--warmup", str(warmup)] if warmup else [])]


def render_blender(src: Path, out: Path, settings: Settings, *, ffmpeg: str, blender: str,
                   input_size: Tuple[int, int], rate: str, folder: Path, src_in: List[str], limit: List[str],
                   prefilter: str, alpha: bool, codec: str, audio: bool, total: Optional[int],
                   on_progress: Optional[Callable[[int, Optional[int]], None]], chain: Optional[Path] = None,
                   warmup: int = 0) -> int:
    """The video through blender_crt.py (render_piped), with the chain's textures. Raises BlenderUnavailable if
    Blender stops before its first frame."""
    chain = chain or shaders.get(settings.shader).chain
    luts = lut_folder(folder, ffmpeg, chain)
    return render_piped(lambda in_fd, out_fd: blender_command(blender, luts, in_fd, out_fd, input_size, settings,
                                                              chain=chain, warmup=warmup),
                        "blender", "Blender", BlenderUnavailable, src, out, settings, ffmpeg=ffmpeg, rate=rate,
                        folder=folder, src_in=src_in, limit=limit, prefilter=prefilter, alpha=alpha, codec=codec,
                        audio=audio, total=total, on_progress=on_progress)


def stream_command(stream: str, preset: Path, input_size: Tuple[int, int], settings: Settings,
                   warmup: int = 0) -> List[str]:
    return [stream, "--preset", str(preset), "--input", f"{input_size[0]}x{input_size[1]}",
            "--output", f"{settings.width}x{settings.height}", "--params", settings.params,
            *(["--warmup", str(warmup)] if warmup else [])]


def render_stream(src: Path, out: Path, settings: Settings, *, stream: str, preset: Path,
                  input_size: Tuple[int, int], warmup: int = 0, **kw) -> int:
    """The video through crt-stream (render_piped), on its stdin and stdout, which works on Windows too. Raises
    StreamUnavailable if it stops before its first frame."""
    return render_piped(lambda in_fd, out_fd: stream_command(stream, preset, input_size, settings, warmup),
                        "stream", "crt-stream", StreamUnavailable, src, out, settings, stdio=True, **kw)


def render_piped(command: Callable[[int, int], List[str]], name: str, title: str, unavailable: type,
                 src: Path, out: Path, settings: Settings, *, ffmpeg: str, rate: str, folder: Path,
                 src_in: List[str], limit: List[str], prefilter: str, alpha: bool, codec: str, audio: bool,
                 total: Optional[int], on_progress: Optional[Callable[[int, Optional[int]], None]],
                 stdio: bool = False) -> int:
    """The video through a drawer that reads raw RGBA frames from one file descriptor and writes the drawn ones to
    another, and reports CRT_READY, CRT_FRAMES n and CRT_DONE on stderr (blender_crt.py, crt-stream).
    `command(in_fd, out_fd)` starts it: with the two pipes inherited (macOS, Linux), or with `stdio`, as its stdin
    and stdout (also Windows). ffmpeg decodes into one pipe, the drawer draws from it into another, ffmpeg encodes
    from that. Python only starts them; the frames don't pass through it. Raises `unavailable` if the drawer stops
    before its first frame; its log is `name`.log."""
    chain = ",".join(f for f in (prefilter, "format=bgr24", "format=rgba") if f)   # the colour, opaque, as BMPs had it
    size = (settings.width, settings.height)
    frames_in = ["-f", "rawvideo", "-pix_fmt", "rgb0", "-s", f"{size[0]}x{size[1]}", "-framerate", rate, "-i", "-"]
    logs = {n: (folder / f"{n}.log").open("wb") for n in ("decode", "encode", name)}
    procs: List[subprocess.Popen] = []
    done, ready, reports = 0, False, []
    try:
        decoder = subprocess.Popen([ffmpeg, "-nostdin", "-v", "error"] + src_in + limit
                                   + ["-vf", chain, "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=logs["decode"])
        procs.append(decoder)
        encoder = subprocess.Popen(encoder_command(ffmpeg, frames_in, out, size, codec=codec, rate=rate, src_in=src_in,
                                                   limit=limit, prefilter=prefilter, alpha=alpha, audio=audio),
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=logs["encode"])
        procs.append(encoder)
        if stdio:
            drawer = subprocess.Popen(command(0, 1), stdin=decoder.stdout, stdout=encoder.stdin,
                                      stderr=subprocess.PIPE)
        else:
            in_fd, out_fd = decoder.stdout.fileno(), encoder.stdin.fileno()
            drawer = subprocess.Popen(command(in_fd, out_fd), pass_fds=(in_fd, out_fd), stdin=subprocess.DEVNULL,
                                      stdout=logs[name], stderr=subprocess.PIPE)
        procs.append(drawer)
        decoder.stdout.close()   # the drawer has them now: each pipe ends when its last holder closes it
        encoder.stdin.close()
        for raw in drawer.stderr:
            logs[name].write(raw)
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("CRT_READY "):
                ready = True
                reports.append(line[len("CRT_READY "):])
            elif line.startswith("CRT_FRAMES "):
                done = int(line.split()[1])
                if on_progress:
                    on_progress(done, total)
        drawer.wait()
        for f in logs.values():
            f.flush()
        if drawer.returncode != 0 or not ready:
            if done == 0:
                raise unavailable(f"{title} couldn't draw the CRT (exit {drawer.returncode}): "
                                  f"{_tail(folder / f'{name}.log')}")
            raise CrtError(f"{title} stopped after {done} frames (exit {drawer.returncode}): "
                           f"{_tail(folder / f'{name}.log')}")
        if encoder.wait() != 0:
            raise CrtError(f"ffmpeg couldn't encode the CRT frames (exit {encoder.returncode}): {_tail(folder / 'encode.log')}")
        if decoder.wait() != 0:
            raise CrtError(f"ffmpeg couldn't decode {src} (exit {decoder.returncode}): {_tail(folder / 'decode.log')}")
        if done == 0:
            raise CrtError(f"ffmpeg decoded no frames from {src}: {_tail(folder / 'decode.log')}")
        return done
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
        for f in logs.values():
            f.close()


def render(src: Path, out: Path, settings: Settings, *, ffmpeg: str, librashader: Optional[str],
           input_size: Tuple[int, int], rate: str, prefilter: str = "", start: Optional[float] = None,
           duration: Optional[float] = None, alpha: bool = False, codec: str = "prores4444", audio: bool = False,
           runtime: str = "auto", jobs: int = 4, preset: Optional[Path] = None, total: Optional[int] = None,
           on_progress: Optional[Callable[[int, Optional[int]], None]] = None, work: Optional[Path] = None,
           keep: bool = False, blender: Optional[str] = None, warmup: int = 0,
           stream: Optional[str] = None) -> Tuple[int, str]:
    """The video through the settings' shader (or `preset`) into `out` (a folder of PNGs with codec png). Returns
    (frames, runtime).

    ffmpeg decodes `src` through `prefilter` into frames of `input_size`, which Blender (blender_crt.py) or
    crt-stream draws at the settings' size in one process, or librashader-cli in one process per frame, `jobs` at a
    time. The encoding
    ffmpeg takes them in order. With `alpha`, it scales the alpha of `src` (through the same `prefilter`) up to the
    CRT's size and merges it back (bilinear), as the crt-royale project's script did; with `audio`, it copies the
    source's audio in (AAC). `warmup` draws the first frame that many extra times first, so state kept across
    frames (guest's afterglow) starts settled; Blender and crt-stream do it. `stream` None looks for crt-stream, ""
    leaves it out."""
    if codec not in CODECS:
        raise ValueError(f"unknown codec {codec!r}; choose from {', '.join(CODECS)}")
    preset = Path(preset) if preset else shaders.get(settings.shader).preset
    stream = find_stream() if stream is None else stream
    order = candidates(librashader, blender, runtime, preset=preset, stream=stream)
    folder = Path(work) if work else Path(tempfile.mkdtemp(prefix="crt-"))
    folder.mkdir(parents=True, exist_ok=True)
    if codec == "png":
        Path(out).mkdir(parents=True, exist_ok=True)
    src_in = (["-ss", str(start)] if start else []) + ["-i", str(src)]
    limit = ["-t", str(duration)] if duration else []
    piped = dict(ffmpeg=ffmpeg, input_size=input_size, rate=rate, folder=folder, src_in=src_in, limit=limit,
                 prefilter=prefilter, alpha=alpha, codec=codec, audio=audio, total=total, on_progress=on_progress,
                 warmup=warmup)
    ok = False
    try:
        while order[0] in ("blender", "stream"):
            try:
                if order[0] == "blender":
                    done = render_blender(src, out, settings, blender=blender, chain=blender_chain(preset), **piped)
                else:
                    done = render_stream(src, out, settings, stream=stream, preset=preset, **piped)
                ok = True
                return done, order[0]
            except DrawerUnavailable as e:
                order = order[1:]
                if not order:
                    raise
                instead = "crt-stream" if order[0] == "stream" else "librashader-cli"
                print(f"  {e}\n  drawing with {instead} instead", file=sys.stderr)
        done, chosen = render_librashader(src, out, settings, ffmpeg=ffmpeg, librashader=librashader,
                                          input_size=input_size, rate=rate, folder=folder, src_in=src_in, limit=limit,
                                          prefilter=prefilter, alpha=alpha, codec=codec, audio=audio, jobs=jobs,
                                          preset=preset, candidates=order, total=total, on_progress=on_progress)
        ok = True
        return done, chosen
    finally:
        if ok and not keep:
            shutil.rmtree(folder, ignore_errors=True)
        elif not ok:
            print(f"  CRT work folder left for a look: {folder}", file=sys.stderr)


def render_librashader(src: Path, out: Path, settings: Settings, *, ffmpeg: str, librashader: str,
                       input_size: Tuple[int, int], rate: str, folder: Path, src_in: List[str], limit: List[str],
                       prefilter: str, alpha: bool, codec: str, audio: bool, jobs: int, preset: Path,
                       candidates: Sequence[str], total: Optional[int],
                       on_progress: Optional[Callable[[int, Optional[int]], None]]) -> Tuple[int, str]:
    """The video through librashader-cli, one run per frame, `jobs` at a time, the frames as BMP files. Each frame is
    drawn in a fresh chain, so a temporal shader loses what it carries over (guest's afterglow: it says so once). Where
    the frame count's parity matters (guest-ntsc's chroma phase), odd frames are drawn with -f 1."""
    shader = shaders.by_preset(preset)
    if shader and shader.temporal and settings.afterglow and shader.afterglow_off:
        print(f"  warning: librashader-cli draws each frame on its own, so {shader.id}'s afterglow is lost (it only "
              f"shows below 8/255; Blender keeps it)", file=sys.stderr)
    parity = bool(shader and shader.frame_parity)
    frames_in, frames_out = folder / "in", folder / "out"
    for d in (frames_in, frames_out):
        d.mkdir(parents=True, exist_ok=True)
    # PNGs without alpha to merge come straight from librashader-cli, which compresses them `jobs` at a time
    # (ffmpeg's PNG encoder would do them one by one). Everything else goes to the encoder as BMPs.
    direct = codec == "png" and not alpha

    def drawn_path(i: int) -> Path:
        return Path(out) / f"{i + 1:06d}.png" if direct else frames_out / f"{i:06d}.bmp"

    def log(name: str) -> str:
        return _tail(folder / f"{name}.log")

    width, height = input_size
    frame_size = width * height * 3
    chain = ",".join(f for f in (prefilter, "format=bgr24") if f)
    dec_log, enc_log = (folder / "decode.log").open("wb"), (folder / "encode.log").open("wb")
    decoder = subprocess.Popen([ffmpeg, "-nostdin", "-v", "error"] + src_in + limit
                               + ["-vf", chain, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=dec_log)
    encoder = None
    pool = cf.ThreadPoolExecutor(max_workers=max(1, jobs))
    done = 0
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
            frames_args = ["-f", "image2pipe", "-c:v", "bmp", "-framerate", rate, "-i", "-"]
            encoder = subprocess.Popen(encoder_command(ffmpeg, frames_args, out, size, codec=codec, rate=rate,
                                                       src_in=src_in, limit=limit, prefilter=prefilter, alpha=alpha,
                                                       audio=audio),
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=enc_log)

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
            inflight.append(pool.submit(draw, librashader, chosen, preset, settings, path, drawn_path(i),
                                        i % 2 if parity else 0))
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
        return done, chosen
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        for proc in (decoder, encoder):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
        decoder.stdout.close()
        dec_log.close()
        enc_log.close()


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
    ap.add_argument("input", nargs="?")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--shader", default=shaders.DEFAULT, choices=list(shaders.SHADERS),
                    help=f"the CRT: {', '.join(f'{s.id} ({s.name})' for s in shaders.SHADERS.values())} "
                         f"(default: {shaders.DEFAULT})")
    ap.add_argument("--list-masks", action="store_true", help="print each shader's looks for --mask, and stop")
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
    ap.add_argument("--mask", help="the shader's look, its phosphor mask (default: grille, an aperture grille; "
                                   "--list-masks shows each shader's)")
    ap.add_argument("--triad", type=float,
                    help="phosphor triad size in output pixels (default: calculated automatically from scale / mode)")
    ap.add_argument("--start", type=float, default=0.0, help="start timestamp in seconds")
    ap.add_argument("--duration", type=float, help="seconds to render (default: all)")
    ap.add_argument("--fps", help="output frame rate (default: input frame rate)")
    ap.add_argument("--jobs", type=int, default=4, help="frames drawn at once (default: 4)")
    ap.add_argument("--codec", default="prores4444", choices=CODECS,
                    help="output video codec: prores4444, h264-444, or png sequence (default: prores4444)")
    ap.add_argument("--params", default="", help="more parameters of the shader, after the look's, e.g. "
                                                  "crt_gamma=2.2,halation_weight=0.1 for royale")
    ap.add_argument("--no-afterglow", action="store_false", dest="afterglow",
                    help="guest and guest-ntsc without their afterglow (AS=0): each frame as if it were the first. "
                         "The other shaders have none, so it changes nothing there")
    ap.add_argument("--runtime", default="auto", choices=RUNTIMES,
                    help="what draws the shader (default: blender where Blender is found, on macOS and Linux; then "
                         "stream (crt-stream) where it's built; then librashader-cli's: metal on macOS, d3d11 on "
                         "Windows, wgpu (on Vulkan) on Linux, falling back to the others the program has)")
    ap.add_argument("--librashader", help="librashader-cli (default: packages/librashader, the PATH or ~/.cargo/bin)")
    ap.add_argument("--blender", help="Blender, for --runtime blender (default: $BLENDER, the usual install places)")
    ap.add_argument("--crt-stream", help="crt-stream, for --runtime stream (default: $CRT_STREAM, packages/librashader, "
                                         "the PATH)")
    ap.add_argument("--preset", help="another shader preset, drawn by librashader-cli with --shader's parameters "
                                     "(default: --shader's, in slang-shaders/)")
    ap.add_argument("--ffmpeg", help="ffmpeg (ffprobe is expected next to it)")
    ap.add_argument("--warmup", type=int, default=0, metavar="N",
                    help="draw the first frame N extra times first, so guest's afterglow starts settled (Blender "
                         "and crt-stream). The video then starts at frame count N: an odd N flips guest-ntsc's phase")
    ap.add_argument("--keep", action="store_true", help="keep the work folder")
    a = ap.parse_args(argv)
    if a.list_masks:
        print(shaders.describe_looks())
        return 0
    if not a.input or not a.output:
        ap.error("the input and output videos are needed")
    shaders.get(a.shader).check_mask(a.mask)

    ffmpeg = locate.find_ffmpeg(a.ffmpeg)
    ffprobe = locate.find_ffmpeg(a.ffmpeg, name="ffprobe")
    exe = find_librashader_or_none(a.librashader)
    blender = find_blender(a.blender)
    stream = find_stream(a.crt_stream) or ""
    info = probe_video(ffprobe, a.input)
    rate = a.fps or info["rate"]
    use_alpha = has_alpha(ffprobe, info["pix_fmt"]) if a.alpha is None else a.alpha
    if a.physical_pixels or a.scale > 0:
        settings = physical_settings(info["width"], info["height"], a.scale, mask=a.mask, triad=a.triad,
                                     triads_per_pixel=a.triads_per_pixel, aspect=a.aspect, params=a.params,
                                     shader=a.shader, afterglow=a.afterglow)
        vf, size = f"fps={rate}", (info["width"], info["height"])
    else:
        settings, fit = standard_settings(a.size, a.lines, a.fit, mask=a.mask, triad=a.triad, params=a.params,
                                          shader=a.shader, afterglow=a.afterglow)
        vf, size = f"fps={rate},{fit}", (a.lines, a.lines)
    total = info["frames"] if not a.start and not a.duration else None
    alpha_str = ", alpha preserved" if use_alpha else ""
    triad = f"triad {settings.triad:g} px" if settings.triad else "the look's own mask size"
    glow = "" if settings.afterglow or not shaders.get(a.shader).afterglow_off else ", no afterglow"
    print(f"{total if total else 'all'} frames, {rate} fps, {settings.describe}, {shaders.get(a.shader).name}, "
          f"{settings.mask} look, {triad}{glow}{alpha_str}", flush=True)

    def progress(done: int, of: Optional[int]) -> None:
        if done % 10 == 0 or (of and done == of):
            print(f"  rendered {done}" + (f"/{of}" if of else ""), flush=True)

    t0 = time.monotonic()
    frames, runtime = render(Path(a.input), Path(a.output), settings, ffmpeg=ffmpeg, librashader=exe,
                             input_size=size, rate=rate, prefilter=vf, start=a.start or None, duration=a.duration,
                             alpha=use_alpha, codec=a.codec, audio=info["audio"], runtime=a.runtime, jobs=a.jobs,
                             preset=Path(a.preset) if a.preset else None, total=total, on_progress=progress, keep=a.keep, blender=blender,
                             warmup=a.warmup, stream=stream)
    how = {"blender": "Blender's GPU module", "stream": "crt-stream (one librashader chain)"}.get(
        runtime, f"librashader's {runtime} runtime")
    print(f"{frames} frames in {time.monotonic() - t0:.0f} s, drawn by {how}")
    print("wrote", a.output)
    if use_alpha and a.codec == "h264-444":
        print("wrote", matte_path(Path(a.output)), "(the alpha, as a matte: white is opaque)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CrtError, locate.NotFound, ValueError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
