#!/usr/bin/env python3
"""Check stagedata.py against real replays: do fighters stand, hang and land where the geometry on the ISO says?

    python3 tools/logo-stage/validate_stagedata.py [--replays FILE_OR_FOLDER ...] [--iso PATH] [--stage NAME_OR_ID]

Every replay's post-frame events (one per fighter per frame) are matched with the stage it was played on.
Per stage:

  standing  grounded frames (not airborne) with y within 0.01 of the main stage's top y: how far out do fighters
            get? A grounded fighter can be 0.1 past the end of a floor (the game's tolerance), so the largest |x|
            should be the end of the top surface give or take that. Shown twice: every frame, and without the
            states where the floor does not decide the position (ledge states, dying and respawning, being
            grabbed or thrown).
  reach     the same for every floor of the main stage (ledge pieces and slopes too), found by the "last ground
            id" Slippi records, which is the line's number in the file: the largest |x| against the ledge point.
  hanging   CliffWait frames: how far outside the ledge point and how far below it the fighter hangs.
  lines     grounded frames by last ground id: is the fighter at the height of that line at its x? For the main
            stage's floors, the platforms of the same joint, and other joints (which may be in joint space).

Then, across stages: a character hangs at the same offset from the ledge point on every stage, so a wrong ledge
point on one stage would show as a different offset for the same character.

Exit status 1 if the data and the replays disagree, 2 on an error. Replays default to the test replays that
tools/render-tests downloads to the cache folder. Only the standard library and slp2alpha are used.
"""

from __future__ import annotations

import argparse
import os
import statistics
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import stagedata  # noqa: E402
from slp2alpha import locate, slp  # noqa: E402  (stagedata puts tools/slp2alpha on sys.path)

RAW_HEADER = b"{U\x03raw[$U#l"
EVENT_PAYLOAD_SIZES, EVENT_POST_FRAME = 0x35, 0x38

# Action states (melee/ft/kinds/ftCommon/forward.h) where a grounded fighter is not just standing on the floor.
CLIFF_WAIT = 253
LEDGE_STATES = tuple(range(252, 264))  # CliffCatch .. CliffJumpQuick2
OFF_STAGE_STATES = tuple(range(0, 14)) + (322, 323, 324)  # Dead*, Sleep, Rebirth*, Entry*
DRAGGED_STATES = tuple(range(223, 233)) + tuple(range(239, 244))  # Capture* and Thrown*: another fighter decides
# Where a fighter's height is the floor's: Wait .. KneeBend, Squat .. LandingFallSpecial. (Rolls, getups and the
# like can move the fighter off the floor line by animation: Samus's forward roll sits 2 below it.)
SETTLED_STATES = tuple(range(14, 25)) + (39, 40, 41, 42, 43)
SKIPPED_STATES = frozenset(LEDGE_STATES + OFF_STAGE_STATES + DRAGGED_STATES)

CHARACTERS = ("Mario", "Fox", "Captain Falcon", "Donkey Kong", "Kirby", "Bowser", "Link", "Sheik", "Ness", "Peach",
              "Popo", "Nana", "Pikachu", "Samus", "Yoshi", "Jigglypuff", "Mewtwo", "Luigi", "Marth", "Zelda",
              "Young Link", "Dr. Mario", "Falco", "Pichu", "Mr. Game & Watch", "Ganondorf", "Roy")  # internal ids

LEVEL = 0.01  # how close to the top y counts as standing on the top surface
FLOOR_SLACK = 0.1  # a grounded fighter may be this far past the end of a floor (mpLib_8004DD90_Floor)
FIT = 0.02  # a fighter is on a line if its height is this close to the line's
SAME_OFFSET = 0.05  # one character's hanging offset may differ this much between stages
REACHED = 1.0  # fighters should get this close to an end of the stage, on one side at least
MIN_FRAMES = 500  # ... if there are this many frames to judge by


def character_name(internal_id: int) -> str:
    return CHARACTERS[internal_id] if internal_id < len(CHARACTERS) else f"character {internal_id}"


# ---- a minimal Slippi reader -----------------------------------------------------------------------------

