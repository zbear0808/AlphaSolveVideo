#!/usr/bin/env python3
"""What a replay says about its Shy Guys: which item types it holds, each Shy Guy's track, and a frame window.

Slippi records every item on every frame (type, state, facing, velocity, position, damage, spawn id), and
Shy Guys are items (type 0xD2 = 210), so their paths are in the .slp file itself.

    python3 research/shyguy-probe/items.py summary [--replay FILE]
    python3 research/shyguy-probe/items.py tracks  [--replay FILE]
    python3 research/shyguy-probe/items.py window --from 60 --to 700 --step 40 [--replay FILE]
"""

from __future__ import annotations

import argparse
import collections
from typing import Dict, List

from common import SHY_GUY_ITEM, cli, find_replay, fighter_positions, item_records, shy_guys_by_frame

ON_SCREEN_X = 200  # |x| below this is roughly on the stage's side of the blast zones


def cmd_summary(args) -> int:
    replay = find_replay(args.replay)
    frames: Dict[int, List[int]] = collections.defaultdict(list)
    spawns: Dict[int, set] = collections.defaultdict(set)
    count: collections.Counter = collections.Counter()
    for rec in item_records(replay):
        count[rec.type_id] += 1
        frames[rec.type_id].append(rec.frame)
        spawns[rec.type_id].add(rec.spawn_id)
    print(f"{replay.name}: item types")
    for kind, n in sorted(count.items()):
        label = "  (Shy Guy)" if kind == SHY_GUY_ITEM else ""
        print(f"  type 0x{kind:02x} ({kind:3d}): {n:6d} item-frames, {len(spawns[kind]):3d} spawn ids, "
              f"frames {min(frames[kind])}..{max(frames[kind])}{label}")
    per_frame = collections.Counter(rec.frame for rec in item_records(replay, SHY_GUY_ITEM))
    if per_frame:
        print(f"Shy Guys: at most {max(per_frame.values())} in one frame, present on {len(per_frame)} frames "
              "(Slippi stores at most 15 items per frame)")
    return 0


def cmd_tracks(args) -> int:
    replay = find_replay(args.replay)
    tracks: Dict[int, list] = collections.defaultdict(list)
    for rec in item_records(replay, SHY_GUY_ITEM):
        tracks[rec.spawn_id].append(rec)
    print(f"{replay.name}: {len(tracks)} Shy Guys")
    print("states as they behave in this replay: 0 waiting out its group's stagger, 1 walking, 2 knocked away "
          "(falls off), 3 stunned by a hit, 4 fleeing")
    for sid, recs in sorted(tracks.items()):
        xs, ys = [r.x for r in recs], [r.y for r in recs]
        states = collections.Counter(r.state for r in recs)
        near = sum(abs(r.x) < ON_SCREEN_X for r in recs)
        print(f"  spawn {sid:3d}: frames {recs[0].frame:6d}..{recs[-1].frame:6d}  x [{min(xs):7.1f}, {max(xs):7.1f}]  "
              f"y [{min(ys):6.1f}, {max(ys):6.1f}]  states {dict(sorted(states.items()))}  "
              f"frames with |x| < {ON_SCREEN_X}: {near}  max damage {max(r.damage for r in recs)}")
    return 0


def cmd_window(args) -> int:
    replay = find_replay(args.replay)
    shy = shy_guys_by_frame(replay)
    fighters = fighter_positions(replay)
    for frame in range(args.start, args.end, args.step):
        guys = sorted((r.spawn_id, r.state, round(r.x), round(r.y), int(r.facing)) for r in shy.get(frame, []))
        pos = {port: (round(f.x), round(f.y)) for port, f in sorted(fighters.get(frame, {}).items())}
        print(f"{frame:6d}  shy guys (spawn, state, x, y, facing): {guys}  fighters: {pos}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, text in (("summary", cmd_summary, "item types in the replay"),
                           ("tracks", cmd_tracks, "one line per Shy Guy"),
                           ("window", cmd_window, "Shy Guys and fighters on selected frames")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--replay", help="replay to read (default: the Shy Guy test replay from tools/render-tests)")
        p.set_defaults(func=fn)
        if name == "window":
            p.add_argument("--from", dest="start", type=int, default=60)
            p.add_argument("--to", dest="end", type=int, default=700)
            p.add_argument("--step", type=int, default=40)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    cli(main)
