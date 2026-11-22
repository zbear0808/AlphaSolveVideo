"""How far apart two raw RGBA frames are, in their colour (alpha ignored): mean and largest difference out of 255,
the share of values more than 4/255 apart, and PSNR. Needs numpy (Blender's Python has it).

    python3 frame_diff.py A.rgba B.rgba WIDTH HEIGHT
"""
import sys

import numpy as np

a_path, b_path, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
a = np.fromfile(a_path, dtype=np.uint8)[:w * h * 4].reshape(h, w, 4)[..., :3].astype(np.int16)
b = np.fromfile(b_path, dtype=np.uint8)[:w * h * 4].reshape(h, w, 4)[..., :3].astype(np.int16)
d = np.abs(a - b)
mse = max(1e-9, float((d.astype(np.float64) ** 2).mean()))
print(f"mean {d.mean():.3f}/255, max {d.max()}, over 4/255: {(d > 4).mean() * 100:.2f}%, "
      f"PSNR {10 * np.log10(255 ** 2 / mse):.1f} dB")
