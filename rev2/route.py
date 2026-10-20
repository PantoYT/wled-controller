"""Route wled-controller-v2-<size>.kicad_pcb: rev 1.0's grid A* router, without hand-drawn
presets (rev 2.0's channel strips route themselves).

Run with KiCad's bundled Python, right after gen_board.py:
    "C:/Program Files/KiCad/10.0/bin/python.exe" route.py --size 120
    kicad-cli pcb drc --refill-zones --save-board wled-controller-v2-120.kicad_pcb

Routes every net except GND (the GND pours on both layers pick up all
through-hole GND pads), then adds GND stitching vias.

What makes the result look hand-drawn rather than autorouted:
  * the grid is 1.27/4 mm, so every pad centre on the 1.27 mm placement grid is
    a grid node and straight runs line up with pad rows;
  * only 0/45/90 degree segments; a 45 degree turn is cheap, 90 costs more,
    anything sharper is forbidden;
  * a soft "keep away" field: tracks pay extra for running near foreign copper
    or across a part's body, so they keep a visible gap instead of hugging pads.
"""
import argparse
import heapq
import math
import os
import sys

import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
_ap = argparse.ArgumentParser()
_ap.add_argument("--size", choices=("120", "100", "phi", "phi4", "wall"), default="120")
_ap.add_argument("--art", action="store_true", help="route the -art board from gen_board.py --art")
_a = _ap.parse_args()
SIZE = _a.size
PCB = os.path.join(HERE, f"wled-controller-v2-{SIZE}" + ("-art" if _a.art else "") + ".kicad_pcb")

OX, OY = 100.0, 100.0          # board origin on the sheet (matches gen_board.py)
W, H = {"120": (120.0, 74.16), "100": (100.0, 100.0), "phi": (100.0, 61.8), "phi4": (100.0, 61.8), "wall": (100.0, 61.8)}[SIZE]
CORNER_R = 2.0
EDGE_CLEAR = 0.5
G = 1.27 / 4                   # routing grid, mm
MARGIN = 0.1                   # extra clearance so diagonal steps never cut a corner

CH = range(1, 9)
POWER = {"VIN_RAW": 2.6, "+5V": 2.6, "+3V3": 1.0, "GND": 0.8, **{f"V_CH{c}": (2.0 if SIZE == "phi4" else 1.5) for c in CH}}
SIGNAL_W = 0.4
CLEAR = {"power": 0.3, "signal": 0.2}
VIA = {"power": (1.2, 0.6), "signal": (0.8, 0.4)}
VIA_COST = 20.0                # in mm of track
TURN_45, TURN_90 = 2.0, 6.0    # extra cost per turn, mm of track
DIAGONAL = 1.15                # 45 degree runs cost a bit more, so they stay short chamfers
SOFT = 1.6                     # keep-away band beyond the hard clearance, mm
SOFT_WEIGHT = 2.5              # cost multiplier at the edge of the hard clearance
BODY_WEIGHT = 0.8              # extra cost multiplier inside a foreign part's courtyard
# Power prefers the top layer, signals the bottom, so they cross instead of fighting.
LAYER_COST = {"power": (1.0, 1.4), "signal": (1.3, 1.0)}

# Route order: wide and long first.
ORDER = (["VIN_RAW", "+5V", "+3V3"] + [f"V_CH{c}" for c in CH] + [f"IO_CH{c}" for c in CH]
         + [f"OUT{c}_RAW" for c in CH] + [f"DATA{c}" for c in CH]
         + [f"ACT{c}" for c in CH] + [f"LEDA{c}" for c in CH] + [f"PLED{c}" for c in CH])

KEEPOUTS = []                  # filled from rule areas: (x0, y0, x1, y1)

# rev 1.0 laid hand-drawn presets here; rev 2.0 has none, the router takes every net.


