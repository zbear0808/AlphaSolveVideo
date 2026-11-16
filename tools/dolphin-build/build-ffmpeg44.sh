#!/bin/bash
# FFmpeg 4.4 for the x86_64 Ishiiruka build (its AVIDump.cpp uses APIs removed in FFmpeg 5).
# Usage: build-ffmpeg44.sh [prefix]   (default ~/Library/Caches/AlphaSolveVideo/ffmpeg44-x86_64)
set -euo pipefail
CACHE="${ALPHASOLVE_CACHE:-$HOME/Library/Caches/AlphaSolveVideo}"
exec "$(dirname "$0")/build-ffmpeg.sh" "${FFMPEG_VERSION:-4.4.8}" x86_64 "${1:-$CACHE/ffmpeg44-x86_64}"
