"""Launch Slippi's playback Dolphin, follow its --cout progress markers and stop it at the end."""

from __future__ import annotations

import functools
import os
import plistlib
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional

from . import config

_MARKER = re.compile(r"^\[([A-Z_]+)\](?:\s+(-?\d+|.+))?\s*$")
_HELP_OPTION = re.compile(r"(?<![\w-])(--[a-z][a-z0-9_-]*)")
MAINLINE_EXECUTABLE = "dolphin-emu-nogui"


@dataclass
class RunResult:
    returncode: Optional[int]
    reason: str
    """Why the run ended: "finished", "timeout-boot", "stalled", "exited", "time-limit"."""
    markers: Dict[str, str] = field(default_factory=dict)
    first_frame: Optional[int] = None
    last_frame: Optional[int] = None
    started_at: float = 0.0
    first_frame_at: Optional[float] = None
    last_frame_at: Optional[float] = None
    ended_at: float = 0.0
    stdout_path: Optional[Path] = None
    stderr_path: Optional[Path] = None
    frame_times: List[float] = field(default_factory=list)

    @property
    def boot_seconds(self) -> Optional[float]:
        return None if self.first_frame_at is None else self.first_frame_at - self.started_at

    @property
    def frames_played(self) -> int:
        if self.first_frame is None or self.last_frame is None:
            return 0
        return self.last_frame - self.first_frame

    @property
    def game_fps(self) -> Optional[float]:
        if not self.frames_played or self.first_frame_at is None or self.last_frame_at is None:
            return None
        span = self.last_frame_at - self.first_frame_at
        return self.frames_played / span if span > 0 else None


def dolphin_executable(app_or_exe: Path) -> Path:
    """Accept either a macOS .app bundle or the executable itself."""
    p = Path(app_or_exe)
    if p.suffix == ".app":
        name = "Slippi Dolphin"
        try:
            with open(p / "Contents" / "Info.plist", "rb") as f:
                name = plistlib.load(f).get("CFBundleExecutable", name)
        except (OSError, plistlib.InvalidFileException):
            pass
        return p / "Contents" / "MacOS" / name
    return p


def engine_of(app_or_exe: Path) -> str:
    """Which playback build this is: the headless mainline build or Ishiiruka."""
    name = dolphin_executable(app_or_exe).name.lower()
    return config.MAINLINE if name.startswith(MAINLINE_EXECUTABLE) else config.ISHIIRUKA


