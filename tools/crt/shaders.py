"""The shaders render_video.py draws, one profile each: preset, Blender chain, named looks and the parameters a look
takes at a given size.

    guest       crt-guest-advanced by guest(r) (the default)
    guest-ntsc  its NTSC variant: a composite-video signal in front of the same CRT
    megatron    Sony Megatron Colour Video Monitor v2 by MajorPainTheCactus, in SDR
    royale      CRT Royale by TroggleMonkey

The looks and the parameters come from the crt-royale TouchDesigner project's render profiles
(pipelines/<name>/video.py, params_ex), which worked them out against the original shaders. Each shader's first look
is its default: "grille", an aperture grille. Standard library only, like the rest of tools/crt.
"""

from __future__ import annotations

import functools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import vendor_shaders

HERE = Path(__file__).resolve().parent
SLANG = vendor_shaders.VENDORED
CHAINS = HERE / "blender-chain"
DEFAULT = "guest"


class ShaderError(ValueError):
    pass


@dataclass(frozen=True)
class Context:
    """What a profile needs to know about the picture: the CRT's size, the size of the frames it gets, the triad pitch
    asked for (None: the look's own), the screen's aspect and whether it's the physical-pixels mode."""
    out_w: int
    out_h: int
    src_w: int
    src_h: int
    mask: str
    triad_px: Optional[float] = None
    aspect_x: float = 1.0
    aspect_y: float = 1.0
    physical: bool = False
    scale: Optional[int] = None

    @property
    def lines(self) -> int:
        return self.src_h


Params = Dict[str, object]


@dataclass(frozen=True)
class Shader:
    id: str
    name: str
    preset: Path                           # the vendored .slangp
    looks: Tuple[Tuple[str, str], ...]     # (name, what it is), the first is the default
    params: Callable[[Context], Params]
    temporal: bool = False                 # state across frames: needs one chain for the whole video
    frame_parity: bool = False             # the frame count's parity changes the picture
    afterglow_off: Params = field(default_factory=dict)   # what turns its afterglow off ({}: it has none)
    default_triad: Optional[Callable[[int, int], float]] = None   # the triad it draws when none is asked for

    @property
    def chain(self) -> Path:
        """Its Blender chain: the preset as librashader-cli compiles it (vendor_chain.py)."""
        return CHAINS / self.id

    @property
    def masks(self) -> Tuple[str, ...]:
        return tuple(name for name, _ in self.looks)

    @property
    def default_mask(self) -> str:
        return self.looks[0][0]

    def check_mask(self, mask: Optional[str]) -> str:
        """The look asked for, or the default; a ShaderError if this shader hasn't it."""
        mask = mask or self.default_mask
        if mask not in self.masks:
            raise ShaderError(f"{self.id} has no {mask!r} look: it has {', '.join(self.masks)}")
        return mask


def format_params(params: Params, extra: str = "") -> str:
    """`k=v,...` for librashader-cli and blender_crt.py, with `extra` (more `k=v,...`) last: a key already there takes
    the new value in its place."""
    out = {k: str(v) for k, v in params.items()}
    for kv in filter(None, (s.strip() for s in extra.split(","))):
        key, sep, value = kv.partition("=")
        if not sep or not key.strip() or not value.strip():
            raise ShaderError(f"a shader parameter is name=value, not {kv!r}")
        out[key.strip()] = value.strip()
    return ",".join(f"{k}={v}" for k, v in out.items())


# ---------------------------------------------------------------- CRT Royale (as render_video.py has always drawn it)
ROYALE_MASKS = {"grille": 0, "slot": 1, "shadow": 2}


def royale_triad(out_w: int, out_h: int) -> float:
    """3 px at 1280 px wide, scaled with the width."""
    return round(3.0 * out_w / 1280.0 * 8) / 8


def royale_params(ctx: Context) -> Params:
    return {"mask_type": ROYALE_MASKS[ctx.mask],
            "mask_triad_size_desired": ctx.triad_px or royale_triad(ctx.out_w, ctx.out_h),
            "interlace_detect_toggle": 0, "geom_aspect_ratio_x": ctx.aspect_x, "geom_aspect_ratio_y": ctx.aspect_y}


# ---------------------------------------------------------------- crt-guest-advanced (pipelines/guest_advanced/video.py)
# The mask state every look starts from, so that no look keeps another's slot or shift settings
GUEST_MASK_BASE = dict(shadowMask=6, masksize=1, mask_zoom=0, mzoom_sh=0, mshift=0, mask_layout=0, maskstr=0.3,
                       mcut=1.1, maskboost=1.0, slotmask=0, slotmask1=0, slotwidth=0, double_slot=2, slotms=1)
