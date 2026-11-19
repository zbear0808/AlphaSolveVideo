#!/usr/bin/env python3
"""Render-test the replays in replays.json (public replays from Slippi Lab) and check the results.

Usage (from the repo root):
    python3 tools/render-tests/run.py [--only TEXT ...] [--out DIR] [--keep-videos] [--quick] [--force]

Every replay is rendered with each argument list in its "renders" entry
(`python3 -m slp2alpha render REPLAY --keep ARGS...`), then checked:
- the render succeeds and prints no warnings;
- the transparent video has exactly one frame per game frame;
- across the whole recording, the solver paired each black frame with the white frame of the same
  game frame, not a neighbouring one (skipped with --quick);
- how much of each frame is transparent (sampled once a second).
A contact sheet (8 frames over magenta, and their alpha) is written for a visual check.
Results go to OUT/summary.md; finished renders are skipped on the next run unless --force.
Renders in a format this ffmpeg has no encoder for (e.g. --format hevc off macOS) are skipped.
The large files (videos, recordings) are deleted after checking unless --keep-videos.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SLP2ALPHA = REPO / "tools" / "slp2alpha"
sys.path.insert(0, str(SLP2ALPHA))
from slp2alpha import camera, locate, slp, solve, validate  # noqa: E402

BLOCK_PAIRS = 300  # pair check granularity: 5 s of gameplay
NO_SIGNAL = 0.02   # mean pair violation below which a block tells nothing (nothing moved)


def cache_dir() -> Path:
    return locate.cache_root() / "test-replays"


def fetch(source: str, name: str) -> Path:
    dest = cache_dir() / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = source.format(file=name)
    print(f"downloading {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaSolveVideo render tests"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except OSError:  # e.g. Python without CA certificates: fall back to curl
        data = subprocess.run(["curl", "-sfL", "-A", "AlphaSolveVideo render tests", "--max-time", "60", url],
                              capture_output=True, check=True).stdout
    if not data.startswith(b"{U\x03raw[$U#l"):
        raise RuntimeError(f"{url} did not return a Slippi replay")
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    time.sleep(1)  # be gentle with the site
    return dest


def slug(args: List[str]) -> str:
    return "_".join((Path(a).name if "/" in a else a).lstrip("-") for a in args) or "default"


def flag_value(args: List[str], flag: str) -> Optional[int]:
    return int(args[args.index(flag) + 1]) if flag in args else None


def ffmpeg_values(ffmpeg: str, inputs: List[str], graph: str, files: Dict[str, Path]) -> Dict[str, List[float]]:
    """Run a filter graph whose chains print YAVG to the given metadata files; return the values per file.

    The graph names the files without a folder, and ffmpeg runs in the files' folder: a path inside a filter
    graph would need its colons escaped, and a Windows path (C:\\...) always has one. Inputs must be absolute.
    """
    folder = next(iter(files.values())).parent
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[o]",
                    "-fps_mode", "passthrough", "-f", "null", "-"], check=True, cwd=folder)
    out = {}
    for key, path in files.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        out[key] = [float(v) for v in re.findall(r"YAVG=([0-9.]+)", text)]
    return out


def probe(ffprobe: str, video: Path) -> dict:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=codec_name,pix_fmt,width,height,nb_read_packets,r_frame_rate", "-of", "json",
                          str(video)], capture_output=True, encoding="utf-8", errors="replace", check=True).stdout
    return json.loads(out)["streams"][0]


def camera_check(files: List[Path], work: Optional[Path]) -> dict:
    """For --export-camera renders: the export's own checks (tools/camera-export/validate_camera.py check)."""
    if not files or not files[0].exists():
        return {"problems": ["no camera export was written"]}
    sys.path.insert(0, str(REPO / "tools" / "camera-export"))
    import validate_camera

    doc = camera.load(files[0])
    problems = validate_camera.check_export(doc)
    raw = work / "camera.csv" if work else None
    if raw and raw.exists():
        rows = [r for r in camera.read_csv(raw) if doc["frames"]["first"] <= r.frame <= doc["frames"]["last"]]
        problems += camera.check_rows(rows, doc["stage"]["id"], doc["samples"][0]["mode"] == camera.FIXED)
    return {"file": files[0].name, "samples": len(doc["samples"]), "video": doc["frames"]["video"],
            "problems": problems}


