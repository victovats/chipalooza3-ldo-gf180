#!/usr/bin/env python3
"""EM / IR check of the extracted v2 LDO layout.

    cd layout/pex && python3 emir_check.py

Same method as ../../layout_v1/pex/emir_check.py (v1):
IR drop: a DC operating point of the RC-extracted netlist (ldo_pex_rc.spice) at
the worst current condition (VIN = 5 V, EN on, 10 mA load); extresist splits each
power net into resistor segments, and every segment node is compared with the
net's pin.
EM: the current in each element of the high-current path is checked against the
GF180MCU design-manual limits (section 14.2, DC unidirectional, 110 C):
    metal1-4  1.0 mA per um of width;  metal5  2.2 mA per um;  via1-4  0.28 mA per via
The load current is assumed to split evenly between the pass-device straps, with
IMBALANCE extra margin. Strap and bus sizes are the ones route_v2.py draws; the
via cuts per strap per row are counted in the GDS.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
sys.path.insert(0, str(V2))
import build_layout as bl  # noqa: E402

PDK = "/foss/pdks/gf180mcuD/libs.tech/ngspice"
ILOAD = 10e-3
LIMIT = {"m1-4": 1.0e-3, "m5": 2.2e-3, "via": 0.28e-3}
IMBALANCE = 1.2
STRAP_W, STRAP_PITCH, BUS_W = 2.6, 3.2, 6.0          # route_v2.py: SW, SPP, BUS


def run_op():
    pins = re.search(r"(?m)^\.subckt ldo_flat (.*)$", (HERE / "ldo_pex_rc.spice").read_text()).group(1)
    deck = f"""* EM/IR operating point: RC-extracted v2 LDO at full load
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice typical
.lib {PDK}/sm141064.ngspice res_typical
.lib {PDK}/sm141064.ngspice cap_mim
.lib {PDK}/sm141064.ngspice mimcap_typical
.include ldo_pex_rc.spice
x1 {pins} ldo_flat
Vvin VIN 0 5
Vvss VSS 0 0
Vvref VREF 0 1.2
Ven EN 0 3.3
Iload VOUT 0 {ILOAD}
.control
op
print all > emir_op.txt
print i(vvin) i(vvss) > emir_i.txt
.endc
.end
"""
    (HERE / "emir_op.spice").write_text(deck)
    subprocess.run([shutil.which("ngspice") or "/foss/tools/ngspice/bin/ngspice", "-b", "emir_op.spice"], cwd=HERE,
                   capture_output=True, text=True)
    v = {}
    for name, val in re.findall(r"(?m)^(\S+)\s*=\s*(\S+)", (HERE / "emir_op.txt").read_text()):
        try:
            v[name.lower()] = float(val)
        except ValueError:
            pass
    i = dict(re.findall(r"(?m)^(i\(\S+\))\s*=\s*(\S+)", (HERE / "emir_i.txt").read_text()))
    return v, {k: float(x) for k, x in i.items()}


def ir_report(v):
    print("IR drop at 10 mA load (largest difference between a net's pin and any point on it)")
    for net in ("vin", "vout", "vss"):
        pin = v[net]
        nodes = {k: x for k, x in v.items() if re.match(rf"x1\.{net}\.[nt]\d+$", k)}
        if not nodes:
            continue
        worst = max(nodes, key=lambda k: abs(nodes[k] - pin))
        print(f"  {net.upper():5s} pin {pin:8.5f} V   {len(nodes):4d} segment nodes   "
              f"worst drop {abs(nodes[worst] - pin) * 1e3:6.2f} mV  (at {worst})")


def em_report(iload):
    pl = json.loads((V2 / "ldo_v2_place_snug.json").read_text())
    cell = pl["MPASS"]["cell"]
    bars = json.loads((bl.GL / "terms.json").read_text())[cell]
    nrow = sum(1 for k in bars if re.match(r"S\d+$", k))
    xl, xr = bars["S0"][0], bars["S0"][1]
    straps, x, k = [], xl + 1.0 + STRAP_W / 2, 0
    while x + STRAP_W / 2 <= xr - 1.0:
        straps.append("S" if k % 2 == 0 else "D")
        x += STRAP_PITCH
        k += 1
    n_s, n_d = straps.count("S"), straps.count("D")
    i_strap = iload / min(n_s, n_d) * IMBALANCE
    import klayout.db as kdb
    lay = kdb.Layout()
    lay.read(str(V2 / "ldo_v2.gds"))
    top = lay.top_cell()
    pbox = next(i.bbox() for i in top.each_inst() if i.cell.name == cell)
    nvia = {}
    for name, (ln, dt) in (("via2", (38, 0)), ("via3", (40, 0))):
        cuts = [s_ for s_ in top.shapes(lay.layer(ln, dt)).each() if pbox.contains(s_.bbox().center())]
        nvia[name] = len(cuts) / (len(straps) * nrow)
    vias_per = min(nvia.values())
    i_via = i_strap / nrow / vias_per
    print(f"\nEM check, load current {iload * 1e3:.2f} mA (GF180MCU DRM 14.2, DC, 110 C)")
    for name, i, w, lim in (("VIN / VOUT metal5 bus (all the load current)", iload, BUS_W, "m5"),
                            (f"pass-device metal4 strap ({n_s} VIN / {n_d} VOUT straps, "
                             f"+{(IMBALANCE - 1) * 100:.0f}% imbalance)", i_strap, STRAP_W, "m1-4")):
        j = i / w
        print(f"  {'OK  ' if j <= LIMIT[lim] else 'FAIL'} {name}: {i * 1e3:.2f} mA in {w:.1f} um = "
              f"{j * 1e3:.2f} mA/um (limit {LIMIT[lim] * 1e3:.1f})")
    print(f"  {'OK  ' if i_via <= LIMIT['via'] else 'FAIL'} via2/via3 under each strap at each of the {nrow} rows "
          f"({vias_per:.0f} cuts): {i_via * 1e3:.3f} mA per via (limit {LIMIT['via'] * 1e3:.2f})")


def main():
    v, i = run_op()
    iin = -i.get("i(vvin)", -ILOAD)
    print(f"Supply current at 10 mA load: {iin * 1e3:.3f} mA (VOUT = {v['vout']:.4f} V)\n")
    ir_report(v)
    em_report(iin)


if __name__ == "__main__":
    main()
