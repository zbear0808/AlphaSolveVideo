#!/usr/bin/env python3
"""Checks that a camera export is exact: the game's numbers, on the right frames, and the same in Blender.

    python3 tools/camera-export/validate_camera.py check  CAMERA.json [--raw camera.csv]
    python3 tools/camera-export/validate_camera.py static REPLAY.slp [--start 600 --end 900]
    python3 tools/camera-export/validate_camera.py track  REPLAY.slp [--start N --end M] [--scale 1]
    python3 tools/camera-export/validate_camera.py track  --camera CAMERA.json --alpha-map ALPHAMAP.mov --replay REPLAY.slp
    python3 tools/camera-export/validate_camera.py blender CAMERA.json
    python3 tools/camera-export/validate_camera.py overlay CAMERA.json --replay REPLAY.slp [--every 30] [--video out.mp4]
    python3 tools/camera-export/validate_camera.py compare A.json B.json
    python3 tools/camera-export/validate_camera.py readonly REPLAY.slp [--start 1500 --end 1799]

check     the file on its own: counts, frame numbers, projection settings, roll, camera modes, and that each view
          matrix is the game's look-at of its eye and look-at point. --raw (the CSV in a `render --keep` work
          folder) adds the check that the drawn camera is the game camera plus the shake.
static    renders a clip with --static-camera and compares every sample with the stage's fixed camera from the ISO.
track     which video frame each sample belongs to: measures standing fighters in the alpha map, and fits how far
          they follow a one-frame shift of the camera samples or of the fighters' positions (0: right, +-1: a
          frame off). Exits 1 if a fit is half a frame or more from 0, or the camera offset with the smallest
          spread isn't 0; 3 if there are too few samples to tell.
blender   imports the file in Blender (headless) and compares Blender's pixels with projection.LookAtCamera's.
overlay   draws the stage's floors and ledges and the fighters' positions on frames of the transparent video.
compare   two exports of the same replay (a clip and a whole render, or two runs) have the same samples.
readonly  the same clip with and without --export-camera: the same recorded frames, the same solved frames.

docs/camera-export.md has what each check found. Needs numpy and Pillow for track and overlay.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SLP2ALPHA = REPO / "tools" / "slp2alpha"
sys.path.insert(0, str(SLP2ALPHA))
sys.path.insert(0, str(REPO / "tools" / "logo-stage"))
import projection  # noqa: E402
import replay_events  # noqa: E402
import stagedata  # noqa: E402
from slp2alpha import camera, locate, slp  # noqa: E402

FAR = 45.0                       # other fighters must be at least this far away (check_projection.py)
SHIELD_STATES = range(178, 183)  # GuardOn .. GuardReflect: the shield bubble is bigger than the fighter
ALPHA_ON = 40                    # alpha-map level (0-255) that counts as part of a fighter
MIN_SAMPLES = 200
BLENDER_TOLERANCE_PX = 0.01


def fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def size_of(doc: dict) -> Tuple[int, int]:
    return int(doc["render"]["width"]), int(doc["render"]["height"])


def cameras(doc: dict) -> List[projection.LookAtCamera]:
    aspect = float(doc["projection"]["aspect"])
    return [projection.from_sample(s, aspect) for s in doc["samples"]]


# ---------------------------------------------------------------- check
def check_export(doc: dict, static_camera: Optional[bool] = None) -> List[str]:
    problems: List[str] = []
    samples, frames = doc["samples"], doc["frames"]
    if frames["count"] != len(samples):
        problems.append(f"frames.count {frames['count']} but {len(samples)} samples")
    # One video frame without a sample is the game's last frame, after the replay's last frame request.
    last_frame_only = frames.get("video") == len(samples) + 1 and frames["last"] == frames.get("replay_last")
    if frames.get("video") != len(samples) and not last_frame_only:
        problems.append(f"{len(samples)} samples for a {frames.get('video')}-frame video")
    labels = [s["frame"] for s in samples]
    gaps = [b for a, b in zip(labels, labels[1:]) if b != a + 1]
    if gaps:
        problems.append(f"frame numbers jump at {camera.frame_ranges(gaps)}")
    if samples and (labels[0], labels[-1]) != (frames["first"], frames["last"]):
        problems.append("frames.first / frames.last don't match the samples")
    p = doc["projection"]
    if (struct.pack(">f", p["aspect"]).hex() != camera.ASPECT_BITS or tuple(p["viewport"]) != camera.VIEWPORT
            or not 0 < p["near"] < p["far"] or p.get("type") != "perspective"):
        problems.append(f"unexpected projection {p}")
    clip = sorted({(s["near"], s["far"]) for s in samples if "near" in s})
    if clip:
        print(f"  near and far change during the export: {clip[:4]} besides {p['near']}, {p['far']}")
    if doc["render"].get("fps") != camera.OUTPUT_RATE:
        problems.append(f"render.fps is {doc['render'].get('fps')}, not {camera.OUTPUT_RATE}")
    rolled = [s["frame"] for s in samples if s.get("roll") or s.get("up")]
    if rolled:
        problems.append(f"roll or up vector on frames {camera.frame_ranges(rolled)}")
    worst_rot = worst_pos = 0.0
    for s in samples:
        eye, interest = [camera.f32(v) for v in s["eye"]], [camera.f32(v) for v in s["interest"]]
        mine = camera.look_at(eye, interest, camera.up_hint(eye, interest, s.get("roll", 0.0)))
        for k, (a, b) in enumerate(zip(mine, s["view"])):
            if k % 4 == 3:
                worst_pos = max(worst_pos, abs(a - b))
            else:
                worst_rot = max(worst_rot, abs(a - b))
    if worst_rot > camera.MATRIX_TOLERANCE[0] or worst_pos > camera.MATRIX_TOLERANCE[1]:
        problems.append(f"view matrices off by {worst_rot:.1e} (rotation), {worst_pos:.1e} (translation)")
    modes = sorted({s["mode"] for s in samples})
    if static_camera is None:
        static_camera = modes == [camera.FIXED]
    want = camera.FIXED if static_camera else camera.STANDARD
    if modes != [want]:
        problems.append(f"camera modes {modes}, expected only {want}")
    if static_camera and any(s["shake"] != [0.0, 0.0] for s in samples):
        problems.append("the fixed camera shakes (Disable Screen Shake should be on)")
    print(f"  {len(samples)} samples, frames {labels[0] if labels else '-'}..{labels[-1] if labels else '-'}, "
          f"video {frames.get('video')} frames; view matrices within {worst_rot:.1e} / {worst_pos:.1e}")
    shaking = [s for s in samples if s["shake"] != [0.0, 0.0]]
    if shaking:
        big = max(max(abs(v) for v in s["shake"]) for s in shaking)
        print(f"  shake on {len(shaking)} frames, at most {big:.2f} units")
    return problems


def cmd_check(args) -> int:
    doc = camera.load(Path(args.camera))
    print(f"{Path(args.camera).name}:")
    problems = check_export(doc)
    if args.raw:
        rows = camera.read_csv(Path(args.raw))
        rows = [r for r in rows if doc["frames"]["first"] <= r.frame <= doc["frames"]["last"]]
        raw = camera.check_rows(rows, doc["stage"]["id"], doc["samples"][0]["mode"] == camera.FIXED)
        print(f"  raw rows checked: {len(rows)} (the drawn camera against the game camera plus shake)")
        problems += raw
    for p in problems:
        print(f"  problem: {p}")
    print("PASS" if not problems else "FAIL")
    return 0 if not problems else 1


# ---------------------------------------------------------------- rendering through slp2alpha
def render(replay: Path, out_dir: Path, extra: Sequence[str], keep: bool = True) -> Dict[str, Path]:
    cmd = [sys.executable, "-m", "slp2alpha", "render", str(replay), "--out-dir", str(out_dir), *extra]
    if keep:
        cmd.append("--keep")
    p = subprocess.run(cmd, cwd=SLP2ALPHA, capture_output=True, encoding="utf-8", errors="replace",
                       env=locate.utf8_child_env())
    text = (p.stdout + p.stderr).replace("\r", "\n")
    if p.returncode != 0:
        raise RuntimeError(f"slp2alpha render failed ({p.returncode}):\n" + "\n".join(text.splitlines()[-15:]))
    found: Dict[str, Path] = {}
    for line in text.splitlines():
        line = line.strip()
        path = Path(line)
        for key, prefix in (("transparent", "fullTransparent - "), ("alpha_map", "alphaMap - "),
                            ("camera", "camera - ")):
            if path.is_absolute() and path.name.startswith(prefix):
                found[key] = path
        m = re.match(r"work folder kept: (.+)", line)
        if m:
            found["work"] = Path(m.group(1).strip())
    found["warnings"] = [ln.strip() for ln in text.splitlines() if "warning:" in ln]  # type: ignore[assignment]
    return found


# ---------------------------------------------------------------- static
def cmd_static(args) -> int:
    replay = Path(args.replay).expanduser()
    info = slp.read_replay(replay)
    geo = stagedata.load_stage(info.stage_id, args.iso)
    tmp = Path(tempfile.mkdtemp(prefix="camera-static-"))
    out: Dict[str, Path] = {}
    try:
        extra = ["--characters-only", "--static-camera", "--export-camera", "--start-frame", str(args.start),
                 "--end-frame", str(args.end)] + (["--animelee"] if args.animelee else [])
        out = render(replay, tmp, extra)
        for w in out["warnings"]:
            print(f"  {w}")
        doc = camera.load(out["camera"])
        c = geo.camera
        want_eye = [camera.f32(v) for v in c.eye]
        want_interest = projection.game_interest(c.eye, c.vert_angle_deg, c.horz_angle_deg)
        worst = 0.0
        for s in doc["samples"]:
            worst = max(worst, max(abs(a - b) for a, b in zip(s["eye"], want_eye)),
                        max(abs(a - b) for a, b in zip(s["interest"], want_interest)), abs(s["fov"] - c.fov_deg))
        print(f"{geo.name}: {len(doc['samples'])} samples; fixed camera from the ISO: eye {c.eye}, look-at "
              f"({want_interest[0]:.4f}, {want_interest[1]:.4f}, 0), fov {c.fov_deg}")
        print(f"  largest difference from it: {worst:.2e}")
        problems = check_export(doc, static_camera=True)
        rows = camera.read_csv(out["work"] / "camera.csv")
        problems += camera.check_rows([r for r in rows if r.frame >= doc["frames"]["first"]], info.stage_id, True)
        if worst > 1e-4:
            problems.append(f"the samples differ from the stage's fixed camera by up to {worst:.2e}")
        for p in problems:
            print(f"  problem: {p}")
        print("PASS" if not problems else "FAIL")
        return 0 if not problems else 1
    finally:
        if out.get("work"):
            shutil.rmtree(out["work"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- track
def gray_frames(video: Path, width: int, height: int) -> Iterator["object"]:
    import numpy as np

    proc = subprocess.Popen([locate.find_ffmpeg(), "-nostdin", "-v", "error", "-i", str(video), "-f", "rawvideo",
                             "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    size = width * height
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                return
            yield np.frombuffer(buf, np.uint8).reshape(height, width)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def measure(img, cam, x: float, y: float, size) -> Optional[Tuple[float, float]]:
    """(middle column, bottom edge) of the silhouette around a fighter at (x, y, 0), or None."""
    import numpy as np

    ppu_x, ppu_y = cam.pixels_per_unit(x, y, 0.0, size=size)
    u, v = cam.project((x, y, 0.0), size=size)
    h, w = img.shape
    c0, c1 = int(u - 18 * ppu_x), int(u + 18 * ppu_x) + 1
    r0, r1 = int(v - 40 * ppu_y), int(v + 8 * ppu_y) + 1
    if c0 < 0 or r0 < 0 or c1 > w or r1 > h:
        return None
    mask = img[r0:r1, c0:c1] > ALPHA_ON
    if mask.sum() < 40:
        return None
    cols = np.nonzero(mask.sum(axis=0) >= 2)[0]
    rows = np.nonzero(mask.sum(axis=1) >= 3)[0]
    if len(cols) == 0 or len(rows) == 0 or cols[0] == 0 or cols[-1] == mask.shape[1] - 1 or rows[-1] == mask.shape[0] - 1:
        return None  # touching the window: another fighter, or cut off
    return c0 + 0.5 * (cols[0] + cols[-1]) + 0.5, r0 + rows[-1] + 1.0


def standing(f, top_y: float, flat: Tuple[float, float]) -> bool:
    return (not f.airborne and f.state not in SHIELD_STATES and abs(f.y - top_y) <= 0.02
            and flat[0] + 3 < f.x < flat[1] - 3)


def track_measure(doc: dict, alpha_map: Path, replay: Path, iso: Optional[str]):
    """Measured silhouettes: one record per (video frame, fighter) that passes the rules."""
    size = size_of(doc)
    cams = cameras(doc)
    fighters = replay_events.fighter_frames(replay)
    geo = stagedata.load_stage(doc["stage"]["id"], iso)
    m = geo.main_stage
    records = []
    for k, img in enumerate(gray_frames(alpha_map, *size)):
        if k >= len(cams):
            break
        label = doc["samples"][k]["frame"]
        now = fighters.get(label - 1, {})
        for port, f in now.items():
            hist = [fighters.get(label + d, {}).get(port) for d in (-2, -1, 0)]
            if any(h is None or not standing(h, m.top_y, m.top_x) for h in hist):
                continue
            if any(abs(o.x - f.x) < FAR for p, o in now.items() if p != port):
                continue
            got = measure(img, cams[k], f.x, f.y, size)
            if got is not None:
                records.append((k, label, port, f.character, got[0], got[1]))
    return records, fighters, cams, size, geo


def _moving(fighters, label: int, port: int) -> bool:
    """Whether a fighter moves across frames label - 2 .. label: its silhouette then sits differently around its
    origin (a run leans and trails), so residuals are grouped by this too."""
    return abs(fighters[label][port].x - fighters[label - 2][port].x) >= 0.04


def track_scores(records, fighters, cams, size):
    """Spread of the residuals for every (camera offset, fighter offset), on all samples and on the moving ones."""
    import numpy as np

    out = {}
    cam_moving, fighter_moving = set(), set()
    for i, (k, label, port, _, _, _) in enumerate(records):
        f = fighters[label - 1][port]
        if k > 0:
            a = cams[k].project((f.x, f.y, 0.0), size=size)
            b = cams[k - 1].project((f.x, f.y, 0.0), size=size)
            if math.hypot(a[0] - b[0], a[1] - b[1]) >= 1.0:
                cam_moving.add(i)
        g = fighters.get(label - 2, {}).get(port)
        if g is not None and abs(f.x - g.x) >= 0.5:
            fighter_moving.add(i)
    for dc in range(-2, 3):
        for df in (-2, -1, 0):
            rows = []
            for i, (k, label, port, char, um, vm) in enumerate(records):
                if not 0 <= k + dc < len(cams):
                    continue
                f = fighters.get(label + df, {}).get(port)
                if f is None:
                    continue
                cam = cams[k + dc]
                u, v = cam.project((f.x, f.y, 0.0), size=size)
                ppx, ppy = cam.pixels_per_unit(f.x, f.y, 0.0, size=size)
                group = (char, f.facing > 0, _moving(fighters, label, port))
                rows.append((i, group, (um - u) / ppx, (vm - v) / ppy))
            groups = defaultdict(list)
            for r in rows:
                groups[r[1]].append(r[2])
            med = {g: statistics.median(v) for g, v in groups.items()}
            feet_all = [r[3] for r in rows]
            feet_med = statistics.median(feet_all) if feet_all else 0.0

            def spread(sel):
                pick = [r for r in rows if sel is None or r[0] in sel]
                if not pick:
                    return float("nan"), 0
                across = np.array([r[2] - med[r[1]] for r in pick])
                feet = np.array([r[3] - feet_med for r in pick])
                return float(np.median(np.abs(across)) + np.median(np.abs(feet))), len(pick)

            out[(dc, df)] = {"all": spread(None), "camera_moving": spread(cam_moving),
                             "fighter_moving": spread(fighter_moving), "feet_median": feet_med}
    return out, len(cam_moving), len(fighter_moving)


def _slope(pairs) -> Tuple[float, float, int]:
    """Least-squares s in r = s * d over 2-D (residual, shift) pairs, with one pass dropping outliers.
    Returns (s, standard error, samples used)."""
    import numpy as np

    if len(pairs) < 3:
        return float("nan"), float("nan"), len(pairs)
    r = np.array([p[0] for p in pairs], float)
    d = np.array([p[1] for p in pairs], float)
    keep = np.ones(len(r), bool)
    for _ in range(2):
        dd = (d[keep] * d[keep]).sum()
        s = float((r[keep] * d[keep]).sum() / dd)
        err = np.linalg.norm(r - s * d, axis=1)
        keep = err <= 4 * np.median(err[keep]) + 1e-9
    dd = (d[keep] * d[keep]).sum()
    s = float((r[keep] * d[keep]).sum() / dd)
    res = r[keep] - s * d[keep]
    n = int(keep.sum())
    se = float(np.sqrt((res * res).sum() / max(1, 2 * n - 1) / dd))
    return s, se, n


def track_slopes(records, fighters, cams, size):
    """How far the measured fighters follow a one-frame shift of the camera, and of the fighters.

    For each measured fighter: the residual against the export's alignment (camera of the same video frame,
    fighter at frame - 1), minus each character's own offset, and how far the point would move if the camera
    were one frame later (or the fighter one frame later). The fitted slope estimates the error in frames: 0
    means the alignment is right, +-1 that the picture matches the neighbouring frame's camera or position.
    Camera shifts are measured on fighters standing still, so a running fighter's lean, which goes with its
    motion and with the camera following it, doesn't count as camera error."""
    bias = defaultdict(list)
    base = []
    for k, label, port, char, um, vm in records:
        f = fighters[label - 1][port]
        u, v = cams[k].project((f.x, f.y, 0.0), size=size)
        moving = _moving(fighters, label, port)
        base.append((um - u, vm - v, moving))
        bias[(char, f.facing > 0, moving)].append(um - u)
    med_u = {g: statistics.median(v) for g, v in bias.items()}
    med_v = statistics.median(b[1] for b in base) if base else 0.0
    cam_next, cam_prev, fighter_next = [], [], []
    for (k, label, port, char, um, vm), (du, dv, moving) in zip(records, base):
        f = fighters[label - 1][port]
        r = (du - med_u[(char, f.facing > 0, moving)], dv - med_v)
        p0 = cams[k].project((f.x, f.y, 0.0), size=size)
        if not moving:
            for other, out in ((k + 1, cam_next), (k - 1, cam_prev)):
                if 0 <= other < len(cams):
                    p1 = cams[other].project((f.x, f.y, 0.0), size=size)
                    d = (p1[0] - p0[0], p1[1] - p0[1])
                    if math.hypot(*d) >= 0.25:
                        out.append((r, d))
        g = fighters[label][port]
        p1 = cams[k].project((g.x, g.y, 0.0), size=size)
        d = (p1[0] - p0[0], p1[1] - p0[1])
        if math.hypot(*d) >= 0.25:
            fighter_next.append((r, d))
    return {"camera one frame later": _slope(cam_next), "camera one frame earlier": _slope(cam_prev),
            "fighters one frame later": _slope(fighter_next)}


