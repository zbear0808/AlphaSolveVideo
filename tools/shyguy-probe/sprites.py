#!/usr/bin/env python3
"""Replace the Shy Guy sprite with your own art, through the repo's real render pipeline.

    python3 tools/shyguy-probe/sprites.py make DIR [--kind badge|solid|halves] [--scale 2]
    python3 tools/shyguy-probe/sprites.py demo    [--from 1180 --to 1780] [--scale 1]
    python3 tools/shyguy-probe/sprites.py markers [--from 560 --to 1800]

make     writes the three replacement PNGs, named the way Dolphin looks them up, at --scale times the size of
         the originals: "badge" is test art with a pointing arrow and "GO" (so a mirror image is obvious),
         "solid" a flat colour, "halves" a colour on the left half and white on the right.
demo     renders a replay window with the Shy Guys drawn from those PNGs: flicker recording, then the repo's
         solver. Frames of the transparent result are laid over a mock "YOUR LOGO" backdrop in demo-sheet.png.
markers  checks two things the custom textures do, by drawing each Shy Guy in coloured halves: which of the
         three textures is on screen frame by frame (the flip-book), and whether the sprite is mirrored when
         the Shy Guy faces left. Both are compared with what the replay says.
"""

from __future__ import annotations

import argparse
import collections
import math
import statistics
import subprocess
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from common import (SHY_GUY_HIDE_CODE, SHY_GUY_ITEM, SHY_GUY_TEXTURES, YS_STATIC_FIT, add_tool_args, cli,
                    find_replay, find_tools, in_view, item_records, iter_frames, need_imaging, run_variant,
                    shy_guys_by_frame, work_dir)
from slp2alpha import config, solve, validate

MARKER_COLORS = ((255, 0, 0), (0, 255, 0), (0, 0, 255))  # one per texture, in SHY_GUY_TEXTURES order
BADGE_TILT = (0.0, 0.6, 1.2)  # the tick mark on the badge, so the three flip-book frames differ
TURN_FRAMES = 21  # a Shy Guy takes about 20 frames to turn round after its facing flips