def build_presets(board):
    """GND stubs laid before anything else is routed, for pads that tracks can fence off from
    both pours. C3's GND pad sits where the +5V runs to U1 pass, so it gets its own via."""
    c3 = [p for p in board.FindFootprintByReference("C3").Pads()]
    (a,) = [p for p in c3 if p.GetNumber() == "1"]
    (b,) = [p for p in c3 if p.GetNumber() == "2"]
    ax, ay = to_mm(a.GetPosition().x) - OX, to_mm(a.GetPosition().y) - OY
    bx, by = to_mm(b.GetPosition().x) - OX, to_mm(b.GetPosition().y) - OY
    d = math.hypot(bx - ax, by - ay)
    via = (round(bx + (bx - ax) / d * 2.8, 3), round(by + (by - ay) / d * 2.8, 3))
    pieces = [(0, [(bx, by), via]), ("via", via)]
    # U1's GND pin ends the input row, where the incoming signal tracks close round it on both
    # layers; it gets a stub past the end of the row to a via of its own.
    u1 = {p.GetNumber(): p for p in board.FindFootprintByReference("U1").Pads()}
    (x9, y9), (x10, y10) = [(to_mm(u1[n].GetPosition().x) - OX, to_mm(u1[n].GetPosition().y) - OY)
                            for n in ("9", "10")]
    u1_via = (round(x10 + (x10 - x9) / 2.54 * 2.8, 3), round(y10 + (y10 - y9) / 2.54 * 2.8, 3))
    pieces += [(0, [(x10, y10), u1_via]), ("via", u1_via)]
    # The ESP32's GND pins sit in a row of signal pins whose tracks leave sideways and can
    # fence them in on both layers; a stub on each layer into the free space between the
    # header rows keeps them on the pours.
    def gnd_pin(ref):
        (gp,) = [p for p in board.FindFootprintByReference(ref).Pads() if p.GetNumber() == "2"]
        return to_mm(gp.GetPosition().x) - OX, to_mm(gp.GetPosition().y) - OY

    for ref, other in (("U2", "U3"), ("U3", "U2")):
        (x, y), (ox, oy) = gnd_pin(ref), gnd_pin(other)     # stub points at the other row
        d = math.hypot(ox - x, oy - y)
        end = (round(x + (ox - x) / d * 3.0, 3), round(y + (oy - y) / d * 3.0, 3))
        pieces += [(0, [(x, y), end]), (1, [(x, y), end])]
    return {"GND": pieces}


nx, ny = int(W / G) + 1, int(H / G) + 1
XS = np.arange(nx) * G
YS = np.arange(ny) * G
GX, GY = np.meshgrid(XS, YS)
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
# Directions in angle order, so |a - b| (mod 8) is the turn in 45 degree steps.
DIRS = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1)]


def mm(v):
    return pcbnew.FromMM(v)


def to_mm(v):
    return pcbnew.ToMM(v)


def cls(net):
    return "power" if net in POWER else "signal"


def width(net):
    return POWER.get(net, SIGNAL_W)


# ---------------------------------------------------------------- obstacles
class Obstacle:
    """Copper (or hole) shape as a rounded rectangle or a capsule, in board mm."""

    def __init__(self, net, layers, kind, geom, clear):
        self.net, self.layers, self.kind, self.geom, self.clear = net, layers, kind, geom, clear

    def window(self, reach):
        if self.kind == "rrect":
            x0, y0, x1, y1, r = self.geom
        else:
            ax, ay, bx, by, r = self.geom
            x0, x1, y0, y1 = min(ax, bx) - r, max(ax, bx) + r, min(ay, by) - r, max(ay, by) + r
        return x0 - reach, y0 - reach, x1 + reach, y1 + reach

    def distance(self, X, Y):
        if self.kind == "rrect":
            x0, y0, x1, y1, r = self.geom
            dx = np.maximum(np.maximum(x0 + r - X, 0), X - (x1 - r))
            dy = np.maximum(np.maximum(y0 + r - Y, 0), Y - (y1 - r))
            return np.hypot(dx, dy) - r
        ax, ay, bx, by, r = self.geom
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = np.clip(((X - ax) * vx + (Y - ay) * vy) / L2, 0, 1) if L2 > 0 else 0
        return np.hypot(X - (ax + t * vx), Y - (ay + t * vy)) - r


def pad_obstacle(pad):
    bb = pad.GetBoundingBox()
    x0, y0 = to_mm(bb.GetLeft()) - OX, to_mm(bb.GetTop()) - OY
    x1, y1 = to_mm(bb.GetRight()) - OX, to_mm(bb.GetBottom()) - OY
    shape = pad.GetShape(pcbnew.F_Cu)
    r = min(x1 - x0, y1 - y0) / 2 if shape in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL) else 0.0
    net = pad.GetNetname()
    # GND pads keep a wider ring free, so their thermal spokes into the pours survive.
    clear = 0.6 if net == "GND" else (CLEAR[cls(net)] if net else 0.25)
    return Obstacle(net, (0, 1), "rrect", (x0, y0, x1, y1, r), clear)