def decoder_args(video: Path) -> List[str]:
    # FFmpeg's built-in VP9 decoder ignores alpha; libvpx reads it
    return ["-c:v", "libvpx-vp9"] if video.suffix == ".webm" else []


def alpha_stats(ffmpeg: str, video: Path, tmp: Path, every: int = 60) -> dict:
    """Fraction of fully transparent and of opaque pixels, sampled every `every` frames."""
    t, o = tmp / "transparent.txt", tmp / "opaque.txt"
    graph = (f"[0:v]select=not(mod(n\\,{every})),format=rgba,alphaextract,split[a][b];"
             f"[a]lut=y='if(eq(val\\,0)\\,255\\,0)',signalstats,"
             f"metadata=print:key=lavfi.signalstats.YAVG:file={t.name},nullsink;"
             f"[b]lut=y='if(gte(val\\,250)\\,255\\,0)',signalstats,"
             f"metadata=print:key=lavfi.signalstats.YAVG:file={o.name}[o]")
    v = ffmpeg_values(ffmpeg, decoder_args(video) + ["-i", str(Path(video).resolve())], graph, {"t": t, "o": o})
    tr = [x / 255 for x in v["t"]]
    op = [x / 255 for x in v["o"]]
    if not tr:
        return {}
    srt = sorted(tr)
    return {"samples": len(tr), "transparent_median": round(statistics.median(tr), 3),
            "transparent_p5": round(srt[len(srt) // 20], 3), "transparent_min": round(srt[0], 3),
            "opaque_median": round(statistics.median(op), 3) if op else None}


def contact_sheet(ffmpeg: str, video: Path, frames: int, width: int, height: int, png: Path,
                  alpha: bool = True) -> None:
    """Eight frames over magenta with their alpha below; without alpha (--keep-background), the frames only."""
    picks = [int((i + 0.5) * frames / 8) for i in range(8)]
    sel = "+".join(f"eq(n\\,{k})" for k in picks)
    h = round(320 * height / width / 2) * 2
    if alpha:
        graph = (f"[0:v]select='{sel}',setpts=N/(60*TB),scale=320:{h},format=rgba,split[f][a];"
                 f"color=c=magenta:s=320x{h}:r=60[bg];[bg][f]overlay=format=auto:shortest=1,tile=4x2[top];"
                 f"[a]alphaextract,format=gray,tile=4x2[bot];[top]format=rgb24[t2];[bot]format=rgb24[b2];"
                 f"[t2][b2]vstack[o]")
    else:
        graph = f"[0:v]select='{sel}',setpts=N/(60*TB),scale=320:{h},tile=4x2,format=rgb24[o]"
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", *decoder_args(video), "-i", str(video),
                    "-filter_complex", graph, "-map", "[o]", "-frames:v", "1", str(png)], check=True)


