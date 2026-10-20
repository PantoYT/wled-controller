"""Generate the unrouted wled-controller rev 2.0 board (KiCad 10).

Run with KiCad's bundled Python, once per board size:
    "C:/Program Files/KiCad/10.0/bin/python.exe" gen_board.py --size 120   # 120 x 74.16, golden
    "C:/Program Files/KiCad/10.0/bin/python.exe" gen_board.py --size 100   # 100 x 100, cheapest fab

Eight independent outputs from one ESP32 DevKit through a 74HCT245. Every output is a
self-contained strip at the board edge: screw terminal at the edge, a JST-XH socket behind
it, then its own polyfuse and series resistor. The channels run down the right edge, then
along the bottom edge from right to left (4 + 4 on the 120 mm board, 6 + 2 on the 100 mm one).
Inputs (DC jack, screw terminal) and the main fuse sit above the ESP32, outside its outline.

Places footprints, assigns nets, draws the outline, silkscreen, GND pours and the antenna
keepout. route.py lays the tracks. Re-running overwrites the .kicad_pcb.
"""
import argparse
import json
import math
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FP_ROOT = os.environ.get(
    "KICAD10_FOOTPRINT_DIR", "C:/Program Files/KiCad/10.0/share/kicad/footprints"
)
PROJECT_LIBS = {"wled": os.path.join(ROOT, "footprints")}

PHI = (1 + math.sqrt(5)) / 2
ap = argparse.ArgumentParser()
ap.add_argument("--size", choices=("120", "100", "phi", "phi4", "wall"), default="120")
ap.add_argument("--art", help="back-silkscreen art from art/make_art.py (silk-runs.json); "
                              "the board is then saved as wled-controller-v2-<size>-art")
ARGS = ap.parse_args()
SIZE = ARGS.size
NAME = f"wled-controller-v2-{SIZE}" + ("-art" if ARGS.art else "")

# Everything that differs between the boards. Cell centres: y on the right edge, x on the
# bottom edge. The ESP32 sits so its antenna end overhangs an edge by about 3.5 mm: the bottom
# edge on the vertical boards, the right edge on "phi", where it lies on its side.
LAYOUTS = {
    "120": dict(W=120.0, H=round(120.0 / PHI, 2), esp_top=31.75,
                right=[6.5 + 12.0 * k for k in range(4)], bottom=[89.5 - 12.0 * k for k in range(4)],
                # U1 turned 90: its input row faces the ESP32, so the GND pin at the row's far
                # end is not closed in by the incoming tracks (at 270 it was, on both layers).
                u1=(57.15, 31.75), u1_rot=90, u1_label_dy=3.8, c3=(53.0, 31.75, 90),
                holes=[(3.81, 70.35), (44.0, 70.35), (92.0, 12.5)],
                logo=(74.0, 6.0), legend=(108.0, 52.0), one_source_y=50.8),
    "100": dict(W=100.0, H=100.0, esp_top=57.15,
                right=[6.5 + 12.0 * k for k in range(6)], bottom=[69.5, 57.5],
                u1=(68.58, 34.29), c3=(69.08, 30.0, 180),
                holes=[(3.81, 96.19), (44.0, 96.19), (3.81, 20.0), (68.0, 14.5)],
                logo=(60.0, 22.0), legend=(88.0, 80.0), one_source_y=38.0),
    # 100 x 61.8 (rev 1.0's size): six channels along the bottom, numbered right to left,
    # inputs top left, the ESP32 on its side top right with USB-C facing left.
    "phi": dict(W=100.0, H=61.8, esp="h", esp_x0=57.15, esp_row=6.35,
                gpio=["D4", "D18", "D19", "D21", "D22", "D23"],
                right=[], bottom=[66.5 - 12.0 * k for k in range(6)],
                u1=(41.91, 22.86), c3=(46.41, 24.13, 270), c1=(4.0, 22.0), c2=(77.5, 38.8, 0),
                holes=[(3.81, 31.0), (96.5, 39.0), (76.0, 58.0)],
                logo=(91.0, 45.5), logo_split=True, legend=(90.0, 53.8), u1_label_dy=-3.2,
                one_source=(14.6, 22.0, 90)),
    # phi4: the wall board. Four channels (desk, ASUS, TV, spare), no DC jack and no JST-XH
    # sockets (strips plug in through JST SM pigtails into the screw terminals), 4 A polyfuses,
    # two status LEDs per channel, and the left and right edges kept free for the case's rails.
    "phi4": dict(W=100.0, H=61.8, esp="h", esp_x0=57.15, esp_row=6.35,
                 gpio=["D4", "D18", "D19", "D21"], names=["DESK", "ASUS", "TV", "AUX"],
                 right=[], bottom=[62.23, 45.72, 29.21, 12.70], cell="status", jack=False,
                 u1=(41.91, 22.86), c3=(46.41, 24.13, 270), c1=(38.1, 6.35), c2=(77.5, 39.37, 0), c2_label=(80.0, 44.6),
                 holes=[(3.81, 24.13), (3.5, 56.5), (96.52, 39.37), (73.66, 57.15)],
                 logo=(87.0, 47.0), u1_label_dy=-3.2),
    # wall: phi4's lessons with six channels again. The DC jack faces the top edge (the open
    # end of the wall mount) next to the screw input J2; no status LEDs, no gold, white silk;
    # numbered channels with a blank box under each number to write on.
    "wall": dict(W=100.0, H=61.8, esp="h", esp_x0=57.15, esp_row=6.35,
                 gpio=["D4", "D18", "D19", "D21", "D22", "D23"],
                 right=[], bottom=[70.58 - 12.0 * k for k in range(6)], cell="wall",
                 jack_at=(9.0, 14.0, 270), j2_x=22.86, f1_x=29.85, c1=(7.62, 26.67),
                 u1=(41.91, 22.86), c3=(46.41, 24.13, 270), c2=(79.5, 39.37, 0), c2_label=(82.0, 44.6),
                 holes=[(3.5, 21.0), (3.5, 33.0), (96.52, 39.37), (96.52, 57.15)],
                 logo=(86.0, 47.6), u1_label_dy=-3.2, one_source=(22.5, 16.6, 0)),
}
L = LAYOUTS[SIZE]
W, H = L["W"], L["H"]
CORNER_R = 2.0
OX, OY = 100.0, 100.0

