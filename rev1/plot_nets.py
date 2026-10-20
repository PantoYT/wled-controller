"""Draw one PNG per net group, for marking up routes by hand (white background).

    "C:/Program Files/KiCad/10.0/bin/python.exe" plot_nets.py

Writes renders/nets/*.png. Red = top layer, blue = bottom layer.
"""
import os

import pcbnew
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders", "nets")
OX, OY, W, H = 100.0, 100.0, 100.0, 61.8
S = 16                      # px per mm
M = 60                      # margin, px

GROUPS = [
    ("00-blank", "All parts, no tracks: draw your own", []),
    ("01-vin-raw", "VIN_RAW: power inputs to fuse (1.5 mm)", ["VIN_RAW"]),
    ("02-5v", "+5V: fuse to ESP VIN, C1, C3, U1 and every + output (1.5 mm)", ["+5V"]),
    ("03-3v3", "+3V3: ESP 3V3 to C2 (1.0 mm)", ["+3V3"]),
    ("04-gnd", "GND: no tracks, the copper pour on both layers; dots = stitching vias", ["GND"]),
    ("05-gpio4", "ESP_D4: GPIO4 to the four shifter inputs (0.4 mm)", ["ESP_D4"]),
    ("06-shifter-out", "DATAx_RAW: shifter outputs to resistors (0.4 mm)",
     ["DATA1_RAW", "DATA2_RAW", "DATA3_RAW", "DATA4_RAW"]),
    ("07-data-out", "DATAx: resistors to outputs (1 JST, 2 screw, 3 pins, 4 solder)",
     ["DATA1", "DATA2", "DATA3", "DATA4"]),
]

LABELS = {
    "J1": "DC jack", "J2": "screw IN", "J3": "solder IN", "J4": "pins IN", "F1": "fuse",
    "C1": "C1 5V", "C2": "C2 3V3", "C3": "C3", "U1": "U1 shifter",
    "U2": "ESP left", "U3": "ESP right", "J5": "MAIN JST",
    "J6": "screw +", "J7": "screw -", "J8": "screw D/-", "J16": "pins out",
    "R1": "R1", "R2": "R2", "R3": "R3", "R4": "R4",
}


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def P(v):
    return (pcbnew.ToMM(v.x) - OX) * S + M, (pcbnew.ToMM(v.y) - OY) * S + M + 40


def main():
    os.makedirs(OUT, exist_ok=True)
    b = pcbnew.LoadBoard(os.path.join(HERE, "wled-controller.kicad_pcb"))
    f_lbl, f_title, f_pad = font(15), font(22), font(11)
    for key, title, nets in GROUPS:
        im = Image.new("RGB", (int(W * S) + 2 * M, int(H * S) + 2 * M + 40), "white")
        d = ImageDraw.Draw(im)
        d.text((M, 15), title, fill="black", font=f_title)
        d.rounded_rectangle([M, M + 40, M + W * S, M + 40 + H * S], radius=2 * S, outline="black", width=3)
        for fp in b.GetFootprints():
            cy = fp.GetCourtyard(pcbnew.F_CrtYd)
            if cy.OutlineCount() == 0:
                continue
            bb = cy.BBox()
            (x0, y0), (x1, y1) = P(bb.GetOrigin()), P(bb.GetEnd())
            d.rectangle([x0, y0, x1, y1], outline=(200, 200, 200))
            ref = fp.GetReference()
            if ref in LABELS:
                d.text((x0 + 3, y0 + 2), LABELS[ref], fill=(120, 120, 120), font=f_lbl)
        for t in b.GetTracks():
            if t.GetNetname() not in nets:
                continue
            if isinstance(t, pcbnew.PCB_VIA):
                x, y = P(t.GetPosition())
                r = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2 * S
                d.ellipse([x - r, y - r, x + r, y + r], fill=(150, 90, 200))
                continue
            col = (220, 50, 40) if t.GetLayer() == pcbnew.F_Cu else (40, 100, 220)
            w = max(2, int(pcbnew.ToMM(t.GetWidth()) * S))
            a, c = P(t.GetStart()), P(t.GetEnd())
            d.line([a, c], fill=col, width=w)
            for q in (a, c):
                d.ellipse([q[0] - w / 2, q[1] - w / 2, q[0] + w / 2, q[1] + w / 2], fill=col)
        for fp in b.GetFootprints():
            for p in fp.Pads():
                bb = p.GetBoundingBox()
                (x0, y0), (x1, y1) = P(bb.GetOrigin()), P(bb.GetEnd())
                on = p.GetNetname() in nets
                d.ellipse([x0, y0, x1, y1], fill=(255, 200, 0) if on else None,
                          outline="black" if on else (170, 170, 170), width=2)
                if on and p.GetNetname().startswith("DATA"):
                    d.text((x1 + 2, y0 - 12), p.GetNetname().replace("_RAW", "r"), fill="black", font=f_pad)
        d.text((M, M + 50 + H * S), "red = top layer   blue = bottom layer   yellow = pads of this net",
               fill=(90, 90, 90), font=f_lbl)
        im.save(os.path.join(OUT, key + ".png"))
        print("wrote", key)


if __name__ == "__main__":
    main()
