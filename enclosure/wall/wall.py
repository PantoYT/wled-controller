"""Wall mount for wled-controller rev 2.0 `wall`, printed in PLA or PETG.

An open frame with a flat back: a rail down each side, an X brace between them, a bar
across the middle with two pads for double-sided tape, and a bar along the bottom. The board drops
in from the top, its left and right edges in the rails' grooves, and slides down until it sits
on the stops at the bottom of the grooves. Gravity holds it there; the last PINCH_L mm of each
groove is narrower, so the board is pressed in rather than resting loose. Four posts under the
mounting holes hold the board up when a terminal screw or plug pushes it towards the wall, so
it no longer tips like rev 1.0's base did, and take an M2 x 8 screw each through the board's
holes, so it cannot be lifted out either. The front is open: the whole board shows.

The bottom bar carries a cable-tie block under each output, so the strip leads pull on the
frame and not on the terminals or the tape. Rev 1.0's solid base took about 50 g of filament;
the frame prints far less (python wall.py prints the volume).

Coordinates follow KiCad's board, as in ../enclosure.py: x along the 100 mm edge (0 = left),
y from the top edge (y = 0, input J2) to the bottom edge (y = 61.8, the outputs), z out of the
wall from the board's underside. This frame is a mirror image of the real board; real()
mirrors every part once on export. On the wall, y = 0 is up.

    python wall.py           # wall.stl, wall-fit-test.stl, wall.step
    python wall.py check     # the board's STEP parts against the mount, in place and sliding in
    python wall.py render    # renders/wall-*.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import math

from build123d import (Align, Axis, Box, Compound, Cylinder, Part, Plane, Pos, Rot, export_step,
                       export_stl, fillet, import_step, mirror)

HERE = Path(__file__).resolve().parent
STEP = HERE.parent.parent / "rev2" / "wled-controller-v2-wall.step"

# ---------------------------------------------------------------- the board (rev 2.0 wall)
BOARD_W, BOARD_H, BOARD_T = 100.0, 61.8, 1.6
LEADS_BELOW = 3.0          # THT leads under the board, trimmed (STEP: 2.9)
HOLES = [(3.5, 21.0), (3.5, 33.0), (96.52, 39.37), (96.52, 57.15)]   # H1-H4, gen_board.py
CHANNELS = [70.58 - 12.0 * k for k in range(6)]                       # CH1-CH6 centres

# ---------------------------------------------------------------- fits (mm), tune here
SLOT_PLAY_Z = 0.6          # board 1.6 in a 2.2 groove (1.9 was too tight in PETG, 2026-10-29)...
PINCH_Z = 0.2              # ...that closes to 2.0 over the last PINCH_L mm; the M2 screws hold it
PINCH_L = 12.0
PINCH_RAMP = 3.0           # half the pinch over this length first, so the board finds its way in
SLOT_PLAY_X = 0.5          # per side, board edge to groove bottom (0.2 spread the rails in PETG)
LENGTH_PLAY = 0.3          # board's bottom edge to the stops
LIP = 1.2                  # how far the groove lips reach over the board's top face
LIP_T = 1.4
LEDGE = 2.0                # how far the rails reach under the board
RAIL_W = 3.0               # rail wall outside the groove
PLATE_T = 2.4
LEAD_CLEAR = 1.0           # leads to the plate
POST_D = 5.0               # under the mounting holes; they pass under the board's own columns
SCREW_PILOT = 1.7          # through each post: an M2 x 8 cuts its own thread (or tap it M2); the
                           # 6.4 mm post takes exactly the 8 - 1.6 mm left past the board, so the
                           # tip ends flush with the back
STOP_L = 2.4               # stop block below each groove
TAB = 9.0                  # bottom bar below the board, for the cable ties
BRACE_W = 6.0              # X brace and middle bar
PAD_W, PAD_H = 24.0, 18.0  # the two tape pads on the middle bar
PAD_X = (25.0, 75.0)
TIE_W, TIE_H = 4.0, 1.8    # tunnel for 3.6 x 1.2 mm cable ties
CORNER_R = 3.0

# ---------------------------------------------------------------- derived
Z_PLATE = -(LEADS_BELOW + LEAD_CLEAR)          # plate's front face
Z_BACK = Z_PLATE - PLATE_T                     # the flat back, on the wall: every part reaches it
Z_SLOT1 = BOARD_T + SLOT_PLAY_Z                # groove ceiling; the floor is the board's underside
Z_LIP1 = Z_SLOT1 + LIP_T
X0, X1 = -SLOT_PLAY_X - RAIL_W, BOARD_W + SLOT_PLAY_X + RAIL_W
Y_STOP = BOARD_H + LENGTH_PLAY
Y_END = Y_STOP + STOP_L + TAB


def box(x0, x1, y0, y1, z0, z1) -> Part:
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def rail(left: bool) -> Part:
    gx = -SLOT_PLAY_X if left else BOARD_W + SLOT_PLAY_X          # groove bottom
    ox = X0 if left else X1                                        # outer face
    ix = LEDGE if left else BOARD_W - LEDGE                        # ledge under the board
    lx = LIP if left else BOARD_W - LIP                            # lip over the board
    lo, hi = sorted((ox, gx))
    r = box(*sorted((ox, ix)), 0, Y_STOP + STOP_L, Z_BACK, 0)      # under the board, down to the wall
    r += box(lo, hi, 0, Y_STOP + STOP_L, 0, Z_LIP1)                # wall
    r += box(*sorted((ox, lx)), 0, Y_STOP + STOP_L, Z_SLOT1, Z_LIP1)   # lip
    r += box(*sorted((ox, ix)), Y_STOP, Y_STOP + STOP_L, 0, Z_LIP1)    # stop
    # Pinch: the ceiling comes down over the last PINCH_L mm, in two steps.
    px = sorted((gx, lx))
    r += box(*px, Y_STOP - PINCH_L, Y_STOP, Z_SLOT1 - PINCH_Z / 2, Z_SLOT1)
    r += box(*px, Y_STOP - PINCH_L + PINCH_RAMP, Y_STOP, Z_SLOT1 - PINCH_Z, Z_SLOT1)
    return r


def tie_block(x: float, y: float) -> Part:
    """A block with a tunnel along x: the tie goes through it and round the lead on top."""
    w, d, h = 6.0, TIE_W + 2.4, TIE_H + 1.6
    b = box(x - w / 2, x + w / 2, y - d / 2, y + d / 2, Z_PLATE, Z_PLATE + h)
    return b - box(x - w, x + w, y - TIE_W / 2, y + TIE_W / 2, Z_PLATE - 0.01, Z_PLATE + TIE_H)


def bar(xa, ya, xb, yb, w) -> Part:
    """A flat bar of width w on the back plane, from (xa, ya) to (xb, yb)."""
    length = math.hypot(xb - xa, yb - ya)
    b = Box(length, w, PLATE_T)
    return Pos((xa + xb) / 2, (ya + yb) / 2, (Z_BACK + Z_PLATE) / 2) * Rot(
        0, 0, math.degrees(math.atan2(yb - ya, xb - xa))) * b


def mount() -> Part:
    y_bot = Y_STOP + STOP_L
    frame = box(X0, X1, 0, Y_END, Z_BACK, Z_PLATE)          # outline the diagonals are trimmed to
    m = rail(True) + rail(False)
    inner0, inner1 = X0 + RAIL_W, X1 - RAIL_W
    m += (bar(inner0, 0, inner1, y_bot, BRACE_W) + bar(inner0, y_bot, inner1, 0, BRACE_W)) & frame
    mid_y = y_bot / 2                                        # where the diagonals cross
    m += box(X0, X1, mid_y - BRACE_W / 2, mid_y + BRACE_W / 2, Z_BACK, Z_PLATE)   # middle bar
    for x in PAD_X:                                          # tape pads
        m += box(x - PAD_W / 2, x + PAD_W / 2, mid_y - PAD_H / 2, mid_y + PAD_H / 2, Z_BACK, Z_PLATE)
    bottom = box(X0, X1, y_bot - BRACE_W, Y_END, Z_BACK, Z_PLATE)
    m += fillet(bottom.edges().filter_by(Axis.Z).group_by(Axis.Y)[-1], CORNER_R)
    for x, y in HOLES:                                       # posts, joined to the rails
        m += Pos(x, y, Z_BACK) * Cylinder(POST_D / 2, -Z_BACK,
                                          align=(Align.CENTER, Align.CENTER, Align.MIN))
    for x, y in HOLES:                                       # M2 pilot, all the way through
        m -= Pos(x, y, Z_BACK - 0.01) * Cylinder(SCREW_PILOT / 2, -Z_BACK + 0.02,
                                                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    y_tie = y_bot + TAB / 2
    for x in CHANNELS:
        m += tie_block(x, y_tie)
    return m


def fit_test(m: Part) -> Part:
    """The bottom 17 mm of the mount: both grooves with the pinch, the stops and the posts
    there. Slide the bare board in from the top of this piece before the full print."""
    return m & box(X0 - 1, X1 + 1, Y_STOP - PINCH_L - 5, Y_STOP + STOP_L, Z_BACK - 1, Z_LIP1 + 1)


def real(p: Part) -> Part:
    """From KiCad's mirrored frame to the real object."""
    return mirror(p, Plane.XZ)


