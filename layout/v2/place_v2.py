#!/usr/bin/env python3
"""Layout v2, step 1: device placement only (no routing).

    cd layout/v2 && python3 place_v2.py         # side
    cd layout/v2 && python3 place_v2.py top

Places the compact core groups from core_groups.py and the other device cells
from ../build_layout.py (Cc and MPASS reshaped, see V2_RESHAPE) as one rectangle,
in one of two floorplans (see plan()):

  * side: R1/R2 divider | amplifier core column | Miller cap Cc | pass device
  * top:  pass device across the top on the amplifier axis; R1/R2 | core | Cc below
  * snug: core column = the two groups; Rref under Cc in the right column; pass device
          above the core + right columns; R1/R2 beside the pass device
  * core column in signal order from the bottom: Rref -> all NMOS (bias /
    enable row, folded input pair) -> all PMOS (folded load, cascodes +
    switches, MP1), every matched device on one vertical axis
  * the test buffers (RrefEA, bias mirror, followers) sit outside the
    rectangle on the far left; they are not part of the LDO

Writes ldo_v2_place[_top].mag / .gds / .png / .json (placement record).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_layout as bl  # noqa: E402

TOP = "ldo_v2_place"
G_IN = 1.5     # um between devices inside a cluster (same well type)
G_NP = 3.0     # um between NMOS and PMOS (well spacing)

# Compact core groups from core_groups.py (shared rings, tap rows, diffusion sharing,
# common-centroid rows); every other device is a v1 cell from ../build_layout.py.
V2_GROUPS = {"v2_nmos_core": ["MREF_MTAIL", "MPDREF", "MN2", "MENDISCHARGE", "MN1", "MIN1_MIN2"],
             "v2_pmos_core": ["MLOAD1_MLOAD2", "MCASC1_MCASC2", "MENPASSOFF", "MP2", "MBIASSW", "MP1"]}

# Two floorplans (python3 place_v2.py [side|top]); both put the LDO in one rectangle and the
# test buffers outside it, 12 um to the left. Core column, bottom-up: Rref, all NMOS in one
# ring (bias / enable / level-shifter row, tap row, folded input pair), all PMOS but the pass
# device in one n-well (folded load, cascodes + switches, MP1).
#   side: R1/R2 | core | Cc | MPASS (10 rows x 21 fingers), all top-aligned (VIN side).
#   top:  MPASS (3 rows x 70 fingers) across the top, centred on the core axis, with the
#         VIN / VOUT buses above it; below it R1/R2 | core | Cc. The heat source sits on the
#         amplifier's symmetry axis and EAOUT runs straight up from the core to the gate.
FLOORPLAN = sys.argv[1] if len(sys.argv) > 1 else "side"
TOP = "ldo_v2_place" + ("" if FLOORPLAN == "side" else "_" + FLOORPLAN)


CORE_GAP = 1.2   # NMOS ring diffusion to PMOS n-well (DRC sweep: NW.4 / LPW.12 fail at 1.0 um)
G_MP = 4.4       # core column / Cc top to the pass device: a channel for 4 metal4 tracks (snug)
G_LC = 3.2       # R1/R2 to the core column: channel for EAOUT and ENB_5V going down (snug)
G_BUF = 5.0      # test-buffer row to RrefEA: channel for the buffer drains / sources


def core_gap():
    """Bounding-box gap between the NMOS and PMOS groups that leaves CORE_GAP between the
    NMOS ring's diffusion (top) and the PMOS n-well (bottom); negative = boxes overlap."""
    import klayout.db as db
    out = []
    for g_, layer, top in (("v2_nmos_core", (22, 0), True), ("v2_pmos_core", (21, 0), False)):
        lay = db.Layout()
        lay.read(str(HERE / "gl" / f"{g_}.gds"))
        c = lay.top_cell()
        e = c.dbbox_per_layer(lay.find_layer(*layer))
        bb = db.DBox()                       # magic's box: every layer except the DUALGATE margin
        for li in lay.layer_indexes():
            if (lay.get_info(li).layer, lay.get_info(li).datatype) != (55, 0):
                bb += c.dbbox_per_layer(li)
        out.append(bb.top - e.top if top else e.bottom - bb.bottom)
    return CORE_GAP - sum(out)


