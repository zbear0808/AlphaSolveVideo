"""Find the tools a render needs: the Dolphin build, the Melee ISO, ffmpeg."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
RESOURCES = REPO_ROOT / "Resources"
PACKAGES = REPO_ROOT / "packages"


class NotFound(RuntimeError):
    pass


def exe(name: str) -> str:
    """A program's file name on this platform: name.exe on Windows."""
    return name + (".exe" if os.name == "nt" else "")


def given_path(*choices: Tuple[Optional[str], str]) -> Optional[Path]:
    """The first (value, label) choice that's set, e.g. (args.blender, "--blender"). An explicit choice must exist:
    never fall back to another program."""
    for given, what in choices:
        if given:
            p = Path(given).expanduser()
            if not p.exists():
                raise NotFound(f"{what}: {p} does not exist")
            return p
    return None


def find_first(choices: Sequence[Tuple[Optional[str], str]], candidates: Iterable, missing: str) -> Path:
    """given_path(*choices), else the first of `candidates` (paths, or None) that exists, else NotFound(missing)."""
    found = given_path(*choices) or next((Path(c) for c in candidates if c and Path(c).exists()), None)
    if found is None:
        raise NotFound(missing)
    return found


def cache_root() -> Path:
    """This repo's cache folder (builds, downloads, test replays): $ALPHASOLVE_CACHE if set, else the platform's
    cache location: ~/Library/Caches on macOS, %LOCALAPPDATA% on Windows, $XDG_CACHE_HOME or ~/.cache elsewhere."""
    if os.environ.get("ALPHASOLVE_CACHE"):
        return Path(os.environ["ALPHASOLVE_CACHE"]).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "AlphaSolveVideo"


def mainline_package() -> Path:
    """Where the build scripts put the headless mainline build."""
    name = "Slippi Dolphin.app" if sys.platform == "darwin" else exe("dolphin-emu-nogui")
    return PACKAGES / "slippi-playback-mainline" / name


def build_hint() -> str:
    """How to get the headless mainline build on this platform."""
    if sys.platform == "darwin":
        return "build it with tools/dolphin-build/build-mac-mainline.sh"
    if os.name == "nt":
        return ("build it with tools\\dolphin-build\\build-windows-mainline.py, or unpack the zip from the "
                "\"Windows playback Dolphin\" GitHub Actions workflow into packages\\slippi-playback-mainline")
    if sys.platform.startswith("linux"):
        return ("build it with tools/dolphin-build/build-linux-mainline.py (or in Docker, with "
                "tools/dolphin-build/linux.Dockerfile), or unpack the tarball from the \"Linux playback Dolphin\" "
                "GitHub Actions workflow into packages/")
    return "there is no build script for this platform yet (docs/plan-linux.md has the Linux one)"


def utf8_child_env() -> dict:
    """The environment for running slp2alpha (or another Python script) whose output is read and decoded as
    UTF-8. On Windows a child Python writes to a pipe in the locale's code page unless told otherwise."""
    return dict(os.environ, PYTHONIOENCODING="utf-8")


def launcher_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Slippi Launcher"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Slippi Launcher"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Slippi Launcher"


def find_dolphin(explicit: Optional[str] = None) -> Path:
    """The frame-dump-capable playback build. The Launcher's own copy can't record on macOS."""
    candidates: List[Path] = []
    if sys.platform == "darwin":
        # Prefer the native headless build (tools/dolphin-build/build-mac-mainline.sh).
        candidates.append(mainline_package())
        candidates.append(PACKAGES / "slippi-playback-framedump" / "Slippi Dolphin.app")
    elif os.name == "nt":
        # The headless build first (tools/dolphin-build/build-windows-mainline.py), then Ishiiruka (a window).
        candidates.append(mainline_package())
        candidates.append(PACKAGES / "slippi-playback-3.5.2" / "Slippi Dolphin.exe")
        candidates.append(launcher_data_dir() / "playback" / "Slippi Dolphin.exe")
    else:
        # The headless build (tools/dolphin-build/build-linux-mainline.py). The Launcher's AppImage can't record.
        candidates.append(mainline_package())
    return find_first(((explicit, "--dolphin"), (os.environ.get("SLP2ALPHA_DOLPHIN"), "SLP2ALPHA_DOLPHIN")),
                      candidates,
                      f"No frame-dump-capable Slippi playback Dolphin found: {build_hint()}, or pass --dolphin PATH.")


