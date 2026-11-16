"""Shared helpers for the Shy Guy probes.

Puts the repo's slp2alpha package on the path, finds the test replay, reads item and fighter events from a
.slp file, and runs the headless Dolphin build for one variant (Gecko codes, graphics settings, custom
textures). Everything is written to a work folder outside the repo.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "slp2alpha"))
from slp2alpha import config, gecko, locate, runner, validate  # noqa: E402

# Yoshi's Story with Shy Guys: a public replay from Slippi Lab, listed in tools/render-tests/replays.json.
DEFAULT_REPLAY = "RichAuthenticGull.slp"

SHY_GUY_ITEM = 0xD2  # Slippi item type id 210
SHY_GUY_HIDE_CODE = "Hide Shy Guys (Yoshi's Story)"  # Resources/Characters Only Codes.txt

# The textures a Shy Guy is drawn with (Yoshi's Story, NTSC 1.02): Dolphin's custom-texture names and their
# sizes. RGB5A3 (format 5); the three are the frames of a flip-book. The names are xxHash64 of the texture
# bytes in GrSt.dat, so they are the same on every machine: `textures.py iso` re-derives them from your ISO.
SHY_GUY_TEXTURES: Tuple[Tuple[str, int, int], ...] = (
    ("tex1_76x72_7f157caad3c96c68_5", 76, 72),
    ("tex1_76x72_d55c2685f515d087_5", 76, 72),
    ("tex1_76x73_49a3777afd3829a5_5", 76, 73),
)

# Replay (x, y) of an item -> pixel (u, v) = (U0 * x + U1, V0 * y + V1) in a Yoshi's Story render with
# --static-camera at --scale 1 (640x528), as fitted by calibrate.py. Other scales are assumed to multiply it
# (only used to pick demo frames; not checked).
YS_STATIC_FIT = (3.0757, 313.16, -3.0813, 378.81)


def cli(main: Callable[[], int]) -> None:
    try:
        sys.exit(main())
    except (locate.NotFound, KeyError, RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


def need_imaging() -> None:
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        raise RuntimeError("this needs numpy and Pillow: pip install numpy pillow") from None


# ---- replays -------------------------------------------------------------------------------------------

def find_replay(given: Optional[str]) -> Path:
    """The --replay file, or the Shy Guy test replay (downloaded to the cache tools/render-tests uses)."""
    if given:
        path = Path(given).expanduser()
        if not path.exists():
            raise locate.NotFound(f"replay not found: {path}")
        return path
    spec = importlib.util.spec_from_file_location("render_tests_run", REPO / "tools" / "render-tests" / "run.py")
    render_tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_tests)
    manifest = json.loads((REPO / "tools" / "render-tests" / "replays.json").read_text())
    return render_tests.fetch(manifest["source"], DEFAULT_REPLAY)


def slp_events(replay: Path) -> Iterator[Tuple[int, bytes]]:
    """(command byte, payload) of every event in a replay's raw stream."""
    data = replay.read_bytes()
    header = b"{U\x03raw[$U#l"
    if not data.startswith(header):
        raise ValueError(f"{replay.name}: not a Slippi replay")
    start = len(header) + 4
    length = struct.unpack(">I", data[len(header):start])[0]
    if length == 0:  # still being written: the stream runs to the metadata or the end
        end = data.find(b"U\x08metadata", start)
        length = (end if end != -1 else len(data)) - start
    raw = data[start:start + length]
    sizes = {0x35: raw[1]}
    for i in range(2, 1 + raw[1], 3):
        sizes[raw[i]] = struct.unpack(">H", raw[i + 1:i + 3])[0]
    pos = 0
    while pos < len(raw):
        size = sizes[raw[pos]]
        if pos + 1 + size > len(raw):
            break
        yield raw[pos], raw[pos + 1:pos + 1 + size]
        pos += 1 + size


@dataclass(frozen=True)
class ItemRecord:
    """One Item Update event: an item (or projectile) on one frame."""
    frame: int
    type_id: int
    state: int
    facing: float
    x_velocity: float
    y_velocity: float
    x: float
    y: float
    damage: int
    timer: float
    spawn_id: int


