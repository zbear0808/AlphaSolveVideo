"""Turn a librashader preset into what blender_crt.py draws: each pass's GLSL, the lookup textures as raw RGBA, and
chain.json (each pass's filter, wrap mode, framebuffer format and scaling, and every parameter's default).

    python3 prep_chain.py [--preset PRESET] [--librashader librashader-cli] [--ffmpeg ffmpeg] OUT_DIR

librashader-cli does the work: `parse` reads the preset, `transpile` compiles each slang pass to GLSL 330 (through
SPIR-V, as its own runtimes do), `preprocess` lists each pass's parameters and framebuffer format. Defaults: the
crt-royale preset in tools/crt and the librashader-cli that tools/crt/install_librashader.py builds.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "crt"))
import render_video  # noqa: E402
from slp2alpha import locate  # noqa: E402


def run(*cmd) -> str:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, check=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--preset", default=str(render_video.PRESET))
    ap.add_argument("--librashader")
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()
    cli = render_video.find_librashader(a.librashader)
    ffmpeg = locate.find_ffmpeg(a.ffmpeg)
    ffprobe = locate.find_ffmpeg(a.ffmpeg, name="ffprobe")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = json.loads(run(cli, "parse", "-p", a.preset))
    params, passes = {}, []
    for p in doc["passes"]:
        m, i = p["meta"], p["meta"]["id"]
        for stage in ("vertex", "fragment"):
            (out / f"p{i}.{stage}.glsl").write_text(run(cli, "transpile", "-s", p["path"], "-o", stage, "-f", "glsl",
                                                        "-v", "330"))
        for k, v in json.loads(run(cli, "preprocess", "-s", p["path"], "-o", "params")).items():
            params.setdefault(k, v["initial"])
        # the preset's srgb_framebuffer / float_framebuffer win over the shader's own #pragma format
        fmt = ("R8G8B8A8Srgb" if m["srgb_framebuffer"] else "R16G16B16A16Sfloat" if m["float_framebuffer"]
               else run(cli, "preprocess", "-s", p["path"], "-o", "passformat").strip())
        sc = m["scaling"]
        passes.append(dict(id=i, alias=m["alias"], filter=m["filter"], wrap=m["wrap_mode"], format=fmt,
                           mipmap_input=m["mipmap_input"], frame_count_mod=m["frame_count_mod"],
                           scale_x=[sc["x"]["scale_type"], next(iter(sc["x"]["factor"].values()))],
                           scale_y=[sc["y"]["scale_type"], next(iter(sc["y"]["factor"].values()))]))
    luts = []
    for t in doc["textures"]:
        name = t["meta"]["name"]
        w, h = run(ffprobe, "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                   t["path"]).strip().split(",")
        run(ffmpeg, "-v", "error", "-y", "-i", t["path"], "-f", "rawvideo", "-pix_fmt", "rgba", out / f"{name}.rgba")
        luts.append(dict(name=name, size=[int(w), int(h)], filter=t["meta"]["filter_mode"],
                         wrap=t["meta"]["wrap_mode"], mipmap=t["meta"]["mipmap"]))
    for k, v in doc.get("parameters") or []:   # the preset's own parameter values, if it sets any
        params[k] = v
    (out / "chain.json").write_text(json.dumps(dict(preset=a.preset, passes=passes, luts=luts, params=params), indent=1))
    print(f"{out}: {len(passes)} passes, {len(luts)} lookup textures, {len(params)} parameters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