def launcher_playback_app() -> Optional[Path]:
    p = launcher_data_dir() / "playback" / ("Slippi Dolphin.app" if sys.platform == "darwin" else "Slippi Dolphin.exe")
    return p if p.exists() else None


def find_iso(explicit: Optional[str] = None) -> Path:
    """--iso, else $SLP2ALPHA_ISO (which tools that run slp2alpha set for it), else the Slippi Launcher's setting."""
    given = given_path((explicit, "--iso"), (os.environ.get("SLP2ALPHA_ISO"), "SLP2ALPHA_ISO"))
    if given:
        return given
    settings = launcher_data_dir() / "Settings"
    try:
        iso = json.loads(settings.read_text(encoding="utf-8"))["settings"]["isoPath"]
    except (OSError, KeyError, ValueError, TypeError):
        raise NotFound("No Melee ISO given and none configured in the Slippi Launcher; pass --iso PATH "
                       "(or set SLP2ALPHA_ISO).")
    p = Path(iso)
    if not p.exists():
        raise NotFound(f"The ISO configured in the Slippi Launcher does not exist: {p}")
    return p


def animelee_iso_path() -> Path:
    """Where tools/animelee/build_iso.py writes the Animelee ISO."""
    return cache_root() / "animelee" / "ANIMELEE - COMPLETE EDITION.iso"


def find_animelee_iso() -> Path:
    p = animelee_iso_path()
    if not p.exists():
        raise NotFound(f"No Animelee ISO at {p}. Build it with tools/animelee/build_iso.py.")
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
    for c in (os.environ.get("ALPHASOLVE_FFMPEG_DIR"), str(PACKAGES / "ffmpeg"),
              str(REPO_ROOT / "packages" / "ffmpeg-6.0-full_build" / "bin")):
        if c and (Path(c) / exe(name)).exists():
            return str(Path(c) / exe(name))
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "darwin":
        for c in ("/opt/homebrew/bin", "/usr/local/bin"):
            if (Path(c) / name).exists():
                return str(Path(c) / name)
    raise NotFound(f"{name} not found; install it (macOS: brew install ffmpeg; Windows: winget install Gyan.FFmpeg, "
                   "or unpack an FFmpeg build's bin folder into packages/ffmpeg; Linux: your distribution's ffmpeg, "
                   "or a static build's bin folder in ALPHASOLVE_FFMPEG_DIR) or pass --ffmpeg PATH.")


BLENDER_APP = Path("/Applications/Blender.app/Contents/MacOS/Blender")


def _windows_blenders() -> list:
    """Blender's Windows installs (C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe, newest first,
    then Steam's)."""
    if os.name != "nt":
        return []
    root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    found = [p for p in root.glob("Blender*/blender.exe") if p.is_file()]

    def version(p: Path):
        digits = p.parent.name.replace("Blender", "").strip().split(".")
        return [int(d) if d.isdigit() else 0 for d in digits]

    steam = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam" / "steamapps" / "common"
    return [str(p) for p in sorted(found, key=version, reverse=True)] + [str(steam / "Blender" / "blender.exe")]


def _unix_blenders() -> list:
    """Where Blender goes on macOS and Linux besides the PATH: an app in your own Applications folder, an unpacked
    download linked from ~/.local/bin (which a plain SSH command doesn't put on the PATH), a snap."""
    if os.name == "nt":
        return []
    return [str(Path.home() / "Applications" / "Blender.app" / "Contents" / "MacOS" / "Blender"),
            str(Path.home() / ".local" / "bin" / "blender"), "/snap/bin/blender"]


def find_blender(explicit: Optional[str] = None) -> str:
    """Blender: as given, $BLENDER, /Applications, Program Files or Steam, the PATH, ~/Applications, ~/.local/bin,
    /snap/bin."""
    return str(find_first(((explicit, "--blender"), (os.environ.get("BLENDER"), "BLENDER")),
                          (BLENDER_APP, *_windows_blenders(), shutil.which("blender"), *_unix_blenders()),
                          "Blender not found: install it, or pass --blender PATH / set BLENDER"))


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"
