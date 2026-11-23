#!/usr/bin/env python3
"""The CRT step of slp2video on real renders: Blender's GPU module against librashader-cli, into each output format,
for speed, CPU, GPU memory and accuracy. The numbers behind docs/report-gpu-crt.md.

    python3 research/crt-in-blender/bench.py --out DIR [--replay REPLAY] [--frames FIRST LAST] [--iso ISO]
        [--runtimes blender,wgpu] [--formats mov,mp4] [--accuracy-frames 0,120,239] [--skip-speed]

1. `slp2alpha render` records the replay's frames twice at the console's native 640x480 (--raw-resolution, as
   `slp2video --crt` records regular Melee): the fighters alone, transparent; and the whole game, opaque, the
   hardest picture for the encoders. Both are kept in DIR and reused.
2. Speed: slp2video.crt_pass (the squeeze to 584x480, then the CRT at 3504x2880 and the encoder) on each input,
   with each runtime and format. A transparent mp4 also writes its matte. Wall time, CPU seconds of every child
   process, frames per second, file size, and on NVIDIA the peak video memory in use (nvidia-smi).
3. Accuracy: the frames listed, squeezed as crt_pass squeezes them, drawn with each mask by Blender and by the
   first librashader runtime, as PNG; the mean and largest difference, the share of pixels that differ.

Results go to DIR/results.json and DIR/results.md. Default replay: the render tests' DishonestMuddyCoyote.slp.
"""
from __future__ import annotations

import argparse
import json
import operator
import os
import resource
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
for p in (REPO / "tools" / "slp2video", REPO / "tools" / "crt", REPO / "tools" / "slp2alpha"):
    sys.path.insert(0, str(p))
import render_video as rv  # noqa: E402
import slp2video  # noqa: E402
from slp2alpha import locate  # noqa: E402

INPUTS = {"fighters": ["--characters-only"], "game": ["--keep-background"]}


def children_cpu() -> float:
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


class GpuMemory:
    """The most video memory nvidia-smi sees in use while it runs, in MiB (None without nvidia-smi)."""

    def __init__(self):
        self.peak, self.proc = None, None
        if shutil.which("nvidia-smi"):
            self.proc = subprocess.Popen(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
                                          "-lms", "250"], stdout=subprocess.PIPE, encoding="utf-8")
            self.thread = threading.Thread(target=self._read, daemon=True)
            self.thread.start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                v = int(line.strip().split()[0])
            except (ValueError, IndexError):
                continue
            self.peak = v if self.peak is None else max(self.peak, v)

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait()
            self.thread.join(timeout=2)
        return self.peak


def record(replay: Path, first: int, last: int, out: Path, iso: str | None) -> dict:
    found = {}
    for name, flags in INPUTS.items():
        folder = out / f"input-{name}"
        videos = sorted(folder.glob("full*.mov")) if folder.exists() else []
        if not videos:
            folder.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, "-m", "slp2alpha", "render", str(replay), "--out-dir", str(folder), "--scale", "1",
                   "--raw-resolution", "--format", "mov", "--start-frame", str(first), "--end-frame", str(last), *flags]
            if iso:
                cmd += ["--iso", iso]
            subprocess.run(cmd, cwd=REPO / "tools" / "slp2alpha", check=True, env=locate.utf8_child_env())
            videos = sorted(folder.glob("full*.mov"))
        found[name] = videos[0]
    return found


def crt_args(runtime: str, fmt: str, mask: str = "grille") -> SimpleNamespace:
    return SimpleNamespace(crt_mask=mask, crt_scale=None, crt_triads_per_pixel=None, crt_params=None, format=fmt,
                           crt_runtime=runtime, crt_jobs=4)