def pair_check(ffmpeg: str, recording: Path, pairs: int, tmp: Path) -> dict:
    """Over the whole recording: is the chosen pairing better than the other one in every 5 s block?"""
    pairing = validate.detect_pairing(ffmpeg, str(recording))
    s = [validate.select_exprs(pairing.first_color, off) for off in (0, 1)]
    lut = f"lut=y='if(gt(val\\,{validate.VIOLATION_LEVEL})\\,255\\,0)'"
    files = {"v0": tmp / "v0.txt", "v1": tmp / "v1.txt", "luma": tmp / "luma.txt"}
    chains = []
    for off in (0, 1):
        chains.append(f"[a{off}]select={s[off]['black']},setpts=N/TB/60[k{off}];"
                      f"[b{off}]select={s[off]['white']},setpts=N/TB/60[w{off}];"
                      f"[k{off}][w{off}]blend=all_mode=subtract:shortest=1,format=gray,{lut},signalstats,"
                      f"metadata=print:key=lavfi.signalstats.YAVG:file={files[f'v{off}'].name},nullsink;")
    graph = ("[0:v]format=gbrp,split=5[a0][b0][a1][b1][l];" + "".join(chains) +
             f"[l]scale=iw/4:ih/4,format=gray,signalstats,metadata=print:key=lavfi.signalstats.YAVG:"
             f"file={files['luma'].name}[o]")
    v = ffmpeg_values(ffmpeg, ["-i", str(Path(recording).resolve())], graph, files)
    chosen, other = v[f"v{pairing.offset}"][:pairs], v[f"v{1 - pairing.offset}"][:pairs]
    bad = []
    for start in range(0, min(len(chosen), len(other)), BLOCK_PAIRS):
        c = statistics.mean(chosen[start:start + BLOCK_PAIRS])
        o = statistics.mean(other[start:start + BLOCK_PAIRS])
        if c > NO_SIGNAL and c > 0.5 * o:
            bad.append({"from_s": round(start / 60, 1), "chosen": round(c, 3), "other": round(o, 3)})
    luma = v["luma"][: 2 * pairs]
    turns = [(luma[i] - luma[i - 1]) * (luma[i - 1] - luma[i - 2]) < 0 for i in range(2, len(luma))]
    return {"pairing": f"{pairing.first_color}/{pairing.offset}",
            "pairs_checked": min(len(chosen), len(other)), "bad_blocks": bad,
            "alternation": round(sum(turns) / len(turns), 4) if turns else None}


def run_one(entry: dict, args: List[str], replay: Path, out_root: Path, opts) -> Optional[dict]:
    out_dir = out_root / replay.stem / slug(args)
    result_file = out_dir / "result.json"
    if opts.recheck:  # re-evaluate saved results with the current checks; render nothing
        if not result_file.exists():
            return None
        res = json.loads(result_file.read_text(encoding="utf-8"))
        res["problems"] = problems(res)
        res["status"] = status(res)
        result_file.write_text(json.dumps(res, indent=2), encoding="utf-8")
        return res
    if result_file.exists() and not opts.force:
        return json.loads(result_file.read_text(encoding="utf-8"))
    info = slp.read_replay(replay)
    first, last = slp.clip_range(info, flag_value(args, "--start-frame"), flag_value(args, "--end-frame"))
    expected = last - first + 1
    res = {"replay": replay.name, "label": entry["label"], "args": args, "expected_frames": expected,
           "game_seconds": round(expected / 60, 1), "mid_match": first > slp.FIRST_FRAME + 1,
           "to_end": last == info.last_frame}
    print(f"\n== {replay.name} [{' '.join(args) or 'default'}]: {entry['label']}", flush=True)
    fmt = args[args.index("--format") + 1] if "--format" in args else solve.DEFAULT_FORMAT
    missing = solve.missing_encoder(locate.find_ffmpeg(), fmt)
    if missing:  # e.g. --format hevc off macOS; not saved, so it runs once this ffmpeg can
        res.update(status="SKIP", returncode=None, problems=[f"skipped: this ffmpeg has no {missing} encoder"])
        print(f"   SKIP: this ffmpeg has no {missing} encoder")
        return res
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    t0 = time.monotonic()
    cli_args = [a.replace("{tests}", str(HERE)) for a in args]  # {tests}: this folder, for files kept next to run.py
    p = subprocess.run([sys.executable, "-m", "slp2alpha", "render", str(replay), "--out-dir", str(out_dir),
                        "--keep", *cli_args], cwd=SLP2ALPHA, capture_output=True, encoding="utf-8",
                       errors="replace", env=locate.utf8_child_env())
    res["seconds"] = round(time.monotonic() - t0, 1)
    text = (p.stdout + "\n" + p.stderr).replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("Dolphin: frame")]
    (out_dir / "render.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    res["returncode"] = p.returncode
    res["messages"] = [ln.strip() for ln in lines if re.search(r"\b(warning|error|note):", ln)]
    m = re.search(r"([0-9.]+)x real time", text)
    res["realtime"] = float(m.group(1)) if m else None
    work = re.search(r"work folder kept: (.+)", text)
    work = Path(work.group(1).strip()) if work else None
    printed = [Path(ln.strip()) for ln in lines if ln.strip().startswith(str(out_dir))]
    videos = [p for p in printed if p.suffix != ".json"]
    camera_files = [p for p in printed if p.suffix == ".json"]

    ff, fp = locate.find_ffmpeg(), locate.find_ffmpeg(name="ffprobe")
    plain = "--keep-background" in args   # recorded without the flicker: one opaque video, nothing to pair
    tmp = Path(tempfile.mkdtemp(prefix="render-test-"))
    try:
        if videos and videos[0].exists():
            pr = probe(fp, videos[0])
            res["output"] = {"file": videos[0].name, "codec": pr.get("codec_name"), "pix_fmt": pr.get("pix_fmt"),
                             "size": f"{pr.get('width')}x{pr.get('height')}",
                             "frames": int(pr.get("nb_read_packets", 0)),
                             "rate": pr.get("r_frame_rate"),
                             "bytes": videos[0].stat().st_size}
            if len(videos) > 1 and videos[1].exists():
                alpha_probe = probe(fp, videos[1])
                res["output"]["alpha_map_frames"] = int(alpha_probe.get("nb_read_packets", 0))
                res["output"]["alpha_map_rate"] = alpha_probe.get("r_frame_rate")
            if not plain:
                res["alpha"] = alpha_stats(ff, videos[0], tmp)
            sheet = out_dir / "sheet.png"
            contact_sheet(ff, videos[0], res["output"]["frames"], int(pr["width"]), int(pr["height"]), sheet,
                          alpha=not plain)
            res["sheet"] = str(sheet)
        if "--export-camera" in args:
            res["camera"] = camera_check(camera_files, work)
        recordings = sorted(work.rglob("*.mkv")) + sorted(work.rglob("*.avi")) if work and work.exists() else []
        if recordings and not opts.quick and not plain:
            res["pairs"] = pair_check(ff, recordings[0], expected, tmp)
    except subprocess.CalledProcessError as e:
        res["check_error"] = f"{' '.join(map(str, e.cmd[:3]))}... exited {e.returncode}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if work and work.exists():
            shutil.rmtree(work, ignore_errors=True)
        if not opts.keep_videos:
            for v in videos + camera_files:
                if v.exists():
                    v.unlink()

    res["problems"] = problems(res)
    res["status"] = status(res)
    result_file.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"   {res['status']}: {res.get('realtime')}x real time; " + ("; ".join(res["problems"]) or "no problems"))
    return res


