"""Interference check: every 3D part of the board against the enclosure (in place and while
sliding in from the right) and against the open base. Works in enclosure.py's KiCad frame.
Exit 1 on any overlap."""

import sys

from build123d import Box, Plane, Pos, import_step, mirror

import enclosure as E


def board_parts():
    step = import_step(str(E.HERE.parent.parent / "rev1" / "wled-controller.step"))
    for c in step.children:
        s = Pos(-100, -100, 0) * mirror(c, Plane.XZ)          # STEP y runs the other way
        if c.label == "header_spacer":                        # the stacked header, full height
            bb = s.bounding_box()
            s = Pos(bb.center().X, bb.center().Y, (bb.min.Z + bb.max.Z + E.DEVKIT_RAISE) / 2) * Box(
                bb.size.X, bb.size.Y, bb.size.Z + E.DEVKIT_RAISE)
        yield c.label, (Pos(0, 0, E.DEVKIT_RAISE) * s if c.label in E.RAISED else s)


def main() -> int:
    b, l, base = E.body(), E.lid(), E.base()
    parts = list(board_parts())
    hits = 0
    if (b & l).volume > 0.01:
        hits += 1
        print("HIT body x lid")
    for label, s in parts:
        for name, part in (("body", b), ("lid", l), ("base", base)):
            if (v := (s & part).volume) > 0.01:
                hits += 1
                print(f"HIT {label} x {name}: {v:.2f} mm3")
    for dx in range(104, 0, -4):
        for label, s in parts:
            if (v := (Pos(dx, 0, 0) * s & b).volume) > 0.01:
                hits += 1
                print(f"SLIDE HIT at dx={dx}: {label} {v:.2f} mm3")
    print(f"{len(parts)} board parts, in place and sliding in: {hits} overlaps")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
