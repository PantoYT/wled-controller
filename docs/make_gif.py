"""docs/evolution.gif: every board this project went through, rendered with the same camera.

    python make_gif.py [--font path/to/mono.ttf]

Needs kicad-cli (found as in ../rev2/fab.py) and Pillow. Frames are rendered into a temporary
folder; the captions use a monospace TrueType font if one is given or found, else Pillow's own.
"""
import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "rev2"))
from fab import run  # noqa: E402

FRAMES = [  # board, side, title, caption, ms
    ("rev1/wled-controller", "top", "rev 1.0", "1 channel, built and on the desk", 1800),
    ("rev2/old-variants/wled-controller-v2-phi", "top", "rev 2.0 phi", "6 channels, screw terminal + JST-XH each", 1800),
    ("rev2/old-variants/wled-controller-v2-120", "top", "rev 2.0 120", "8 channels, 120 x 74 mm: too big", 1800),
    ("rev2/old-variants/wled-controller-v2-100", "top", "rev 2.0 100", "8 channels, 100 x 100 mm: a square", 1800),
    ("rev2/old-variants/wled-controller-v2-phi4", "top", "rev 2.0 phi4", "4 channels, status LEDs, gold logo: dropped", 1800),
    ("rev2/wled-controller-v2-wall", "top", "rev 2.0 wall", "6 channels, DC jack from the top, wall mount", 2600),
    ("rev2/wled-controller-v2-wall", "bottom", "rev 2.0 wall, back", "channel table on the back", 2000),
]
FONTS = [r"C:\Windows\Fonts\consola.ttf", "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def font(path, size):
    for p in ([path] if path else []) + FONTS:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font")
    a = ap.parse_args()
    big, small = font(a.font, 34), font(a.font, 24)
    frames, durations = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (board, side, title, caption, ms) in enumerate(FRAMES):
            png = Path(tmp) / f"{i}.png"
            run("pcb", "render", "--use-board-stackup-colors", "--background", "opaque", "--side", side,
                "--zoom", "0.9", "-w", "1200", "-h", "800", "-o", str(png), str(ROOT / f"{board}.kicad_pcb"))
            im = Image.open(png).convert("RGB").resize((900, 600), Image.LANCZOS)
            out = Image.new("RGB", (900, 692), (14, 15, 18))
            out.paste(im, (0, 0))
            d = ImageDraw.Draw(out)
            d.text((28, 614), title, font=big, fill=(240, 240, 240))
            d.text((28, 656), caption, font=small, fill=(170, 172, 180))
            frames.append(out.quantize(colors=200, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
            durations.append(ms)
    frames[0].save(HERE / "evolution.gif", save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True)
    print(f"evolution.gif: {len(frames)} frames, {(HERE / 'evolution.gif').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