def item_records(replay: Path, type_id: Optional[int] = None) -> Iterator[ItemRecord]:
    for cmd, p in slp_events(replay):
        if cmd != 0x3B or len(p) < 37:
            continue
        frame, kind, state = struct.unpack(">iHB", p[:7])
        if type_id is not None and kind != type_id:
            continue
        facing, x_vel, y_vel, x, y = struct.unpack(">5f", p[7:27])
        damage = struct.unpack(">H", p[27:29])[0]
        timer = struct.unpack(">f", p[29:33])[0]
        spawn_id = struct.unpack(">I", p[33:37])[0]
        yield ItemRecord(frame, kind, state, facing, x_vel, y_vel, x, y, damage, timer, spawn_id)


def shy_guys_by_frame(replay: Path) -> Dict[int, List[ItemRecord]]:
    out: Dict[int, List[ItemRecord]] = {}
    for rec in item_records(replay, SHY_GUY_ITEM):
        out.setdefault(rec.frame, []).append(rec)
    return out


@dataclass(frozen=True)
class FighterPos:
    x: float
    y: float
    airborne: bool


def fighter_positions(replay: Path) -> Dict[int, Dict[int, FighterPos]]:
    """frame -> port -> position, from the post-frame events (Nana and other followers are left out)."""
    out: Dict[int, Dict[int, FighterPos]] = {}
    for cmd, p in slp_events(replay):
        if cmd != 0x38 or len(p) <= 0x2E or p[5]:
            continue
        frame = struct.unpack(">i", p[:4])[0]
        x, y = struct.unpack(">ff", p[9:17])
        out.setdefault(frame, {})[p[4]] = FighterPos(x, y, bool(p[0x2E]))
    return out


# ---- Dolphin -------------------------------------------------------------------------------------------

@dataclass
class Tools:
    dolphin: Path
    engine: str
    iso: Path
    ffmpeg: str
    ffprobe: str
    codes: Dict[str, "gecko.GeckoCode"]


def add_tool_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--replay", help="replay to play (default: the Shy Guy test replay from tools/render-tests)")
    ap.add_argument("--out", help="work folder (default: a new temporary folder)")
    ap.add_argument("--keep-videos", action="store_true", help="keep the raw recordings (30-40 MB per 1000 frames)")
    ap.add_argument("--dolphin", help="headless mainline playback build (default: packages/)")
    ap.add_argument("--iso", help="Melee NTSC 1.02 ISO (default: the one set in the Slippi Launcher)")
    ap.add_argument("--ffmpeg", help="ffmpeg executable (ffprobe is expected next to it)")


def find_tools(args: argparse.Namespace) -> Tools:
    dolphin = locate.find_dolphin(args.dolphin)
    engine = runner.engine_of(dolphin)
    if engine != config.MAINLINE:
        # The flicker codes would flash a window; custom texture names are also specific to the mainline build.
        raise locate.NotFound(f"{dolphin} is not the headless mainline build "
                              "(tools/dolphin-build/build-mac-mainline.sh)")
    iso = locate.find_iso(args.iso)
    locate.check_iso(iso)
    codes = gecko.load_codes(*(locate.RESOURCES / f for f in config.CODE_FILES))
    return Tools(dolphin, engine, iso, locate.find_ffmpeg(args.ffmpeg),
                 locate.find_ffmpeg(args.ffmpeg, name="ffprobe"), codes)


def work_dir(args: argparse.Namespace, name: str) -> Path:
    path = Path(args.out).expanduser() if args.out else Path(tempfile.mkdtemp(prefix=f"shyguy-{name}-"))
    path.mkdir(parents=True, exist_ok=True)
    print(f"work folder: {path}")
    return path


@dataclass
class Run:
    folder: Path
    user: Path
    frames: Tuple[Optional[int], Optional[int]]

    @property
    def recordings(self) -> List[Path]:
        return sorted((self.user / "Dump" / "Frames").glob("*.mkv"))

    @property
    def video(self) -> Path:
        if not self.recordings:
            raise RuntimeError(f"{self.folder.name}: Dolphin wrote no recording")
        return self.recordings[0]

    def dumped_textures(self) -> Dict[str, Path]:
        """Textures Dolphin dumped (needs DumpTextures = True), by Dolphin's name."""
        folder = self.user / "Dump" / "Textures" / "GALE01"
        return {p.stem: p for p in sorted(folder.glob("*.png"))} if folder.exists() else {}

    def discard_recordings(self) -> None:
        shutil.rmtree(self.user / "Dump" / "Frames", ignore_errors=True)


