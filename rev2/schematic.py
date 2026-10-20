"""Schematic of the rev 2.0 `wall` board: docs/schematic-wall.svg and .png, drawn with schemdraw.

The board is generated straight from gen_board.py, without a KiCad schematic, so this drawing
is made from NETS below, and NETS is checked against the routed board:

    python schematic.py                                                # draw (needs schemdraw)
    "C:/Program Files/KiCad/10.0/bin/python.exe" schematic.py --check  # NETS == the board's nets

The check exits 1 on any difference, so the drawing cannot drift from the PCB unnoticed.
Pad names are the PCB's: U2 and U3 are the DevKit's two header sockets (U2 the 3V3 row,
U3 the VIN row), J11-J16 the strip terminals (1 = +, 2 = D, 3 = -).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PCB = HERE / "wled-controller-v2-wall.kicad_pcb"
OUT = HERE.parent / "docs" / "schematic-wall"
N = 6
GPIO = {1: ("D4", 5), 2: ("D18", 9), 3: ("D19", 10), 4: ("D21", 11), 5: ("D22", 14), 6: ("D23", 15)}

NETS = {
    "VIN_RAW": ["J1.1", "J2.2", "F1.1"],
    "+5V": ["F1.2", "C1.1", "C3.1", "U1.1", "U1.20", "U3.1"] + [f"F{10 + c}.1" for c in range(1, N + 1)],
    "+3V3": ["U2.1", "C2.1"],
    "GND": ["J1.2", "J1.3", "J2.1", "C1.2", "C2.2", "C3.2", "U1.8", "U1.9", "U1.10", "U1.19",
            "U2.2", "U3.2"] + [f"J{10 + c}.3" for c in range(1, N + 1)],
}
for c in range(1, N + 1):
    NETS[f"IO_CH{c}"] = [f"U2.{GPIO[c][1]}", f"U1.{1 + c}"]        # GPIO -> A1-A6
    NETS[f"OUT{c}_RAW"] = [f"U1.{19 - c}", f"R{c}.1"]               # B1-B6 -> 100R
    NETS[f"DATA{c}"] = [f"R{c}.2", f"J{10 + c}.2"]
    NETS[f"V_CH{c}"] = [f"F{10 + c}.2", f"J{10 + c}.1"]


def check() -> int:
    import pcbnew
    board = pcbnew.LoadBoard(str(PCB))
    got = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname():
                got.setdefault(p.GetNetname(), set()).add(f"{fp.GetReference()}.{p.GetNumber()}")
    want = {k: set(v) for k, v in NETS.items()}
    bad = 0
    for net in sorted(set(got) | set(want)):
        g, w = got.get(net, set()), want.get(net, set())
        if g != w:
            bad += 1
            print(f"{net}: only on the board {sorted(g - w)}, only in the drawing {sorted(w - g)}")
    print(f"{len(want)} nets, {bad} differences")
    return 1 if bad else 0


# ---------------------------------------------------------------- drawing
BG, INK, DIM = "#0e0f12", "#d4d7de", "#7d828e"
PWR, GND_C, SIG, OUT_C = "#e8834a", "#8a8f9a", "#58b6e8", "#7fd18b"


def draw() -> None:
    import schemdraw
    import schemdraw.elements as elm

    schemdraw.config(bgcolor=BG, color=INK, fontsize=11, lw=1.3, font="DejaVu Sans")
    d = schemdraw.Drawing(show=False)

    def ic(pins, size, at, anchor=None, pad=None):
        e = elm.Ic(pins=pins, size=size).theta(0)
        for side, (spacing, padding) in (pad or {}).items():
            e = e.side(side, spacing=spacing, pad=padding, label_size=11, pinlabel_size=9)
        if anchor:
            e = e.anchor(anchor)
        return d.add(e.at(at))

    def pin(name, side, a, num=None):
        return elm.IcPin(name=name, pin=num, side=side, anchorname=a)

    def gnd(at, dx=0.0, dy=-0.5):
        d.add(elm.Line().at(at).to((at[0] + dx, at[1] + dy)).color(GND_C))
        d.add(elm.Ground().color(GND_C))

    def vdd(at, name="+5V", dx=0.0, dy=0.5, color=PWR):
        d.add(elm.Line().at(at).to((at[0] + dx, at[1] + dy)).color(color))
        d.add(elm.Vdd().color(color).label(name, fontsize=10))

    # ---- U1, the shifter. Pins listed top to bottom (schemdraw fills a side bottom-up).
    u1 = ic([pin("DIR", "top", "DIR", "1"), pin("VCC", "top", "VCC", "20")]
            + [pin(f"A{c}", "left", f"A{c}", str(1 + c)) for c in range(8, 0, -1)]
            + [pin(f"B{c}", "right", f"B{c}", str(19 - c)) for c in range(8, 0, -1)]
            + [pin("OE", "bot", "OE", "19"), pin("GND", "bot", "GND", "10")],
            None, (14.0, -4.5), pad={"L": (1.0, 1.2), "R": (1.0, 1.2), "T": (1.4, 1.0), "B": (1.4, 1.0)})
    d.add(elm.Label().at((u1.center[0], u1.center[1] + 0.3)).label("U1\n74AHCT245", fontsize=11))
    d.add(elm.Label().at((u1.center[0], u1.center[1] - 0.9)).label("HCT or AHCT", fontsize=9, color=DIM))
    vdd(u1.DIR, dy=0.6)
    vdd(u1.VCC, dy=0.6)
    gnd(u1.OE)
    gnd(u1.GND)
    for c in (7, 8):                                   # unused inputs must not float
        a = getattr(u1, f"A{c}")
        gnd(a, dx=-1.0, dy=0.0)
    for c in (7, 8):
        b = getattr(u1, f"B{c}")
        d.add(elm.Line().at(b).right(0.25).color(DIM).label("nc", "right", fontsize=8, color=DIM))

    # ---- ESP32 DevKit, its GPIO pins level with A1-A6, so the six wires are straight
    esp = ic([pin("VIN", "top", "VIN"), pin("3V3", "top", "V3")]
             + [pin(f"GPIO{GPIO[c][0][1:]}", "right", f"G{c}") for c in range(N, 0, -1)]
             + [pin("GND", "bot", "GNDa"), pin("GND", "bot", "GNDb")],
             None, (u1.A1[0] - 5.0, u1.A1[1]), anchor="G1",
             pad={"R": (1.0, 1.2), "T": (2.4, 0.8), "B": (2.4, 0.8), "L": (1.0, 1.0)})
    d.add(elm.Label().at((esp.center[0] - 0.9, esp.center[1] + 0.2)).label("ESP32\nDevKit\n30-pin", fontsize=11))
    d.add(elm.Label().at((esp.center[0] - 0.9, esp.center[1] - 1.3)).label("U2 + U3", fontsize=9, color=DIM))
    for c in range(1, N + 1):
        d.add(elm.Line().at(getattr(esp, f"G{c}")).to(getattr(u1, f"A{c}")).color(SIG))
    vdd(esp.VIN, dy=0.6)
    vdd(esp.V3, name="+3V3", dy=0.6)
    gnd(esp.GNDa)
    gnd(esp.GNDb)

    # ---- power input, left: J1 and J2 in parallel -> F1 -> +5V, with C1, C3; C2 on +3V3
    px, py = esp.center[0] - 17.0, esp.center[1] + 2.2
    d.add(elm.Label().at((px - 1.0, py + 2.4)).label("5 V IN, one source at a time", loc="right", color=DIM))
    j1 = ic([pin("−", "right", "n"), pin("+", "right", "p")], (1.6, 1.6), (px, py))
    j2 = ic([pin("−", "right", "n"), pin("+", "right", "p")], (1.6, 1.6), (px, py - 3.2))
    d.add(elm.Label().at((j1.center[0] - 1.7, j1.center[1])).label("J1\nDC jack", loc="left", fontsize=10))
    d.add(elm.Label().at((j2.center[0] - 1.7, j2.center[1])).label("J2\nscrew", loc="left", fontsize=10))
    for j in (j1, j2):
        gnd(j.n, dx=0.8, dy=0.0)
    node_x = j1.p[0] + 1.8
    d.add(elm.Line().at(j1.p).to((node_x, j1.p[1])).color(PWR))
    d.add(elm.Line().at(j2.p).to((node_x, j2.p[1])).color(PWR))
    d.add(elm.Line().at((node_x, j2.p[1])).to((node_x, j1.p[1])).color(PWR))
    d.add(elm.Dot().at((node_x, j1.p[1])).color(PWR))
    d.add(elm.Line().at((node_x, j1.p[1])).right(0.8).color(PWR))
    d.add(elm.Fuse().right().color(PWR).label("F1  7.5 A max", "top", fontsize=10)
          .label("VIN_RAW → +5V", "bottom", fontsize=9, color=DIM))
    rail = d.add(elm.Line().right(4.6).color(PWR))
    d.add(elm.Vdd().color(PWR).label("+5V", fontsize=10))
    for dx, polar, label in ((1.0, True, "C1  1000 µF"), (3.4, False, "C3  100 nF")):
        x, y = rail.start[0] + dx, rail.start[1]
        d.add(elm.Dot().at((x, y)).color(PWR))
        d.add(elm.Capacitor(polar=polar).at((x, y)).down().label(label, "bottom", fontsize=10))
        d.add(elm.Ground().color(GND_C))
    c2x, c2y = rail.start[0] + 2.2, rail.start[1] - 5.6
    d.add(elm.Vdd().at((c2x, c2y)).color(PWR).label("+3V3", fontsize=10))
    d.add(elm.Capacitor(polar=True).at((c2x, c2y)).down().label("C2  1000 µF", "bottom", fontsize=10))
    d.add(elm.Ground().color(GND_C))

    # ---- six outputs, fanned out from B1-B6 without crossing
    x0 = u1.B1[0] + 3.2
    pc = (u1.B1[1] + u1.B6[1]) / 2
    pitch = 3.0
    for c in range(1, N + 1):
        b = getattr(u1, f"B{c}")
        y = pc + (N / 2 + 0.5 - c) * pitch
        k = 1.3 + 0.45 * min(c - 1, N - c)            # later turns in the middle: no crossings
        kx = b[0] + k
        for a, z in (((b[0], b[1]), (kx, b[1])), ((kx, b[1]), (kx, y)), ((kx, y), (x0, y))):
            d.add(elm.Line().at(a).to(z).color(OUT_C))
        d.add(elm.Resistor().at((x0, y)).right().color(OUT_C).label(f"R{c}  100 Ω", "bottom", fontsize=9))
        j = ic([pin("−", "left", "n"), pin("D", "left", "dd"), pin("+", "left", "p")],
               (1.4, 2.4), (x0 + 4.6, y), anchor="dd")
        d.add(elm.Label().at((j.center[0] + 1.0, j.center[1])).label(
            f"J{10 + c}  CH{c}\nGPIO{GPIO[c][0][1:]}", loc="right", fontsize=10))
        d.add(elm.Line().at((x0 + 3.0, y)).to(j.dd).color(OUT_C))
        d.add(elm.Fuse().at(j.p).left().color(PWR).label(f"F{10 + c}  3 A PTC", "top", fontsize=9))
        d.add(elm.Label().label("+5V", loc="left", fontsize=9, color=PWR))
        gnd(j.n, dx=-0.6, dy=0.0)

    d.add(elm.Label().at((px - 3.0, u1.GND[1] - 2.6)).label(
        "wled-controller rev 2.0 'wall'   ·   terminals: + D −   ·   a short on one channel trips only its PTC",
        loc="right", fontsize=10, color=DIM))
    OUT.parent.mkdir(exist_ok=True)
    d.save(str(OUT) + ".svg", transparent=False)
    d.save(str(OUT) + ".png", transparent=False, dpi=170)
    print(f"{OUT.relative_to(HERE.parent)}.svg/.png")


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else draw())
