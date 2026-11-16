"""Gecko code lists in Dolphin's text format ("$Name [Author]" headers followed by code lines)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

_AUTHOR_SUFFIX = re.compile(r"\s*\[[^\]]*\]\s*$")


@dataclass
class GeckoCode:
    name: str
    """Name without the "[Author]" suffix; this is what Dolphin's [Gecko_Enabled] section expects."""
    title: str
    """The full header line, including the leading "$"."""
    lines: List[str] = field(default_factory=list)


def parse_codes(text: str) -> Dict[str, GeckoCode]:
    codes: Dict[str, GeckoCode] = {}
    current = None
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.startswith("$"):
            name = _AUTHOR_SUFFIX.sub("", line[1:]).strip()
            current = GeckoCode(name=name, title=line)
            codes[name] = current
        elif current is not None and line:
            current.lines.append(line)
    return codes


def load_codes(*paths: Path) -> Dict[str, GeckoCode]:
    codes: Dict[str, GeckoCode] = {}
    for path in paths:
        codes.update(parse_codes(Path(path).read_text(encoding="utf-8")))
    return codes


def gecko_section(codes: Dict[str, GeckoCode]) -> str:
    """Body of a [Gecko] section containing every code."""
    out = []
    for code in codes.values():
        out.append(code.title)
        out.extend(code.lines)
    return "\n".join(out) + "\n"
