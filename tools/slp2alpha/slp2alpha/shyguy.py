"""Draw Yoshi's Story's Shy Guys with your own image.

A Shy Guy is a flat quad textured with three frames of its walk cycle (RGB5A3 images in GrSt.dat). Dolphin
replaces a texture when a PNG named after it is in Load/Textures/GALE01, so one image, fitted to the quad and
saved under the three names, is drawn wherever the game draws a Shy Guy: same path, same turns and hit
reactions. Only what is drawn changes, so replays stay in sync. docs/shy-guy-sprite.md has the details and
tools/shyguy-probe the experiments behind them.

Only ffmpeg is needed to read and scale the image (any format it reads: PNG with transparency works best).
"""

from __future__ import annotations

import json
import struct
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from .disc import Archive, Disc, dolphin_name, image_descs

STAGE_ID = 8  # Yoshi's Story
RGB5A3 = 5

# The Shy Guy's quad is 76:72, the shape of its textures. A variant is one disc's names for them (Dolphin's
# custom texture names); `textures.py diff` in tools/shyguy-probe finds them for a disc.
QUAD_ASPECT = 76 / 72


@dataclass(frozen=True)
class Variant:
    name: str
    textures: Tuple[str, ...]


VARIANTS = (
    Variant("vanilla NTSC 1.02", ("tex1_76x72_7f157caad3c96c68_5", "tex1_76x73_49a3777afd3829a5_5",
                                  "tex1_76x72_d55c2685f515d087_5")),
    Variant("Animelee Complete Edition", ("tex1_152x144_377049d6e3cdf69d_5", "tex1_152x144_4aaf5f4c29082125_5",
                                          "tex1_152x144_874f410ad9681124_5")),
)

# How wide the texture is made, per --scale step. Dolphin doesn't mipmap custom textures, so one much larger
# than the quad's size on screen shimmers; this matches it. The quad is 35 px wide at --scale 1 with the fixed
# camera, and 40 to 115 px (median 56) with the game's own camera, which zooms.
STATIC_CAMERA_WIDTH = 38
FOLLOWING_CAMERA_WIDTH = 76

# Texels this far outside the visible part get its colours (see _bleed).
BLEED_RINGS = 3


class SpriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class Sprite:
    textures: Dict[str, bytes]
    """PNG data to install, by Dolphin's name for the texture it replaces."""
    size: Tuple[int, int]
    variant: str


def find_variant(iso: Path) -> Variant:
    """Which known set of Shy Guy textures this disc has, by hashing the right-sized ones in its GrSt.dat."""
    wanted = {name for v in VARIANTS for name in v.textures}
    sizes = {tuple(int(n) for n in name.split("_")[1].split("x")) for name in wanted}
    try:
        archive = Archive(Disc(iso).read_file("GrSt.dat"))
        present = {dolphin_name(archive, d) for d in image_descs(archive)
                   if d.format == RGB5A3 and (d.width, d.height) in sizes}
    except (KeyError, OSError, ValueError, struct.error) as e:
        raise SpriteError(f"can't read Yoshi's Story's data (GrSt.dat) from {iso}: {e}")
    for variant in VARIANTS:
        if set(variant.textures) <= present:
            return variant
    raise SpriteError(f"{iso} draws Shy Guys with textures this tool doesn't know (it knows "
                      f"{', '.join(v.name for v in VARIANTS)}); tools/shyguy-probe/textures.py diff finds them")


