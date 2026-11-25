#!/usr/bin/env python3
"""Tests for the shader profiles (shaders.py) and how render_video.py uses them. test_crt.py runs these too.

    python3 tools/crt/test_shaders.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_video as rv  # noqa: E402
import shaders  # noqa: E402
import vendor_shaders  # noqa: E402
from slp2alpha import locate  # noqa: E402

CONTEXTS = {
    "slp": dict(out_w=3504, out_h=2880, src_w=584, src_h=480, triad_px=3.0, aspect_x=1.217, physical=True, scale=6),
    "std": dict(out_w=1280, out_h=1280, src_w=288, src_h=288),
    "wide": dict(out_w=1920, out_h=1080, src_w=240, src_h=240, aspect_x=1.778),
    "phys8": dict(out_w=5120, out_h=3840, src_w=640, src_h=480, triad_px=4.0, aspect_x=1.333, physical=True, scale=8),
    "frac": dict(out_w=1280, out_h=1280, src_w=288, src_h=288, triad_px=2.5),
}

# The parameter strings the crt-royale TouchDesigner project's own profiles give (pipelines/<name>/video.py
# params_ex, joined k=v as its render_video.py does), computed once from its modules on 25 November 2026.
# Contexts: slp (slp2video: 584x480 -> 3504x2880, scale 6, triad 3), std (render_video's standard 1280: 288
# lines), wide (1920x1080, 240 lines), phys8 (640x480 at scale 8, triad 4), frac (1280 with --triad 2.5).
TD_PARAMS = {
    'guest|slp|grille': "interm=0,bloom=0.5,bmask1=1.0,shadowMask=6,masksize=1,mask_zoom=0.0,mzoom_sh=0,mshift=0,"
        "mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1",
    'guest|std|grille': "interm=0,bloom=0.5,bmask1=1.0,shadowMask=6,masksize=1,mask_zoom=0.0,mzoom_sh=0,mshift=0,"
        "mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1",
    'guest|wide|grille': "interm=0,bloom=0.5,bmask1=1.0,shadowMask=6,masksize=1,mask_zoom=0.0,mzoom_sh=0,mshift=0,"
        "mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1",
    'guest|phys8|grille': "interm=0,bloom=0.5,bmask1=1.0,shadowMask=6,masksize=1,mask_zoom=1.0,mzoom_sh=1.0,mshift=0,"
        "mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1",
    'guest|frac|grille': "interm=0,bloom=0.5,bmask1=1.0,shadowMask=6,masksize=2,mask_zoom=-3.5,mzoom_sh=1.0,mshift=0,"
        "mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1",
    'guest-ntsc|slp|grille': "interm=0,bloom=0.5,bmask1=1.0,shadowMask=6,masksize=1,mask_zoom=0.0,mzoom_sh=0,"
        "mshift=0,mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,"
        "slotms=1",
    'guest-ntsc|std|grille': "bloom=0.5,bmask1=1.0,shadowMask=6,masksize=1,mask_zoom=0.0,mzoom_sh=0,mshift=0,"
        "mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1",
    'guest-ntsc|wide|grille': "bloom=0.5,bmask1=1.0,shadowMask=6,masksize=1,mask_zoom=0.0,mzoom_sh=0,mshift=0,"
        "mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1",
    'guest-ntsc|phys8|grille': "interm=0,bloom=0.5,bmask1=1.0,shadowMask=6,masksize=1,mask_zoom=1.0,mzoom_sh=1.0,"
        "mshift=0,mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,"
        "slotms=1",
    'guest-ntsc|frac|grille': "bloom=0.5,bmask1=1.0,shadowMask=6,masksize=2,mask_zoom=-3.5,mzoom_sh=1.0,mshift=0,"
        "mask_layout=0,maskstr=0.5,mcut=1.1,maskboost=1.0,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1",
    'megatron|slp|grille': "hcrt_colour_space=2,hcrt_brightness=0.2,hcrt_crt_screen_type=0,hcrt_lcd_resolution=1,"
        "hcrt_crt_resolution=2,hcrt_lcd_subpixel=2",
    'megatron|slp|pvm2730': "hcrt_blue_beam_attack=0.45,hcrt_blue_beam_sharpness=1.9,hcrt_blue_scanline_attack=0.65,"
        "hcrt_blue_scanline_max=1.0,hcrt_blue_scanline_min=0.72,hcrt_blue_vertical_convergence=0.0,"
        "hcrt_brightness=0.2,hcrt_colour_system=3.0,hcrt_crt_screen_type=0.0,hcrt_green_beam_attack=0.8,"
        "hcrt_green_beam_sharpness=1.6,hcrt_green_scanline_attack=0.13,hcrt_green_scanline_max=0.9,"
        "hcrt_green_scanline_min=0.55,hcrt_green_vertical_convergence=0.0,hcrt_red_beam_attack=0.72,"
        "hcrt_red_beam_sharpness=1.75,hcrt_red_scanline_attack=0.65,hcrt_red_scanline_max=0.82,"
        "hcrt_red_scanline_min=0.55,hcrt_red_vertical_convergence=-0.14,hcrt_colour_space=2,hcrt_lcd_resolution=1,"
        "hcrt_crt_resolution=2,hcrt_lcd_subpixel=2",
    'megatron|slp|pvm20l4': "hcrt_blue_beam_attack=1.0,hcrt_blue_beam_sharpness=2.0,hcrt_blue_scanline_attack=0.15,"
        "hcrt_blue_scanline_max=0.4,hcrt_blue_scanline_min=0.25,hcrt_blue_vertical_convergence=0.0,"
        "hcrt_brightness=0.2,hcrt_colour_system=3.0,hcrt_crt_resolution=2,hcrt_crt_screen_type=0.0,"
        "hcrt_green_beam_attack=1.0,hcrt_green_beam_sharpness=2.0,hcrt_green_scanline_attack=0.15,"
        "hcrt_green_scanline_max=0.4,hcrt_green_scanline_min=0.25,hcrt_green_vertical_convergence=0.0,"
        "hcrt_red_beam_attack=1.0,hcrt_red_beam_sharpness=2.0,hcrt_red_scanline_attack=0.15,"
        "hcrt_red_scanline_max=0.4,hcrt_red_scanline_min=0.25,hcrt_red_vertical_convergence=0.1,hcrt_colour_space=2,"
        "hcrt_lcd_resolution=1,hcrt_lcd_subpixel=2",
    'megatron|slp|pvm1910': "hcrt_blue_beam_attack=0.45,hcrt_blue_beam_sharpness=1.4,hcrt_blue_scanline_attack=0.35,"
        "hcrt_blue_scanline_max=0.75,hcrt_blue_scanline_min=0.4,hcrt_blue_vertical_convergence=0.0,"
        "hcrt_brightness=0.2,hcrt_colour_system=3.0,hcrt_crt_resolution=2,hcrt_crt_screen_type=0.0,"
        "hcrt_green_beam_attack=0.8,hcrt_green_beam_sharpness=1.4,hcrt_green_scanline_attack=0.35,"
        "hcrt_green_scanline_max=1.0,hcrt_green_scanline_min=0.4,hcrt_green_vertical_convergence=-0.15,"
        "hcrt_red_beam_attack=0.72,hcrt_red_beam_sharpness=1.4,hcrt_red_scanline_attack=0.35,"
        "hcrt_red_scanline_max=0.75,hcrt_red_scanline_min=0.4,hcrt_red_vertical_convergence=0.0,hcrt_saturation=0.1,"
        "hcrt_colour_space=2,hcrt_lcd_resolution=1,hcrt_lcd_subpixel=2",
    'megatron|slp|mx8000': "hcrt_blue_beam_attack=1.75,hcrt_blue_beam_sharpness=1.6,hcrt_blue_scanline_attack=0.5,"
        "hcrt_blue_scanline_max=0.9,hcrt_blue_scanline_min=0.65,hcrt_crt_screen_type=2.0,hcrt_green_beam_attack=1.75,"
        "hcrt_green_beam_sharpness=1.6,hcrt_green_scanline_attack=0.5,hcrt_green_scanline_max=0.9,"
        "hcrt_green_scanline_min=0.65,hcrt_red_beam_attack=1.75,hcrt_red_beam_sharpness=1.6,"
        "hcrt_red_scanline_attack=0.5,hcrt_red_scanline_max=0.9,hcrt_red_scanline_min=0.65,hcrt_colour_space=2,"
        "hcrt_brightness=0.2,hcrt_lcd_resolution=1,hcrt_crt_resolution=2,hcrt_lcd_subpixel=2",
    'megatron|std|grille': "hcrt_colour_space=2,hcrt_brightness=0.2,hcrt_crt_screen_type=0,hcrt_lcd_resolution=1,"
        "hcrt_crt_resolution=1,hcrt_lcd_subpixel=0",
    'megatron|std|pvm2730': "hcrt_blue_beam_attack=0.45,hcrt_blue_beam_sharpness=1.9,hcrt_blue_scanline_attack=0.65,"
        "hcrt_blue_scanline_max=1.0,hcrt_blue_scanline_min=0.72,hcrt_blue_vertical_convergence=0.0,"
        "hcrt_brightness=0.2,hcrt_colour_system=3.0,hcrt_crt_screen_type=0.0,hcrt_green_beam_attack=0.8,"
        "hcrt_green_beam_sharpness=1.6,hcrt_green_scanline_attack=0.13,hcrt_green_scanline_max=0.9,"
        "hcrt_green_scanline_min=0.55,hcrt_green_vertical_convergence=0.0,hcrt_red_beam_attack=0.72,"
        "hcrt_red_beam_sharpness=1.75,hcrt_red_scanline_attack=0.65,hcrt_red_scanline_max=0.82,"
        "hcrt_red_scanline_min=0.55,hcrt_red_vertical_convergence=-0.14,hcrt_colour_space=2",
    'megatron|std|pvm20l4': "hcrt_blue_beam_attack=1.0,hcrt_blue_beam_sharpness=2.0,hcrt_blue_scanline_attack=0.15,"
        "hcrt_blue_scanline_max=0.4,hcrt_blue_scanline_min=0.25,hcrt_blue_vertical_convergence=0.0,"
        "hcrt_brightness=0.2,hcrt_colour_system=3.0,hcrt_crt_resolution=1.0,hcrt_crt_screen_type=0.0,"
        "hcrt_green_beam_attack=1.0,hcrt_green_beam_sharpness=2.0,hcrt_green_scanline_attack=0.15,"
        "hcrt_green_scanline_max=0.4,hcrt_green_scanline_min=0.25,hcrt_green_vertical_convergence=0.0,"
        "hcrt_red_beam_attack=1.0,hcrt_red_beam_sharpness=2.0,hcrt_red_scanline_attack=0.15,"
        "hcrt_red_scanline_max=0.4,hcrt_red_scanline_min=0.25,hcrt_red_vertical_convergence=0.1,hcrt_colour_space=2",
    'megatron|std|pvm1910': "hcrt_blue_beam_attack=0.45,hcrt_blue_beam_sharpness=1.4,hcrt_blue_scanline_attack=0.35,"
        "hcrt_blue_scanline_max=0.75,hcrt_blue_scanline_min=0.4,hcrt_blue_vertical_convergence=0.0,"
        "hcrt_brightness=0.2,hcrt_colour_system=3.0,hcrt_crt_resolution=0.0,hcrt_crt_screen_type=0.0,"
        "hcrt_green_beam_attack=0.8,hcrt_green_beam_sharpness=1.4,hcrt_green_scanline_attack=0.35,"
        "hcrt_green_scanline_max=1.0,hcrt_green_scanline_min=0.4,hcrt_green_vertical_convergence=-0.15,"
        "hcrt_red_beam_attack=0.72,hcrt_red_beam_sharpness=1.4,hcrt_red_scanline_attack=0.35,"
        "hcrt_red_scanline_max=0.75,hcrt_red_scanline_min=0.4,hcrt_red_vertical_convergence=0.0,hcrt_saturation=0.1,"
        "hcrt_colour_space=2",
    'megatron|std|mx8000': "hcrt_blue_beam_attack=1.75,hcrt_blue_beam_sharpness=1.6,hcrt_blue_scanline_attack=0.5,"
        "hcrt_blue_scanline_max=0.9,hcrt_blue_scanline_min=0.65,hcrt_crt_screen_type=2.0,hcrt_green_beam_attack=1.75,"
        "hcrt_green_beam_sharpness=1.6,hcrt_green_scanline_attack=0.5,hcrt_green_scanline_max=0.9,"
        "hcrt_green_scanline_min=0.65,hcrt_red_beam_attack=1.75,hcrt_red_beam_sharpness=1.6,"
        "hcrt_red_scanline_attack=0.5,hcrt_red_scanline_max=0.9,hcrt_red_scanline_min=0.65,hcrt_colour_space=2,"
        "hcrt_brightness=0.2",
    'megatron|wide|grille': "hcrt_colour_space=2,hcrt_brightness=0.2,hcrt_crt_screen_type=0,hcrt_lcd_resolution=1,"
        "hcrt_crt_resolution=1,hcrt_lcd_subpixel=0",
    'megatron|phys8|grille': "hcrt_colour_space=2,hcrt_brightness=0.2,hcrt_crt_screen_type=0,hcrt_lcd_resolution=1,"
        "hcrt_crt_resolution=1,hcrt_lcd_subpixel=0",
    'megatron|frac|grille': "hcrt_colour_space=2,hcrt_brightness=0.2,hcrt_crt_screen_type=0,hcrt_lcd_resolution=1,"
        "hcrt_crt_resolution=2,hcrt_lcd_subpixel=2",
}
# Every other look: the values that differ from the grille's in the same context (same keys, same order)
TD_CHANGES = {
    'guest|slp|grille-soft': 'maskstr=0.3',
    'guest|slp|grille-strong': 'maskstr=0.8',
    'guest|slp|grille-wide': '',
    'guest|slp|slot': 'slotmask=0.7,slotmask1=0.85,slotms=2',
    'guest|slp|shadow': 'mshift=1.0',
    'guest|slp|cgwg': 'shadowMask=0,mask_zoom=1.0,mzoom_sh=1.0,maskstr=0.3',
    'guest|slp|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest|slp|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest|slp|rgbx': 'shadowMask=10,mask_zoom=-1.0,mzoom_sh=1.0',
    'guest|slp|rrggbbx': 'shadowMask=12,mask_zoom=-4.0,mzoom_sh=1.0',
    'guest|slp|none': 'shadowMask=-1,mask_zoom=0,maskstr=0.3',
    'guest|std|grille-soft': 'maskstr=0.3',
    'guest|std|grille-strong': 'maskstr=0.8',
    'guest|std|grille-wide': 'masksize=2',
    'guest|std|slot': 'slotmask=0.7,slotmask1=0.85,slotms=2',
    'guest|std|shadow': 'mshift=1.0',
    'guest|std|cgwg': 'shadowMask=0,maskstr=0.3',
    'guest|std|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest|std|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest|std|rgbx': 'shadowMask=10',
    'guest|std|rrggbbx': 'shadowMask=12',
    'guest|std|none': 'shadowMask=-1,mask_zoom=0,maskstr=0.3',
    'guest|wide|grille-soft': 'maskstr=0.3',
    'guest|wide|grille-strong': 'maskstr=0.8',
    'guest|wide|grille-wide': 'mask_zoom=2.0,mzoom_sh=1.0',
    'guest|wide|slot': 'slotmask=0.7,slotmask1=0.85,slotms=2',
    'guest|wide|shadow': 'mshift=1.0',
    'guest|wide|cgwg': 'shadowMask=0,maskstr=0.3',
    'guest|wide|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest|wide|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest|wide|rgbx': 'shadowMask=10,mask_zoom=-1.0,mzoom_sh=1.0',
    'guest|wide|rrggbbx': 'shadowMask=12,mask_zoom=-1.0,mzoom_sh=1.0',
    'guest|wide|none': 'shadowMask=-1,mask_zoom=0,maskstr=0.3',
    'guest|phys8|grille-soft': 'maskstr=0.3',
    'guest|phys8|grille-strong': 'maskstr=0.8',
    'guest|phys8|grille-wide': '',
    'guest|phys8|slot': 'slotmask=0.7,slotmask1=0.85,slotwidth=4.0,slotms=3',
    'guest|phys8|shadow': 'mshift=1.0',
    'guest|phys8|cgwg': 'shadowMask=0,masksize=2,mask_zoom=0.0,mzoom_sh=0,maskstr=0.3',
    'guest|phys8|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest|phys8|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest|phys8|rgbx': 'shadowMask=10,mask_zoom=0.0,mzoom_sh=0',
    'guest|phys8|rrggbbx': 'shadowMask=12,mask_zoom=-3.0',
    'guest|phys8|none': 'shadowMask=-1,mask_zoom=0,mzoom_sh=0,maskstr=0.3',
    'guest|frac|grille-soft': 'maskstr=0.3',
    'guest|frac|grille-strong': 'maskstr=0.8',
    'guest|frac|grille-wide': '',
    'guest|frac|slot': 'slotmask=0.7,slotmask1=0.85,slotwidth=2.5,slotms=2',
    'guest|frac|shadow': 'mshift=1.0',
    'guest|frac|cgwg': 'shadowMask=0,mask_zoom=-1.5,maskstr=0.3',
    'guest|frac|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest|frac|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest|frac|rgbx': 'shadowMask=10,masksize=1,mask_zoom=-1.5',
    'guest|frac|rrggbbx': 'shadowMask=12,masksize=1,mask_zoom=-4.5',
    'guest|frac|none': 'shadowMask=-1,masksize=1,mask_zoom=0,mzoom_sh=0,maskstr=0.3',
    'guest-ntsc|slp|grille-soft': 'maskstr=0.3',
    'guest-ntsc|slp|grille-strong': 'maskstr=0.8',
    'guest-ntsc|slp|grille-wide': '',
    'guest-ntsc|slp|slot': 'slotmask=0.7,slotmask1=0.85,slotms=2',
    'guest-ntsc|slp|shadow': 'mshift=1.0',
    'guest-ntsc|slp|cgwg': 'shadowMask=0,mask_zoom=1.0,mzoom_sh=1.0,maskstr=0.3',
    'guest-ntsc|slp|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest-ntsc|slp|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest-ntsc|slp|rgbx': 'shadowMask=10,mask_zoom=-1.0,mzoom_sh=1.0',
    'guest-ntsc|slp|rrggbbx': 'shadowMask=12,mask_zoom=-4.0,mzoom_sh=1.0',
    'guest-ntsc|slp|none': 'shadowMask=-1,mask_zoom=0,maskstr=0.3',
    'guest-ntsc|std|grille-soft': 'maskstr=0.3',
    'guest-ntsc|std|grille-strong': 'maskstr=0.8',
    'guest-ntsc|std|grille-wide': 'masksize=2',
    'guest-ntsc|std|slot': 'slotmask=0.7,slotmask1=0.85,slotms=2',
    'guest-ntsc|std|shadow': 'mshift=1.0',
    'guest-ntsc|std|cgwg': 'shadowMask=0,maskstr=0.3',
    'guest-ntsc|std|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest-ntsc|std|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest-ntsc|std|rgbx': 'shadowMask=10',
    'guest-ntsc|std|rrggbbx': 'shadowMask=12',
    'guest-ntsc|std|none': 'shadowMask=-1,mask_zoom=0,maskstr=0.3',
    'guest-ntsc|wide|grille-soft': 'maskstr=0.3',
    'guest-ntsc|wide|grille-strong': 'maskstr=0.8',
    'guest-ntsc|wide|grille-wide': 'mask_zoom=2.0,mzoom_sh=1.0',
    'guest-ntsc|wide|slot': 'slotmask=0.7,slotmask1=0.85,slotms=2',
    'guest-ntsc|wide|shadow': 'mshift=1.0',
    'guest-ntsc|wide|cgwg': 'shadowMask=0,maskstr=0.3',
    'guest-ntsc|wide|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest-ntsc|wide|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest-ntsc|wide|rgbx': 'shadowMask=10,mask_zoom=-1.0,mzoom_sh=1.0',
    'guest-ntsc|wide|rrggbbx': 'shadowMask=12,mask_zoom=-1.0,mzoom_sh=1.0',
    'guest-ntsc|wide|none': 'shadowMask=-1,mask_zoom=0,maskstr=0.3',
    'guest-ntsc|phys8|grille-soft': 'maskstr=0.3',
    'guest-ntsc|phys8|grille-strong': 'maskstr=0.8',
    'guest-ntsc|phys8|grille-wide': '',
    'guest-ntsc|phys8|slot': 'slotmask=0.7,slotmask1=0.85,slotwidth=4.0,slotms=3',
    'guest-ntsc|phys8|shadow': 'mshift=1.0',
    'guest-ntsc|phys8|cgwg': 'shadowMask=0,masksize=2,mask_zoom=0.0,mzoom_sh=0,maskstr=0.3',
    'guest-ntsc|phys8|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest-ntsc|phys8|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest-ntsc|phys8|rgbx': 'shadowMask=10,mask_zoom=0.0,mzoom_sh=0',
    'guest-ntsc|phys8|rrggbbx': 'shadowMask=12,mask_zoom=-3.0',
    'guest-ntsc|phys8|none': 'shadowMask=-1,mask_zoom=0,mzoom_sh=0,maskstr=0.3',
    'guest-ntsc|frac|grille-soft': 'maskstr=0.3',
    'guest-ntsc|frac|grille-strong': 'maskstr=0.8',
    'guest-ntsc|frac|grille-wide': '',
    'guest-ntsc|frac|slot': 'slotmask=0.7,slotmask1=0.85,slotwidth=2.5,slotms=2',
    'guest-ntsc|frac|shadow': 'mshift=1.0',
    'guest-ntsc|frac|cgwg': 'shadowMask=0,mask_zoom=-1.5,maskstr=0.3',
    'guest-ntsc|frac|lottes-grille': 'shadowMask=2,maskstr=0.3',
    'guest-ntsc|frac|lottes-shadow': 'shadowMask=1,maskstr=0.3',
    'guest-ntsc|frac|rgbx': 'shadowMask=10,masksize=1,mask_zoom=-1.5',
    'guest-ntsc|frac|rrggbbx': 'shadowMask=12,masksize=1,mask_zoom=-4.5',
    'guest-ntsc|frac|none': 'shadowMask=-1,masksize=1,mask_zoom=0,mzoom_sh=0,maskstr=0.3',
    'megatron|slp|slot': 'hcrt_crt_screen_type=2',
    'megatron|slp|shadow': 'hcrt_crt_screen_type=1,hcrt_crt_resolution=1,hcrt_lcd_subpixel=0',
    'megatron|slp|grille3': '',
    'megatron|std|slot': 'hcrt_crt_screen_type=2',
    'megatron|std|shadow': 'hcrt_crt_screen_type=1',
    'megatron|std|grille3': 'hcrt_crt_resolution=2,hcrt_lcd_subpixel=2',
    'megatron|wide|slot': 'hcrt_crt_screen_type=2',
    'megatron|wide|shadow': 'hcrt_crt_screen_type=1',
    'megatron|wide|grille3': 'hcrt_crt_resolution=2,hcrt_lcd_subpixel=2',
    'megatron|phys8|slot': 'hcrt_crt_screen_type=2',
    'megatron|phys8|shadow': 'hcrt_crt_screen_type=1',
    'megatron|phys8|grille3': '',
    'megatron|frac|slot': 'hcrt_crt_screen_type=2',
    'megatron|frac|shadow': 'hcrt_crt_screen_type=1,hcrt_crt_resolution=1,hcrt_lcd_subpixel=0',
    'megatron|frac|grille3': '',
}


def expected(key: str) -> str:
    if key in TD_PARAMS:
        return TD_PARAMS[key]
    shader, ctx, _ = key.split("|")
    values = dict(kv.split("=") for kv in TD_PARAMS[f"{shader}|{ctx}|grille"].split(","))
    values.update(kv.split("=") for kv in TD_CHANGES[key].split(",") if kv)
    return ",".join(f"{k}={v}" for k, v in values.items())


def params(key: str) -> str:
    shader, ctx, mask = key.split("|")
    return shaders.format_params(shaders.get(shader).params(shaders.Context(mask=mask, **CONTEXTS[ctx])))


class Profiles(unittest.TestCase):
    """Each profile's parameters are the TouchDesigner project's, string for string."""

    def test_every_look_in_every_context(self):
        keys = list(TD_PARAMS) + list(TD_CHANGES)
        self.assertEqual(len(keys), 148)
        for key in keys:
            self.assertEqual(params(key), expected(key), key)

    def test_each_shader_has_every_look_tested(self):
        for shader in ("guest", "guest-ntsc", "megatron"):
            tested = {k.split("|")[2] for k in list(TD_PARAMS) + list(TD_CHANGES) if k.startswith(shader + "|slp|")}
            self.assertEqual(tested, set(shaders.get(shader).masks), shader)

    def test_grille_first(self):
        for s in shaders.SHADERS.values():
            self.assertEqual(s.default_mask, "grille", s.id)
            self.assertTrue(s.preset.is_file(), s.preset)
            self.assertTrue((s.chain / "chain.json").is_file(), s.chain)
        self.assertEqual(set(shaders.SHADERS), set(vendor_shaders.PRESETS))
        self.assertEqual(shaders.DEFAULT, "guest")

    def test_megatron_looks_are_its_display_presets(self):
        self.assertEqual(shaders.get("megatron").masks[4:], tuple(vendor_shaders.MEGATRON_DISPLAYS))

    def test_megatron_pitches(self):
        self.assertEqual(shaders.megatron_mask_for_pitch(0, 3), (1, 2, 2, 3))     # grille3's table
        self.assertEqual(shaders.megatron_mask_for_pitch(0, 4), (1, 1, 0, 4))
        self.assertEqual(shaders.megatron_mask_for_pitch(1, 3), (1, 1, 0, 6))     # shadow: 6 px dots
        self.assertEqual(shaders.megatron_mask_for_pitch(0, 2), (1, 3, 0, 2))     # magenta / green below 2.5

    def test_guest_mask_size(self):
        self.assertEqual(shaders.guest_mask_size(3, 3.0, exact=True), (1, 0.0))
        self.assertEqual(shaders.guest_mask_size(3, 3.5, exact=True), (2, -2.5))   # 0.5 is too small to zoom
        self.assertEqual(shaders.guest_mask_size(3, 4.4, exact=False), (1, 1.0))


class Settings(unittest.TestCase):
    """render_video's settings ask the profile."""

    def test_slp2video_geometry(self):
        for shader in ("guest", "guest-ntsc", "megatron"):
            s = rv.physical_settings(584, 480, 6, shader=shader)
            self.assertEqual((s.width, s.height, s.triad, s.shader, s.mask), (3504, 2880, 3.0, shader, "grille"))
            self.assertEqual(s.params, TD_PARAMS[f"{shader}|slp|grille"], shader)

    def test_standard_1280(self):
        for shader in ("guest", "guest-ntsc", "megatron"):
            s, vf = rv.standard_settings("1280", 288, "crop", shader=shader)
            self.assertEqual((s.width, s.height, s.triad), (1280, 1280, 0.0))   # the look's own mask size
            self.assertEqual(s.params, TD_PARAMS[f"{shader}|std|grille"], shader)
            self.assertIn("scale=288:288", vf)
        s, _ = rv.standard_settings("1920x1080", 240, mask="slot", shader="guest")
        self.assertEqual(s.params, expected("guest|wide|slot"))
        s, _ = rv.standard_settings("1280", 288, mask="rgbx", triad=2.5, shader="guest")
        self.assertEqual(s.params, expected("guest|frac|rgbx"))

    def test_guest_is_the_default(self):
        self.assertEqual(rv.physical_settings(584, 480, 6).params, TD_PARAMS["guest|slp|grille"])

    def test_royale_unchanged(self):
        s = rv.physical_settings(584, 480, 6, shader="royale")
        self.assertEqual(s.params, "mask_type=0,mask_triad_size_desired=3.0,interlace_detect_toggle=0,"
                                   "geom_aspect_ratio_x=1.217,geom_aspect_ratio_y=1.0")
        s, _ = rv.standard_settings("1920x1080", 240, mask="shadow", shader="royale")
        self.assertEqual((s.triad, s.params), (4.5, "mask_type=2,mask_triad_size_desired=4.5,interlace_detect_toggle=0,"
                                                    "geom_aspect_ratio_x=1.778,geom_aspect_ratio_y=1.0"))
        self.assertEqual(rv.shader_params("slot", 3.0, 1.217, 1.0, "halation_weight=0.1"),
                         "mask_type=1,mask_triad_size_desired=3.0,interlace_detect_toggle=0,"
                         "geom_aspect_ratio_x=1.217,geom_aspect_ratio_y=1.0,halation_weight=0.1")

    def test_masks_are_checked_per_shader(self):
        with self.assertRaisesRegex(ValueError, "royale has no 'cgwg' look"):
            rv.physical_settings(584, 480, 6, shader="royale", mask="cgwg")
        with self.assertRaises(ValueError):
            rv.standard_settings("1280", shader="megatron", mask="grille-soft")
        self.assertEqual(rv.physical_settings(584, 480, 6, shader="megatron", mask="pvm2730").params,
                         TD_PARAMS["megatron|slp|pvm2730"])
        with self.assertRaises(ValueError):
            shaders.get("lottes")

    def test_more_params_replace_or_follow(self):
        s = rv.physical_settings(584, 480, 6, params="maskstr=0.4,glow=0.1")
        self.assertIn(",maskstr=0.4,", s.params)
        self.assertNotIn("maskstr=0.5", s.params)
        self.assertTrue(s.params.endswith(",slotms=1,glow=0.1"))
        with self.assertRaises(ValueError):
            rv.physical_settings(584, 480, 6, params="maskstr")

    def test_no_afterglow(self):
        for shader in ("guest", "guest-ntsc"):
            s = rv.physical_settings(584, 480, 6, shader=shader, afterglow=False)
            self.assertEqual(s.params, TD_PARAMS[f"{shader}|slp|grille"] + ",AS=0.0")
            self.assertFalse(s.afterglow)
        for shader in ("megatron", "royale"):   # nothing to turn off
            self.assertEqual(rv.physical_settings(584, 480, 6, shader=shader, afterglow=False).params,
                             rv.physical_settings(584, 480, 6, shader=shader).params)

    def test_list_masks(self):
        text = shaders.describe_looks()
        for s in shaders.SHADERS.values():
            self.assertIn(f"{s.id} ({s.name})", text)
        self.assertIn("pvm20l4", text)