def status(res: dict) -> str:
    if res["returncode"] != 0 or "output" not in res:
        return "FAIL"
    return "CHECK" if res["problems"] else "PASS"


def problems(res: dict) -> List[str]:
    out = [m for m in res.get("messages", []) if "note:" not in m]
    o = res.get("output")
    if o:
        # The first game frame of a match (-122, during "Ready") never reaches the recording, so one frame
        # less is expected; replays that end in a quit-out can also fill the last frame. A clip that starts
        # later has exactly the frames asked for.
        lo, hi = res["expected_frames"] - 1, res["expected_frames"]
        if res.get("mid_match"):
            lo = hi
        if "--keep-background" in res["args"] and res.get("to_end"):
            # without the flicker the game's last picture comes after the playback has ended, unrecorded
            lo -= 1
        if o.get("codec") == "gif":  # GIF timing can't do 60 fps: the solver writes 50 fps
            lo, hi = (round(n * 50 / (60000 / 1001)) for n in (lo, hi))
            lo -= 1
        if not lo <= o["frames"] <= hi:
            out.append(f"{o['frames']} frames, expected {lo}..{hi}")
        if "alpha_map_frames" in o and o["alpha_map_frames"] != o["frames"]:
            out.append(f"alpha map has {o['alpha_map_frames']} frames, transparent video {o['frames']}")
        if "--export-camera" in res["args"]:
            rates = {o.get("rate"), o.get("alpha_map_rate", o.get("rate"))}
            if rates != {camera.OUTPUT_RATE}:
                out.append(f"camera export videos are labelled {sorted(r for r in rates if r)} fps, "
                           f"not {camera.OUTPUT_RATE}")
    cam = res.get("camera")
    if cam:
        out += [f"camera: {p}" for p in cam["problems"]]
        if o and "samples" in cam and cam["samples"] not in (o["frames"], o["frames"] - 1):
            out.append(f"camera: {cam['samples']} samples for {o['frames']} video frames")
    a = res.get("alpha") or {}
    if a:
        floor = 0.8 if "--characters-only" in res["args"] else 0.15
        if a["transparent_median"] < floor:
            out.append(f"only {a['transparent_median']:.0%} of a typical frame is transparent (expected > {floor:.0%})")
    pc = res.get("pairs")
    if pc:
        for b in pc["bad_blocks"]:
            out.append(f"pairing looks wrong from {b['from_s']} s (violations {b['chosen']} vs {b['other']})")
        if pc["alternation"] is not None and pc["alternation"] < 0.97:
            out.append(f"background alternates on only {pc['alternation']:.1%} of the fields")
    if res.get("check_error"):
        out.append(f"check failed: {res['check_error']}")
    return out