# ESP32 DevKit, 30 pins (DOIT V1 layout), USB-C towards the top edge. The antenna end
# overhangs the bottom edge by about 3.5 mm, as on rev 1.0.
ESP_ROW_SPACING = 25.4    # measure your board! some clones use 22.86
ESP_LEFT_X = 12.7
ESP_TOP_PIN_Y = L.get("esp_top", 0.0)
ESP_CX = ESP_LEFT_X + ESP_ROW_SPACING / 2
ESP_LEFT = ["3V3", "GND", "D15", "D2", "D4", "RX2", "TX2", "D5", "D18", "D19",
            "D21", "RX0", "TX0", "D22", "D23"]
ESP_RIGHT = ["VIN", "GND", "D13", "D12", "D14", "D27", "D26", "D25", "D33", "D32",
             "D35", "D34", "VN", "VP", "EN"]
# Channel -> GPIO. No boot-strapping pins (0, 2, 5, 12, 15), no input-only pins (34-39), and
# not 16/17 (PSRAM on WROVER modules). CH1 keeps rev 1.0's GPIO4; the rest come from the
# header row nearest the shifter, in order, so their tracks run to it without crossing.
CHANNEL_GPIO = L.get("gpio", ["D4", "D32", "D33", "D25", "D26", "D27", "D14", "D13"])
N = len(CHANNEL_GPIO)
ESP_H = L.get("esp") == "h"
if ESP_H:
    # On its side: right-hand header (VIN...) on top, left-hand (3V3...) below, pins running
    # from the USB end (left) to the antenna end (right).
    ESP_X0, ESP_ROW_Y = L["esp_x0"], L["esp_row"]
    ESP_CX, ESP_CY = ESP_X0 + 7 * 2.54, ESP_ROW_Y + ESP_ROW_SPACING / 2


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def g(n):
    return round(n * 1.27, 3)


board = pcbnew.BOARD()
nets = {}


def net(name):
    if name not in nets:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n
    return nets[name]


def place(ref, value, lib, fp_name, x, y, rot=0, pads=None, show_ref=False):
    """Place a footprint with its anchor (pad 1) at (x, y). pads: {pad_number: net_name}."""
    fp = pcbnew.FootprintLoad(os.path.join(PROJECT_LIBS.get(lib, FP_ROOT), lib + ".pretty"), fp_name)
    assert fp is not None, f"missing footprint {lib}:{fp_name}"
    fp.SetFPID(pcbnew.LIB_ID(lib, fp_name))
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.Value().SetVisible(False)
    fp.Reference().SetVisible(show_ref)
    board.Add(fp)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(pt(x, y))
    for pad in fp.Pads():
        if pads and pad.GetNumber() in pads:
            pad.SetNet(net(pads[pad.GetNumber()]))
    return fp


def text(s, x, y, size=1.0, rot=0, layer=pcbnew.F_SilkS, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    t.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def pad_labels(fp, labels, dx, dy, size=1.0):
    for pad in fp.Pads():
        n = pad.GetNumber()
        if n in labels:
            p = pad.GetPosition()
            text(labels[n], pcbnew.ToMM(p.x) - OX + dx, pcbnew.ToMM(p.y) - OY + dy, size)


def segment(layer, x0, y0, x1, y1, width):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pt(x0, y0))
    s.SetEnd(pt(x1, y1))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def arc(layer, cx, cy, sx, sy, angle, width):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetCenter(pt(cx, cy))
    s.SetStart(pt(sx, sy))
    s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T), True)
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def rect_zone(x0, y0, x1, y1, layer, net_name=None, rule_area=False):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetZoneName("ANTENNA_KEEPOUT")
    else:
        z.SetNet(net(net_name))
        z.SetMinThickness(mm(0.5))      # no copper slivers between parallel tracks
        z.SetLocalClearance(mm(0.4))
        # Thermal reliefs everywhere, ESP32 power pins included: rev 1.0's cold joints were
        # pads tied straight into wide copper.
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)   # no floating copper
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(z)


