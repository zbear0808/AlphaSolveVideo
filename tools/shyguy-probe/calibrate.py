#!/usr/bin/env python3
"""Where does a position from the replay land on screen? Fit it from renders made with the fixed camera.

    python3 tools/shyguy-probe/calibrate.py fit      [--from -123 --to 1400]
    python3 tools/shyguy-probe/calibrate.py fighters [--from -123 --to 2400]

fit       draws every Shy Guy as a flat magenta square (a custom texture), finds the squares in the frames,
          matches them with the Shy Guys the replay lists, and fits pixel = scale * position + offset on each
          axis. Compares the result with YS_STATIC_FIT in common.py, and exits 1 if they disagree.
fighters  a rougher check of that mapping on the fighters themselves: a fighter standing on the main platform
          (y = 0) should have its feet on the line the fit gives for y = 0, and sit at the column it gives for
          its x. Useful because the Shy Guys may not be in the same plane as the fighters.

Slippi replays don't record the camera, so this only works with --static-camera (Melee's fixed camera) at
--scale 1 (640x528); the numbers scale with --scale.
"""

from __future__ import annotations

import argparse
import statistics
from typing import Dict, List

from common import (YS_STATIC_FIT, add_tool_args, blobs, cli, fighter_positions, find_replay, find_tools, in_view,
                    iter_frames, need_imaging, run_variant, shy_guys_by_frame, work_dir)
from sprites import make_sprites, render_codes, turning_frames

BASE_SEARCH = range(-20, 31)  # recorded frame 0 = replay frame (--from + this): frames can go missing in a recording
GATE = 45  # px: a Shy Guy this far inside the picture is fully in view, so it must show up as a square


def lstsq(x, y):
    import numpy as np

    a = np.c_[x, np.ones_like(x)]
    coef = np.linalg.lstsq(a, y, rcond=None)[0]
    return coef[0], coef[1], y - a @ coef


def cmd_fit(args) -> int:
    need_imaging()
    import numpy as np

    tools = find_tools(args)
    replay = find_replay(args.replay)
    work = work_dir(args, "calibrate")
    make_sprites(work / "sprites", "solid", 2)
    run = run_variant(tools, replay, work, "fit", render_codes(), args.start, args.end, gfx=["HiresTextures = True"],
                      textures=work / "sprites")
    shy = shy_guys_by_frame(replay)
    turning = turning_frames(replay)
    u0, u1, v0, v1 = YS_STATIC_FIT  # only used to tell which Shy Guys should be fully in view
    found: List[tuple] = []
    for n, img in enumerate(iter_frames(tools, run.video)):
        if n % args.every == 0:
            mask = (img[..., 0] > 200) & (img[..., 1] < 70) & (img[..., 2] > 200)
            if mask.sum() >= 150:
                squares = [b for b in blobs(mask) if not b["edge"]]
                found.append((n, squares, img.shape[1], img.shape[0]))
    print(f"{len(found)} sampled frames have magenta squares")

    best = None
    for shift in BASE_SEARCH:
        base = args.start + shift
        pts = []
        for n, squares, width, height in found:
            expected = sorted((r for r in shy.get(base + n, [])
                               if in_view(u0 * r.x + u1, v0 * r.y + v1, width, height, GATE)), key=lambda r: r.x)
            if any(r.state > 1 or (r.spawn_id, r.frame) in turning for r in expected):
                continue  # stunned, knocked away or still turning: the square is tilted, so its centre is off
            if expected and len(expected) == len(squares):
                pts += [(r.x, r.y, b["u"], b["v"], b["area"]) for r, b in zip(expected, squares)]
        if len(pts) < 8:
            continue
        x, y, u, v, _ = (np.array(c) for c in zip(*pts))
        _, _, ru = lstsq(x, u)
        _, _, rv = lstsq(y, v)
        rms = float(np.sqrt((ru ** 2).mean() + (rv ** 2).mean()))
        if best is None or rms < best[0]:
            best = (rms, base, pts)
    if best is None:
        print("could not match squares with the replay's Shy Guys (too few frames with every Shy Guy in view)")
        return 1
    rms, base, pts = best
    x, y, u, v, area = (np.array(c) for c in zip(*pts))
    su, ou, ru = lstsq(x, u)
    sv, ov, rv = lstsq(y, v)
    print(f"recorded frame 0 = replay frame {base}; {len(pts)} Shy Guys matched with their squares")
    for label, coef, off, res in (("u", su, ou, ru), ("v", sv, ov, rv)):
        axis = "x" if label == "u" else "y"
        print(f"  {label} = {coef:.4f} * {axis} + {off:.2f}   (rms {np.sqrt((res ** 2).mean()):.2f} px, "
              f"95% within {np.percentile(np.abs(res), 95):.2f}, worst {np.abs(res).max():.2f})")
    print(f"  {su:.3f} px per unit across, {-sv:.3f} up; each square covers {statistics.median(area):.0f} px "
          f"(about {statistics.median(area) ** 0.5:.0f} px wide, {statistics.median(area) ** 0.5 / su:.1f} units)")
    stored = np.array(YS_STATIC_FIT)
    fitted = np.array([su, ou, sv, ov])
    xs, ys = np.array([-100.0, 100.0]), np.array([0.0, 100.0])
    drift = max(np.abs((fitted[0] - stored[0]) * xs + fitted[1] - stored[1]).max(),
                np.abs((fitted[2] - stored[2]) * ys + fitted[3] - stored[3]).max())
    print(f"YS_STATIC_FIT in common.py {'agrees' if drift < 1 else 'DISAGREES'}: at most {drift:.2f} px apart "
          "over x -100..100 and y 0..100")
    if not args.keep_videos:
        run.discard_recordings()
    return 0 if drift < 1 else 1


