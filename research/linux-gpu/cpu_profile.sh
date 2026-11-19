#!/bin/bash
# Where the CPU goes in a render (Linux): one clip of a replay, with the CPU seconds of each process and thread of
# Dolphin and ffmpeg, from /proc (thread_sampler.py).
#
#   research/linux-gpu/cpu_profile.sh NAME SCALE START END [more slp2alpha render options]
#
# REPLAY: the replay (default: the render tests' DishonestMuddyCoyote.slp in the cache). The ISO comes from
# SLP2ALPHA_ISO or the Slippi Launcher. Output in ${TMPDIR:-/tmp}/asv-prof/NAME.
set -u
NAME=$1; SCALE=$2; START=$3; END=$4; shift 4
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
CACHE=${ALPHASOLVE_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/AlphaSolveVideo}
REPLAY=${REPLAY:-$CACHE/test-replays/DishonestMuddyCoyote.slp}
OUT=${TMPDIR:-/tmp}/asv-prof/$NAME
rm -rf "$OUT"; mkdir -p "$OUT"
cd "$REPO/tools/slp2alpha" || exit 1
python3 -m slp2alpha render "$REPLAY" --characters-only --start-frame "$START" --end-frame "$END" --scale "$SCALE" \
  --out-dir "$OUT" "$@" > "$OUT/render.log" 2>&1 &
rp=$!
python3 "$HERE/thread_sampler.py" $rp > "$OUT/threads.txt"
wait $rp
rc=$?
echo "== $NAME: scale $SCALE, frames $START-$END, exit $rc"
tr '\r' '\n' < "$OUT/render.log" | grep -E "done in|warning|error" | tail -4
cat "$OUT/threads.txt"