@functools.lru_cache(maxsize=None)
def _help_options(exe: str, mtime: float) -> FrozenSet[str]:
    try:
        out = subprocess.run([exe, "--help"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    return frozenset(_HELP_OPTION.findall(out.stdout + out.stderr))


def dolphin_options(app_or_exe: Path) -> FrozenSet[str]:
    """The long options a Dolphin build lists in --help, e.g. "--camera-out" on builds with that patch."""
    exe = dolphin_executable(app_or_exe)
    try:
        mtime = exe.stat().st_mtime
    except OSError:
        return frozenset()
    return _help_options(str(exe), mtime)


def dolphin_args(engine: str, exe: Path, iso: Path, comm_file: Path, user_dir: Path, dump_dir: Path) -> List[str]:
    args = [str(exe), "-e", str(iso), "-i", str(comm_file), "-u", str(user_dir), "--cout", "--hide-seekbar"]
    if engine == config.MAINLINE:
        return args + ["-p", "headless"]  # no window; dumps go to <user>/Dump/Frames; exits when emulation stops
    return args + ["-b", "--output-directory", str(dump_dir)]


def run_dolphin(
    dolphin: Path,
    iso: Path,
    comm_file: Path,
    user_dir: Path,
    dump_dir: Path,
    log_dir: Path,
    stop_at_frame: Optional[int] = None,
    max_seconds: Optional[float] = None,
    boot_timeout: float = 120.0,
    stall_timeout: float = 45.0,
    grace_seconds: float = 1.5,
    extra_env: Optional[Dict[str, str]] = None,
    extra_args: Optional[List[str]] = None,
    on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
    on_start: Optional[Callable[[subprocess.Popen], None]] = None,
) -> RunResult:
    """Run one replay. Stops once [CURRENT_FRAME] reaches stop_at_frame (default: [GAME_END_FRAME]),
    or when the build reports [PLAYBACK_TERMINATED] (the mainline build does at the replay's end)."""
    exe = dolphin_executable(dolphin)
    for d in (dump_dir, log_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    args = dolphin_args(engine_of(dolphin), exe, iso, comm_file, user_dir, dump_dir)
    args += list(extra_args or [])
    env = dict(os.environ)
    env.update(extra_env or {})

    stdout_path = Path(log_dir) / "dolphin.stdout"
    stderr_path = Path(log_dir) / "dolphin.stderr"
    result = RunResult(returncode=None, reason="", stdout_path=stdout_path, stderr_path=stderr_path)
    lock = threading.Lock()
    state = {"current": None, "game_end": None, "terminated": False, "last_change": time.monotonic()}

    result.started_at = time.monotonic()
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, start_new_session=True)
    if on_start:
        on_start(proc)

    def read_stdout():
        with open(stdout_path, "wb") as out:
            for raw in iter(proc.stdout.readline, b""):
                out.write(raw)
                line = raw.decode("utf-8", "replace").strip()
                m = _MARKER.match(line)
                if not m:
                    continue
                key, value = m.group(1), (m.group(2) or "")
                now = time.monotonic()
                with lock:
                    if key == "CURRENT_FRAME":
                        frame = int(value)
                        if result.first_frame is None:
                            result.first_frame, result.first_frame_at = frame, now
                        result.last_frame, result.last_frame_at = frame, now
                        result.frame_times.append(now)
                        state["current"] = frame
                        state["last_change"] = now
                    else:
                        result.markers[key] = value
                        if key == "GAME_END_FRAME":
                            state["game_end"] = int(value)
                        elif key == "PLAYBACK_TERMINATED":
                            state["terminated"] = True

    def drain_stderr():
        with open(stderr_path, "wb") as err:
            for raw in iter(proc.stderr.readline, b""):
                err.write(raw)

    readers = [threading.Thread(target=read_stdout, daemon=True), threading.Thread(target=drain_stderr, daemon=True)]
    for t in readers:
        t.start()

    reported = None
    try:
        while True:
            if proc.poll() is not None:
                result.reason = "exited"
                break
            time.sleep(0.25)
            now = time.monotonic()
            with lock:
                current, game_end, last_change = state["current"], state["game_end"], state["last_change"]
                terminated = state["terminated"]
            target = stop_at_frame if stop_at_frame is not None else game_end
            if on_progress and current is not None and current != reported:
                reported = current
                on_progress(current, target)
            if terminated:
                result.reason = "finished"
                time.sleep(0.5)  # nothing more is recorded after this; just let the last frame flush
                break
            if current is None:
                if now - result.started_at > boot_timeout:
                    result.reason = "timeout-boot"
                    break
            else:
                if target is not None and current >= target:
                    result.reason = "finished"
                    time.sleep(grace_seconds)
                    break
                if now - last_change > stall_timeout:
                    result.reason = "stalled"
                    break
            if max_seconds is not None and now - result.started_at > max_seconds:
                result.reason = "time-limit"
                break
    finally:
        result.ended_at = time.monotonic()
        result.returncode = _stop(proc)
        for t in readers:
            t.join(timeout=5)
    return result


def _stop(proc: subprocess.Popen, term_wait: float = 20.0) -> Optional[int]:
    if proc.poll() is not None:
        return proc.returncode
    for sig, wait in ((signal.SIGTERM, term_wait), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            break
        try:
            return proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            continue
    return proc.poll()
