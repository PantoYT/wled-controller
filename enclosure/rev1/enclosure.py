"""Slide-in enclosure for wled-controller rev 1.0, printed in PLA.

The board slides in from the output end (right) along two rails, grooves in the long walls,
until it stops against the left wall. The lid slides in over it along grooves in the same
walls; its end plate closes the right end and has windows for the output screw terminals.
One M3 screw through the end plate goes into a heat-set insert in the body and holds the lid,
and the lid holds the board.

Why from the right: J8 ends 0.1 mm from the far edge, so it would scrape the far rail's lip
along the whole board length on the way in from the left.

Coordinates follow KiCad's board: x along the 100 mm edge (0 = left edge), y from the input
edge (y = 0, DC jack and screw input) to the far edge (y = 61.8), z up from the board's
underside. KiCad's y points down the screen, so this frame is a mirror image of the real
board; everything is designed and checked here and mirrored once, in real(), on export.
Every fit is a named clearance below, so a tight fit is changed in one place.

    python enclosure.py      # body.stl, lid.stl, fit-test-body.stl, fit-test-lid.stl, enclosure.step
    python check.py          # the real board's 3D parts against the enclosure, also while sliding in
    python render.py         # renders/*.png
"""

from __future__ import annotations

from pathlib import Path

from build123d import (Align, Axis, Box, Cylinder, Part, Plane, Pos, Rot, Text, chamfer,
                       export_step, export_stl, extrude, mirror)

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- the board (rev 1.0)
BOARD_W, BOARD_H, BOARD_T = 100.0, 61.8, 1.6
LEADS_BELOW = 2.4          # THT leads under the board (STEP: -2.3)
TALLEST = 24.6             # button caps of the DevKit on two stacked female headers
ESP_OVERHANG = 3.4         # the DevKit's antenna end passes the far edge (STEP: 3.3)
# The STEP has the DevKit on one 2.5 mm spacer; board #1 has it on a second 8.5 mm female
# header (to clear the fuse), so these STEP parts sit 6 mm higher in check.py and render.py.
RAISED = {"devkit_pcb", "ESP32-WROOM-32", "usb_c", "button", "button_cap", "ch340", "ldo", "led"}
DEVKIT_RAISE = 6.0

# ---------------------------------------------------------------- PLA fits (mm)
SLOT_PLAY_Z = 0.5          # board 1.6 in a 2.1 slot
SLOT_PLAY_Y = 0.4          # per side, between the board edge and the groove bottom
LENGTH_PLAY = 0.8          # board 100 in 100.8 (PLA shrinks about 0.3-0.5 % along the long axis)
LIP = 0.9                  # how far the groove lips reach over the board (J4 sits 1.3 mm in)
LID_T = 2.0
LID_PLAY_Z = 0.6           # lid 2.0 in a 2.6 groove
LID_PLAY_Y = 0.4           # per side
END_PLAY = 0.3             # end plate to body
WALL = 2.4
FLOOR = 2.0
INSERT_D, INSERT_DEPTH = 4.0, 6.5   # M3 brass insert up to 5.7 mm long
SCREW_D = 3.4
END_T = 2.6
FOOT_D, FOOT_DEPTH = 10.4, 0.8   # recesses for 10 mm stick-on rubber bumpers

# ---------------------------------------------------------------- heights
Z_FLOOR = -(LEADS_BELOW + 1.6)                  # inner floor; the leads clear it by 1.6
Z_SLOT0, Z_SLOT1 = -SLOT_PLAY_Z / 2, BOARD_T + SLOT_PLAY_Z / 2
Z_LIP1 = Z_SLOT1 + 1.2                          # top of the groove lips
Z_LID0 = TALLEST + 1.8                          # bottom of the lid groove
Z_LID1 = Z_LID0 + LID_T + LID_PLAY_Z            # top of the lid groove
Z_TOP = Z_LID1 + 1.2                            # wall top: a lip over the lid
Z_BOTTOM = Z_FLOOR - FLOOR

