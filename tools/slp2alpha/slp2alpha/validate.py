"""Checks on a flicker recording: black/white alternation and which frames form pairs.

Each game frame is rendered twice, once over a black and once over a white background. For a true
pair (same game frame), the white-background render is never darker than the black one in any
channel, so "black brighter than white" pixels only show up when frames from different game frames
are paired. That gives a robust way to find the pairing and to detect dropped or duplicated frames.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_YAVG = re.compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")


@dataclass
class Probe:
    codec: str
    pix_fmt: str
    width: int
    height: int
    frames: int
    rate: str = "60/1"
    """The recording's field rate (r_frame_rate), e.g. 60000/1001 (mainline) or 60/1 (Ishiiruka)."""


def probe(ffprobe: str, video: str) -> Probe:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_packets,r_frame_rate",
                          "-of", "json", video], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return Probe(s.get("codec_name", "?"), s.get("pix_fmt", "?"), int(s.get("width", 0)),
                 int(s.get("height", 0)), int(s.get("nb_read_packets", 0)), s.get("r_frame_rate", "60/1"))


def timestamp_gaps(ffprobe: str, video: str, rate: str) -> List[Tuple[int, int]]:
    """(frame index after the gap, fields missing) wherever Dolphin skipped a field.

    Cheap: reads packet timestamps only. Recordings with real timestamps (Matroska) show a dropped or
    skipped field as a jump of two field durations.
    """
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", video], capture_output=True, text=True, check=True).stdout
    times = sorted(float(t) for t in out.split() if t not in ("N/A", ""))
    num, _, den = rate.partition("/")
    step = float(den or 1) / float(num)
    gaps = []
    for i in range(1, len(times)):
        fields = round((times[i] - times[i - 1]) / step)
        if fields > 1:
            gaps.append((i, fields - 1))
    return gaps


def select_exprs(first_color: str, offset: int) -> Dict[str, str]:
    """ffmpeg select expressions for the black and the white frame of each pair (as in AlphaSolve.bat)."""
    even, odd = "mod(n-1\\,2)", "mod(n\\,2)"  # mod(n-1,2) is non-zero for even n (incl. n=0), mod(n,2) for odd n
    black, white = (even, odd) if first_color == "black" else (odd, even)
    if offset:
        black, white = f"gt(n\\,0)*{black}", f"gt(n\\,0)*{white}"
    return {"black": black, "white": white}


