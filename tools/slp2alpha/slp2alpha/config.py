"""Generate an isolated Dolphin user folder and the Slippi playback "comm" file for one render."""

from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .gecko import GeckoCode, gecko_section

# Two playback builds are supported:
#   ishiiruka: Slippi's Ishiiruka v3.5.2 (the build the Launcher installs; x86_64 on macOS).
#   mainline:  Slippi's mainline-based playback branch, headless NoGUI (native arm64 on Apple Silicon).
ISHIIRUKA = "ishiiruka"
MAINLINE = "mainline"

# EFBScale values in Ishiiruka's VideoConfig.h: 2 = 1x (native), 3 = 1.5x, 4 = 2x, 6 = 3x, 7 = 4x.
EFB_SCALE_FOR = {1: 2, 2: 4, 3: 6, 4: 7}
ASPECT_73_60 = 5
# Mainline: AspectMode::ForceMelee and FrameDumpResolutionType::XFBAspectRatioCorrectedResolution.
MAINLINE_ASPECT_MELEE = 3
MAINLINE_DUMP_XFB_ASPECT_CORRECTED = 1

FLICKER_CODE = "(EPILEPSY WARNING) Flicker Background Black/White asm v5"


def _ini(sections: "OrderedDict[str, Dict[str, str]]") -> str:
    out: List[str] = []
    for section, values in sections.items():
        out.append(f"[{section}]")
        out.extend(f"{key} = {value}" for key, value in values.items())
    return "\n".join(out) + "\n"


def _ishiiruka_inis(scale: int, record: bool, cpu_core: Optional[int], fastmem: Optional[bool],
                    video_backend: Optional[str]) -> Tuple[OrderedDict, OrderedDict, List[str]]:
    core = OrderedDict()
    if cpu_core is not None:
        core["CPUCore"] = str(cpu_core)  # only needed where the JIT can't run (Docker on Apple Silicon)
    if fastmem is not None:
        core["Fastmem"] = str(fastmem)
    if video_backend:
        core["GFXBackend"] = video_backend
    core.update([
        ("SlippiEnableSpectator", "False"),  # no listening socket: no port clashes, no firewall prompt
        ("SlippiJukeboxEnabled", "False"),
        ("EmulationSpeed", "0"),             # unthrottled
        ("AdapterRumble0", "False"),
        ("AdapterRumble1", "False"),
        ("AdapterRumble2", "False"),
        ("AdapterRumble3", "False"),
    ])
    dolphin = OrderedDict([
        ("Core", core),
        ("Movie", OrderedDict([("DumpFrames", str(record)), ("DumpFramesSilent", "True")])),
        ("DSP", OrderedDict([("Backend", "No audio output"), ("DumpAudio", "False")])),
        ("Display", OrderedDict([("Fullscreen", "False"), ("RenderToMain", "True"),
                                 ("RenderWindowAutoSize", "True")])),
        ("Interface", OrderedDict([("ConfirmStop", "False"), ("UsePanicHandlers", "False"),
                                   ("ShowLogWindow", "False"), ("PauseOnFocusLost", "False")])),
        ("Analytics", OrderedDict([("Enabled", "False"), ("PermissionAsked", "True")])),
    ])
    gfx = OrderedDict([
        ("Settings", OrderedDict([
            ("UseFFV1", "True"),
            ("InternalResolutionFrameDumps", "True"),  # record from the offscreen buffer, not the window
            ("AspectRatio", str(ASPECT_73_60)),
            ("EFBScale", str(EFB_SCALE_FOR[scale])),
            ("ShowFPS", "False"),
        ])),
        ("Hardware", OrderedDict([("VSync", "False")])),
    ])
    log_names = ("ActionReplay Audio AudioInterface Boot CommandProcessor Common Console Core DSPHLE DVD "
                 "DynaRec EXI GPFifo HostGPU Memory OSHLE OSReport PixelEngine PowerPC Slippi SlippiOnline "
                 "Video VideoInterface MASTER").split()
    return dolphin, gfx, log_names


