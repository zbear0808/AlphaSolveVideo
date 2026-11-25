#!/usr/bin/env python3
"""Tests for the CRT renderer's settings and set-up (no GPU needed; the frame test needs ffmpeg).

    python3 tools/crt/test_crt.py
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blender_crt  # noqa: E402   (its GLSL rewrites; without Blender it doesn't draw)
import render_video as rv  # noqa: E402
import vendor_shaders  # noqa: E402
from slp2alpha import locate  # noqa: E402
from test_shaders import Afterglow, NtscPhase, Profiles, Runtimes as ShaderRuntimes, Settings  # noqa: E402,F401


ROYALE = dict(shader="royale")


class PhysicalPixels(unittest.TestCase):
    """The numbers the crt-royale project's render_video.py --physical-pixels worked out (CRT Royale's parameters, as
    render_video.py has always written them)."""

    def test_melee_at_native_resolution(self):
        s = rv.physical_settings(584, 480, 6, **ROYALE)
        self.assertEqual((s.width, s.height, s.triad), (3504, 2880, 3.0))
        self.assertEqual(s.params, "mask_type=0,mask_triad_size_desired=3.0,interlace_detect_toggle=0,"
                                   "geom_aspect_ratio_x=1.217,geom_aspect_ratio_y=1.0")

    def test_animelee_at_scale_2(self):
        s = rv.physical_settings(1168, 960, 3, mask="slot", **ROYALE)
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
        s = rv.physical_settings(640, 480, 6, aspect="16:9", **ROYALE)
        self.assertEqual((s.width, s.height), (5120, 2880))
        self.assertIn("geom_aspect_ratio_x=16.0,geom_aspect_ratio_y=9.0", s.params)
        self.assertEqual(rv.physical_settings(641, 481, 1).width, 642)  # even, for the encoders

    def test_extra_params_go_last(self):
        self.assertTrue(rv.physical_settings(584, 480, 6, params="halation_weight=0.1", **ROYALE).params
                        .endswith(",halation_weight=0.1"))


class StandardMode(unittest.TestCase):
    def test_square(self):
        s, vf = rv.standard_settings("1280", 288, "crop", **ROYALE)
        self.assertEqual((s.width, s.height, s.triad), (1280, 1280, 3.0))
        self.assertIn("scale=288:288", vf)

    def test_wide(self):
        s, vf = rv.standard_settings("1920x1080", 240, "letterbox", mask="shadow", **ROYALE)
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


class Candidates(unittest.TestCase):
    """Blender first where it can draw, then librashader-cli's runtimes."""

    def setUp(self):
        patcher = mock.patch.object(rv, "runtimes_of", return_value=("metal", "wgpu", "vulkan", "d3d11"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_blender_first_on_macos_and_linux(self):
        self.assertEqual(rv.candidates("cli", "blender", platform="darwin"), ["blender", "metal", "wgpu"])
        self.assertEqual(rv.candidates("cli", "blender", platform="linux")[:2], ["blender", "wgpu"])
        self.assertEqual(rv.candidates("cli", "blender", platform="win32")[0], "d3d11")

    def test_without_one_of_them(self):
        self.assertEqual(rv.candidates("cli", None, platform="linux")[0], "wgpu")
        self.assertEqual(rv.candidates(None, "blender", platform="linux"), ["blender"])
        with self.assertRaises(rv.CrtError):
            rv.candidates(None, None, platform="linux")

    def test_asked_for(self):
        self.assertEqual(rv.candidates("cli", "blender", "blender", platform="linux"), ["blender"])
        self.assertEqual(rv.candidates("cli", "blender", "wgpu", platform="linux"), ["wgpu"])
        for librashader, blender, runtime, platform in ((None, "blender", "wgpu", "linux"),
                                                        ("cli", None, "blender", "linux"),
                                                        ("cli", "blender", "blender", "win32")):
            with self.assertRaises(rv.CrtError):
                rv.candidates(librashader, blender, runtime, platform=platform)

    def test_another_preset_goes_to_librashader(self):
        other = rv.HERE / "slang-shaders" / "other.slangp"
        self.assertEqual(rv.candidates("cli", "blender", platform="linux", preset=other)[0], "wgpu")

    def test_blender_reads_and_writes_through_inherited_pipes(self):
        settings = rv.physical_settings(584, 480, 6, **ROYALE)
        cmd = rv.blender_command("blender", Path("luts"), 5, 7, (584, 480), settings, platform="linux")
        self.assertEqual(cmd[cmd.index("--") + 1:], [str(rv.BLENDER_CHAIN), "luts", "5", "7", "584", "480", "3504",
                                                     "2880", settings.params])
        self.assertIn("opengl", cmd)   # faster than Blender's Vulkan backend on Linux
        self.assertNotIn("--gpu-backend", rv.blender_command("blender", Path("luts"), 5, 7, (584, 480), settings,
                                                             platform="darwin"))
        self.assertEqual(rv.blender_command("blender", Path("luts"), 5, 7, (584, 480), settings, warmup=30)[-2:],
                         ["--warmup", "30"])


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
        self.assertEqual(len(files), 38)

    def test_every_preset_is_vendored(self):
        needed = vendor_shaders.needed(vendor_shaders.VENDORED)
        for preset in tuple(vendor_shaders.PRESETS.values()) + vendor_shaders.MORE_PRESETS:
            self.assertIn(preset, needed)
        self.assertIn("crt/shaders/guest/hd/gaussian_horizontal.slang", needed)   # guest-ntsc's
        self.assertIn("hdr/shaders/include/sony_megatron_v2.h", needed)           # Megatron's, through #reference

    def _closure(self, files: dict, preset: str = "p.slangp") -> set:
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in files.items():
                (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / name).write_text(text, encoding="utf-8")
            return vendor_shaders.closure(Path(tmp), preset)

    def test_closure_reads_quoted_and_unquoted_paths(self):
        files = self._closure({"p.slangp": 'shaders = 2\nshader0 = s/a.slang\nscale0 = 1.0\nalias0 = A\n'
                                           'shader1 = "s/b.slang"\nfilter_linear1 = "false"\n'})
        self.assertEqual(files, {"p.slangp", "s/a.slang", "s/b.slang"})

    def test_closure_reads_textures(self):
        files = self._closure({"p.slangp": 'shaders = 1\nshader0 = a.slang\nLUT2 = "l/two.png"\n'
                                           'textures = "LUT1;LUT2"\nLUT1 = l/one.png\nLUT1_linear = true\n'
                                           'other = "x.png"\n'})
        self.assertEqual(files, {"p.slangp", "a.slang", "l/one.png", "l/two.png"})

    def test_closure_follows_references_and_includes(self):
        files = self._closure({
            "p.slangp": '/* shader9 = "not/this.slang" */\n#reference "base/b.slangp"\nparam_a = "0.5"\n',
            "base/b.slangp": '#reference "../c.slangp"\nshaders = 1\nshader0 = "s.slang"\n',
            "c.slangp": "# a comment\nshaders = 1\nshader0 = base/s.slang\n",
            "base/s.slang": '#version 450\n#include "inc/i.h"\n',
            "base/inc/i.h": '  #  include "../../j.inc"\n'})
        self.assertEqual(files, {"p.slangp", "base/b.slangp", "c.slangp", "base/s.slang", "base/inc/i.h", "j.inc"})

    def test_closure_lists_missing_files(self):
        self.assertEqual(self._closure({"p.slangp": "shader0 = gone.slang\n"}), {"p.slangp", "gone.slang"})

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


class Encoders(unittest.TestCase):
    """video_encoder's order, with this machine's encoders and probes replaced: the first faster encoder that's
    listed and encodes a frame of the size, else the portable one."""

    def pick(self, codec, alpha, have, works=lambda args: True):
        with mock.patch.object(rv.solve, "available_encoders", return_value=frozenset(have)), \
                mock.patch.object(rv.solve, "encoder_works", side_effect=lambda f, args, size: works(args)):
            args = rv.video_encoder("ffmpeg", codec, alpha, (3504, 2880))
        return args[args.index("-c:v") + 1], args

    def test_prores_order(self):
        all_three = {"prores_videotoolbox", "prores_aw", "prores_ks"}
        self.assertEqual(self.pick("prores4444", True, all_three)[0], "prores_videotoolbox")
        self.assertEqual(self.pick("prores4444", True, {"prores_aw", "prores_ks"})[0], "prores_aw")
        self.assertEqual(self.pick("prores4444", True, {"prores_ks"})[0], "prores_ks")
        refuses_apple = lambda args: "prores_videotoolbox" not in args
        self.assertEqual(self.pick("prores4444", True, all_three, refuses_apple)[0], "prores_aw")

    def test_prores_keeps_alpha_only_when_asked(self):
        _, with_alpha = self.pick("prores4444", True, {"prores_aw"})
        _, opaque = self.pick("prores4444", False, {"prores_aw"})
        self.assertIn("yuva444p10le", with_alpha)
        self.assertIn("yuv444p10le", opaque)
        self.assertEqual(self.pick("prores4444", False, {"prores_ks"})[1], rv.solve.OPAQUE_ARGS["mov"])

    def test_h264_nvenc_then_libx264(self):
        name, args = self.pick("h264-444", False, {"h264_nvenc", "libx264"})
        self.assertEqual(name, "h264_nvenc")
        self.assertIn("high444p", args)
        self.assertEqual(args[-2:], ["-movflags", "+faststart"])
        self.assertEqual(self.pick("h264-444", False, {"h264_nvenc", "libx264"}, lambda a: "h264_nvenc" not in a)[0],
                         "libx264")
        self.assertEqual(self.pick("h264-444", False, {"libx264"})[0], "libx264")

    def test_unknown_codec(self):
        with self.assertRaises(ValueError):
            rv.video_encoder("ffmpeg", "vp9", False, (64, 64))


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
        settings = rv.physical_settings(width, height, scale, **ROYALE)
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


def png_rgb(ffmpeg: str, path: Path) -> bytes:
    return subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True).stdout


class Chain(unittest.TestCase):
    """blender-chain/<shader>/ is what librashader-cli compiles from each vendored preset."""

    def test_the_copy_is_what_librashader_writes(self):
        try:
            cli = rv.find_librashader()
        except locate.NotFound:
            raise unittest.SkipTest("no librashader-cli: python3 tools/crt/install_librashader.py")
        import vendor_chain
        self.assertEqual(vendor_chain.check(cli), [])

    def _chain(self, shader: str) -> dict:
        return json.loads((rv.HERE / "blender-chain" / shader / "chain.json").read_text(encoding="utf-8"))

    def test_the_copy_is_complete(self):
        self.assertEqual(rv.BLENDER_CHAIN, rv.HERE / "blender-chain" / "royale")
        for shader, preset in vendor_shaders.PRESETS.items():
            with self.subTest(shader):
                doc, folder = self._chain(shader), rv.HERE / "blender-chain" / shader
                self.assertEqual(doc["shaders_commit"], rv.SHADERS_COMMIT)
                self.assertEqual((rv.HERE / doc["preset"]).resolve(), (vendor_shaders.VENDORED / preset).resolve())
                for p in doc["passes"]:
                    for stage in ("vertex", "fragment"):
                        self.assertTrue((folder / f"p{p['id']}.{stage}.glsl").is_file())
                for lut in doc["luts"]:
                    self.assertTrue(((rv.HERE / doc["preset"]).parent / lut["path"]).is_file(), lut["path"])
        self.assertEqual((rv.HERE / self._chain("royale")["preset"]).resolve(), rv.PRESET.resolve())

    def test_feedback_passes(self):
        for shader, ids in (("royale", []), ("guest", [2, 4]), ("guest-ntsc", [2, 10]), ("megatron", [])):
            self.assertEqual([p["id"] for p in self._chain(shader)["passes"] if p.get("feedback")], ids, shader)

    def test_megatron_looks(self):
        looks = self._chain("megatron")["looks"]
        self.assertEqual(list(looks), list(vendor_shaders.MEGATRON_DISPLAYS))
        self.assertEqual(looks["mx8000"]["hcrt_crt_screen_type"], 2.0)   # a slot mask
        self.assertEqual(looks["pvm2730"]["hcrt_red_vertical_convergence"], -0.14)
        self.assertEqual(looks["pvm1910"]["hcrt_crt_resolution"], 0.0)   # 300 TVL
        self.assertNotIn("looks", self._chain("guest"))


class Rewrites(unittest.TestCase):
    """blender_crt.split()'s GLSL rewrites for Blender's GPU module, on snippets and on the chains."""

    def test_brackets(self):
        self.assertEqual(blender_crt.closing("a[b[1]](c) d", 1), 7)
        self.assertEqual(blender_crt.arguments("f(a, b), c[1, 2], 3"), ["f(a, b)", "c[1, 2]", "3"])
        self.assertEqual(blender_crt.leaves("uint[][](uint[](1u, 2u), uint[](3u, f(4u, 5u)))"),
                         ["1u", "2u", "3u", "f(4u, 5u)"])

    def test_constant_arrays_of_arrays_become_flat(self):
        src = ("const uint t[2][3] = uint[][](uint[](1u, 2u, 3u), uint[](4u, 5u, 6u));\n"
               "const uint u[2][2][2] = uint[][][](uint[][](uint[](1u, 2u), uint[](3u, 4u)), "
               "uint[][](uint[](5u, 6u), uint[](7u, 8u)));\n"
               "uint f(uint a, int b[2]) { return t[a + uint(b[1])][f(a, b)] + u[a][t[0][1]] [2u]; }\n")
        self.assertEqual(blender_crt.flatten_nested_arrays(src),
                         "const uint t[6] = uint[](1u, 2u, 3u, 4u, 5u, 6u);\n"
                         "const uint u[8] = uint[](1u, 2u, 3u, 4u, 5u, 6u, 7u, 8u);\n"
                         "uint f(uint a, int b[2]) { return t[(int(a + uint(b[1]))) * 3 + int(f(a, b))] + "
                         "u[((int(a)) * 2 + int(t[(int(0)) * 3 + int(1)])) * 2 + int(2u)]; }\n")
        with self.assertRaises(ValueError):   # a whole row can't be indexed into a flat array
            blender_crt.flatten_nested_arrays("const uint t[2][2] = uint[][](uint[](1u, 2u), uint[](3u, 4u));\n"
                                              "uint g() { return t[1]; }")

    def test_local_arrays_are_assigned_element_by_element(self):
        src = "void main()\n{\n    float a[3] = float[](0.5, f(1.0, 2.0), -3.0);\n    a = b;\n}\n"
        self.assertEqual(blender_crt.unroll_local_arrays(src),
                         "void main()\n{\n    float a[3]; a[0] = 0.5; a[1] = f(1.0, 2.0); a[2] = -3.0;\n    a = b;\n}\n")
        self.assertEqual(blender_crt.unroll_local_arrays("const float k[2] = float[](1.0, 2.0);\n"),
                         "const float k[2] = float[](1.0, 2.0);\n")   # constants stay as they are

    def test_whole_arrays_are_copied_element_by_element(self):
        src = "const float k[3] = float[](1.0, 2.0, 3.0);\nvoid main()\n{\n    float a[3];\n    a = k;\n    x = y;\n}"
        self.assertIn("    for (int _k = 0; _k < 3; _k++) { a[_k] = k[_k]; }\n    x = y;",
                      blender_crt.copy_arrays(src))

    def test_constant_arrays_become_functions(self):
        src = ("const float k[3] = float[](1.0, f(2.0, 3.0), 4.0);\nconst float w[2] = float[](1.0, 2.0);\n"
               "void main() { x = k[k[u + 1u]] + w[0]; g(w); }")
        self.assertEqual(blender_crt.constant_tables(src),
                         "float k(int i) { switch (i) { case 0: return 1.0; case 1: return f(2.0, 3.0); "
                         "default: return 4.0; } }\nconst float w[2] = float[](1.0, 2.0);\n"
                         "void main() { x = k(int(k(int(u + 1u)))) + w[0]; g(w); }")   # w is used as a whole

    def stages(self, shader):
        folder = rv.HERE / "blender-chain" / shader
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("p*.glsl"))}

    def test_royale_is_drawn_from_the_same_source_as_before(self):
        for name, src in self.stages("royale").items():
            body = blender_crt.split(src)[-1]
            for rewrite in (blender_crt.flatten_nested_arrays, blender_crt.unroll_local_arrays,
                            blender_crt.copy_arrays, blender_crt.constant_tables):
                self.assertEqual(rewrite(body), body, f"{name}: {rewrite.__name__}")

    def test_what_blender_cant_compile_is_gone(self):
        for shader in ("guest", "guest-ntsc", "megatron"):
            for name, src in self.stages(shader).items():
                body = blender_crt.split(src)[-1]
                self.assertNotRegex(body, r"\]\s*\[|#extension|^\s+\w+ \w+\[\d+\] = \w+\[\]\(", f"{shader} {name}")
        p6 = blender_crt.split(self.stages("guest-ntsc")["p6.fragment.glsl"])[-1]
        self.assertIn("for (int _k = 0; _k < 33; _k++) { luma_filter_3_phase[_k] = _262(int(_k)); }", p6)
        self.assertNotRegex(p6, r"(?m)^const ", "every constant table is a function")


