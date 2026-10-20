"""Generate the unrouted WLED ESP32 controller board (KiCad 10).

Run with KiCad's bundled Python:
    "C:/Program Files/KiCad/10.0/bin/python.exe" gen_board.py [--gear PATH.png]

Places every footprint, assigns nets (ratsnest), draws the outline,
silkscreen labels, GND pours, the antenna keepout and a pixel-art gear
outline on the back silkscreen. Tracks are left for the human to route.
Re-running overwrites the .kicad_pcb, so do not re-run after you start routing.
"""
import argparse
import json
import math
import os

import pcbnew
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "wled-controller"
FP_ROOT = os.environ.get(
    "KICAD10_FOOTPRINT_DIR", "C:/Program Files/KiCad/10.0/share/kicad/footprints"
)

W = 100.0
H = round(W / ((1 + math.sqrt(5)) / 2), 2)   # golden rectangle: 100 x 61.8 mm
CORNER_R = 2.0
OX, OY = 100.0, 100.0                          # board origin on the sheet

# ESP32 DevKit, 30 pins (DOIT V1 layout), turned so USB-C faces the top edge.
ESP_ROW_SPACING = 25.4    # measure your board! some clones use 22.86
ESP_LEFT_X = 12.7       # 10 x 1.27
ESP_TOP_PIN_Y = 19.05    # 15 x 1.27; pin nearest the USB end (measure: ~6 mm from the USB edge)
ESP_CX = ESP_LEFT_X + ESP_ROW_SPACING / 2
# Seen from the top with USB-C up, top to bottom:
ESP_LEFT = ["3V3", "GND", "D15", "D2", "D4", "RX2", "TX2", "D5", "D18", "D19",
            "D21", "RX0", "TX0", "D22", "D23"]
ESP_RIGHT = ["VIN", "GND", "D13", "D12", "D14", "D27", "D26", "D25", "D33", "D32",
             "D35", "D34", "VN", "VP", "EN"]


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


board = pcbnew.BOARD()
nets = {}


def net(name):
    if name not in nets:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n
    return nets[name]


PROJECT_LIBS = {"wled": os.path.join(os.path.dirname(HERE), "footprints")}   # footprints made for this board


def place(ref, value, lib, fp_name, x, y, rot=0, pads=None, show_ref=True):
    """Place footprint with pad 1 at (x, y). pads: {pad_number: net_name}."""
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
    """Put a silkscreen label next to each numbered pad."""
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
        z.SetMinThickness(mm(0.25))
        z.SetLocalClearance(mm(0.4))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
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


