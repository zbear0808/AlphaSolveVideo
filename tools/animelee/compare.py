#!/usr/bin/env python3
"""Render one replay with a vanilla ISO and with an Animelee ISO, then compare the two.

    python3 compare.py REPLAY.slp --vanilla V.iso --animelee A.iso [--out DIR] [-- render options...]

Everything after "--" goes to `slp2alpha render` (for example --characters-only --scale 2).

What it reports:
  * frame counts of both transparent videos (must match, or the replay desynced / dropped fields);
  * how far apart the two alpha maps are (the fighters should sit in the same places; only their look changes);
  * a contact sheet, `sheet.png`: the same frames of both renders over magenta, vanilla on top.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SLP2ALPHA = REPO / "tools" / "slp2alpha"


def render(replay: Path, iso: Path, out: Path, extra):
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "slp2alpha", "render", str(replay), "--iso", str(iso), "--out-dir", str(out), *extra]
    r = subprocess.run(cmd, cwd=SLP2ALPHA, capture_output=True, text=True)
    text = (r.stdout + r.stderr).replace("\r", "\n")
    lines = [l for l in text.splitlines() if "Dolphin: frame" not in l]
    if r.returncode:
        print("\n".join(lines[-20:]))
        raise SystemExit(f"render failed for {iso}")
    full = next(out.glob("fullTransparent*.mov"))
    alpha = next(out.glob("alphaMap*.mov"))
    return full, alpha, [l for l in lines if "warn" in l.lower()]


def nframes(ffprobe, path):
    o = subprocess.run([ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True).stdout.strip()
    return int(o)


def alpha_difference(ffmpeg, a, b):
    """Mean luma of |A-B| per frame (0-255; 0 = identical alpha maps): (mean over frames, worst frame)."""
    r = subprocess.run([ffmpeg, "-v", "info", "-i", str(a), "-i", str(b), "-filter_complex",
                        "[0:v]format=gray[x];[1:v]format=gray[y];"
                        "[x][y]blend=all_mode=difference,signalstats,metadata=print",
                        "-f", "null", "-"], capture_output=True, text=True)
    vals = [float(v) for v in re.findall(r"lavfi.signalstats.YAVG=([0-9.]+)", r.stderr)]
    return (sum(vals) / len(vals), max(vals)) if vals else (float("nan"), float("nan"))


def sheet(ffmpeg, v_full, a_full, out, n_frames, frames=5):
    """Same frames of both renders over magenta, hstacked per render, vanilla row above Animelee row."""
    step = max(1, n_frames // (frames + 1))
    rows = []
    for tag, path in (("v", v_full), ("a", a_full)):
        cells = []
        for i in range(frames):
            cell = out / f"cell_{tag}{i}.png"
            subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(path), "-f", "lavfi", "-i", "color=c=0xff00ff:s=640x528",
                            "-filter_complex",
                            f"[0:v]select=eq(n\\,{step * (i + 1)}),scale=640:528,setpts=PTS-STARTPTS[f];[1:v][f]overlay=format=auto:shortest=1",
                            "-frames:v", "1", "-update", "1", str(cell)], check=True)
            cells.append(cell)
        row = out / f"row_{tag}.png"
        cmd = [ffmpeg, "-v", "error", "-y"]
        for c in cells:
            cmd += ["-i", str(c)]
        cmd += ["-filter_complex", f"hstack=inputs={frames}", "-frames:v", "1", "-update", "1", str(row)]
        subprocess.run(cmd, check=True)
        rows.append(row)
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(rows[0]), "-i", str(rows[1]),
                    "-filter_complex", "vstack", "-frames:v", "1", "-update", "1", str(out / "sheet.png")], check=True)
    for p in out.glob("cell_*.png"):
        p.unlink()


def main():
    argv = sys.argv[1:]
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("replay", type=Path)
    ap.add_argument("--vanilla", type=Path, required=True)
    ap.add_argument("--animelee", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("animelee-compare"))
    args = ap.parse_args(argv)

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    results = {}
    for tag, iso in (("vanilla", args.vanilla), ("animelee", args.animelee)):
        print(f"rendering {tag} ...", flush=True)
        results[tag] = render(args.replay.resolve(), iso.resolve(), (args.out / tag).resolve(), extra)
    vf, va, vw = results["vanilla"]
    af, aa, aw = results["animelee"]
    nv, na = nframes(ffprobe, vf), nframes(ffprobe, af)
    print(f"frames: vanilla {nv}, animelee {na}  {'OK' if nv == na else 'MISMATCH'}")
    mean, worst = alpha_difference(ffmpeg, va, aa)
    print(f"alpha map |vanilla - animelee|: mean {mean:.3f}/255, worst frame {worst:.3f}/255")
    for tag, w in (("vanilla", vw), ("animelee", aw)):
        if w:
            print(f"{tag} warnings: {w}")
    sheet(ffmpeg, vf, af, args.out.resolve(), min(nv, na))
    print(f"contact sheet: {args.out.resolve() / 'sheet.png'} (vanilla on top, Animelee below)")


main()