GUEST_MASKS: Dict[str, Params] = {
    "grille": dict(shadowMask=6, maskstr=0.5),
    "grille-soft": dict(shadowMask=6, maskstr=0.3),
    "grille-strong": dict(shadowMask=6, maskstr=0.8),
    "grille-wide": dict(shadowMask=6, masksize=2, maskstr=0.5),
    "slot": dict(shadowMask=6, maskstr=0.5, slotmask=0.7, slotmask1=0.85, slotms=2, double_slot=2),
    "shadow": dict(shadowMask=6, maskstr=0.5, mshift=1.0),
    "cgwg": dict(shadowMask=0, maskstr=0.3),
    "lottes-grille": dict(shadowMask=2),
    "lottes-shadow": dict(shadowMask=1),
    "rgbx": dict(shadowMask=10, maskstr=0.5),
    "rrggbbx": dict(shadowMask=12, maskstr=0.5),
    "none": dict(shadowMask=-1),
}
GUEST_LOOKS = (
    ("grille", "aperture grille, R | G | B stripes 3 px, strength 0.5 (full on dark pixels)"),
    ("grille-soft", "the same at guest's own strength, 0.3"),
    ("grille-strong", "the same at 0.8: coloured stripes even on white"),
    ("grille-wide", "6 px grille, 2 px stripes: a small TV's pitch"),
    ("slot", "the grille cut by staggered slot gaps"),
    ("shadow", "the grille shifted half a triad every other row: delta-like dots"),
    ("cgwg", "the shader's own default: 2 px magenta / green, 30%"),
    ("lottes-grille", "Lottes's RGB grille (never black)"),
    ("lottes-shadow", "Lottes's compressed TV shadow mask, 3 px x 2 rows"),
    ("rgbx", "black, R, G, B: 4 px"),
    ("rrggbbx", "black, R, R, G, G, B, B: 7 px, coarse"),
    ("none", "no mask: scanlines, bloom and glow only"),
)
# On top of the shader's defaults: progressive video (no interlace emulation, even from 375 lines), and the blurred
# picture added back through the mask (bloom 0.5, bmask1 1), which brightens it without washing out the stripes
GUEST_LOOK = dict(interm=0, bloom=0.5, bmask1=1.0)
# The horizontal period of each shadowMask pattern at masksize 1 (the whole part of the shader's mwidths[])
GUEST_PERIOD = (2, 3, 3, 6, 6, 2, 3, 2, 3, 3, 4, 4, 7, 6, 5)
GUEST_AFTERGLOW_OFF = {"AS": 0.0}   # pre-shaders-afterglow.slang: the afterglow's strength


