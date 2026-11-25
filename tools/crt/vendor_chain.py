#!/usr/bin/env python3
"""Write each CRT preset as Blender's GPU module draws it into tools/crt/blender-chain/<shader>/, or check them.

    python3 tools/crt/vendor_chain.py write [SHADER ...]   # needs librashader-cli 0.12.1 (install_librashader.py)
    python3 tools/crt/vendor_chain.py check [SHADER ...]   # test_crt.py runs this when librashader-cli is there

SHADER is royale, guest, guest-ntsc or megatron (default: all of them), the presets vendor_shaders.PRESETS names.
librashader-cli does the compiling, as its own runtimes do: `transpile` turns each slang pass of the vendored preset
(for royale slang-shaders/crt/crt-royale.slangp) into GLSL 330 through SPIR-V, `parse` and `preprocess` give each
pass's filter, wrap mode, framebuffer format and scaling, and every parameter's default. chain.json has those;
p0.vertex.glsl, p0.fragment.glsl ... the shaders. A pass whose output a pass reads on the next frame (as
<alias>Feedback or PassFeedback<N>) has "feedback": true. blender_crt.py draws them, so --runtime blender needs no
librashader at all. The LUT textures stay in slang-shaders/; chain.json names them relative to the preset's folder.

Megatron's chain.json also has "looks": for each of its display presets (vendor_shaders.MEGATRON_DISPLAYS), the value
of every parameter that either the default preset or the display preset sets, as the display preset leaves it. Those
parameters on top of the default preset draw what the display preset draws.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_video  # noqa: E402
import vendor_shaders  # noqa: E402

CHAINS = HERE / "blender-chain"
SHADERS = tuple(vendor_shaders.PRESETS)
_SAMPLER = re.compile(r"^uniform sampler2D LIBRA_TEXTURE_(\w+);", re.M)


def _run(*cmd) -> str:
    return subprocess.run([str(c) for c in cmd], capture_output=True, encoding="utf-8", errors="replace",
                          check=True).stdout


def preset_path(shader: str) -> Path:
    return vendor_shaders.VENDORED / vendor_shaders.PRESETS[shader]


def overrides(cli: str, preset: Path) -> Dict[str, float]:
    """The parameter values a preset sets, through the presets it #references."""
    return {o["name"]: o["value"] for o in json.loads(_run(cli, "parse", "-p", preset)).get("parameters") or []}


def looks(cli: str, defaults: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """Megatron's display looks from the shader's parameter defaults (as pipelines/megatron/params.py's
    display_params() in the crt-royale TouchDesigner project)."""
    base = overrides(cli, preset_path("megatron"))
    out = {}
    for name, stem in vendor_shaders.MEGATRON_DISPLAYS.items():
        display = overrides(cli, vendor_shaders.VENDORED / vendor_shaders.MEGATRON_DISPLAY_PRESET.format(stem))
        effective = dict(defaults, **{k: v for k, v in display.items() if k in defaults})
        out[name] = {k: effective[k] for k in sorted((set(base) | set(display)) & set(defaults))}
    return out


def build(cli: str, preset: Path = render_video.PRESET, with_looks: bool = False) -> Dict[str, str]:
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
    samplers = {s for text in files.values() for s in _SAMPLER.findall(text)}
    for p in passes:
        if f"PassFeedback{p['id']}" in samplers or (p["alias"] and f"{p['alias']}Feedback" in samplers):
            p["feedback"] = True
    luts = [dict(name=t["meta"]["name"], path=Path(t["path"]).resolve().relative_to(preset.parent).as_posix(),
                 filter=t["meta"]["filter_mode"], wrap=t["meta"]["wrap_mode"], mipmap=t["meta"]["mipmap"])
            for t in doc["textures"]]
    defaults = dict(params)
    for o in doc.get("parameters") or []:   # the preset's own parameter values, if it sets any
        params[o["name"]] = o["value"]
    version = _run(cli, "--version").strip()
    chain = dict(preset=preset.relative_to(HERE).as_posix(), shaders_commit=render_video.SHADERS_COMMIT,
                 librashader=version, passes=passes, luts=luts, params=dict(sorted(params.items())))
    if with_looks:
        chain["looks"] = looks(cli, defaults)
    files["chain.json"] = json.dumps(chain, indent=1) + "\n"
    return files


def build_shader(cli: str, shader: str) -> Dict[str, str]:
    return build(cli, preset_path(shader), with_looks=shader == "megatron")


def write(cli: str, shaders: Iterable[str] = SHADERS, chains: Path = CHAINS) -> int:
    for shader in shaders:
        files = build_shader(cli, shader)
        folder = chains / shader
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.iterdir():
            if old.name not in files:
                old.unlink()
        for name, text in files.items():
            (folder / name).write_bytes(text.encode("utf-8"))
        print(f"wrote {len(files)} files ({sum(len(t) for t in files.values()) // 1024} KB) into {folder}")
    return 0


def check(cli: str, shaders: Iterable[str] = SHADERS, chains: Path = CHAINS) -> List[str]:
    """What differs between the copies and what librashader-cli writes now."""
    problems = []
    for shader in shaders:
        files, folder = build_shader(cli, shader), chains / shader
        problems += [f"{shader}/{name}: missing" for name in files if not (folder / name).is_file()]
        problems += [f"{shader}/{name}: differs from librashader-cli's" for name, text in files.items()
                     if (folder / name).is_file() and (folder / name).read_bytes() != text.encode("utf-8")]
        present = {p.name for p in folder.iterdir() if p.is_file()} if folder.is_dir() else set()
        problems += [f"{shader}/{name}: not written by librashader-cli" for name in sorted(present - set(files))]
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("write", "check"))
    ap.add_argument("shaders", nargs="*", metavar="SHADER", help=f"{', '.join(SHADERS)} (default: all)")
    ap.add_argument("--librashader", help="librashader-cli (default: as render_video.py finds it)")
    args = ap.parse_args(argv)
    for shader in args.shaders:
        if shader not in SHADERS:
            ap.error(f"no shader {shader!r}: {', '.join(SHADERS)}")
    cli = render_video.find_librashader(args.librashader)
    shaders = args.shaders or SHADERS
    if args.cmd == "write":
        return write(cli, shaders)
    problems = check(cli, shaders)
    for p in problems:
        print(f"problem: {p}")
    print("the copies are what librashader-cli writes" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
