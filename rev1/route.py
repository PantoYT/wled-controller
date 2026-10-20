"""Route wled-controller.kicad_pcb: a grid A* router tuned for tidy two-layer THT boards.

Run with KiCad's bundled Python, on the unrouted board:
    cp wled-controller.unrouted.kicad_pcb wled-controller.kicad_pcb
    "C:/Program Files/KiCad/10.0/bin/python.exe" route.py
    kicad-cli pcb drc --refill-zones --save-board wled-controller.kicad_pcb

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
import heapq
import math
import os
import sys

import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "wled-controller.kicad_pcb")

OX, OY = 100.0, 100.0          # board origin on the sheet (matches gen_board.py)
W, H, CORNER_R = 100.0, 61.8, 2.0
EDGE_CLEAR = 0.5
G = 1.27 / 4                   # routing grid, mm
MARGIN = 0.1                   # extra clearance so diagonal steps never cut a corner

POWER = {"VIN_RAW": 1.5, "+5V": 1.5, "+3V3": 1.0}
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
ORDER = ["VIN_RAW", "+5V", "+3V3", "ESP_D4",
         "DATA1_RAW", "DATA2_RAW", "DATA3_RAW", "DATA4_RAW",
         "DATA1", "DATA2", "DATA3", "DATA4"]

KEEPOUTS = []                  # filled from rule areas: (x0, y0, x1, y1)

# Hand-drawn routes, laid down before the router runs; it only joins whatever is
# left (here: +3V3) onto them. Built from the real pad positions, so moving a part
# in gen_board.py moves its routes with it. Layer 0 = F.Cu, 1 = B.Cu, "via" = via.


def build_presets(board):
    def pad(ref, num, k=0):
        ps = [p for p in board.FindFootprintByReference(ref).Pads() if p.GetNumber() == str(num)]
        q = ps[k].GetPosition()
        return round(to_mm(q.x) - OX, 3), round(to_mm(q.y) - OY, 3)

    def u1(pin):
        return pad("U1", pin)

    mid = (u1(14)[1] + u1(1)[1]) / 2                       # channel between U1's rows
    jack, j4, j3, j2 = pad("J1", 1), pad("J4", 1), pad("J3", 1), pad("J2", 2)
    fuse1, fuse1b, fuse2, fuse2b = pad("F1", 1, 0), pad("F1", 1, 1), pad("F1", 2, 0), pad("F1", 2, 1)
    jst_p, jst_d = pad("J5", 1), pad("J5", 2)
    vin, c1, c3, u14 = pad("U3", 1), pad("C1", 1), pad("C3", 1), u1(14)
    s_top, s_bot = pad("J6", 3), pad("J6", 1)
    pins = [pad("J16", n) for n in range(1, 8)]
    trunk = jst_p[1]                                          # +5V bus level = MAIN JST +
    step = 1.27

    return {
        # Inputs meet at fuse pad 1 on the top; the screw terminal comes round under
        # the fuse on the bottom. The holder's two pad-1 clips are tied in copper.
        "VIN_RAW": [
            (0, [jack, (jack[0] + 2.4, jack[1]), (jack[0] + 2.4 + fuse1[1] - jack[1], fuse1[1]), fuse1]),
            (0, [j4, (j4[0], fuse1[1])]),
            (0, [j3, (j3[0] - (fuse1[1] - j3[1]), fuse1[1]), fuse1]),
            (0, [fuse1, fuse1b]),
            (1, [j2, (j2[0], 13.97 - step), (j2[0] - step, 13.97),
                 (fuse1b[0] + 13.97 - fuse1b[1] - 0.74, 13.97), (fuse1b[0], fuse1b[1] + 0.74), fuse1b]),
        ],
        # One bus along the top at MAIN JST level: fuse -> JST + -> screw + block.
        # A straight drop to C1 +, crossed by the VIN -> C3 -> U1 pin 14 run; the JST + pad also
        # feeds the solder + column and, round the bottom, the pin header.
        "+5V": [
            (0, [fuse2, fuse2b, (fuse2b[0] + trunk - fuse2b[1], trunk),
                 (s_top[0] - (s_top[1] - trunk), trunk), s_top, s_bot]),
            (0, [(c1[0], trunk), c1]),                       # straight drop to C1 +
            (0, [vin, (c3[0] - (c3[1] - vin[1]), vin[1]), c3, u14]),
            (0, [jst_p, (jst_p[0], 52.07), (jst_p[0] - step, 53.34), (64.77, 53.34), (63.5, 54.61),
                 (63.5, pins[0][1] - step), (64.77, pins[0][1]), pins[2]]),
        ],
        # GPIO4 goes round the ESP32 (left, under, up the right) on the bottom, then a
        # via and a comb on the top: one bus down the middle of U1, a stub per input.
        "ESP_D4": [
            (1, [pad("U2", 5), (11.43, 29.21), (10.16, 30.48), (10.16, 55.245), (11.43, 56.515),
                 (39.37, 56.515), (40.64, 55.245), (40.64, 30.48), (41.91, mid), (48.26, mid)]),
            ("via", (48.26, mid)),
            (0, [(48.26, mid), (u1(2)[0], mid), (u1(9)[0], mid)]),
        ] + [(0, [u1(p), (u1(p)[0], mid)]) for p in (2, 5, 9, 12)],
        # Shifter outputs: pins 3 and 6 straight down to R2 and R3; pin 11 round the
        # left end of the chip to R1 (bottom), pin 8 round the right end to R4 (top).
        "DATA2_RAW": [(1, [u1(3), pad("R2", 1)])],
        "DATA4_RAW": [(1, [u1(6), pad("R3", 1)])],
        "DATA3_RAW": [(1, [u1(11), (u1(11)[0], 24.765), (u1(11)[0] - step, 23.495), (50.8, 23.495),
                           (49.53, 24.765), (49.53, 34.29), pad("R1", 1)])],
        "DATA1_RAW": [(0, [u1(8), (u1(8)[0] + step, u1(8)[1]), (70.485, u1(8)[1] + 1.905),
                           (70.485, pad("R4", 1)[1] - 1.905), pad("R4", 1)])],
        # Resistor outputs, all on the bottom: R4 -> MAIN JST, R3 -> solder D,
        # R2 -> screw D, R1 -> pin header D (above the header, away from the edge).
        "DATA1": [(1, [pad("R4", 2), (72.39, pad("R4", 2)[1]), (73.66, pad("R4", 2)[1] - step),
                       (73.66, jst_d[1] + step), (73.66 + step, jst_d[1]), jst_d])],
        "DATA4": [(1, [pad("R3", 2), (pad("R3", 2)[0] + 2 * step, 50.8),
                       (pad("J9", 1)[0] - 2 * step, 50.8), pad("J9", 1)])],
        "DATA2": [(1, [pad("R2", 2), (63.5, 54.61), (85.09, 54.61), (86.36, 55.88), (86.36, 57.15),
                       (87.63, 58.42), pad("J8", 1)])],
        "DATA3": [(1, [pad("R1", 2), (pad("R1", 2)[0], 54.94), (pad("R1", 2)[0] + step, 56.21),
                       (pins[3][0] - 0.635, 56.21), (pins[3][0], 56.845), pins[3]])],
    }


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
    return Obstacle(net, (0, 1), "rrect", (x0, y0, x1, y1, r), CLEAR[cls(net)] if net else 0.25)


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
            pts = simplify(path)
            cx, cy = centre(p)
            coords = [(l, i * G, j * G) for (l, i, j) in pts]
            coords[-1] = (coords[-1][0], cx, cy)
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
    for y in np.arange(5.08, H - 2.0, 10.16):
        for x in np.arange(5.08, W - 2.0, 10.16):
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

    pcbnew.SaveBoard(PCB, board)
    if failed:
        print("UNROUTED:", *failed, sep="\n  ")
        sys.exit(1)
    print("all nets routed")


if __name__ == "__main__":
    main()