def plan(sz):
    """Lower-left corner of every cell (um) from the cell sizes sz[inst] = (w, h)."""
    core_h = sz["Rref"][1] + G_IN + sz["v2_nmos_core"][1] + G_NP + sz["v2_pmos_core"][1]
    colw = max(sz[g][0] for g in ("Rref", "v2_nmos_core", "v2_pmos_core"))
    x0 = sz["R1R2"][0] + (G_LC if FLOORPLAN == "snug" else G_NP)   # core column
    axis = x0 + colw / 2                          # the amplifier's symmetry axis
    xc = x0 + colw + G_NP                         # Cc
    if FLOORPLAN == "snug":
        # core column = the two groups only; right column = Rref under Cc; pass device above
        # the core and right columns (from the core column's left edge); R1/R2 left of the
        # pass device, top-aligned with it (in the flipped slot view: next to the VOUT side)
        colw = max(sz[g][0] for g in ("v2_nmos_core", "v2_pmos_core"))
        axis = x0 + colw / 2
        y_nc = 0.0
        y_pc = y_nc + sz["v2_nmos_core"][1] + core_gap()
        col_top = y_pc + sz["v2_pmos_core"][1]
        xr = x0 + colw + G_NP
        y_mp = col_top + G_MP
        p = {"v2_nmos_core": (axis - sz["v2_nmos_core"][0] / 2, y_nc),
             "v2_pmos_core": (axis - sz["v2_pmos_core"][0] / 2, y_pc),
             "Rref": (xr, 0.0),
             "Cc": (xr, col_top - sz["Cc"][1]),
             "MPASS": (x0, y_mp),
             "R1R2": (0.0, y_mp + sz["MPASS"][1] - sz["R1R2"][1])}
    elif FLOORPLAN == "side":
        top_y = max(core_h, sz["Cc"][1], sz["MPASS"][1], sz["R1R2"][1])
        p = {"Cc": (xc, top_y - sz["Cc"][1]), "MPASS": (xc + sz["Cc"][0] + G_NP, top_y - sz["MPASS"][1])}
    else:
        top_y = max(core_h, sz["Cc"][1], sz["R1R2"][1])
        p = {"Cc": (xc, top_y - sz["Cc"][1]), "MPASS": (axis - sz["MPASS"][0] / 2, top_y + G_NP)}
    if FLOORPLAN != "snug":
        y_pc = top_y - sz["v2_pmos_core"][1]
        y_nc = y_pc - core_gap() - sz["v2_nmos_core"][1]
        p.update({
            "R1R2": (0.0, top_y - sz["R1R2"][1]),
            "v2_pmos_core": (axis - sz["v2_pmos_core"][0] / 2, y_pc),
            "v2_nmos_core": (axis - sz["v2_nmos_core"][0] / 2, y_nc),
            "Rref": (axis - sz["Rref"][0] / 2, y_nc - G_IN - sz["Rref"][1]),
        })
    # test buffers, 12 um left of the LDO, centred on it vertically: device row under RrefEA
    ldo = [(x, y, x + sz[k][0], y + sz[k][1]) for k, (x, y) in p.items()]
    ly0, ly1 = min(b[1] for b in ldo), max(b[3] for b in ldo)
    lx0 = min(b[0] for b in ldo)
    row = ("MREFEA_MBIAS", "MPDEA", "MFBBUF", "MEAOUTBUF")
    hb = max(sz[i][1] for i in row)
    wrow = sum(sz[i][0] for i in row) + G_IN * (len(row) - 1)
    wb = max(wrow, sz["RrefEA"][0])
    xb = lx0 - 12.0 - wb
    yb = (ly0 + ly1) / 2 - (hb + G_BUF + sz["RrefEA"][1]) / 2
    p["RrefEA"] = (xb + (wb - sz["RrefEA"][0]) / 2, yb + hb + G_BUF)
    x = xb + (wb - wrow) / 2
    for i in row:
        p[i] = (x, yb + (hb - sz[i][1]) / 2)
        x += sz[i][0] + G_IN
    return p


