"""Find the tools a render needs: the Dolphin build, the Melee ISO, ffmpeg."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
RESOURCES = REPO_ROOT / "Resources"
PACKAGES = REPO_ROOT / "packages"


class NotFound(RuntimeError):
    pass


def launcher_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Slippi Launcher"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Slippi Launcher"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Slippi Launcher"


def find_dolphin(explicit: Optional[str] = None) -> Path:
    """The frame-dump-capable playback build. The Launcher's own copy can't record on macOS."""
    for given, what in ((explicit, "--dolphin"), (os.environ.get("SLP2ALPHA_DOLPHIN"), "SLP2ALPHA_DOLPHIN")):
        if given:  # an explicit choice must exist: never fall back to a different build
            p = Path(given).expanduser()
            if not p.exists():
                raise NotFound(f"{what}: {p} does not exist")
            return p
    candidates: List[Path] = []
    if sys.platform == "darwin":
        # Prefer the native headless build (tools/dolphin-build/build-mac-mainline.sh).
        candidates.append(PACKAGES / "slippi-playback-mainline" / "Slippi Dolphin.app")
        candidates.append(PACKAGES / "slippi-playback-framedump" / "Slippi Dolphin.app")
    elif os.name == "nt":
        candidates.append(PACKAGES / "slippi-playback-3.5.2" / "Slippi Dolphin.exe")
        candidates.append(launcher_data_dir() / "playback" / "Slippi Dolphin.exe")
    for c in candidates:
        if c.exists():
            return c
    raise NotFound("No frame-dump-capable Slippi playback Dolphin found. On macOS, build it with "
                   "tools/dolphin-build/build-mac-local.sh, or pass --dolphin PATH.")


def launcher_playback_app() -> Optional[Path]:
    p = launcher_data_dir() / "playback" / ("Slippi Dolphin.app" if sys.platform == "darwin" else "Slippi Dolphin.exe")
    return p if p.exists() else None


def find_iso(explicit: Optional[str] = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            raise NotFound(f"ISO not found: {p}")
        return p
    settings = launcher_data_dir() / "Settings"
    try:
        iso = json.loads(settings.read_text(encoding="utf-8"))["settings"]["isoPath"]
    except (OSError, KeyError, ValueError, TypeError):
        raise NotFound("No Melee ISO given and none configured in the Slippi Launcher; pass --iso PATH.")
    p = Path(iso)
    if not p.exists():
        raise NotFound(f"The ISO configured in the Slippi Launcher does not exist: {p}")
    return p


def check_iso(path: Path) -> None:
    """The Gecko codes target NTSC 1.02: game id GALE01, disc revision 2."""
    with open(path, "rb") as f:
        header = f.read(8)
    if header[:6] != b"GALE01":
        raise NotFound(f"{path} is not an NTSC Melee disc (game id {header[:6]!r}); NTSC 1.02 is required.")
    if header[7] != 2:
        raise NotFound(f"{path} is Melee NTSC revision {header[7]}; revision 2 (1.02) is required.")


def find_ffmpeg(explicit: Optional[str] = None, name: str = "ffmpeg") -> str:
    if explicit:
        p = Path(explicit).expanduser()
        if name != "ffmpeg":
            p = p.with_name(name + p.suffix)
        if p.exists():
            return str(p)
    exe = name + (".exe" if os.name == "nt" else "")
    for c in (os.environ.get("ALPHASOLVE_FFMPEG_DIR"), str(PACKAGES / "ffmpeg"),
              str(REPO_ROOT / "packages" / "ffmpeg-6.0-full_build" / "bin")):
        if c and (Path(c) / exe).exists():
            return str(Path(c) / exe)
    found = shutil.which(name)
    if found:
        return found
    for c in ("/opt/homebrew/bin", "/usr/local/bin"):
        if (Path(c) / name).exists():
            return str(Path(c) / name)
    raise NotFound(f"{name} not found; install it (macOS: brew install ffmpeg) or pass --ffmpeg PATH.")


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"
