#!/usr/bin/env python3
"""Copy the slang-shaders files crt-royale needs into tools/crt/slang-shaders/, or check the copy.

    python3 tools/crt/vendor_shaders.py copy SLANG_SHADERS_CHECKOUT    # a checkout at commit 2345ee91
    python3 tools/crt/vendor_shaders.py check                          # test_crt.py runs this too

The files are the preset's shaders and textures, everything they #include, and crt-royale's licence, readme and
thanks, unmodified. MANIFEST lists each one with its git blob id, the same id `git ls-tree -r 2345ee91` shows for
it in a checkout of https://github.com/libretro/slang-shaders, so the copy can be checked against upstream.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set

HERE = Path(__file__).resolve().parent
VENDORED = HERE / "slang-shaders"
PRESET = "crt/crt-royale.slangp"
COMMIT = "2345ee91602a7404d3a1a6a5df6108d7305fdad4"
EXTRAS = ("crt/shaders/crt-royale/LICENSE.TXT", "crt/shaders/crt-royale/README.TXT",
          "crt/shaders/crt-royale/THANKS.TXT")
OURS = ("README.md", "MANIFEST")   # written here, not upstream's
SOURCES = (".slang", ".h", ".inc", ".glsl")
_PRESET_FILE = re.compile(r'^\s*[A-Za-z_0-9]+\s*=\s*"([^"]+\.(?:slang|png|slangp))"', re.M)
_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)


def closure(root: Path, preset: str = PRESET) -> Set[str]:
    """The preset and every file it needs: its shaders and textures, and what they #include (under any #if, so
    this may list a little more than one configuration compiles). Paths relative to root, with forward slashes."""
    root = root.resolve()
    start = root / preset
    need = {start}
    todo = []
    for m in _PRESET_FILE.finditer(start.read_text(encoding="utf-8", errors="replace")):
        path = (start.parent / m.group(1)).resolve()
        need.add(path)
        if path.suffix in SOURCES:
            todo.append(path)
    seen = set()
    while todo:
        path = todo.pop()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        for m in _INCLUDE.finditer(path.read_text(encoding="utf-8", errors="replace")):
            inc = (path.parent / m.group(1)).resolve()
            need.add(inc)
            if inc.suffix in SOURCES:
                todo.append(inc)
    return {p.relative_to(root).as_posix() for p in need}


def blob_id(data: bytes) -> str:
    """git's id for a file's contents (git hash-object)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def read_manifest(folder: Path = VENDORED) -> Dict[str, str]:
    out = {}
    for line in (folder / "MANIFEST").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            blob, path = line.split(None, 1)
            out[path] = blob
    return out


def check(folder: Path = VENDORED) -> List[str]:
    """What's wrong with the copy: missing files, files changed since they were copied, files not in MANIFEST."""
    problems = []
    manifest = read_manifest(folder)
    needed = closure(folder) | set(EXTRAS)
    problems += [f"{p}: needed but missing" for p in sorted(needed) if not (folder / p).is_file()]
    problems += [f"{p}: needed but not in MANIFEST" for p in sorted(needed - set(manifest))]
    for path, blob in sorted(manifest.items()):
        file = folder / path
        if not file.is_file():
            problems.append(f"{path}: in MANIFEST but missing")
        elif blob_id(file.read_bytes()) != blob:
            problems.append(f"{path}: changed (git blob {blob_id(file.read_bytes())[:10]}, MANIFEST {blob[:10]})")
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    problems += [f"{p}: not in MANIFEST" for p in sorted(present - set(manifest) - set(OURS))]
    return problems


def copy(checkout: Path, allow_other_commit: bool = False) -> int:
    checkout = checkout.resolve()
    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, encoding="utf-8")
    commit = head.stdout.strip() if head.returncode == 0 else None
    if commit != COMMIT and not allow_other_commit:
        raise SystemExit(f"{checkout} is at {commit or 'no git commit'}, not {COMMIT} "
                         "(--allow-other-commit to copy it anyway, then update COMMIT here and in render_video.py)")
    files = sorted(closure(checkout) | set(EXTRAS))
    missing = [f for f in files if not (checkout / f).is_file()]
    if missing:
        raise SystemExit(f"not in {checkout}: {', '.join(missing)}")
    for item in VENDORED.iterdir() if VENDORED.exists() else ():
        if item.name not in OURS:
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    lines = [f"# libretro/slang-shaders {commit or 'unknown commit'}: the files crt/crt-royale.slangp needs, "
             "unmodified. git blob id, path."]
    for f in files:
        data = (checkout / f).read_bytes()
        (VENDORED / f).parent.mkdir(parents=True, exist_ok=True)
        (VENDORED / f).write_bytes(data)
        lines.append(f"{blob_id(data)} {f}")
    (VENDORED / "MANIFEST").write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum((VENDORED / f).stat().st_size for f in files)
    print(f"copied {len(files)} files ({total // 1024} KB) into {VENDORED}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("copy", help="copy the files from a slang-shaders checkout")
    pc.add_argument("checkout")
    pc.add_argument("--allow-other-commit", action="store_true")
    sub.add_parser("check", help="check the copy against MANIFEST and the preset")
    args = ap.parse_args(argv)
    if args.cmd == "copy":
        return copy(Path(args.checkout).expanduser(), args.allow_other_commit)
    problems = check()
    for p in problems:
        print(f"problem: {p}")
    print(f"{len(read_manifest())} files, " + ("all as upstream" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
