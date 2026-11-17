#!/usr/bin/env python3
"""Tests for projection.py (pure maths, always run) and for how the logo is fitted to each stage (needs the ISO).

    python3 tools/logo-stage/test_projection.py
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
import projection  # noqa: E402
from slp2alpha import locate  # noqa: E402

YOSHIS = projection.from_ground_param((2.0, 64.0, 387.0), 25.0, -4.0)
BATTLEFIELD = projection.from_ground_param((0.0, 100.0, 300.0), 30.0, -12.0)


class CameraMaths(unittest.TestCase):
    def test_interest_is_the_view_ray_cut_with_the_plane_z_0(self):
        x, y, z = YOSHIS.interest
        self.assertEqual((x, z), (2.0, 0.0))
        self.assertAlmostEqual(y, 64.0 + 387.0 * math.tan(math.radians(-4.0)), places=6)
        _, _, fwd = YOSHIS.axes
        t = -YOSHIS.eye[2] / fwd[2]
        self.assertAlmostEqual(YOSHIS.eye[1] + t * fwd[1], y, places=6)

    def test_the_interest_is_the_middle_of_the_picture(self):
        for cam in (YOSHIS, BATTLEFIELD):
            for scale in (1, 2, 3):
                u, v = cam.project(cam.interest, scale)
                w, h = cam.size(scale)
                self.assertAlmostEqual(u, w / 2, places=6)
                self.assertAlmostEqual(v, h / 2, places=6)

    def test_negative_vertical_angle_looks_down(self):
        _, _, fwd = BATTLEFIELD.axes
        self.assertLess(fwd[1], 0)
        self.assertAlmostEqual(math.degrees(math.asin(fwd[1])), -12.0, places=6)

    def test_up_is_up_and_right_is_right(self):
        u0, v0 = BATTLEFIELD.project((0, 0, 0))
        u1, v1 = BATTLEFIELD.project((10, 20, 0))
        self.assertGreater(u1, u0)
        self.assertLess(v1, v0)

    def test_nearer_things_are_bigger(self):
        far = BATTLEFIELD.project((10, 0, -50))[0] - BATTLEFIELD.project((0, 0, -50))[0]
        near = BATTLEFIELD.project((10, 0, 50))[0] - BATTLEFIELD.project((0, 0, 50))[0]
        self.assertGreater(near, far)

    def test_scale_multiplies_the_picture(self):
        p = (-31.0, 22.0, 0.0)
        u1, v1 = YOSHIS.project(p, 1)
        u3, v3 = YOSHIS.project(p, 3)
        self.assertAlmostEqual(u3, 3 * u1, places=6)
        self.assertAlmostEqual(v3, 3 * v1, places=6)
        self.assertEqual(YOSHIS.size(2), (1280, 1056))

    def test_unproject_undoes_project(self):
        for cam in (YOSHIS, BATTLEFIELD):
            for p in ((-60.0, 0.0), (0.0, 54.4), (68.4, -16.5)):
                u, v = cam.project((p[0], p[1], 0.0), 2)
                x, y = cam.unproject(u, v, 0.0, 2)
                self.assertAlmostEqual(x, p[0], places=6)
                self.assertAlmostEqual(y, p[1], places=6)

    def test_yoshis_story_regression(self):
        # the numbers of the checked Yoshi's Story camera (eye 2, 64, 387; 25 degrees; -4 degrees)
        for p, want in (((0, 0, 0), (313.93, 376.36)), ((0, 100, 0), (313.82, 68.68)), ((-100, 0, 0), (10.30, 376.36))):
            u, v = YOSHIS.project(p)
            self.assertAlmostEqual(u, want[0], delta=0.01)
            self.assertAlmostEqual(v, want[1], delta=0.01)

    def test_behind_the_camera_is_an_error(self):
        with self.assertRaises(ValueError):
            BATTLEFIELD.project((0, 0, 1000))


class LogoFit(unittest.TestCase):
    """plate.make_job reads the six stages from your ISO: the logo is as wide as the ledges and sits on the top."""

    @classmethod
    def setUpClass(cls):
        try:
            import plate
            import stagedata
            locate.check_iso(locate.find_iso(None))
        except (locate.NotFound, OSError) as e:
            raise unittest.SkipTest(f"no Melee ISO: {e}")
        cls.plate, cls.stagedata = plate, stagedata

    def test_width_is_ledge_to_ledge_for_every_stage(self):
        for sid in self.stagedata.STAGE_FILES:
            job = self.plate.make_job(sid, "metal", 1, Path("x.png"))
            m = self.stagedata.load_stage(sid).main_stage
            self.assertAlmostEqual(job["fit"]["width"], m.ledge_right[0] - m.ledge_left[0], places=6)
            self.assertAlmostEqual(job["fit"]["center_x"], 0.5 * (m.ledge_left[0] + m.ledge_right[0]), places=6)
            self.assertAlmostEqual(job["ground"]["y"], m.top_y, places=6)

    def test_ledges_land_inside_the_picture(self):
        for sid in self.stagedata.STAGE_FILES:
            geo = self.stagedata.load_stage(sid)
            cam = self.plate.camera_of(geo)
            w, h = cam.size(1)
            for p in (geo.main_stage.ledge_left, geo.main_stage.ledge_right):
                u, v = cam.project((p[0], p[1], 0.0))
                self.assertTrue(40 < u < w - 40 and 40 < v < h - 40, (sid, u, v))

    def test_known_ledges(self):
        want = {31: 68.4, 32: 85.566, 28: 77.271, 8: 56.0, 2: 63.348, 3: 87.75}
        for sid, x in want.items():
            self.assertAlmostEqual(self.stagedata.load_stage(sid).main_stage.ledge_right[0], x, delta=0.01)


if __name__ == "__main__":
    unittest.main(verbosity=1)