def run_variant(tools: Tools, replay: Path, work: Path, label: str, enabled: Sequence[str], start: int, end: int, *,
                scale: int = 1, record: bool = True, gfx: Sequence[str] = (),
                textures: Optional[Path] = None) -> Run:
    """Play replay frames start..end in the headless build with these Gecko codes enabled.

    gfx: extra lines for GFX.ini's [Settings] (e.g. "HiresTextures = True"). textures: a folder of PNGs
    that becomes Load/Textures/GALE01 (Dolphin's custom textures, named tex1_WxH_HASH_FORMAT.png).
    """
    folder = work / label
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    user, logs = folder / "user", folder / "logs"
    dump = config.dump_dir_for(tools.engine, user, folder / "dump")
    config.write_user_dir(user, tools.codes, enabled=enabled, scale=scale, engine=tools.engine, record=record)
    if gfx:
        ini = user / "Config" / "GFX.ini"
        text = ini.read_text()
        assert "[Settings]\n" in text, "GFX.ini has no [Settings] section"
        ini.write_text(text.replace("[Settings]\n", "[Settings]\n" + "".join(f"{line}\n" for line in gfx), 1))
    if textures:
        target = user / "Load" / "Textures" / "GALE01"
        target.mkdir(parents=True)
        for png in sorted(Path(textures).glob("*.png")):
            shutil.copy(png, target / png.name)
    comm = folder / "comm.json"
    config.write_comm(comm, replay, start_frame=start, end_frame=end + 1)  # records strictly between the two
    t0 = time.monotonic()
    res = runner.run_dolphin(tools.dolphin, tools.iso, comm, user, dump, logs, stop_at_frame=end, boot_timeout=180,
                             grace_seconds=1.0)
    print(f"  [{label}] {res.reason}: frames {res.first_frame}..{res.last_frame} in {time.monotonic() - t0:.0f} s",
          flush=True)
    if res.reason != "finished":
        raise RuntimeError(f"{label}: Dolphin did not finish ({res.reason}); logs in {logs}")
    return Run(folder, user, (res.first_frame, res.last_frame))


# ---- recordings ----------------------------------------------------------------------------------------

def iter_frames(tools: Tools, video: Path) -> Iterator["np.ndarray"]:
    """Every frame of a recording as a (height, width, 3) uint8 array, decoded one at a time."""
    import numpy as np

    info = validate.probe(tools.ffprobe, str(video))
    size = info.width * info.height * 3
    proc = subprocess.Popen([tools.ffmpeg, "-nostdin", "-v", "error", "-i", str(video), "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(info.height, info.width, 3)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def blobs(mask: "np.ndarray", min_area: int = 150) -> List[dict]:
    """Connected regions of a boolean mask: centroid, area, bounding box and whether it touches the edge."""
    import numpy as np

    height, width = mask.shape
    ys, xs = np.nonzero(mask)
    pending = set(zip(ys.tolist(), xs.tolist()))
    found = []
    while pending:
        stack = [pending.pop()]
        points = list(stack)
        while stack:
            y, x = stack.pop()
            for n in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if n in pending:
                    pending.remove(n)
                    stack.append(n)
                    points.append(n)
        if len(points) >= min_area:
            py, px = zip(*points)
            box = (min(px), max(px), min(py), max(py))
            found.append({"u": float(np.mean(px)), "v": float(np.mean(py)), "area": len(points), "box": box,
                          "edge": box[0] == 0 or box[1] == width - 1 or box[2] == 0 or box[3] == height - 1})
    return sorted(found, key=lambda b: b["u"])


def in_view(u: float, v: float, width: int, height: int, margin: int = 30) -> bool:
    return margin < u < width - margin and margin < v < height - margin
