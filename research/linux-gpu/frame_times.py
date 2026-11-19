"""Time per frame from Blender's render logs, from the lines `00:12.278  render | Saved: '.../000001.png'`
(time since Blender started).

    python3 frame_times.py BLENDER.log [...]

Prints, for each log, the frames saved, when the first was saved (start-up and shader compilation) and the median
time between frames after it. plate.py keeps one log per Blender process: OUT/../blender-N.log.
"""
import re
import statistics
import sys

for path in sys.argv[1:]:
    text = open(path, encoding="utf-8", errors="replace").read()
    stamps = [int(m) * 60 + float(s) for m, s in re.findall(r"^(\d+):(\d+\.\d+)\s+render\s+\| Saved:", text, re.M)]
    if len(stamps) < 2:
        print(f"{path}: fewer than two frames saved")
        continue
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    print(f"{path}: {len(stamps)} frames; first saved at {stamps[0]:.1f} s; "
          f"then median {statistics.median(gaps):.3f} s a frame")