def gap_field(obstacles, net, layer, clear_self):
    """Per grid node: distance from a track centreline to the nearest foreign
    copper, minus the clearance that copper needs. Hard limit is gap >= half."""
    gap = np.full((ny, nx), 99.0)
    for ob in obstacles:
        if layer not in ob.layers or (ob.net and ob.net == net):
            continue
        need = max(clear_self, ob.clear)
        reach = 2.0 + need + SOFT
        x0, y0, x1, y1 = ob.window(reach)
        i0, i1 = max(0, int(x0 / G)), min(nx, int(math.ceil(x1 / G)) + 1)
        j0, j1 = max(0, int(y0 / G)), min(ny, int(math.ceil(y1 / G)) + 1)
        if i0 >= i1 or j0 >= j1:
            continue
        d = ob.distance(GX[j0:j1, i0:i1], GY[j0:j1, i0:i1]) - need
        np.minimum(gap[j0:j1, i0:i1], d, out=gap[j0:j1, i0:i1])
    # Board edge (rounded rectangle).
    r = CORNER_R
    dx = np.maximum(np.maximum(r - GX, 0), GX - (W - r))
    dy = np.maximum(np.maximum(r - GY, 0), GY - (H - r))
    np.minimum(gap, (r - np.hypot(dx, dy)) - EDGE_CLEAR, out=gap)
    for kx0, ky0, kx1, ky1 in KEEPOUTS:
        inside = (GX > kx0) & (GX < kx1) & (GY > ky0) & (GY < ky1)
        gap[inside] = -1.0
        ddx = np.maximum(np.maximum(kx0 - GX, 0), GX - kx1)
        ddy = np.maximum(np.maximum(ky0 - GY, 0), GY - ky1)
        np.minimum(gap, np.hypot(ddx, ddy), out=gap)
    return gap


def body_mask(board, net):
    """Courtyards of parts that have no pad on this net (tracks may cross, at a price)."""
    m = np.zeros((ny, nx), dtype=bool)
    for fp in board.GetFootprints():
        if any(p.GetNetname() == net for p in fp.Pads()):
            continue
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount() == 0:
            continue
        bb = cy.BBox()
        x0, y0 = to_mm(bb.GetLeft()) - OX, to_mm(bb.GetTop()) - OY
        x1, y1 = to_mm(bb.GetRight()) - OX, to_mm(bb.GetBottom()) - OY
        m |= (GX > x0) & (GX < x1) & (GY > y0) & (GY < y1)
    return m


# ---------------------------------------------------------------- search
def astar(sources, goal, free, step_cost, via_ok, kind):
    """sources: iterable of (layer, i, j). goal: (i, j) on either layer."""
    gi, gj = goal
    lc = min(LAYER_COST[kind])

    def h(i, j):
        dx, dy = abs(i - gi), abs(j - gj)
        return (max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)) * G * lc

    best = {}
    heap = []
    for (l, i, j) in sources:
        if free[l][j, i]:
            best[(l, i, j, -1)] = 0.0
            heapq.heappush(heap, (h(i, j), 0.0, l, i, j, -1))
    parent = {}
    while heap:
        f, g, l, i, j, d = heapq.heappop(heap)
        if best.get((l, i, j, d), 1e18) < g:
            continue
        if (i, j) == (gi, gj):
            path = [(l, i, j)]
            key = (l, i, j, d)
            while key in parent:
                key = parent[key]
                path.append(key[:3])
            return path[::-1]
        sc = step_cost[l]
        for nd, (di, dj) in enumerate(DIRS):
            turn = 0 if d < 0 else min(abs(nd - d), 8 - abs(nd - d))
            if turn > 2:
                continue
            ni, nj = i + di, j + dj
            if not (0 <= ni < nx and 0 <= nj < ny) or not free[l][nj, ni]:
                continue
            length = G * (math.sqrt(2) * DIAGONAL if di and dj else 1.0)
            ng = g + length * (sc[j, i] + sc[nj, ni]) / 2 + (0, TURN_45, TURN_90)[turn]
            key = (l, ni, nj, nd)
            if ng < best.get(key, 1e18):
                best[key] = ng
                parent[key] = (l, i, j, d)
                heapq.heappush(heap, (ng + h(ni, nj), ng, l, ni, nj, nd))
        if via_ok[j, i]:
            ol = 1 - l
            key = (ol, i, j, -1)
            ng = g + VIA_COST
            if free[ol][j, i] and ng < best.get(key, 1e18):
                best[key] = ng
                parent[key] = (l, i, j, d)
                heapq.heappush(heap, (ng + h(i, j), ng, ol, i, j, -1))
    return None


