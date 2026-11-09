#!/usr/bin/env python3
"""EM / IR check of the extracted LDO layout.

    cd layout/pex && python3 emir_check.py

IR drop: a DC operating point of the RC-extracted netlist (ldo_pex_rc.spice) at
the worst current condition (VIN = 5 V, EN on, 10 mA load). extresist splits each
power net into resistor segments (VIN.n12, VIN.t3, ...); the voltage of every
segment node is compared with the net's pin to find the largest drop.

EM: the current in each element of the high-current path (power buses, pass-
device straps, strap vias) is checked against the GF180MCU design-manual limits
(section 14.2, DC unidirectional, 110 C):
    metal1-4        1.0 mA per um of width
    metal5 (11 kA)  2.2 mA per um of width
    via1-4          0.28 mA per via
The load current is taken from the simulation; it is assumed to split evenly
between the pass-device straps (they are identical and connect to a bus whose
resistance is small compared with theirs), with IMBALANCE extra margin.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_layout as bl  # noqa: E402  (layout constants: bus / strap sizes)

PDK = "/foss/pdks/gf180mcuD/libs.tech/ngspice"
ILOAD = 10e-3
LIMIT = {"m1-4": 1.0e-3, "m5": 2.2e-3, "via": 0.28e-3}     # A/um, A/um, A/via at 110 C
IMBALANCE = 1.2


def run_op():
    pins = re.search(r"(?m)^\.subckt ldo_flat (.*)$", (HERE / "ldo_pex_rc.spice").read_text()).group(1)
    deck = f"""* EM/IR operating point: RC-extracted LDO at full load
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
    subprocess.run([shutil.which("ngspice") or "/foss/tools/ngspice/bin/ngspice", "-b", "emir_op.spice"], cwd=HERE, capture_output=True, text=True)
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
    rows = []
    for net in ("vin", "vout", "vss"):
        pin = v[net]
        nodes = {k: x for k, x in v.items() if re.match(rf"x1\.{net}\.[nt]\d+$", k)}
        if not nodes:
            continue
        worst = max(nodes, key=lambda k: abs(nodes[k] - pin))
        drop = abs(nodes[worst] - pin)
        rows.append((net.upper(), len(nodes), drop, worst))
        print(f"  {net.upper():5s} pin {pin:8.5f} V   {len(nodes):4d} segment nodes   worst drop {drop * 1e3:6.2f} mV  (at {worst})")
    return rows


def em_report(iload):
    straps = []
    xl, xr = None, None
    terms = (HERE.parent / "gl" / "terms.json")
    import json
    bars = json.loads(terms.read_text())[bl.gl_cell(bl.fet("pmos", 3, 0.55, 30, mult=7))]
    xl, xr = bl.um(bars["S0"][0]), bl.um(bars["S0"][1])
    x = xl + bl.um(1.0) + bl.PASS_STRAP // 2
    k = 0
    while x + bl.PASS_STRAP // 2 <= xr - bl.um(1.0):
        straps.append("S" if k % 2 == 0 else "D")
        x += bl.PASS_PITCH
        k += 1
    n_s, n_d = straps.count("S"), straps.count("D")
    rows_ = 7
    w_strap = bl.PASS_STRAP / bl.UM
    w_bus = bl.BUS_W_TOP / bl.UM
    i_strap = iload / min(n_s, n_d) * IMBALANCE
    # via cuts actually drawn per strap per row: count the via2 / via3 cuts the GDS has
    # over the pass device (top-level shapes only) and divide by straps x rows
    import klayout.db as kdb
    lay = kdb.Layout()
    lay.read(str(HERE.parent / "gds" / "ldo.gds"))
    top = lay.top_cell()
    pbox = next(i.bbox() for i in top.each_inst() if i.cell.name.startswith("gl_pmos_3x0p55_30x7"))
    nvia = {}
    for name, (ln, dt) in (("via2", (38, 0)), ("via3", (40, 0))):
        cuts = [s_ for s_ in top.shapes(lay.layer(ln, dt)).each() if pbox.contains(s_.bbox().center())]
        nvia[name] = len(cuts) / (len(straps) * rows_)
    vias_per = min(nvia.values())
    i_via = i_strap / rows_ / vias_per
    print(f"\nEM check, load current {iload * 1e3:.2f} mA (GF180MCU DRM 14.2, DC, 110 C)")
    checks = [
        ("VIN / VOUT metal5 bus (all the load current)", iload, w_bus, "m5"),
        (f"pass-device metal4 strap ({n_s} VIN / {n_d} VOUT straps, +{(IMBALANCE - 1) * 100:.0f}% imbalance)",
         i_strap, w_strap, "m1-4"),
    ]
    out = []
    for name, i, w, lay in checks:
        j = i / w
        ok = j <= LIMIT[lay]
        out.append((name, i, j, LIMIT[lay], ok))
        print(f"  {'OK  ' if ok else 'FAIL'} {name}: {i * 1e3:.2f} mA in {w:.1f} um = {j * 1e3:.2f} mA/um "
              f"(limit {LIMIT[lay] * 1e3:.1f})")
    ok = i_via <= LIMIT["via"]
    out.append(("strap vias", i_via, i_via, LIMIT["via"], ok))
    print(f"  {'OK  ' if ok else 'FAIL'} via2/via3 under each strap at each row ({vias_per:.0f} cuts): "
          f"{i_via * 1e3:.3f} mA per via (limit {LIMIT['via'] * 1e3:.2f})")
    return out


def main():
    v, i = run_op()
    iin = -i.get("i(vvin)", -ILOAD)
    print(f"Supply current at 10 mA load: {iin * 1e3:.3f} mA (VOUT = {v['vout']:.4f} V)\n")
    ir_report(v)
    em_report(iin)


if __name__ == "__main__":
    main()
