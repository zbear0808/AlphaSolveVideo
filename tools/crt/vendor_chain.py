#!/usr/bin/env python3
"""Write crt-royale as Blender's GPU module draws it into tools/crt/blender-chain/, or check that copy.

    python3 tools/crt/vendor_chain.py write     # needs librashader-cli 0.12.1 (install_librashader.py)
    python3 tools/crt/vendor_chain.py check     # test_crt.py runs this when librashader-cli is there

librashader-cli does the compiling, as its own runtimes do: `transpile` turns each slang pass of the vendored preset
(slang-shaders/crt/crt-royale.slangp) into GLSL 330 through SPIR-V, `parse` and `preprocess` give each pass's filter,
wrap mode, framebuffer format and scaling, and every parameter's default. chain.json has those; p0.vertex.glsl ...
p11.fragment.glsl the shaders. blender_crt.py draws them, so --runtime blender needs no librashader at all. The
mask textures stay in slang-shaders/; chain.json names them relative to the preset's folder.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_video  # noqa: E402

CHAIN = HERE / "blender-chain"


def _run(*cmd) -> str:
    return subprocess.run([str(c) for c in cmd], capture_output=True, encoding="utf-8", errors="replace",
                          check=True).stdout


def build(cli: str, preset: Path = render_video.PRESET) -> Dict[str, str]:
    """The chain's files (name -> text) for `preset`, from librashader-cli."""
    preset = Path(preset).resolve()
    doc = json.loads(_run(cli, "parse", "-p", preset))
    files: Dict[str, str] = {}
    params: Dict[str, float] = {}
    passes: List[dict] = []
    for p in doc["passes"]:
        m, i = p["meta"], p["meta"]["id"]
        for stage in ("vertex", "fragment"):
            files[f"p{i}.{stage}.glsl"] = _run(cli, "transpile", "-s", p["path"], "-o", stage, "-f", "glsl",
                                               "-v", "330")
        for k, v in json.loads(_run(cli, "preprocess", "-s", p["path"], "-o", "params")).items():
            params.setdefault(k, v["initial"])
        # the preset's srgb_framebuffer / float_framebuffer win over the shader's own #pragma format
        fmt = ("R8G8B8A8Srgb" if m["srgb_framebuffer"] else "R16G16B16A16Sfloat" if m["float_framebuffer"]
               else _run(cli, "preprocess", "-s", p["path"], "-o", "passformat").strip())
        sc = m["scaling"]
        passes.append(dict(id=i, alias=m["alias"], filter=m["filter"], wrap=m["wrap_mode"], format=fmt,
                           mipmap_input=m["mipmap_input"], frame_count_mod=m["frame_count_mod"],
                           scale_x=[sc["x"]["scale_type"], next(iter(sc["x"]["factor"].values()))],
                           scale_y=[sc["y"]["scale_type"], next(iter(sc["y"]["factor"].values()))]))
    luts = [dict(name=t["meta"]["name"], path=Path(t["path"]).resolve().relative_to(preset.parent).as_posix(),
                 filter=t["meta"]["filter_mode"], wrap=t["meta"]["wrap_mode"], mipmap=t["meta"]["mipmap"])
            for t in doc["textures"]]
    for k, v in doc.get("parameters") or []:   # the preset's own parameter values, if it sets any
        params[k] = v
    version = _run(cli, "--version").strip()
    files["chain.json"] = json.dumps(dict(
        preset=preset.relative_to(HERE).as_posix(), shaders_commit=render_video.SHADERS_COMMIT, librashader=version,
        passes=passes, luts=luts, params=dict(sorted(params.items()))), indent=1) + "\n"
    return files


def write(cli: str, folder: Path = CHAIN) -> int:
    files = build(cli)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        if old.name not in files and old.name != "README.md":
            old.unlink()
    for name, text in files.items():
        (folder / name).write_bytes(text.encode("utf-8"))
    print(f"wrote {len(files)} files ({sum(len(t) for t in files.values()) // 1024} KB) into {folder}")
    return 0


def check(cli: str, folder: Path = CHAIN) -> List[str]:
    """What differs between the copy and what librashader-cli writes now."""
    files = build(cli)
    problems = [f"{name}: missing" for name in files if not (folder / name).is_file()]
    problems += [f"{name}: differs from librashader-cli's" for name, text in files.items()
                 if (folder / name).is_file() and (folder / name).read_bytes() != text.encode("utf-8")]
    present = {p.name for p in folder.iterdir() if p.is_file()} - {"README.md"}
    problems += [f"{name}: not written by librashader-cli" for name in sorted(present - set(files))]
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("write", "check"))
    ap.add_argument("--librashader", help="librashader-cli (default: as render_video.py finds it)")
    args = ap.parse_args(argv)
    cli = render_video.find_librashader(args.librashader)
    if args.cmd == "write":
        return write(cli)
    problems = check(cli)
    for p in problems:
        print(f"problem: {p}")
    print("the copy is what librashader-cli writes" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
