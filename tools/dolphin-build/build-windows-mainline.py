#!/usr/bin/env python3
"""Windows build of Slippi's mainline playback Dolphin: headless (NoGUI), with frame dumping and this repo's
patches. The Windows counterpart of build-mac-mainline.sh; docs/plan-windows-mainline.md has the reasoning.

    python tools\\dolphin-build\\build-windows-mainline.py [fetch|configure|build|bundle|all]   (default: all)

Needs Git, Python 3.9 or newer, Rust (rustup), and Visual Studio 2022 or its Build Tools with the "Desktop
development with C++" workload. Any shell works: the script loads the x64 compiler environment (vcvars64.bat)
itself unless cl.exe is already on the PATH. CMake 3.31 and Ninja come from pip, into a venv in the work folder.

The result goes to packages\\slippi-playback-mainline\\ (dolphin-emu-nogui.exe, its DLLs and Sys\\), where
slp2alpha looks for it. The GitHub Actions workflow .github/workflows/dolphin-windows.yml runs this script.

Environment:
  ALPHASOLVE_CACHE   work folder (default %LOCALAPPDATA%\\AlphaSolveVideo). A short one such as C:\\asv keeps the
                     Rust build's paths under Windows' 260-character limit.
  OUTPUT_DIR         where the package goes (default <repo>\\packages\\slippi-playback-mainline)
  JOBS               build parallelism (default: all cores)
"""

from __future__ import annotations

import datetime
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "slp2alpha"))
from slp2alpha import locate  # noqa: E402

COMMIT = "c5f635948ed43f4d14a72069343e0cecdc117391"  # fix/mainline-playback, 2026-06-15, as build-mac-mainline.sh
DOLPHIN_GIT = "https://github.com/project-slippi/dolphin.git"
RUST = "1.88.0"  # Externals/SlippiRustExtensions/rust-toolchain.toml
# Dolphin's own Windows FFmpeg (the Externals/FFmpeg-bin submodule) can't write Matroska, which slp2alpha records
# in. This is FFmpeg 8.1, as in the macOS build, from BtbN's builds: a month-end one, which they keep for two years.
FFMPEG_URL = ("https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/autobuild-2026-10-31-12-59/"
              "ffmpeg-n8.1.3-27-g8dca1586f4-win64-lgpl-shared-8.1.zip")
FFMPEG_SHA256 = "5cef7bc48e513f3cee7c881e8b2999d835541edb1846c3e89443a67f8f8556ab"
FFMPEG_LIBS = ("avcodec", "avformat", "avutil", "swresample", "swscale")  # what Dolphin links

CACHE = locate.cache_root()
SRC = CACHE / "mainline"
BUILD = SRC / "build"
PATCHES = REPO / "tools" / "dolphin-build" / "patches-mainline"
OUT = Path(os.environ.get("OUTPUT_DIR") or REPO / "packages" / "slippi-playback-mainline")
FFMPEG_ZIP = CACHE / "downloads" / FFMPEG_URL.rsplit("/", 1)[1]
FFMPEG = CACHE / "ffmpeg-windows" / FFMPEG_ZIP.stem  # the zip's own top folder: bin\, include\, lib\
VENV = CACHE / "venv-cmake3"
EXE = "dolphin-emu-nogui.exe"
RUST_DLL = "slippi_rust_extensions.dll"
CMAKE_ARGS = [
    "-G", "Ninja",
    "-DCMAKE_BUILD_TYPE=Release",
    "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",
    "-DCMAKE_C_COMPILER=cl", "-DCMAKE_CXX_COMPILER=cl",
    "-DSLIPPI_PLAYBACK=ON",
    "-DENABLE_QT=OFF",
    "-DENABLE_NOGUI=ON",
    "-DENABLE_SDL=OFF",
    "-DENABLE_TESTS=OFF",
    "-DENABLE_LLVM=OFF",
    "-DENABLE_ANALYTICS=OFF",
    "-DENABLE_AUTOUPDATE=OFF",
    "-DUSE_DISCORD_PRESENCE=OFF",
    "-DUSE_SYSTEM_LIBS=OFF",
    f"-DRust_TOOLCHAIN={RUST}",
]  # Vulkan stays on (the default): a second backend that runs without a window, besides Direct3D


def log(message: str) -> None:
    print(f"\n== {message}", flush=True)


def fail(message: str) -> None:
    sys.exit(f"ERROR: {message}")


def git(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(SRC), *args], check=check, capture_output=capture,
                          encoding="utf-8", errors="replace")


