#!/usr/bin/env python3
"""Generate the LDO transistors with gLayout and convert them to 5/6 V devices.

Run by build_layout.py under the gLayout Python environment:
    glpy gl_devices.py <spec.json> <outdir>

spec.json: {cellname: {"type": nmos|pmos|npair|ppair|nmatch|pmatch, "w", "l", "nf", "numcols", "pattern", "v5"}}
(nmatch/pmatch: matched pair with unit fingers in "pattern", e.g. ABBA, plus end dummies)
For each cell this writes <outdir>/<cellname>.gds (flat, DUALGATE drawn around
the device, V5_XTOR too for 5 V devices, 1 nm database unit) and collects the
terminal bars into <outdir>/terms.json: {cellname: {terminal: [xl, xr, y]}} in
microns. All bars are metal2, 0.5 um tall. Terminals: G, S, D, B for single
devices; A_G, A_S, A_D, B_G, B_S, B_D, B for interdigitated pairs (B = bulk tap).

gLayout's gf180 setup only draws 3.3 V devices; adding the DUALGATE (55/0) and
V5_XTOR (112/1) markers turns them into pfet_06v0 / nfet_06v0 / nfet_05v0, and
its default spacing already meets the 6 V rules (checked with the KLayout deck).
"""
import json
import sys
from pathlib import Path

import gdsfactory as gf
import klayout.db as db
from glayout import gf180, nmos, pmos
from glayout.placement.two_transistor_interdigitized import (two_nfet_interdigitized,
                                                             two_pfet_interdigitized)
from glayout.primitives.fet import multiplier
from glayout.primitives.guardring import tapring
from glayout.routing.straight_route import straight_route
from glayout.util.comp_utils import evaluate_bbox, prec_ref_center
from glayout.util.port_utils import rename_ports_by_list, rename_ports_by_orientation
from glayout.backend import Component, transformed

DUALGATE, V5_XTOR, MARGIN = (55, 0), (112, 1), 1.0


def pattern_pair(pdk, pattern, nfet, width, length):
    """Matched devices (letters A, B, C...) in one row, unit fingers placed in
    `pattern` (e.g. "ABBA", "BACCAB" = common centroid in one dimension), one
    dummy finger at each end tied to the bulk ring. Derived from gLayout's
    macro_two_transistor_interdigitized, which only does ABAB for two devices.
    Each device's source/drain/gate bars sit one level further out than the
    previous letter's. Exports <letter>_source/_drain/_gate bars and the ring."""
    sdlayer = "n+s/d" if nfet else "p+s/d"
    letters = sorted(set(pattern))
    base = dict(pdk=pdk, width=width, length=length, fingers=1, sdlayer=sdlayer,
                sd_route_extension=0, gate_route_extension=0)
    unit0 = multiplier(**base, dummy=False)
    ext_sd = pdk.snap_to_2xgrid(pdk.util_max_metal_seperation()
                                + abs(unit0.ports["drain_N"].center[1] - unit0.ports["diff_N"].center[1]))
    ext_g = pdk.snap_to_2xgrid(pdk.util_max_metal_seperation()
                               + abs(unit0.ports["row0_col0_gate_S"].center[1] - unit0.ports["gate_S"].center[1]))
    kinds = {}
    def unit(d, dummy):
        if (d, dummy) not in kinds:
            lvl = letters.index(d)
            kinds[(d, dummy)] = multiplier(**dict(base, dummy=dummy, sd_route_extension=lvl * ext_sd,
                                                  gate_route_extension=lvl * ext_g))
        return kinds[(d, dummy)]
    n = len(pattern)
    comp = Component()
    xdisp = pdk.snap_to_2xgrid(evaluate_bbox(unit0)[0] + pdk.get_grule("active_diff")["min_separation"])
    refs, count = [], {d: 0 for d in letters}
    for i, d in enumerate(pattern):
        dummy = (True, False) if i == 0 else (False, True) if i == n - 1 else False
        r = comp << unit(d, dummy)
        r.movex(i * xdisp)
        comp.add_ports(r.get_ports_list(), prefix=f"{d}_{count[d]}_")
        count[d] += 1
        refs.append((d, r))
    first = {d: next(r for e, r in refs if e == d) for d in letters}
    top = first[letters[-1]]            # outermost bar level
    for d, r in refs:   # bring every unit's source/drain up past the bar levels; equalise gate poly
        lay = pdk.layer_to_glayer(r.ports["row0_col0_rightsd_top_met_N"].layer)
        comp << straight_route(pdk, r.ports["row0_col0_rightsd_top_met_N"], top.ports["drain_E"], glayer2=lay)
        comp << straight_route(pdk, r.ports["leftsd_top_met_N"], top.ports["drain_E"], glayer2=lay)
        if d != letters[-1]:
            comp << straight_route(pdk, r.ports["row0_col0_gate_S"], top.ports["gate_E"], glayer2="poly")
    left, right = refs[0][1], refs[-1][1]
    comp << straight_route(pdk, left.ports["plusdoped_W"], right.ports["plusdoped_E"])
    for d in letters:
        for name in ("source", "drain", "gate"):
            rb = comp << rename_ports_by_orientation(rename_ports_by_list(
                straight_route(pdk, first[d].ports[f"{name}_W"], right.ports[f"{name}_E"]), [("route_", "_")]))
            comp.add_ports(rb.get_ports_list(), prefix=f"{d}_{name}")
    centred = transformed(prec_ref_center(comp))
    comp = Component()          # fresh (uncached) component to add the ring to
    comp.add_ports((comp << centred).get_ports_list())
    # bulk tap ring, dummies tied to it
    sep = max(pdk.util_max_metal_seperation(), pdk.get_grule("active_diff", "active_tap")["min_separation"])
    sep += pdk.get_grule(sdlayer, "active_tap")["min_enclosure"]
    ring = comp << tapring(pdk, enclosed_rectangle=(2 * (sep + comp.xmax), 2 * (sep + comp.ymax)),
                           sdlayer="p+s/d" if nfet else "n+s/d", horizontal_glayer="met2", vertical_glayer="met1")
    comp.add_ports(ring.get_ports_list(), prefix="welltie_")
    dl, dr = f"{pattern[0]}_0_dummy_L_gsdcon_top_met_W", f"{pattern[-1]}_{count[pattern[-1]] - 1}_dummy_R_gsdcon_top_met_E"
    comp << straight_route(pdk, comp.ports[dl], comp.ports["welltie_W_top_met_W"], glayer2="met1")
    comp << straight_route(pdk, comp.ports[dr], comp.ports["welltie_E_top_met_E"], glayer2="met1")
    well = "pwell" if nfet else "nwell"
    comp.add_padding(layers=(pdk.get_glayer(well),), default=pdk.get_grule(well, "active_tap")["min_enclosure"])
    return comp


