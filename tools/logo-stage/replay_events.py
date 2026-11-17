"""A minimal Slippi (.slp) reader for the fighter positions the camera checks need.

Only the raw event stream is read: the Event Payloads table, then Post-Frame Update (0x38) events. Payload layout
from the Slippi spec (https://github.com/project-slippi/slippi-wiki, SPEC.md): frame i32 at 0, port u8 at 4,
follower flag u8 at 5, internal character id u8 at 6, action state u16 at 7, x f32 at 9, y f32 at 13, facing f32
at 17, ground/air state u8 at 0x2E.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Tuple

HEADER = b"{U\x03raw[$U#l"
POST_FRAME = 0x38

WAIT = 14
CLIFF_WAIT = 253


@dataclass(frozen=True)
class Fighter:
    x: float
    y: float
    facing: float
    state: int
    airborne: bool
    character: int


def events(path) -> Iterator[Tuple[int, bytes]]:
    """(command byte, payload) of every event in the raw stream."""
    data = Path(path).read_bytes()
    if not data.startswith(HEADER):
        raise ValueError(f"{Path(path).name}: not a Slippi replay")
    start = len(HEADER) + 4
    length = struct.unpack(">I", data[len(HEADER):start])[0]
    if length == 0:  # still being written: the stream runs to the metadata or the end
        end = data.find(b"U\x08metadata", start)
        length = (end if end != -1 else len(data)) - start
    raw = data[start:start + length]
    sizes = {0x35: raw[1]}
    for i in range(2, 1 + raw[1], 3):
        sizes[raw[i]] = struct.unpack(">H", raw[i + 1:i + 3])[0]
    pos = 0
    while pos < len(raw):
        size = sizes[raw[pos]]
        if pos + 1 + size > len(raw):
            break
        yield raw[pos], raw[pos + 1:pos + 1 + size]
        pos += 1 + size


def fighter_frames(path) -> Dict[int, Dict[int, Fighter]]:
    """frame -> port -> Fighter (followers such as Nana are left out)."""
    out: Dict[int, Dict[int, Fighter]] = {}
    for cmd, p in events(path):
        if cmd != POST_FRAME or len(p) <= 0x2E or p[5]:
            continue
        frame = struct.unpack(">i", p[:4])[0]
        state = struct.unpack(">H", p[7:9])[0]
        x, y, facing = struct.unpack(">3f", p[9:21])
        out.setdefault(frame, {})[p[4]] = Fighter(x, y, facing, state, bool(p[0x2E]), p[6])
    return out