def tee(cmd: Sequence, log_file: Path, env: Optional[Dict[str, str]] = None) -> str:
    """Run a command, showing its output as it comes and keeping a copy in log_file. Returns the output."""
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    lines: List[str] = []
    with subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                          encoding="utf-8", errors="replace") as proc, \
            open(log_file, "w", encoding="utf-8") as out:
        for line in proc.stdout:
            sys.stdout.write(line)
            out.write(line)
            lines.append(line)
    if proc.returncode:
        fail(f"{Path(str(cmd[0])).name} exited with {proc.returncode}; the output is in {log_file}")
    return "".join(lines)


# ---------------------------------------------------------------- fetch
def fetch() -> None:
    if not (SRC / ".git").exists():
        log(f"Fetching Slippi mainline Dolphin {COMMIT}")
        SRC.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(SRC)], check=True)
        git("config", "core.autocrlf", "false")  # the patches and Dolphin's sources are LF
        git("config", "core.longpaths", "true")
        git("remote", "add", "origin", DOLPHIN_GIT)
    if git("rev-parse", "HEAD", check=False, capture=True).stdout.strip() != COMMIT:
        git("fetch", "-q", "--depth", "1", "origin", COMMIT)
        git("checkout", "-q", "FETCH_HEAD")
    # Every submodule but Externals/Qt (378 MB of Windows Qt binaries), which the NoGUI build doesn't use.
    listed = git("config", "-f", ".gitmodules", "--get-regexp", r"\.path$", capture=True).stdout.split()
    paths = [p for p in listed[1::2] if p != "Externals/Qt"]
    git("-c", "core.autocrlf=false", "submodule", "update", "--init", "--recursive", "--depth", "1",
        "--jobs", "4", "--", *paths)
    apply_patches()


def apply_patches() -> None:
    """As build-mac-mainline.sh: the patches go on in order, so the tree has the first k of them. The last of
    those has nothing on top, so it reverse-checks on its own; the rest go on one by one."""
    patches = sorted(PATCHES.glob("*.patch"))
    for p in patches:
        if b"\r\n" in p.read_bytes():
            fail(f"{p} has Windows (CRLF) line endings, so it won't apply. This checkout predates .gitattributes "
                 "keeping patches LF: run `git rm --cached -r . && git reset --hard` in the repo (it only "
                 "rewrites line endings), or clone it again.")
    applied = 0
    for i in range(len(patches), 0, -1):
        if git("apply", "--reverse", "--check", str(patches[i - 1]), check=False, capture=True).returncode == 0:
            applied = i
            break
    for p in patches[:applied]:
        print(f"already applied: {p.name}")
    for p in patches[applied:]:
        log(f"Applying {p.name}")
        if git("apply", str(p), check=False).returncode != 0:
            fail(f"{p.name} doesn't apply to {SRC}: it has changes the patches don't expect (an older version "
                 "of a patch, or edits). Undo them, then run this again:\n"
                 f'  git -C "{SRC}" checkout -- . && git -C "{SRC}" clean -fd Source && '
                 f'git -C "{SRC}" submodule foreach --recursive git checkout -- .')


# ---------------------------------------------------------------- tools
def require_windows() -> None:
    if os.name != "nt":
        fail("this builds the Windows package; on macOS use tools/dolphin-build/build-mac-mainline.sh")


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=600) as r, open(part, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    except OSError:  # e.g. no CA certificates for Python: curl.exe is part of Windows 10 and later
        subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(part), url], check=True)
    part.replace(dest)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ensure_ffmpeg() -> Path:
    """FFmpeg's headers, import libraries (lib\\*.lib) and DLLs (bin\\), checked against the pinned SHA-256."""
    if all((FFMPEG / "lib" / f"{name}.lib").exists() for name in FFMPEG_LIBS):
        return FFMPEG
    if not FFMPEG_ZIP.exists():
        log(f"Downloading {FFMPEG_ZIP.name}")
        download(FFMPEG_URL, FFMPEG_ZIP)
    digest = sha256(FFMPEG_ZIP)
    if digest != FFMPEG_SHA256:
        FFMPEG_ZIP.unlink()
        fail(f"{FFMPEG_ZIP.name} has SHA-256 {digest}, not {FFMPEG_SHA256}; deleted it, run this again")
    shutil.rmtree(FFMPEG.parent, ignore_errors=True)
    with zipfile.ZipFile(FFMPEG_ZIP) as z:
        z.extractall(FFMPEG.parent)
    if not (FFMPEG / "lib" / "avcodec.lib").exists():
        fail(f"{FFMPEG_ZIP.name} doesn't have the expected lib\\avcodec.lib")
    return FFMPEG


def cmake_tools() -> Path:
    """CMake 3.31 and Ninja in a venv (CMake 4 rejects the cmake_minimum_required of some submodules)."""
    scripts = VENV / "Scripts"
    if not (scripts / "cmake.exe").exists() or not (scripts / "ninja.exe").exists():
        log(f"Installing CMake 3.31 and Ninja into {VENV}")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
        subprocess.run([str(scripts / "python.exe"), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                        "cmake>=3.31,<3.32", "ninja"], check=True)
    return scripts


