"""Stages and the Gecko codes that remove their backgrounds.

Only stages whose background can be fully removed are allowed: anything left over would end up
baked into the "transparent" output.
"""

from __future__ import annotations

from typing import Dict, List

STAGE_NAMES: Dict[int, str] = {
    2: "Fountain of Dreams",
    3: "Pokémon Stadium",
    8: "Yoshi's Story",
    28: "Dream Land",
    31: "Battlefield",
    32: "Final Destination",
}

# Stage id -> names of the codes (from Resources/*.txt) that remove that stage's background.
BACKGROUND_CODES: Dict[int, List[str]] = {
    28: ["Disable Dreamland Background"],
    31: ["Disable Battlefield Background + Particles"],
}

# Stages checked in characters-only mode (the stage isn't drawn at all). Elsewhere, stage-spawned items
# and enemies (Klaptraps, Goombas, Arwings...) would still show.
CHARACTERS_ONLY_TESTED = (2, 3, 8, 28, 31, 32)


def stage_name(stage_id: int) -> str:
    return STAGE_NAMES.get(stage_id, f"stage {stage_id}")


def is_supported(stage_id: int) -> bool:
    return stage_id in BACKGROUND_CODES


def supported_stage_names() -> List[str]:
    return [stage_name(s) for s in sorted(BACKGROUND_CODES)]