def cell(x, y):
    return int(round(x / G)), int(round(y / G))


def add_track(board, net, layer, a, b, w, clear, obstacles):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(mm(OX + a[0]), mm(OY + a[1])))
    t.SetEnd(pcbnew.VECTOR2I(mm(OX + b[0]), mm(OY + b[1])))
    t.SetWidth(mm(w))
    t.SetLayer(LAYERS[layer])
    t.SetNet(board.FindNet(net))
    board.Add(t)
    obstacles.append(Obstacle(net, (layer,), "seg", (a[0], a[1], b[0], b[1], w / 2), clear))


def lay_presets(board, obstacles):
    """Draw the hand-made pieces; return {net: set of (layer, i, j) they cover}."""
    covered = {}
    for net, pieces in build_presets(board).items():
        cells = covered.setdefault(net, set())
        for layer, pts in pieces:
            if layer == "via":
                vd, vdrill = VIA[cls(net)]
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(mm(OX + pts[0]), mm(OY + pts[1])))
                v.SetWidth(mm(vd))
                v.SetDrill(mm(vdrill))
                v.SetNet(board.FindNet(net))
                board.Add(v)
                obstacles.append(Obstacle(net, (0, 1), "seg", (*pts, *pts, vd / 2), CLEAR[cls(net)]))
                cells |= {(0, *cell(*pts)), (1, *cell(*pts))}
                continue
            for a, b in zip(pts, pts[1:]):
                add_track(board, net, layer, a, b, width(net), CLEAR[cls(net)], obstacles)
                n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (G / 2)))
                for k in range(n + 1):
                    cells.add((layer, *cell(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)))
    return covered


def simplify(path):
    """Collapse a cell path into corner points per layer, keeping layer changes."""
    pts = [path[0]]
    for k in range(1, len(path) - 1):
        a, b, c = pts[-1], path[k], path[k + 1]
        if b[0] != c[0] or b[0] != a[0]:
            pts.append(b)
            continue
        if (b[1] - a[1]) * (c[2] - b[2]) != (b[2] - a[2]) * (c[1] - b[1]):
            pts.append(b)
    pts.append(path[-1])
    return pts


def draw(board, net, path, end, obstacles):
    """Lay a cell path as tracks and vias; the last point snaps to the pad centre `end`."""
    kind, w = cls(net), width(net)
    clear, (vd, vdrill) = CLEAR[kind], VIA[kind]
    net_item = board.FindNet(net)
    coords = [(l, i * G, j * G) for (l, i, j) in simplify(path)]
    coords[-1] = (coords[-1][0], *end)
    for a, b in zip(coords, coords[1:]):
        if a[0] != b[0]:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(mm(OX + a[1]), mm(OY + a[2])))
            v.SetWidth(mm(vd))
            v.SetDrill(mm(vdrill))
            v.SetNet(net_item)
            board.Add(v)
            obstacles.append(Obstacle(net, (0, 1), "seg", (a[1], a[2], a[1], a[2], vd / 2), clear))
            continue
        if (a[1], a[2]) == (b[1], b[2]):
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(OX + a[1]), mm(OY + a[2])))
        t.SetEnd(pcbnew.VECTOR2I(mm(OX + b[1]), mm(OY + b[2])))
        t.SetWidth(mm(w))
        t.SetLayer(LAYERS[a[0]])
        t.SetNet(net_item)
        board.Add(t)
        obstacles.append(Obstacle(net, (a[0],), "seg", (a[1], a[2], b[1], b[2], w / 2), clear))


