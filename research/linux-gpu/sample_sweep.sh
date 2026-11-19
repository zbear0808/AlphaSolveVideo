#!/bin/bash
# The logo plate (tools/logo-stage/plate.py) on 40 frames of the reference camera export, at 1, 16 and 64 EEVEE
# samples, one Blender process each: how the time per frame grows with the samples (the GPU's work) and what's left
# at 1 sample (mostly the CPU's). On Linux, also Blender's CPU use over 8 s in the middle of each run.
#
#   research/linux-gpu/sample_sweep.sh OUT_DIR [ISO]
#
# The environment passes through to Blender, so it can pick the GPU: DRI_PRIME=pci-0000_00_02_0,
# __EGL_VENDOR_LIBRARY_FILENAMES=..., BLENDER=... (see docs/plan-linux-gpu.md section 8).
set -u
REPO=$(cd "$(dirname "$0")/../.." && pwd)
OUT=$1; ISO=${2:-}
mkdir -p "$OUT"
cd "$REPO" || exit 1
python3 - "$OUT/cam40.json" <<'PY'
import json, sys
d = json.load(open("tools/camera-export/reference/DishonestMuddyCoyote_1500-1799_characters-only_macos.json"))
d["samples"] = d["samples"][:40]
d["frames"].update(count=40, video=40, last=d["frames"]["first"] + 39)
json.dump(d, open(sys.argv[1], "w"))
PY
for s in 1 16 64; do
  rm -rf "$OUT/s$s"
  python3 tools/logo-stage/plate.py battlefield --camera-export "$OUT/cam40.json" --jobs 1 --samples $s \
      ${ISO:+--iso "$ISO"} --out "$OUT/s$s/frames" > "$OUT/s$s.log" 2>&1 &
  py=$!
  cpu="-"
  sleep 14
  bpid=$(pgrep -n -f "blender.*blender_plate.py")
  if [ -n "$bpid" ] && [ -r "/proc/$bpid/stat" ]; then   # 100% = one core busy
    t1=$(awk '{print $14 + $15}' "/proc/$bpid/stat"); sleep 8
    t2=$(awk '{print $14 + $15}' "/proc/$bpid/stat" 2>/dev/null || echo "$t1")
    cpu="$(( (t2 - t1) * 100 / 8 / $(getconf CLK_TCK) ))%"
  fi
  wait $py || { echo "  $s samples: plate.py failed, see $OUT/s$s.log"; continue; }
  python3 - "$OUT/s$s/blender-0.log" "$s" "$cpu" <<'PY'
import re, statistics, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
st = [int(m) * 60 + float(x) for m, x in re.findall(r"^(\d+):(\d+\.\d+)\s+render\s+\| Saved:", text, re.M)]
gaps = [b - a for a, b in zip(st, st[1:])]
print(f"  {sys.argv[2]:>2} samples: {statistics.median(gaps):.3f} s a frame (first frame saved at {st[0]:.1f} s); "
      f"Blender CPU {sys.argv[3]}")
PY
done
