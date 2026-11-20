#!/usr/bin/env python3
"""Tests for the CRT renderer's settings and set-up (no GPU needed; the frame test needs ffmpeg).

    python3 tools/crt/test_crt.py
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_video as rv  # noqa: E402
import vendor_shaders  # noqa: E402
from slp2alpha import locate  # noqa: E402


class PhysicalPixels(unittest.TestCase):
    """The numbers the crt-royale project's render_video.py --physical-pixels worked out."""

    def test_melee_at_native_resolution(self):
        s = rv.physical_settings(584, 480, 6)
        self.assertEqual((s.width, s.height, s.triad), (3504, 2880, 3.0))
        self.assertEqual(s.params, "mask_type=0,mask_triad_size_desired=3.0,interlace_detect_toggle=0,"
                                   "geom_aspect_ratio_x=1.217,geom_aspect_ratio_y=1.0")

    def test_animelee_at_scale_2(self):
        s = rv.physical_settings(1168, 960, 3, mask="slot")
        self.assertEqual((s.width, s.height, s.triad), (3504, 2880, 3.0))
        self.assertTrue(s.params.startswith("mask_type=1,"))

    def test_triads(self):
        self.assertEqual(rv.physical_settings(640, 480, 8).triad, 4.0)        # 2 triads per pixel from 6x
        self.assertEqual(rv.physical_settings(640, 480, 4).triad, 3.0)
        self.assertEqual(rv.physical_settings(640, 480, 3).triad, 3.0)
        self.assertEqual(rv.physical_settings(640, 480, 8, triads_per_pixel=1).triad, 8.0)
        self.assertEqual(rv.physical_settings(640, 480, 6, triad=2.5).triad, 2.5)

    def test_auto_scale(self):
        self.assertEqual(rv.physical_settings(320, 240).scale, 6)
        self.assertEqual(rv.physical_settings(640, 480).scale, 4)
        self.assertEqual(rv.physical_settings(1920, 1080).scale, 4)

    def test_aspects(self):
        s = rv.physical_settings(640, 480, 6, aspect="16:9")
        self.assertEqual((s.width, s.height), (5120, 2880))
        self.assertIn("geom_aspect_ratio_x=16.0,geom_aspect_ratio_y=9.0", s.params)
        self.assertEqual(rv.physical_settings(641, 481, 1).width, 642)  # even, for the encoders

    def test_extra_params_go_last(self):
        self.assertTrue(rv.physical_settings(584, 480, 6, params="halation_weight=0.1").params
                        .endswith(",halation_weight=0.1"))


class StandardMode(unittest.TestCase):
    def test_square(self):
        s, vf = rv.standard_settings("1280", 288, "crop")
        self.assertEqual((s.width, s.height, s.triad), (1280, 1280, 3.0))
        self.assertIn("scale=288:288", vf)

    def test_wide(self):
        s, vf = rv.standard_settings("1920x1080", 240, "letterbox", mask="shadow")
        self.assertEqual((s.width, s.height, s.triad), (1920, 1080, 4.5))
        self.assertIn("geom_aspect_ratio_x=1.778", s.params)
        self.assertIn("pad=240:240", vf)


class Runtimes(unittest.TestCase):
    HELP = """Usage: librashader-cli render [OPTIONS] --preset <PRESET> --image <IMAGE> --out <OUT> --runtime <RUNTIME>

      --color-space <COLOR_SPACE>
          [possible values: sdr, hdr10, scrgb, pq-scrgb]
  -r, --runtime <RUNTIME>
          The runtime to use to render the shader preset

          [possible values: opengl3, opengl4, vulkan, wgpu, metal]
"""

    def test_help_lists_the_runtimes(self):
        self.assertEqual(rv.parse_runtimes(self.HELP), ("opengl3", "opengl4", "vulkan", "wgpu", "metal"))

    def test_each_platform_starts_with_its_own(self):
        have = ("opengl4", "vulkan", "wgpu", "metal", "d3d11")
        self.assertEqual(rv.runtime_candidates(have, platform="darwin")[0], "metal")
        self.assertEqual(rv.runtime_candidates(have, platform="win32")[0], "d3d11")
        # librashader-cli's Vulkan runtime ignores the size asked for, so Linux draws through wgpu (on Vulkan)
        self.assertEqual(rv.runtime_candidates(have, platform="linux")[0], "wgpu")
        self.assertEqual(rv.runtime_candidates(("vulkan",), platform="win32"), ["vulkan"])

    def test_one_asked_for(self):
        self.assertEqual(rv.runtime_candidates(("vulkan", "metal"), "vulkan"), ["vulkan"])
        with self.assertRaises(rv.CrtError):
            rv.runtime_candidates(("vulkan",), "metal")

    def test_unreadable_help_tries_the_platforms_runtimes(self):
        self.assertEqual(rv.runtime_candidates((), platform="linux"), list(rv.RUNTIME_ORDER["linux"]))

    def test_the_installer_builds_what_each_platform_tries_first(self):
        import install_librashader
        for platform, order in rv.RUNTIME_ORDER.items():
            built = install_librashader.platform_features(platform)
            self.assertIn(order[0], built, platform)
            self.assertIn("wgpu", built, platform)   # librashader-cli 0.12.1 doesn't compile without it