def outline():
    r = CORNER_R
    edges = [((r, 0), (W - r, 0)), ((W, r), (W, H - r)), ((W - r, H), (r, H)), ((0, H - r), (0, r))]
    for (xa, ya), (xb, yb) in edges:
        segment(pcbnew.Edge_Cuts, xa, ya, xb, yb, 0.1)
    for cx, cy, sx, sy in ((r, r, 0, r), (W - r, r, W - r, 0), (W - r, H - r, W, H - r), (r, H - r, r, H)):
        arc(pcbnew.Edge_Cuts, cx, cy, sx, sy, 90, 0.1)


# ================================================================ layout
outline()
board.GetDesignSettings().SetGridOrigin(pt(0, 0))

# ---------------------------------------------------------------- inputs and main fuse
# Top band, above the ESP32's USB end. Both inputs sit in parallel before F1; one at a time.
IN = "VIN_RAW"
JACK = L.get("jack", True)
JACK_X, JACK_Y = g(11.5), g(5)
if "jack_at" in L:
    # Turned 270: the plug goes in from the top edge.
    jx, jy, jr = L["jack_at"]
    place("J1", "PC-GK2.1", "wled", "DC_Jack_Ninigi_PC-GK2.1", jx, jy, rot=jr,
          pads={"1": IN, "2": "GND", "3": "GND"})
    text("DC", jx, jy + 2.6, 1.2)
    F1_X = L["f1_x"]
elif JACK:
    place("J1", "PC-GK2.1", "wled", "DC_Jack_Ninigi_PC-GK2.1", JACK_X, JACK_Y,
          pads={"1": IN, "2": "GND", "3": "GND"})
    text("5V IN", g(7), g(12), 1.2)
    F1_X = JACK_X + 1.6 + 1.27 + 3.33                 # holder courtyard 1.27 right of the jack
else:
    F1_X = 21.59                                       # right of the screw input J2
F1_Y = 3.0
# On the wall board the holder's drills are opened to 1.9 mm, so Keystone 3568 (TME) and XFCN
# XF-508P-B-B (LCSC, 0.12 mm closer pitch) both fit.
F1_LIB, F1_FP = (("wled", "Fuseholder_Blade_Mini_Keystone_3568_XFCN_XF-508P") if L.get("cell") == "wall"
                 else ("Fuse", "Fuseholder_Blade_Mini_Keystone_3568"))
f1 = place("F1", "Mini blade fuse, 7.5 A max", F1_LIB, F1_FP,
           F1_X, F1_Y, pads={"1": IN, "2": "+5V"})
text("F1  MAIN FUSE", F1_X + 4.96, F1_Y + 7.4, 0.9)
text("7.5 A MAX", F1_X + 4.96, F1_Y + 9.0, 0.8)  # 2.6 mm +5V tracks: ~6.5 A at 20 C rise, ~7.8 A at 30 C (IPC-2221, 1 oz outer)

# Screw input, wires from the top edge: after the fuse, or first in the row without a jack.
J2_X = L.get("j2_x") or (F1_X + 13.26 + 1.27 + 8.18 if JACK else 12.7)
j2 = place("J2", "Screw 2p IN", "TerminalBlock_Phoenix",
           "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", J2_X, JACK_Y, rot=180,
           pads={"1": "GND", "2": IN})
text("+", J2_X - 5.08, JACK_Y + 6.95, 1.4)
text("-", J2_X, JACK_Y + 6.95, 1.4)
if "jack_at" in L:
    OSX, OSY, OSR = L["one_source"]
    text("5V IN  ·  ONE SOURCE AT A TIME", OSX, OSY, 0.8, rot=OSR)
elif JACK:
    OSX, OSY, OSR = L.get("one_source", (g(3.5), L.get("one_source_y"), 90))
    text("ONE SOURCE AT A TIME", OSX, OSY, 0.8, rot=OSR)
else:
    text("5V IN", J2_X - 2.54, JACK_Y + 9.0, 1.2)

# Bulk capacitor on +5V, right after the fuse.
C1_X, C1_Y = L.get("c1", (J2_X + 3.08 + 1.27 + 2.79, 6.6))
place("C1", "1000uF 16V", "Capacitor_THT", "CP_Radial_D8.0mm_P5.00mm", C1_X, C1_Y,
      pads={"1": "+5V", "2": "GND"})

# ---------------------------------------------------------------- ESP32
xr = ESP_LEFT_X + ESP_ROW_SPACING
esp_nets = {"GND": "GND", "VIN": "+5V", "3V3": "+3V3"}
for ch, gpio in enumerate(CHANNEL_GPIO, 1):
    esp_nets[gpio] = f"IO_CH{ch}"
