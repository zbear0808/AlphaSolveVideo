"""Minimal reader for Slippi replay files (.slp).

A .slp file is a UBJSON object: {"raw": <binary event stream>, "metadata": {...}}.
Only what the renderer needs is decoded: replay version, stage, the frame range and the name tags.
"""

from __future__ import annotations

import string
import struct
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EVENT_PAYLOAD_SIZES = 0x35
EVENT_GAME_START = 0x36
EVENT_POST_FRAME = 0x38
EVENT_GAME_END = 0x39

FIRST_FRAME = -123  # Slippi's frame index of the first frame after the game starts loading

# Name tags, in the Game Start event (offsets from its command byte). The game info block's player entries hold
# each player's tag slot (0x78: none) and whether they're human; replays from v1.3.0 on also hold each tag's text:
# the 16 bytes from the slot's 8-byte name onwards, which Slippi's playback copies back into the slot.
PORTS = 4
PLAYER_STATUS = 0x5 + 0x60 + 0x1   # 0: human (0x24 apart)
PLAYER_NAMETAG_ID = 0x5 + 0x60 + 0xA
PLAYER_STRIDE = 0x24
NO_NAMETAG = 0x78
NAMETAG_TEXT = 0x161               # 0x10 apart
NAMETAG_STRIDE = 0x10
# The slot's name is 8 bytes. Past it are the tag's rumble and handicap settings, then the next slot's data.
NAMETAG_MAX_BYTES = 8
# What the tag's font draws, as seen in renders. One byte each: letters, digits, space and . , ' - (other ASCII
# bytes are drawn as the wrong glyphs). Two bytes each (Shift-JIS): the other ASCII symbols in their full-width
# forms, except ` " and \ (drawn blank), and kana. Kanji and the separate voicing marks are drawn blank or broken.
NAMETAG_PLAIN = frozenset(string.ascii_letters + string.digits + " .,'-")
NAMETAG_WIDE = frozenset(c for c in string.punctuation if c not in "`\"\\" and c not in NAMETAG_PLAIN)
NAMETAG_KANA = frozenset([chr(c) for c in range(0x3041, 0x3094)] + [chr(c) for c in range(0x30A1, 0x30F7)] + ["ー", "・"])


@dataclass
class ReplayInfo:
    path: Path
    version: str
    stage_id: int
    first_frame: int
    last_frame: int
    has_game_end: bool
    nametags: List[Optional[str]] = field(default_factory=lambda: [None] * PORTS)  # what each port's tag shows

    @property
    def game_frames(self) -> int:
        return self.last_frame - self.first_frame + 1


class ReplayError(ValueError):
    pass


def _raw_bounds(data: bytes, name: str) -> Tuple[int, int]:
    """Where the event stream starts in the file, and its length."""
    header = b"{U\x03raw[$U#l"
    if not data.startswith(header):
        raise ReplayError(f"{name}: not a Slippi replay (unexpected header)")
    raw_len = struct.unpack(">I", data[len(header):len(header) + 4])[0]
    raw_start = len(header) + 4
    if raw_len == 0:  # replay still being written; the stream runs until the metadata marker or EOF
        end = data.find(b"U\x08metadata", raw_start)
        raw_len = (end if end != -1 else len(data)) - raw_start
    return raw_start, raw_len


def read_replay(path) -> ReplayInfo:
    path = Path(path)
    data = path.read_bytes()
    raw_start, raw_len = _raw_bounds(data, path.name)
    raw = data[raw_start:raw_start + raw_len]

    metadata = _read_metadata(data[raw_start + raw_len:])
    version, stage_id, first, last, has_end = _scan_events(raw, path.name)

    meta_last = metadata.get("lastFrame") if isinstance(metadata, dict) else None
    if isinstance(meta_last, int):
        last = max(last, meta_last) if last is not None else meta_last
    if last is None:
        raise ReplayError(f"{path.name}: no frames found")
    return ReplayInfo(path=path, version=version, stage_id=stage_id,
                      first_frame=first if first is not None else FIRST_FRAME,
                      last_frame=last, has_game_end=has_end, nametags=_read_nametags(data, path.name))