def read_events(path: Path) -> Iterator[Tuple[int, bytes]]:
    """(command, payload) of every event in a .slp file's raw stream.

    The stream follows the header bytes and a u32 length (0 while the game is still being written: then it
    runs to the metadata). Its first event is 0x35, whose payload starts with its own size and then lists
    (command, u16 payload size) for every event that can follow; each event is its command byte and payload."""
    data = path.read_bytes()
    if not data.startswith(RAW_HEADER):
        raise ValueError(f"{path.name}: not a Slippi replay")
    start = len(RAW_HEADER) + 4
    length = struct.unpack_from(">I", data, len(RAW_HEADER))[0]
    if length == 0:
        end = data.find(b"U\x08metadata", start)
        length = (end if end != -1 else len(data)) - start
    raw = data[start:start + length]
    if not raw or raw[0] != EVENT_PAYLOAD_SIZES:
        raise ValueError(f"{path.name}: the raw stream does not start with the payload sizes")
    sizes = {EVENT_PAYLOAD_SIZES: raw[1]}
    for i in range(2, 1 + raw[1], 3):
        sizes[raw[i]] = struct.unpack_from(">H", raw, i + 1)[0]
    pos = 0
    while pos < len(raw):
        size = sizes.get(raw[pos])
        if size is None:
            raise ValueError(f"{path.name}: event 0x{raw[pos]:02x} at byte {pos} is not in the payload table")
        if pos + 1 + size > len(raw):
            break
        yield raw[pos], raw[pos + 1:pos + 1 + size]
        pos += 1 + size


@dataclass(frozen=True)
class Sample:
    """One fighter on one frame (Post-Frame Update; payload offsets are the spec's minus the command byte)."""
    frame: int
    port: int
    character: int
    state: int
    x: float
    y: float
    airborne: bool
    ground_id: int


def read_samples(path: Path) -> List[Sample]:
    """Every fighter on every frame, without followers (Nana). Needs replay version 2.0 or later.

    Payload: i32 frame at 0, u8 port at 4, u8 follower at 5, u8 internal character at 6, u16 action state at 7
    (not 6: that is the character), f32 x at 9, f32 y at 13, u8 airborne at 0x2E, u16 last ground id at 0x2F."""
    out = []
    for command, p in read_events(path):
        if command != EVENT_POST_FRAME or len(p) < 0x31 or p[5]:
            continue
        x, y = struct.unpack_from(">ff", p, 9)
        out.append(Sample(struct.unpack_from(">i", p, 0)[0], p[4], p[6], struct.unpack_from(">H", p, 7)[0], x, y,
                          bool(p[0x2E]), struct.unpack_from(">H", p, 0x2F)[0]))
    return out


# ---- the checks ------------------------------------------------------------------------------------------

def height_at(line: stagedata.Line, x: float) -> Optional[float]:
    """The line's height at x, None if x is further than the floor tolerance past its ends."""
    (lx, ly), (rx, ry) = line.left, line.right
    if not lx - FLOOR_SLACK <= x <= rx + FLOOR_SLACK:
        return None
    return ly if rx == lx else ly + (ry - ly) * min(max((x - lx) / (rx - lx), 0.0), 1.0)


def spread(values: Sequence[float]) -> str:
    if not values:
        return "-"
    return f"median {statistics.median(values):.2f} ({min(values):.2f} to {max(values):.2f})"


def end_of(main: stagedata.MainStage, x: float) -> float:
    """|x| of the end of the top surface on the side x is on."""
    return main.top_x[1] if x > 0 else -main.top_x[0]


@dataclass
class Result:
    stage: stagedata.StageGeometry
    lines: List[str]
    problems: List[str] = field(default_factory=list)
    hangs: Dict[int, Tuple[float, float, int]] = field(default_factory=dict)  # character -> dx, dy, frames


