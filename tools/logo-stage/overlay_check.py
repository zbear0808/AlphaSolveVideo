"""Draw where the camera math puts a stage's collision geometry on a real frame, to check it by eye and by number.

    python3 tools/logo-stage/overlay_check.py FRAME.png STAGE [--scale 1] [--out FILE.png] [--zoom X0 Y0 X1 Y1]

FRAME.png is a recording of that stage with the fixed camera (tools/logo-stage/dolphin_frames.py makes them). The
main stage's top edge, its ledges and every other floor are projected with the stage's own camera and drawn as
thin magenta lines (floors) and cyan crosses (ledges, ends of the flat top). The stage's collision is on the plane
z = 0, which is the middle of the stage's visible thickness, so the lines should run through the middle of the
platforms' top faces.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "slp2alpha"))
import plate  # noqa: E402
import stagedata  # noqa: E402


def draw(frame: Path, stage: int, scale: int, out: Path, zoom=None, iso=None) -> None:
    from PIL import Image, ImageDraw

    geo = stagedata.load_stage(stage, iso)
    cam = plate.camera_of(geo)
    im = Image.open(frame).convert("RGB")
    w, h = im.size
    if (w, h) != cam.size(scale):
        raise SystemExit(f"{frame.name} is {w}x{h}; --scale {scale} should give {cam.size(scale)}")
    k = 4
    big = im.resize((w * k, h * k), Image.NEAREST)
    d = ImageDraw.Draw(big)

    def px(p):
        u, v = cam.project(p, scale)
        return (u + 0.5) * k, (v + 0.5) * k

    for line in geo.lines:
        if line.kind != "floor" or line.dynamic:
            continue
        a, b = px((line.x0, line.y0, 0.0)), px((line.x1, line.y1, 0.0))
        d.line([a, b], fill=(255, 0, 255), width=1)
    m = geo.main_stage
    for name, p in (("ledge", m.ledge_left), ("ledge", m.ledge_right)):
        x, y = px((p[0], p[1], 0.0))
        d.line([(x - 18, y), (x + 18, y)], fill=(0, 255, 255), width=1)
        d.line([(x, y - 18), (x, y + 18)], fill=(0, 255, 255), width=1)
    for xx in m.top_x:
        x, y = px((xx, m.top_y, 0.0))
        d.line([(x - 10, y - 10), (x + 10, y + 10)], fill=(255, 255, 0), width=1)
        d.line([(x - 10, y + 10), (x + 10, y - 10)], fill=(255, 255, 0), width=1)
    if zoom:
        big = big.crop(tuple(int(c * k) for c in zoom))
    big.save(out)
    print(f"wrote {out} ({big.size[0]}x{big.size[1]})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("frame")
    ap.add_argument("stage")
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--out", default="overlay.png")
    ap.add_argument("--zoom", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--iso")
    args = ap.parse_args()
    draw(Path(args.frame), stagedata.find_stage(args.stage), args.scale, Path(args.out), args.zoom, args.iso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
