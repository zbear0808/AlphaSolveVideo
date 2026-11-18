"""Read files from a GameCube disc image and name their textures the way Dolphin does.

Dolphin looks custom textures up by name: tex1_<width>x<height>_<xxHash64 of the texture bytes>_<GX format>.png
(paletted textures also carry a hash of their palette, mipmapped ones an "_m"). The bytes it hashes are the ones
the game uploads, which for Melee are the image data inside the .dat files on the disc, so the names can be
worked out from the ISO alone.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple


class Disc:
    """A GameCube disc image (.iso/.gcm): its file system table and the files in it."""

    def __init__(self, path):
        self.path = Path(path)
        header = self.read(0, 0x440)
        self.game_id = header[:6].decode("ascii", "replace")
        self.revision = header[7]
        fst_offset, fst_size = struct.unpack(">II", header[0x424:0x42C])
        fst = self.read(fst_offset, fst_size)
        count = struct.unpack(">I", fst[8:12])[0]  # the root entry's "length" is the number of entries
        names = count * 12
        self.files: Dict[str, Tuple[int, int]] = {}
        dir_ends: List[int] = []
        folders = [""]
        for i in range(1, count):
            while dir_ends and i >= dir_ends[-1]:
                dir_ends.pop()
                folders.pop()
            kind_and_name, offset, length = struct.unpack(">III", fst[i * 12:i * 12 + 12])
            start = names + (kind_and_name & 0xFFFFFF)
            name = fst[start:fst.index(b"\0", start)].decode("shift_jis", "replace")
            if kind_and_name >> 24:  # directory: `length` is the index after its last entry
                folders.append(folders[-1] + name + "/")
                dir_ends.append(length)
            else:
                self.files[folders[-1] + name] = (offset, length)

    def read(self, offset: int, size: int) -> bytes:
        with open(self.path, "rb") as f:
            f.seek(offset)
            return f.read(size)

    def read_file(self, name: str) -> bytes:
        offset, length = self.files[name]
        return self.read(offset, length)


class Archive:
    """A HAL .dat archive: a data block, a table of the words in it that are pointers, and named roots."""

    def __init__(self, blob: bytes):
        self.file_size, self.data_size, reloc_count, root_count, ref_count = struct.unpack(">5I", blob[:20])
        self.data = blob[0x20:0x20 + self.data_size]
        table = 0x20 + self.data_size
        self.relocs = {struct.unpack(">I", blob[table + 4 * i:table + 4 * i + 4])[0] for i in range(reloc_count)}
        nodes = table + 4 * reloc_count
        strings = blob[nodes + 8 * (root_count + ref_count):self.file_size]

        def name(at: int) -> str:
            return strings[at:strings.index(b"\0", at)].decode("ascii", "replace")

        def node(i: int) -> Tuple[str, int]:
            offset, name_at = struct.unpack(">II", blob[nodes + 8 * i:nodes + 8 * i + 8])
            return name(name_at), offset

        self.roots = [node(i) for i in range(root_count)]
        self.refs = [node(root_count + i) for i in range(ref_count)]

    def u32(self, offset: int) -> int:
        return struct.unpack(">I", self.data[offset:offset + 4])[0]

    def u16(self, offset: int) -> int:
        return struct.unpack(">H", self.data[offset:offset + 2])[0]


GX_FORMATS = {0: "I4", 1: "I8", 2: "IA4", 3: "IA8", 4: "RGB565", 5: "RGB5A3", 6: "RGBA8",
              8: "C4", 9: "C8", 10: "C14X2", 14: "CMPR"}
PALETTED = (8, 9, 10)
# format -> (block width, block height, bits per texel)
_BLOCKS = {0: (8, 8, 4), 1: (8, 4, 8), 2: (8, 4, 8), 3: (4, 4, 16), 4: (4, 4, 16), 5: (4, 4, 16), 6: (4, 4, 32),
           8: (8, 8, 4), 9: (8, 4, 8), 10: (4, 4, 16), 14: (8, 8, 4)}


def texture_size(width: int, height: int, fmt: int) -> int:
    """Bytes of one mip level of a GX texture (the size is rounded up to whole blocks)."""
    bw, bh, bits = _BLOCKS[fmt]
    return -(-width // bw) * -(-height // bh) * bw * bh * bits // 8


@dataclass(frozen=True)
class ImageDesc:
    """An HSD_ImageDesc: where a texture's pixels are in the archive's data block, and their layout."""
    desc_offset: int
    data_offset: int
    width: int
    height: int
    format: int
    mipmap: int


def image_descs(archive: Archive) -> Iterator[ImageDesc]:
    """Every texture descriptor in an archive: a pointer to the pixels, u16 width, u16 height, u32 format,
    u32 mipmap flag. Found by shape (a pointer word followed by plausible sizes), not by walking the models."""
    data = archive.data
    for offset in sorted(archive.relocs):
        if offset + 0x18 > len(data):
            continue
        pixels = archive.u32(offset)
        width, height, fmt = archive.u16(offset + 4), archive.u16(offset + 6), archive.u32(offset + 8)
        if 0 < pixels < len(data) and 4 <= width <= 1024 and 4 <= height <= 1024 and fmt in GX_FORMATS:
            yield ImageDesc(offset, pixels, width, height, fmt, archive.u32(offset + 12))


def dolphin_name(archive: Archive, desc: ImageDesc) -> Optional[str]:
    """The name Dolphin gives this texture; None for paletted or mipmapped ones (their names need more)."""
    if desc.format in PALETTED or desc.mipmap:
        return None
    size = texture_size(desc.width, desc.height, desc.format)
    pixels = archive.data[desc.data_offset:desc.data_offset + size]
    if len(pixels) < size:
        return None
    return f"tex1_{desc.width}x{desc.height}_{xxh64(pixels):016x}_{desc.format}"


def decode_rgb5a3(blob: bytes, width: int, height: int):
    """RGB5A3 pixels (GX: 4x4 tiles of big-endian 16-bit words) as a (height, width, 4) uint8 array."""
    import numpy as np

    tiles_x, tiles_y = -(-width // 4), -(-height // 4)
    words = np.frombuffer(blob[:tiles_x * tiles_y * 32], dtype=">u2").astype(np.int32)
    words = words.reshape(tiles_y, tiles_x, 4, 4).transpose(0, 2, 1, 3).reshape(tiles_y * 4, tiles_x * 4)
    words = words[:height, :width]
    opaque = (words & 0x8000) != 0
    alpha3 = (words >> 12) & 7
    out = np.zeros((height, width, 4), np.uint8)
    for channel, shift5, shift4 in ((0, 10, 8), (1, 5, 4), (2, 0, 0)):
        c5 = (words >> shift5) & 31
        c4 = (words >> shift4) & 15
        out[..., channel] = np.where(opaque, (c5 << 3) | (c5 >> 2), c4 * 17)
    out[..., 3] = np.where(opaque, 255, (alpha3 << 5) | (alpha3 << 2) | (alpha3 >> 1))
    return out


# xxHash64 as Dolphin uses it (XXH64 with seed 0). Checked against the reference C implementation for every
# length from 0 to 130 and for 1000-1003 bytes.
_P1, _P2, _P3, _P4, _P5 = (11400714785074694791, 14029467366897019727, 1609587929392839161, 9650029242287828579,
                           2870177450012600261)
_M = (1 << 64) - 1


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (64 - r))) & _M


def _round(acc: int, lane: int) -> int:
    return (_rotl((acc + lane * _P2) & _M, 31) * _P1) & _M


def _merge(acc: int, val: int) -> int:
    return (((acc ^ _round(0, val)) * _P1) + _P4) & _M


def xxh64(data: bytes, seed: int = 0) -> int:
    n, i = len(data), 0
    if n >= 32:
        v1, v2, v3, v4 = (seed + _P1 + _P2) & _M, (seed + _P2) & _M, seed & _M, (seed - _P1) & _M
        while i + 32 <= n:
            a, b, c, d = struct.unpack_from("<4Q", data, i)
            v1, v2, v3, v4 = _round(v1, a), _round(v2, b), _round(v3, c), _round(v4, d)
            i += 32
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _M
        for v in (v1, v2, v3, v4):
            h = _merge(h, v)
    else:
        h = (seed + _P5) & _M
    h = (h + n) & _M
    while i + 8 <= n:
        h = ((_rotl(h ^ _round(0, struct.unpack_from("<Q", data, i)[0]), 27) * _P1) + _P4) & _M
        i += 8
    if i + 4 <= n:
        h = ((_rotl(h ^ ((struct.unpack_from("<I", data, i)[0] * _P1) & _M), 23) * _P2) + _P3) & _M
        i += 4
    while i < n:
        h = (_rotl(h ^ ((data[i] * _P5) & _M), 11) * _P1) & _M
        i += 1
    h ^= h >> 33
    h = (h * _P2) & _M
    h ^= h >> 29
    h = (h * _P3) & _M
    h ^= h >> 32
    return h