class Runtimes(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(rv, "runtimes_of", return_value=("metal", "wgpu"))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(rv, "find_stream", return_value=None)   # whether or not it's built here
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_blender_draws_every_vendored_preset(self):
        for s in shaders.SHADERS.values():
            self.assertEqual(rv.candidates("cli", "blender", platform="linux", preset=s.preset)[0], "blender", s.id)
            self.assertEqual(rv.blender_chain(s.preset), s.chain)
        self.assertEqual(rv.candidates("cli", "blender", platform="darwin"), ["blender", "metal", "wgpu"])
        other = vendor_shaders.VENDORED / vendor_shaders.MEGATRON_DISPLAY_PRESET.format("sony-pvm-2730")
        self.assertEqual(rv.candidates("cli", "blender", platform="darwin", preset=other), ["metal", "wgpu"])

    def test_blender_gets_the_shaders_chain(self):
        for s in shaders.SHADERS.values():
            settings = rv.physical_settings(584, 480, 6, shader=s.id)
            cmd = rv.blender_command("blender", Path("luts"), 5, 7, (584, 480), settings, platform="darwin")
            self.assertEqual(cmd[cmd.index("--") + 1], str(s.chain))
        self.assertEqual(shaders.get("royale").chain, rv.BLENDER_CHAIN)

    def test_frame_count_for_librashader(self):
        settings = rv.physical_settings(4, 4, 1, shader="guest-ntsc")
        done = mock.Mock(returncode=1, stdout="", stderr="no")
        with mock.patch.object(rv.subprocess, "run", return_value=done) as run:
            for frame in (0, 1):
                with self.assertRaises(rv.CrtError):
                    rv.draw("cli", "metal", Path("p"), settings, Path("a.bmp"), Path("b.bmp"), frame)
        first, second = (c.args[0] for c in run.call_args_list)
        self.assertNotIn("-f", first)
        self.assertEqual(second[-2:], ["-f", "1"])


class NtscPhase(unittest.TestCase):
    """guest-ntsc through librashader-cli: the frames alternate their chroma phase, as in one chain. 2-phase NTSC
    (more than 300 source pixels wide) shows it: on a still picture, frames 1 and 3 match, 1 and 2 don't."""

    def test_the_phase_alternates(self):
        try:
            cli, ffmpeg = rv.find_librashader(), locate.find_ffmpeg()
        except locate.NotFound:
            raise unittest.SkipTest("no librashader-cli or ffmpeg")
        width, height = 304, 120
        settings = rv.physical_settings(width, height, 2, shader="guest-ntsc", afterglow=False)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.nut"
            subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={width}x{height}:r=60",
                            "-vf", "loop=loop=3:size=1", "-frames:v", "4", "-c:v", "ffv1", str(src)], check=True)
            frames, _ = rv.render(src, Path(tmp) / "out", settings, ffmpeg=ffmpeg, librashader=cli,
                                  input_size=(width, height), rate="60", codec="png", jobs=2,
                                  runtime=rv.runtime_candidates(rv.runtimes_of(cli))[0], work=Path(tmp) / "w")
            self.assertEqual(frames, 4)
            f = [(Path(tmp) / "out" / f"{i:06d}.png").read_bytes() for i in range(1, 5)]
        self.assertEqual((f[0] == f[2], f[1] == f[3], f[0] == f[1]), (True, True, False))


if __name__ == "__main__":
    unittest.main()