SLOPE_LIMIT = 0.5   # the offset is a whole number of frames: within half a frame of 0, it is 0


def cmd_track(args) -> int:
    args.replay = args.replay or args.replay_opt
    if args.camera:
        if not (args.alpha_map and args.replay):
            print("error: --camera needs --alpha-map and --replay", file=sys.stderr)
            return 2
        cam_path, alpha_map, replay = Path(args.camera), Path(args.alpha_map), Path(args.replay).expanduser()
        tmp = None
    else:
        if not args.replay:
            print("error: give a replay, or --camera, --alpha-map and --replay", file=sys.stderr)
            return 2
        replay = Path(args.replay).expanduser()
        tmp = Path(tempfile.mkdtemp(prefix="camera-track-"))
        extra = ["--characters-only", "--hide-effects", "--hide-items", "--export-camera", "--scale", str(args.scale)]
        if args.start is not None:
            extra += ["--start-frame", str(args.start)]
        if args.end is not None:
            extra += ["--end-frame", str(args.end)]
        print(f"rendering {replay.name} {' '.join(extra)}")
        out = render(replay, tmp, extra, keep=False)
        for w in out["warnings"]:
            print(f"  {w}")
        cam_path, alpha_map = out["camera"], out["alpha_map"]
    try:
        doc = camera.load(cam_path)
        records, fighters, cams, size, geo = track_measure(doc, alpha_map, replay, args.iso)
        print(f"{geo.name}: {len(records)} measured fighter frames in {len(doc['samples'])} video frames")
        scores, n_cam, n_fighter = track_scores(records, fighters, cams, size)
        print(f"  camera moved >= 1 px on {n_cam} of them, the fighter >= 0.5 units on {n_fighter}")
        print("  spread of the residuals in replay units (across + feet), by camera offset and fighter offset:")
        print("    camera  fighter      all   camera moving   fighter moving")
        for (dc, df), s in sorted(scores.items()):
            mark = "  <- the export's alignment" if (dc, df) == (0, -1) else ""
            print(f"    {dc:+4d}    {df:+4d}    {s['all'][0]:7.3f}   {s['camera_moving'][0]:9.3f}       "
                  f"{s['fighter_moving'][0]:9.3f}{mark}")
        best = min(scores, key=lambda key: scores[key]["all"][0])
        base = scores[(0, -1)]
        problems, unsure = [], []
        # The camera offset by the spread: on the best row of fighter offsets, camera offset 0 must spread least.
        best_dc = min(range(-2, 3), key=lambda dc: scores[(dc, best[1])]["all"][0])
        if best_dc != 0:
            problems.append(f"the smallest spread is at camera offset {best_dc:+d}, not 0")
        print(f"  smallest spread at camera {best[0]:+d}, fighters {best[1]:+d}")
        print("  how far the measured fighters follow a one-frame shift (0: the export's alignment is right, "
              "1: a whole frame off):")
        slopes = track_slopes(records, fighters, cams, size)
        for what, (s, se, n) in slopes.items():
            print(f"    {what:26s} {s:+.3f} +- {2 * se:.3f} (95%), {n} samples")
            if n < MIN_SAMPLES // 2 or not abs(s) + 2 * se < SLOPE_LIMIT and abs(s) <= SLOPE_LIMIT:
                unsure.append(f"{what}: {n} samples, {s:+.2f} +- {2 * se:.2f} doesn't settle it")
            elif abs(s) + 2 * se >= SLOPE_LIMIT:
                problems.append(f"{what}: the fighters follow the shift by {s:+.2f} of a frame")
        print(f"  feet below the stage top at the export's alignment: median {base['feet_median']:+.2f} units")
        if args.json:
            Path(args.json).write_text(json.dumps({"spread": {f"{dc},{df}": s for (dc, df), s in scores.items()},
                                                   "slopes": slopes}, indent=1), encoding="utf-8")
        for p in problems:
            print(f"  problem: {p}")
        for u in unsure:
            print(f"  inconclusive: {u}")
        if problems:
            print("FAIL")
            return 1
        print("INCONCLUSIVE" if unsure else "PASS")
        return 3 if unsure else 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- blender