# ---------------------------------------------------------------- check
def board_parts():
    step = import_step(str(STEP))
    for c in step.children:
        yield c.label, Pos(-100, -100, 0) * mirror(c, Plane.XZ)   # STEP y runs the other way


def check() -> int:
    m = mount()
    parts = list(board_parts())
    hits = 0
    for dy in [0.0] + [-float(d) for d in range(4, 68, 4)]:      # in place, then on the way in
        for label, s in parts:
            if (v := (Pos(0, dy, 0) * s & m).volume) > 0.01:
                hits += 1
                print(f"HIT dy={dy:+.0f}: {label} {v:.2f} mm3")
    print(f"{len(parts)} board parts, in place and sliding in: {hits} overlaps")
    return 1 if hits else 0


# ---------------------------------------------------------------- render
def render() -> None:
    import pyvista as pv
    out = HERE / "renders"
    out.mkdir(exist_ok=True)
    board = HERE / "board.stl"
    if not board.exists():
        export_stl(real(Compound([s for _, s in board_parts()])), str(board), tolerance=0.05)

    def shot(name, pos, focal=(50, -38, 0), up=(0, 1, 0), dy=0.0, with_board=True):
        p = pv.Plotter(off_screen=True, window_size=(1600, 1100))
        p.set_background("#0e0f12")
        p.enable_anti_aliasing("ssaa")
        p.add_mesh(pv.read(HERE / "wall.stl"), color="#6a6e78", specular=0.2, smooth_shading=False)
        if with_board:
            p.add_mesh(pv.read(board).translate((0, -dy, 0), inplace=False), color="#3a3d44",
                   specular=0.4, smooth_shading=False)
        p.add_light(pv.Light(position=(-150, 150, 250), intensity=1.4))
        p.add_light(pv.Light(position=(250, -200, 120), intensity=0.8))
        p.camera_position = [pos, focal, up]
        p.screenshot(str(out / f"wall-{name}.png"))
        p.close()
        print(f"renders/wall-{name}.png")

    # Real frame: y = 0 is the top edge and the board runs to y = -61.8; z points off the wall.
    shot("front", (50, -38, 300))
    shot("iso", (190, 60, 190))
    shot("sliding", (190, 60, 190), dy=-30.0)
    shot("bottom", (60, -230, 120), up=(0, 0, 1))
    shot("back", (50, -38, -300), with_board=False)
    shot("empty", (190, 60, 190), with_board=False)


def main() -> None:
    m = mount()
    export_stl(real(m), str(HERE / "wall.stl"))
    export_stl(real(fit_test(m)), str(HERE / "wall-fit-test.stl"))
    export_step(real(m), str(HERE / "wall.step"))
    size = m.bounding_box().size
    print(f"wall mount: {size.X:.1f} x {size.Y:.1f} x {size.Z:.1f} mm, {m.volume / 1000:.1f} cm3 solid "
          f"= {m.volume / 1000 * 1.24:.0f} g PLA at 100 % infill (less with the slicer's infill)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "check":
        sys.exit(check())
    if cmd == "render":
        render()
    else:
        main()