def speed(inputs: dict, runtimes, formats, out: Path, ffmpeg: str, ffprobe: str, librashader, blender) -> list:
    rows = []
    for name, video in inputs.items():
        info = slp2video.video_info(ffprobe, video)
        transparent = name == "fighters"
        for fmt in formats:
            for runtime in runtimes:
                target = out / "speed" / f"{name}-{runtime}.{fmt}"
                work = out / "work" / f"{name}-{runtime}-{fmt}"
                shutil.rmtree(work, ignore_errors=True)
                target.parent.mkdir(parents=True, exist_ok=True)
                plan = SimpleNamespace(transparent=transparent)
                cpu0, t0, gpu = children_cpu(), time.monotonic(), GpuMemory()
                try:
                    slp2video.crt_pass(crt_args(runtime, fmt), plan, video, target, work, ffmpeg, ffprobe,
                                       librashader, blender)
                    error = None
                except Exception as e:  # noqa: BLE001 - recorded in the results
                    error = str(e)[-300:]
                wall, cpu, peak = time.monotonic() - t0, children_cpu() - cpu0, gpu.stop()
                files = [target] + ([rv.matte_path(target)] if fmt == "mp4" and transparent else [])
                size = sum(f.stat().st_size for f in files if f.exists())
                frames = slp2video.video_info(ffprobe, target)["frames"] if target.exists() else 0
                row = dict(input=name, runtime=runtime, format=fmt, frames=frames, expected=info["frames"],
                           seconds=round(wall, 1), fps=round(frames / wall, 2) if wall else 0,
                           cpu_seconds=round(cpu, 1), cpu_per_frame=round(cpu / max(frames, 1), 2),
                           mb=round(size / 1e6), gpu_mib=peak, matte=len(files) > 1, error=error,
                           encoder=encoder_of(ffprobe, target))
                print(json.dumps(row), flush=True)
                rows.append(row)
                for f in files:
                    f.unlink(missing_ok=True)   # 3504x2880 ProRes is about 23 GB a minute
    return rows


def encoder_of(ffprobe: str, video: Path) -> str | None:
    if not video.exists():
        return None
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,profile,pix_fmt", "-of", "csv=p=0", str(video)],
                         capture_output=True, encoding="utf-8").stdout.strip()
    return out


def mean_diff(a: bytes, b: bytes) -> tuple:
    d = list(map(abs, map(operator.sub, a, b)))
    return sum(d) / len(d), max(d), sum(1 for x in d if x) / len(d)


