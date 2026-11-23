"""The model's difference between two EEVEE sample counts, where it matters: on the model itself, not the whole frame
(the logo covers about a sixth of the plate). Run in samples.sh's output folder, with Blender's Python (numpy):

    python3 model_diff.py FFMPEG

For each sample count against 64, and frames 0, 30 and 59: on the plate, the mean, 99th percentile and largest
difference of the premultiplied colour (what the composite shows) over the pixels either plate covers; after the CRT,
the mean and 99th percentile over the model's bounding box, scaled to the CRT's size.
"""
import subprocess, sys
import numpy as np
ff = sys.argv[1]
def load(p):
    out = subprocess.run([ff, "-v", "error", "-i", p, "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True, check=True).stdout
    probe = str(__import__("pathlib").Path(ff).with_name("ffprobe" + __import__("pathlib").Path(ff).suffix))
    w, h = map(int, subprocess.run([probe, "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip().split(","))
    return np.frombuffer(out, np.uint8).reshape(h, w, 4).astype(np.float64)
for s in (16, 8, 4):
    for n in (0, 30, 59):
        a, b = load(f"s64-plate-{n}.png"), load(f"s{s}-plate-{n}.png")
        pa, pb = a[..., :3] * a[..., 3:] / 255, b[..., :3] * b[..., 3:] / 255   # premultiplied: what the composite shows
        m = (a[..., 3] > 0) | (b[..., 3] > 0)
        ys, xs = np.nonzero(a[..., 3] > 0)
        dp = np.abs(pa - pb)[m]
        ca, cb = load(f"s64-crt-{n}/000001.png"), load(f"s{s}-crt-{n}/000001.png")
        sy, sx = ca.shape[0] / a.shape[0], ca.shape[1] / a.shape[1]
        box = (slice(int(ys.min() * sy), int((ys.max() + 1) * sy)), slice(int(xs.min() * sx), int((xs.max() + 1) * sx)))
        dc = np.abs(ca[box][..., :3] - cb[box][..., :3])
        print(f"{s} vs 64, frame {n}: model covers {m.mean()*100:.0f}% of the plate; on it: mean {dp.mean():.2f}/255, "
              f"99th pct {np.percentile(dp, 99):.0f}, max {dp.max():.0f}; CRT in the model's box: mean {dc.mean():.2f}/255, "
              f"99th pct {np.percentile(dc, 99):.0f}")
