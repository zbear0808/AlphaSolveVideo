#!/usr/bin/env python3
"""Tests for stagedata.py: a made-up stage file (always run) and the real ones on your ISO (skipped without one).

    python3 tools/logo-stage/test_stagedata.py
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stagedata  # noqa: E402
from slp2alpha import locate  # noqa: E402


def build_dat(roots: Dict[str, int], data: bytes, relocs: Sequence[int]) -> bytes:
    """A .dat file: header, data block, relocation table, root nodes, string table."""
    strings, name_at = b"", {}
    for name in roots:
        name_at[name] = len(strings)
        strings += name.encode() + b"\0"
    table = 0x20 + len(data)
    nodes = table + 4 * len(relocs)
    size = nodes + 8 * len(roots) + len(strings)
    header = struct.pack(">5I", size, len(data), len(relocs), len(roots), 0).ljust(0x20, b"\0")
    return (header + data + struct.pack(f">{len(relocs)}I", *relocs)
            + b"".join(struct.pack(">II", at, name_at[name]) for name, at in roots.items()) + strings)


def build_stage(scale: float = 0.5) -> bytes:
    """A little stage: a flat top from -80 to 80 whose outer 40 on each side are ledge floors, a drop-through
    platform above it in the same joint, a floating floor in a second joint and a ceiling; as the file stores
    it, before scaling."""
    verts: List[Tuple[float, float]] = [(-80, 0), (-40, 0), (40, 0), (80, 0), (-40, 40), (40, 40), (-12, 10), (12, 10),
                                        (80, -40), (-80, -40)]
    # (v0, v1, prev, next, alt prev, alt next, kind, property)
    lines = [(0, 1, -1, 1, -1, -1, 1, 0x200), (1, 2, 0, 2, -1, -1, 1, 0), (2, 3, 1, -1, -1, -1, 1, 0x200),
             (4, 5, -1, -1, -1, -1, 1, 0x100), (6, 7, -1, -1, -1, -1, 1, 0x100), (8, 9, -1, -1, -1, -1, 2, 0)]
    joints = [((0, 4), (5, 1), (0, 0), (0, 0), (0, 0), (8, 6)), ((4, 1), (0, 0), (0, 0), (0, 0), (0, 0), (6, 2))]
    data = b"".join(struct.pack(">ff", *v) for v in verts)
    line_at = len(data)
    data += b"".join(struct.pack(">hhhhhhHH", *ln) for ln in lines)
    joint_at = len(data)
    for floors, ceilings, rights, lefts, dyn, vtx in joints:
        data += struct.pack(">10h4f2h", *floors, *ceilings, *rights, *lefts, *dyn, -80.0, -40.0, 80.0, 40.0, *vtx)
    coll = len(data)
    data += struct.pack(">IiIi", 0, len(verts), line_at, len(lines))
    data += struct.pack(">10h", 0, 5, 5, 1, 0, 0, 0, 0, 0, 0)
    data += struct.pack(">Ii", joint_at, len(joints)) + b"\0" * 4
    param = len(data)
    data += struct.pack(">f", scale).ljust(0x50, b"\0") + struct.pack(">6f", 1.0, 2.0, 3.0, 30.0, -10.0, 5.0)
    return build_dat({"coll_data": coll, "grGroundParam": param}, data, [coll, coll + 8, coll + 0x24])


class DatTest(unittest.TestCase):
    def test_roots_and_pointers(self):
        dat = stagedata.read_dat(build_stage())
        self.assertEqual(sorted(dat.roots), ["coll_data", "grGroundParam"])
        self.assertEqual(len(dat.relocs), 3)
        self.assertEqual(struct.unpack_from(">f", dat.data, dat.roots["grGroundParam"])[0], 0.5)

    def test_not_a_dat(self):
        with self.assertRaises(ValueError):
            stagedata.read_dat(b"\xff" * 64)


class MadeUpStageTest(unittest.TestCase):
    def setUp(self):
        self.geo = stagedata.parse_stage(31, stagedata.read_dat(build_stage(0.5)))

    def test_coordinates_are_scaled(self):
        self.assertAlmostEqual(self.geo.scale, 0.5)
        self.assertEqual((self.geo.lines[0].x0, self.geo.lines[0].y0, self.geo.lines[2].x1), (-40.0, 0.0, 40.0))

    def test_camera_is_not_scaled(self):
        cam = self.geo.camera
        self.assertEqual((cam.eye, cam.fov_deg, cam.vert_angle_deg, cam.horz_angle_deg), ((1.0, 2.0, 3.0), 30.0, -10.0, 5.0))

    def test_main_stage(self):
        main = self.geo.main_stage
        self.assertEqual((main.joint, main.lines, main.top_y), (0, (0, 1, 2), 0.0))
        self.assertEqual((main.ledge_left, main.ledge_right, main.top_x), ((-40.0, 0.0), (40.0, 0.0), (-40.0, 40.0)))

    def test_platforms(self):
        by_line = {p.line: p for p in self.geo.platforms}
        self.assertEqual(sorted(by_line), [3, 4])
        self.assertEqual((by_line[3].x0, by_line[3].y0, by_line[3].x1, by_line[3].drop_through, by_line[3].movable,
                          by_line[3].joint), (-20.0, 20.0, 20.0, True, False, 0))
        self.assertEqual((by_line[4].movable, by_line[4].joint), (True, 1))

    def test_every_line_is_kept(self):
        self.assertEqual([l.kind for l in self.geo.lines], ["floor"] * 5 + ["ceiling"])
        self.assertEqual([l.joint for l in self.geo.lines], [0, 0, 0, 0, 1, 0])
        self.assertEqual([l.ledge for l in self.geo.lines], [True, False, True, False, False, False])

    def test_no_ledges_means_no_main_stage(self):
        flat = [l for l in self.geo.lines if not l.ledge]
        with self.assertRaises(ValueError):
            stagedata.find_main_stage(flat)

    def test_ledges_on_one_side_are_not_a_main_stage(self):
        with self.assertRaises(ValueError):
            stagedata.find_main_stage(self.geo.lines[:1] + self.geo.lines[3:])


class NamesTest(unittest.TestCase):
    def test_stage_names(self):
        for text, stage_id in (("31", 31), ("bf", 31), ("Battlefield", 31), ("final destination", 32), ("FD", 32),
                               ("yoshi's story", 8), ("Yoshis Story", 8), ("pokemon stadium", 3),
                               ("Pokémon Stadium", 3), ("GrOp.dat", 28), ("dream", 28), ("fountain", 2)):
            self.assertEqual(stagedata.find_stage(text), stage_id, text)
        with self.assertRaises(KeyError):
            stagedata.find_stage("hyrule")

    def test_no_imports_from_the_probe_folders(self):
        stray = [m.__name__ for m in sys.modules.values() if "shyguy-probe" in str(getattr(m, "__file__", ""))
                 or "/research/" in str(getattr(m, "__file__", ""))]
        self.assertEqual(stray, [])


# What the community uses for the six legal stages, to within what rounding it needs.
LEDGE_X = {31: 68.4, 32: 85.57, 28: 77.27, 8: 56.0, 2: 63.35, 3: 87.75}


class IsoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.iso = locate.find_iso()
            locate.check_iso(cls.iso)
        except locate.NotFound as e:
            raise unittest.SkipTest(str(e))

    def test_ledges(self):
        for stage_id, x in LEDGE_X.items():
            main = stagedata.load_stage(stage_id, self.iso).main_stage
            self.assertAlmostEqual(main.ledge_left[0], -x, delta=0.005, msg=stage_id)
            self.assertAlmostEqual(main.ledge_right[0], x, delta=0.005, msg=stage_id)

    def test_top_surface(self):
        for stage_id in LEDGE_X:
            main = stagedata.load_stage(stage_id, self.iso).main_stage
            self.assertAlmostEqual(main.top_y, 0.0, delta=0.01, msg=stage_id)
            self.assertAlmostEqual(main.top_x[0], -main.top_x[1], delta=0.01, msg=stage_id)
            self.assertLessEqual(main.top_x[1], main.ledge_right[0] + 0.01, msg=stage_id)

    def test_ledge_heights(self):
        heights = {stage_id: stagedata.load_stage(stage_id, self.iso).main_stage.ledge_right[1] for stage_id in LEDGE_X}
        self.assertEqual(heights[8], -3.5)  # Yoshi's Story: the ledge is the foot of a slope
        self.assertAlmostEqual(heights[2], 0.624, delta=0.001)  # Fountain of Dreams: a raised lip
        for stage_id in (31, 32, 3):
            self.assertEqual(heights[stage_id], 0.0)

    def test_cameras(self):
        bf, ys = (stagedata.load_stage(i, self.iso).camera for i in (31, 8))
        self.assertEqual((bf.eye, bf.fov_deg, bf.vert_angle_deg), ((0.0, 100.0, 300.0), 30.0, -12.0))
        self.assertEqual((ys.eye, ys.fov_deg, ys.vert_angle_deg), ((2.0, 64.0, 387.0), 25.0, -4.0))

    def test_battlefield_platforms(self):
        geo = stagedata.load_stage(31, self.iso)
        got = sorted((round(p.x0, 2), round(p.x1, 2), round(p.y0, 2)) for p in geo.platforms)
        self.assertEqual(got, [(-57.6, -20.0, 27.2), (-18.8, 18.8, 54.4), (20.0, 57.6, 27.2)])
        self.assertTrue(all(p.drop_through and not p.movable for p in geo.platforms))

    def test_stages_with_a_second_joint(self):
        ys = stagedata.load_stage(8, self.iso)
        self.assertEqual((ys.main_stage.joint, [p.joint for p in ys.platforms if p.movable]), (1, [0]))

    def test_cached(self):
        self.assertIs(stagedata.load_stage(32, self.iso), stagedata.load_stage(32, self.iso))

    def test_bad_stage(self):
        with self.assertRaises(KeyError):
            stagedata.load_stage(1, self.iso)


if __name__ == "__main__":
    unittest.main()