def fenced_gnd_pads(board):
    """Fill the pours and return the GND pads whose copper reaches the main pour (the largest
    piece) on neither layer, because tracks closed round them on both."""
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    mains = []
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != "GND":
            continue
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not z.IsOnLayer(layer):
                continue
            polys = z.GetFilledPolysList(layer)
            if polys.OutlineCount():
                k = max(range(polys.OutlineCount()), key=lambda i: polys.Outline(i).Area())
                main = pcbnew.SHAPE_POLY_SET()
                main.AddOutline(polys.Outline(k))
                for h in range(polys.HoleCount(k)):
                    main.AddHole(polys.Hole(k, h))
                mains.append(main)
    fenced = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != "GND":
                continue
            reach = int(max(pad.GetSize(pcbnew.F_Cu).x, pad.GetSize(pcbnew.F_Cu).y) * 0.6)
            if not any(m.Collide(pcbnew.VECTOR2I(pad.GetPosition()), reach) for m in mains):
                fenced.append(pad)
    return fenced


def join_fenced_gnd(board, obstacles, centre):
    """Route a GND track from each fenced pad to the nearest GND pad on the main pour."""
    fenced = fenced_gnd_pads(board)
    if not fenced:
        return 0
    def key(p):          # SWIG hands out a new wrapper per call, so compare by name
        return p.GetParentFootprint().GetReference(), p.GetNumber()

    keys = {key(p) for p in fenced}
    good = [p for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == "GND" and key(p) not in keys]
    kind, w = cls("GND"), width("GND")
    half, clear = w / 2, CLEAR[kind]
    gaps = [gap_field(obstacles, "GND", l, clear) for l in (0, 1)]
    free = [gaps[l] >= half + MARGIN for l in (0, 1)]
    step_cost = [np.full((ny, nx), LAYER_COST[kind][l]) for l in (0, 1)]
    via_ok = np.minimum(gaps[0], gaps[1]) >= VIA[kind][0] / 2 + MARGIN
    joined = 0
    for p in fenced:
        start = cell(*centre(p))
        for q in sorted(good, key=lambda q: math.dist(centre(p), centre(q)))[:6]:
            goal = cell(*centre(q))
            for c in (start, goal):
                for l in (0, 1):
                    free[l][c[1], c[0]] = True
            path = astar({(0, *start), (1, *start)}, goal, free, step_cost, via_ok, kind)
            if path:
                draw(board, "GND", path, centre(q), obstacles)
                print(f"joined fenced GND pad {p.GetParentFootprint().GetReference()}.{p.GetNumber()}"
                      f" to {q.GetParentFootprint().GetReference()}.{q.GetNumber()}")
                joined += 1
                break
        else:
            print(f"could not join fenced GND pad {p.GetParentFootprint().GetReference()}.{p.GetNumber()}")
    return joined


