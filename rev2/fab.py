"""Fabrication outputs for one rev 2.0 board: Gerbers + drill zipped for JLCPCB, STEP, renders.

    python fab.py wled-controller-v2-wall          # -> ../jlc/<name>-gerbers.zip, <name>.step, renders/
    python fab.py wled-controller-v2-wall-art --no-step

kicad-cli is found on PATH, then in KiCad 10's default install folder; KICAD_CLI overrides both.
Run it after gen_board.py, route.py and a DRC with --refill-zones --save-board.
"""
import argparse
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
JLC = HERE.parent / "jlc"
LAYERS = "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts"


def kicad_cli() -> str:
    for c in (os.environ.get("KICAD_CLI"), shutil.which("kicad-cli"),
              r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe", "/usr/bin/kicad-cli"):
        if c and Path(c).exists():
            return c
    raise SystemExit("kicad-cli not found; set KICAD_CLI")


def run(*args) -> None:
    r = subprocess.run([kicad_cli(), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"kicad-cli {' '.join(args[:3])} failed:\n{r.stdout}{r.stderr}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="board file name without .kicad_pcb")
    ap.add_argument("--no-step", action="store_true")
    a = ap.parse_args()
    pcb = HERE / f"{a.name}.kicad_pcb"
    if not pcb.exists():
        raise SystemExit(f"no {pcb.name}")

    with tempfile.TemporaryDirectory() as tmp:
        run("pcb", "export", "gerbers", "--layers", LAYERS, "-o", tmp + os.sep, str(pcb))
        run("pcb", "export", "drill", "-o", tmp + os.sep, str(pcb))
        files = sorted(Path(tmp).iterdir())
        if not any(f.suffix == ".drl" for f in files):
            raise SystemExit("no drill file was written")       # kicad-cli once exited 0 without one
        JLC.mkdir(exist_ok=True)
        out = JLC / f"{a.name}-gerbers.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, f.name)
    print(f"{out.relative_to(HERE.parent)}: {len(files)} files")

    if not a.no_step:
        run("pcb", "export", "step", "--subst-models", "--force", "-o", str(HERE / f"{a.name}.step"), str(pcb))
        print(f"{a.name}.step")

    (HERE / "renders").mkdir(exist_ok=True)
    short = a.name.replace("wled-controller-", "")
    common = ["--use-board-stackup-colors", "--floor", "--background", "opaque", "-w", "1600", "-h", "1100"]
    for side in ("top", "bottom"):
        run("pcb", "render", *common, "--side", side, "-o", str(HERE / "renders" / f"{short}-{side}.png"), str(pcb))
    run("pcb", "render", *common, "--rotate", "-45,0,25", "--zoom", "0.9",
        "-o", str(HERE / "renders" / f"{short}-iso.png"), str(pcb))
    print(f"renders/{short}-top/bottom/iso.png")


if __name__ == "__main__":
    main()
