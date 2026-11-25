#!/usr/bin/env python3
"""Tests for slp2video's planning: which render, model, composite and CRT steps a set of options gives (no Dolphin,
Blender or CRT needed).

    python3 tools/slp2video/test_slp2video.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import slp2video  # noqa: E402
import plate  # noqa: E402  (tools/logo-stage, on the path through slp2video)
import projection  # noqa: E402

BATTLEFIELD, DREAM_LAND, FINAL_DESTINATION, YOSHIS = 31, 28, 32, 8
REPLAY = Path("/replays/game.slp")


def options(*argv):
    args, passthrough = slp2video.parse(["game.slp", *argv])
    return args


def plan(*argv, stage=BATTLEFIELD):
    return slp2video.make_plan(options(*argv), stage)


class WhatIsDrawn(unittest.TestCase):
    def test_the_default_is_the_stage_without_its_background_where_it_can_be_removed(self):
        for stage in (BATTLEFIELD, DREAM_LAND):
            p = plan(stage=stage)
            self.assertEqual((p.mode, p.transparent, p.background, p.notes), ("stage", True, None, []))

    def test_elsewhere_only_the_fighters_with_a_note(self):
        p = plan(stage=FINAL_DESTINATION)
        self.assertEqual(p.mode, "characters")
        self.assertIn("--keep-background", p.notes[0])

    def test_keep_background_is_the_game_as_it_looks_on_every_stage(self):
        for stage in (BATTLEFIELD, FINAL_DESTINATION, YOSHIS):
            p = plan("--keep-background", stage=stage)
            self.assertEqual((p.mode, p.transparent, p.background), ("game", False, None))

    def test_keep_background_refuses_what_it_would_ignore(self):
        for extra in (["--model", "statue.glb"], ["--characters-only"], ["--bg-color", "00ff00"],
                      ["--transparency"], ["--hide-items"]):
            with self.assertRaises(slp2video.UsageError, msg=extra):
                plan("--keep-background", *extra)

    def test_a_model_hides_the_stage(self):
        p = plan("--model", "statue.glb", stage=DREAM_LAND)
        self.assertEqual((p.mode, p.model, p.style), ("characters", "statue.glb", "original"))

    def test_the_shy_guy_sprite_only_on_yoshis_story(self):
        self.assertIsNone(plan("--shy-guy-sprite", "me.png").sprite)
        p = plan("--shy-guy-sprite", "me.png", stage=YOSHIS)
        self.assertEqual((p.sprite, p.mode), ("me.png", "characters"))
        self.assertEqual(plan("--shy-guy-sprite", "me.png", "--keep-background", stage=YOSHIS).mode, "game")


class Transparency(unittest.TestCase):
    def test_bg_color_flattens(self):
        p = plan("--bg-color", "#00FF00")
        self.assertEqual((p.transparent, p.background), (False, "00ff00"))

    def test_no_transparency_flattens_onto_black(self):
        p = plan("--no-transparency")
        self.assertEqual((p.transparent, p.background), (False, "000000"))

    def test_mp4_flattens_unless_asked_and_then_has_a_matte(self):
        p = plan("--format", "mp4")
        self.assertEqual((p.transparent, p.background, p.matte), (False, "000000", False))
        p = plan("--format", "mp4", "--transparency")
        self.assertEqual((p.transparent, p.background, p.matte), (True, None, True))
        self.assertFalse(plan().matte)   # ProRes keeps its alpha
        with self.assertRaises(slp2video.UsageError):
            plan("--format", "mp4", "--transparency", "--bg-color", "00ff00")

    def test_a_bad_colour(self):
        with self.assertRaises(slp2video.UsageError):
            plan("--bg-color", "green")

    def test_the_format_follows_the_output_name(self):
        self.assertEqual(options("-o", "clip.mp4").format, "mp4")
        self.assertEqual(options("-o", "clip").format, "mov")
        with self.assertRaises(SystemExit):
            options("-o", "clip.mp4", "--format", "mov")


class ScaleAndCrt(unittest.TestCase):
    def test_default_scale(self):
        self.assertEqual(plan().scale, 1)
        self.assertEqual(plan("--animelee").scale, 2)
        self.assertEqual(plan("--scale", "3").scale, 3)

    def test_regular_melee_goes_on_the_crt_at_native_resolution(self):
        p = plan("--crt")
        self.assertEqual((p.scale, p.raw), (1, True))
        self.assertEqual(p.notes, [])

    def test_a_higher_scale_on_the_crt_is_kept_with_a_note(self):
        p = plan("--crt", "--scale", "2")
        self.assertEqual(p.scale, 2)
        self.assertIn("native resolution", p.notes[0])

    def test_animelee_on_the_crt_keeps_its_scale(self):
        p = plan("--crt", "--animelee")
        self.assertEqual((p.scale, p.raw, p.notes), (2, True, []))

    def test_only_the_crt_records_the_raw_picture(self):
        self.assertFalse(plan().raw)

    def test_the_picture_is_as_wide_as_melee_draws_it(self):
        self.assertEqual(slp2video.crt_width(480), 584)
        self.assertEqual(slp2video.crt_width(960), 1168)
        self.assertEqual(slp2video.crt_width(1440), 1752)


class Models(unittest.TestCase):
    def test_finishes(self):
        self.assertEqual(plan("--model", "logo").style, "metal")
        self.assertEqual(plan("--model", "logo", "--animelee").style, "cel")
        self.assertEqual(plan("--model", "x.glb", "--animelee").style, "cel")
        self.assertEqual(plan("--model", "x.glb", "--animelee", "--no-model-cel").style, "original")
        self.assertEqual(plan("--model", "x.glb", "--model-cel").style, "cel")

    def test_the_moving_camera_needs_the_camera_export(self):
        self.assertTrue(plan("--model", "x.glb").export_camera)
        self.assertFalse(plan("--model", "x.glb", "--static-camera").export_camera)
        self.assertFalse(plan().export_camera)

    def test_shadows_off_for_the_logo_through_the_moving_camera(self):
        shadows = lambda *a: slp2video.moving_shadows(options(*a), plan(*a))
        self.assertFalse(shadows("--model", "logo"))
        self.assertTrue(shadows("--model", "logo", "--model-shadows"))
        self.assertTrue(shadows("--model", "x.glb"))
        self.assertFalse(shadows("--model", "x.glb", "--no-model-shadows"))

    def test_rotation(self):
        self.assertEqual(plate.rotation("90"), 90.0)
        self.assertEqual(plate.rotation("90,0,45"), [90.0, 0.0, 45.0])

    def test_frames_are_shared_between_processes(self):
        self.assertEqual(plate.chunks(300, 2), [(1, 150), (151, 300)])
        self.assertEqual(plate.chunks(5, 3), [(1, 2), (3, 3), (4, 5)])
        self.assertEqual(plate.chunks(1, 4), [(1, 1)])

    def test_recording_sizes(self):
        self.assertEqual(projection.recording_size(1), (640, 528))
        self.assertEqual(projection.recording_size(3), (1920, 1580))
        self.assertEqual(projection.recording_size(2, raw=True), (1280, 960))


class Commands(unittest.TestCase):
    def render_args(self, *argv, stage=BATTLEFIELD, passthrough=()):
        args = options(*argv)
        return slp2video.slp2alpha_args(args, slp2video.make_plan(args, stage), REPLAY, Path("/work"), passthrough)

    def test_the_default_render(self):
        self.assertEqual(self.render_args(), ["render", str(REPLAY), "--out-dir", "/work", "--scale", "1",
                                              "--format", "mov"])

    def test_a_model_with_the_moving_camera_on_the_crt(self):
        a = self.render_args("--model", "x.glb", "--crt", "--start-frame", "100", "--no-hud",
                             passthrough=["--debug"])
        for flag in ("--characters-only", "--export-camera", "--raw-resolution", "--no-hud", "--debug"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--start-frame") + 1], "100")
        self.assertNotIn("--static-camera", a)

    def test_the_game_as_it_looks(self):
        a = self.render_args("--keep-background", "--static-camera", "--animelee", stage=FINAL_DESTINATION)
        for flag in ("--keep-background", "--static-camera", "--animelee"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--scale") + 1], "2")

    def test_name_tags_go_to_the_render(self):
        a = self.render_args("--nametag", "P1=ZUBAIR", "--nametag", "P4=")
        self.assertEqual(a[-4:], ["--nametag", "P1=ZUBAIR", "--nametag", "P4="])
        self.assertIn("--no-nametags", self.render_args("--no-nametags"))

class Names(unittest.TestCase):
    def test_this_runs_steps_are_added(self):
        args = options("--model", "statue.glb", "--bg-color", "112233", "--crt", "--crt-mask", "slot")
        p = slp2video.make_plan(args, BATTLEFIELD)
        self.assertEqual(slp2video.output_name("game (characters only, raw resolution, 60 fps)", p, args),
                         "game (characters only, 60 fps), statue stage, on 112233, crt slot mask")

    def test_the_crt_drops_the_raw_label(self):
        args = options("--keep-background", "--crt")
        p = slp2video.make_plan(args, BATTLEFIELD)
        self.assertEqual(slp2video.output_name("game (with background, raw resolution)", p, args),
                         "game (with background), crt")
        self.assertEqual(slp2video.output_name("game (raw resolution)", p, args), "game, crt")
        self.assertEqual(slp2video.output_name("game (1) (raw resolution)", p, args), "game (1), crt")

    def test_a_plain_render_keeps_its_name(self):
        args = options()
        self.assertEqual(slp2video.output_name("game", slp2video.make_plan(args, BATTLEFIELD), args), "game")


class ModelCache(unittest.TestCase):
    """The moving camera's plates are kept by what they show, and only the most recently used few."""

    def test_the_key_follows_the_camera_not_where_it_was_written(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src, a, b, c = (Path(tmp) / n for n in ("model.blend", "a.json", "b.json", "c.json"))
            src.write_bytes(b"model")
            a.write_text('{"x": 1}')
            b.write_text('{"x": 1}')
            c.write_text('{"x": 2}')
            job = {"style": "metal", "size": [640, 480]}
            key = lambda p, **kw: plate.sequence_key(dict(job, camera_export=str(p), **kw), src)
            self.assertEqual(key(a), key(b))
            self.assertNotEqual(key(a), key(c))
            self.assertNotEqual(key(a), key(a, samples=8))

    def test_only_complete_sequences_count(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertFalse(plate.cached_sequence(folder, 10))
            (folder / plate.SEQUENCE_DONE).write_text('{"frames": 10}')
            self.assertTrue(plate.cached_sequence(folder, 10))
            self.assertFalse(plate.cached_sequence(folder, 11))

    def test_the_least_recently_used_go(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(5):
                (root / f"s{i}").mkdir()
                os.utime(root / f"s{i}", (1000 + i, 1000 + i))
            dropped = plate.prune_sequences(root, 3, spare=root / "s0")
            self.assertEqual(sorted(p.name for p in dropped), ["s1", "s2"])
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["s0", "s3", "s4"])
            self.assertEqual(plate.prune_sequences(root / "none", 3), [])


if __name__ == "__main__":
    unittest.main()