# ---------------------------------------------------------------- plan
X_STOP = -0.3                                   # left wall inner face, the board stops here
X_OUT0 = X_STOP - 1.2 - WALL                    # lid groove + wall
X_END = BOARD_W + LENGTH_PLAY - 0.3             # open right end of the body
Y_IN0 = LIP                                     # input-side wall inner face at the lips
Y_G0 = -SLOT_PLAY_Y                             # its board groove bottom
Y_OUT0 = Y_G0 - WALL
Y_IN1 = BOARD_H - LIP                           # far wall lips
Y_G1 = BOARD_H + SLOT_PLAY_Y
Y_FAR = BOARD_H + ESP_OVERHANG + 0.8            # far wall inner face above the lips
Y_OUT1 = Y_FAR + 1.2 + WALL                     # lid groove + wall
Y_LID0, Y_LID1 = Y_IN0 - 2.1, Y_FAR + 1.2       # lid groove bottoms (y)

# Openings, from the board's STEP.
INPUT_WINDOWS = [               # in the input-side wall: (x0, x1, z1)
    (1.0, 15.6, 13.5),          # J1 DC jack
    (17.4, 34.8, Z_LID0 - 0.6), # J4 pins, J3 solder pads, F1, and the DevKit's USB-C
    (36.0, 48.0, 14.0),         # J2 screw input
    (76.5, 88.5, 9.0),          # J5 JST pigtail wires
]
END_WINDOWS = [                 # in the lid's end plate: (y0, y1, z1), the output terminals
    (15.1, 32.1, 13.0),         # J6
    (32.7, 49.7, 13.0),         # J7
    (50.3, BOARD_H + 0.4, 13.0),  # J8
]
SCREW_Y, SCREW_Z = (BOARD_H + Y_OUT1) / 2 + 0.6, 12.0   # the lid screw, far right corner


