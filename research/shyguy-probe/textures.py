#!/usr/bin/env python3
"""Which textures does a Shy Guy use, and what are Dolphin's names for them?

    python3 research/shyguy-probe/textures.py diff [--full] [--from 400 --to 490]
    python3 research/shyguy-probe/textures.py iso [--compare DIR]

diff  plays the same replay window twice in the headless build with DumpTextures on: once with Shy Guys
      drawn, once with the "Hide Shy Guys" code. The textures that only exist in the first dump are the
      ones Shy Guys draw. (A short window is enough: textures load when first drawn, even off screen.)
iso   works the names out without Dolphin: finds the texture descriptors in GrSt.dat (Yoshi's Story) on
      your ISO and hashes their pixels the way Dolphin does. With --compare DIR, it also decodes them and
      checks them against the PNGs a diff run dumped.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from common import (SHY_GUY_HIDE_CODE, SHY_GUY_TEXTURES, add_tool_args, cli, find_replay, find_tools,
                    need_imaging, run_variant, work_dir)
from iso import GX_FORMATS, Archive, Disc, decode_rgb5a3, dolphin_name, image_descs, texture_size
from slp2alpha import locate, slp


def cmd_diff(args) -> int:
    if args.sheet:
        need_imaging()
    tools = find_tools(args)
    replay = find_replay(args.replay)
    work = work_dir(args, "textures")
    start, end = (-123, slp.read_replay(replay).last_frame) if args.full else (args.start, args.end)
    print(f"{replay.name}: playing frames {start}..{end} twice")
    settings = ["DumpTextures = True", "HiresTextures = False"]
    drawn = run_variant(tools, replay, work, "shy-guys-drawn", [], start, end, record=False, gfx=settings)
    hidden = run_variant(tools, replay, work, "shy-guys-hidden", [SHY_GUY_HIDE_CODE], start, end, record=False,
                         gfx=settings)
    a, b = drawn.dumped_textures(), hidden.dumped_textures()
    only = sorted(set(a) - set(b))
    print(f"textures dumped: {len(a)} with Shy Guys drawn, {len(b)} with them hidden")
    print(f"only when Shy Guys are drawn ({len(only)}):")
    for name in only:
        print(f"  {name}")
    if set(b) - set(a):
        print(f"(also only in the hidden run: {sorted(set(b) - set(a))})")
    out = work / "shy-guy-textures"
    out.mkdir(exist_ok=True)
    for name in only:
        shutil.copy(a[name], out / f"{name}.png")
    print(f"copied to {out}")
    if args.sheet:
        _sheet(out)
    expected = {name for name, _, _ in SHY_GUY_TEXTURES}
    if set(only) != expected:
        print("DIFFERENT from SHY_GUY_TEXTURES in common.py: update it, or check the replay/ISO/build",
              f"\n  expected {sorted(expected)}")
        return 1
    print("same as SHY_GUY_TEXTURES in common.py")
    return 0


def _sheet(folder: Path) -> None:
    """The textures at 4x over magenta, side by side, to look at."""
    from PIL import Image

    images = [Image.open(p).convert("RGBA") for p in sorted(folder.glob("*.png"))]
    if not images:
        return
    scale, gap = 4, 20
    sheet = Image.new("RGBA", (sum(i.width * scale + gap for i in images) + gap,
                               max(i.height for i in images) * scale + 2 * gap), (255, 0, 255, 255))
    x = gap
    for im in images:
        big = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        sheet.alpha_composite(big, (x, gap))
        x += big.width + gap
    sheet.convert("RGB").save(folder.parent / "shy-guy-textures-sheet.png")
    print(f"sheet: {folder.parent / 'shy-guy-textures-sheet.png'}")


def cmd_iso(args) -> int:
    if args.compare:
        need_imaging()
    iso = locate.find_iso(args.iso)
    locate.check_iso(iso)
    archive = Archive(Disc(iso).read_file("GrSt.dat"))
    found = {}
    for desc in image_descs(archive):
        name = dolphin_name(archive, desc)
        if name:
            found.setdefault(name, desc)
    print(f"GrSt.dat: {len(found)} unpaletted, unmipmapped textures named")
    status = 0
    for name, width, height in SHY_GUY_TEXTURES:
        desc = found.get(name)
        if not desc:
            print(f"  {name}: NOT in GrSt.dat")
            status = 1
            continue
        print(f"  {name}: {GX_FORMATS[desc.format]} {desc.width}x{desc.height} at GrSt.dat data+0x{desc.data_offset:x}")
        if args.compare:
            status |= _compare(archive, desc, Path(args.compare) / f"{name}.png")
    return status


def _compare(archive: Archive, desc, png: Path) -> int:
    import numpy as np
    from PIL import Image

    if not png.exists():
        print(f"      no dump to compare: {png}")
        return 1
    if GX_FORMATS[desc.format] != "RGB5A3":
        print("      (only RGB5A3 is decoded here)")
        return 0
    size = texture_size(desc.width, desc.height, desc.format)
    mine = decode_rgb5a3(archive.data[desc.data_offset:desc.data_offset + size], desc.width, desc.height)
    theirs = np.asarray(Image.open(png).convert("RGBA"), dtype=int)
    seen = theirs[..., 3] > 0  # Dolphin leaves the colour of fully transparent texels arbitrary
    same = theirs.shape[:2] == mine.shape[:2] and (theirs[..., 3] == mine[..., 3]).all() \
        and np.abs(theirs[seen] - mine[seen].astype(int)).max() == 0
    print(f"      decoded pixels {'match' if same else 'DIFFER from'} Dolphin's dump")
    return 0 if same else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff", help="find the Shy Guy textures by diffing two Dolphin texture dumps")
    add_tool_args(d)
    d.add_argument("--from", dest="start", type=int, default=400, help="first replay frame to play")
    d.add_argument("--to", dest="end", type=int, default=490, help="last replay frame to play")
    d.add_argument("--full", action="store_true", help="play the whole replay (about 2 x 100 s)")
    d.add_argument("--sheet", action=argparse.BooleanOptionalAction, default=True,
                   help="also write a picture of the textures (needs Pillow)")
    d.set_defaults(func=cmd_diff)
    i = sub.add_parser("iso", help="work out the texture names from the ISO")
    i.add_argument("--iso", help="Melee NTSC 1.02 ISO (default: the one set in the Slippi Launcher)")
    i.add_argument("--compare", help="a folder of dumped PNGs (diff's shy-guy-textures) to compare pixels with")
    i.set_defaults(func=cmd_iso)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    cli(main)