GROUPS = {
    "Feedback divider": ["R1R2"],
    "Amplifier core + enable / level shifter": ["Rref", "v2_nmos_core", "v2_pmos_core"],
    "Loop output": ["Cc", "MPASS"],
    "Test buffers (not part of the LDO)": ["RrefEA", "MREFEA_MBIAS", "MPDEA", "MFBBUF", "MEAOUTBUF"],
}
LABEL = {"v2_nmos_core": "All NMOS: one p+ ring",
         "v2_pmos_core": "All PMOS (except MPASS): one n-well",
         "MREFEA_MBIAS": "MREFEA/MBIASEA/MBIASFB",
         "R1R2": "R1/R2 divider", "Cc": "Cc 3 pF", "MPASS": "MPASS pass device", "RrefEA": "RrefEA 2 MOhm"}


# v2 shapes of the loop-output devices. Cc keeps its plate area (38.6 x 38.6 = 1490 um^2,
# 3 pF) and MPASS its 210 fingers x 3 um (630 um); only their aspect ratio changes:
#   side: Cc 23.6 x 63.2 plate, MPASS 10 rows x 21 fingers (both as tall as the block)
#   top:  Cc plate as tall as the core column (from gl/groups.json), MPASS 3 rows x 70 fingers
# Added to bl.ROWS as extra entries so the v1 cells stay generated.
def _cc_top():
    """Cc plate as tall as the core column (Rref + NMOS group + PMOS group), same 1490 um^2."""
    import json
    sz = json.loads((HERE / "gl" / "groups.json").read_text())
    h = 13.53 + G_IN + (sz["v2_nmos_core"]["size"][1] - 2) + core_gap() + (sz["v2_pmos_core"]["size"][1] - 2)
    l_ = round((h - 1.2) / 0.05) * 0.05
    return f"w {round(1490.0 / l_ / 0.05) * 0.05:.2f} l {l_:.2f}"


def _cc_snug():
    """Cc plate as tall as the two groups minus Rref (Rref sits under Cc), same 1490 um^2."""
    import json
    sz = json.loads((HERE / "gl" / "groups.json").read_text())
    h = (sz["v2_nmos_core"]["size"][1] - 2) + core_gap() + (sz["v2_pmos_core"]["size"][1] - 2) - 13.53 - G_IN
    l_ = round((h - 1.2) / 0.05) * 0.05
    return f"w {round(1490.0 / l_ / 0.05) * 0.05:.2f} l {l_:.2f}"


_SHAPES = {"side": lambda: ("w 23.6 l 63.2", (21, 10)),       # (Cc plate, MPASS fingers x rows)
           "top": lambda: (_cc_top(), (70, 3)),
           "snug": lambda: (_cc_snug(), (70, 3))}
_CC, _MP = _SHAPES[FLOORPLAN]()
# RrefEA (test-buffer bias, 1944 um of 1 um poly): 30 longer segments instead of 40, so the
# test-buffer cluster is nearly as tall as the LDO and as wide as its device row (same length,
# so the same resistance -- res() compensates the bends)
RREFEA_NX = 30
V2_RESHAPE = {"Cc": ("cap", (bl.CAP, _CC), dict(TOP="EAOUT", BOT="VOUT")),
              "RrefEA": ("res", bl.res(1, 1944.26, RREFEA_NX), dict(A="IREF_EA", B="VIN_BIAS", BULK="VSS")),
              "MPASS": ("gl", bl.fet("pmos", 3, 0.55, _MP[0], mult=_MP[1]), dict(D="VOUT", G="EAOUT", S="VIN", B="VIN"))}


