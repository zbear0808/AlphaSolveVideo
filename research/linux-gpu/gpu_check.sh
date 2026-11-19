#!/bin/bash
# Which GPUs this Linux PC has, which driver runs each, and which one each program of the pipeline draws on:
# Vulkan, EGL, Blender, ffmpeg (NVENC, Vulkan) and Dolphin, after a driver change for example. Renders a few
# seconds into ${TMPDIR:-/tmp}/asv-gpu-check; changes nothing else.
#
#   research/linux-gpu/gpu_check.sh [--no-dolphin]
#
# Dolphin renders frames 1500-1799 of REPLAY (default: the render tests' DishonestMuddyCoyote.slp in the cache)
# with each GPU, and compares the camera export with the Mac's reference. The ISO comes from SLP2ALPHA_ISO or the
# Slippi Launcher. BLENDER: Blender (default: the one on the PATH, else ~/.local/bin/blender). FFMPEG: the ffmpeg
# for the NVENC and Vulkan checks (default: packages/ffmpeg/ffmpeg; NVENC on driver 580 needs an FFmpeg 8.1 build).
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
CACHE=${ALPHASOLVE_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/AlphaSolveVideo}
REPLAY=${REPLAY:-$CACHE/test-replays/DishonestMuddyCoyote.slp}
OUT=${TMPDIR:-/tmp}/asv-gpu-check
F=${FFMPEG:-$REPO/packages/ffmpeg/ffmpeg}; [ -x "$F" ] || F=$(command -v ffmpeg)
B=${BLENDER:-$(command -v blender || echo "$HOME/.local/bin/blender")}
GLVND=/usr/share/glvnd/egl_vendor.d
rm -rf "$OUT"; mkdir -p "$OUT"
h() { printf '\n## %s\n' "$*"; }

h GPUs and their kernel drivers
NV=""; INTEL=""
for d in /sys/class/drm/renderD*; do
  v=$(cat "$d/device/vendor"); id=$(cat "$d/device/device"); drv=$(basename "$(readlink "$d/device/driver")")
  slot=$(basename "$(readlink -f "$d/device")")
  echo "${d##*/}: PCI $slot, ${v#0x}:${id#0x}, driver $drv"
  case $v in 0x10de) NV=${v#0x}:${id#0x} ;; 0x8086) INTEL=${v#0x}:${id#0x} ;; esac
done
echo "loaded: $(lsmod | awk '$1 ~ /^(nvidia|nvidia_drm|nvidia_modeset|nouveau|i915|amdgpu)$/ {printf "%s ", $1}')"

h NVIDIA
if command -v nvidia-smi > /dev/null; then
  nvidia-smi --query-gpu=name,driver_version,memory.total,clocks.max.sm,clocks.max.mem,temperature.gpu,power.draw,pstate \
    --format=csv 2>&1 | head -3
else
  echo "no nvidia-smi"
fi

h Vulkan devices, in the order programs see them
vulkaninfo --summary 2>/dev/null | grep -E 'deviceName|deviceType|driverName' | sed 's/^ */  /'

h EGL, without a display
env -u DISPLAY -u WAYLAND_DISPLAY eglinfo -B 2>/dev/null | grep -E 'platform:$|OpenGL core profile renderer' | sed 's/^ */  /'

h Blender: which GPU EEVEE draws on, 3 frames of its startup scene
probe() {  # NAME ENV... -- BLENDER ARGS...
  local name=$1; shift; local envs=(); while [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
  env "${envs[@]}" "$B" -b --factory-startup "$@" --python "$HERE/eevee_probe.py" -- 3 "$OUT/blender-$name" 2>&1 |
    grep -E '^(GPU|RESULT):' | sed "s/^/  $name: /"
}
probe default --
[ -f $GLVND/50_mesa.json ] && probe mesa-egl __EGL_VENDOR_LIBRARY_FILENAMES=$GLVND/50_mesa.json --
[ -f $GLVND/10_nvidia.json ] && probe nvidia-egl __EGL_VENDOR_LIBRARY_FILENAMES=$GLVND/10_nvidia.json --
probe vulkan -- --gpu-backend vulkan

h ffmpeg: NVENC and Vulkan
"$F" -hide_banner -v error -f lavfi -i testsrc2=s=1280x720:r=60 -frames:v 120 -c:v h264_nvenc -f null - 2>&1 | head -2
echo "  h264_nvenc: exit ${PIPESTATUS[0]}"
"$F" -hide_banner -v error -f lavfi -i testsrc2=s=1280x720:r=60 -frames:v 30 -pix_fmt yuv444p -c:v h264_nvenc \
  -profile:v high444p -f null - 2>&1 | head -2
echo "  h264_nvenc 4:4:4: exit ${PIPESTATUS[0]}"
for dev in NVIDIA Intel; do
  "$F" -hide_banner -v verbose -init_hw_device "vulkan=vk:$dev" -f lavfi -i testsrc2=s=640x480 -frames:v 1 \
    -filter_hw_device vk -vf format=yuv420p,hwupload,hwdownload,format=yuv420p -f null - 2>&1 |
    grep -m1 -iE 'Device [0-9]+ selected|Using device' | sed "s/^/  Vulkan $dev: /" || echo "  Vulkan $dev: not opened"
done

[ "${1:-}" = --no-dolphin ] && exit 0
h Dolphin: frames 1500-1799, characters only, with the camera export
REF=$REPO/tools/camera-export/reference/DishonestMuddyCoyote_1500-1799_characters-only_macos.json
render() {  # NAME ENV... -- RENDER ARGS...
  local name=$1; shift; local envs=(); while [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
  local dir=$OUT/dolphin-$name
  (cd "$REPO/tools/slp2alpha" && env "${envs[@]}" python3 -m slp2alpha render "$REPLAY" --characters-only \
    --start-frame 1500 --end-frame 1799 --export-camera --keep --out-dir "$dir" "$@" > "$dir.log" 2>&1)
  local rc=$?
  local fps; fps=$(tr '\r' '\n' < "$dir.log" | grep -oE '[0-9]+ game fps' | tail -1)
  local work; work=$(grep -oE 'work folder kept: .*' "$dir.log" | cut -d' ' -f4-)
  local cam; cam=$(ls "$dir"/camera*.json 2>/dev/null | head -1)
  local same="-"
  [ -n "$cam" ] && same=$(python3 "$REPO/tools/camera-export/validate_camera.py" compare "$REF" "$cam" 2>&1 | tail -1)
  echo "  $name: exit $rc, ${fps:-? game fps}; camera against the Mac's: $same"
  [ -n "$work" ] && rm -rf "$work"
}
render vulkan-default --
[ -n "$NV" ] && render vulkan-nvidia MESA_VK_DEVICE_SELECT=$NV MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE=1 --
[ -n "$INTEL" ] && render vulkan-intel MESA_VK_DEVICE_SELECT=$INTEL MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE=1 --
render opengl-default -- --backend OGL