if ESP_H:
    rows = (("U2", ESP_X0, ESP_ROW_Y + ESP_ROW_SPACING, ESP_LEFT, (0, -2.8)),
            ("U3", ESP_X0, ESP_ROW_Y, ESP_RIGHT, (0, 2.8)))
else:
    rows = (("U2", ESP_LEFT_X, ESP_TOP_PIN_Y, ESP_LEFT, (2.8, 0)),
            ("U3", xr, ESP_TOP_PIN_Y, ESP_RIGHT, (-2.8, 0)))
for ref, x, y, names, (ldx, ldy) in rows:
    pads = {str(i + 1): esp_nets[n] for i, n in enumerate(names) if n in esp_nets}
    fp = place(ref, "ESP32 socket", "Connector_PinSocket_2.54mm",
               "PinSocket_1x15_P2.54mm_Vertical", x, y, rot=90 if ESP_H else 0, pads=pads)
    for pad in fp.Pads():
        q = pad.GetPosition()
        text(names[int(pad.GetNumber()) - 1], pcbnew.ToMM(q.x) - OX + ldx,
             pcbnew.ToMM(q.y) - OY + ldy, 0.8, rot=90 if ESP_H else 0)
if ESP_H:
    text("USB-C", ESP_X0 - 4.0, ESP_CY, 1.0, rot=90)
    text("ESP32 DevKit 30p", ESP_CX, ESP_CY, 1.2)
else:
    text("USB-C", ESP_CX, ESP_TOP_PIN_Y - 4.5, 1.0)
    text("ESP32 DevKit 30p", ESP_CX, ESP_TOP_PIN_Y + 13 * 1.27, 1.2)

# 3V3 bulk capacitor near the 3V3 pin, outside the module's outline (it is taller than the
# gap under the DevKit).
C2_X, C2_Y, C2_ROT = L.get("c2", (5.6, ESP_TOP_PIN_Y - 0.6, 270))
place("C2", "1000uF 16V", "Capacitor_THT", "CP_Radial_D8.0mm_P5.00mm", C2_X, C2_Y,
      rot=C2_ROT, pads={"1": "+3V3", "2": "GND"})
if "c2_label" in L:
    text("3V3", *L["c2_label"], 0.9)
elif ESP_H:
    text("3V3", C2_X + 2.5, C2_Y + 5.6, 0.9)
else:
    text("3V3", 9.4, ESP_TOP_PIN_Y + 8.6, 0.9)

# ---------------------------------------------------------------- level shifter
# 74HCT245 turned 270 (default): pins 1-10 on the top row from right to left (DIR, A1-A8,
# GND), pins 11-20 on the bottom row from left to right (B8-B1, OE, VCC). A1 sits over B1, so
# channel n goes in at the top and out at the bottom of the same column. Turned 90 (the 120
# board) it is the same chip upside down: inputs on the bottom row, outputs on the top.
U1_X, U1_Y = L["u1"]
u1_pads = {"1": "+5V", "10": "GND", "19": "GND", "20": "+5V"}   # DIR high: A -> B; OE low
STATUS = L.get("cell") == "status"
for ch in range(1, 9):
    if ch <= N:
        u1_pads[str(1 + ch)] = f"IO_CH{ch}"     # A1-A8 = pins 2-9
        u1_pads[str(19 - ch)] = f"OUT{ch}_RAW"  # B1-B8 = pins 18-11
    elif STATUS and ch <= 2 * N:
        # The spare buffers copy each channel's data to its DATA LED, so the LED never
        # loads the strip's own output.
        u1_pads[str(1 + ch)] = f"IO_CH{ch - N}"
        u1_pads[str(19 - ch)] = f"ACT{ch - N}"
    else:
        u1_pads[str(1 + ch)] = "GND"            # unused inputs must not float; outputs open
u1 = place("U1", "74HCT245", "Package_DIP", "DIP-20_W7.62mm_Socket", U1_X, U1_Y, rot=L.get("u1_rot", 270),
           pads=u1_pads)                   # the "74HCT245" label names it
text("74HCT245 / 74AHCT245", U1_X + (11.43 if L.get("u1_rot", 270) == 90 else -11.43),
     U1_Y + L.get("u1_label_dy", 11.4), 0.9)
C3_X, C3_Y, C3_ROT = L["c3"]
place("C3", "100nF", "Capacitor_THT", "C_Disc_D5.0mm_W2.5mm_P5.00mm", C3_X, C3_Y,
      rot=C3_ROT, pads={"1": "+5V", "2": "GND"})

# ---------------------------------------------------------------- outputs
# One strip per channel. Right edge: turned 90 so the pins run down the edge and the screw
# terminal's wire entry faces right. Bottom edge: unturned, entry facing down. From the edge
# inwards: terminal (+ D -), JST-XH (+ D -), polyfuse (+5V -> V_CHn), resistor (OUT -> DATA).
TB = "TerminalBlock_Phoenix_PT-1,5-3-3.5-H_1x03_P3.50mm_Horizontal"
XH = "JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"
PTC = "Fuse_Bourns_MF-RG300"
RV = "R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical"
CELL = 12.0
EDGE = 0.3


