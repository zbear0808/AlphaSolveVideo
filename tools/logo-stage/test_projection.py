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

    def test_a_real_size_overrides_the_scale(self):
        p = (-31.0, 22.0, 0.0)
        u, v = YOSHIS.project(p, size=(1920, 1580))
        u1, v1 = YOSHIS.project(p)
        self.assertAlmostEqual(u, 3 * u1, places=6)
        self.assertAlmostEqual(v, v1 * 1580 / 528, places=6)
        self.assertEqual(projection.picture_size(3), (1920, 1584))


class LookAt(unittest.TestCase):
    """LookAtCamera: the camera as the game's camera object holds it (eye, look-at point, roll)."""

    POINTS = ((0, 0, 0), (-60, 0, 0), (68.4, -16.5, 0), (10, 40, 30), (-80, 90, -60))

    def test_same_pictures_as_the_stage_camera(self):
        for cam in (YOSHIS, BATTLEFIELD):
            look = projection.LookAtCamera(cam.eye, cam.interest, cam.fov_deg)
            for p in self.POINTS:
                for scale in (1, 2):
                    a, b = cam.project(p, scale), look.project(p, scale)
                    self.assertAlmostEqual(a[0], b[0], places=9)
                    self.assertAlmostEqual(a[1], b[1], places=9)

    def test_the_interest_is_the_middle_of_the_picture(self):
        cam = projection.LookAtCamera((7.0, 33.7, 208.6), (10.7, 16.6, 0.0), 30.0)
        u, v = cam.project(cam.interest, size=(1920, 1580))
        self.assertAlmostEqual(u, 960, places=9)
        self.assertAlmostEqual(v, 790, places=9)

    def test_axes_are_orthonormal_and_up_is_level(self):
        cam = projection.LookAtCamera((7.0, 33.7, 208.6), (10.7, 16.6, 0.0), 30.0)
        right, up, fwd = cam.axes
        for a, b in ((right, up), (up, fwd), (right, fwd)):
            self.assertAlmostEqual(sum(x * y for x, y in zip(a, b)), 0.0, places=12)
        self.assertAlmostEqual(right[1], 0.0, places=12)  # no roll: the horizon stays level
        self.assertGreater(up[1], 0)

    def test_roll_turns_up_about_the_view_by_minus_roll(self):
        fwd = projection._unit((0.3, -0.2, -1.0))
        level, rolled = projection.roll_up(fwd), projection.roll_up(fwd, 0.25)
        # Rodrigues by hand: rotating `level` about fwd by -0.25
        c, s = math.cos(-0.25), math.sin(-0.25)
        k = fwd
        kv = projection._cross(k, level)
        want = [level[i] * c + kv[i] * s for i in range(3)]  # level is perpendicular to k
        for a, b in zip(rolled, want):
            self.assertAlmostEqual(a, b, places=12)

    def test_unproject_undoes_project(self):
        cam = projection.LookAtCamera((-12.0, 40.0, 150.0), (-5.0, 12.0, 0.0), 30.0)
        for p in ((-60.0, 0.0), (0.0, 54.4), (40.0, -10.0)):
            u, v = cam.project((p[0], p[1], 0.0), size=(1280, 1056))
            x, y = cam.unproject(u, v, 0.0, size=(1280, 1056))
            self.assertAlmostEqual(x, p[0], places=6)
            self.assertAlmostEqual(y, p[1], places=6)

    def test_the_fixed_camera_looks_where_the_game_says(self):
        # look-at points of --static-camera, read from game memory by a camera export (NTSC 1.02)
        for eye, vert, want in (((0.0, 100.0, 300.0), -12.0, 37.066086), ((0.0, 100.0, 400.0), -10.0, 30.431921),
                                ((0.0, 45.0, 356.0), -2.0, 32.762108), ((2.0, 64.0, 387.0), -4.0, 37.34896),
                                ((0.0, 56.0, 373.0), -5.0, 23.854458), ((0.0, 91.0, 463.0), -5.0, 51.098164)):
            x, y, z = projection.game_interest(eye, vert)
            self.assertAlmostEqual(y, want, delta=2e-5)
            self.assertEqual((x, z), (eye[0], 0.0))

    def test_matches_the_game_view_matrix(self):
        # frame 1799 of DishonestMuddyCoyote.slp (Battlefield), from a camera export
        eye, interest = (7.0864463, 33.748684, 208.5777), (10.68385, 16.60999, 0.0)
        view = (0.9998512, 1.21354055e-11, 0.017244743, -10.6822605, 0.0014120212, 0.99664193, -0.08186907,
                -16.569296, -0.017186837, 0.081881255, 0.9964938, -210.48798)
        right, up, fwd = projection.LookAtCamera(eye, interest, 30.0).axes
        look = tuple(-c for c in fwd)
        for row, axis in enumerate((right, up, look)):
            for col in range(3):
                self.assertAlmostEqual(view[4 * row + col], axis[col], delta=1e-6)
            self.assertAlmostEqual(view[4 * row + 3], -sum(axis[i] * eye[i] for i in range(3)), delta=1e-4)


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
