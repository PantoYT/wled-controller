"""Write the simple coloured STEP boxes used by the ESP32 DevKit stand-in model.

Plain Python, no dependencies:
    python 3d/make_boxes.py

Each box is a single solid with its origin at the centre of its bottom face,
so a model offset in KiCad places it exactly where its footprint says.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# name: (size x, size y, size z in mm, colour RGB 0-1)
BOXES = {
    "devkit_pcb": (28.5, 52.0, 1.6, (0.06, 0.06, 0.07)),
    "usb_c": (8.94, 7.35, 3.16, (0.78, 0.79, 0.80)),
    "button": (6.0, 3.5, 3.5, (0.86, 0.86, 0.86)),
    "button_cap": (2.0, 1.4, 0.8, (0.10, 0.10, 0.10)),
    "ch340": (6.0, 10.0, 1.6, (0.12, 0.12, 0.13)),
    "ldo": (6.5, 3.5, 1.6, (0.12, 0.12, 0.13)),
    "led": (1.6, 0.8, 0.6, (0.95, 0.20, 0.20)),
    "header_spacer": (2.54, 38.1, 2.5, (0.08, 0.08, 0.08)),
    # 3 A mini blade fuses are violet.
    "fuse_mini": (10.9, 3.6, 9.0, (0.55, 0.30, 0.80)),
}


def box_step(name, sx, sy, sz, rgb):
    ents = []

    def add(text):
        ents.append(text)
        return f"#{len(ents)}"

    def pt(x, y, z):
        return add(f"CARTESIAN_POINT('',({x:.4f},{y:.4f},{z:.4f}))")

    def dr(x, y, z):
        return add(f"DIRECTION('',({x:.1f},{y:.1f},{z:.1f}))")

    x0, x1, y0, y1, z0, z1 = -sx / 2, sx / 2, -sy / 2, sy / 2, 0.0, sz
    coord = {(i, j, k): ((x0, x1)[i], (y0, y1)[j], (z0, z1)[k])
             for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    verts = {c: add(f"VERTEX_POINT('',{pt(*p)})") for c, p in coord.items()}

    edges = {}

    def edge(a, b):
        key = tuple(sorted((a, b)))
        if key not in edges:
            s, e = key
            ps, pe = coord[s], coord[e]
            d = [pe[n] - ps[n] for n in range(3)]
            length = max(abs(v) for v in d)
            u = dr(*[v / length for v in d])
            line = add(f"LINE('',{pt(*ps)},{add(f'VECTOR({chr(39)}{chr(39)},{u},{length:.4f})')})")
            edges[key] = add(f"EDGE_CURVE('',{verts[s]},{verts[e]},{line},.T.)")
        same = (a, b) == tuple(sorted((a, b)))
        return add(f"ORIENTED_EDGE('',*,*,{edges[tuple(sorted((a, b)))]},{'.T.' if same else '.F.'})")

    # Corner order is counter-clockwise seen from outside, so normals point out.
    faces_def = [
        ([(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)], (0, 0, -1), (1, 0, 0)),
        ([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], (0, 0, 1), (1, 0, 0)),
        ([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], (0, -1, 0), (1, 0, 0)),
        ([(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)], (0, 1, 0), (1, 0, 0)),
        ([(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)], (-1, 0, 0), (0, 1, 0)),
        ([(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], (1, 0, 0), (0, 1, 0)),
    ]
    faces = []
    for corners, normal, ref in faces_def:
        oes = [edge(corners[k], corners[(k + 1) % 4]) for k in range(4)]
        loop = add(f"EDGE_LOOP('',({','.join(oes)}))")
        bound = add(f"FACE_OUTER_BOUND('',{loop},.T.)")
        axis = add(f"AXIS2_PLACEMENT_3D('',{pt(*coord[corners[0]])},{dr(*normal)},{dr(*ref)})")
        plane = add(f"PLANE('',{axis})")
        faces.append(add(f"ADVANCED_FACE('',({bound}),{plane},.T.)"))
    shell = add(f"CLOSED_SHELL('',({','.join(faces)}))")
    brep = add(f"MANIFOLD_SOLID_BREP('{name}',{shell})")

    length = add("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
    angle = add("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
    solid = add("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
    unc = add(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),{length},"
              "'distance_accuracy_value','confusion accuracy')")
    ctx = add(f"( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({unc})) "
              f"GLOBAL_UNIT_ASSIGNED_CONTEXT(({length},{angle},{solid})) "
              "REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY') )")
    origin = add(f"AXIS2_PLACEMENT_3D('',{pt(0, 0, 0)},{dr(0, 0, 1)},{dr(1, 0, 0)})")
    rep = add(f"ADVANCED_BREP_SHAPE_REPRESENTATION('',({origin},{brep}),{ctx})")

    app = add("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
    add(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,{app})")
    pctx = add(f"PRODUCT_CONTEXT('',{app},'mechanical')")
    prod = add(f"PRODUCT('{name}','{name}','',({pctx}))")
    add(f"PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,({prod}))")
    form = add(f"PRODUCT_DEFINITION_FORMATION('','',{prod})")
    dctx = add(f"PRODUCT_DEFINITION_CONTEXT('part definition',{app},'design')")
    pdef = add(f"PRODUCT_DEFINITION('design','',{form},{dctx})")
    pshape = add(f"PRODUCT_DEFINITION_SHAPE('','',{pdef})")
    add(f"SHAPE_DEFINITION_REPRESENTATION({pshape},{rep})")

    colour = add(f"COLOUR_RGB('',{rgb[0]:.3f},{rgb[1]:.3f},{rgb[2]:.3f})")
    fill_c = add(f"FILL_AREA_STYLE_COLOUR('',{colour})")
    fill = add(f"FILL_AREA_STYLE('',({fill_c}))")
    sfill = add(f"SURFACE_STYLE_FILL_AREA({fill})")
    side = add(f"SURFACE_SIDE_STYLE('',({sfill}))")
    usage = add(f"SURFACE_STYLE_USAGE(.BOTH.,{side})")
    psa = add(f"PRESENTATION_STYLE_ASSIGNMENT(({usage}))")
    styled = add(f"STYLED_ITEM('color',({psa}),{brep})")
    add(f"MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION('',({styled}),{ctx})")

    body = "\n".join(f"#{n + 1}={t};" for n, t in enumerate(ents))
    return ("ISO-10303-21;\nHEADER;\n"
            f"FILE_DESCRIPTION(('{name}'),'2;1');\n"
            f"FILE_NAME('{name}.step','2026-10-02T00:00:00',(''),(''),'make_boxes.py','','');\n"
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\n"
            f"ENDSEC;\nDATA;\n{body}\nENDSEC;\nEND-ISO-10303-21;\n")


if __name__ == "__main__":
    for name, (sx, sy, sz, rgb) in BOXES.items():
        with open(os.path.join(HERE, name + ".step"), "w", encoding="ascii", newline="\n") as f:
            f.write(box_step(name, sx, sy, sz, rgb))
        print("wrote", name + ".step")