def _metadata_values(ffmpeg: str, video: str, graph: str, frames: Optional[int] = None) -> List[float]:
    cmd = [ffmpeg, "-v", "error", "-i", video, "-filter_complex", graph, "-map", "[o]"]
    if frames:
        cmd += ["-frames:v", str(frames)]
    cmd += ["-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return [float(v) for v in _YAVG.findall(out)]


def luma_series(ffmpeg: str, video: str, frames: Optional[int] = None) -> List[float]:
    graph = "[0:v]scale=iw/4:ih/4,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-[o]"
    return _metadata_values(ffmpeg, video, graph, frames)


def first_color(ffmpeg: str, video: str) -> str:
    l0, l1 = luma_series(ffmpeg, video, frames=2)[:2]
    return "white" if l0 > l1 else "black"


def pair_violations(ffmpeg: str, video: str, color: str, offset: int, pairs: Optional[int] = None) -> List[float]:
    sel = select_exprs(color, offset)
    graph = (f"[0:v]format=gbrp,split[a][b];"
             f"[a]select={sel['black']},setpts=N/TB/60[blk];"
             f"[b]select={sel['white']},setpts=N/TB/60[wht];"
             f"[blk][wht]blend=all_mode=subtract:shortest=1,format=gray,"
             f"signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-[o]")
    return _metadata_values(ffmpeg, video, graph, pairs)


@dataclass
class PairingResult:
    first_color: str
    offset: int
    scores: Dict[int, float]
    ambiguous: bool


def detect_pairing(ffmpeg: str, video: str, pairs: int = 60) -> PairingResult:
    color = first_color(ffmpeg, video)
    scores = {}
    for off in (0, 1):
        v = pair_violations(ffmpeg, video, color, off, pairs)
        scores[off] = sum(v) / len(v) if v else float("inf")
    best = min(scores, key=scores.get)
    other = scores[1 - best]
    ambiguous = other < 0.02 or (best and scores[best] > 0.25 * other)
    return PairingResult(color, best, scores, ambiguous)


@dataclass
class DumpReport:
    probe: Probe
    pairing: PairingResult
    alternation: float
    """Fraction of neighbouring frames that alternate dark/bright (whole-screen flashes lower it a little)."""
    breaks: List[int]
    """Frame indexes where two neighbouring frames are clearly the same background colour."""
    worst_pair_violation: float

    def problems(self, expected_frames: Optional[int] = None) -> List[str]:
        out = []
        if self.probe.codec != "ffv1":
            out.append(f"recording codec is {self.probe.codec}, expected lossless ffv1")
        if expected_frames is not None and abs(self.probe.frames - expected_frames) > 4:
            out.append(f"recording has {self.probe.frames} frames, expected about {expected_frames}")
        if self.pairing.ambiguous:
            out.append("could not tell which frames form black/white pairs "
                       f"(violation scores {self.pairing.scores})")
        if self.alternation < 0.95:
            out.append(f"background alternates on only {self.alternation:.0%} of frames; "
                       "the flicker code may not be active")
        if self.worst_pair_violation > 8:
            out.append(f"a black/white pair is inconsistent (worst violation {self.worst_pair_violation:.1f}); "
                       "frames may have been dropped or duplicated")
        return out


def validate_dump(ffmpeg: str, ffprobe: str, video: str) -> DumpReport:
    p = probe(ffprobe, video)
    pairing = detect_pairing(ffmpeg, video)
    luma = luma_series(ffmpeg, video)
    mid = (max(luma) + min(luma)) / 2 if luma else 0
    bright = [v > mid for v in luma]
    alternating = [bright[i] != bright[i - 1] for i in range(1, len(bright))]
    alternation = sum(alternating) / len(alternating) if alternating else 0.0
    breaks = [i for i in range(1, len(luma)) if not alternating[i - 1] and abs(luma[i] - luma[i - 1]) < 0.15 * (max(luma) - min(luma))]
    violations = pair_violations(ffmpeg, video, pairing.first_color, pairing.offset)
    return DumpReport(p, pairing, alternation, breaks[:20], max(violations) if violations else 0.0)


def _alternation(luma: List[float]) -> float:
    if len(luma) < 2:
        return 0.0
    mid = (max(luma) + min(luma)) / 2
    bright = [v > mid for v in luma]
    return sum(bright[i] != bright[i - 1] for i in range(1, len(bright))) / (len(bright) - 1)


@dataclass
class QuickReport:
    """The checks a render needs before solving, in a few seconds instead of several full decodes."""
    probe: Probe
    pairing: PairingResult
    alternation: float
    """Over the first CHECK_FRAMES frames: is the flicker code active?"""
    gaps: List[Tuple[int, int]]

    def problems(self, expected_frames: Optional[int] = None) -> List[str]:
        out = []
        if self.probe.codec != "ffv1":
            out.append(f"recording codec is {self.probe.codec}, expected lossless ffv1")
        if expected_frames is not None and abs(self.probe.frames - expected_frames) > 4:
            out.append(f"recording has {self.probe.frames} frames, expected about {expected_frames}")
        if self.pairing.ambiguous:
            out.append("could not tell which frames form black/white pairs "
                       f"(violation scores {self.pairing.scores})")
        if self.alternation < 0.95:
            out.append(f"background alternates on only {self.alternation:.0%} of the first frames; "
                       "the flicker code may not be active")
        if self.gaps:
            missing = sum(n for _, n in self.gaps)
            out.append(f"Dolphin skipped {missing} field(s) in {len(self.gaps)} place(s) (first at frame "
                       f"{self.gaps[0][0]}); the game lagged there and black/white pairs may be off")
        return out


CHECK_FRAMES = 1200


def quick_check(ffmpeg: str, ffprobe: str, video: str) -> QuickReport:
    p = probe(ffprobe, video)
    return QuickReport(p, detect_pairing(ffmpeg, video), _alternation(luma_series(ffmpeg, video, CHECK_FRAMES)),
                       timestamp_gaps(ffprobe, video, p.rate))
