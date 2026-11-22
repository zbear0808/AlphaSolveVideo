#!/bin/bash
# crt-royale through Blender's GPU module against librashader-cli: the same frames, and the speed into an encoder.
#
#   research/crt-in-blender/compare.sh CLIP [FRAMES]
#
# CLIP is any video; its first FRAMES frames (default 120) are squeezed to 584x480 and drawn at 3504x2880, the size
# `slp2video --crt` draws regular Melee at. Prints, for frames 0, the middle and the last, and each mask, how far
# Blender's frames are from librashader-cli's; then the frames per second of Blender's CRT alone and into each
# encoder there is, and of today's render_video.render for comparison.
#
# Environment: BLENDER (default: plate.find_blender), FFMPEG (default: slp2alpha's), GPU_BACKEND (Blender's
# --gpu-backend, e.g. opengl on Linux), ENCODERS (default: this platform's), VK_DRIVER_FILES (for librashader-cli's
# wgpu on Linux, e.g. /usr/share/vulkan/icd.d/nvidia_icd.json).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
CLIP=$1
FRAMES=${2:-120}
W=584 H=480 OW=3504 OH=2880
WORK=$(mktemp -d "${TMPDIR:-/tmp}/crt-in-blender.XXXXXX")
pyrepo() { (cd "$REPO/tools/crt" && PYTHONPATH="$REPO/tools/slp2alpha" python3 -c "$1"); }
FFMPEG=${FFMPEG:-$(pyrepo 'from slp2alpha import locate; print(locate.find_ffmpeg())')}
BLENDER=${BLENDER:-$(cd "$REPO/tools/logo-stage" && python3 -c 'import plate; print(plate.find_blender())')}
LIBRA=$(pyrepo 'import render_video as r; print(r.find_librashader())')
RUNTIME=$(pyrepo 'import render_video as r; print(r.runtime_candidates(r.runtimes_of(r.find_librashader()))[0])')
BPY=$("$BLENDER" -b --factory-startup --python-expr 'import sys; print("BPY", sys.executable)' 2>/dev/null | awk '/^BPY/ {print $2}')
BL=("$BLENDER" -b --factory-startup -noaudio ${GPU_BACKEND:+--gpu-backend "$GPU_BACKEND"} --python "$HERE/blender_crt.py" --)
params() { echo "mask_type=$1,mask_triad_size_desired=3.0,interlace_detect_toggle=0,geom_aspect_ratio_x=1.217,geom_aspect_ratio_y=1.0"; }
echo "work folder: $WORK"

python3 "$HERE/prep_chain.py" "$WORK/chain" --ffmpeg "$FFMPEG"
"$FFMPEG" -v error -y -i "$CLIP" -frames:v "$FRAMES" -vf "scale=$W:$H:flags=lanczos,format=rgba" -f rawvideo "$WORK/clip.rgba"
"$FFMPEG" -v error -y -f rawvideo -pix_fmt rgba -s ${W}x$H -i "$WORK/clip.rgba" -vf vflip -f rawvideo "$WORK/clip_up.rgba"
N=$(( $(wc -c < "$WORK/clip.rgba") / (W * H * 4) ))

echo "== the same frames: Blender against librashader-cli ($RUNTIME)"
for f in 0 $((N / 2)) $((N - 1)); do
  "$FFMPEG" -v error -y -f rawvideo -pix_fmt rgba -s ${W}x$H -i "$WORK/clip.rgba" -vf "select=eq(n\,$f)" -frames:v 1 "$WORK/f.png"
  "$FFMPEG" -v error -y -i "$WORK/f.png" -f rawvideo -pix_fmt rgba "$WORK/f.rgba"
  for m in 0 1 2; do
    "$LIBRA" render -p "$REPO/tools/crt/slang-shaders/crt/crt-royale.slangp" -i "$WORK/f.png" -o "$WORK/lib.png" \
      -r "$RUNTIME" -d ${OW}x$OH --params "$(params $m)"
    "$FFMPEG" -v error -y -i "$WORK/lib.png" -f rawvideo -pix_fmt rgba "$WORK/lib.rgba"
    "${BL[@]}" "$WORK/chain" "$WORK/f.rgba" $W $H $OW $OH "$(params $m)" "$WORK/bl.rgba" --top-down >/dev/null 2>&1
    echo -n "frame $f, mask $m: "; "$BPY" "$HERE/frame_diff.py" "$WORK/lib.rgba" "$WORK/bl.rgba" $OW $OH
  done
done

echo "== speed, $N frames"
"${BL[@]}" "$WORK/chain" "$WORK/clip_up.rgba" $W $H $OW $OH "$(params 0)" /dev/null 2>&1 | grep BLENDER_CRT
if [ -z "${ENCODERS:-}" ]; then
  ENCODERS="prores_aw -profile:v 4 -pix_fmt yuva444p10le .mov"
  [ "$(uname)" = Darwin ] && ENCODERS="prores_videotoolbox -allow_sw 1 -profile:v 4444 -pix_fmt bgra .mov"
  "$FFMPEG" -hide_banner -encoders 2>/dev/null > "$WORK/encoders.txt" || true
  grep -q h264_nvenc "$WORK/encoders.txt" && ENCODERS="$ENCODERS
h264_nvenc -preset p5 -tune hq -profile:v high444p -pix_fmt yuv444p -rc vbr -cq 16 -b:v 0 .mp4
hevc_nvenc -preset p5 -tune hq -profile:v rext -pix_fmt yuv444p -rc vbr -cq 16 -b:v 0 .mp4"
fi
mkfifo "$WORK/crt.fifo"
while IFS= read -r spec; do
  [ -n "$spec" ] || continue
  ext=${spec##* }; args=${spec% *}
  start=$(python3 -c 'import time; print(time.time())')
  # shellcheck disable=SC2086
  "$FFMPEG" -v error -y -f rawvideo -pix_fmt rgba -s ${OW}x$OH -framerate 60 -i "$WORK/crt.fifo" -vf vflip -c:v $args "$WORK/out$ext" &
  "${BL[@]}" "$WORK/chain" "$WORK/clip_up.rgba" $W $H $OW $OH "$(params 0)" "$WORK/crt.fifo" >/dev/null 2>&1
  wait
  python3 -c "import time; t = time.time() - $start; print(f'Blender CRT into ${args%% *}: {t:.1f} s, {$N / t:.1f} frames/s')"
done <<< "$ENCODERS"

"$FFMPEG" -v error -y -f rawvideo -pix_fmt rgba -s ${W}x$H -framerate 60 -i "$WORK/clip.rgba" -c:v ffv1 "$WORK/clip.nut"
pyrepo "
import time, render_video as r
from pathlib import Path
from slp2alpha import locate
s = r.physical_settings($W, $H, 6, mask='grille')
for codec, ext in (('prores4444', '.mov'), ('h264-444', '.mp4')):
    t = time.time()
    n, rt = r.render(Path('$WORK/clip.nut'), Path('$WORK/today' + ext), s, ffmpeg='$FFMPEG', librashader='$LIBRA',
                     input_size=($W, $H), rate='60', prefilter='format=bgr0', codec=codec, jobs=4)
    t = time.time() - t
    print(f'today, render_video.render ({rt}, 4 jobs) into {codec}: {t:.1f} s, {n / t:.1f} frames/s')
"
