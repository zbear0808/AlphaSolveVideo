#!/usr/bin/env python3
"""Build the Animelee Complete Edition ISO from your own Melee NTSC 1.02 ISO.

    python3 tools/animelee/build_iso.py [--iso VANILLA.iso] [--zip PATCH.zip] [--out FILE] [--xdelta3 PATH]

--iso      defaults to the ISO set in the Slippi Launcher.
--zip      a downloaded "ANIMELEE_-_COMPLETE_EDITION_-_PATCH_1.0.zip"; without it the zip is fetched from
           animelee.xyz's MediaFire link (30 MB).
--out      defaults to "ANIMELEE - COMPLETE EDITION.iso" in animelee/ under the cache folder
           (~/Library/Caches/AlphaSolveVideo on macOS, %LOCALAPPDATA%\\AlphaSolveVideo on Windows), where
           `slp2alpha render --animelee` looks for it.
--xdelta3  the xdelta3 program, if it isn't on the PATH as xdelta3 (macOS: brew install xdelta; Windows: the
           x86_64 .exe from https://github.com/jmacd/xdelta-gpl/releases).

The patch only changes data files (the DOL is identical), so every Gecko code in Resources/ keeps working.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
from slp2alpha import locate  # noqa: E402

PAGE = "https://www.mediafire.com/file/2ztqob93nrug8yg/ANIMELEE_-_COMPLETE_EDITION_-_PATCH_1.0.zip/file"
VANILLA_MD5 = "0e63d4223b01d9aba596259dc155a174"
USER_AGENT = "Mozilla/5.0"


def fetch(url: str) -> bytes:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120) as r:
            return r.read()
    except OSError:  # e.g. a Python without CA certificates: curl has its own (also on Windows 10 and later)
        return subprocess.run(["curl", "-sfL", "-A", USER_AGENT, url], capture_output=True, check=True).stdout


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--iso", help="your Melee NTSC 1.02 ISO (default: the one set in the Slippi Launcher)")
    ap.add_argument("--zip", help="the Animelee patch zip, if already downloaded")
    ap.add_argument("--out", help=f"the ISO to write (default: {locate.animelee_iso_path()})")
    ap.add_argument("--xdelta3", help="the xdelta3 program (default: xdelta3 on the PATH)")
    args = ap.parse_args()

    xdelta3 = args.xdelta3 or shutil.which("xdelta3")
    if not xdelta3 or not Path(xdelta3).exists():
        print("xdelta3 not found (macOS: brew install xdelta; Windows: the .exe from "
              "https://github.com/jmacd/xdelta-gpl/releases, on the PATH or passed with --xdelta3)", file=sys.stderr)
        return 1
    try:
        iso = locate.find_iso(args.iso)
    except locate.NotFound as e:
        print(e, file=sys.stderr)
        return 1
    out = Path(args.out).expanduser() if args.out else locate.animelee_iso_path()
    digest = md5_of(iso)
    if digest != VANILLA_MD5:
        print(f"warning: {iso} has MD5 {digest}, not the clean 1.02 hash {VANILLA_MD5}; the patch may fail",
              file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="animelee-") as tmp:
        work = Path(tmp)
        patch_zip = Path(args.zip).expanduser() if args.zip else None
        if patch_zip is None:
            print("downloading the Animelee patch ...")
            link = re.search(r'https://download[^"]*zip', fetch(PAGE).decode("utf-8", "replace"))
            if not link:
                print("could not find the download link on MediaFire; download the zip from animelee.xyz and "
                      "pass --zip", file=sys.stderr)
                return 1
            patch_zip = work / "patch.zip"
            patch_zip.write_bytes(fetch(link.group(0)))
        with zipfile.ZipFile(patch_zip) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".xdelta")]
            if not names:
                print(f"no .xdelta file in {patch_zip}", file=sys.stderr)
                return 1
            xdelta = Path(z.extract(names[0], work / "patch"))
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([xdelta3, "-d", "-f", "-s", str(iso), str(xdelta), str(out)], check=True)
    print(f"built: {out}")
    print("render with: python -m slp2alpha render REPLAY.slp --animelee --scale 2   (from tools/slp2alpha)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
