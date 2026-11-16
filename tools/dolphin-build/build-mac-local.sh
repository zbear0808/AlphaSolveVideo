#!/bin/bash
# Local build of Slippi's playback Dolphin (Ishiiruka v3.5.2) for macOS with frame dumping enabled.
#
# The result is an x86_64 app (it runs under Rosetta 2 on Apple Silicon), like the build the Slippi
# Launcher installs, except that it links FFmpeg 4.4 so Dolphin can record lossless FFV1 video.
#
# Usage: build-mac-local.sh [configure|build|bundle|all]   (default: all)
# Environment:
#   ALPHASOLVE_CACHE   work folder (default ~/Library/Caches/AlphaSolveVideo)
#   OUTPUT_APP         where the finished app is copied
#                      (default <repo>/packages/slippi-playback-framedump/Slippi Dolphin.app)
set -euo pipefail

STEP="${1:-all}"
COMMIT=bffe989d0bd3b83a4be3eaee708cf2755659e01e   # "release: v3.5.2" (the playback build the Launcher installs)
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CACHE="${ALPHASOLVE_CACHE:-$HOME/Library/Caches/AlphaSolveVideo}"
SRC="$CACHE/ishiiruka"
BUILD="$SRC/build"
FFMPEG44="$CACHE/ffmpeg44-x86_64"
OUTPUT_APP="${OUTPUT_APP:-$REPO_ROOT/packages/slippi-playback-framedump/Slippi Dolphin.app}"
PATCHES="$REPO_ROOT/tools/dolphin-build/patches"
export PATH="$HOME/.cargo/bin:$PATH"

# Ishiiruka's CMake files need CMake 3.x: CMake 4 rejects the target name "Slippi Dolphin"
# (Slippi's own CI pins CMake 3.31 for the same reason). Keep a private copy in a Python venv.
CMAKE="$CACHE/venv-cmake3/bin/cmake"
ensure_cmake3() {
  if [ ! -x "$CMAKE" ]; then
    log "Installing CMake 3.31 into $CACHE/venv-cmake3"
    python3 -m venv "$CACHE/venv-cmake3"
    "$CACHE/venv-cmake3/bin/pip" install -q --disable-pip-version-check "cmake>=3.31,<3.32"
  fi
}

log() { printf '\n== %s\n' "$*"; }

fetch() {
  if [ ! -d "$SRC/.git" ]; then
    log "Fetching Ishiiruka $COMMIT"
    git init -q "$SRC"
    git -C "$SRC" remote add origin https://github.com/project-slippi/Ishiiruka.git
  fi
  if [ "$(git -C "$SRC" rev-parse HEAD 2>/dev/null || true)" != "$COMMIT" ]; then
    git -C "$SRC" fetch -q --depth 1 origin "$COMMIT"
    git -C "$SRC" checkout -q FETCH_HEAD
    git -C "$SRC" submodule update --init --recursive --depth 1
  fi
}

apply_patches() {
  [ -d "$PATCHES" ] || return 0
  for p in "$PATCHES"/*.patch; do
    [ -e "$p" ] || continue
    if git -C "$SRC" apply --reverse --check "$p" 2>/dev/null; then
      echo "already applied: $(basename "$p")"
    else
      log "Applying $(basename "$p")"
      git -C "$SRC" apply "$p"
    fi
  done
}

configure() {
  [ -f "$FFMPEG44/lib/pkgconfig/libavcodec.pc" ] || "$REPO_ROOT/tools/dolphin-build/build-ffmpeg44.sh" "$FFMPEG44"
  command -v pkg-config >/dev/null || { echo "pkg-config is required (brew install pkgconf)"; exit 1; }
  rustup toolchain list | grep -q '^1\.88\.0' || \
    rustup toolchain install 1.88.0 --profile minimal --component rustfmt --component rustc-dev --target x86_64-apple-darwin
  rustup target list --installed --toolchain 1.88.0 | grep -q x86_64-apple-darwin || \
    rustup target add x86_64-apple-darwin --toolchain 1.88.0

  log "Configuring (x86_64, playback, FFmpeg 4.4 from $FFMPEG44)"
  ensure_cmake3
  # PKG_CONFIG_LIBDIR replaces pkg-config's default search path, so arm64 Homebrew packages are
  # never picked up for this x86_64 build; only our FFmpeg is visible.
  PKG_CONFIG_LIBDIR="$FFMPEG44/lib/pkgconfig" PKG_CONFIG_PATH="" \
  "$CMAKE" -S "$SRC" -B "$BUILD" \
    -DCMAKE_BUILD_TYPE=Release \
    -DIS_PLAYBACK=true \
    -DCMAKE_OSX_ARCHITECTURES=x86_64 \
    -DCMAKE_SYSTEM_PROCESSOR=x86_64 \
    -DCMAKE_OSX_SYSROOT=macosx \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCMAKE_IGNORE_PREFIX_PATH="/opt/homebrew;/usr/local" \
    -DRust_TOOLCHAIN=1.88.0 \
    -DRust_CARGO_TARGET=x86_64-apple-darwin \
    -DENABLE_LLVM=OFF \
    -DENABLE_AO=OFF \
    2>&1 | tee "$CACHE/configure.log"
  grep -q "libav/ffmpeg found, enabling AVI frame dumps" "$CACHE/configure.log" || {
    echo "ERROR: CMake did not find FFmpeg; frame dumping would be disabled."; exit 1; }
}

build() {
  local jobs="${JOBS:-$(sysctl -n hw.ncpu)}"
  log "Building with $jobs parallel jobs"
  PKG_CONFIG_LIBDIR="$FFMPEG44/lib/pkgconfig" PKG_CONFIG_PATH="" \
    nice -n "${NICE:-0}" make -C "$BUILD" -j"$jobs" 2>&1 | tee "$CACHE/build.log"
}

bundle() {
  local app="$BUILD/Binaries/Slippi Dolphin.app"
  local res="$app/Contents/Resources"
  log "Bundling Sys folder and playback Gecko codes"
  mkdir -p "$res/Sys"
  cp -Rf "$SRC/Data/Sys/." "$res/Sys/"
  rm -rf "$res/Sys/GameSettings"
  mkdir -p "$res/Sys/GameSettings"
  cp -r "$SRC/Data/PlaybackGeckoCodes/." "$res/Sys/GameSettings/"

  log "Checking that frame dumping is compiled in"
  local bin="$app/Contents/MacOS/Slippi Dolphin"
  lipo -archs "$bin"
  otool -L "$bin" | grep -E "libav(codec|format)|libswscale" || { echo "ERROR: FFmpeg not linked"; exit 1; }
  if strings -a "$bin" | grep -q "compiled without libav"; then echo "ERROR: built without libav"; exit 1; fi

  log "Copying to $OUTPUT_APP and signing (ad hoc)"
  rm -rf "$OUTPUT_APP"
  mkdir -p "$(dirname "$OUTPUT_APP")"
  ditto "$app" "$OUTPUT_APP"
  codesign --force --deep --sign - "$OUTPUT_APP"
  echo "Done: $OUTPUT_APP"
}

case "$STEP" in
  configure) fetch; apply_patches; configure ;;
  build)     build ;;
  bundle)    bundle ;;
  all)       fetch; apply_patches; configure; build; bundle ;;
  *) echo "usage: $0 [configure|build|bundle|all]"; exit 2 ;;
esac
