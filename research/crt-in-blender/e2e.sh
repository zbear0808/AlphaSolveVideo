#!/bin/bash
# The whole of slp2video, from a replay to the finished video, with the CRT drawn by Blender and by librashader-cli:
# each step's time, as slp2video prints it, and the total.
#
#   research/crt-in-blender/e2e.sh OUT_DIR [slp2video options...]
#
# Default: frames 1500-1739 (4 s) of the render tests' DishonestMuddyCoyote.slp with the logo through the moving
# camera and the CRT (--model logo --crt), once per runtime in RUNTIMES (default: "auto" and this platform's
# librashader runtime, wgpu on Linux, metal on macOS). Environment as for slp2video: SLP2ALPHA_ISO, VK_DRIVER_FILES.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
OUT=$1; shift
CACHE=${ALPHASOLVE_CACHE:-$( [ "$(uname)" = Darwin ] && echo "$HOME/Library/Caches" || echo "${XDG_CACHE_HOME:-$HOME/.cache}")/AlphaSolveVideo}
REPLAY=${REPLAY:-$CACHE/test-replays/DishonestMuddyCoyote.slp}
OPTS=("$@"); [ ${#OPTS[@]} -gt 0 ] || OPTS=(--model logo --crt --start-frame 1500 --end-frame 1739)
LIB=$([ "$(uname)" = Darwin ] && echo metal || echo wgpu)
mkdir -p "$OUT"
for rt in ${RUNTIMES:-auto $LIB}; do
  log="$OUT/e2e-$rt.log"
  start=$(python3 -c 'import time; print(time.time())')
  python3 "$REPO/tools/slp2video/slp2video.py" "$REPLAY" "${OPTS[@]}" --crt-runtime "$rt" --out-dir "$OUT/$rt" > "$log" 2>&1
  status=$?
  total=$(python3 -c "import time; print(round(time.time() - $start))")
  echo "== --crt-runtime $rt: exit $status, $total s"
  tr '\r' '\n' < "$log" | grep -E "^(render|done in|model:|composited in|CRT: drawn)|real time|Dolphin:|warning|error" | grep -v "frames through" | sed 's/^/   /'
  ls -la "$OUT/$rt" 2>/dev/null | tail -n +4 | awk '{print "   " $5, $NF}'
done