def main():
    bl.ROWS.append([(k + "_v2", *v) for k, v in V2_RESHAPE.items()])
    cells, _ = bl.gen_devices()
    info = {}
    grouped = {d for v in V2_GROUPS.values() for d in v}
    (HERE / "mag").mkdir(exist_ok=True)
    tcl = HERE / "mag" / "_read.tcl"
    # read-only: magic keeps gLayout's GDS for these cells when writing GDS (regenerating the
    # implants from its own layers leaves NP.1 notches at the ring corners)
    tcl.write_text("gds readonly true\n" + "".join(f"gds read ../gl/{g}.gds\n" for g in V2_GROUPS)
                   + "writeall force\nquit -noprompt\n")
    subprocess.run([bl.MAGIC, "-dnull", "-noconsole", "-rcfile", bl.RC, tcl.name], cwd=HERE / "mag",
                   stdin=subprocess.DEVNULL, capture_output=True, text=True)
    tcl.unlink()
    for g in V2_GROUPS:
        r, props = bl.parse_mag(HERE / "mag" / f"{g}.mag")
        info[g] = (g, bl.bbox([x for v in r.values() for x in v]), props)
    for row in bl.ROWS:
        for inst, kind, spec, nets in row:
            if inst in grouped or inst in V2_RESHAPE:
                continue
            if inst.endswith("_v2"):
                inst = inst[:-3]
                c = cells[inst + "_v2"]
            else:
                c = cells[inst]
            if kind == "resarray":
                _, bb = bl.make_res_array(c[1])
                name = c[0]
                props = bl.parse_mag(bl.MAG / f"{name}.mag")[1]
            else:
                name = c
                r, props = bl.parse_mag(bl.MAG / f"{name}.mag")
                bb = bl.bbox([x for v in r.values() for x in v])
            info[inst] = (name, bb, props)
    PLACE = plan({i: ((v[1][2] - v[1][0]) / bl.UM, (v[1][3] - v[1][1]) / bl.UM) for i, v in info.items()})
    assert set(info) == set(PLACE), set(info) ^ set(PLACE)

    # shift so every device sits at x, y >= 2 um
    dx = 2.0 - min(x for x, y in PLACE.values())
    dy = 2.0 - min(y for x, y in PLACE.values())
    boxes = {}
    s = ["magic", f"tech {bl.PDK}", "magscale 1 10", "timestamp 0"]
    for inst, (x, y) in PLACE.items():
        name, bb, props = info[inst]
        tx, ty = bl.um(x + dx) - bb[0], bl.um(y + dy) - bb[1]
        boxes[inst] = (tx + bb[0], ty + bb[1], tx + bb[2], ty + bb[3])
        fb = props.get("FIXED_BBOX", " ".join(map(str, bb)))
        s += [f"use {name}  {inst}", f"timestamp {props.get('timestamp', '0')}",
              f"transform 1 0 {tx} 0 1 {ty}", f"box {fb}"]
    s.append("<< end >>")
    # placement record for ratsnest.py: cell box and cell origin of every instance, in um
    import json
    (HERE / f"{TOP}.json").write_text(json.dumps({inst: dict(
        cell=info[inst][0], box=[round(v / bl.UM, 3) for v in boxes[inst]],
        origin=[round((boxes[inst][0] - info[inst][1][0]) / bl.UM, 3), round((boxes[inst][1] - info[inst][1][1]) / bl.UM, 3)])
        for inst in boxes}, indent=1) + "\n")
    (HERE / f"{TOP}.mag").write_text("\n".join(s) + "\n")

    # spacing report: overlaps and closest neighbours
    names = list(boxes)
    worst = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = boxes[a], boxes[b]
            gx = max(B[0] - A[2], A[0] - B[2])
            gy = max(B[1] - A[3], A[1] - B[3])
            gap = max(gx, gy) / bl.UM
            worst.append((gap, a, b))
    worst.sort()
    print("closest device pairs (bbox gap, um):")
    for g, a, b in worst[:8]:
        print(f"  {g:6.2f}  {a} - {b}{'   OVERLAP' if g < 0 and {a, b} != {'v2_nmos_core', 'v2_pmos_core'} else ''}")
    allb = list(boxes.values())
    W = (max(b[2] for b in allb) + bl.um(2)) / bl.UM
    H = (max(b[3] for b in allb) + bl.um(2)) / bl.UM
    print(f"placement extent {W:.1f} x {H:.1f} um")
    ldo = [boxes[m] for t, ms in GROUPS.items() if not t.startswith("Test buffers") for m in ms]
    print("LDO rectangle (without test buffers) {:.1f} x {:.1f} um".format(
        (max(b[2] for b in ldo) - min(b[0] for b in ldo)) / bl.UM, (max(b[3] for b in ldo) - min(b[1] for b in ldo)) / bl.UM))

    tcl = HERE / "_gds.tcl"
    tcl.write_text(f"addpath ../mag\naddpath mag\nload {TOP}\nselect top cell\ngds write {TOP}.gds\nquit -noprompt\n")
    subprocess.run([bl.MAGIC, "-dnull", "-noconsole", "-rcfile", bl.RC, tcl.name], cwd=HERE,
                   stdin=subprocess.DEVNULL, capture_output=True, text=True)
    tcl.unlink()
    render(boxes, W, H)