def find_blender(explicit: Optional[str]) -> str:
    sys.path.insert(0, str(REPO / "tools" / "logo-stage"))
    import plate

    return plate.find_blender(explicit)


def probe_frames(doc: dict) -> List[int]:
    n = len(doc["samples"])
    eyes = [s["eye"] for s in doc["samples"]]
    moves = sorted(range(1, n), key=lambda i: -math.dist(eyes[i], eyes[i - 1]))[:10]
    return sorted(set(list(range(0, n, 60)) + [0, n - 1] + moves))


def cmd_blender(args) -> int:
    path = Path(args.camera).resolve()
    doc = camera.load(path)
    size = size_of(doc)
    cams = cameras(doc)
    geo = None
    try:
        geo = stagedata.load_stage(doc["stage"]["id"], args.iso)
    except (locate.NotFound, KeyError, OSError):
        pass
    probes: List[Tuple[int, List[float]]] = []
    for k in probe_frames(doc):
        c = cams[k].interest
        pts = [list(c)] + [[c[0] + dx, c[1] + dy, c[2] + dz] for dx, dy, dz in
                           ((20, 0, 0), (-20, 0, 0), (0, 20, 0), (0, -20, 0), (0, 0, 20), (0, 0, -20))]
        if geo:
            m = geo.main_stage
            pts += [[m.ledge_left[0], m.ledge_left[1], 0.0], [m.ledge_right[0], m.ledge_right[1], 0.0],
                    [m.top_x[0], m.top_y, 0.0], [m.top_x[1], m.top_y, 0.0]]
        for p in pts:
            probes.append((k, p))
    blender = find_blender(args.blender)
    problems: List[str] = []
    for label, opts in (("default", {}), ("scaled", {"scale": 0.1, "offset": [3.0, -2.0, 1.0]})):
        frame_start = opts.get("frame_start", 1)
        with tempfile.TemporaryDirectory(prefix="camera-blender-") as tmp:
            job = {"camera": str(path), "options": opts, "out": str(Path(tmp) / "out.json"),
                   "probes": [[frame_start + k, p] for k, p in probes]}
            (Path(tmp) / "job.json").write_text(json.dumps(job), encoding="utf-8")
            done = subprocess.run([blender, "-b", "--factory-startup", "-noaudio", "--python",
                                   str(HERE / "blender_probe.py"), "--", str(Path(tmp) / "job.json")],
                                  capture_output=True, encoding="utf-8", errors="replace")
            if done.returncode != 0 or not (Path(tmp) / "out.json").exists():
                return fail("Blender failed:\n" + "\n".join((done.stdout + done.stderr).splitlines()[-20:]))
            result = json.loads((Path(tmp) / "out.json").read_text(encoding="utf-8"))
        worst = worst_center = 0.0
        for (k, p), got in zip(probes, result["pixels"]):
            want = cams[k].project(p, size=size) if _in_front(cams[k], p) else None
            if want is None:
                continue
            err = math.hypot(got[0] - want[0], got[1] - want[1])
            worst = max(worst, err)
            if p == list(cams[k].interest):
                worst_center = max(worst_center, math.hypot(got[0] - size[0] / 2, got[1] - size[1] / 2))
        sc = result["scene"]
        want_aspect = (float(doc["projection"]["aspect"]) * size[1] / size[0], 1.0)
        print(f"{label}: {len(probes)} probes on {len(set(k for k, _ in probes))} frames: Blender within "
              f"{worst:.5f} px of the model, the look-at point within {worst_center:.6f} px of the centre")
        if worst > BLENDER_TOLERANCE_PX:
            problems.append(f"{label}: Blender is {worst:.4f} px off")
        if worst_center > 1e-3:  # Blender's matrices are float32: about 2e-4 px at 640 px
            problems.append(f"{label}: the look-at point is {worst_center:.6f} px off centre")
        if sc["resolution"] != list(size) or sc["percentage"] != 100:
            problems.append(f"{label}: resolution {sc['resolution']} at {sc['percentage']}%")
        if any(abs(a - b) > 1e-6 for a, b in zip(sc["pixel_aspect"], want_aspect)):
            problems.append(f"{label}: pixel aspect {sc['pixel_aspect']}, expected {want_aspect}")
        if (sc["fps"], sc["fps_base"]) != (60, 1.0):
            problems.append(f"{label}: {sc['fps']} fps, base {sc['fps_base']}")
        want_end = frame_start + max(doc["frames"]["count"], doc["frames"]["video"]) - 1
        if (sc["frame_start"], sc["frame_end"]) != (frame_start, want_end):
            problems.append(f"{label}: frame range {sc['frame_start']}..{sc['frame_end']}")
        wrong = [f for f, sf in result["slippi_frame"].items()
                 if sf != doc["samples"][int(f) - frame_start]["frame"]]
        if wrong:
            problems.append(f"{label}: slippi_frame wrong on Blender frames {wrong[:5]}")
    for p in problems:
        print(f"  problem: {p}")
    print("PASS" if not problems else "FAIL")
    return 0 if not problems else 1


