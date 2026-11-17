"""Check the camera math against real fighters: where do idle fighters standing on the main stage show in a recording?

    python3 tools/logo-stage/check_projection.py REPLAY.slp [--start -123 --end 6000] [--scale 1] [--animelee]
        [--keep-video FILE.mkv | --video FILE.mkv --start N]

Fighters move in the plane z = 0, the same plane as the stage's collision, so a fighter standing still on the flat
top of the main stage is a point of known world position (x, top y) that the camera should put at one pixel. The
script records the replay with the fixed camera and the stage hidden (fighters on black), finds the frames where a
fighter has stood still for 11 frames on the main stage's flat top with no other fighter close by, measures the
fighter's silhouette, and compares it with `projection.Camera.project`:

  feet     the lowest row of the silhouette minus the row the model gives for the stage top (fighters' soles sit
           on the surface, so this is about 0 to +1 px)
  across   the middle of the silhouette's width minus the model's column for the fighter's x, split by the
           direction the fighter faces (a fighter's body is not centred on its origin, but the two directions
           mirror each other); the slope of that against the column is the horizontal scale error

Everything is robust (medians), because dust, projectiles and other effects pollute some frames.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
import dolphin_frames  # noqa: E402
import plate  # noqa: E402
import replay_events  # noqa: E402
import stagedata  # noqa: E402
from slp2alpha import locate, slp  # noqa: E402

IDLE_HALF_WINDOW = 5      # frames either side in which the fighter must not have moved
FAR = 45.0                # world units: other fighters must be at least this far away
BACKGROUND = 20           # brightest channel at or below this is background
SHIELD_STATES = range(178, 183)   # GuardOn .. GuardReflect: the shield bubble is bigger than the fighter


def decode(video: Path, ffmpeg: str, width: int, height: int):
    import numpy as np

    proc = subprocess.Popen([ffmpeg, "-nostdin", "-v", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                            stdout=subprocess.PIPE)
    size = width * height * 3
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                return
            yield np.frombuffer(buf, np.uint8).reshape(height, width, 3)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def idle_samples(frames, top_y: float, flat: Tuple[float, float], first: int, last: int):
    """(frame, port, Fighter) of fighters that stand still on the flat top, away from the others."""
    out = []
    for f in range(first + IDLE_HALF_WINDOW, last - IDLE_HALF_WINDOW):
        here = frames.get(f)
        if not here:
            continue
        for port, a in here.items():
            if a.state in SHIELD_STATES or a.airborne or abs(a.y - top_y) > 0.02 or not (flat[0] + 3 < a.x < flat[1] - 3):
                continue
            if any(abs(o.x - a.x) < FAR for p, o in here.items() if p != port):
                continue
            still = True
            for g in range(f - IDLE_HALF_WINDOW, f + IDLE_HALF_WINDOW + 1):
                b = frames.get(g, {}).get(port)
                if b is None or abs(b.x - a.x) > 0.01 or abs(b.y - a.y) > 0.01 or b.airborne:
                    still = False
                    break
            if still:
                out.append((f, port, a))
    return out


def measure(img, u_pred: float, v_pred: float, scale: float):
    import numpy as np

    h, w, _ = img.shape
    corners = np.concatenate([img[:8, :8].reshape(-1, 3), img[:8, -8:].reshape(-1, 3),
                              img[-8:, :8].reshape(-1, 3), img[-8:, -8:].reshape(-1, 3)])
    bg = np.median(corners, axis=0).astype(int)   # the clear colour: the stage is hidden, so only fighters differ
    c0, c1 = max(0, int(u_pred - 30 * scale)), min(w, int(u_pred + 30 * scale))
    r0, r1 = max(0, int(v_pred - 70 * scale)), min(h, int(v_pred + 14 * scale))
    mask = np.abs(img[r0:r1, c0:c1].astype(int) - bg).max(axis=2) > BACKGROUND
    if mask.sum() < 40 * scale * scale:
        return None
    cols = np.nonzero(mask.sum(axis=0) >= 2)[0]
    rows = np.nonzero(mask.sum(axis=1) >= 3)[0]
    if len(cols) == 0 or len(rows) == 0:
        return None
    return (c0 + 0.5 * (cols[0] + cols[-1]) + 0.5, r0 + rows[-1] + 1.0, c0 + cols[0], c0 + cols[-1] + 1)


def fit_line(xs: List[float], ys: List[float]) -> Tuple[float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return slope, my - slope * mx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("replay")
    ap.add_argument("--start", type=int, default=-123)
    ap.add_argument("--end", type=int)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--animelee", action="store_true")
    ap.add_argument("--video", help="use this recording of the same window instead of playing the replay")
    ap.add_argument("--keep-video", help="copy the recording here")
    ap.add_argument("--offset", type=int, help="video frame n shows replay frame start + n + OFFSET (default 0; only matters for fighters that move)")
    ap.add_argument("--crops", type=int, default=0, help="save this many annotated crops of measured fighters")
    ap.add_argument("--crops-out", default="crops.png")
    ap.add_argument("--json", help="write the measurements here")
    ap.add_argument("--iso")
    args = ap.parse_args()

    replay = Path(args.replay).expanduser()
    info = slp.read_replay(replay)
    geo = stagedata.load_stage(info.stage_id, args.iso)
    cam = plate.camera_of(geo)
    end = min(args.end if args.end is not None else info.last_frame, info.last_frame)
    width, height = cam.size(args.scale)
    ffmpeg = locate.find_ffmpeg()
    frames = replay_events.fighter_frames(replay)

    tmp = None
    if args.video:
        video = Path(args.video)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="logo-stage-check-"))
        print(f"{geo.name}: playing frames {args.start}..{end} with the fixed camera, stage hidden")
        video = dolphin_frames.record(replay, args.start, end, tmp, animelee=args.animelee, scale=args.scale,
                                      static_camera=True, stage_hidden=True)
        if args.keep_video:
            Path(args.keep_video).write_bytes(video.read_bytes())

    m = geo.main_stage
    samples = idle_samples(frames, m.top_y, m.top_x, args.start, end)
    print(f"{len(samples)} idle fighter frames on the flat top ({m.top_x[0]:.1f}..{m.top_x[1]:.1f})")
    by_video_frame: Dict[int, List[Tuple[int, int, object]]] = defaultdict(list)
    offsets = [args.offset] if args.offset is not None else [0]
    for f, port, a in samples:
        by_video_frame[f - args.start + offsets[0]].append((f, port, a))

    rows = []
    shots = []
    for n, img in enumerate(decode(video, ffmpeg, width, height)):
        for f, port, a in by_video_frame.get(n, ()):
            u, v = cam.project((a.x, a.y, 0.0), args.scale)
            got = measure(img, u, v, args.scale)
            if got is not None:
                rows.append((a.x, a.facing, a.character, u, v, got[0], got[1], got[2], got[3]))
                if args.crops and len(shots) < args.crops and (len(rows) % max(1, len(samples) // args.crops) == 0):
                    shots.append((f, a, u, v, got, img[max(0, int(v) - 90):int(v) + 30, max(0, int(u) - 50):int(u) + 50].copy(),
                                  (max(0, int(u) - 50), max(0, int(v) - 90))))
    if shots:
        from PIL import Image, ImageDraw
        tiles = []
        for f, a, u, v, got, crop, (cx, cy) in shots:
            k = 4
            tile = Image.fromarray(crop).resize((crop.shape[1] * k, crop.shape[0] * k), Image.NEAREST)
            d = ImageDraw.Draw(tile)
            px, py = (u - cx) * k, (v - cy) * k
            d.line([(px - 14, py), (px + 14, py)], fill=(255, 0, 255), width=1)       # where the model puts (x, stage top)
            d.line([(px, py - 14), (px, py + 14)], fill=(255, 0, 255), width=1)
            d.line([(0, (got[1] - cy) * k), (tile.width, (got[1] - cy) * k)], fill=(0, 255, 0), width=1)   # lowest row found
            d.line([((got[0] - cx) * k, 0), ((got[0] - cx) * k, tile.height)], fill=(0, 255, 255), width=1)  # middle found
            d.text((3, 3), f"f{f} x{a.x:.1f} st{a.state}", fill=(255, 255, 0))
            tiles.append(tile)
        sheet = Image.new("RGB", (tiles[0].width * min(4, len(tiles)), tiles[0].height * ((len(tiles) + 3) // 4)))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % 4) * t.width, (i // 4) * t.height))
        sheet.save(args.crops_out)
        print(f"wrote {args.crops_out}")
    if tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    if len(rows) < 20:
        print("too few measurable frames")
        return 1

    s = float(args.scale)
    feet = [(r[6] - r[4]) / s for r in rows]
    print(f"\n{len(rows)} measured frames, {len({r[2] for r in rows})} characters")
    print(f"feet row minus model row of the stage top: median {statistics.median(feet):+.2f} px "
          f"(middle half {statistics.quantiles(feet, n=4)[0]:+.2f} .. {statistics.quantiles(feet, n=4)[2]:+.2f}) at scale 1")
    per_char: Dict[int, List[float]] = defaultdict(list)
    for r in rows:
        per_unit = cam.pixels_per_unit(r[0], m.top_y, 0.0, args.scale)[1]
        per_char[r[2]].append((r[6] - r[4]) / per_unit)
    print("feet below the stage top, in game units, per character id: "
          + ", ".join(f"{c}: {statistics.median(v):+.2f} (n={len(v)})" for c, v in sorted(per_char.items())))
    if args.json:
        import json
        plain = [[float(c) for c in r] for r in rows]
        Path(args.json).write_text(json.dumps({"stage": info.stage_id, "replay": replay.name, "rows": plain,
                                               "per_char_units": {str(c): [float(x) for x in v] for c, v in per_char.items()}}))

    res_u = [((r[5] - r[3]) / s, r[1], r[0], r[3] / s, r[2]) for r in rows]
    for facing in (-1.0, 1.0):
        sel = [d for d in res_u if (d[1] > 0) == (facing > 0)]
        if sel:
            print(f"across, facing {'right' if facing > 0 else 'left '}: median {statistics.median(d[0] for d in sel):+.2f} px over {len(sel)}")
    # slope against the column: remove the facing and character offsets first
    groups: Dict[Tuple[int, bool], List[Tuple[float, float]]] = defaultdict(list)
    for d in res_u:
        groups[(d[4], d[1] > 0)].append((d[3] - 320.0, d[0]))
    xs, ys = [], []
    for (char, right), pts in groups.items():
        if len(pts) < 6:
            continue
        med = statistics.median(p[1] for p in pts)
        for col, val in pts:
            xs.append(col)
            ys.append(val - med)
    if xs and (max(xs) - min(xs)) > 60:
        slope, _ = fit_line(xs, ys)
        print(f"horizontal scale error from {len(xs)} frames spanning {min(xs):+.0f}..{max(xs):+.0f} px: "
              f"{100 * slope:+.2f} %  (the model's column error grows by {slope * 100:.2f} px per 100 px from the centre)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (locate.NotFound, RuntimeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
