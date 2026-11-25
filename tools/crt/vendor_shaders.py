#!/usr/bin/env python3
"""Copy the slang-shaders files our CRT presets need into tools/crt/slang-shaders/, or check the copy.

    python3 tools/crt/vendor_shaders.py copy SLANG_SHADERS_CHECKOUT    # a checkout at commit 2345ee91
    python3 tools/crt/vendor_shaders.py check                          # test_crt.py runs this too

The files are each preset's shaders and textures, the presets it #references, everything they #include, and each
shader family's licence and readme, unmodified. MANIFEST lists each one with its git blob id, the same id
`git ls-tree -r 2345ee91` shows for it in a checkout of https://github.com/libretro/slang-shaders, so the copy can be
checked against upstream.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set

HERE = Path(__file__).resolve().parent
VENDORED = HERE / "slang-shaders"
PRESETS = {"royale": "crt/crt-royale.slangp", "guest": "crt/crt-guest-advanced.slangp",
           "guest-ntsc": "crt/crt-guest-advanced-ntsc.slangp", "megatron": "hdr/crt-sony-megatron-v2-default.slangp"}
MEGATRON_DISPLAYS = ("sony-pvm-2730", "sony-pvm-20L4", "sony-pvm-1910", "bang-olufsen-mx8000")
# vendored with the presets: Megatron's display presets and its SDR preset (they #reference the default one)
MORE_PRESETS = tuple(f"hdr/sony_megatron_v2_presets/crt-sony-megatron-v2-{d}.slangp" for d in MEGATRON_DISPLAYS) + (
    "hdr/crt-sony-megatron-v2-default-sdr.slangp",)
COMMIT = "2345ee91602a7404d3a1a6a5df6108d7305fdad4"
EXTRAS = ("crt/shaders/crt-royale/LICENSE.TXT", "crt/shaders/crt-royale/README.TXT",
          "crt/shaders/crt-royale/THANKS.TXT", "crt/shaders/guest/advanced/README_old")
OURS = ("README.md", "MANIFEST")   # written here, not upstream's
SOURCES = (".slang", ".h", ".inc", ".glsl")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_REFERENCE = re.compile(r'^\s*#\s*reference\s+"([^"]+)"', re.M)
_SETTING = re.compile(r'^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(?:"([^"]*)"|([^\s#;]+))', re.M)
_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)


def preset_files(preset: Path) -> Set[Path]:
    """One preset file's shaders and textures, quoted or not, and the presets it #references (not followed)."""
    text = _BLOCK_COMMENT.sub("", preset.read_text(encoding="utf-8", errors="replace"))
    out = {(preset.parent / m.group(1)).resolve() for m in _REFERENCE.finditer(text)}
    settings: Dict[str, str] = {}
    for m in _SETTING.finditer(text):
        settings[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    textures = [t.strip() for t in settings.get("textures", "").split(";") if t.strip()]
    for key, value in settings.items():
        if (re.fullmatch(r"shader\d+", key) or key in textures) and value:
            out.add((preset.parent / value).resolve())
    return out


def closure(root: Path, preset: str = PRESETS["royale"]) -> Set[str]:
    """The preset and every file it needs: the presets it #references (recursively), their shaders and textures, and
    what the shaders #include (under any #if, so this may list a little more than one configuration compiles).
    Paths relative to root, with forward slashes."""
    root = root.resolve()
    need: Set[Path] = set()
    todo = [(root / preset).resolve()]
    while todo:
        path = todo.pop()
        if path in need:
            continue
        need.add(path)
        if not path.is_file():
            continue
        if path.suffix == ".slangp":
            todo += preset_files(path)
        elif path.suffix in SOURCES:
            todo += [(path.parent / m.group(1)).resolve()
                     for m in _INCLUDE.finditer(path.read_text(encoding="utf-8", errors="replace"))]
    return {p.relative_to(root).as_posix() for p in need}


def needed(root: Path, presets: Iterable[str] = tuple(PRESETS.values()) + MORE_PRESETS) -> Set[str]:
    """Everything every preset needs, and the licence and readme files."""
    out = set(EXTRAS)
    for preset in presets:
        out |= closure(root, preset)
    return out


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
    need = needed(folder)
    problems += [f"{p}: needed but missing" for p in sorted(need) if not (folder / p).is_file()]
    problems += [f"{p}: needed but not in MANIFEST" for p in sorted(need - set(manifest))]
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
    files = sorted(needed(checkout))
    missing = [f for f in files if not (checkout / f).is_file()]
    if missing:
        raise SystemExit(f"not in {checkout}: {', '.join(missing)}")
    for item in VENDORED.iterdir() if VENDORED.exists() else ():
        if item.name not in OURS:
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    lines = [f"# libretro/slang-shaders {commit or 'unknown commit'}: the files "
             f"{', '.join(tuple(PRESETS.values()) + MORE_PRESETS)} need, unmodified. git blob id, path."]
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
