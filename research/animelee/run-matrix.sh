#!/bin/sh
# Characters-only comparison (vanilla vs Animelee) over a spread of stages and characters.
#   run-matrix.sh VANILLA.iso ANIMELEE.iso OUT_DIR
V="$1"; A="$2"; OUT="$3"
C="$HOME/Library/Caches/AlphaSolveVideo/test-replays"
cd "$(dirname "$0")" || exit 1
for r in DishonestMuddyCoyote:BF_fox_falco LimpYearlyFly:FD_ics_sheik BothGreatFly:FoD_falco_pikachu \
         DistortedOblongCrab:PS_pikachu_gw DentalCorruptLobster:DL_peach_falcon RichAuthenticGull:YS_falco_puff; do
  f=${r%%:*}; name=${r##*:}
  echo "=== $name ($f)"
  python3 compare.py "$C/$f.slp" --vanilla "$V" --animelee "$A" --out "$OUT/$name" -- --characters-only
done
