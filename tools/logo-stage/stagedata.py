#!/usr/bin/env python3
"""Main-stage geometry and fixed-camera settings of the six legal stages, read from the stage .dat files on the ISO.

    python3 tools/logo-stage/stagedata.py [--stage NAME_OR_ID] [--json] [--lines] [--iso PATH]

Without --stage it prints one row per stage (ledge, top surface, camera); with --stage it also lists the
platforms. --lines adds every collision line, --json prints everything as JSON. The ISO defaults to the one set
in the Slippi Launcher. From Python: `load_stage(31)` gives a StageGeometry (read once per process).

Where the numbers come from. Each stage file has a `coll_data` root (HSDRaw: SBM_Coll_Data, the decompiled game:
MapCollData) and a `grGroundParam` root. All big-endian; a pointer is an offset into the data block.

    coll_data     +0x00 vertices*  +0x04 count    8 bytes each: f32 x, f32 y
                  +0x08 lines*     +0x0C count    0x10 bytes each, see below
                  +0x10 five (s16 start, s16 count) pairs: floors, ceilings, right walls, left walls, dynamic
                  +0x24 joints*    +0x28 count    0x28 bytes each: the same five pairs for that joint's lines,
                                                  f32 left/bottom/right/top bounds, s16 vertex start and count
    line          +0x00 s16 vertex 0   +0x02 s16 vertex 1    floors run left to right
                  +0x04 s16 previous   +0x06 s16 next         neighbouring line on the same surface, -1 for none
                  +0x08 s16 alt prev   +0x0A s16 alt next     used instead while another joint is active
                  +0x0C u16 kind       1 floor, 2 ceiling, 4 right wall, 8 left wall; 0x10 on dynamic lines only
                  +0x0E u16 property   0x100 drop-through, 0x200 ledge grab, 0x400 dynamic; low byte: material
    grGroundParam +0x00 f32 stage scale; camera +0x50 f32 eye x, y, z, +0x5C fov, +0x60 vertical angle,
                  +0x64 horizontal angle (degrees)

A line's number is the "last ground id" Slippi records for a fighter standing on it.

Scale. The game multiplies every collision coordinate by the stage scale when it loads them (mpLibLoad), so the
file's Battlefield is 85.5 wide per side but plays at 68.4. The scale is 0.8 on Battlefield, 0.7 on Yoshi's
Story, 0.75 on Fountain of Dreams and 1 on the rest. Everything in a StageGeometry is already scaled, in the
units of the positions in a replay. The camera is not scaled.

Ledges. A ledge is not an object: it is a floor line whose property has the 0x200 bit (the decompiled game's
LINE_FLAG_LEDGE), and no vertex is flagged. To grab the stage's left edge the game looks for ledge-flagged
floors that touch the fighter's grab box and takes the left end of the leftmost one; for the right edge, the
right end of the rightmost (mpLib_80051BA8_Floor, called from mpColl_80044164 and mpColl_800443C4). So the ledge
points are the outer ends of the outermost ledge floors, one group on each side of the stage. A joint with
ledge floors on one side only (the Rock form of Pokémon Stadium) or none (Battlefield's platforms) is not the
main stage. On Battlefield, Dream Land, Final Destination and Pokémon Stadium those floors continue the flat
top out to the edge; on Yoshi's Story they slope down to (+-56, -3.5), and on Fountain of Dreams they sit 0.62
above the flat top.

Joints. A joint is a group of lines that the stage can hide or move as one. The main stage is the joint with the
ledges. The vertices of any other joint are in that joint's own space, which is the world only if the stage never
moves it: Dream Land's three platforms are separate joints but stand still, while Yoshi's Story's Randall and
Fountain of Dreams' three platforms are drawn around the joint's origin and put in place by the stage model, so
their coordinates here are not where they are in a match. Pokémon Stadium holds the lines of every form. Dynamic
lines (the rotating shape in Pokémon Stadium) are re-classified as floor, wall or ceiling every frame from their
slope, so their stored kind means nothing and they are left out of the platforms.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple, Union

_SLP2ALPHA = Path(__file__).resolve().parents[1] / "slp2alpha"
if str(_SLP2ALPHA) not in sys.path:
    sys.path.insert(0, str(_SLP2ALPHA))
from slp2alpha import locate  # noqa: E402
from slp2alpha.disc import Disc  # noqa: E402

STAGE_FILES: Dict[int, Tuple[str, str]] = {
    2: ("Fountain of Dreams", "GrIz.dat"),
    3: ("Pokémon Stadium", "GrPs.dat"),
    8: ("Yoshi's Story", "GrSt.dat"),
    28: ("Dream Land", "GrOp.dat"),
    31: ("Battlefield", "GrNBa.dat"),
    32: ("Final Destination", "GrNLa.dat"),
}

# Facts about joints that the file does not say; from the decompiled game and from test replays.
STAGE_NOTES: Dict[int, Tuple[str, ...]] = {
    2: ("joints 0-2 are the three platforms and are in joint space (all three read x +-14.25 at y 1.125); in "
        "replays the top one (joint 2) stands at y 42.75 and the side ones rise and fall (y 5.9 to 27.4 seen)",),
    3: ("joints 4 and 6 are the stage at the start of a match and for all of a frozen Stadium: joint 6 holds the "
        "ends of the top surface with the ledges, joint 4 the flat middle (line 34) and the two platforms",
        "the other joints exist only during a transformation, and rise and sink with it: Fire is joints 1 and 2, "
        "Grass 3, Rock 5, Water 7 and 0 (the rotating shape); from the game's joint table and the model names in "
        "the file, and a replay confirms Normal and Water",),
    8: ("joint 0 is Randall the cloud, in joint space; joint 1 holds the stage and the three platforms on it",),
    28: ("joints 0-2 are the three platforms; they stand still (constant height in 3 replays), so these are "
         "world coordinates",),
}

EPS = 1e-3  # units: lines this close in height count as level
LEDGE_GAP = 10.0  # the ledge floors of a stage form two groups at least this far apart
KINDS = {1: "floor", 2: "ceiling", 4: "right wall", 8: "left wall"}
DROP_THROUGH, LEDGE = 0x100, 0x200


def f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


# ---- the .dat archive ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Dat:
    """A HAL .dat archive: its data block, the offsets in it that hold pointers, and its named roots."""
    data: bytes
    relocs: FrozenSet[int]
    roots: Dict[str, int]  # name -> offset in the data block


def read_dat(blob: bytes) -> Dat:
    """Header (big-endian u32): file size, data size, relocation count, root count, reference count; 0x20 bytes
    in all. Then the data block, the relocation table (u32 offsets), root_count + ref_count nodes of (data offset,
    name offset) and the string table, which the name offsets count from and which runs to the end of the file."""
    file_size, data_size, reloc_count, root_count, ref_count = struct.unpack_from(">5I", blob, 0)
    table = 0x20 + data_size
    nodes = table + 4 * reloc_count
    strings = nodes + 8 * (root_count + ref_count)
    if file_size > len(blob) or strings > file_size:
        raise ValueError("not a .dat archive (the header does not fit the file)")
    relocs = frozenset(struct.unpack_from(f">{reloc_count}I", blob, table))
    roots = {}
    for i in range(root_count):
        offset, name_at = struct.unpack_from(">II", blob, nodes + 8 * i)
        end = blob.index(b"\0", strings + name_at, file_size)
        roots[blob[strings + name_at:end].decode("ascii", "replace")] = offset
    return Dat(blob[0x20:table], relocs, roots)


# ---- the geometry ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Camera:
    """The fixed camera in grGroundParam: position (not scaled), field of view and angles in degrees."""
    eye: Tuple[float, float, float]
    fov_deg: float
    vert_angle_deg: float
    horz_angle_deg: float


@dataclass(frozen=True)
class Line:
    index: int
    kind: str  # floor, ceiling, right wall, left wall (as stored: wrong for dynamic lines)
    x0: float
    y0: float
    x1: float
    y1: float
    flags: int  # the u16 at +0x0C
    props: int  # the u16 at +0x0E
    material: int
    drop_through: bool
    ledge: bool
    disabled: bool  # the 0x10 bit of the kind (HSDRaw's name for it); only dynamic lines have it
    dynamic: bool
    joint: int  # the joint that owns the line, -1 for none
    prev: int
    next: int
    alt_prev: int
    alt_next: int

    @property
    def left(self) -> Tuple[float, float]:
        return (self.x0, self.y0) if self.x0 <= self.x1 else (self.x1, self.y1)

    @property
    def right(self) -> Tuple[float, float]:
        return (self.x1, self.y1) if self.x0 <= self.x1 else (self.x0, self.y0)


@dataclass(frozen=True)
class Joint:
    index: int
    floors: Tuple[int, int]  # first line, count; likewise for the rest
    ceilings: Tuple[int, int]
    right_walls: Tuple[int, int]
    left_walls: Tuple[int, int]
    dynamic: Tuple[int, int]
    bounds: Tuple[float, float, float, float]  # left, bottom, right, top
    vertices: Tuple[int, int]


@dataclass(frozen=True)
class MainStage:
    top_y: float  # height of the longest flat floor of the main joint
    top_x: Tuple[float, float]  # extent of the floors level with it (YS: the flat part, not the slopes to the ledge)
    ledge_left: Tuple[float, float]  # grab points (x, y)
    ledge_right: Tuple[float, float]
    joint: int
    lines: Tuple[int, ...]  # every drop-through-free floor of that joint: ledge pieces, slopes, flat top


@dataclass(frozen=True)
class Platform:
    line: int
    x0: float
    y0: float
    x1: float
    y1: float
    drop_through: bool
    movable: bool  # belongs to a joint other than the main stage's, so the stage may move it
    joint: int
    ledge: bool


@dataclass(frozen=True)
class StageGeometry:
    stage_id: int
    name: str
    dat: str
    scale: float
    camera: Camera
    main_stage: MainStage
    platforms: Tuple[Platform, ...]  # every floor that is not part of the main stage
    lines: Tuple[Line, ...]
    joints: Tuple[Joint, ...]
    notes: Tuple[str, ...] = ()


def parse_stage(stage_id: int, dat: Dat) -> StageGeometry:
    name, file = STAGE_FILES[stage_id]
    for root in ("coll_data", "grGroundParam"):
        if root not in dat.roots:
            raise ValueError(f"{file}: no {root} root, is it a stage file?")
    data = dat.data

    param = dat.roots["grGroundParam"]
    scale = struct.unpack_from(">f", data, param)[0]
    eye = struct.unpack_from(">3f", data, param + 0x50)
    fov, vert, horz = struct.unpack_from(">3f", data, param + 0x5C)

    coll = dat.roots["coll_data"]
    for at in (coll, coll + 0x08, coll + 0x24):
        if at not in dat.relocs:
            raise ValueError(f"{file}: coll_data +0x{at - coll:02x} is not a pointer, so the layout differs")
    vtx_at, vtx_n, line_at, line_n = struct.unpack_from(">IiIi", data, coll)
    global_ranges = struct.unpack_from(">10h", data, coll + 0x10)
    joint_at, joint_n = struct.unpack_from(">Ii", data, coll + 0x24)
    for what, at, count, size in (("vertices", vtx_at, vtx_n, 8), ("lines", line_at, line_n, 0x10),
                                  ("joints", joint_at, joint_n, 0x28)):
        if count < 0 or at + count * size > len(data):
            raise ValueError(f"{file}: the coll_data {what} do not fit in the data block")

    verts = []
    for i in range(vtx_n):
        x, y = struct.unpack_from(">ff", data, vtx_at + 8 * i)
        verts.append((f32(scale * x), f32(scale * y)))

    joints = []
    owner: Dict[int, int] = {}
    dynamic = set(range(global_ranges[8], global_ranges[8] + global_ranges[9]))
    for i in range(joint_n):
        raw = struct.unpack_from(">10h4f2h", data, joint_at + 0x28 * i)
        pairs = [(raw[k], raw[k + 1]) for k in range(0, 10, 2)]
        bounds = (f32(scale * raw[10]), f32(scale * raw[11]), f32(scale * raw[12]), f32(scale * raw[13]))
        joints.append(Joint(i, pairs[0], pairs[1], pairs[2], pairs[3], pairs[4], bounds, (raw[14], raw[15])))
        for start, count in pairs:
            for index in range(start, start + count):
                owner.setdefault(index, i)
        dynamic.update(range(pairs[4][0], pairs[4][0] + pairs[4][1]))

    lines = []
    for i in range(line_n):
        v0, v1, prev, nxt, alt_prev, alt_next, flags, props = struct.unpack_from(">hhhhhhHH", data, line_at + 0x10 * i)
        if not (0 <= v0 < vtx_n and 0 <= v1 < vtx_n):
            raise ValueError(f"{file}: line {i} uses a vertex that does not exist")
        (x0, y0), (x1, y1) = verts[v0], verts[v1]
        lines.append(Line(i, KINDS.get(flags & 0xF, f"kind {flags & 0xF}"), x0, y0, x1, y1, flags, props, props & 0xFF,
                          bool(props & DROP_THROUGH), bool(props & LEDGE), bool(flags & 0x10), i in dynamic,
                          owner.get(i, -1), prev, nxt, alt_prev, alt_next))

    main = find_main_stage(lines)
    in_main = set(main.lines)
    platforms = tuple(Platform(l.index, l.x0, l.y0, l.x1, l.y1, l.drop_through, l.joint != main.joint, l.joint,
                               l.ledge) for l in lines if _is_floor(l) and l.index not in in_main)
    return StageGeometry(stage_id, name, file, scale, Camera(eye, fov, vert, horz), main, platforms, tuple(lines),
                         tuple(joints), STAGE_NOTES.get(stage_id, ()))


def _is_floor(line: Line) -> bool:
    return line.kind == "floor" and not line.dynamic and not line.disabled


def find_main_stage(lines: Sequence[Line]) -> MainStage:
    """The joint whose ledge floors form a left and a right group, with its top surface and ledge points."""
    floors = [l for l in lines if _is_floor(l)]
    by_joint: Dict[int, List[Line]] = {}
    for line in floors:
        if line.ledge:
            by_joint.setdefault(line.joint, []).append(line)
    best = None
    for joint, group in sorted(by_joint.items()):
        group.sort(key=lambda l: l.left[0])
        reach, split, widest = group[0].right[0], 0, LEDGE_GAP
        for k in range(1, len(group)):
            if group[k].left[0] - reach > widest:
                split, widest = k, group[k].left[0] - reach
            reach = max(reach, group[k].right[0])
        if not split:
            continue
        left = group[0].left
        right = max(group[split:], key=lambda l: l.right[0]).right
        if best is None or right[0] - left[0] > best[0]:
            best = (right[0] - left[0], joint, left, right)
    if best is None:
        raise ValueError("no joint has ledge-grab floors on both sides")
    _, joint, left, right = best

    solid = [l for l in floors if l.joint == joint and not l.drop_through]
    flat = [l for l in solid if abs(l.y1 - l.y0) < EPS]
    if not flat:
        raise ValueError(f"joint {joint} has no flat floor")
    top_y = max(flat, key=lambda l: l.right[0] - l.left[0]).y0
    level = [l for l in flat if abs(l.y0 - top_y) < EPS]
    top_x = (min(l.left[0] for l in level), max(l.right[0] for l in level))
    return MainStage(top_y, top_x, left, right, joint, tuple(l.index for l in solid))


# ---- loading from the disc -------------------------------------------------------------------------------

_DISCS: Dict[str, Disc] = {}
_CACHE: Dict[Tuple[int, str], StageGeometry] = {}


def load_stage(stage_id: int, iso: Optional[Union[str, Path]] = None) -> StageGeometry:
    """Read one stage from the ISO (default: the one set in the Slippi Launcher). Cached for the process."""
    if stage_id not in STAGE_FILES:
        raise KeyError(f"stage {stage_id} is not one of the legal stages {sorted(STAGE_FILES)}")
    path = locate.find_iso(None if iso is None else str(iso)).resolve()
    key = (stage_id, str(path))
    if key not in _CACHE:
        if str(path) not in _DISCS:
            locate.check_iso(path)
            _DISCS[str(path)] = Disc(path)
        blob = _DISCS[str(path)].read_file(STAGE_FILES[stage_id][1])
        _CACHE[key] = parse_stage(stage_id, read_dat(blob))
    return _CACHE[key]


def _key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if c.isalnum())


_ALIASES = {"bf": 31, "fd": 32, "dl": 28, "dl64": 28, "ys": 8, "fod": 2, "ps": 3, "stadium": 3}


def find_stage(text: str) -> int:
    """A stage id from an id, a name, a .dat file name or a short name (bf, fd, dl, ys, fod, ps)."""
    key = _key(text)
    if key.isdigit() and int(key) in STAGE_FILES:
        return int(key)
    names = {_key(n): sid for sid, (n, _) in STAGE_FILES.items()}
    names.update({_key(d): sid for sid, (_, d) in STAGE_FILES.items()})
    names.update({_key(d[:-4]): sid for sid, (_, d) in STAGE_FILES.items()})
    names.update(_ALIASES)
    if key in names:
        return names[key]
    starts = {sid for n, sid in names.items() if len(key) >= 3 and n.startswith(key)}
    if len(starts) == 1:
        return starts.pop()
    raise KeyError(f"no stage called {text!r}; choose from "
                   + ", ".join(f"{n} ({sid})" for sid, (n, _) in sorted(STAGE_FILES.items())))


# ---- output ----------------------------------------------------------------------------------------------

def _num(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _point(values: Sequence[float]) -> str:
    return "(" + ", ".join(_num(v) for v in values) + ")"


def _ledge_x(geo: StageGeometry) -> str:
    left, right = geo.main_stage.ledge_left[0], geo.main_stage.ledge_right[0]
    return f"+-{_num(right)}" if abs(left + right) < 0.01 else f"{_num(left)} / {_num(right)}"


def _ledge_y(geo: StageGeometry) -> str:
    left, right = geo.main_stage.ledge_left[1], geo.main_stage.ledge_right[1]
    return _num(right) if abs(left - right) < 0.001 else f"{_num(left)} / {_num(right)}"


def _top_x(geo: StageGeometry) -> str:
    x0, x1 = geo.main_stage.top_x
    return f"+-{_num(x1)}" if abs(x0 + x1) < 0.01 else f"{_num(x0)} .. {_num(x1)}"


def _table(rows: List[List[str]]) -> List[str]:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return ["  ".join(c.ljust(w) if i < 2 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths))).rstrip()
            for r in rows]


def summary_table(stages: Sequence[StageGeometry]) -> List[str]:
    rows = [["id", "stage", "ledge x", "ledge y", "top y", "top x", "scale", "camera eye (x, y, z)", "fov", "vert"]]
    for g in stages:
        rows.append([str(g.stage_id), g.name, _ledge_x(g), _ledge_y(g), _num(g.main_stage.top_y), _top_x(g),
                     _num(g.scale), _point(g.camera.eye), _num(g.camera.fov_deg), _num(g.camera.vert_angle_deg)])
    return _table(rows)


def platform_table(geo: StageGeometry) -> List[str]:
    main, cam = geo.main_stage, geo.camera
    out = [f"{geo.name} ({geo.dat}, stage scale {_num(geo.scale)}): main stage is joint {main.joint}, "
           f"floors {' '.join(map(str, main.lines))}",
           f"  ledge points {_point(main.ledge_left)} and {_point(main.ledge_right)}; top y {_num(main.top_y)}, "
           f"top x {_num(main.top_x[0])} .. {_num(main.top_x[1])}",
           f"  camera: eye {_point(cam.eye)}, fov {_num(cam.fov_deg)}, vertical angle {_num(cam.vert_angle_deg)}, "
           f"horizontal angle {_num(cam.horz_angle_deg)}"]
    out += [f"  note: {n}" for n in geo.notes]
    if geo.platforms:
        rows = [["line", "joint", "x0", "y0", "x1", "y1", "drop-through", "movable", "ledge"]]
        for p in geo.platforms:
            rows.append([str(p.line), str(p.joint), _num(p.x0), _num(p.y0), _num(p.x1), _num(p.y1),
                         "yes" if p.drop_through else "no", "yes" if p.movable else "no", "yes" if p.ledge else "no"])
        out += [f"{len(geo.platforms)} other floors:"] + _table(rows)
    return out


def line_table(geo: StageGeometry) -> List[str]:
    def span(pair: Tuple[int, int]) -> str:
        return f"{pair[0]}+{pair[1]}" if pair[1] else ""

    joints = [["joint", "floors", "ceilings", "right walls", "left walls", "dynamic", "bounds l, b, r, t", "vertices"]]
    for j in geo.joints:
        joints.append([str(j.index), span(j.floors), span(j.ceilings), span(j.right_walls), span(j.left_walls),
                       span(j.dynamic), _point(j.bounds), span(j.vertices)])
    rows = [["line", "kind", "x0", "y0", "x1", "y1", "flags", "props", "joint", "dyn", "prev", "next", "alt prev",
             "alt next"]]
    for l in geo.lines:
        rows.append([str(l.index), l.kind, _num(l.x0), _num(l.y0), _num(l.x1), _num(l.y1), f"0x{l.flags:04x}",
                     f"0x{l.props:04x}", str(l.joint), "yes" if l.dynamic else "", str(l.prev), str(l.next),
                     str(l.alt_prev), str(l.alt_next)])
    return ([f"{geo.name}: {len(geo.joints)} joints (first line + count of each kind)"] + _table(joints)
            + [f"{len(geo.lines)} lines"] + _table(rows))


def as_json(geo: StageGeometry, with_lines: bool = False) -> dict:
    """Plain dicts and lists, floats rounded to 4 places; the lines only when asked."""
    def plain(value):
        if isinstance(value, float):
            return round(value, 4)
        if isinstance(value, (tuple, list)):
            return [plain(v) for v in value]
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        return value

    out = plain(asdict(geo))
    if not with_lines:
        del out["lines"]
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stage", help="stage name or id (default: all six); also lists its platforms")
    ap.add_argument("--json", action="store_true", help="print JSON instead of tables")
    ap.add_argument("--lines", action="store_true", help="also list every collision line")
    ap.add_argument("--iso", help="Melee NTSC 1.02 ISO (default: the one set in the Slippi Launcher)")
    args = ap.parse_args(argv)
    try:
        ids = [find_stage(args.stage)] if args.stage else sorted(STAGE_FILES)
        stages = [load_stage(i, args.iso) for i in ids]
    except (locate.NotFound, KeyError, ValueError, OSError) as e:
        print(f"error: {e.args[0] if isinstance(e, KeyError) else e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([as_json(g, args.lines) for g in stages], indent=2))
        return 0
    print("\n".join(summary_table(stages)))
    for geo in stages:
        if args.stage:
            print("\n" + "\n".join(platform_table(geo)))
        if args.lines:
            print("\n" + "\n".join(line_table(geo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
