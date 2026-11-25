#!/usr/bin/env python3
"""Tests for slp2alpha's replay reader and its name tag rewriting, on a small made-up replay (no Dolphin needed).

    python3 tools/slp2alpha/test_slp.py
"""

from __future__ import annotations

import argparse
import struct
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from slp2alpha import slp  # noqa: E402
from slp2alpha.__main__ import nametag_arg  # noqa: E402

GAME_START_SIZE = 0x2FF   # v3.17's
POST_FRAME_SIZE = 0x50
# What the slot's name is followed by in a real replay: its other settings (rumble on, handicap 5).
SETTINGS = b"\x00\x01\x05\x00\x00\x00\x00\x00"


def make_replay(path: Path, tags, version=(3, 17, 0), size=GAME_START_SIZE) -> Path:
    """A replay of one frame on Battlefield with these ports' tags: text, or None for none."""
    start = bytearray(size + 1)
    start[0] = slp.EVENT_GAME_START
    start[1:4] = bytes(version)
    start[0x13:0x15] = struct.pack(">H", 31)
    for port in range(slp.PORTS):
        tag = tags[port] if port < len(tags) else None
        start[slp.PLAYER_NAMETAG_ID + port * slp.PLAYER_STRIDE] = slp.NO_NAMETAG if tag is None else port
        at = slp.NAMETAG_TEXT + port * slp.NAMETAG_STRIDE
        if tag is not None and at + slp.NAMETAG_STRIDE <= len(start):
            start[at:at + slp.NAMETAG_STRIDE] = tag.encode("cp932") + SETTINGS
    frame = bytes([slp.EVENT_POST_FRAME]) + struct.pack(">i", 100) + bytes(POST_FRAME_SIZE - 4)
    sizes = bytes([slp.EVENT_GAME_START]) + struct.pack(">H", size) + \
        bytes([slp.EVENT_POST_FRAME]) + struct.pack(">H", POST_FRAME_SIZE)
    raw = bytes([slp.EVENT_PAYLOAD_SIZES, len(sizes) + 1]) + sizes + bytes(start) + frame
    path.write_bytes(b"{U\x03raw[$U#l" + struct.pack(">I", len(raw)) + raw + b"}")
    return path


class Tests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)
        self.replay = make_replay(self.tmp / "game.slp", ["ＤＵＦＦ", None, None, "ＢＯＺＯ"])

    def tearDown(self):
        self.dir.cleanup()

    def tag_bytes(self, path: Path, port: int) -> bytes:
        data = path.read_bytes()
        pos, _ = slp._game_start(data, path.name)
        at = pos + slp.NAMETAG_TEXT + port * slp.NAMETAG_STRIDE
        return data[at:at + slp.NAMETAG_STRIDE]


class Reading(Tests):
    def test_the_tags_read_as_plain_text(self):
        r = slp.read_replay(self.replay)
        self.assertEqual(r.nametags, ["DUFF", None, None, "BOZO"])
        self.assertEqual((r.stage_id, r.last_frame), (31, 100))

    def test_a_replay_too_old_to_hold_their_text_has_none(self):
        old = make_replay(self.tmp / "old.slp", ["ＤＵＦＦ"], version=(1, 0, 0), size=0x140)
        self.assertEqual(slp.read_replay(old).nametags, [None] * 4)

    def test_a_cpu_has_no_tag(self):
        data = bytearray(self.replay.read_bytes())
        pos, _ = slp._game_start(data, "game.slp")
        data[pos + slp.PLAYER_STATUS] = 1
        self.replay.write_bytes(bytes(data))
        self.assertEqual(slp.read_replay(self.replay).nametags, [None, None, None, "BOZO"])