class Shaders(unittest.TestCase):
    def test_the_copy_is_complete_and_unmodified(self):
        self.assertEqual(vendor_shaders.check(), [])

    def test_the_preset_is_the_copy(self):
        self.assertTrue(rv.PRESET.is_file())
        self.assertEqual(rv.SHADERS_COMMIT, vendor_shaders.COMMIT)

    def test_closure_follows_includes(self):
        files = vendor_shaders.closure(vendor_shaders.VENDORED)
        self.assertIn("crt/shaders/crt-royale/src/crt-royale-bloom-approx.h", files)   # only #included
        self.assertIn("include/gamma-management.h", files)                             # outside crt/
        self.assertIn("crt/shaders/crt-royale/TileableLinearShadowMaskEDP.png", files)  # a texture

    def test_blob_id_is_gits(self):
        self.assertEqual(vendor_shaders.blob_id(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")


class Frames(unittest.TestCase):
    def test_bmp_header(self):
        h = rv.bmp_header(5, 2)
        size, offset = struct.unpack("<I", h[2:6])[0], struct.unpack("<I", h[10:14])[0]
        self.assertEqual((len(h), offset, size), (54, 54, 54 + 16 * 2))   # rows of 15 bytes padded to 16
        self.assertEqual(rv.image_size_of(h), (5, 2))

    def test_png_size(self):
        png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 3504, 2880)
        self.assertEqual(rv.image_size_of(png), (3504, 2880))
        self.assertIsNone(rv.image_size_of(b"GIF89a"))

    def test_bmp_reads_back_as_the_frame(self):
        try:
            ffmpeg = locate.find_ffmpeg()
        except locate.NotFound:
            self.skipTest("no ffmpeg")
        width, height = 5, 3
        bgr = bytes(range(width * height * 3))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.bmp"
            path.write_bytes(rv.bmp_bytes(bgr, width, height))
            back = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                                  capture_output=True, check=True).stdout
        self.assertEqual(back, bgr)

    def test_frame_clock(self):
        self.assertEqual(rv.frame_clock("60000/1001"), "settb=1001/60000,setpts=N")
        self.assertEqual(rv.frame_clock("60"), "settb=1/60,setpts=N")


def read_bmp(path: Path):
    """(width, height, bytes per pixel, rows top first) of an uncompressed 24- or 32-bit BMP; rows as bytes, BGR(A)."""
    data = path.read_bytes()
    offset, width, height, bits = (struct.unpack("<I", data[10:14])[0], *struct.unpack("<ii", data[18:26]),
                                   struct.unpack("<H", data[28:30])[0])
    step = bits // 8
    stride = (width * step + 3) & ~3
    rows = [data[offset + y * stride:offset + y * stride + width * step] for y in range(abs(height))]
    return width, abs(height), step, rows if height < 0 else rows[::-1]


class Render(unittest.TestCase):
    """CRT Royale really drawing on this machine, with the runtime render_video.py would pick: needs librashader-cli
    (install_librashader.py) and a GPU, or Mesa's lavapipe on Linux. Checks the picture's structure, not exact
    values, which differ a little between GPUs."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.exe = rv.find_librashader()
        except locate.NotFound:
            raise unittest.SkipTest("no librashader-cli: python3 tools/crt/install_librashader.py")

    def test_a_grey_frame_becomes_scanlines_and_phosphor_stripes(self):
        # The preset resizes the phosphor mask into a 16th of the screen, which needs room for two tiles of 8
        # triads: 3 px triads need a screen at least 768 px wide and tall (136 x 6 = 816)
        width = height = 136
        scale = 6
        settings = rv.physical_settings(width, height, scale)
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.bmp", Path(tmp) / "out.bmp"
            src.write_bytes(rv.bmp_bytes(bytes([128]) * (width * height * 3), width, height))
            runtime = rv.pick_runtime(self.exe, rv.PRESET, settings, src, dst,
                                      rv.runtime_candidates(rv.runtimes_of(self.exe)))
            w, h, step, rows = read_bmp(dst)
        self.assertEqual((w, h), (settings.width, settings.height), runtime)
        middle = range(h // 4, 3 * h // 4)   # away from the screen's border
        level = sum(sum(rows[y]) for y in middle) / (len(middle) * w * step)
        self.assertGreater(level, 20, f"{runtime}: the picture is nearly black")
        # Scanlines: each source row is a beam `scale` pixels tall, brightest in its middle
        by_phase = [0] * scale
        for y in middle:
            by_phase[y % scale] += sum(rows[y])
        self.assertGreater(max(by_phase), 1.15 * min(by_phase), f"{runtime}: no scanlines {by_phase}")
        # The aperture grille: red, green and blue stripes, one triad every settings.triad (3) pixels
        triad = int(settings.triad)
        for channel in range(3):
            by_column = [sum(sum(rows[y][(x * step + channel)::triad * step]) for y in middle) for x in range(triad)]
            self.assertGreater(max(by_column), 1.5 * min(by_column) + 1,
                               f"{runtime}: no phosphor stripes in channel {'bgr'[channel]} {by_column}")


if __name__ == "__main__":
    unittest.main()
