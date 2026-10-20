"""Turn a picture into back-silkscreen art for the `wall` board: art/silk-runs.json.

The picture is fitted to the full board width (top and bottom padded with black), dithered
(Floyd-Steinberg) on a PIXEL mm grid and written as each row's runs of white pixels.
gen_board.py mirrors it onto the back silkscreen, cuts it away round every pad and hole
pixel by pixel, and merges the runs into rectangles.

    python make_art.py [picture] [--pixel 0.25]   # default: bongo-space.png
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageEnhance

HERE = Path(__file__).resolve().parent
W, H = 100.0, 61.8

ap = argparse.ArgumentParser()
ap.add_argument("picture", nargs="?", default=str(HERE / "bongo-space.png"))
ap.add_argument("--pixel", type=float, default=0.25, help="silk dot pitch, mm (JLC: 0.15 min line)")
ap.add_argument("--contrast", type=float, default=1.4)
ap.add_argument("--gamma", type=float, default=1.6, help=">1 darkens the mid tones")
a = ap.parse_args()

nx, ny = int(W / a.pixel), int(H / a.pixel)
src = Image.open(a.picture).convert("L")
sw, sh = src.size
canvas = Image.new("L", (sw, round(sw * H / W)), 0)
canvas.paste(src, (0, (canvas.size[1] - sh) // 2))
g = canvas.resize((nx, ny), Image.LANCZOS)
g = ImageEnhance.Contrast(g).enhance(a.contrast)
g = g.point(lambda v: int(255 * (v / 255) ** a.gamma))
bits = g.convert("1")
bits.convert("L").resize((nx * 3, ny * 3), Image.NEAREST).save(HERE / "preview.png")

px = bits.load()
rows = []
for j in range(ny):
    runs, i = [], 0
    while i < nx:
        if px[i, j]:
            k = i
            while k < nx and px[k, j]:
                k += 1
            runs.append([i, k])
            i = k
        else:
            i += 1
    rows.append(runs)
(HERE / "silk-runs.json").write_text(json.dumps({"pixel": a.pixel, "nx": nx, "ny": ny, "rows": rows}))
print(f"{nx} x {ny} px at {a.pixel} mm, {sum(map(len, rows))} runs -> silk-runs.json, preview.png")