class Encoding(Tests):
    def test_letters_digits_and_a_few_marks_are_one_byte(self):
        self.assertEqual(slp.encode_nametag("Zubair 7"), b"Zubair 7")
        self.assertEqual(slp.encode_nametag("A.B,C'D-"), b"A.B,C'D-")

    def test_other_symbols_go_in_full_width(self):
        self.assertEqual(slp.encode_nametag("!?"), "！？".encode("cp932"))
        self.assertEqual(slp.encode_nametag("アイ"), "アイ".encode("cp932"))

    def test_typed_full_width_is_the_same_character(self):
        self.assertEqual(slp.encode_nametag("ＤＵＦＦ"), b"DUFF")
        self.assertEqual(slp.encode_nametag("！"), "！".encode("cp932"))

    def test_eight_bytes_at_most(self):
        self.assertEqual(len(slp.encode_nametag("ZUBAIR77")), 8)
        with self.assertRaises(ValueError):
            slp.encode_nametag("ZUBAIR777")
        with self.assertRaises(ValueError):
            slp.encode_nametag("AB!?&*")   # 1 + 1 + 2 + 2 + 2 + 2 bytes

    def test_characters_the_font_lacks(self):
        for text in ("é", "😀", "\t", "`", '"', "\\", "日", "゛"):
            with self.assertRaises(ValueError, msg=text):
                slp.encode_nametag(text)

    def test_the_option(self):
        self.assertEqual(nametag_arg("P1=ZUBAIR"), (0, b"ZUBAIR"))
        self.assertEqual(nametag_arg("p4="), (3, b""))
        self.assertEqual(nametag_arg("2=A=B"), (1, b"A" + "＝".encode("cp932") + b"B"))
        for bad in ("P5=X", "ZUBAIR", "P1", "P1=TOOLONGTAG"):
            with self.assertRaises(argparse.ArgumentTypeError, msg=bad):
                nametag_arg(bad)


class Writing(Tests):
    def test_a_tag_is_rewritten_and_the_rest_left_alone(self):
        out = self.tmp / "out.slp"
        slp.write_nametags(self.replay, out, {0: b"ZUBAIR"})
        self.assertEqual(slp.read_replay(out).nametags, ["ZUBAIR", None, None, "BOZO"])
        self.assertEqual(self.tag_bytes(out, 0)[:7], b"ZUBAIR\0")
        self.assertEqual(self.tag_bytes(out, 0)[8:], SETTINGS)   # the slot's settings survive
        before, after = self.replay.read_bytes(), out.read_bytes()
        self.assertEqual(len(before), len(after))
        changed = [i for i in range(len(before)) if before[i] != after[i]]
        pos, _ = slp._game_start(before, "game.slp")
        at = pos + slp.NAMETAG_TEXT
        self.assertTrue(all(at <= i < at + 7 for i in changed))

    def test_an_eight_byte_tag_ends_where_the_slots_name_does(self):
        out = self.tmp / "out.slp"
        slp.write_nametags(self.replay, out, {3: b"ZUBAIR77"})
        self.assertEqual(self.tag_bytes(out, 3), b"ZUBAIR77" + SETTINGS)

    def test_an_empty_tag_hides_it(self):
        out = self.tmp / "out.slp"
        slp.write_nametags(self.replay, out, {0: b"", 3: b""})
        self.assertEqual(slp.read_replay(out).nametags, [None] * 4)

    def test_the_replay_itself_is_untouched(self):
        before = self.replay.read_bytes()
        slp.write_nametags(self.replay, self.tmp / "out.slp", {0: b"X"})
        self.assertEqual(self.replay.read_bytes(), before)

    def test_only_a_tag_that_is_shown(self):
        with self.assertRaises(slp.ReplayError) as e:
            slp.write_nametags(self.replay, self.tmp / "out.slp", {1: b"X"})
        self.assertIn("P2 has no name tag", str(e.exception))

    def test_not_in_a_replay_too_old_to_hold_them(self):
        old = make_replay(self.tmp / "old.slp", ["ＤＵＦＦ"], version=(1, 0, 0), size=0x140)
        with self.assertRaises(slp.ReplayError):
            slp.write_nametags(old, self.tmp / "out.slp", {0: b"X"})


if __name__ == "__main__":
    unittest.main()