def build(spec):
    t, w, l = spec["type"], spec["w"], spec["l"]
    if t == "nmos":
        return nmos(gf180, width=w, length=l, fingers=spec["nf"], multipliers=1,
                    with_dummy=False, with_dnwell=False, with_substrate_tap=False)
    if t == "pmos":
        return pmos(gf180, width=w, length=l, fingers=spec["nf"], multipliers=spec.get("mult", 1),
                    with_dummy=False, with_substrate_tap=False)
    if t in ("nmatch", "pmatch"):
        return pattern_pair(gf180, spec["pattern"], t == "nmatch", w, l)
    pair = two_nfet_interdigitized if t == "npair" else two_pfet_interdigitized
    return pair(gf180, numcols=spec["numcols"], dummy=False, with_substrate_tap=False,
                width=w, length=l, fingers=1)


def bar(comp, name):
    e, w = comp.ports[f"{name}_E"], comp.ports[f"{name}_W"]
    assert tuple(e.layer) == (36, 0), f"{name} is not on metal2"
    return [round(float(w.center[0]), 3), round(float(e.center[0]), 3), round(float(e.center[1]), 3)]


def terminals(comp, t, spec):
    if t in ("nmos", "pmos") and spec.get("mult", 1) > 1:
        # multi-row block: every row's own source / drain bar (S0.., D0..), the
        # bottom row's gate bar (rows are joined inside the block) and the bulk tap
        tb = {}
        for i in range(spec["mult"]):
            tb[f"S{i}"] = bar(comp, f"multiplier_{i}_source")
            tb[f"D{i}"] = bar(comp, f"multiplier_{i}_drain")
        tb["G"] = bar(comp, "multiplier_0_gate")
        tb["B"] = bar(comp, "tie_S_top_met")
    elif t in ("nmos", "pmos"):
        tb = {k: bar(comp, n) for k, n in (("G", "gate"), ("S", "source"), ("D", "drain"))}
        tb["B"] = bar(comp, "tie_S_top_met")
    else:
        devs = sorted(set(spec["pattern"])) if "pattern" in spec else "AB"
        tb = {f"{d}_{k}": bar(comp, f"{d}_{n}") for d in devs
              for k, n in (("G", "gate"), ("S", "source"), ("D", "drain"))}
        tb["B"] = bar(comp, "welltie_S_top_met")
    return tb


def write_hv(comp, name, path, v5):
    c = gf.Component(name + "_wrap")
    r = c << comp
    (x0, y0), (x1, y1) = r.bbox
    box = [(x0 - MARGIN, y0 - MARGIN), (x1 + MARGIN, y0 - MARGIN), (x1 + MARGIN, y1 + MARGIN), (x0 - MARGIN, y1 + MARGIN)]
    c.add_polygon(box, layer=DUALGATE)
    if v5:
        c.add_polygon(box, layer=V5_XTOR)
    c = c.flatten()
    raw = path.with_suffix(".raw.gds")
    c.write_gds(raw)
    lay = db.Layout()
    lay.read(str(raw))
    lay.top_cell().name = name
    opt = db.SaveLayoutOptions()
    opt.dbu = 0.001
    lay.write(str(path), opt)
    raw.unlink()


def main():
    specs = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    terms_f = out / "terms.json"
    terms = json.loads(terms_f.read_text()) if terms_f.exists() else {}
    for name, spec in specs.items():
        comp = build(spec)
        terms[name] = terminals(comp, spec["type"], spec)
        write_hv(comp, name, out / f"{name}.gds", spec["v5"])
        print("GL", name, flush=True)
    terms_f.write_text(json.dumps(terms, indent=1) + "\n")


if __name__ == "__main__":
    main()