def ensure_rust() -> None:
    if not shutil.which("rustup"):
        fail("rustup not found: install Rust from https://rustup.rs")
    toolchains = subprocess.run(["rustup", "toolchain", "list"], capture_output=True, encoding="utf-8",
                                errors="replace").stdout
    if not any(line.startswith(RUST) for line in toolchains.splitlines()):
        log(f"Installing Rust {RUST}")
        subprocess.run(["rustup", "toolchain", "install", RUST, "--profile", "minimal", "--component", "rustfmt"],
                       check=True)


def msvc_env() -> Dict[str, str]:
    """This environment if cl.exe is already on the PATH (a developer prompt, or vs-shell in CI); otherwise the one
    vcvars64.bat sets up, as an "x64 Native Tools Command Prompt" would."""
    env = {k.upper(): v for k, v in os.environ.items()}
    if shutil.which("cl"):
        return env
    installer = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio"
    vswhere = installer / "Installer" / "vswhere.exe"
    install = ""
    if vswhere.exists():
        install = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                                  "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                                 capture_output=True, encoding="utf-8", errors="replace").stdout.strip()
    vcvars = Path(install) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not install or not vcvars.exists():
        fail("no Visual Studio C++ compiler found. Install Visual Studio 2022 or its Build Tools with the "
             "\"Desktop development with C++\" workload, or run this from an x64 Native Tools Command Prompt.")
    # As setuptools does: run the batch file, then print the environment it leaves (/u: as UTF-16).
    out = subprocess.check_output(f'cmd /u /c "{vcvars}" && set', stderr=subprocess.STDOUT)
    for line in out.decode("utf-16le", errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if sep and key and " " not in key:
            env[key.upper()] = value
    if not shutil.which("cl", path=env.get("PATH")):
        fail(f"{vcvars} didn't put cl.exe on the PATH")
    return env


def build_env() -> Dict[str, str]:
    env = msvc_env()
    env["PATH"] = str(cmake_tools()) + os.pathsep + env.get("PATH", "")
    # CMakeLists.txt points FFMPEG_DIR at the bundled FFmpeg on Windows, which hides -DFFMPEG_DIR; FindFFmpeg.cmake
    # takes this environment variable instead.
    env["FFMPEG_DIR"] = str(ensure_ffmpeg())
    return env


# ---------------------------------------------------------------- configure, build
def configure() -> None:
    require_windows()
    ensure_rust()
    env = build_env()
    log(f"Configuring (playback, NoGUI only, FFmpeg from {env['FFMPEG_DIR']})")
    out = tee(["cmake", "-S", SRC, "-B", BUILD, *CMAKE_ARGS], CACHE / "mainline-configure.log", env)
    if "libav/ffmpeg found, enabling AVI frame dumps" not in out:
        fail("CMake did not find FFmpeg, so frame dumping would be disabled")
    found = [line for line in out.splitlines() if "Found avcodec:" in line]
    if not found or Path(env["FFMPEG_DIR"]).as_posix().lower() not in found[0].replace("\\", "/").lower():
        fail(f"CMake found another FFmpeg than {env['FFMPEG_DIR']}: {found[:1]}")


def build() -> None:
    require_windows()
    env = build_env()
    jobs = os.environ.get("JOBS") or str(os.cpu_count() or 4)
    log(f"Building dolphin-nogui with {jobs} parallel jobs")
    tee(["cmake", "--build", BUILD, "--target", "dolphin-nogui", "-j", jobs], CACHE / "mainline-build.log", env)


# ---------------------------------------------------------------- bundle
def dependents(binary: Path, env: Dict[str, str]) -> List[str]:
    """The DLLs a program or DLL loads, from dumpbin /dependents."""
    out = subprocess.run(["dumpbin", "/nologo", "/dependents", str(binary)], capture_output=True, env=env,
                         encoding="utf-8", errors="replace", check=True).stdout
    return parse_dependents(out)


def parse_dependents(dumpbin_output: str) -> List[str]:
    names = []
    for line in dumpbin_output.splitlines():
        name = line.strip()
        if line.startswith("    ") and name.lower().endswith(".dll") and " " not in name:
            names.append(name)
    return names


def vc_redist(env: Dict[str, str]) -> Optional[Path]:
    """The Visual C++ runtime DLLs that come with the compiler, to ship next to the program."""
    root = env.get("VCTOOLSREDISTDIR")
    folders = sorted(Path(root).glob("x64/Microsoft.VC*.CRT")) if root else []
    return folders[-1] if folders else None


def bundle() -> None:
    require_windows()
    env = msvc_env()
    exe = SRC / "Binary" / "x64" / EXE  # Windows builds put their programs in the source tree (CMakeLists.txt)
    rust_dll = BUILD / "cargo" / "build" / "x86_64-pc-windows-msvc" / "release" / RUST_DLL
    for f in (exe, rust_dll):
        if not f.exists():
            fail(f"{f} isn't built")
    stage = BUILD / "AlphaSolvePackage"
    log(f"Assembling {stage}")
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    shutil.copy2(exe, stage)
    shutil.copy2(rust_dll, stage)
    ffmpeg = ensure_ffmpeg()
    for name in FFMPEG_LIBS:
        dlls = sorted((ffmpeg / "bin").glob(f"{name}-*.dll"))
        if len(dlls) != 1:
            fail(f"expected one {name}-*.dll in {ffmpeg / 'bin'}, found {[d.name for d in dlls]}")
        shutil.copy2(dlls[0], stage)
    if b"matroska" not in next(stage.glob("avformat-*.dll")).read_bytes():
        fail("this FFmpeg's avformat has no Matroska muxer, which slp2alpha records in")

    # Dolphin looks for Sys next to the program. Playback builds swap the netplay Gecko codes for the playback ones.
    shutil.copytree(SRC / "Data" / "Sys", stage / "Sys")
    shutil.copy2(SRC / "Data" / "PlaybackGeckoCodes" / "GALE01r2.ini", stage / "Sys" / "GameSettings" / "GALE01r2.ini")
    for placeholder in (stage / "Sys" / "GameSettings").glob("Replace *.txt"):
        placeholder.unlink()
    shutil.copy2(SRC / "COPYING", stage / "COPYING")
    shutil.copytree(SRC / "LICENSES", stage / "Licenses")
    if (ffmpeg / "LICENSE.txt").exists():
        shutil.copy2(ffmpeg / "LICENSE.txt", stage / "Licenses" / "FFmpeg-LICENSE.txt")

    log("Checking the DLLs")
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    redist = vc_redist(env)
    missing = set()
    for binary in sorted(stage.glob("*.exe")) + sorted(stage.glob("*.dll")):
        for dll in dependents(binary, env):
            low = dll.lower()
            if (stage / dll).exists() or low.startswith(("api-ms-win-", "ext-ms-")):
                continue
            if redist and (redist / dll).exists():  # the VC++ runtime: ship it, so it needn't be installed
                shutil.copy2(redist / dll, stage / dll)
                continue
            if not (system32 / dll).exists():
                missing.add(f"{dll} (needed by {binary.name})")
    if missing:
        fail("DLLs that are neither in the package nor in Windows: " + ", ".join(sorted(missing)))
    print("\n".join(sorted(p.name for p in stage.iterdir())))

    log("Checking the program")
    help_out = subprocess.run([str(stage / EXE), "--help"], capture_output=True, encoding="utf-8", errors="replace",
                              timeout=120)
    text = help_out.stdout + help_out.stderr
    for option in ("--cout", "--camera-out", "--hide-seekbar"):
        if option not in text:
            fail(f"{EXE} --help doesn't list {option} (exit code {help_out.returncode}): a patch is missing, or a "
                 f"DLL didn't load\n{text[-500:]}")

    cl = subprocess.run(["cl"], capture_output=True, env=env, encoding="utf-8", errors="replace")
    compiler = next((line.strip() for line in (cl.stderr + cl.stdout).splitlines() if "Version" in line), "cl")
    (stage / "BUILD.txt").write_text("\n".join([
        "Slippi mainline playback Dolphin, headless (dolphin-emu-nogui), for slp2alpha",
        f"source: {DOLPHIN_GIT} {COMMIT}",
        "patches: " + ", ".join(p.name for p in sorted(PATCHES.glob("*.patch"))),
        f"FFmpeg: {FFMPEG_ZIP.name} (SHA-256 {FFMPEG_SHA256})",
        f"compiler: {compiler}",
        f"built: {datetime.datetime.now().isoformat(timespec='seconds')}",
    ]) + "\n", encoding="utf-8")

    log(f"Copying to {OUT}")
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(stage, OUT)
    print(f"Done: {OUT / EXE}")


STEPS = {
    "fetch": [fetch],
    "configure": [fetch, configure],
    "build": [build],
    "bundle": [bundle],
    "all": [fetch, configure, build, bundle],
}


def main(argv: Sequence[str]) -> int:
    step = argv[0] if argv else "all"
    if step not in STEPS or len(argv) > 1:
        print(f"usage: {Path(__file__).name} [{'|'.join(STEPS)}]", file=sys.stderr)
        return 2
    for function in STEPS[step]:
        function()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