def cmd_fighters(args) -> int:
    need_imaging()
    import numpy as np

    tools = find_tools(args)
    replay = find_replay(args.replay)
    work = work_dir(args, "calibrate")
    run = run_variant(tools, replay, work, "fighters", render_codes(hide_shy_guys=True), args.start, args.end)
    fighters = fighter_positions(replay)
    u0, u1, v0, v1 = YS_STATIC_FIT
    samples: Dict[int, List[tuple]] = {shift: [] for shift in BASE_SEARCH}
    for n, img in enumerate(iter_frames(tools, run.video)):
        if n < 100 or n % 3:
            continue
        lit = img.astype(int).sum(axis=2) > 90  # everything drawn: the stage is hidden, so only fighters and effects
        for shift in BASE_SEARCH:
            here = fighters.get(args.start + shift + n, {})
            if len(here) != 2:
                continue
            (_, a), (_, b) = sorted(here.items())
            if abs(a.x - b.x) < 60:  # far enough apart that each has its own columns
                continue
            for f in (a, b):
                if f.airborne or abs(f.y) > 0.01 or abs(f.x) > 52:  # standing on the main platform
                    continue
                u = u0 * f.x + u1
                if not in_view(u, v0 * f.y + v1, img.shape[1], img.shape[0], 30):
                    continue
                cols = lit[int(v1) - 130:int(v1) + 25, int(u) - 22:int(u) + 22]
                rows, xs = np.nonzero(cols)
                if len(rows) >= 60:
                    samples[shift].append((xs.mean() + int(u) - 22 - u, rows.max() + int(v1) - 130 - v1))
    usable = {s: v for s, v in samples.items() if len(v) >= 8}
    if not usable:
        print("too few frames with a lone fighter standing on the main platform")
        return 1
    mad = lambda vals: statistics.median(abs(v - statistics.median(vals)) for v in vals)
    shift = min(usable, key=lambda s: mad([d[0] for d in usable[s]]))
    du, dv = zip(*usable[shift])
    q = statistics.quantiles(dv, n=4)
    print(f"recorded frame 0 = replay frame {args.start + shift}; {len(du)} samples of a fighter standing on y = 0")
    print(f"  column of the fighter minus the column the fit gives for its x: median {statistics.median(du):+.1f} px "
          f"(typical spread {mad(du):.1f})")
    print(f"  lowest lit pixel minus the row the fit gives for y = 0: median {statistics.median(dv):+.1f} px, "
          f"middle half {q[0]:+.1f} to {q[2]:+.1f} (dust and other effects below the feet make this one rough)")
    if not args.keep_videos:
        run.discard_recordings()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit", help="fit replay position -> pixels from the Shy Guys")
    add_tool_args(f)
    f.add_argument("--from", dest="start", type=int, default=-123)
    f.add_argument("--to", dest="end", type=int, default=1400)
    f.add_argument("--every", type=int, default=10, help="look at every Nth recorded frame")
    f.set_defaults(func=cmd_fit)
    g = sub.add_parser("fighters", help="check that mapping on fighters standing on the main platform")
    add_tool_args(g)
    g.add_argument("--from", dest="start", type=int, default=-123)
    g.add_argument("--to", dest="end", type=int, default=2400)
    g.set_defaults(func=cmd_fighters)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    cli(main)
