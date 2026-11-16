"""Command line: python3 -m slp2alpha {info,render,bench} ..."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import config, gecko, locate, runner, slp, solve, stages, validate


def cmd_info(args) -> int:
    for path in args.replays:
        r = slp.read_replay(path)
        ok = "supported" if stages.is_supported(r.stage_id) else "NOT supported (no background codes)"
        print(f"{Path(path).name}: replay v{r.version}, {stages.stage_name(r.stage_id)} (id {r.stage_id}, {ok}), "
              f"frames {r.first_frame}..{r.last_frame} ({r.game_frames / 60:.1f} s)")
    return 0


def _sample_cpu(pid: int, delay: float, out: dict) -> None:
    """Best-effort snapshot of per-thread CPU use and scheduling priority (App Nap shows as low priority)."""
    time.sleep(delay)
    try:
        rows = subprocess.run(["ps", "-M", "-p", str(pid)], capture_output=True, text=True, timeout=10).stdout
        threads = []
        for line in rows.splitlines()[1:]:
            parts = line.split()
            # thread rows: [USER PID TT] %CPU STAT PRI STIME UTIME [COMMAND]; take the %CPU/STAT/PRI triple
            for i in range(len(parts) - 2):
                try:
                    cpu = float(parts[i])
                except ValueError:
                    continue
                if parts[i + 1][:1].isalpha() and parts[i + 2][:1].isdigit():
                    threads.append((cpu, parts[i + 2]))
                    break
        threads.sort(reverse=True)
        out["busiest_threads"] = [f"{c:.0f}% (pri {p})" for c, p in threads[:4]]
        out["process_cpu"] = subprocess.run(["ps", "-o", "%cpu=", "-p", str(pid)], capture_output=True,
                                            text=True, timeout=10).stdout.strip()
    except Exception as e:  # sampling is best effort
        out["error"] = str(e)


def cmd_bench(args) -> int:
    """M0: measure unthrottled emulation speed of a Dolphin build on this machine."""
    replay = slp.read_replay(args.replay)
    iso = locate.find_iso(args.iso)
    codes = gecko.load_codes(locate.RESOURCES / "Required Codes.txt")
    enabled = []
    if args.flicker:
        enabled = config.FLICKER_CODES + stages.BACKGROUND_CODES.get(replay.stage_id, [])
    enabled += args.code

    work = Path(tempfile.mkdtemp(prefix="slp2alpha-bench-"))
    user, logs = work / "user", work / "logs"
    engine = runner.engine_of(Path(args.dolphin))
    dump = config.dump_dir_for(engine, user, work / "dump")
    config.write_user_dir(user, codes, enabled=enabled, scale=args.scale, record=args.record,
                          fastmem=args.fastmem, video_backend=args.backend, debug_logging=args.debug,
                          engine=engine, cpu_thread=args.dual_core)
    comm = work / "comm.json"
    stop_at = min(replay.last_frame, replay.first_frame + int(args.max_game_seconds * 60))
    config.write_comm(comm, args.replay, end_frame=stop_at + 1)

    cpu: dict = {}
    load_before = os.getloadavg()

    def on_start(proc):
        threading.Thread(target=_sample_cpu, args=(proc.pid, args.cpu_sample_after, cpu), daemon=True).start()

    print(f"Benchmark: {Path(args.dolphin).name} ({engine}) | replay {Path(args.replay).name} "
          f"({stages.stage_name(replay.stage_id)}, playing to frame {stop_at}) | "
          f"record={args.record} flicker={args.flicker} scale={args.scale}x | work dir {work}")
    res = runner.run_dolphin(Path(args.dolphin), iso, comm, user, dump, logs, stop_at_frame=stop_at,
                             max_seconds=args.time_limit, boot_timeout=args.boot_timeout, on_start=on_start,
                             extra_args=args.extra_arg)
    fields_per_frame = 2 if args.flicker else 1
    report = {
        "dolphin": str(args.dolphin),
        "engine": engine,
        "reason": res.reason,
        "returncode": res.returncode,
        "boot_seconds": round(res.boot_seconds, 1) if res.boot_seconds else None,
        "frames": f"{res.first_frame}..{res.last_frame}",
        "game_fps": round(res.game_fps, 1) if res.game_fps else None,
        "emulation_speed_S": round(res.game_fps * fields_per_frame / 60, 2) if res.game_fps else None,
        "load_avg_before": [round(x, 1) for x in load_before],
        "cpu_sample": cpu,
    }
    dumps = sorted(p for ext in ("*.avi", "*.mkv") for p in dump.rglob(ext))
    if dumps:
        ffprobe = locate.find_ffmpeg(name="ffprobe")
        probe = subprocess.run([ffprobe, "-v", "error", "-count_packets", "-select_streams", "v:0",
                                "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_packets",
                                "-of", "json", str(dumps[0])], capture_output=True, text=True)
        try:
            report["dump"] = json.loads(probe.stdout)["streams"][0]
        except (ValueError, KeyError, IndexError):
            report["dump"] = probe.stderr.strip()[-300:]
        report["dump"]["bytes"] = dumps[0].stat().st_size
    print(json.dumps(report, indent=2))
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if res.reason == "finished" else 1


def _progress_printer(label: str):
    """Single-line progress for a render: frames done, emulation speed and ETA."""
    state = {"t0": None, "f0": None, "shown": 0.0}

    def show(current: int, target) -> None:
        now = time.monotonic()
        if state["t0"] is None:
            state["t0"], state["f0"] = now, current
        if now - state["shown"] < 1.0 and (target is None or current < target):
            return
        state["shown"] = now
        done = current - state["f0"]
        elapsed = now - state["t0"]
        fps = done / elapsed if elapsed > 0.5 else 0.0
        line = f"\r  {label}: frame {current}"
        if target is not None:
            total = target - state["f0"]
            line += f"/{target} ({100 * done / total:.0f}%)" if total > 0 else f"/{target}"
            if fps > 0:
                eta = (target - current) / fps
                line += f"  {fps:.0f} game fps ({fps / 60:.2f}x real time)  ETA {int(eta // 60)}:{int(eta % 60):02d}"
        sys.stderr.write(line + "   ")
        sys.stderr.flush()

    return show


def _render_one(args, replay_path: Path, dolphin: Path, engine: str, iso: Path, ffmpeg: str, ffprobe: str,
                codes) -> bool:
    replay = slp.read_replay(replay_path)
    stage = stages.stage_name(replay.stage_id)
    if not stages.is_supported(replay.stage_id):
        print(f"{replay_path.name}: skipped, {stage} has no background-removal codes "
              f"(supported: {', '.join(stages.supported_stage_names())})", file=sys.stderr)
        return False

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else replay_path.resolve().parent
    name = replay_path.stem
    work = Path(tempfile.mkdtemp(prefix="slp2alpha-"))
    user, logs = work / "user", work / "logs"
    dump = config.dump_dir_for(engine, user, work / "dump")
    enabled = config.FLICKER_CODES + stages.BACKGROUND_CODES[replay.stage_id]
    config.write_user_dir(user, codes, enabled=enabled, scale=args.scale, engine=engine,
                          cpu_thread=args.dual_core, debug_logging=args.debug)
    comm = work / "comm.json"
    # Dolphin records strictly between startFrame and endFrame, so this covers the whole replay.
    config.write_comm(comm, replay_path, end_frame=replay.last_frame + 1)

    print(f"{replay_path.name}: {stage}, {replay.game_frames / 60:.1f} s of gameplay -> {out_dir}")
    t_start = time.monotonic()
    res = runner.run_dolphin(dolphin, iso, comm, user, dump, logs, stop_at_frame=replay.last_frame,
                             boot_timeout=args.boot_timeout, on_progress=_progress_printer("Dolphin"))
    sys.stderr.write("\n")
    t_rendered = time.monotonic()
    dumps = sorted(p for ext in ("*.mkv", "*.avi") for p in dump.rglob(ext))
    if res.reason != "finished" or not dumps:
        why = res.reason if res.reason != "finished" else "no recording was written"
        print(f"  Dolphin did not finish ({why}, exit code {res.returncode}). Logs kept in {logs}", file=sys.stderr)
        return False
    if len(dumps) > 1:
        print(f"  warning: Dolphin split the recording into {len(dumps)} files; using {dumps[0].name}",
              file=sys.stderr)
    video = str(dumps[0])

    report = validate.quick_check(ffmpeg, ffprobe, video)
    expected = 2 * (replay.last_frame - slp.FIRST_FRAME)
    for problem in report.problems(expected_frames=expected):
        print(f"  warning: {problem}", file=sys.stderr)
    pairs = solve.pair_count(report.probe.frames, report.pairing.offset)
    outputs = solve.solve(ffmpeg, video, out_dir, name, report.pairing.first_color, report.pairing.offset,
                          fmt=args.format, pairs=pairs, show_progress=False, rate=report.probe.rate)
    t_done = time.monotonic()
    game_seconds = replay.game_frames / 60
    print(f"  done in {t_done - t_start:.0f} s (Dolphin {t_rendered - t_start:.0f} s, solve {t_done - t_rendered:.0f} s) "
          f"for {game_seconds:.0f} s of gameplay: {game_seconds / (t_done - t_start):.2f}x real time")
    print(f"  {outputs.transparent}\n  {outputs.alpha_map}")
    if args.keep:
        print(f"  work folder kept: {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    return True


def cmd_render(args) -> int:
    """Render replays to transparent video: Dolphin records the flicker video, then the alpha solver runs."""
    dolphin = locate.find_dolphin(args.dolphin)
    engine = runner.engine_of(dolphin)
    if engine != config.MAINLINE and not args.allow_window:
        print(f"error: {dolphin} is not the headless build: it would open a window that flashes black and "
              "white (EPILEPSY WARNING). Build the headless one with tools/dolphin-build/build-mac-mainline.sh, "
              "or pass --allow-window to use this build anyway.", file=sys.stderr)
        return 2
    iso = locate.find_iso(args.iso)
    locate.check_iso(iso)
    ffmpeg = locate.find_ffmpeg(args.ffmpeg)
    ffprobe = locate.find_ffmpeg(args.ffmpeg, name="ffprobe")
    codes = gecko.load_codes(locate.RESOURCES / "Required Codes.txt")
    ok = [_render_one(args, Path(r), dolphin, engine, iso, ffmpeg, ffprobe, codes) for r in args.replays]
    return 0 if all(ok) else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="slp2alpha", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("info", help="show replay stage, length and whether it can be rendered")
    pi.add_argument("replays", nargs="+")
    pi.set_defaults(func=cmd_info)

    pr = sub.add_parser("render", help="render replays (.slp) to transparent video")
    pr.add_argument("replays", nargs="+")
    pr.add_argument("--format", default=solve.DEFAULT_FORMAT, choices=sorted(solve.FORMATS),
                    help="output format (default: mov, ProRes 4444 with alpha)")
    pr.add_argument("--out-dir", help="output folder (default: next to each replay)")
    pr.add_argument("--scale", type=int, default=1, choices=sorted(config.EFB_SCALE_FOR),
                    help="internal resolution multiplier (1 = 640x528)")
    pr.add_argument("--dolphin", help="Slippi playback Dolphin .app or executable (default: packages/)")
    pr.add_argument("--iso", help="Melee NTSC 1.02 ISO (default: the one set in the Slippi Launcher)")
    pr.add_argument("--ffmpeg", help="ffmpeg executable (ffprobe is expected next to it)")
    pr.add_argument("--dual-core", action=argparse.BooleanOptionalAction, default=None,
                    help="override the playback codes' single-core setting (CPUThread)")
    pr.add_argument("--boot-timeout", type=float, default=120.0)
    pr.add_argument("--allow-window", action="store_true",
                    help="allow a non-headless Dolphin build (its window flashes: EPILEPSY WARNING)")
    pr.add_argument("--debug", action="store_true", help="write Dolphin's log file")
    pr.add_argument("--keep", action="store_true", help="keep the work folder (raw recording, logs)")
    pr.set_defaults(func=cmd_render)

    pb = sub.add_parser("bench", help="measure Dolphin's emulation speed on this machine")
    pb.add_argument("--dolphin", required=True, help="Slippi Dolphin .app (or executable)")
    pb.add_argument("--replay", required=True)
    pb.add_argument("--iso")
    pb.add_argument("--record", action=argparse.BooleanOptionalAction, default=True)
    pb.add_argument("--flicker", action=argparse.BooleanOptionalAction, default=False,
                    help="enable the strobing background code (EPILEPSY WARNING if the window is visible)")
    pb.add_argument("--scale", type=int, default=1, choices=sorted(config.EFB_SCALE_FOR))
    pb.add_argument("--max-game-seconds", type=float, default=30.0)
    pb.add_argument("--time-limit", type=float, default=600.0)
    pb.add_argument("--cpu-sample-after", type=float, default=20.0)
    pb.add_argument("--boot-timeout", type=float, default=120.0)
    pb.add_argument("--fastmem", action=argparse.BooleanOptionalAction, default=None)
    pb.add_argument("--dual-core", action=argparse.BooleanOptionalAction, default=None,
                    help="override the playback codes' single-core setting (CPUThread)")
    pb.add_argument("--backend", help="video backend, e.g. Metal, OGL or Vulkan (default: build default)")
    pb.add_argument("--extra-arg", action="append", default=[], help="extra Dolphin argument")
    pb.add_argument("--code", action="append", default=[], help="extra Gecko code to enable (by name)")
    pb.add_argument("--debug", action="store_true", help="write Dolphin's log file")
    pb.add_argument("--keep", action="store_true")
    pb.set_defaults(func=cmd_bench)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (locate.NotFound, slp.ReplayError, KeyError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