def check_stage(geo: stagedata.StageGeometry, replays: Dict[str, List[Sample]]) -> Result:
    main = geo.main_stage
    samples = [s for group in replays.values() for s in group]
    res = Result(geo, [f"{geo.name} ({geo.stage_id}): {len(replays)} replays, {len(samples):,} fighter-frames; "
                       f"top y {main.top_y:.4f}, top x {main.top_x[0]:.3f} .. {main.top_x[1]:.3f}, ledge points "
                       f"({main.ledge_left[0]:.3f}, {main.ledge_left[1]:.3f}) and "
                       f"({main.ledge_right[0]:.3f}, {main.ledge_right[1]:.3f})"])
    out = res.lines

    # standing on the top surface
    level = [s for s in samples if not s.airborne and abs(s.y - main.top_y) <= LEVEL]
    own = [s for s in level if s.state not in SKIPPED_STATES]
    for label, group in (("standing, every grounded frame", level), ("standing, floor decides the position", own)):
        left = min((s.x for s in group if s.x < 0), default=None)
        right = max((s.x for s in group if s.x > 0), default=None)
        ys = [s.y for s in group]
        out.append(f"  {label}: {len(group):,} frames, y {min(ys, default=0):.4f} to {max(ys, default=0):.4f}; "
                   f"furthest left {'-' if left is None else f'{left:.3f}'}, "
                   f"furthest right {'-' if right is None else f'{right:.3f}'}")
    far = max(own, key=lambda s: abs(s.x) - end_of(main, s.x), default=None)
    if far is not None and abs(far.x) > end_of(main, far.x) + FLOOR_SLACK + 0.05:
        res.problems.append(f"{geo.name}: a fighter stands at x {far.x:.3f}, {abs(far.x) - end_of(main, far.x):.3f} "
                            f"past the end of the top surface (state {far.state})")
    gaps = [end_of(main, side) - max((abs(s.x) for s in own if (s.x > 0) == (side > 0)), default=0.0)
            for side in (-1.0, 1.0) if any((s.x > 0) == (side > 0) for s in own)]
    if len(own) >= MIN_FRAMES and gaps and min(gaps) > REACHED:
        res.problems.append(f"{geo.name}: no fighter gets within {REACHED} of either end of the top surface "
                            f"(closest: {min(gaps):.2f} short), so it may be too wide")

    # reach on all the floors of the main stage
    in_main = set(main.lines)
    on_main = [s for s in samples if not s.airborne and s.ground_id in in_main and s.state not in SKIPPED_STATES]
    reached: List[float] = []
    for side, ledge in (("left", main.ledge_left), ("right", main.ledge_right)):
        xs = [s.x for s in on_main if (s.x < 0) == (ledge[0] < 0)]
        if xs:
            reach = min(xs) if ledge[0] < 0 else max(xs)
            out.append(f"  reach, {side}: furthest grounded x {reach:.3f} on floors {sorted(in_main)} "
                       f"({len(xs):,} frames); ledge x {ledge[0]:.3f}, so {abs(reach) - abs(ledge[0]):+.3f}")
            if abs(reach) > abs(ledge[0]) + FLOOR_SLACK + 0.05:
                res.problems.append(f"{geo.name}: a fighter stands {abs(reach) - abs(ledge[0]):.3f} beyond the "
                                    f"{side} ledge point")
            reached.append(abs(ledge[0]) - abs(reach))
    if len(on_main) >= MIN_FRAMES and reached and min(reached) > REACHED:
        res.problems.append(f"{geo.name}: no fighter gets within {REACHED} of either ledge point "
                            f"(closest: {min(reached):.2f} short), so the stage may be too wide")

    # hanging on the ledge
    hang = [s for s in samples if s.state == CLIFF_WAIT]
    per_character: Dict[int, List[Tuple[float, float]]] = {}
    for side, ledge, group in (("left", main.ledge_left, [s for s in hang if s.x < 0]),
                               ("right", main.ledge_right, [s for s in hang if s.x > 0])):
        if not group:
            out.append(f"  hanging, {side}: no CliffWait frames")
            continue
        dx = [abs(s.x) - abs(ledge[0]) for s in group]
        dy = [s.y - ledge[1] for s in group]
        for s, a, b in zip(group, dx, dy):
            per_character.setdefault(s.character, []).append((a, b))
        out.append(f"  hanging, {side}: {len(group)} CliffWait frames, |x| {spread([abs(s.x) for s in group])}; "
                   f"outside the ledge point by {spread(dx)}; y relative to it {spread(dy)}")
    for character, pairs in per_character.items():
        res.hangs[character] = (statistics.median(a for a, _ in pairs), statistics.median(b for _, b in pairs),
                                len(pairs))
    if hang:
        dx_all = [a for pairs in per_character.values() for a, _ in pairs]
        if min(dx_all) < 0 or max(dx_all) > 10:
            res.problems.append(f"{geo.name}: CliffWait x is not just outside the ledge point ({spread(dx_all)})")

    # which line is the fighter on?
    cells: Dict[str, Dict[str, List[float]]] = {}
    past: Dict[str, int] = {}
    platforms = {p.line: p for p in geo.platforms}
    for s in samples:
        if s.airborne or s.state in SKIPPED_STATES or s.ground_id >= len(geo.lines):
            continue
        line = geo.lines[s.ground_id]
        if s.ground_id in in_main:
            name = "main stage"
        elif s.ground_id in platforms and not platforms[s.ground_id].movable:
            name = f"platforms, joint {main.joint}"
        elif line.kind == "floor":
            name = f"joint {line.joint}" + (" (dynamic)" if line.dynamic else "")
        else:
            name = f"{line.kind}, joint {line.joint}"
        height = height_at(line, s.x)
        if height is None:
            past[name] = past.get(name, 0) + 1
        else:
            bucket = cells.setdefault(name, {"settled": [], "other": []})
            bucket["settled" if s.state in SETTLED_STATES else "other"].append(s.y - height)
    out.append("  last ground id: grounded frames at the height of that line at x, within 0.02 "
               "(settled: standing, walking, running, crouching, landing)")
    for name in sorted(set(cells) | set(past)):
        parts = []
        for kind in ("settled", "other"):
            diffs = cells.get(name, {}).get(kind, [])
            fit = sum(abs(d) <= FIT for d in diffs)
            parts.append(f"{kind} {fit:,}/{len(diffs):,}" + (f" ({100 * fit / len(diffs):.1f}%)" if diffs else ""))
            if kind == "settled" and diffs and name in ("main stage", f"platforms, joint {main.joint}") \
                    and fit < 0.99 * len(diffs):
                res.problems.append(f"{geo.name}: only {100 * fit / len(diffs):.1f}% of the standing frames on {name} "
                                    f"are at the height of their line")
        settled = cells.get(name, {}).get("settled", [])
        out.append(f"    {name:20s} {'; '.join(parts)}"
                   + (f"; median offset {statistics.median(settled):+.3f}" if settled else "")
                   + (f"; {past[name]:,} frames past the line's ends" if name in past else ""))
    return res