def box(x0, x1, y0, y1, z0, z1) -> Part:
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def body() -> Part:
    b = box(X_OUT0, X_END, Y_OUT0, Y_OUT1, Z_BOTTOM, Z_TOP)
    b -= box(X_STOP, X_END + 1, Y_IN0, Y_FAR, Z_LIP1, Z_LID0)    # cavity above the lips
    b -= box(X_STOP, X_END + 1, Y_IN0, Y_IN1, Z_FLOOR, Z_LIP1)   # between floor and lips
    b -= box(X_STOP, X_END + 1, Y_G0, Y_G1, Z_SLOT0, Z_SLOT1)    # board grooves
    b -= box(X_STOP - 1.2, X_END + 1, Y_LID0, Y_LID1, Z_LID0, Z_LID1)   # lid grooves
    b -= box(X_STOP, X_END + 1, Y_IN0, Y_FAR, Z_LID1 - 0.01, Z_TOP + 1)  # open over the lid
    for x0, x1, z1 in INPUT_WINDOWS:
        b -= box(x0, x1, Y_OUT0 - 1, Y_IN0 + 0.1, Z_SLOT1, z1)
    # J8 reaches 0.1 mm from the far edge: no lip over it, the ledge under the board stays.
    b -= box(88.3, X_END + 1, Y_IN1 - 0.1, Y_FAR, Z_SLOT1, Z_LIP1 + 0.1)
    # Screw block in the far right corner, outside the board's edge and under the DevKit's
    # antenna end (that passes over it on the way in).
    b += box(92.0, X_END, BOARD_H + 0.2, Y_FAR, Z_LIP1, 17.5)
    b -= Pos(X_END + 0.01, SCREW_Y, SCREW_Z) * Rot(0, -90, 0) * Cylinder(
        INSERT_D / 2, INSERT_DEPTH, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Printed feet would make the floor print on four points, so: recesses for bumpers.
    for x in (X_OUT0 + 7, X_END - 7):
        for y in (Y_OUT0 + 7, Y_OUT1 - 7):
            b -= Pos(x, y, Z_BOTTOM - 0.01) * Cylinder(
                FOOT_D / 2, FOOT_DEPTH, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return b


def lid() -> Part:
    z0 = Z_LID0 + LID_PLAY_Z / 2
    x_end0 = X_END + END_PLAY
    plate = box(X_STOP - 1.2 + LID_PLAY_Y, x_end0 + END_T, Y_LID0 + LID_PLAY_Y,
                Y_LID1 - LID_PLAY_Y, z0, z0 + LID_T)
    end = box(x_end0, x_end0 + END_T, Y_OUT0, Y_OUT1, Z_BOTTOM, Z_TOP)
    lid = plate + end
    for y0, y1, z1 in END_WINDOWS:
        lid -= box(x_end0 - 1, x_end0 + END_T + 1, y0, y1, Z_SLOT1, z1)
    lid -= Pos(x_end0 - 1, SCREW_Y, SCREW_Z) * Rot(0, 90, 0) * Cylinder(
        SCREW_D / 2, END_T + 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Finger grip along the end plate's top edge, and a quiet mark on top.
    lid -= box(x_end0 + END_T - 0.8, x_end0 + END_T + 1, 8, Y_OUT1 - 18, Z_TOP - 5, Z_TOP + 1)
    mark = Pos(BOARD_W / 2, (Y_OUT0 + Y_OUT1) / 2, z0 + LID_T - 0.6) * extrude(
        mirror(Text("panto", 7, align=(Align.CENTER, Align.CENTER)), Plane.XZ), 1)  # reads right after real()
    return lid - mark


def fit_test(b: Part, l: Part) -> tuple[Part, Part]:
    """The last 16 mm of body and lid: both rails, both lid grooves, the insert block and the
    screw. Slide the real board's right end and the lid piece in before the full print."""
    cut = box(BOARD_W - 16, X_END + END_T + 2, Y_OUT0 - 1, Y_OUT1 + 1,
              Z_BOTTOM - 1, Z_TOP + 1)
    return b & cut, l & cut


# ---------------------------------------------------------------- open base
BASE_PLAY = 0.5            # board to rim, per side
BASE_RIM = 2.0
POST_D = 7.5
POST_H = 6.5               # floor to the board's underside; leads clear the floor by 4
HOLES = [(3.81, 57.15), (45.72, 57.15), (72.39, 3.81)]   # H1-H3 (the jack owns the 4th corner)
PEG_D = 3.0                # into the board's 3.2 mm holes
PEG_UP = 1.4               # above the board's top face, tip chamfered
RIM_TOP = 1.0              # below the board's top face: the edges and every connector stay free


def base() -> Part:
    """The board on three posts in a shallow tray, located by pegs through its mounting holes,
    no screws: lift it off, drop it on. The whole board stays visible, the floor keeps the
    leads off the desk, and nothing is in the way of a plug."""
    z_floor = -POST_H
    x0, x1 = -BASE_PLAY - BASE_RIM, BOARD_W + BASE_PLAY + BASE_RIM
    y0, y1 = -BASE_PLAY - BASE_RIM, BOARD_H + BASE_PLAY + BASE_RIM
    b = box(x0, x1, y0, y1, z_floor - FLOOR, RIM_TOP)
    b -= box(x0 + BASE_RIM, x1 - BASE_RIM, y0 + BASE_RIM, y1 - BASE_RIM, z_floor, RIM_TOP + 1)
    for x, y in HOLES:
        b += Pos(x, y, z_floor) * Cylinder(POST_D / 2, POST_H,
                                           align=(Align.CENTER, Align.CENTER, Align.MIN))
        peg = Pos(x, y, 0) * Cylinder(PEG_D / 2, BOARD_T + PEG_UP,
                                      align=(Align.CENTER, Align.CENTER, Align.MIN))
        b += chamfer(peg.edges().group_by(Axis.Z)[-1], 0.5)
    for x in (x0 + 7, x1 - 7):
        for y in (y0 + 7, y1 - 7):
            b -= Pos(x, y, z_floor - FLOOR - 0.01) * Cylinder(
                FOOT_D / 2, FOOT_DEPTH, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return b


def real(p: Part) -> Part:
    """From KiCad's mirrored frame to the real object."""
    return mirror(p, Plane.XZ)


def main() -> None:
    b, l, s = body(), lid(), base()
    tb, tl = fit_test(b, l)
    parts = {"body": b, "lid": l, "fit-test-body": tb, "fit-test-lid": tl, "base": s}
    for name, p in parts.items():
        export_stl(real(p), str(HERE / f"{name}.stl"))
    export_step(real(b + l), str(HERE / "enclosure.step"))
    export_step(real(s), str(HERE / "base.step"))
    for name, p in (("enclosure, closed", b + l), ("base", s)):
        size = p.bounding_box().size
        print(f"{name}: {size.X:.1f} x {size.Y:.1f} x {size.Z:.1f} mm")


if __name__ == "__main__":
    main()