def accuracy(inputs: dict, frames, out: Path, ffmpeg: str, ffprobe: str, librashader, blender) -> list:
    rows = []
    lib_runtime = rv.runtime_candidates(rv.runtimes_of(librashader))[0]
    for name, video in inputs.items():
        info = slp2video.video_info(ffprobe, video)
        lines = info["height"]
        width = slp2video.crt_width(lines)
        squeeze = (f"format=gbrap16le,premultiply=inplace=1,scale={width}:{lines}:flags=lanczos+accurate_rnd+"
                   f"full_chroma_int,unpremultiply=inplace=1,format=bgra" if name == "fighters" else
                   f"format=gbrp16le,scale={width}:{lines}:flags=lanczos+accurate_rnd+full_chroma_int,format=bgr0")
        for n in frames:
            clip = out / "accuracy" / f"{name}-{n}.nut"
            clip.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(video), "-vf", f"select=eq(n\\,{n}),{squeeze}",
                            "-frames:v", "1", "-c:v", "ffv1", str(clip)], check=True)
            for mask in sorted(rv.MASKS):
                settings = slp2video.crt_settings(crt_args("auto", "mov", mask), lines)
                pngs = {}
                for runtime, lib, bl in (("blender", None, blender), (lib_runtime, librashader, None)):
                    folder = out / "accuracy" / f"{name}-{n}-{mask}-{runtime}"
                    shutil.rmtree(folder, ignore_errors=True)
                    rv.render(clip, folder, settings, ffmpeg=ffmpeg, librashader=lib, blender=bl, runtime=runtime,
                              input_size=(width, lines), rate="60", codec="png", work=out / "work" / "acc")
                    pngs[runtime] = subprocess.run([ffmpeg, "-v", "error", "-i", str(folder / "000001.png"), "-f",
                                                    "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True,
                                                   check=True).stdout
                    shutil.rmtree(folder, ignore_errors=True)
                mean, worst, share = mean_diff(pngs["blender"], pngs[lib_runtime])
                row = dict(input=name, frame=n, mask=mask, against=lib_runtime, mean=round(mean, 4), max=worst,
                           differ=round(share * 100, 3))
                print(json.dumps(row), flush=True)
                rows.append(row)
    return rows


def markdown(doc: dict) -> str:
    out = [f"# CRT benchmark: {doc['machine']}", "", f"{doc['when']}; {doc['frames']} frames of `{doc['replay']}`", ""]
    if doc.get("speed"):
        out += ["| Input | Runtime | Format | Encoder | Frames | Seconds | Frames/s | CPU s/frame | MB | GPU MiB |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for r in doc["speed"]:
            out.append(f"| {r['input']} | {r['runtime']} | {r['format']}{' + matte' if r['matte'] else ''} | "
                       f"{r['encoder']} | {r['frames']}/{r['expected']} | {r['seconds']} | {r['fps']} | "
                       f"{r['cpu_per_frame']} | {r['mb']} | {r['gpu_mib'] or '-'} |"
                       + (f" error: {r['error']}" if r["error"] else ""))
    if doc.get("accuracy"):
        out += ["", "| Input | Frame | Mask | Against | Mean /255 | Max | Pixels differing % |", "|---|---|---|---|---|---|---|"]
        for r in doc["accuracy"]:
            out.append(f"| {r['input']} | {r['frame']} | {r['mask']} | {r['against']} | {r['mean']} | {r['max']} | "
                       f"{r['differ']} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--replay", default=str(locate.cache_root() / "test-replays" / "DishonestMuddyCoyote.slp"))
    ap.add_argument("--frames", nargs=2, type=int, default=(1500, 1739))
    ap.add_argument("--iso")
    ap.add_argument("--runtimes", default=None, help="default: blender and this platform's first librashader runtime")
    ap.add_argument("--formats", default="mov,mp4")
    ap.add_argument("--accuracy-frames", default="0,120,239")
    ap.add_argument("--skip-speed", action="store_true")
    ap.add_argument("--skip-accuracy", action="store_true")
    a = ap.parse_args()
    out = Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg, ffprobe = locate.find_ffmpeg(), locate.find_ffmpeg(name="ffprobe")
    librashader, blender = rv.find_librashader(), rv.find_blender()
    lib_runtime = rv.runtime_candidates(rv.runtimes_of(librashader))[0]
    runtimes = a.runtimes.split(",") if a.runtimes else ["blender", lib_runtime]
    inputs = record(Path(a.replay), a.frames[0], a.frames[1], out, a.iso)
    doc = dict(machine=os.uname().nodename + " " + sys.platform, when=time.strftime("%Y-%m-%d %H:%M"),
               replay=Path(a.replay).name, frames=f"{a.frames[0]}-{a.frames[1]}", ffmpeg=ffmpeg,
               ffmpeg_version=subprocess.run([ffmpeg, "-version"], capture_output=True, encoding="utf-8").stdout.split("\n")[0],
               blender=blender, inputs={k: str(v) for k, v in inputs.items()})
    if not a.skip_speed:
        doc["speed"] = speed(inputs, runtimes, a.formats.split(","), out, ffmpeg, ffprobe, librashader, blender)
    if not a.skip_accuracy:
        doc["accuracy"] = accuracy(inputs, [int(f) for f in a.accuracy_frames.split(",")], out, ffmpeg, ffprobe,
                                   librashader, blender)
    (out / "results.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    (out / "results.md").write_text(markdown(doc), encoding="utf-8")
    print(markdown(doc))
    shutil.rmtree(out / "work", ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
