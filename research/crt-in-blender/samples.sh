#!/bin/bash
# The model's EEVEE samples against the final CRT picture: slp2video --model logo --crt at each sample count, the
# CRT redrawn losslessly (PNG) from each run's composite, and each compared with the most samples' frames.
#
#   research/crt-in-blender/samples.sh OUT_DIR [SAMPLES...]      (default: 64 16 8 4; the first is the reference)
#
# Frames 1500-1559 of the render tests' DishonestMuddyCoyote.slp (FRAMES="1500 1559"); frames 0, 30 and 59 compared.
# Prints each run's model time, and the mean and largest difference of the plate and of the CRT picture.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
OUT=$(mkdir -p "$1" && cd "$1" && pwd); shift
SAMPLES=("$@"); [ ${#SAMPLES[@]} -gt 0 ] || SAMPLES=(64 16 8 4)
read -r FIRST LAST <<< "${FRAMES:-1500 1559}"
CACHE=${ALPHASOLVE_CACHE:-$( [ "$(uname)" = Darwin ] && echo "$HOME/Library/Caches" || echo "${XDG_CACHE_HOME:-$HOME/.cache}")/AlphaSolveVideo}
REPLAY=${REPLAY:-$CACHE/test-replays/DishonestMuddyCoyote.slp}
FF=$(cd "$REPO/tools/slp2alpha" && python3 -c 'from slp2alpha import locate; print(locate.find_ffmpeg())')
BLENDER=$(cd "$REPO/tools/slp2alpha" && python3 -c 'from slp2alpha import locate; print(locate.find_blender())')
BPY=$("$BLENDER" -b --factory-startup --python-expr 'import sys; print("BPY", sys.executable)' 2>/dev/null | awk '/^BPY/ {print $2}')
PICK="0 30 59"
for s in "${SAMPLES[@]}"; do
  log="$OUT/s$s.log"
  python3 "$REPO/tools/slp2video/slp2video.py" "$REPLAY" --model logo --crt --model-samples "$s" --keep-intermediates \
    --start-frame "$FIRST" --end-frame "$LAST" --out-dir "$OUT/s$s" > "$log" 2>&1 || { echo "samples $s: failed, $log"; continue; }
  work=$(grep -o "work folder kept: .*" "$log" | sed 's/work folder kept: //')
  echo "samples $s: $(grep -o "model: rendered in [0-9]* s" "$log")"
  for n in $PICK; do
    cp "$work/plate/$(printf %06d $((n + 1))).png" "$OUT/s$s-plate-$n.png"
    "$FF" -v error -y -i "$work/composite.nut" -vf "select=eq(n\,$n),format=gbrap16le,premultiply=inplace=1,scale=584:480:flags=lanczos+accurate_rnd+full_chroma_int,unpremultiply=inplace=1,format=bgra" -frames:v 1 -c:v ffv1 "$OUT/f.nut"
    python3 "$REPO/tools/crt/render_video.py" "$OUT/f.nut" "$OUT/s$s-crt-$n" --physical-pixels --scale 6 --codec png --no-alpha > /dev/null
  done
  rm -rf "$work" "$OUT/s$s"
done
ref=${SAMPLES[0]}
cat > "$OUT/diff.py" <<'EOF'
import sys
import numpy as np
from pathlib import Path
import subprocess
ff, a, b = sys.argv[1:4]
def load(p):
    return np.frombuffer(subprocess.run([ff, "-v", "error", "-i", p, "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                                        capture_output=True, check=True).stdout, np.uint8).astype(np.int16)
x, y = load(a), load(b)
d = np.abs(x - y).reshape(-1, 4)
print(f"{d[:, :3].mean():.3f} {d[:, :3].max()} {d[:, 3].mean():.3f}")
EOF
for s in "${SAMPLES[@]:1}"; do
  for n in $PICK; do
    read -r pm px pa <<< "$("$BPY" "$OUT/diff.py" "$FF" "$OUT/s$ref-plate-$n.png" "$OUT/s$s-plate-$n.png")"
    read -r cm cx _ <<< "$("$BPY" "$OUT/diff.py" "$FF" "$OUT/s$ref-crt-$n/000001.png" "$OUT/s$s-crt-$n/000001.png")"
    echo "samples $s against $ref, frame $n: plate colour mean $pm/255 (max $px), alpha mean $pa; CRT mean $cm/255 (max $cx)"
  done
done
