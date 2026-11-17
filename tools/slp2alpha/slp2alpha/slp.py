"""Minimal reader for Slippi replay files (.slp).

A .slp file is a UBJSON object: {"raw": <binary event stream>, "metadata": {...}}.
Only what the renderer needs is decoded: replay version, stage, and the frame range.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

EVENT_PAYLOAD_SIZES = 0x35
EVENT_GAME_START = 0x36
EVENT_POST_FRAME = 0x38
EVENT_GAME_END = 0x39

FIRST_FRAME = -123  # Slippi's frame index of the first frame after the game starts loading


@dataclass
class ReplayInfo:
    path: Path
    version: str
    stage_id: int
    first_frame: int
    last_frame: int
    has_game_end: bool

    @property
    def game_frames(self) -> int:
        return self.last_frame - self.first_frame + 1


class ReplayError(ValueError):
    pass


def read_replay(path) -> ReplayInfo:
    path = Path(path)
    data = path.read_bytes()
    header = b"{U\x03raw[$U#l"
    if not data.startswith(header):
        raise ReplayError(f"{path.name}: not a Slippi replay (unexpected header)")
    raw_len = struct.unpack(">I", data[len(header):len(header) + 4])[0]
    raw_start = len(header) + 4
    if raw_len == 0:  # replay still being written; the stream runs until the metadata marker or EOF
        end = data.find(b"U\x08metadata", raw_start)
        raw_len = (end if end != -1 else len(data)) - raw_start
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
                      last_frame=last, has_game_end=has_end)


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