def render(boxes, W, H):
    import klayout.db as db
    import klayout.lay as lay
    ann = db.Layout()
    ann.dbu = 0.001
    top = ann.create_cell("ann")
    L_grp, L_txt, L_gtxt = ann.layer(200, 0), ann.layer(201, 0), ann.layer(202, 0)
    k = 1000 // bl.UM          # magic units -> nm
    for title, members in GROUPS.items():
        bs = [boxes[m] for m in members]
        x1, y1 = min(b[0] for b in bs) * k - 1200, min(b[1] for b in bs) * k - 1200
        x2, y2 = max(b[2] for b in bs) * k + 1200, max(b[3] for b in bs) * k + 1200
        top.shapes(L_grp).insert(db.Path([db.Point(x1, y1), db.Point(x2, y1), db.Point(x2, y2),
                                          db.Point(x1, y2), db.Point(x1, y1)], 250))
        top.shapes(L_gtxt).insert(db.Text(title, db.Trans(db.Point(x1, y2 + 900))))
    for inst, b in boxes.items():
        lab = LABEL.get(inst, inst).replace("\n", " ")
        top.shapes(L_txt).insert(db.Text(lab, db.Trans(db.Point(b[0] * k, b[3] * k + 350))))
    ann.write(str(HERE / "_ann.gds"))
    v = lay.LayoutView()
    v.load_layout(str(HERE / f"{TOP}.gds"), 0)
    v.load_layer_props("/foss/pdks/gf180mcuD/libs.tech/klayout/tech/gf180mcu.lyp")
    v.load_layout(str(HERE / "_ann.gds"), True)
    for ln, col, w in ((200, 0x0060d0, 2), (201, 0x000000, 1), (202, 0x0040a0, 1)):
        p = lay.LayerPropertiesNode()
        p.source = f"{ln}/0@2"
        p.frame_color = p.fill_color = col
        p.width = w
        v.insert_layer(v.end_layers(), p)
    v.max_hier()
    v.set_config("background-color", "#ffffff")
    v.set_config("default-text-size", "1.4")
    v.zoom_box(db.DBox(-3, -3, W + 3, H + 8))
    v.save_image(str(HERE / f"{TOP}.png"), 2400, int(2400 * (H + 11) / (W + 6)))
    (HERE / "_ann.gds").unlink()


if __name__ == "__main__":
    main()