def guest_mask_size(base: int, period: float, exact: bool) -> Tuple[int, float]:
    """(masksize, mask_zoom) for a mask whose period is `base` px at masksize 1 and should be `period` px. The shader's
    period is base * masksize + mask_zoom, the zoom only counting when it's over 0.75 (it then interpolates the
    columns); masksize 1 to 4, mask_zoom -10 to 6. Not exact: a whole zoom, dropped up to 0.75 (crisp, within 0.75
    px). Exact: the period itself, for a mask that has to stay on a pixel grid (physical pixels)."""
    period = max(float(period), 2.0)
    ms = max(1, min(4, int(period // base)))
    zoom = period - base * ms
    if not exact:
        zoom = float(round(zoom))
        return ms, (zoom if abs(zoom) > 0.75 else 0.0)
    if 1e-6 < abs(zoom) <= 0.75:   # too small to zoom: the next mask size, zoomed down
        ms = ms + 1 if ms < 4 else ms - 1
        zoom = period - base * ms
    return ms, max(-10.0, min(6.0, round(zoom, 4)))


def guest_params(ctx: Context) -> Params:
    """The look, with its mask's period: the triad pitch asked for, exactly, or the look's own period scaled with the
    smaller side of the CRT / 1280. Scanlines need nothing: guest draws one beam per source row. It has no aspect
    parameter: the picture fills the CRT."""
    p: Params = dict(GUEST_LOOK)
    p.update(GUEST_MASK_BASE)
    p.update(GUEST_MASKS[ctx.mask])
    t = int(p["shadowMask"])
    if t < 0:
        return p
    base = GUEST_PERIOD[t]
    if ctx.triad_px:
        ms, zoom = guest_mask_size(base, ctx.triad_px, exact=True)
    else:
        ms, zoom = guest_mask_size(base, base * p["masksize"] * min(ctx.out_w, ctx.out_h) / 1280.0, exact=False)
    p["masksize"], p["mask_zoom"] = ms, zoom
    zoomed = abs(zoom) > 0.75
    if zoomed:
        p["mzoom_sh"] = 1.0   # sharpens the interpolated columns, which are pastel otherwise
    period = base * ms + (zoom if zoomed else 0.0)
    if p["slotmask"] + p["slotmask1"] > 0:
        p["slotwidth"] = period if zoomed else 0                         # the slots follow fractional triads
        p["slotms"] = max(1, min(4, int(round(2.0 * period / 3.0))))   # slots about 2.7 triads tall
    return p


def guest_ntsc_params(ctx: Context) -> Params:
    """guest's, but below 375 lines the NTSC preset keeps its own interlace mode (2), which does nothing there."""
    p = guest_params(ctx)
    if ctx.lines < 375:
        p.pop("interm", None)
    return p


# ---------------------------------------------------------------- Sony Megatron v2, SDR (pipelines/megatron/params.py)
# Our SDR adaptation of the v2 default preset: a pure 2.2 power out (the inverse of its 2.22 decode, as upstream's
# -sdr preset has it), and brightness at least 0.2, which keeps the tone curve neutral. The mask stays at full
# strength: the picture keeps about a fifth of the light, as the shader is designed for an HDR display.
MEGATRON_OURS = {"hcrt_colour_space": 2, "hcrt_brightness": 0.2}
MEGATRON_SDR_MIN_BRIGHTNESS = 0.2
MEGATRON_MASKS: Dict[str, Params] = {
    "grille": dict(hcrt_crt_screen_type=0, hcrt_lcd_resolution=1, hcrt_crt_resolution=1, hcrt_lcd_subpixel=0),
    "slot": dict(hcrt_crt_screen_type=2, hcrt_lcd_resolution=1, hcrt_crt_resolution=1, hcrt_lcd_subpixel=0),
    "shadow": dict(hcrt_crt_screen_type=1, hcrt_lcd_resolution=1, hcrt_crt_resolution=1, hcrt_lcd_subpixel=0),
    "grille3": dict(hcrt_crt_screen_type=0, hcrt_lcd_resolution=1, hcrt_crt_resolution=2, hcrt_lcd_subpixel=2),
}
# The upstream display presets offered as looks (vendor_shaders.MEGATRON_DISPLAYS): their values are in chain.json
MEGATRON_LOOKS = (
    ("grille", "aperture grille R G B X, 4 px a triad (1 black column)"),
    ("slot", "slot mask: R G B X columns, a black row every 6, staggered (8x6 tile)"),
    ("shadow", "shadow mask: 2 px dots, 6x4 tile"),
    ("grille3", "finer aperture grille R G B, 3 px a triad, no black column"),
    ("pvm2730", "Sony PVM-2730 Trinitron: 600 TVL grille, red misconvergence, NTSC-J colours, D93 white"),
    ("pvm20l4", "Sony PVM-20L4 Trinitron: 600 TVL grille, very thin sharp beams (the darkest)"),
    ("pvm1910", "Sony PVM-1910: 300 TVL grille, coarse, NTSC-J"),
    ("mx8000", "Bang & Olufsen MX8000: 600 TVL slot mask, soft wide beams"),
)
# Megatron's patterns are fixed, per output pixel, so a triad pitch picks the nearest of them, for the look's screen
# type. Pitch -> (hcrt_lcd_resolution, hcrt_crt_resolution, hcrt_lcd_subpixel), in R G B order. The 2 px patterns
# are magenta / green, not a triad: only below 2.5 px.
MEGATRON_PITCHES = {
    0: {2: (1, 3, 0), 3: (1, 2, 2), 4: (1, 1, 0), 5: (2, 2, 0), 7: (1, 0, 0), 13: (2, 0, 0)},   # aperture grille
    1: {2: (1, 2, 0), 6: (1, 1, 0), 12: (1, 0, 0)},                                              # shadow mask (dots)
    2: {2: (1, 3, 0), 3: (1, 2, 2), 4: (1, 1, 0), 5: (2, 2, 0), 7: (1, 0, 0)},                  # slot mask (columns)
}


@functools.lru_cache(maxsize=None)
def _chain_looks(path: Path, mtime: float) -> Dict[str, Params]:
    return json.loads(path.read_text(encoding="utf-8")).get("looks") or {}


def megatron_display(look: str) -> Params:
    """A display preset's values (chain.json's "looks", which vendor_chain.py writes from the vendored presets)."""
    path = CHAINS / "megatron" / "chain.json"
    try:
        looks = _chain_looks(path, path.stat().st_mtime)
    except (OSError, ValueError) as e:
        raise ShaderError(f"Megatron's {look} look needs {path}: {e}")
    if look not in looks:
        raise ShaderError(f"{path} has no {look!r} look")
    return dict(sorted(looks[look].items()))


def megatron_mask_for_pitch(screen: int, triad_px: float) -> Tuple[int, int, int, int]:
    """(hcrt_lcd_resolution, hcrt_crt_resolution, hcrt_lcd_subpixel, pitch) nearest to triad_px, by ratio."""
    cands = {k: v for k, v in MEGATRON_PITCHES[int(screen)].items() if k > 2 or triad_px < 2.5}
    pitch = min(cands, key=lambda k: abs(math.log(k / float(triad_px))))
    return cands[pitch] + (pitch,)


def megatron_look(look: str) -> Params:
    if look in MEGATRON_MASKS:
        p: Params = dict(MEGATRON_OURS)
        p.update(MEGATRON_MASKS[look])
        return p
    p = megatron_display(look)
    p["hcrt_colour_space"] = MEGATRON_OURS["hcrt_colour_space"]
    p["hcrt_brightness"] = max(float(p.get("hcrt_brightness", 0.0)), MEGATRON_SDR_MIN_BRIGHTNESS)
    return p


def megatron_params(ctx: Context) -> Params:
    """The look, its mask re-picked for the triad pitch when one is asked for. Nothing else depends on the size: the
    beam follows the source rows, and the picture fills the CRT (no aspect parameter)."""
    p = megatron_look(ctx.mask)
    if ctx.triad_px:
        res, tvl, sub, _ = megatron_mask_for_pitch(int(p.get("hcrt_crt_screen_type", 0)), ctx.triad_px)
        p.update(hcrt_lcd_resolution=res, hcrt_crt_resolution=tvl, hcrt_lcd_subpixel=sub)
    return p


# ---------------------------------------------------------------- the profiles
def _preset(shader_id: str) -> Path:
    return SLANG / vendor_shaders.PRESETS[shader_id]


SHADERS: Dict[str, Shader] = {s.id: s for s in (
    Shader("guest", "crt-guest-advanced", _preset("guest"), GUEST_LOOKS, guest_params, temporal=True,
           afterglow_off=GUEST_AFTERGLOW_OFF),
    # its chroma phase alternates with the frame count
    Shader("guest-ntsc", "crt-guest-advanced-ntsc", _preset("guest-ntsc"), GUEST_LOOKS, guest_ntsc_params,
           temporal=True, frame_parity=True, afterglow_off=GUEST_AFTERGLOW_OFF),
    Shader("megatron", "Sony Megatron v2 (SDR)", _preset("megatron"), MEGATRON_LOOKS, megatron_params),
    Shader("royale", "CRT Royale", _preset("royale"),
           (("grille", "aperture grille"), ("slot", "slot mask"), ("shadow", "EDP shadow mask")), royale_params,
           default_triad=royale_triad),
)}
ALL_MASKS = tuple(dict.fromkeys(m for s in SHADERS.values() for m in s.masks))


def get(shader_id: Optional[str]) -> Shader:
    shader_id = shader_id or DEFAULT
    if shader_id not in SHADERS:
        raise ShaderError(f"no shader {shader_id!r}: choose from {', '.join(SHADERS)}")
    return SHADERS[shader_id]


def by_preset(preset: Path) -> Optional[Shader]:
    """The vendored shader whose preset this is, if any."""
    preset = Path(preset).resolve()
    return next((s for s in SHADERS.values() if s.preset.resolve() == preset), None)


def describe_looks() -> str:
    """Every shader's looks, for --list-masks."""
    out = []
    for s in SHADERS.values():
        out.append(f"{s.id} ({s.name})" + (", the default" if s.id == DEFAULT else "") + ":")
        out += [f"  {name:14s} {what}" + ("  (default)" if i == 0 else "") for i, (name, what) in enumerate(s.looks)]
    return "\n".join(out)