def check_hangs(results: Sequence[Result]) -> Tuple[List[str], List[str]]:
    """Hanging offsets from the ledge point per character and stage, and the characters that differ by stage."""
    lines, problems = [], []
    for character in sorted({c for r in results for c in r.hangs}):
        cells = [(r.stage, r.hangs[character]) for r in results if character in r.hangs]
        text = ", ".join(f"{g.name} {dx:.2f}/{dy:.2f} ({n})" for g, (dx, dy, n) in cells)
        dxs, dys = [dx for _, (dx, _, _) in cells], [dy for _, (_, dy, _) in cells]
        wide = len(cells) > 1 and (max(dxs) - min(dxs) > SAME_OFFSET or max(dys) - min(dys) > SAME_OFFSET)
        lines.append(f"  {character_name(character):16s} {text}" + ("  <- DIFFERS" if wide else ""))
        if wide:
            problems.append(f"{character_name(character)} hangs {max(dxs) - min(dxs):.2f} (x) and "
                            f"{max(dys) - min(dys):.2f} (y) differently on different stages")
    return lines, problems


def default_replays() -> List[Path]:
    base = Path.home() / "Library" / "Caches" if sys.platform == "darwin" else Path(
        os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return [base / "AlphaSolveVideo" / "test-replays"]


def find_replays(places: Sequence[str]) -> List[Path]:
    found: List[Path] = []
    for place in places:
        p = Path(place).expanduser()
        found += sorted(p.glob("*.slp")) if p.is_dir() else [p]
    return found


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--replays", nargs="+", help="replay files or folders of them (default: the render-tests cache)")
    ap.add_argument("--iso", help="Melee NTSC 1.02 ISO (default: the one set in the Slippi Launcher)")
    ap.add_argument("--stage", help="only this stage (name or id)")
    args = ap.parse_args(argv)
    try:
        only = stagedata.find_stage(args.stage) if args.stage else None
        paths = find_replays(args.replays or [str(p) for p in default_replays()])
        if not paths:
            raise locate.NotFound("no .slp files found; pass --replays FILE_OR_FOLDER")
        by_stage: Dict[int, Dict[str, List[Sample]]] = {}
        for path in paths:
            stage_id = slp.read_replay(path).stage_id
            if stage_id in stagedata.STAGE_FILES and only in (None, stage_id):
                by_stage.setdefault(stage_id, {})[path.name] = read_samples(path)
        results = [check_stage(stagedata.load_stage(sid, args.iso), by_stage[sid]) for sid in sorted(by_stage)]
    except (locate.NotFound, KeyError, ValueError, OSError, slp.ReplayError) as e:
        print(f"error: {e.args[0] if isinstance(e, KeyError) else e}", file=sys.stderr)
        return 2
    for res in results:
        print("\n".join(res.lines) + "\n")
    problems = [p for res in results for p in res.problems]
    if len(results) > 1:
        lines, more = check_hangs(results)
        print("hanging offset by character and stage (outside the ledge point / y relative to it (frames)):")
        print("\n".join(lines) + "\n")
        problems += more
    for p in problems:
        print(f"DISAGREES: {p}")
    print(f"{len(results)} stages checked: " + ("the data and the replays agree" if not problems
                                                else f"{len(problems)} disagreements"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
