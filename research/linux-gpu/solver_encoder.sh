#!/bin/bash
# The solver's ProRes encoder in a streamed render (the solver runs while Dolphin records, as for whole games):
# 40 s of a game at --scale 1 (frames 1000-3399), once with prores_ks, the solver's encoder off macOS, and once with
# prores_aw swapped in. Prints the render's summary and each process's CPU seconds (Linux).
#
#   research/linux-gpu/solver_encoder.sh [more slp2alpha render options]
#
# REPLAY: the replay (default: the render tests' DishonestMuddyCoyote.slp in the cache). The ISO comes from
# SLP2ALPHA_ISO or the Slippi Launcher, the GPU from the environment (MESA_VK_DEVICE_SELECT=10de:1c20 and
# MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE=1, for example). Output in ${TMPDIR:-/tmp}/asv-solver-ks and -aw.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
CACHE=${ALPHASOLVE_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/AlphaSolveVideo}
REPLAY=${REPLAY:-$CACHE/test-replays/DishonestMuddyCoyote.slp}
cd "$REPO/tools/slp2alpha" || exit 1
for enc in ks aw; do
  OUT=${TMPDIR:-/tmp}/asv-solver-$enc; rm -rf "$OUT"
  python3 - "$enc" "$OUT" "$REPLAY" "$@" > "$OUT.log" 2>&1 <<'PY' &
import sys
from slp2alpha import solve
from slp2alpha.__main__ import main
enc, out, replay, extra = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
if enc == "aw":
    aw = ["-c:v", "prores_aw", "-profile:v", "4", "-vendor", "apl0"]
    solve.FORMATS["mov"] = solve.OutputFormat(".mov", aw + ["-pix_fmt", "yuva444p10le"], aw + ["-pix_fmt", "yuv444p10le"])
sys.exit(main(["render", replay, "--characters-only", "--start-frame", "1000", "--end-frame", "3399",
               "--out-dir", out] + extra))
PY
  pid=$!
  python3 "$HERE/thread_sampler.py" $pid > "$OUT.threads"
  wait $pid
  echo "== solver with prores_$enc: exit $?"
  tr '\r' '\n' < "$OUT.log" | grep -E "done in|warning" | tail -3
  grep -E "^  (ffmpeg|dolphin)" "$OUT.threads" | head -4
done