def channel(ch, side, c):
    """side 'R': c = centre y on the right edge. side 'B': c = centre x on the bottom edge."""
    v, d, raw = f"V_CH{ch}", f"DATA{ch}", f"OUT{ch}_RAW"
    pins3 = {"1": v, "2": d, "3": "GND"}
    if side == "R":
        # Rotation 90 maps a footprint's (x, y) to (X + y, Y - x).
        tx = W - EDGE - 5.04
        place(f"J{10 + ch}", f"Screw CH{ch}", "TerminalBlock_Phoenix", TB, tx, c + 3.5, rot=90, pads=pins3)
        xh_x = tx - 3.65 - 0.5 - 3.94
        place(f"J{20 + ch}", f"JST-XH CH{ch}", "Connector_JST", XH, xh_x, c + 2.5, rot=90, pads=pins3)
        ptc_x = xh_x - 2.9 - 0.5 - 2.4
        place(f"F{10 + ch}", "MF-RG300 3A", "Fuse", PTC, ptc_x, c + 2.55, rot=90,
              pads={"1": "+5V", "2": v})
        r_x = ptc_x - 1.2 - 0.5 - 1.54
        place(f"R{ch}", "100R", "Resistor_THT", RV, r_x, c + 1.27, rot=90, pads={"1": raw, "2": d})
        text(f"{ch}", r_x - 4.8, c, 1.8, bold=True)
        text(f"IO{CHANNEL_GPIO[ch - 1][1:]}", r_x - 2.7, c, 0.8, rot=90)
    else:
        ty = H - EDGE - 5.04
        place(f"J{10 + ch}", f"Screw CH{ch}", "TerminalBlock_Phoenix", TB, c - 3.5, ty, pads=pins3)
        xh_y = ty - 3.65 - 0.5 - 3.94
        place(f"J{20 + ch}", f"JST-XH CH{ch}", "Connector_JST", XH, c - 2.5, xh_y, pads=pins3)
        ptc_y = xh_y - 2.9 - 0.5 - 2.4
        place(f"F{10 + ch}", "MF-RG300 3A", "Fuse", PTC, c - 2.55, ptc_y, pads={"1": "+5V", "2": v})
        r_y = ptc_y - 1.2 - 0.5 - 1.54
        place(f"R{ch}", "100R", "Resistor_THT", RV, c - 1.27, r_y, pads={"1": raw, "2": d})
        text(f"{ch}", c, r_y - 5.0, 1.8, bold=True)
        text(f"IO{CHANNEL_GPIO[ch - 1][1:]}", c, r_y - 2.6, 0.8)


def channel_status(ch, c):
    """phi4 cell, centre x = c, from the bottom edge up: XY302R terminal (+ D -), 4 A polyfuse,
    the 100R data resistor and the PWR LED's resistor, then the DATA LED (yellow, left) and the
    PWR LED (green, right) with the channel number between them. PWR is lit while the
    channel's polyfuse passes current; DATA glows while WLED sends frames on that channel."""
    v, d, raw = f"V_CH{ch}", f"DATA{ch}", f"OUT{ch}_RAW"
    ty = 52.07                                  # pins; the body's wire entry is 8.5 mm further
    place(f"J{10 + ch}", f"Screw CH{ch}", "wled", "TerminalBlock_Xinya_XY302R-3_P3.50mm_Horizontal",
          c - 3.5, ty, pads={"1": v, "2": d, "3": "GND"})
    place(f"F{10 + ch}", "RG400-16 4A", "Fuse", "Fuse_Bourns_MF-RG400", c - 2.55, 47.625,
          pads={"1": "+5V", "2": v})
    place(f"R{ch}", "100R", "Resistor_THT", RV, c - 5.08, 44.45, pads={"1": raw, "2": d})
    place(f"R{20 + ch}", "10k", "Resistor_THT", RV, c + 2.54, 44.45, pads={"1": v, "2": f"PLED{ch}"})
    place(f"D{10 + ch}", "LED 3mm yellow (DATA)", "LED_THT", "LED_D3.0mm", c - 5.08, 40.64,
          pads={"1": "GND", "2": f"LEDA{ch}"})
    place(f"D{20 + ch}", "LED 3mm green (PWR)", "LED_THT", "LED_D3.0mm", c + 2.54, 40.64,
          pads={"1": "GND", "2": f"PLED{ch}"})
    # DATA LED resistors sit in a row under the shifter's B5-B8 outputs.
    place(f"R{30 + ch}", "470R", "Resistor_THT", RV, 26.67 - 6.35 * (ch - 1), 34.29,
          pads={"1": f"ACT{ch}", "2": f"LEDA{ch}"})
    text(f"{ch}", c, 40.64, 1.8, bold=True)
    text(L["names"][ch - 1], c, 37.4, 0.9)


