#!/bin/bash
# FFmpeg's ProRes 4444 encoders, with alpha, on a real transparent render: prores_ks (what the solver uses off
# macOS), prores_aw (CPU) and prores_ks_vulkan (GPU, FFmpeg 8.1 and later). At the render's size and at the CRT's
# 3504x2880, made from the same frames. "null" is the same pipeline without an encoder: decoding and scaling.
#
#   research/linux-gpu/prores_test.sh "fullTransparent - NAME.mov" [VULKAN_DEVICE]
#
# VULKAN_DEVICE: part of the GPU's name (NVIDIA, Intel) or its index (default 0). FFMPEG: the ffmpeg to test
# (default: packages/ffmpeg/ffmpeg, else the one on the PATH). Output in ${TMPDIR:-/tmp}/asv-prores. Linux (GNU date).
set -u
SRC=$1; DEV=${2:-0}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
F=${FFMPEG:-$REPO/packages/ffmpeg/ffmpeg}; [ -x "$F" ] || F=$(command -v ffmpeg)
P=$(dirname "$F")/ffprobe; [ -x "$P" ] || P=$(command -v ffprobe)
O=${TMPDIR:-/tmp}/asv-prores; rm -rf "$O"; mkdir -p "$O"
echo "source: $SRC; ffmpeg: $F; Vulkan device: $DEV"
"$F" -hide_banner -v error -i "$SRC" -frames:v 120 -c:v ffv1 -pix_fmt yuva444p10le -y "$O/src.nut" || exit 1
psnr() {  # psnr A B [alpha]: average and lowest PSNR of the colour planes, or of the alpha plane
  local g="[0]format=yuv444p10le[a];[1]format=yuv444p10le[b];[a][b]psnr"
  [ "${3:-}" = alpha ] && g="[0]alphaextract,format=gray16le[a];[1]alphaextract,format=gray16le[b];[a][b]psnr"
  "$F" -hide_banner -i "$1" -i "$2" -lavfi "$g" -f null - 2>&1 | grep -oE 'average:[^ ]+ min:[^ ]+' | tail -1
}
maxalpha() {  # the largest difference between the alpha planes, in 8 bits
  "$F" -hide_banner -i "$1" -i "$2" -lavfi "[0]alphaextract,format=gray[a];[1]alphaextract,format=gray[b];[a][b]blend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YMAX" \
    -f null - 2>&1 | grep -oE 'YMAX=[0-9]+' | cut -d= -f2 | sort -n | tail -1
}
for size in src big; do
  if [ $size = src ]; then n=120; scale=""; else n=40; scale="scale=3504:2880:flags=neighbor,"; fi
  for enc in null ks aw vk; do
    pre=(); out="$O/$size-$enc.mov"
    case $enc in
      null) args=(-vf "${scale}format=yuva444p10le" -f null); out=- ;;
      ks) args=(-vf "${scale}format=yuva444p10le" -c:v prores_ks -profile:v 4444 -alpha_bits 16 -vendor apl0) ;;
      aw) args=(-vf "${scale}format=yuva444p10le" -c:v prores_aw -profile:v 4 -vendor apl0) ;;  # "4444" is refused
      vk) pre=(-init_hw_device "vulkan=vk:$DEV" -filter_hw_device vk)
          args=(-vf "${scale}format=yuva444p10le,hwupload" -c:v prores_ks_vulkan -profile:v 4444 -vendor apl0) ;;
    esac
    s=$(date +%s.%N)
    "$F" -hide_banner -v error ${pre[@]+"${pre[@]}"} -stream_loop 1 -i "$O/src.nut" -frames:v $n "${args[@]}" -y "$out" \
      > "$O/$size-$enc.log" 2>&1
    rc=$?; e=$(date +%s.%N)
    line="== $size $enc: exit $rc, $(python3 -c "print(round($n / ($e - $s), 1))") frames/s"
    if [ $enc != null ] && [ -s "$out" ]; then
      probe=$("$P" -v error -select_streams v:0 -count_frames -show_entries stream=profile,pix_fmt,nb_read_frames \
        -of csv=p=0 "$out" 2>&1 | head -1)
      errs=$("$F" -hide_banner -v error -i "$out" -f null - 2>&1 | head -1)
      line="$line, $(du -h "$out" | cut -f1), $probe${errs:+; decode errors: $errs}"
    fi
    echo "$line"
    [ $rc = 0 ] || tail -3 "$O/$size-$enc.log"
  done
  [ $size = src ] && for enc in ks aw vk; do
    [ -s "$O/src-$enc.mov" ] && echo "   $enc against the source: colour $(psnr "$O/src.nut" "$O/src-$enc.mov")"
  done
  for enc in aw vk; do
    [ -s "$O/$size-ks.mov" ] && [ -s "$O/$size-$enc.mov" ] || continue
    echo "   $enc against ks: colour $(psnr "$O/$size-ks.mov" "$O/$size-$enc.mov") | alpha" \
         "$(psnr "$O/$size-ks.mov" "$O/$size-$enc.mov" alpha) | largest alpha difference" \
         "$(maxalpha "$O/$size-ks.mov" "$O/$size-$enc.mov")/255"
  done
done
