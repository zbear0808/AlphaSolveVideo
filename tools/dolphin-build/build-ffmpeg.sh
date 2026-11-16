#!/bin/bash
# Builds a minimal FFmpeg (shared libraries) with just what Dolphin's frame dumper needs.
#
# Usage: build-ffmpeg.sh VERSION ARCH PREFIX
#   VERSION  e.g. 4.4.8 (Ishiiruka) or 7.1.2 (Slippi mainline Dolphin)
#   ARCH     x86_64 or arm64
#   PREFIX   install folder
set -euo pipefail

VERSION="${1:?version}"
ARCH="${2:?arch}"
PREFIX="${3:?prefix}"
CACHE="${ALPHASOLVE_CACHE:-$HOME/Library/Caches/AlphaSolveVideo}"
MIN_MACOS="${MACOSX_DEPLOYMENT_TARGET:-11.0}"
MAJOR="${VERSION%%.*}"

mkdir -p "$CACHE/src"
cd "$CACHE/src"
if [ ! -f "ffmpeg-$VERSION.tar.xz" ]; then
  curl -fL --retry 3 -o "ffmpeg-$VERSION.tar.xz.part" "https://ffmpeg.org/releases/ffmpeg-$VERSION.tar.xz"
  mv "ffmpeg-$VERSION.tar.xz.part" "ffmpeg-$VERSION.tar.xz"
fi
rm -rf "ffmpeg-$VERSION-$ARCH"
mkdir "ffmpeg-$VERSION-$ARCH"
tar xf "ffmpeg-$VERSION.tar.xz" -C "ffmpeg-$VERSION-$ARCH" --strip-components 1
cd "ffmpeg-$VERSION-$ARCH"

CROSS=()
if [ "$(uname -m)" != "$ARCH" ]; then
  CROSS=(--arch="$ARCH" --target-os=darwin --enable-cross-compile --cc="clang -arch $ARCH" --cxx="clang++ -arch $ARCH")
fi
ASM=()
if [ "$ARCH" = "x86_64" ]; then ASM=(--disable-x86asm); fi   # avoids needing nasm; the dump path barely uses SIMD

# Ishiiruka (FFmpeg 4.4) doesn't need swresample; mainline Dolphin's CMake requires it.
RESAMPLE=(--disable-swresample)
if [ "$MAJOR" -ge 5 ]; then RESAMPLE=(--enable-swresample); fi
POSTPROC=(--disable-postproc)
if [ "$MAJOR" -ge 8 ]; then POSTPROC=(); fi   # libpostproc was removed from FFmpeg 8

# ${arr[@]+"${arr[@]}"} keeps bash 3.2 (macOS /bin/bash) happy with empty arrays under set -u
./configure --prefix="$PREFIX" ${CROSS[@]+"${CROSS[@]}"} ${ASM[@]+"${ASM[@]}"} \
  --extra-cflags="-arch $ARCH -mmacosx-version-min=$MIN_MACOS" \
  --extra-ldflags="-arch $ARCH -mmacosx-version-min=$MIN_MACOS" \
  --enable-shared --disable-static --enable-pic \
  --disable-programs --disable-doc --disable-autodetect \
  --disable-avdevice --disable-avfilter ${POSTPROC[@]+"${POSTPROC[@]}"} "${RESAMPLE[@]}" \
  --disable-everything \
  --enable-encoder=ffv1,utvideo,mpeg4 \
  --enable-muxer=avi,matroska,mov \
  --enable-protocol=file

make -j"$(sysctl -n hw.ncpu)"
make install

echo "Installed FFmpeg $VERSION ($ARCH) to $PREFIX"
lipo -archs "$PREFIX/lib/libavcodec.dylib"