def channel_wall(ch, c):
    """wall cell, centre x = c, from the bottom edge up: screw terminal (+ D -), 3 A polyfuse,
    100R, the channel number and an empty box to write the strip's name in.

    The terminal footprint takes either XY302R (TME) or KF350 (LCSC). XY302R's wire entry ends
    flush with the bottom edge; KF350 reaches 3.4 mm behind its pins, so the polyfuse row sits
    far enough back for it. The polyfuse is RG300-16 (TME) or FRG300-16F (LCSC), same size."""
    v, d, raw = f"V_CH{ch}", f"DATA{ch}", f"OUT{ch}_RAW"
    place(f"J{10 + ch}", f"Screw CH{ch}", "wled", "TerminalBlock_3P_P3.50mm_XY302R_KF350",
          c - 3.5, 52.07, pads={"1": v, "2": d, "3": "GND"})
    place(f"F{10 + ch}", "RG300-16 / FRG300-16F 3A", "Fuse", PTC, c - 2.55, 46.0375, pads={"1": "+5V", "2": v})
    place(f"R{ch}", "100R", "Resistor_THT", RV, c - 1.27, 42.8625, pads={"1": raw, "2": d})
    text(f"{ch}", c, 39.4, 1.8, bold=True)
    text(f"IO{CHANNEL_GPIO[ch - 1][1:]}", c, 34.5, 0.8)
    for x0, y0, x1, y1 in ((c - 4.8, 35.6, c + 4.8, 35.6), (c + 4.8, 35.6, c + 4.8, 37.6),
                           (c + 4.8, 37.6, c - 4.8, 37.6), (c - 4.8, 37.6, c - 4.8, 35.6)):
        segment(pcbnew.F_SilkS, x0, y0, x1, y1, 0.15)


n_right = len(L["right"])
for k, c in enumerate(L["right"]):
    channel(1 + k, "R", c)
for k, c in enumerate(L["bottom"]):
    if STATUS:
        channel_status(1 + n_right + k, c)
    elif L.get("cell") == "wall":
        channel_wall(1 + n_right + k, c)
    else:
        channel(1 + n_right + k, "B", c)
# Pin order legend in the free bottom-right corner (phi4: under the logo, see branding).
LX, LY = L.get("legend", (0, 0))
if STATUS or L.get("cell") == "wall":
    pass
elif n_right:
    text(f"CH1-{n_right}  TOP TO BOTTOM  - D +", LX, LY, 0.8)
    text(f"CH{n_right + 1}-{N}  LEFT TO RIGHT  + D -", LX, LY + 2.0, 0.8)
else:
    text(f"CH1-{N} RIGHT TO LEFT", LX, LY, 0.8)
    text("PINS LEFT TO RIGHT  + D -", LX, LY + 2.0, 0.8)
if not STATUS and L.get("cell") != "wall":
    text("PTC 3A PER CHANNEL", LX, LY + 5.0, 0.8)

# ---------------------------------------------------------------- mounting holes
# No hole in the top-left corner: the DC jack owns it.
for i, (x, y) in enumerate(L["holes"]):
    place(f"H{i + 1}", "M3", "MountingHole", "MountingHole_3.2mm_M3", x, y)

# ---------------------------------------------------------------- 3D extras
def model(fp, path, offset=(0, 0, 0), rot=(0, 0, 0)):
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = path
    m.m_Offset = pcbnew.VECTOR3D(*offset)   # mm; y points up, away from the PCB's y
    m.m_Rotation = pcbnew.VECTOR3D(*rot)
    fp.Models().push_back(m)


KICAD_3D = "${KICAD10_3DMODEL_DIR}"
BOX = "${KIPRJMOD}/../3d/"
model(u1, KICAD_3D + "/Package_DIP.3dshapes/DIP-20_W7.62mm.step", (0, 0, 3.0))
model(f1, BOX + "fuse_mini.step", (4.96, -1.7, 4.0))

SOCKET_H, SPACER_H, KIT_PCB = 8.5, 2.5, 1.6     # one header, the DevKit's own pin plastic
kit_z = SOCKET_H + SPACER_H
kit_cy = (ESP_X0 if ESP_H else ESP_TOP_PIN_Y) - 6.0 + 26.0   # along the module's length
kit = pcbnew.FOOTPRINT(board)
kit.SetReference("ESP1")
kit.SetValue("ESP32 DevKit (3D only)")
kit.Reference().SetVisible(False)
kit.Value().SetVisible(False)
kit.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
board.Add(kit)
if ESP_H:
    kit.SetPosition(pt(kit_cy, ESP_CY))
    kit.SetOrientationDegrees(90)                # USB end to the left
    rows_dy = (ESP_X0 + 7 * 2.54) - kit_cy
else:
    kit.SetPosition(pt(ESP_CX, kit_cy))
    rows_dy = (ESP_TOP_PIN_Y + 7 * 2.54) - kit_cy
for dx in (-ESP_ROW_SPACING / 2, ESP_ROW_SPACING / 2):
    model(kit, BOX + "header_spacer.step", (dx, -rows_dy, SOCKET_H))