# ---------------------------------------------------------------- main
def main():
    board = pcbnew.LoadBoard(PCB)
    for t in list(board.GetTracks()):
        board.Remove(t)

    for z in board.Zones():
        if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
            bb = z.GetBoundingBox()
            KEEPOUTS.append((to_mm(bb.GetLeft()) - OX, to_mm(bb.GetTop()) - OY,
                             to_mm(bb.GetRight()) - OX, to_mm(bb.GetBottom()) - OY))
        elif not z.GetIsRuleArea():
            z.SetThermalReliefSpokeWidth(mm(0.8))

    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    # Tracks squeeze between the DIP pins, so thermal spokes there can starve;
    # the shifter's GND pins get a solid connection to the pour instead.
    for p in board.FindFootprintByReference("U1").Pads():
        if p.GetNetname() == "GND":
            p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    # phi4: the strip terminals' GND pins carry the whole strip current, and the tracks
    # around them starve their thermal spokes; they join the pours solid instead, as do the
    # status LEDs' cathodes (small pads, easy to solder either way).
    if SIZE in ("phi4", "wall"):
        for fp in board.GetFootprints():
            if fp.GetReference() in ("J11", "J12", "J13", "J14", "J15", "J16", "J2") or fp.GetReference().startswith("D"):
                for p in fp.Pads():
                    if p.GetNetname() == "GND":
                        p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    obstacles = [pad_obstacle(p) for p in pads]
    by_net = {}
    for p in pads:
        by_net.setdefault(p.GetNetname(), []).append(p)

    def centre(p):
        q = p.GetPosition()
        return to_mm(q.x) - OX, to_mm(q.y) - OY

    preset_cells = lay_presets(board, obstacles)
    failed = []
    for net in ORDER:
        npads = by_net.get(net, [])
        if len(npads) < 2:
            continue
        kind, w = cls(net), width(net)
        half, clear = w / 2, CLEAR[kind]
        vd, vdrill = VIA[kind]
        gaps = [gap_field(obstacles, net, l, clear) for l in (0, 1)]
        body = body_mask(board, net)
        free, step_cost = [], []
        for l in (0, 1):
            gap = gaps[l]
            free.append(gap >= half + MARGIN)
            # 0 at SOFT mm beyond the hard limit, 1 right at it.
            closeness = np.clip((half + MARGIN + SOFT - gap) / SOFT, 0, 1)
            step_cost.append(LAYER_COST[kind][l] * (1 + SOFT_WEIGHT * closeness ** 2 + BODY_WEIGHT * body))
        via_ok = (np.minimum(gaps[0], gaps[1]) >= vd / 2 + MARGIN) & ~body

        # Each pad's centre node is reachable on both layers (through-hole).
        for p in npads:
            i, j = cell(*centre(p))
            for l in (0, 1):
                free[l][j, i] = True
        # Each net's presets form one connected piece; start the tree from a pad it
        # touches, so every other pad gets routed onto it.
        pre = preset_cells.get(net, set())
        touched = [p for p in npads if any((l, *cell(*centre(p))) in pre for l in (0, 1))]
        start = touched[0] if touched else npads[0]
        npads = [start] + [p for p in npads if p is not start]
        tree = {(l, *cell(*centre(start))) for l in (0, 1)} | pre
        # A pad a preset already reaches counts as part of the tree on both layers.
        for p in npads:
            c = cell(*centre(p))
            if any((l, *c) in tree for l in (0, 1)):
                tree |= {(0, *c), (1, *c)}
        for (l, i, j) in tree:
            free[l][j, i] = True
        todo = npads[1:]
        net_item = board.FindNet(net)
        while todo:
            tx = [(i * G, j * G) for (_, i, j) in tree]
            todo.sort(key=lambda p: min(math.hypot(centre(p)[0] - a, centre(p)[1] - b) for a, b in tx))
            p = todo.pop(0)
            if any((l, *cell(*centre(p))) in tree for l in (0, 1)):
                continue  # already touched (e.g. duplicate fuse pads)
            path = astar(tree, cell(*centre(p)), free, step_cost, via_ok, kind)
            if path is None:
                failed.append(f"{net} -> {p.GetParentFootprint().GetReference()}.{p.GetNumber()}")
                continue
            draw(board, net, path, centre(p), obstacles)
            tree |= set(path)
        print(f"routed {net}")

    # GND stitching vias wherever both layers have room, on a coarse grid,
    # away from part bodies and silkscreen text.
    gfree = np.minimum(gap_field(obstacles, "GND", 0, 0.3), gap_field(obstacles, "GND", 1, 0.3)) >= 0.4 + 0.6
    gfree &= ~body_mask(board, "__no_net__")
    for d in board.GetDrawings():
        if isinstance(d, pcbnew.PCB_TEXT):
            bb = d.GetBoundingBox()
            x0, y0 = to_mm(bb.GetLeft()) - OX - 1.0, to_mm(bb.GetTop()) - OY - 1.0
            x1, y1 = to_mm(bb.GetRight()) - OX + 1.0, to_mm(bb.GetBottom()) - OY + 1.0
            gfree[max(0, int(y0 / G)):int(y1 / G) + 1, max(0, int(x0 / G)):int(x1 / G) + 1] = False
    gnd = board.FindNet("GND")
    stitched = 0
    for y in np.arange(3.81, H - 2.0, 7.62):         # denser than rev 1.0: more pour fragments here
        for x in np.arange(3.81, W - 2.0, 7.62):
            i, j = cell(x, y)
            if gfree[j, i]:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(mm(OX + i * G), mm(OY + j * G)))
                v.SetWidth(mm(0.8))
                v.SetDrill(mm(0.4))
                v.SetNet(gnd)
                board.Add(v)
                stitched += 1
    print(f"stitching vias: {stitched}")
    join_fenced_gnd(board, obstacles, centre)

    pcbnew.SaveBoard(PCB, board)
    if failed:
        print("UNROUTED:", *failed, sep="\n  ")
        sys.exit(1)
    print("all nets routed")


if __name__ == "__main__":
    main()