def summary(results: List[dict], out_root: Path) -> Path:
    rows = ["| Status | Replay | Options | Gameplay | Speed | Frames | Transparent (median / p5) | Pairing | Problems |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        o, a, pc = r.get("output", {}), r.get("alpha", {}), r.get("pairs", {})
        frames = f"{o.get('frames', '-')}/{r['expected_frames']}"
        alpha = f"{a['transparent_median']:.0%} / {a['transparent_p5']:.0%}" if a else "-"
        pairing = (f"{pc['pairing']}, {len(pc['bad_blocks'])} bad blocks, alt {pc['alternation']}" if pc else "-")
        rows.append(f"| {r['status']} | {r['label']} | {' '.join(r['args']) or 'default'} | {r['game_seconds']} s | "
                    f"{r.get('realtime') or '-'}x | {frames} | {alpha} | {pairing} | "
                    f"{'; '.join(r['problems']) or '-'} |")
    path = out_root / "summary.md"
    path.write_text("# Render tests\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", nargs="+", help="only replays whose file name or label contains one of these")
    ap.add_argument("--out", default=str(cache_dir().parent / "render-test-results"))
    ap.add_argument("--keep-videos", action="store_true")
    ap.add_argument("--quick", action="store_true", help="skip the whole-recording pairing check")
    ap.add_argument("--force", action="store_true", help="redo renders that already have results")
    ap.add_argument("--recheck", action="store_true",
                    help="only re-evaluate saved results with the current checks (renders nothing)")
    ap.add_argument("--fetch-only", action="store_true",
                    help=f"only download the replays (into {cache_dir()}) and list them")
    ap.add_argument("--iso", help="Melee NTSC 1.02 ISO (default: the one set in the Slippi Launcher)")
    opts = ap.parse_args()
    if opts.iso:  # the renders run slp2alpha, which takes it from here
        os.environ["SLP2ALPHA_ISO"] = str(Path(opts.iso).expanduser().resolve())

    manifest = json.loads((HERE / "replays.json").read_text(encoding="utf-8"))
    if opts.fetch_only:
        for entry in manifest["replays"]:
            if not opts.only or any(t.lower() in (entry["file"] + entry["label"]).lower() for t in opts.only):
                print(fetch(manifest["source"], entry["file"]))
        return 0
    out_root = Path(opts.out).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    results = []
    for entry in manifest["replays"]:
        if opts.only and not any(t.lower() in (entry["file"] + entry["label"]).lower() for t in opts.only):
            continue
        replay = fetch(manifest["source"], entry["file"])
        for args in entry["renders"]:
            res = run_one(entry, args, replay, out_root, opts)
            if res is not None:
                results.append(res)
    path = summary(results, out_root)
    counts = {s: sum(r["status"] == s for r in results) for s in ("PASS", "CHECK", "FAIL", "SKIP")}
    skipped = f", {counts['SKIP']} skipped" if counts["SKIP"] else ""
    print(f"\n{counts['PASS']} passed, {counts['CHECK']} to check, {counts['FAIL']} failed{skipped}. Summary: {path}")
    return 0 if not counts["FAIL"] and not counts["CHECK"] else 1


if __name__ == "__main__":
    sys.exit(main())