def _mainline_inis(scale: int, record: bool, cpu_core: Optional[int], fastmem: Optional[bool],
                   video_backend: Optional[str]) -> Tuple[OrderedDict, OrderedDict, List[str]]:
    core = OrderedDict([
        ("GFXBackend", video_backend or "Metal"),
        ("EmulationSpeed", "0"),  # unthrottled
        ("EnableCheats", "True"),
    ])
    if cpu_core is not None:
        core["CPUCore"] = str(cpu_core)
    if fastmem is not None:
        core["Fastmem"] = str(fastmem)
    dolphin = OrderedDict([
        ("Core", core),
        ("Slippi", OrderedDict([("EnableSpectator", "False"), ("EnableJukebox", "False"),
                                ("SaveReplays", "False")])),
        ("Movie", OrderedDict([("DumpFrames", str(record)), ("DumpFramesSilent", "True")])),
        ("DSP", OrderedDict([("Backend", "No Audio Output"), ("DumpAudio", "False")])),
        ("Interface", OrderedDict([("ConfirmStop", "False"), ("UsePanicHandlers", "False"),
                                   ("OnScreenDisplayMessages", "False")])),
        ("Analytics", OrderedDict([("Enabled", "False"), ("PermissionAsked", "True")])),
    ])
    gfx = OrderedDict([
        ("Settings", OrderedDict([
            ("InternalResolution", str(scale)),
            ("AspectRatio", str(MAINLINE_ASPECT_MELEE)),
            ("FrameDumpsResolutionType", str(MAINLINE_DUMP_XFB_ASPECT_CORRECTED)),
            ("DumpFormat", "mkv"),   # FFV1 in Matroska; readable while it is still being written
            ("DumpCodec", "ffv1"),
            ("ShowFPS", "False"),
        ])),
        # Present at each VI field (not on XFB copy), so every frame lands on the exact 1/60 s grid.
        ("Hacks", OrderedDict([("ImmediateXFBEnable", "False")])),
        ("Hardware", OrderedDict([("VSync", "False")])),
    ])
    log_names = "ActionReplay BOOT CORE EXI FRAMEDUMP OSREPORT SLIPPI SLIPPI_ONLINE Video".split()
    return dolphin, gfx, log_names


def write_user_dir(
    user_dir: Path,
    codes: Dict[str, GeckoCode],
    enabled: Iterable[str],
    disabled: Iterable[str] = ("Optional: Show Player Names",),
    scale: int = 1,
    record: bool = True,
    cpu_core: Optional[int] = None,
    fastmem: Optional[bool] = None,
    video_backend: Optional[str] = None,
    debug_logging: bool = False,
    engine: str = ISHIIRUKA,
    cpu_thread: Optional[bool] = None,
) -> None:
    """Write Config/Dolphin.ini, Config/GFX.ini and GameSettings/GALE01.ini under user_dir.

    cpu_thread overrides the playback codes' "CPUThread = False" (single core) for this game.
    """
    user_dir = Path(user_dir)
    (user_dir / "Config").mkdir(parents=True, exist_ok=True)
    (user_dir / "GameSettings").mkdir(parents=True, exist_ok=True)

    make = _mainline_inis if engine == MAINLINE else _ishiiruka_inis
    dolphin, gfx, log_names = make(scale, record, cpu_core, fastmem, video_backend)
    (user_dir / "Config" / "Dolphin.ini").write_text(_ini(dolphin), encoding="utf-8")
    (user_dir / "Config" / "GFX.ini").write_text(_ini(gfx), encoding="utf-8")

    if debug_logging:
        logger = OrderedDict([
            ("Options", OrderedDict([("Verbosity", "4"), ("WriteToFile", "True"), ("WriteToConsole", "False"),
                                     ("WriteToWindow", "False")])),
            ("Logs", OrderedDict((name, "True") for name in log_names)),
        ])
        (user_dir / "Config" / "Logger.ini").write_text(_ini(logger), encoding="utf-8")

    enabled = list(enabled)
    missing = [name for name in enabled if name not in codes and not name.startswith("Optional:")]
    if missing:
        raise KeyError(f"unknown Gecko code(s): {missing}")
    game_ini = []
    if cpu_thread is not None:
        game_ini += ["[Core]", f"CPUThread = {cpu_thread}"]
    game_ini += ["[Gecko]", gecko_section(codes).rstrip("\n"), "[Gecko_Enabled]"]
    game_ini += [f"${name}" for name in enabled]
    game_ini += ["[Gecko_Disabled]"] + [f"${name}" for name in disabled]
    (user_dir / "GameSettings" / "GALE01.ini").write_text("\n".join(game_ini) + "\n", encoding="utf-8")


def dump_dir_for(engine: str, user_dir: Path, requested: Path) -> Path:
    """Where the build writes its frame dumps: Ishiiruka takes --output-directory, mainline uses the user folder."""
    return Path(user_dir) / "Dump" / "Frames" if engine == MAINLINE else Path(requested)


def write_comm(path: Path, replay: Path, start_frame: int = -123, end_frame: Optional[int] = None) -> dict:
    """Slippi playback "comm" file. Dolphin records frames strictly between startFrame and endFrame."""
    comm = {
        "mode": "normal",
        "replay": str(Path(replay).resolve()),
        "startFrame": start_frame,
        "isRealTimeMode": False,
        "shouldResync": True,
        "rollbackDisplayMethod": "off",
        "commandId": str(uuid.uuid4()),
    }
    if end_frame is not None:
        comm["endFrame"] = end_frame
    Path(path).write_text(json.dumps(comm, indent=2), encoding="utf-8")
    return comm