model(kit, BOX + "devkit_pcb.step", (0, 0, kit_z))
top = kit_z + KIT_PCB
model(kit, KICAD_3D + "/RF_Module.3dshapes/ESP32-WROOM-32.step", (0, -(26.0 - 15.74), top), (0, 0, 180))
model(kit, BOX + "usb_c.step", (0, 26.0 - 7.35 / 2 + 1.0, top))
for dx in (-9.5, 9.5):
    model(kit, BOX + "button.step", (dx, 21.0, top))
    model(kit, BOX + "button_cap.step", (dx, 21.0, top + 3.5))
model(kit, BOX + "ch340.step", (0, 11.0, top))
model(kit, BOX + "ldo.step", (-8.0, 13.0, top))
model(kit, BOX + "led.step", (8.0, 13.0, top))

# ---------------------------------------------------------------- pours & keepout
rect_zone(0.3, 0.3, W - 0.3, H - 0.3, pcbnew.B_Cu, "GND")
rect_zone(0.3, 0.3, W - 0.3, H - 0.3, pcbnew.F_Cu, "GND")
if ESP_H:
    antenna_x = ESP_X0 + 14 * 2.54 + 2.5
    rect_zone(antenna_x, max(0.3, ESP_CY - 15), W - 0.3, ESP_CY + 15, pcbnew.F_Cu, rule_area=True)
else:
    antenna_top = ESP_TOP_PIN_Y + 14 * 2.54 + 2.5
    rect_zone(ESP_CX - 15, antenna_top, ESP_CX + 15, H - 0.3, pcbnew.F_Cu, rule_area=True)

# ---------------------------------------------------------------- branding
def gold(item):
    """Copy a copper item onto F.Mask, so it comes out as bare ENIG gold on the black mask."""
    m = item.Duplicate()
    m.SetLayer(pcbnew.F_Mask)
    board.Add(m)


if STATUS:
    # Logo in bare gold, and a row of gold "pixels" whose size peaks like the desk's fill-in wave.
    LGX, LGY = L["logo"]
    t = pcbnew.PCB_TEXT(board)
    t.SetText("panto")
    t.SetPosition(pt(LGX, LGY))
    t.SetLayer(pcbnew.F_Cu)
    t.SetTextSize(pcbnew.VECTOR2I(mm(3.4), mm(3.4)))
    t.SetTextThickness(mm(0.7))
    board.Add(t)
    gold(t)
    text("WLED CONTROLLER", LGX, LGY + 3.9, 0.9)
    text(f"REV 2.0  ·  {N} CH  ·  5 V", LGX, LGY + 5.7, 0.9)
    text("LEDS  L DATA  ·  R POWER", LGX, LGY + 8.2, 0.8)
    text("PINS  + D -  ·  PTC 4 A", LGX, LGY + 9.8, 0.8)
    for k in range(15):
        s = 0.35 + 0.75 * math.exp(-((k - 7) / 3.2) ** 2)
        x = LGX - 8.4 + 1.2 * k
        sq = pcbnew.PCB_SHAPE(board)
        sq.SetShape(pcbnew.SHAPE_T_RECT)
        sq.SetStart(pt(x - s / 2, 59.4 - s / 2))
        sq.SetEnd(pt(x + s / 2, 59.4 + s / 2))
        sq.SetFilled(True)
        sq.SetWidth(0)
        sq.SetLayer(pcbnew.F_Cu)
        board.Add(sq)
        gold(sq)
elif L.get("cell") == "wall":
    LGX, LGY = L["logo"]
    text("panto", LGX, LGY, 3.2, bold=True)
    text("WLED CONTROLLER", LGX, LGY + 3.8, 0.9)
    text(f"REV 2.0  ·  {N} CH", LGX, LGY + 5.6, 0.9)
    text("PINS  + D -", LGX, LGY + 7.9, 0.8)
    text("PTC 3 A PER CHANNEL", LGX, LGY + 9.5, 0.8)
else:
    text("panto", L["logo"][0], L["logo"][1], 3.2, bold=True)
if STATUS or L.get("cell") == "wall":
    pass
elif L.get("logo_split"):
    text("WLED CONTROLLER", L["logo"][0], L["logo"][1] + 3.8, 0.9)
    text(f"REV 2.0  ·  {N} CH", L["logo"][0], L["logo"][1] + 5.6, 0.9)
else:
    text(f"WLED CONTROLLER  ·  REV 2.0  ·  {N} CH", L["logo"][0], L["logo"][1] + 3.8, 0.9)
# Back: name and the channel -> GPIO table between the header rows (no pads there).
ART_X, ART_Y = (ESP_CX, ESP_CY - 9.0) if ESP_H else (ESP_CX, ESP_TOP_PIN_Y + 7 * 2.54 - 2.0)
if not ARGS.art:
    text("panto", ART_X, ART_Y, 2.2, layer=pcbnew.B_SilkS, bold=True)
    text("panto-dev.com", ART_X, ART_Y + 2.8, 0.9, layer=pcbnew.B_SilkS)
