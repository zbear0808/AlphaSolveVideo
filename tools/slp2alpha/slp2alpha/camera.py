"""The camera export: Melee's camera for every frame of a render (`render --export-camera`).

The patched Dolphin (tools/dolphin-build/patches-mainline/0004-camera-export.patch) writes one CSV row per
recorded playback frame when it's given `--camera-out`. This module checks those rows, picks the one for each
video frame, and writes `camera - NAME.json` next to the videos (docs/camera-export.md). Renders without
--export-camera never get here, and Dolphin doesn't read the camera for them.
"""

from __future__ import annotations

import csv
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import slp

FORMAT = "alphasolve-camera"
VERSION = 1
CSV_HEADER = "# alphasolve-camera 1"
DOLPHIN_OPTION = "--camera-out"
# Camera exports label their videos exactly 60 fps, frame N at N/60 s. (NTSC really runs at 60000/1001.)
OUTPUT_RATE = "60/1"

ASPECT_BITS = "3f9bd194"            # 1.2173333, the main camera's aspect (camera.c, cm_803BCB64)
VIEWPORT = (0.0, 640.0, 0.0, 480.0)
# Near and far are 0.1 and 16384 unless the stage sets its own (Camera_800311DC, Camera_800311CC): Final
# Destination uses 1 and 30000. They only clip depth; the picture doesn't depend on them.
STANDARD, FIXED = 0, 4              # CameraType: the following camera, and the fixed one (--static-camera)
LEGAL_STAGES = {2, 3, 8, 28, 31, 32}   # the eye is only clamped on other stages (Camera_8002AF68)
MATRIX_TOLERANCE = (1e-5, 1e-3)        # rotation, translation: the console computes in float32


def f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


@dataclass
class Row:
    """One CSV row. `values` are the exact float32s (for checks); `plain` the numbers as written (for output)."""
    frame: int
    ok: bool
    mode: int
    values: Dict[str, float]
    plain: Dict[str, float]

    def vec(self, prefix: str, axes: str = "xyz") -> List[float]:
        return [self.values[f"{prefix}_{a}"] for a in axes]

    @property
    def view(self) -> List[float]:
        return [self.values[f"m{i}{j}"] for i in range(3) for j in range(4)]


class CameraError(ValueError):
    pass


def read_csv(path: Path) -> List[Row]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != CSV_HEADER:
        raise CameraError(f"{path} is not a camera file from the patched Dolphin (first line {lines[:1]})")
    rows = []
    for rec in csv.DictReader(lines[1:]):
        plain = {k: float(v) for k, v in rec.items() if k not in ("frame", "ok", "mode") and v not in ("", None)}
        rows.append(Row(int(rec["frame"]), rec["ok"] == "1", int(rec["mode"]),
                        {k: f32(v) for k, v in plain.items()}, plain))
    return rows


# ------------------------------------------------------------------ the game's view maths (cobj.c)
def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return [a[0] / n, a[1] / n, a[2] / n]


def up_hint(eye: Sequence[float], interest: Sequence[float], roll: float) -> List[float]:
    """roll2upvec: world up made perpendicular to the view direction, then turned by -roll about it."""
    e = _unit(_sub(interest, eye))
    if 1.0 - abs(e[1]) < 0.0001:
        x = math.sqrt(e[1] * e[1] + e[2] * e[2])
        v0 = [x, -e[1] * e[0] / x, -e[2] * e[0] / x]
    else:
        h = math.sqrt(e[0] * e[0] + e[2] * e[2])
        v0 = [-e[0] * e[1] / h, h, -e[2] * e[1] / h]
    if roll:
        c, s = math.cos(-roll), math.sin(-roll)   # Rodrigues: about e by -roll (PSMTXRotAxisRad)
        kv, kd = _cross(e, v0), _dot(e, v0)
        v0 = [v0[i] * c + kv[i] * s + e[i] * kd * (1 - c) for i in range(3)]
    return _unit(v0)


def look_at(eye: Sequence[float], interest: Sequence[float], up: Sequence[float]) -> List[float]:
    """C_MTXLookAt: the 3 x 4 view matrix, row-major."""
    look = _unit(_sub(eye, interest))
    right = _unit(_cross(up, look))
    up2 = _cross(look, right)
    out: List[float] = []
    for axis in (right, up2, look):
        out += axis + [-_dot(axis, eye)]
    return out