class BlenderRender(unittest.TestCase):
    """CRT Royale drawn by Blender's GPU module on this machine: needs Blender and a GPU. Against librashader-cli,
    when it's there too, on the same frames: within the 1/255 the plan allows (docs/plan-gpu-crt-model.md)."""

    @classmethod
    def setUpClass(cls):
        if not rv.blender_platform():
            raise unittest.SkipTest("the Blender runtime runs on macOS and Linux")
        cls.blender = rv.find_blender()
        if not cls.blender:
            raise unittest.SkipTest("no Blender")
        cls.ffmpeg = locate.find_ffmpeg()

    def test_frames_match_librashader(self):
        width = height = 136   # 816x816 at 6x: room for crt-royale's mask tiles (see Render)
        settings = rv.physical_settings(width, height, 6, mask="slot", **ROYALE)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.nut"
            subprocess.run([self.ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                            f"testsrc2=s={width}x{height}:r=60:d=0.05", "-c:v", "ffv1", str(src)], check=True)
            kw = dict(ffmpeg=self.ffmpeg, input_size=(width, height), rate="60", prefilter="", codec="png")
            frames, runtime = rv.render(src, Path(tmp) / "blender", settings, librashader=None, blender=self.blender,
                                        runtime="blender", work=Path(tmp) / "w1", **kw)
            self.assertEqual((frames, runtime), (3, "blender"))
            first = Path(tmp) / "blender" / "000001.png"
            self.assertEqual(rv.image_size(first), (settings.width, settings.height))
            try:
                cli = rv.find_librashader()
            except locate.NotFound:
                return
            runtime = rv.runtime_candidates(rv.runtimes_of(cli))[0]
            rv.render(src, Path(tmp) / "cli", settings, librashader=cli, runtime=runtime, work=Path(tmp) / "w2", **kw)
            a, b = png_rgb(self.ffmpeg, first), png_rgb(self.ffmpeg, Path(tmp) / "cli" / "000001.png")
        self.assertEqual(len(a), len(b))
        mean = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
        self.assertLessEqual(mean, 1.0, f"Blender's frame is {mean:.3f}/255 from librashader-cli's ({runtime})")


