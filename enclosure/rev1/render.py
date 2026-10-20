"""Renders of the enclosure with the real board inside: renders/enclosure-*.png.

The board comes from ../../rev1/wled-controller.step (the DevKit raised as in check.py)
and is cached as board.stl next to this script."""

from __future__ import annotations

from pathlib import Path

import pyvista as pv

HERE = Path(__file__).resolve().parent
OUT = HERE / "renders"
BG = "#0e0f12"
PLA = "#34363c"
BOARD = "#1c1d21"


def board_stl() -> Path:
    path = HERE / "board.stl"
    if not path.exists():
        from build123d import Compound, export_stl
        from check import board_parts
        from enclosure import real
        export_stl(real(Compound([s for _, s in board_parts()])), str(path), tolerance=0.05)
    return path


def scene(lid_offset=(0, 0, 0), body_opacity=1.0, lid_opacity=1.0, board=True, size=(1600, 1000),
          shell="body"):
    p = pv.Plotter(off_screen=True, window_size=size)
    p.set_background(BG)
    p.enable_anti_aliasing("ssaa")
    kw = dict(smooth_shading=False, specular=0.25, specular_power=12)
    p.add_mesh(pv.read(HERE / f"{shell}.stl"), color=PLA, opacity=body_opacity, **kw)
    if lid_opacity:
        lid = pv.read(HERE / "lid.stl").translate(lid_offset, inplace=False)
        p.add_mesh(lid, color=PLA, opacity=lid_opacity, **kw)
    if board:
        p.add_mesh(pv.read(board_stl()), color=BOARD, specular=0.4, **{"smooth_shading": False})
    p.add_light(pv.Light(position=(-150, -200, 250), intensity=0.9))
    p.add_light(pv.Light(position=(250, 200, 120), intensity=0.5))
    return p


def shot(p: pv.Plotter, name: str, pos, focal=(52, -33, 10), up=(0, 0, 1)) -> None:
    p.camera_position = [pos, focal, up]
    OUT.mkdir(exist_ok=True)
    p.screenshot(str(OUT / f"enclosure-{name}.png"))
    p.close()
    print("renders/enclosure-" + name + ".png")


def main() -> None:
    # Real frame: the input edge is at y = 0 and the board runs to y = -61.8, so the camera
    # stands at +y to look at the inputs.
    shot(scene(), "closed", (210, 150, 160))
    shot(scene(lid_offset=(70, 0, 22)), "open", (220, 160, 170))
    shot(scene(lid_opacity=0.18), "inside", (190, 130, 190))
    shot(scene(), "outputs", (230, -120, 90))
    shot(scene(lid_opacity=0), "top", (52, -33, 260), up=(0, 1, 0))
    shot(scene(lid_opacity=0, shell="base"), "base", (190, 140, 150), focal=(52, -33, 0))
    shot(scene(lid_opacity=0, shell="base"), "base-outputs", (200, -150, 110), focal=(52, -33, 0))


if __name__ == "__main__":
    main()