def _game_start(data: bytes, name: str) -> Tuple[int, int]:
    """The Game Start event: its command byte's offset in the file, and its payload size."""
    raw_start, raw_len = _raw_bounds(data, name)
    if raw_len < 2 or data[raw_start] != EVENT_PAYLOAD_SIZES:
        raise ReplayError(f"{name}: event stream does not start with the payload-size table")
    table_len = data[raw_start + 1]
    sizes = {data[i]: struct.unpack(">H", data[i + 1:i + 3])[0]
             for i in range(raw_start + 2, raw_start + 1 + table_len, 3)}
    pos = raw_start + 1 + table_len
    if data[pos] != EVENT_GAME_START or EVENT_GAME_START not in sizes:
        raise ReplayError(f"{name}: no Game Start event after the payload-size table")
    return pos, sizes[EVENT_GAME_START]


def _has_nametag_text(size: int) -> bool:
    return size >= NAMETAG_TEXT + PORTS * NAMETAG_STRIDE - 1


def _read_nametags(data: bytes, name: str) -> List[Optional[str]]:
    """What each port's name tag shows: None where there's none (or the replay is too old to hold its text)."""
    try:
        pos, size = _game_start(data, name)
    except (ReplayError, IndexError, struct.error):
        return [None] * PORTS
    if not _has_nametag_text(size):
        return [None] * PORTS
    out: List[Optional[str]] = []
    for port in range(PORTS):
        text = data[pos + NAMETAG_TEXT + port * NAMETAG_STRIDE:][:NAMETAG_STRIDE]
        shown = (data[pos + PLAYER_STATUS + port * PLAYER_STRIDE] == 0
                 and data[pos + PLAYER_NAMETAG_ID + port * PLAYER_STRIDE] != NO_NAMETAG and text[0] != 0)
        out.append(decode_nametag(text) if shown else None)
    return out


def decode_nametag(text: bytes) -> str:
    """A tag's text as it reads: Shift-JIS up to its terminator, full-width letters as plain ones."""
    end = text.find(b"\0")
    return unicodedata.normalize("NFKC", text[:end if end != -1 else len(text)].decode("cp932", "replace"))


def encode_nametag(text: str) -> bytes:
    """Text for a name tag as Melee stores it. Letters, digits, spaces and . , ' - take one byte each; other
    symbols and kana are Shift-JIS, two bytes each, the symbols in their full-width forms."""
    out = bytearray()
    for c in text:
        if "\uff01" <= c <= "\uff5e":   # typed full-width: the same character
            c = chr(ord(c) - 0xFEE0)
        if c in NAMETAG_PLAIN:
            out += c.encode("ascii")
        elif c in NAMETAG_WIDE:
            out += chr(ord(c) + 0xFEE0).encode("cp932")
        elif c in NAMETAG_KANA:
            out += c.encode("cp932")
        else:
            raise ValueError(f"name tag {text!r}: Melee's font doesn't draw {c!r} (it has letters, digits, spaces, "
                             "most ASCII symbols but ` \" and \\, and kana)")
    if len(out) > NAMETAG_MAX_BYTES:
        raise ValueError(f"name tag {text!r} is too long: a tag holds {NAMETAG_MAX_BYTES} bytes, which is 8 letters, "
                         f"digits, spaces or . , ' -, and 2 bytes for anything else (this needs {len(out)})")
    return bytes(out)


def write_nametags(src: Path, dst: Path, tags: Dict[int, bytes]) -> None:
    """Copy a replay with these ports' name tags rewritten (port 0 is P1); b"" hides the tag. Only the text
    changes, which nothing in the game reads but the tag's drawing. A port must already show a tag: one without
    has no tag slot to write to."""
    src, dst = Path(src), Path(dst)
    data = bytearray(src.read_bytes())
    pos, size = _game_start(data, src.name)
    if not _has_nametag_text(size):
        raise ReplayError(f"{src.name}: replay v{'.'.join(str(b) for b in data[pos + 1:pos + 4])} is too old to hold "
                          "name tags (they're recorded from v1.3.0 on)")
    shown = _read_nametags(bytes(data), src.name)
    for port, text in tags.items():
        if shown[port] is None:
            have = [f"P{p + 1}" for p, t in enumerate(shown) if t is not None]
            raise ReplayError(f"{src.name}: P{port + 1} has no name tag to change "
                              f"({'tags: ' + ', '.join(have) if have else 'no player has one'})")
        if len(text) > NAMETAG_MAX_BYTES:
            raise ValueError(f"name tag of {len(text)} bytes: a tag holds {NAMETAG_MAX_BYTES}")
        at = pos + NAMETAG_TEXT + port * NAMETAG_STRIDE
        # The terminator goes right after the text; the recorded bytes past it (the tag's settings) stay.
        data[at:at + len(text) + 1] = text + b"\0"
    dst.write_bytes(bytes(data))