GUEST_GRILLE = ("interm=0,bloom=0.5,bmask1=1,shadowMask=6,masksize=1,mask_zoom=0,mzoom_sh=0,mshift=0,mask_layout=0,"
                "maskstr=0.5,mcut=1.1,maskboost=1,slotmask=0,slotmask1=0,slotwidth=0,double_slot=2,slotms=1")
MEGATRON_GRILLE3 = ("hcrt_colour_space=2,hcrt_brightness=0.2,hcrt_crt_screen_type=0,hcrt_lcd_resolution=1,"
                    "hcrt_crt_resolution=2,hcrt_lcd_subpixel=2")


class BlenderShaders(unittest.TestCase):
    """guest, guest-ntsc and Megatron drawn by blender_crt.py on this machine, frame by frame through its pipes:
    needs Blender and a GPU (and librashader-cli for the comparisons)."""

    @classmethod
    def setUpClass(cls):
        if not rv.blender_platform():
            raise unittest.SkipTest("the Blender runtime runs on macOS and Linux")
        cls.blender = rv.find_blender()
        if not cls.blender:
            raise unittest.SkipTest("no Blender")
        cls.ffmpeg = locate.find_ffmpeg()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)

    def draw(self, shader: str, frames: list, size, out, params: str = "", warmup: int = 0) -> list:
        """The frames (raw RGBA of `size`) as blender_crt.py draws them at `out`, raw RGBA."""
        import os
        import threading
        chain = rv.HERE / "blender-chain" / shader
        luts = rv.lut_folder(Path(self.tmp.name) / shader, self.ffmpeg, chain=chain)
        settings = rv.Settings(out[0], out[1], params, 3.0, "")
        r_in, w_in = os.pipe()
        r_out, w_out = os.pipe()
        cmd = rv.blender_command(self.blender, luts, r_in, w_out, size, settings, warmup=warmup)
        cmd[cmd.index("--") + 1] = str(chain)
        proc = subprocess.Popen(cmd, pass_fds=(r_in, w_out), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        os.close(r_in)
        os.close(w_out)

        def feed():
            with os.fdopen(w_in, "wb") as f:
                for frame in frames:
                    f.write(frame)

        threading.Thread(target=feed, daemon=True).start()
        drawn, n = [], out[0] * out[1] * 4
        with os.fdopen(r_out, "rb") as f:
            while len(chunk := f.read(n)) == n:
                drawn.append(chunk)
        log = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        proc.wait()
        self.assertEqual((proc.returncode, len(drawn)), (0, len(frames)), log[-2000:])
        return drawn

    def picture(self, size, name="card") -> tuple:
        """A test card of `size`: its PNG and its raw RGBA."""
        png = Path(self.tmp.name) / f"{name}{size[0]}x{size[1]}.png"
        subprocess.run([self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={size[0]}x{size[1]}",
                        "-frames:v", "1", str(png)], check=True)
        raw = subprocess.run([self.ffmpeg, "-v", "error", "-i", str(png), "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                             capture_output=True, check=True).stdout
        return png, raw

    def test_frame_0_matches_librashader(self):
        try:
            cli = rv.find_librashader()
        except locate.NotFound:
            raise unittest.SkipTest("no librashader-cli: python3 tools/crt/install_librashader.py")
        runtime = rv.runtime_candidates(rv.runtimes_of(cli))[0]
        size, out = (160, 120), (960, 720)
        for shader, params in (("guest", GUEST_GRILLE), ("guest-ntsc", GUEST_GRILLE), ("megatron", MEGATRON_GRILLE3)):
            with self.subTest(shader):
                png, raw = self.picture(size, shader)   # draw() deletes it
                drawn = self.draw(shader, [raw], size, out, params)[0]
                doc = json.loads((rv.HERE / "blender-chain" / shader / "chain.json").read_text(encoding="utf-8"))
                dst = Path(self.tmp.name) / f"{shader}.png"
                rv.draw(cli, runtime, rv.HERE / doc["preset"], rv.Settings(out[0], out[1], params, 3.0, ""),
                        png, dst)
                b = subprocess.run([self.ffmpeg, "-v", "error", "-i", str(dst), "-f", "rawvideo", "-pix_fmt", "rgba",
                                    "-"], capture_output=True, check=True).stdout
                self.assertEqual(len(drawn), len(b))
                mean = (sum(abs(x - y) for x, y in zip(drawn, b)) - sum(abs(x - y) for x, y in
                                                                        zip(drawn[3::4], b[3::4]))) / (len(b) * 3 / 4)
                self.assertLessEqual(mean, 1.0, f"{shader}: {mean:.3f}/255 from librashader-cli's ({runtime})")

    def test_the_afterglow_decays_as_measured(self):
        # The crt-royale project's lrs-seq measurement (pipelines/guest_advanced/temporal_results.json): flat
        # 288x288 frames drawn at 1280x1280 with guest's own defaults, 10 white then black; the mean of the picture
        # inside a 48 px margin
        measured = [222.4, 35.7, 28.8, 22.6, 18.3, 14.8, 12.1, 9.5, 6.9, 6.1, 4.3, 3.5, 2.6, 1.7, 1.0, 1.0, 0.0, 0.0]
        side, out, margin = 288, 1280, 48
        frames = [bytes([255, 255, 255, 255]) * side * side] * 10 + [bytes([0, 0, 0, 255]) * side * side] * 17
        means = []
        for drawn in self.draw("guest", frames, (side, side), (out, out))[9:]:
            total = 0
            for y in range(margin, out - margin):
                row = drawn[(y * out + margin) * 4:(y * out + out - margin) * 4]
                total += sum(row) - sum(row[3::4])
            means.append(total / ((out - 2 * margin) ** 2 * 3))
        for i, (got, want) in enumerate(zip(means, measured)):
            self.assertAlmostEqual(got, want, delta=1.0, msg=f"black frame {i}: {[round(m, 1) for m in means]}")

    def test_the_ntsc_phase_alternates(self):
        size, out = (320, 240), (960, 720)   # over 300 px wide: 2 phases, alternating
        _, raw = self.picture(size)
        drawn = self.draw("guest-ntsc", [raw] * 3, size, out)

        def apart(a, b):
            return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

        self.assertGreater(apart(drawn[0], drawn[1]), 1.0)
        self.assertLess(apart(drawn[0], drawn[2]), 0.1)

    def test_warmup_is_the_first_frame_drawn_before(self):
        side = 64
        white, black = bytes([255] * 4) * side * side, bytes([0, 0, 0, 255]) * side * side
        plain = self.draw("guest", [white, white, white, black], (side, side), (256, 256))
        warmed = self.draw("guest", [white, black], (side, side), (256, 256), warmup=2)
        self.assertEqual(warmed, plain[2:])
        self.assertNotEqual(plain[3], self.draw("guest", [black], (side, side), (256, 256))[0])   # the afterglow


if __name__ == "__main__":
    unittest.main()
