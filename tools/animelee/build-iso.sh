#!/bin/sh
# Build the Animelee Complete Edition ISO from your own Melee NTSC 1.02 ISO.
#
#   tools/animelee/build-iso.sh [--iso VANILLA.iso] [--zip PATCH.zip] [--out FILE]
#
# --iso  defaults to the ISO set in the Slippi Launcher.
# --zip  a downloaded "ANIMELEE_-_COMPLETE_EDITION_-_PATCH_1.0.zip"; without it the zip is fetched from
#        animelee.xyz's MediaFire link (30 MB).
# --out  defaults to ~/Library/Caches/AlphaSolveVideo/animelee/ANIMELEE - COMPLETE EDITION.iso, where
#        `slp2alpha render --animelee` looks for it.
#
# Needs xdelta3 (brew install xdelta). The patch only changes data files (the DOL is identical), so
# every Gecko code in Resources/ keeps working.
set -eu

PAGE="https://www.mediafire.com/file/2ztqob93nrug8yg/ANIMELEE_-_COMPLETE_EDITION_-_PATCH_1.0.zip/file"
VANILLA_MD5="0e63d4223b01d9aba596259dc155a174"
case "$(uname)" in
  Darwin) CACHE="$HOME/Library/Caches/AlphaSolveVideo/animelee"
          LAUNCHER="$HOME/Library/Application Support/Slippi Launcher/Settings" ;;
  *)      CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/AlphaSolveVideo/animelee"
          LAUNCHER="${XDG_CONFIG_HOME:-$HOME/.config}/Slippi Launcher/Settings" ;;
esac
ISO=""; ZIP=""; OUT="$CACHE/ANIMELEE - COMPLETE EDITION.iso"
while [ $# -gt 0 ]; do
  case "$1" in
    --iso) ISO="$2"; shift 2 ;;
    --zip) ZIP="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

command -v xdelta3 >/dev/null || { echo "xdelta3 not found (macOS: brew install xdelta)" >&2; exit 1; }
if [ -z "$ISO" ]; then
  ISO=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["settings"]["isoPath"])' "$LAUNCHER" 2>/dev/null) \
    || { echo "no --iso given and none set in the Slippi Launcher" >&2; exit 1; }
fi
[ -f "$ISO" ] || { echo "ISO not found: $ISO" >&2; exit 1; }

if command -v md5 >/dev/null; then sum=$(md5 -q "$ISO"); else sum=$(md5sum "$ISO" | cut -d' ' -f1); fi
[ "$sum" = "$VANILLA_MD5" ] || echo "warning: $ISO has MD5 $sum, not the clean 1.02 hash $VANILLA_MD5; the patch may fail" >&2

mkdir -p "$CACHE"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
if [ -z "$ZIP" ]; then
  echo "downloading the Animelee patch ..."
  URL=$(curl -sL -A "Mozilla/5.0" "$PAGE" | grep -o 'https://download[^"]*zip' | head -1)
  [ -n "$URL" ] || { echo "could not find the download link on MediaFire; download the zip from animelee.xyz and pass --zip" >&2; exit 1; }
  ZIP="$WORK/patch.zip"
  curl -sL "$URL" -o "$ZIP"
fi
unzip -q -o "$ZIP" -d "$WORK/patch"
XD=$(find "$WORK/patch" -name '*.xdelta' | head -1)
[ -n "$XD" ] || { echo "no .xdelta file in the zip" >&2; exit 1; }

mkdir -p "$(dirname "$OUT")"
xdelta3 -d -f -s "$ISO" "$XD" "$OUT"
echo "built: $OUT"
echo "render with: python3 -m slp2alpha render REPLAY.slp --animelee --scale 2"