def _in_front(cam, p) -> bool:
    _, _, fwd = cam.axes
    return sum((p[i] - cam.eye[i]) * fwd[i] for i in range(3)) > 1.0


# ---------------------------------------------------------------- overlay
def rgba_frames(video: Path, width: int, height: int):
    import numpy as np

    proc = subprocess.Popen([locate.find_ffmpeg(), "-nostdin", "-v", "error", "-i", str(video), "-f", "rawvideo",
                             "-pix_fmt", "rgba", "-"], stdout=subprocess.PIPE)
    size = width * height * 4
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                return
            yield np.frombuffer(buf, np.uint8).reshape(height, width, 4)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def draw(img, cam, geo, fighters_now, size):
    from PIL import Image, ImageDraw

    base = Image.new("RGBA", (size[0], size[1]), (90, 90, 96, 255))
    base.alpha_composite(Image.fromarray(img))
    d = ImageDraw.Draw(base)

    def px(p):
        try:
            return cam.project(p, size=size)
        except ValueError:
            return None

    for line in geo.lines:
        if line.kind != "floor" or line.dynamic:
            continue
        a, b = px((line.x0, line.y0, 0.0)), px((line.x1, line.y1, 0.0))
        if a and b:
            d.line([a, b], fill=(255, 0, 255, 255), width=1)
    m = geo.main_stage
    for p in (m.ledge_left, m.ledge_right):
        q = px((p[0], p[1], 0.0))
        if q:
            d.line([(q[0] - 8, q[1]), (q[0] + 8, q[1])], fill=(0, 255, 255, 255))
            d.line([(q[0], q[1] - 8), (q[0], q[1] + 8)], fill=(0, 255, 255, 255))
    for f in fighters_now.values():
        q = px((f.x, f.y, 0.0))
        if q:
            d.line([(q[0] - 5, q[1]), (q[0] + 5, q[1])], fill=(255, 230, 0, 255))
            d.line([(q[0], q[1] - 5), (q[0], q[1] + 5)], fill=(255, 230, 0, 255))
    return base.convert("RGB")