def fit_box(image: Tuple[int, int], texture: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """(x, y, width, height) of the image inside the texture: as big as fits the quad, shape kept, centred."""
    iw, ih = image
    if iw / ih >= QUAD_ASPECT:
        fw, fh = 1.0, QUAD_ASPECT / (iw / ih)
    else:
        fw, fh = (iw / ih) / QUAD_ASPECT, 1.0
    tw, th = texture
    w, h = max(1, round(fw * tw)), max(1, round(fh * th))
    return (tw - w) // 2, (th - h) // 2, w, h


def _image_size(ffprobe: str, image: Path) -> Tuple[int, int]:
    p = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "json", str(image)], capture_output=True, text=True)
    try:
        stream = json.loads(p.stdout)["streams"][0]
        size = int(stream["width"]), int(stream["height"])
    except (ValueError, KeyError, IndexError):
        size = (0, 0)
    if min(size) <= 0:
        raise SpriteError(f"{image} isn't an image ffmpeg can read: {p.stderr.strip()[-200:] or 'no picture found'}")
    return size


def _scaled(ffmpeg: str, image: Path, texture: Tuple[int, int], box: Tuple[int, int, int, int]) -> bytearray:
    """The image as straight-alpha RGBA texels of the texture's size, with transparent padding around it.

    It is scaled with its colours multiplied by its alpha, so transparent pixels don't pull their (arbitrary)
    colour into the edges, and divided again afterwards.
    """
    tw, th = texture
    x, y, w, h = box
    graph = (f"format=gbrap16le,premultiply=inplace=1,scale={w}:{h}:flags=lanczos+accurate_rnd,"
             f"pad={tw}:{th}:{x}:{y}:color=black@0,unpremultiply=inplace=1,format=rgba")
    p = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(image), "-frames:v", "1", "-vf", graph,
                        "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True)
    if p.returncode != 0 or len(p.stdout) != tw * th * 4:
        raise SpriteError(f"couldn't scale {image}: {p.stderr.decode('utf-8', 'replace').strip()[-200:]}")
    return bytearray(p.stdout)


def _bleed(rgba: bytearray, width: int, height: int, rings: int = BLEED_RINGS) -> None:
    """Give fully transparent texels the colour of the visible ones beside them, a few texels out.

    The game filters its textures, so a sprite's edge mixes in the colour of the transparent texels next to
    it, which is black after scaling. That would draw a dark fringe around every edge. Colouring those texels
    like their neighbours (alpha stays 0) makes the edge blend only with what's behind the sprite.
    """
    known = bytearray(1 if a else 0 for a in rgba[3::4])
    if all(known):
        return
    near = [(dy * width + dx, dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]
    frontier = {i for i in range(width * height) if known[i]}
    for _ in range(rings):
        fresh = {}
        for i in frontier:
            y, x = divmod(i, width)
            for step, dx, dy in near:
                if 0 <= x + dx < width and 0 <= y + dy < height and not known[i + step] and (i + step) not in fresh:
                    fresh[i + step] = None
        if not fresh:
            return
        colours = {}
        for j in fresh:
            y, x = divmod(j, width)
            seen = [(rgba[4 * (j + s):4 * (j + s) + 3]) for s, dx, dy in near
                    if 0 <= x + dx < width and 0 <= y + dy < height and known[j + s]]
            colours[j] = [sum(c[k] for c in seen) // len(seen) for k in range(3)]
        for j, (r, g, b) in colours.items():
            rgba[4 * j:4 * j + 3] = bytes((r, g, b))
            known[j] = 1
        frontier = set(fresh)


def _png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\0" + bytes(rgba[y * width * 4:(y + 1) * width * 4]) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def load(ffmpeg: str, ffprobe: str, image: Path, iso: Path, scale: int, static_camera: bool) -> Sprite:
    """Fit an image to the Shy Guy's quad and name the result after this disc's Shy Guy textures."""
    if not image.is_file():
        raise SpriteError(f"--shy-guy-sprite: no such file: {image}")
    variant = find_variant(iso)
    width = (STATIC_CAMERA_WIDTH if static_camera else FOLLOWING_CAMERA_WIDTH) * scale
    texture = (width, round(width / QUAD_ASPECT))
    rgba = _scaled(ffmpeg, image, texture, fit_box(_image_size(ffprobe, image), texture))
    _bleed(rgba, *texture)
    png = _png(*texture, rgba)
    return Sprite({name: png for name in variant.textures}, texture, variant.name)