def badge(size: Tuple[int, int], tilt: float):
    """Round blue badge with a yellow arrow pointing right, "GO" above it and a soft translucent glow."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    w, h = size
    s = 4  # draw at 4x and shrink, for clean edges
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    cx, cy, r = w * s / 2, h * s / 2, min(w, h) * s * 0.44
    glow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([cx - r * 1.08, cy - r * 1.08, cx + r * 1.08, cy + r * 1.08], fill=(80, 200, 255, 140))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(s * 3)))
    d = ImageDraw.Draw(im)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 60, 160, 255), outline=(255, 255, 255, 255), width=s * 2)
    x0, x1 = cx - r * 0.55, cx + r * 0.62
    d.polygon([(x0, cy - r * 0.16), (cx + r * 0.2, cy - r * 0.16), (cx + r * 0.2, cy - r * 0.42), (x1, cy),
               (cx + r * 0.2, cy + r * 0.42), (cx + r * 0.2, cy + r * 0.16), (x0, cy + r * 0.16)],
              fill=(255, 210, 0, 255))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", int(r * 0.5))
    except OSError:
        font = ImageFont.load_default()
    d.text((cx, cy - r * 0.62), "GO", fill=(255, 255, 255, 255), anchor="mm", font=font)
    px, py = cx - r * 0.78, cy - r * 0.78
    d.line([(px - r * 0.2 * math.cos(tilt), py - r * 0.2 * math.sin(tilt)),
            (px + r * 0.2 * math.cos(tilt), py + r * 0.2 * math.sin(tilt))], fill=(255, 80, 80, 255), width=s * 3)
    return im.resize((w, h), Image.LANCZOS)


def make_sprites(dest: Path, kind: str, scale: int = 2, color: Sequence[int] = (255, 0, 255)) -> List[Path]:
    """Write replacement PNGs for the three Shy Guy textures into dest and return their paths."""
    from PIL import Image

    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, (name, w, h) in enumerate(SHY_GUY_TEXTURES):
        size = (w * scale, h * scale)
        if kind == "solid":
            im = Image.new("RGBA", size, (*color, 255))
        elif kind == "halves":
            im = Image.new("RGBA", size, (255, 255, 255, 255))
            im.paste(Image.new("RGBA", (size[0] // 2, size[1]), (*MARKER_COLORS[k], 255)), (0, 0))
        else:
            im = badge(size, BADGE_TILT[k])
        path = dest / f"{name}.png"
        im.save(path)
        paths.append(path)
    return paths


def mock_logo(size: Tuple[int, int]):
    """A stand-in for the stage replacement: a dark grid with "YOUR LOGO" on it."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = size
    im = Image.new("RGB", size, (24, 28, 44))
    d = ImageDraw.Draw(im)
    for x in range(0, w, w // 20):
        d.line([(x, 0), (x, h)], fill=(34, 40, 62))
    for y in range(0, h, w // 20):
        d.line([(0, y), (w, y)], fill=(34, 40, 62))
    try:
        big = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Black.ttf", w // 5)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", w // 21)
    except OSError:
        big = small = ImageFont.load_default()
    d.text((w / 2, h * 0.47), "YOUR LOGO", fill=(235, 235, 245), anchor="mm", font=big)
    d.text((w / 2, h * 0.63), "stage replacement backdrop", fill=(150, 160, 190), anchor="mm", font=small)
    return im.convert("RGBA")


def render_codes(hide_shy_guys: bool = False) -> List[str]:
    """Characters-only, fixed camera, no HUD. The Shy Guys stay drawn: they are what gets the new sprite."""
    codes = [c for c in config.HIDE_STAGE_CODES if hide_shy_guys or c != SHY_GUY_HIDE_CODE]
    return codes + config.STATIC_CAMERA_CODES + [config.HIDE_HUD_CODE]


def pick_frames(replay: Path, first_frame: int, total: int, scale: int, count: int = 3, spacing: int = 60):
    """Output frames with the most Shy Guys in view (by the replay and the calibrated mapping)."""
    shy = shy_guys_by_frame(replay)
    u0, u1, v0, v1 = YS_STATIC_FIT
    width, height = 640 * scale, 528 * scale
    score = [sum(in_view(scale * (u0 * r.x + u1), scale * (v0 * r.y + v1), width, height, 20)
                 for r in shy.get(first_frame + i, [])) for i in range(total)]
    picks: List[int] = []
    for i in sorted(range(total), key=lambda i: (-score[i], i)):
        if all(abs(i - j) >= spacing for j in picks):
            picks.append(i)
        if len(picks) == count:
            break
    return sorted(picks), max(score, default=0)


def cmd_make(args) -> int:
    need_imaging()
    for path in make_sprites(Path(args.dir).expanduser(), args.kind, args.scale):
        print(path)
    return 0


def cmd_demo(args) -> int:
    need_imaging()
    from PIL import Image

    tools = find_tools(args)
    replay = find_replay(args.replay)
    work = work_dir(args, "sprites")
    make_sprites(work / "sprites", "badge", 2 * args.scale)
    enabled = list(config.FLICKER_CODES) + render_codes()
    run = run_variant(tools, replay, work, "demo", enabled, args.start, args.end, scale=args.scale,
                      gfx=["HiresTextures = True"], textures=work / "sprites")
    video = str(run.video)
    report = validate.quick_check(tools.ffmpeg, tools.ffprobe, video)
    problems = report.problems(expected_frames=2 * (args.end - args.start))
    pairing = report.pairing
    print(f"recording: {report.probe.frames} fields, pairing {pairing.first_color}/{pairing.offset}, "
          + ("problems: " + "; ".join(problems) if problems else "no problems"))
    pairs = solve.pair_count(report.probe.frames, pairing.offset)
    out = solve.solve(tools.ffmpeg, video, work / "out", "shy-guy-demo", pairing.first_color, pairing.offset,
                      fmt="mov", pairs=pairs, show_progress=False, rate=report.probe.rate)
    print(f"transparent video: {out.transparent}")

    picks, most = pick_frames(replay, args.start + 1, pairs, args.scale)
    print(f"sheet frames {picks} (up to {most} Shy Guys in view)")
    tiles = []
    for i in picks:
        png = work / f"frame-{i}.png"
        subprocess.run([tools.ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(out.transparent), "-vf",
                        f"select=eq(n\\,{i})", "-frames:v", "1", "-pix_fmt", "rgba", str(png)], check=True)
        fg = Image.open(png).convert("RGBA")
        base = mock_logo(fg.size)
        base.alpha_composite(fg)
        tiles.append(base.convert("RGB"))
    sheet = Image.new("RGB", (sum(t.width for t in tiles) + 10 * (len(tiles) - 1), tiles[0].height), (255, 0, 255))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width + 10
    sheet.save(work / "demo-sheet.png")
    print(f"sheet: {work / 'demo-sheet.png'}")
    if not args.keep_videos:
        run.discard_recordings()
    return 1 if problems else 0


def classify(pixel) -> str:
    r, g, b = (int(c) for c in pixel)
    if r > 200 and g < 70 and b < 70:
        return "R"
    if g > 200 and r < 70 and b < 70:
        return "G"
    if b > 200 and r < 70 and g < 70:
        return "B"
    return "W" if min(r, g, b) > 200 else "?"


def turning_frames(replay: Path) -> set:
    """(spawn id, frame) pairs shortly after a Shy Guy's facing flips, while its model is still turning."""
    last: Dict[int, Tuple[int, float]] = {}
    turning = set()
    for rec in item_records(replay, SHY_GUY_ITEM):
        prev = last.get(rec.spawn_id)
        if prev and prev[1] != rec.facing:
            turning.update((rec.spawn_id, rec.frame + k) for k in range(TURN_FRAMES))
        last[rec.spawn_id] = (rec.frame, rec.facing)
    return turning


def cmd_markers(args) -> int:
    need_imaging()
    tools = find_tools(args)
    replay = find_replay(args.replay)
    work = work_dir(args, "markers")
    make_sprites(work / "sprites", "halves", 2)
    run = run_variant(tools, replay, work, "markers", render_codes(), args.start, args.end,
                      gfx=["HiresTextures = True"], textures=work / "sprites")
    shy = shy_guys_by_frame(replay)
    turning = turning_frames(replay)
    u0, u1, v0, v1 = YS_STATIC_FIT
    half = 8  # sample this many pixels left and right of a Shy Guy's centre
    # Recorded frame 0 is replay frame `base`; frames can go missing, so try a few and keep the best fit.
    bases = list(range(args.start - 10, args.start + 12))
    rows: Dict[int, list] = {b: [] for b in bases}  # base -> (recorded frame, spawn id, facing, left, right)
    for n, img in enumerate(iter_frames(tools, run.video)):
        height, width = img.shape[:2]
        for base in bases:
            for rec in shy.get(base + n, []):
                if rec.state != 1 or rec.facing == 0 or (rec.spawn_id, rec.frame) in turning:
                    continue  # only walking Shy Guys that have finished turning
                u, v = u0 * rec.x + u1, v0 * rec.y + v1
                if in_view(u, v, width, height, 24):
                    row, col = int(round(v)), int(round(u))
                    rows[base].append((n, rec.spawn_id, rec.facing, classify(img[row, col - half]),
                                       classify(img[row, col + half])))

    def valid(row) -> bool:
        return (row[3] in "RGB" and row[4] == "W") or (row[3] == "W" and row[4] in "RGB")

    best = max(bases, key=lambda b: (sum(map(valid, rows[b])), -abs(b - args.start)))
    ok = [r for r in rows[best] if valid(r)]
    print(f"recorded frame 0 = game frame {best}; {len(ok)} of {len(rows[best])} samples of walking Shy Guys "
          "show the coloured-halves sprite")
    if not ok:
        return 1

    left = [r for r in ok if r[2] < 0]
    right = [r for r in ok if r[2] > 0]
    mirrored = lambda r: r[3] == "W"  # the coloured half is on the right
    print(f"mirrored: {sum(map(mirrored, left))} of {len(left)} samples where the replay says the Shy Guy faces left; "
          f"{sum(map(mirrored, right))} of {len(right)} where it faces right")

    colors = "RGB"
    track: Dict[int, List[Tuple[int, str]]] = collections.defaultdict(list)
    for n, sid, _, l, r in ok:
        track[sid].append((n, l if l != "W" else r))
    steps: collections.Counter = collections.Counter()
    lengths: List[int] = []
    for samples in track.values():
        samples.sort()
        prev, length, clean = None, 0, False
        for n, c in samples:
            if prev and n == prev[0] + 1:
                if c == prev[1]:
                    length += 1
                else:
                    steps[(prev[1], c)] += 1
                    if clean:
                        lengths.append(length)  # began and ended at a change: a whole run
                    length, clean = 1, True
            else:
                length, clean = 1, False
            prev = (n, c)
    short = [name.split("_")[2][:4] for name, _, _ in SHY_GUY_TEXTURES]
    order = " ".join(f"{short[colors.index(a)]}->{short[colors.index(b)]} x{n}" for (a, b), n in sorted(steps.items()))
    print(f"flip-book changes: {order or 'none seen'}")
    if lengths:
        print(f"each texture stays on screen for {statistics.median(lengths):g} frames (median of {len(lengths)} "
              f"whole runs, range {min(lengths)}-{max(lengths)})")
    if not args.keep_videos:
        run.discard_recordings()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="write replacement PNGs")
    m.add_argument("dir")
    m.add_argument("--kind", choices=("badge", "solid", "halves"), default="badge")
    m.add_argument("--scale", type=int, default=2, help="size relative to the originals (76x72)")
    m.set_defaults(func=cmd_make)
    d = sub.add_parser("demo", help="render with the replacement sprites and lay the result over a mock logo")
    add_tool_args(d)
    d.add_argument("--from", dest="start", type=int, default=1180)
    d.add_argument("--to", dest="end", type=int, default=1780)
    d.add_argument("--scale", type=int, default=1, help="internal resolution (as for slp2alpha render)")
    d.set_defaults(func=cmd_demo)
    k = sub.add_parser("markers", help="check the flip-book order and the mirroring against the replay")
    add_tool_args(k)
    k.add_argument("--from", dest="start", type=int, default=560)
    k.add_argument("--to", dest="end", type=int, default=1800)
    k.set_defaults(func=cmd_markers)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    cli(main)