# ---------------------------------------------------------------- gear artwork
def grid_cell(im):
    """Size of one art pixel in image pixels (largest cell with uniform blocks)."""
    w = im.size[0]
    for c in range(w // 16, 1, -1):
        if w % c:
            continue
        if all(im.getpixel((bx, by)) == im.getpixel((bx + c - 1, by + c - 1)) == im.getpixel((bx + c // 2, by))
               for bx in range(0, w, c) for by in range(0, w, c)):
            return c
    return 1


def gear_outline(png, cx, cy, size, width=0.3, keep_clear=0.35):
    """Trace a pixel-art image into white outlines on the back silkscreen.

    Draws the silhouette, the square inner plate and the hub. Pieces that
    would land on a pad are dropped so the fab does not have to clip them.
    """
    im = Image.open(png).convert("RGB")
    bg = im.getpixel((0, 0))
    cell = grid_cell(im)
    n = im.size[0] // cell

    def px(x, y):
        return im.getpixel((x * cell + cell // 2, y * cell + cell // 2))

    def is_bg(c):
        return sum(abs(a - b) for a, b in zip(c, bg)) < 30

    # Silhouette = everything the outside background cannot reach (fills pinholes).
    outside, todo = set(), [(0, 0)]
    while todo:
        x, y = todo.pop()
        if (x, y) in outside or not (0 <= x < n and 0 <= y < n) or not is_bg(px(x, y)):
            continue
        outside.add((x, y))
        todo += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    solid = {(x, y) for y in range(n) for x in range(n)} - outside
    # Hub: bounding square of the grey/steel (low saturation) centre.
    grey = [(x, y) for (x, y) in solid if not is_bg(px(x, y)) and abs(px(x, y)[0] - px(x, y)[2]) < 25]
    hub = {(x, y) for x in range(min(g[0] for g in grey), max(g[0] for g in grey) + 1)
           for y in range(min(g[1] for g in grey), max(g[1] for g in grey) + 1)}
    xs = [x for x, _ in solid]
    ys = [y for _, y in solid]
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    span = max(x1 - x0, y1 - y0)
    inset = round(span * 0.29)
    plate = {(x, y) for x in range(x0 + inset, x1 - inset) for y in range(y0 + inset, y1 - inset)}

    k = size / span
    boxes = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            boxes.append((pcbnew.ToMM(bb.GetLeft()) - OX - keep_clear, pcbnew.ToMM(bb.GetTop()) - OY - keep_clear,
                          pcbnew.ToMM(bb.GetRight()) - OX + keep_clear, pcbnew.ToMM(bb.GetBottom()) - OY + keep_clear))

    def blocked(x, y):
        return any(a <= x <= c and b <= y <= d for a, b, c, d in boxes)

    def to_board(gx, gy):
        # Mirrored in X: the back side is read from behind.
        return cx - (gx - (x0 + x1) / 2) * k, cy + (gy - (y0 + y1) / 2) * k

    def edges(region):
        for (x, y) in region:
            if (x, y - 1) not in region:
                yield (x, y), (x + 1, y)
            if (x, y + 1) not in region:
                yield (x, y + 1), (x + 1, y + 1)
            if (x - 1, y) not in region:
                yield (x, y), (x, y + 1)
            if (x + 1, y) not in region:
                yield (x + 1, y), (x + 1, y + 1)

    step = 0.25
    count = 0
    for region in (solid, plate, hub):
        for a, b in edges(region):
            (sx, sy), (ex, ey) = to_board(*a), to_board(*b)
            pieces = max(1, int(math.hypot(ex - sx, ey - sy) / step))
            run = None
            for i in range(pieces + 1):
                t = i / pieces
                x, y = sx + (ex - sx) * t, sy + (ey - sy) * t
                if blocked(x, y):
                    if run and run[0] != run[1]:
                        segment(pcbnew.B_SilkS, *run[0], *run[1], width)
                        count += 1
                    run = None
                else:
                    run = ((x, y), (x, y)) if run is None else (run[0], (x, y))
            if run and run[0] != run[1]:
                segment(pcbnew.B_SilkS, *run[0], *run[1], width)
                count += 1
    return count


# ================================================================ layout
# Rows and columns line up pin-to-pin on a 1.27 mm grid measured from the board's
# top-left corner. Where parts sit side by side (top input row, right-hand screw
# column), their courtyards are spaced by the same GAP instead, so the plastic
# bodies look evenly spaced on the real board.
def g(n):
    return round(n * 1.27, 3)


GAP = 1.27
outline()
board.GetDesignSettings().SetGridOrigin(pt(0, 0))

# The top-left corner belongs to the DC jack, so there is no hole there.
for i, (x, y) in enumerate(((g(3), g(45)), (g(36), g(45)), (g(57), g(3)))):
    place(f"H{i + 1}", "M3", "MountingHole", "MountingHole_3.2mm_M3", x, y, show_ref=False)

# ---------------------------------------------------------------- power input (top edge)
# Every input sits in parallel BEFORE the fuse. Only one source at a time.
# Left to right: DC jack | pin header + solder pads over the fuse | screw terminal.
# Courtyard offsets (from each anchor) below come from the KiCad footprints.
IN = "VIN_RAW"
JACK_X, JACK_Y = g(11.5), g(5)
# Ninigi PC-GK2.1 (TME): its pin spacing differs from KiCad's generic barrel jack.
j1 = place("J1", "PC-GK2.1", "wled", "DC_Jack_Ninigi_PC-GK2.1", JACK_X, JACK_Y,
           pads={"1": IN, "2": "GND", "3": "GND"}, show_ref=False)
text("5V IN", g(7), g(12), 1.2)

COL2 = JACK_X + 1.6 + GAP                      # jack courtyard right edge + GAP
ROW_Y = g(2)
j4 = place("J4", "Pin IN", "Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical",
           COL2 + 1.82, ROW_Y, rot=90, pads={"1": IN, "2": "GND"}, show_ref=False)
J3_X = COL2 + 6.19 + GAP + 2.10
j3 = place("J3", "Solder IN", "Connector_Wire", "SolderWire-1sqmm_1x02_P5.4mm_D1.4mm_OD2.7mm",
           J3_X, ROW_Y, pads={"1": IN, "2": "GND"}, show_ref=False)
COL2_RIGHT = J3_X + 7.55
text("+", COL2 + 1.82, ROW_Y + 2.5, 0.8)          # under the pins, above the fuse
text("-", COL2 + 1.82 + 2.54, ROW_Y + 2.5, 0.8)
text("+", J3_X - 2.2, ROW_Y, 1.1)
text("-", J3_X + 5.4 + 2.2, ROW_Y, 1.1)
FUSE_X = (COL2 + COL2_RIGHT) / 2 - 4.955             # centred under the pin/solder pair
FUSE_Y = ROW_Y + 1.93 + GAP + 1.96
f1 = place("F1", "Fuse 3A (mini blade)", "Fuse", "Fuseholder_Blade_Mini_Keystone_3568",
           FUSE_X, FUSE_Y, pads={"1": IN, "2": "+5V"}, show_ref=False)
text("F1 3A", FUSE_X + 4.96, FUSE_Y + 6.5, 1.0)

# Wire entry faces the top edge; + is the left clamp, nearest the fuse.
J2_X = COL2_RIGHT + GAP + 8.18
j2 = place("J2", "Screw 2p IN", "TerminalBlock_Phoenix",
           "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", J2_X, JACK_Y, rot=180,
           pads={"1": "GND", "2": IN}, show_ref=False)
text("+", J2_X - 5.08, JACK_Y + 6.95, 1.4)
text("-", J2_X, JACK_Y + 6.95, 1.4)
text("ONE SOURCE AT A TIME", g(3.5), g(31), 0.8, rot=90)
text("PIN IN MAX 3A", g(5), g(31), 0.8, rot=90)

# ---------------------------------------------------------------- ESP32
# USB-C faces up; the module sits raised in female headers, and its antenna end
# overhangs the bottom edge a little (which the antenna likes).
xr = ESP_LEFT_X + ESP_ROW_SPACING
esp_nets = {"GND": "GND", "VIN": "+5V", "3V3": "+3V3", "D4": "ESP_D4"}
# Pin names go on the inside, under the module: visible while assembling, out of the way after.
for ref, x, names, side in (("U2", ESP_LEFT_X, ESP_LEFT, 2.8), ("U3", xr, ESP_RIGHT, -2.8)):
    pads = {str(i + 1): esp_nets[n] for i, n in enumerate(names) if n in esp_nets}
    fp = place(ref, "ESP32 socket", "Connector_PinSocket_2.54mm",
               "PinSocket_1x15_P2.54mm_Vertical", x, ESP_TOP_PIN_Y, pads=pads, show_ref=False)
    pad_labels(fp, {str(i + 1): n for i, n in enumerate(names)}, side, 0, 0.8)
text("USB-C", ESP_CX, g(13.5), 1.0)
text("ESP32 DevKit 30p", ESP_CX, g(32), 1.2)

# Both bulk capacitors: same orientation, same row, mirrored about the ESP32.
CAP_Y = g(18)
c2 = place("C2", "1000uF 16V", "Capacitor_THT", "CP_Radial_D8.0mm_P5.00mm", g(2), CAP_Y,
           pads={"1": "+3V3", "2": "GND"}, show_ref=False)
c1 = place("C1", "1000uF 16V", "Capacitor_THT", "CP_Radial_D8.0mm_P5.00mm", g(34), CAP_Y,
           pads={"1": "+5V", "2": "GND"}, show_ref=False)
text("3V3", g(2) + 2.5, g(22.5), 1.0)
text("5V", g(34) + 2.5, g(22.5), 1.0)

# ---------------------------------------------------------------- level shifter
# U1 lies flat; C3 sits right above pin 14 (+5V). The series resistors stand in one
# row under the chip: R2 under pin 3 and R3 under pin 6 take the bottom-row outputs
# straight down; R1 and R4 at the ends take pins 11 and 8, which come round the
# left and right ends of the chip. Nothing crosses through the chip.
U1_X, U1_Y = g(41), g(26)
u1 = place("U1", "74AHCT125", "Package_DIP", "DIP-14_W7.62mm_Socket", U1_X, U1_Y, rot=90, pads={
    "1": "GND",       # 1OE, active low
    "2": "ESP_D4",    # 1A
    "3": "DATA2_RAW",       # -> R2 -> screw D
    "4": "GND",       # 2OE
    "5": "ESP_D4",    # 2A
    "6": "DATA4_RAW",       # -> R3 -> solder D
    "7": "GND",
    "8": "DATA1_RAW",       # -> R4 -> MAIN JST
    "9": "ESP_D4",    # 3A
    "10": "GND",      # 3OE
    "11": "DATA3_RAW",      # -> R1 -> pin header D
    "12": "ESP_D4",   # 4A
    "13": "GND",      # 4OE
    "14": "+5V",
})
c3 = place("C3", "100nF", "Capacitor_THT", "C_Disc_D5.0mm_W2.5mm_P5.00mm", U1_X, g(16),
           pads={"1": "+5V", "2": "GND"})

R_TOP, R_BOT = g(30), g(38)          # rows of the resistors' pads
R_AXIAL = "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
# (ref, x, net, pad 1 row): R4 stands the other way round, input at the bottom, so
# its output points up towards MAIN JST.
RESISTORS = (("R1", U1_X + 1.27, "DATA3", R_TOP), ("R2", U1_X + 2 * 2.54, "DATA2", R_TOP),
             ("R3", U1_X + 5 * 2.54, "DATA4", R_TOP), ("R4", U1_X + 6.5 * 2.54, "DATA1", R_BOT))
for ref, x, signal, y in RESISTORS:
    r = place(ref, "100R", "Resistor_THT", R_AXIAL, x, y, rot=270 if y == R_TOP else 90,
              pads={"1": f"{signal}_RAW", "2": signal})
    r.Reference().SetPosition(pt(x, R_TOP + 5.08))
    r.Reference().SetTextAngleDegrees(90)
    r.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.9), mm(0.9)))

# ---------------------------------------------------------------- outputs
COL_D, COL_GND, COL_PLUS = g(57), g(61), g(65)   # solder columns; + also lines up MAIN JST
# Right-hand column, top to bottom: MAIN JST, screw +, screw -, screw D/-. Courtyards
# are GAP apart; the D block's pad 1 shares the pin header's row.
SCREW_X = g(74)
J8_Y = g(46)
J7_Y = J8_Y - 8.17 - GAP - 3.08
J6_Y = J7_Y - 13.26 - GAP - 3.08
J5_Y = J6_Y - 13.26 - GAP - 1.95
# MAIN: JST SM pigtail soldered in, strain relief toward the edge.
j5 = place("J5", "JST SM pigtail MAIN", "Connector_Wire",
           "SolderWire-0.5sqmm_1x03_P4.8mm_D0.9mm_OD2.3mm_Relief", COL_PLUS, J5_Y, rot=90,
           pads={"1": "+5V", "2": "DATA1", "3": "GND"}, show_ref=False)
pad_labels(j5, {"1": "+", "2": "D", "3": "-"}, -2.6, 0, 1.2)
text("MAIN JST", g(61), J5_Y - 5.0, 1.0, rot=90)

PLUS3 = {"1": "+5V", "2": "+5V", "3": "+5V"}
GND3 = {"1": "GND", "2": "GND", "3": "GND"}
TB3 = "TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal"
TB2 = "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
j6 = place("J6", "Screw 3p +", "TerminalBlock_Phoenix", TB3, SCREW_X, J6_Y, rot=90, pads=PLUS3, show_ref=False)
j7 = place("J7", "Screw 3p -", "TerminalBlock_Phoenix", TB3, SCREW_X, J7_Y, rot=90, pads=GND3, show_ref=False)
j8 = place("J8", "Screw D", "TerminalBlock_Phoenix", TB2, SCREW_X, J8_Y, rot=90,
           pads={"1": "DATA2", "2": "GND"}, show_ref=False)
text("+", g(68), J6_Y - 5.08, 2.0, bold=True)
text("-", g(68), J7_Y - 5.08, 2.0, bold=True)
pad_labels(j8, {"1": "D", "2": "-"}, g(68) - SCREW_X, 0, 1.3)

# SOLDER: three - and three +, plus D on the bottom row level with the resistors' outputs.
SOLDER_ROWS = (R_TOP, R_TOP + 5.08, R_BOT)
SW1 = "SolderWire-0.5sqmm_1x01_D0.9mm_OD2.3mm"
place("J9", "Solder D", "Connector_Wire", SW1, COL_D, R_BOT, pads={"1": "DATA4"}, show_ref=False)
for k, y in enumerate(SOLDER_ROWS):
    place(f"J{10 + k}", "Solder -", "Connector_Wire", SW1, COL_GND, y, pads={"1": "GND"}, show_ref=False)
    place(f"J{13 + k}", "Solder +", "Connector_Wire", SW1, COL_PLUS, y, pads={"1": "+5V"}, show_ref=False)
text("D", COL_D, R_BOT - 2.6, 1.2)
for s, x in (("-", COL_GND), ("+", COL_PLUS)):
    text(s, x, R_TOP - 2.6, 1.2)
text("SOLDER", COL_GND, R_BOT + 2.6, 0.9)

# PINS: 7-pin header on the bottom row, + + + D - - -, from the R4 column to the + column.
j16 = place("J16", "Pin 7p", "Connector_PinHeader_2.54mm", "PinHeader_1x07_P2.54mm_Vertical",
            COL_PLUS - 6 * 2.54, g(46), rot=90,
            pads={"1": "+5V", "2": "+5V", "3": "+5V", "4": "DATA3", "5": "GND", "6": "GND", "7": "GND"},
            show_ref=False)
pad_labels(j16, {"1": "+", "2": "+", "3": "+", "4": "D", "5": "-", "6": "-", "7": "-"}, 0, -2.4, 1.0)

# ---------------------------------------------------------------- 3D extras
# Purely visual: what actually sits in the sockets and the fuse holder, so the 3D
# view and the STEP export show the finished board. Boxes come from 3d/make_boxes.py.
def model(fp, path, offset=(0, 0, 0), rot=(0, 0, 0)):
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = path
    m.m_Offset = pcbnew.VECTOR3D(*offset)   # mm; y points up, away from the PCB's y
    m.m_Rotation = pcbnew.VECTOR3D(*rot)
    fp.Models().push_back(m)


KICAD_3D = "${KICAD10_3DMODEL_DIR}"
BOX = "${KIPRJMOD}/../3d/"
model(u1, KICAD_3D + "/Package_DIP.3dshapes/DIP-14_W7.62mm.step", (0, 0, 3.0))
model(f1, BOX + "fuse_mini.step", (4.96, -1.7, 4.0))

# ESP32 DevKit stand-in: a footprint with no pads, only models, centred on the module.
SOCKET_H, SPACER_H, KIT_PCB = 8.5, 2.5, 1.6
kit_z = SOCKET_H + SPACER_H
kit_cy = ESP_TOP_PIN_Y - 6.0 + 26.0          # USB edge sits ~6 mm above the first pin
kit = pcbnew.FOOTPRINT(board)
kit.SetReference("ESP1")
kit.SetValue("ESP32 DevKit (3D only)")
kit.Reference().SetVisible(False)
kit.Value().SetVisible(False)
kit.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
board.Add(kit)
kit.SetPosition(pt(ESP_CX, kit_cy))
rows_dy = (ESP_TOP_PIN_Y + 7 * 2.54) - kit_cy
for dx in (-ESP_ROW_SPACING / 2, ESP_ROW_SPACING / 2):
    model(kit, BOX + "header_spacer.step", (dx, -rows_dy, SOCKET_H))
model(kit, BOX + "devkit_pcb.step", (0, 0, kit_z))
top = kit_z + KIT_PCB
# WROOM-32: footprint origin sits 15.74 mm from the antenna end; turned so the
# antenna points away from USB, flush with the DevKit's far edge.
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
antenna_top = ESP_TOP_PIN_Y + 14 * 2.54 + 2.5
rect_zone(ESP_CX - 15, antenna_top, ESP_CX + 15, H - 0.3, pcbnew.F_Cu, rule_area=True)

# ---------------------------------------------------------------- branding
ap = argparse.ArgumentParser()
ap.add_argument("--gear", default=os.environ.get("GEAR_PNG"),
                help="pixel-art PNG traced into a white outline on the back")
ap.add_argument("--gear-size", type=float, default=21.0, help="gear width on the board, mm")
ap.add_argument("--mask", default="Black", help="solder mask colour for the 3D view (Black, Purple, Green...)")
args = ap.parse_args()


# Front: the logo in the free strip above the +5V bus, board name and revision under it.
text("panto", 59.0, 5.2, 3.2, bold=True)
text("WLED CONTROLLER  ·  REV 1.0", 59.0, 8.9, 0.9)

# Back: name and site in the middle, between the ESP32 header rows (no pads there).
ART_CY = ESP_TOP_PIN_Y + 7 * 2.54
if args.gear:
    print(f"gear: {gear_outline(args.gear, ESP_CX, ART_CY, args.gear_size)} silkscreen segments")
text("panto", ESP_CX, ART_CY + args.gear_size / 2 + 3.0, 2.2, layer=pcbnew.B_SilkS, bold=True)
text("panto-dev.com", ESP_CX, ART_CY + args.gear_size / 2 + 5.6, 0.9, layer=pcbnew.B_SilkS)

out = os.path.join(HERE, NAME + ".kicad_pcb")
pcbnew.SaveBoard(out, board)

# Stackup (mask colour, ENIG finish): not reachable through the Python API, so it
# goes into the saved file's (setup) block directly.
STACKUP = [
    '(layer "F.SilkS" (type "Top Silk Screen") (color "White"))',
    '(layer "F.Paste" (type "Top Solder Paste"))',
    '(layer "F.Mask" (type "Top Solder Mask") (color "{mask}") (thickness 0.01))',
    '(layer "F.Cu" (type "copper") (thickness 0.035))',
    '(layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))',
    '(layer "B.Cu" (type "copper") (thickness 0.035))',
    '(layer "B.Mask" (type "Bottom Solder Mask") (color "{mask}") (thickness 0.01))',
    '(layer "B.Paste" (type "Bottom Solder Paste"))',
    '(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))',
    '(copper_finish "ENIG")',
    '(dielectric_constraints no)',
]
stackup = "\t\t(stackup\n" + "".join(f"\t\t\t{line.format(mask=args.mask)}\n" for line in STACKUP) + "\t\t)\n"
with open(out, encoding="utf-8") as f:
    pcb_text = f.read()
pcb_text = pcb_text.replace("\t(setup\n", "\t(setup\n" + stackup, 1)
with open(out, "w", encoding="utf-8") as f:
    f.write(pcb_text)

# Net classes live in the project file. KiCad fills in every other default.
pro = os.path.join(HERE, NAME + ".kicad_pro")
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
        "netclass_patterns": [{"netclass": "Power", "pattern": p}
                              for p in ("VIN_RAW", "+5V", "+3V3")],
    },
    "meta": {"filename": NAME + ".kicad_pro", "version": 3},
}
with open(pro, "w", encoding="utf-8") as f:
    json.dump(project, f, indent=2)
print("wrote", out)