def clip_range(replay: ReplayInfo, start: Optional[int] = None, end: Optional[int] = None) -> Tuple[int, int]:
    """First and last game frame (both included) to record; the whole replay unless start or end is given.

    Frame FIRST_FRAME is only where playback starts from, and the frame after it never reaches Dolphin's
    recording either, so a range that begins there records one frame fewer than it spans. A start before it
    is clamped, and so is an end past the replay's last frame.
    """
    first = FIRST_FRAME + 1 if start is None else max(start, FIRST_FRAME + 1)
    last = replay.last_frame if end is None else min(end, replay.last_frame)
    if last < first:
        raise ReplayError(f"{replay.path.name}: no frames to render from {first} to {last} "
                          f"(the replay has frames {replay.first_frame} to {replay.last_frame})")
    return first, last


def _scan_events(raw: bytes, name: str) -> Tuple[str, int, Optional[int], Optional[int], bool]:
    if not raw or raw[0] != EVENT_PAYLOAD_SIZES:
        raise ReplayError(f"{name}: event stream does not start with the payload-size table")
    table_len = raw[1]
    sizes: Dict[int, int] = {EVENT_PAYLOAD_SIZES: table_len}
    for i in range(2, 1 + table_len, 3):
        sizes[raw[i]] = struct.unpack(">H", raw[i + 1:i + 3])[0]

    version = "unknown"
    stage_id = -1
    first: Optional[int] = None
    last: Optional[int] = None
    has_end = False
    pos = 0
    n = len(raw)
    while pos < n:
        cmd = raw[pos]
        size = sizes.get(cmd)
        if size is None:
            raise ReplayError(f"{name}: unknown event 0x{cmd:02x} at byte {pos}")
        if pos + 1 + size > n:
            break  # truncated final event
        if cmd == EVENT_GAME_START:
            version = ".".join(str(b) for b in raw[pos + 1:pos + 4])
            stage_id = struct.unpack(">H", raw[pos + 0x13:pos + 0x15])[0]
        elif cmd == EVENT_POST_FRAME:
            frame = struct.unpack(">i", raw[pos + 1:pos + 5])[0]
            first = frame if first is None else min(first, frame)
            last = frame if last is None else max(last, frame)
        elif cmd == EVENT_GAME_END:
            has_end = True
        pos += 1 + size
    return version, stage_id, first, last, has_end


def _read_metadata(rest: bytes) -> Any:
    """Decode the "metadata" value that follows the raw stream, if present."""
    marker = b"U\x08metadata"
    i = rest.find(marker)
    if i == -1:
        return {}
    try:
        value, _ = _ubjson_value(rest, i + len(marker))
        return value
    except (IndexError, struct.error, ValueError):
        return {}


def _ubjson_value(buf: bytes, pos: int, marker: Optional[int] = None):
    t = buf[pos] if marker is None else marker
    if marker is None:
        pos += 1
    if t == ord("{"):
        obj = {}
        while buf[pos] != ord("}"):
            key, pos = _ubjson_string(buf, pos)
            obj[key], pos = _ubjson_value(buf, pos)
        return obj, pos + 1
    if t == ord("["):
        arr = []
        while buf[pos] != ord("]"):
            item, pos = _ubjson_value(buf, pos)
            arr.append(item)
        return arr, pos + 1
    if t == ord("S"):
        length, pos = _ubjson_value(buf, pos)
        return buf[pos:pos + length].decode("utf-8", "replace"), pos + length
    fixed = {ord("i"): ">b", ord("U"): ">B", ord("I"): ">h", ord("l"): ">i",
             ord("L"): ">q", ord("d"): ">f", ord("D"): ">d"}
    if t in fixed:
        fmt = fixed[t]
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, buf[pos:pos + size])[0], pos + size
    if t == ord("T"):
        return True, pos
    if t == ord("F"):
        return False, pos
    if t == ord("Z"):
        return None, pos
    raise ValueError(f"unsupported UBJSON type {chr(t)!r}")


def _ubjson_string(buf: bytes, pos: int):
    length, pos = _ubjson_value(buf, pos)  # object keys are strings without the "S" marker
    return buf[pos:pos + length].decode("utf-8", "replace"), pos + length