# ------------------------------------------------------------------ checks
def frame_ranges(frames: Sequence[int], most: int = 6) -> str:
    """1, 2, 3, 7 -> "1..3, 7"."""
    out: List[str] = []
    for f in frames:
        if out and f == last + 1:
            out[-1] = f"{out[-1].split('..')[0]}..{f}"
        else:
            out.append(str(f))
        last = f
    return ", ".join(out[:most]) + (" ..." if len(out) > most else "")


def check_rows(rows: Sequence[Row], stage_id: int, static_camera: bool) -> List[str]:
    """What's wrong with the rows, if anything (docs/camera-export.md, "Checks")."""
    problems: List[str] = []
    bad = [r.frame for r in rows if not r.ok]
    if bad:
        problems.append(f"no camera object on {len(bad)} frame(s): {frame_ranges(bad)}")
    good = [r for r in rows if r.ok]

    odd = [r.frame for r in good
           if struct.pack(">f", r.values["aspect"]).hex() != ASPECT_BITS or r.values["proj"] != 1
           or (r.values["vp_x0"], r.values["vp_x1"], r.values["vp_y0"], r.values["vp_y1"]) != VIEWPORT
           or not 0 < r.values["near"] < r.values["far"]]
    if odd:
        problems.append(f"unexpected projection settings on {len(odd)} frame(s): {frame_ranges(odd)}")
    rolled = [r.frame for r in good if r.values["u0"] != 0.0 or int(r.values["flags"]) & 1]
    if rolled:
        problems.append(f"the camera has a roll or an up vector on {len(rolled)} frame(s): {frame_ranges(rolled)}")

    # The draw copies the game camera plus the shake into the camera object, and the row is read before the
    # camera's next update. A mismatch means a lag frame (two updates before one draw) or a mistimed read.
    stale = []
    for r in good:
        sx, sy = r.values["shake_x"], r.values["shake_y"]
        eye, t_eye = r.vec("eye"), r.vec("t_eye")
        want_eye = [f32(t_eye[0] + sx), f32(t_eye[1] + sy), t_eye[2]]
        t_interest = r.vec("t_interest")
        want_interest = [f32(t_interest[0] + sx), f32(t_interest[1] + sy), t_interest[2]]
        clamped = stage_id not in LEGAL_STAGES and eye[1] > want_eye[1]
        if (eye[0] != want_eye[0] or (eye[1] != want_eye[1] and not clamped) or eye[2] != want_eye[2]
                or r.vec("interest") != want_interest or r.values["fov"] != r.values["t_fov"]):
            stale.append(r.frame)
    if stale:
        problems.append(f"the drawn camera isn't the game camera plus shake on {len(stale)} frame(s) "
                        f"({frame_ranges(stale)}): a lag frame, or the camera was read at the wrong moment")

    worst_rot = worst_pos = 0.0
    for r in good:
        eye, interest = r.vec("eye"), r.vec("interest")
        mine = look_at(eye, interest, up_hint(eye, interest, r.values["u0"]))
        for k, (a, b) in enumerate(zip(mine, r.view)):
            if k % 4 == 3:
                worst_pos = max(worst_pos, abs(a - b))
            else:
                worst_rot = max(worst_rot, abs(a - b))
    if worst_rot > MATRIX_TOLERANCE[0] or worst_pos > MATRIX_TOLERANCE[1]:
        problems.append(f"the game's view matrix doesn't match its eye, look-at point and roll "
                        f"(rotation off by {worst_rot:.1e}, translation by {worst_pos:.1e})")

    want_mode = FIXED if static_camera else STANDARD
    other = [r.frame for r in rows if r.mode != want_mode]
    if other:
        modes = sorted({r.mode for r in rows if r.mode != want_mode})
        problems.append(f"camera mode {modes} instead of {want_mode} on {len(other)} frame(s): {frame_ranges(other)}")
    return problems


# ------------------------------------------------------------------ the export
def first_shown(first: int) -> int:
    """The label of a render's first video frame. From the match's start the picture for -122 is never
    recorded (docs/clips.md), so that render starts at -121."""
    return first + 1 if first <= slp.FIRST_FRAME + 1 else first