def cmd_overlay(args) -> int:
    from PIL import Image, ImageDraw

    path = Path(args.camera)
    doc = camera.load(path)
    size = size_of(doc)
    cams = cameras(doc)
    video = Path(args.video_in) if args.video_in else path.parent / doc["render"]["transparent"]
    geo = stagedata.load_stage(doc["stage"]["id"], args.iso)
    fighters = replay_events.fighter_frames(Path(args.replay).expanduser())
    writer = None
    if args.video:
        writer = subprocess.Popen([locate.find_ffmpeg(), "-nostdin", "-v", "error", "-y", "-f", "rawvideo",
                                   "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}", "-r", "60", "-i", "-",
                                   "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(args.video)],
                                  stdin=subprocess.PIPE)
    tiles = []
    for k, img in enumerate(rgba_frames(video, *size)):
        if k >= len(cams):
            break
        if writer is None and k % args.every:
            continue
        label = doc["samples"][k]["frame"]
        im = draw(img, cams[k], geo, fighters.get(label - 1, {}), size)
        if writer:
            writer.stdin.write(im.tobytes())
        if k % args.every == 0 and len(tiles) < args.tiles:
            ImageDraw.Draw(im).text((6, 6), f"frame {label}", fill=(255, 255, 0))
            tiles.append(im)
    if writer:
        writer.stdin.close()
        writer.wait()
        print(f"wrote {args.video}")
    if tiles:
        cols = min(4, len(tiles))
        w, h = tiles[0].size
        sheet = Image.new("RGB", (cols * w, ((len(tiles) + cols - 1) // cols) * h))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * w, (i // cols) * h))
        out = Path(args.out)
        sheet.save(out)
        print(f"wrote {out} ({len(tiles)} frames)")
    return 0


# ---------------------------------------------------------------- compare
def cmd_compare(args) -> int:
    a, b = camera.load(Path(args.a)), camera.load(Path(args.b))
    sa = {s["frame"]: s for s in a["samples"]}
    sb = {s["frame"]: s for s in b["samples"]}
    common = sorted(set(sa) & set(sb))
    differ = [f for f in common if sa[f] != sb[f]]
    print(f"{len(common)} frames in both ({common[0] if common else '-'}..{common[-1] if common else '-'}); "
          f"{len(differ)} differ{': ' + camera.frame_ranges(differ) if differ else ''}")
    if not common:
        return fail("no frames in common")
    print("PASS" if not differ else "FAIL")
    return 0 if not differ else 1


# ---------------------------------------------------------------- readonly
def frame_hashes(video: Path) -> List[str]:
    out = subprocess.run([locate.find_ffmpeg(), "-nostdin", "-v", "error", "-i", str(video), "-f", "framemd5", "-"],
                         capture_output=True, encoding="utf-8", errors="replace", check=True).stdout
    return [line.rsplit(",", 1)[-1].strip() for line in out.splitlines() if line and not line.startswith("#")]


def rate_of(video: Path) -> str:
    return subprocess.run([locate.find_ffmpeg(name="ffprobe"), "-v", "error", "-select_streams", "v:0",
                           "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(video)],
                          capture_output=True, encoding="utf-8", errors="replace", check=True).stdout.strip()


def cmd_readonly(args) -> int:
    """Effects are hidden: dust and smoke differ by a few pixels between two runs even with nothing changed
    (6 of 600 fields on the Battlefield clip), so they would hide what the export does or doesn't change."""
    replay = Path(args.replay).expanduser()
    tmp = Path(tempfile.mkdtemp(prefix="camera-readonly-"))
    runs = {}
    try:
        for label, extra in (("with", ["--export-camera"]), ("without", [])):
            out = render(replay, tmp / label, ["--characters-only", "--hide-effects", "--start-frame",
                                               str(args.start), "--end-frame", str(args.end), *extra])
            runs[label] = out
        problems = []
        rec = {k: sorted(v["work"].rglob("*.mkv"))[0] for k, v in runs.items()}
        ha, hb = frame_hashes(rec["with"]), frame_hashes(rec["without"])
        differ = sum(a != b for a, b in zip(ha, hb)) + abs(len(ha) - len(hb))
        print(f"raw recordings: {len(ha)} and {len(hb)} fields, {differ} differ")
        if differ:
            problems.append("the raw recordings differ")
        ta, tb = frame_hashes(runs["with"]["transparent"]), frame_hashes(runs["without"]["transparent"])
        differ = sum(a != b for a, b in zip(ta, tb)) + abs(len(ta) - len(tb))
        print(f"solved videos: {len(ta)} and {len(tb)} frames, {differ} differ when decoded")
        if differ:
            problems.append("the solved videos differ")
        ra, rb = rate_of(runs["with"]["transparent"]), rate_of(runs["without"]["transparent"])
        print(f"frame rates: {ra} with the export, {rb} without")
        if ra != camera.OUTPUT_RATE or rb == camera.OUTPUT_RATE:
            problems.append(f"rates {ra} / {rb}")
        for p in problems:
            print(f"  problem: {p}")
        print("PASS" if not problems else "FAIL")
        return 0 if not problems else 1
    finally:
        for v in runs.values():
            if v.get("work"):
                shutil.rmtree(v["work"], ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="the file on its own")
    c.add_argument("camera")
    c.add_argument("--raw", help="Dolphin's camera.csv from the render's work folder (render --keep)")
    c.set_defaults(func=cmd_check)
    s = sub.add_parser("static", help="--static-camera against the stage's fixed camera")
    s.add_argument("replay")
    s.add_argument("--start", type=int, default=600)
    s.add_argument("--end", type=int, default=900)
    s.add_argument("--animelee", action="store_true")
    s.set_defaults(func=cmd_static)
    t = sub.add_parser("track", help="which video frame each sample belongs to")
    t.add_argument("replay", nargs="?")
    t.add_argument("--replay", dest="replay_opt", help="the replay, with --camera and --alpha-map")
    t.add_argument("--start", type=int)
    t.add_argument("--end", type=int)
    t.add_argument("--scale", type=int, default=1)
    t.add_argument("--camera", help="use this export instead of rendering")
    t.add_argument("--alpha-map", help="its alpha map")
    t.add_argument("--json", help="write the scores here")
    t.set_defaults(func=cmd_track)
    b = sub.add_parser("blender", help="Blender's import against the model")
    b.add_argument("camera")
    b.add_argument("--blender")
    b.set_defaults(func=cmd_blender)
    o = sub.add_parser("overlay", help="stage lines and fighters drawn on the video, to look at")
    o.add_argument("camera")
    o.add_argument("--replay", required=True)
    o.add_argument("--video-in", help="the transparent video (default: the one named in the file, next to it)")
    o.add_argument("--every", type=int, default=30)
    o.add_argument("--tiles", type=int, default=12)
    o.add_argument("--out", default="camera-overlay.png")
    o.add_argument("--video", help="also write every frame with the overlay to this MP4")
    o.set_defaults(func=cmd_overlay)
    m = sub.add_parser("compare", help="two exports have the same samples on the frames they share")
    m.add_argument("a")
    m.add_argument("b")
    m.set_defaults(func=cmd_compare)
    r = sub.add_parser("readonly", help="the export changes nothing in the render")
    r.add_argument("replay")
    r.add_argument("--start", type=int, default=1500)
    r.add_argument("--end", type=int, default=1799)
    r.set_defaults(func=cmd_readonly)
    for p in (c, s, t, b, o, m, r):
        p.add_argument("--iso", help="Melee NTSC 1.02 ISO (default: the one set in the Slippi Launcher)")
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (locate.NotFound, RuntimeError, camera.CameraError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
