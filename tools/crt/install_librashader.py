#!/usr/bin/env python3
"""Install librashader-cli, which the CRT renders with, into packages/librashader/.

    python3 tools/crt/install_librashader.py [--features LIST] [--force]

It builds librashader-cli 0.12.1, the version the CRT was checked with, from source with Rust's cargo
(https://rustup.rs), with the runtimes this platform renders with. wgpu is in every build: librashader-cli 0.12.1
doesn't compile without it (its transpile command always needs wgpu's shader translator, naga).

    macOS    metal, wgpu
    Windows  d3d11, wgpu (d3d12 would download a prebuilt shader compiler while building)
    Linux    wgpu (it draws through Vulkan) and vulkan (OpenGL would need X11's development packages to build)

librashader-cli's own Vulkan runtime draws at the input's size whatever size it's asked for, so render_video.py
draws through wgpu on Linux (it checks every frame's size).

The build needs a C++ compiler: Xcode's command line tools, Visual Studio's C++ build tools, or build-essential.
It takes a few minutes; its build folder stays in the cache folder, so another run is quick. render_video.py finds
the program in packages/librashader/bin/ (also on the PATH, in ~/.cargo/bin, or through LIBRASHADER_CLI).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_video  # noqa: E402
from slp2alpha import locate  # noqa: E402  (render_video puts slp2alpha on the path)


FEATURES = {"darwin": ["metal", "wgpu"], "win32": ["d3d11", "wgpu"], "linux": ["wgpu", "vulkan"]}


def platform_features(platform: str = sys.platform) -> list:
    """The runtimes to build. librashader-cli 0.12.1 only compiles with wgpu among them (`use
    librashader::reflect::naga` in its main.rs, which only the wgpu feature turns on)."""
    return FEATURES.get(platform, FEATURES["linux"])


def find_cargo() -> str:
    exe = "cargo.exe" if os.name == "nt" else "cargo"
    for c in (shutil.which("cargo"), Path.home() / ".cargo" / "bin" / exe):
        if c and Path(c).exists():
            return str(c)
    raise locate.NotFound("cargo not found: install Rust from https://rustup.rs (on Windows also Visual Studio's "
                          "C++ build tools), then run this again")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--features", help=f"runtimes to build, comma-separated (default here: "
                                       f"{','.join(platform_features())}; also wgpu, opengl, d3d12, d3d9)")
    ap.add_argument("--force", action="store_true", help="build again even if this version is installed")
    args = ap.parse_args(argv)
    features = args.features or ",".join(platform_features())
    root = render_video.LIBRASHADER_PACKAGE
    cmd = [find_cargo(), "install", "librashader-cli", "--version", render_video.LIBRASHADER_VERSION, "--locked",
           "--no-default-features", "--features", features, "--root", str(root)]
    if args.force:
        cmd.append("--force")
    env = dict(os.environ, CARGO_TARGET_DIR=str(locate.cache_root() / "librashader-build"))
    print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, env=env, check=True)
    exe = render_video.package_exe()
    version = subprocess.run([str(exe), "--version"], capture_output=True, encoding="utf-8", errors="replace")
    if render_video.LIBRASHADER_VERSION not in version.stdout:
        raise RuntimeError(f"{exe} says {version.stdout.strip() or version.stderr.strip()!r}, "
                           f"not {render_video.LIBRASHADER_VERSION}")
    print(f"{exe}: {version.stdout.strip()}, runtimes {', '.join(render_video.runtimes_of(exe))}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (locate.NotFound, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