def align(rows: Sequence[Row], first: int, video_frames: int, replay_last: int) -> Tuple[List[Row], List[str]]:
    """The rows for video frames 0, 1, 2...: video frame i shows label first_shown(first) + i.

    A render to the end of a replay that ends on stocks or time has one more video frame than frame numbers:
    the game's last frame, drawn after the replay's last frame request. The game asks for no frame after that
    (FetchGameFrame.asm skips the request once the game has ended), so no row can be read for it, and that
    video frame gets no sample. Any other missing row is a problem.
    """
    start = first_shown(first)
    by_frame = {r.frame: r for r in rows}
    samples: List[Row] = []
    for i in range(video_frames):
        row = by_frame.get(start + i)
        if row is None:
            break
        samples.append(row)
    problems = []
    missing = video_frames - len(samples)
    last_frame_only = missing == 1 and samples and samples[-1].frame == replay_last
    if missing and not last_frame_only:
        problems.append(f"no camera for the last {missing} of {video_frames} video frames "
                        f"(from frame {start + len(samples)})")
    extra = sum(1 for r in rows if r.frame >= start + video_frames)
    if extra:
        problems.append(f"Dolphin wrote the camera for {extra} frame(s) past the video's end; "
                        "the recording may have lost frames")
    return samples, problems


def _sample(row: Row, near_far: Tuple[float, float]) -> dict:
    p = row.plain
    out = {"frame": row.frame, "eye": [p["eye_x"], p["eye_y"], p["eye_z"]],
           "interest": [p["interest_x"], p["interest_y"], p["interest_z"]], "fov": p["fov"], "roll": p["u0"],
           "shake": [p["shake_x"], p["shake_y"]], "mode": row.mode,
           "view": [p[f"m{i}{j}"] for i in range(3) for j in range(4)]}
    if int(p["flags"]) & 1:
        out["roll"], out["up"] = 0.0, [p["u0"], p["u1"], p["u2"]]
    if (p["near"], p["far"]) != near_far:  # only where they differ from the file's projection
        out["near"], out["far"] = p["near"], p["far"]
    return out


def write_export(path: Path, samples: Sequence[Row], *, replay: Path, stage_id: int, stage_name: str,
                 width: int, height: int, scale: int, fps: str, video_frames: int, replay_last: int,
                 transparent: Path, alpha_map: Path, iso: str, codes: Sequence[str]) -> Path:
    p = samples[0].plain
    doc = {
        "format": FORMAT,
        "version": VERSION,
        "replay": Path(replay).name,
        "stage": {"id": stage_id, "name": stage_name},
        "render": {"width": width, "height": height, "scale": scale, "fps": fps,
                   "transparent": Path(transparent).name, "alpha_map": Path(alpha_map).name,
                   "iso": iso, "codes": list(codes)},
        "projection": {"type": "perspective", "fov_axis": "vertical", "aspect": p["aspect"],
                       "viewport": [p["vp_x0"], p["vp_x1"], p["vp_y0"], p["vp_y1"]],
                       "near": p["near"], "far": p["far"]},
        "space": {"units": "replay", "x": "right", "y": "up", "z": "towards the camera"},
        "frames": {"first": samples[0].frame, "last": samples[-1].frame, "count": len(samples),
                   "video": video_frames, "replay_last": replay_last, "replay_frame_offset": -1},
        "shake": "included",
    }
    # One sample per line, so the file stays readable and diffs well.
    head = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))[:-1]
    near_far = (p["near"], p["far"])
    lines = [json.dumps(_sample(r, near_far), separators=(",", ":")) for r in samples]
    Path(path).write_text(head + ',\n"samples":[\n' + ",\n".join(lines) + "\n]}\n", encoding="utf-8")
    return Path(path)


def load(path: Path) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("format") != FORMAT or doc.get("version") != VERSION:
        raise CameraError(f"{path}: not a version {VERSION} camera export")
    if len(doc.get("samples", [])) != doc.get("frames", {}).get("count"):
        raise CameraError(f"{path}: {len(doc.get('samples', []))} samples, but frames.count says "
                          f"{doc.get('frames', {}).get('count')}")
    return doc


def export_path(out_dir: Path, name: str) -> Path:
    return Path(out_dir) / f"camera - {name}.json"


def build(csv_path: Path, out: Path, *, first: int, video_frames: int, replay_last: int, stage_id: int,
          static_camera: bool, **meta) -> Tuple[Optional[Path], List[str]]:
    """Read Dolphin's rows, check them and write the export. Returns (the file or None, problems)."""
    if not Path(csv_path).exists():
        return None, ["Dolphin wrote no camera file"]
    rows = read_csv(csv_path)
    samples, problems = align(rows, first, video_frames, replay_last)
    if not samples:
        return None, problems + ["no camera rows for the video's frames"]
    problems = check_rows(samples, stage_id, static_camera) + problems
    return write_export(out, samples, stage_id=stage_id, video_frames=video_frames, replay_last=replay_last,
                        **meta), problems