for ch, gpio in (() if ARGS.art else enumerate(CHANNEL_GPIO, 1)):
    name = ("  " + L["names"][ch - 1]) if "names" in L else ""
    text(f"CH{ch}  GPIO{gpio[1:]}{name}", ART_X, ART_Y + 4.8 + 1.5 * ch, 0.9, layer=pcbnew.B_SilkS)

# ---------------------------------------------------------------- back art
# art/silk-runs.json (made by art/make_art.py) on the back silkscreen, mirrored so it reads
# right from behind, cut away pixel by pixel round every pad and hole, the board edge and any
# back text, then merged into rectangles (a run grows downwards while the next row repeats it).
if ARGS.art:
    with open(ARGS.art, encoding="utf-8") as f:
        art = json.load(f)
    P, nx, ny = art["pixel"], art["nx"], art["ny"]
    keep = [(fp_pad.GetBoundingBox(), 0.35) for fp in board.GetFootprints() for fp_pad in fp.Pads()]
    keep += [(d.GetBoundingBox(), 0.5) for d in board.GetDrawings()
             if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.B_SilkS]
    boxes = [(pcbnew.ToMM(bb.GetLeft()) - OX - m, pcbnew.ToMM(bb.GetTop()) - OY - m,
              pcbnew.ToMM(bb.GetRight()) - OX + m, pcbnew.ToMM(bb.GetBottom()) - OY + m) for bb, m in keep]
    open_runs, rects = {}, []
    for j in range(ny + 1):
        runs = set()
        if j < ny:
            y0, y1 = j * P, (j + 1) * P
            cuts = [(int(bx0 / P), int(math.ceil(bx1 / P))) for bx0, by0, bx1, by1 in boxes
                    if y0 < by1 and y1 > by0]
            if y0 < 0.6 or y1 > H - 0.6:
                cuts.append((0, nx))
            cuts += [(0, int(math.ceil(0.6 / P))), (int((W - 0.6) / P), nx)]
            for a0, a1 in art["rows"][j]:
                m0, m1 = nx - a1, nx - a0              # mirror for the back
                segs = [(m0, m1)]
                for c0, c1 in cuts:
                    segs = [s for s0, s1 in segs for s in ((s0, min(s1, c0)), (max(s0, c1), s1)) if s[1] > s[0]]
                runs.update(segs)
        for r in list(open_runs):
            if r not in runs:
                rects.append((r[0], open_runs.pop(r), r[1], j))
        for r in runs:
            open_runs.setdefault(r, j)
    for x0, y0, x1, y1 in rects:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_RECT)
        s.SetStart(pt(x0 * P, y0 * P))
        s.SetEnd(pt(x1 * P, y1 * P))
        s.SetFilled(True)
        s.SetWidth(0)
        s.SetLayer(pcbnew.B_SilkS)
        board.Add(s)
    print(f"back art: {len(rects)} rectangles")

out = os.path.join(HERE, NAME + ".kicad_pcb")
pcbnew.SaveBoard(out, board)

STACKUP = [
    '(layer "F.SilkS" (type "Top Silk Screen") (color "White"))',
    '(layer "F.Paste" (type "Top Solder Paste"))',
    '(layer "F.Mask" (type "Top Solder Mask") (color "#0A0A0CF0") (thickness 0.01))',
    '(layer "F.Cu" (type "copper") (thickness 0.035))',
    '(layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))',
    '(layer "B.Cu" (type "copper") (thickness 0.035))',
    '(layer "B.Mask" (type "Bottom Solder Mask") (color "#0A0A0CF0") (thickness 0.01))',
    '(layer "B.Paste" (type "Bottom Solder Paste"))',
    '(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))',
    '(copper_finish "ENIG")',
    '(dielectric_constraints no)',
]
stackup = "\t\t(stackup\n" + "".join(f"\t\t\t{line}\n" for line in STACKUP) + "\t\t)\n"
with open(out, encoding="utf-8") as f:
    pcb_text = f.read()
with open(out, "w", encoding="utf-8") as f:
    f.write(pcb_text.replace("\t(setup\n", "\t(setup\n" + stackup, 1))

pro = os.path.join(HERE, NAME + ".kicad_pro")
POWER_NETS = ["VIN_RAW", "+5V", "+3V3"] + [f"V_CH{c}" for c in range(1, N + 1)]
project = {
    "board": {"design_settings": {"rules": {
        "min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6,
        "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.5}}},
    "net_settings": {
        "classes": [
            {"name": "Default", "clearance": 0.2, "track_width": 0.4,
             "via_diameter": 0.8, "via_drill": 0.4, "priority": 2147483647},
            {"name": "Power", "clearance": 0.3, "track_width": 1.5,
             "via_diameter": 1.2, "via_drill": 0.6, "priority": 0},
        ],
        "netclass_patterns": [{"netclass": "Power", "pattern": p} for p in POWER_NETS],
    },
    "meta": {"filename": NAME + ".kicad_pro", "version": 3},
}
with open(pro, "w", encoding="utf-8") as f:
    json.dump(project, f, indent=2)
print("wrote", out)
