#!/usr/bin/env python3
"""Loop-gain / phase-margin analysis of the LDO regulation loop.

    cd simulations && python3 stability.py

The loop (VOUT -> R1/R2 -> FB -> input pair -> EAOUT -> pass device -> VOUT) is
broken for AC at the gate of the input transistor MIN1: the gate gets its own
node FBG, joined to FB through a 1 GH inductor (a short at DC, so the operating
point is unchanged; open for AC), and a 1 V AC source is injected into FBG
through a 1 F capacitor. The loop gain is T = -v(FB) / v(FBG). The gate draws no
current, so breaking the loop there does not load the divider.

Reported per case: low-frequency loop gain, unity-gain frequency (|T| = 1),
phase margin (180 deg + phase of T at the UGF) and gain margin (-|T| in dB
where the phase reaches -180 deg). Swept over load current, process corner,
temperature and output capacitance. Results: results/stability.md, .png.
"""
import re
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import run_sims as rs

HERE = Path(__file__).resolve().parent
RUN, RES = rs.RUN, rs.RES
NETLIST = HERE.parent / "netlist" / "schematic" / "ldo.spice"
PDK = "$PDK_ROOT/gf180mcuD/libs.tech/ngspice".replace("$PDK_ROOT", rs.os.environ.get("PDK_ROOT", "/foss/pdks"))
LOADS = [0, 1e-6, 10e-6, 100e-6, 1e-3, 5e-3, 10e-3]
CORNERS = ["typical", "ff", "ss", "fs", "sf"]
TEMPS = [-40, 27, 110]
CLOADS = [2e-12, 50e-12]


PEX = None          # None = schematic; "c" / "rc" = extracted layout netlist (--pex)
PROBE = "x1"        # hierarchy prefix of the FB / FBG nodes (x1.xpex for the extracted netlist)


def broken_loop_subckt():
    """The LDO netlist with the loop opened for AC at the gate of MIN1.

    Schematic: MIN1's gate FB -> FBG. Extracted layout: every finger of the
    input pair whose gate is FB (nfet_06v0, l=3u) -> FBG, and `ldo` is a
    wrapper around the extracted subcircuit."""
    probe = ("* loop-gain probe: DC path FB-FBG, AC injection into FBG\n"
             "Lbrk FB FBG 1G\nCinj FBG XINJ 1\nVstb XINJ VSS DC 0 AC 1\n")
    if not PEX:
        text = NETLIST.read_text()
        text, n = re.subn(r"(?m)^(XMIN1 \S+ )FB( )", r"\1FBG\2", text)
        assert n == 1, "MIN1 gate not found"
        return re.sub(r"(?m)^(\.subckt ldo VIN .*\n)", r"\1" + probe, text, count=1)
    pexf = rs.PEX_DIR / f"ldo_pex_{PEX}.spice"
    lines, n = [], 0
    for line in pexf.read_text().splitlines():
        f = line.split()
        if f and f[0].startswith("X") and len(f) > 5 and f[2] == "FB" and f[5] == "nfet_06v0" \
                and "l=3u" in line:
            f[2] = "FBG"
            line = " ".join(f)
            n += 1
        lines.append(line)
    assert n >= 1, "input-pair fingers on FB not found in the extracted netlist"
    text = "\n".join(lines) + "\n"
    text = re.sub(r"(?m)^(\.subckt ldo_flat .*\n)", r"\1" + probe, text, count=1)
    pins = re.search(r"(?m)^\.subckt ldo_flat (.*)$", text).group(1)
    return text + f".subckt ldo {rs.LDO_PINS}\nxpex {pins} ldo_flat\n.ends\n"


def run_case(tag, corner, temp, iload, cload):
    deck = f"""* LDO loop gain: {corner}, {temp} C, Iload {iload} A, CL {cload} F
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
.lib {PDK}/sm141064.ngspice res_typical
.lib {PDK}/sm141064.ngspice cap_mim
.lib {PDK}/sm141064.ngspice mimcap_typical
.include stb_ldo.spice
.temp {temp}
x1 VIN VREF EN VOUT FB_BUF EAOUT_BUF 0 ldo
Vvin VIN 0 5
Vvref VREF 0 1.2
Ven EN 0 3.3
Iload VOUT 0 {iload}
CL VOUT 0 {cload}
.control
ac dec 40 1 1G
let t = -v({PROBE}.fb)/v({PROBE}.fbg)
let tdb = db(t)
let tph = 180/pi*cph(t)
wrdata {tag}.txt tdb tph
.endc
.end
"""
    f = RUN / f"{tag}.spice"
    f.write_text(deck)
    subprocess.run([rs.NGSPICE, "-b", f.name], cwd=RUN, capture_output=True, text=True)
    d = np.loadtxt(RUN / f"{tag}.txt")
    return d[:, 0], d[:, 1], d[:, 3]          # freq, |T| dB, phase deg


def margins(freq, tdb, tph):
    out = {"dc_db": tdb[0]}
    i = np.where((tdb[:-1] > 0) & (tdb[1:] <= 0))[0]
    if len(i):
        k = i[0]
        a = tdb[k] / (tdb[k] - tdb[k + 1])
        ugf = 10 ** (np.log10(freq[k]) + a * (np.log10(freq[k + 1]) - np.log10(freq[k])))
        ph = tph[k] + a * (tph[k + 1] - tph[k])
        out.update(ugf=ugf, pm=180 + ph)
    else:
        out.update(ugf=float("nan"), pm=float("nan"))
    j = np.where((tph[:-1] > -180) & (tph[1:] <= -180))[0]
    out["gm"] = -tdb[j[0]] if len(j) else float("inf")
    return out


def main():
    global PEX, PROBE, RES
    ap = rs.argparse.ArgumentParser(description=__doc__, formatter_class=rs.argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pex", choices=["c", "rc"], help="analyse the extracted layout netlist; results to results_pex_<c|rc>/")
    ap.add_argument("--layout", choices=["v1", "v2"], default="v1",
                    help="with --pex: which layout (v2: layout/v2/pex, results to results_v2_pex_<c|rc>/)")
    a = ap.parse_args()
    if a.pex:
        PEX, PROBE, RES = a.pex, "x1.xpex", HERE / f"results_pex_{a.pex}"
        if a.layout == "v2":
            rs.PEX_DIR = HERE.parent / "layout" / "v2" / "pex"
            RES = HERE / f"results_v2_pex_{a.pex}"
    RUN.mkdir(exist_ok=True)
    RES.mkdir(exist_ok=True)
    (RUN / "stb_ldo.spice").write_text(broken_loop_subckt())
    rows, curves = [], {}
    for cload in CLOADS:
        for corner in CORNERS:
            for temp in TEMPS:
                for iload in LOADS:
                    tag = f"stb_{corner}_{temp}_{iload:g}_{cload:g}".replace("-", "m")
                    f, tdb, tph = run_case(tag, corner, temp, iload, cload)
                    m = margins(f, tdb, tph)
                    rows.append(dict(corner=corner, temp=temp, iload=iload, cload=cload, **m))
                    if corner == "typical" and temp == 27:
                        curves[(iload, cload)] = (f, tdb, tph)
                    print(f"CL {cload * 1e12:4.0f}p {corner:8s} {temp:4d}C Iload {iload * 1e3:7.3f} mA: "
                          f"T(dc) {m['dc_db']:5.1f} dB  UGF {m['ugf'] / 1e6:6.2f} MHz  PM {m['pm']:5.1f} deg  "
                          f"GM {m['gm']:5.1f} dB", flush=True)

    # plot: typical corner, 27 C, all loads, CL = 2 pF
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.4, 6.2), sharex=True)
    for iload in LOADS:
        f, tdb, tph = curves[(iload, CLOADS[0])]
        lab = f"{iload * 1e3:g} mA" if iload else "0 (no load)"
        a1.semilogx(f, tdb, label=lab)
        a2.semilogx(f, tph, label=lab)
    a1.axhline(0, color="k", lw=0.8)
    a2.axhline(-180, color="r", lw=0.8, ls="--")
    a1.set_ylabel("loop gain |T| (dB)")
    a2.set_ylabel("phase of T (deg)")
    a2.set_xlabel("frequency (Hz)")
    a1.set_title(f"Regulation-loop gain ({'schematic' if not PEX else 'post-layout ' + PEX.upper()}, typical, 27 C, "
                 f"CL = 2 pF)", fontsize=10.5)
    a1.legend(fontsize=7.5, ncol=2, title="load current", title_fontsize=8)
    for a in (a1, a2):
        a.grid(alpha=0.3, which="both")
    fig.text(0.01, 0.005, "Loop broken at the MIN1 gate (1 GH DC path FB-FBG, 1 F AC injection); T = -v(FB)/v(FBG). "
             "VIN 5 V, VREF 1.2 V, EN 3.3 V, ideal current-sink load.", fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(RES / "stability.png", dpi=120)

    worst = {}
    for r in rows:
        k = r["cload"]
        if k not in worst or r["pm"] < worst[k]["pm"]:
            worst[k] = r
    what = "schematic" if not PEX else f"post-layout, extracted {'C-only' if PEX == 'c' else 'RC'} netlist"
    lines = [f"# Regulation-loop stability ({what})", "",
             "Generated by `simulations/stability.py`. Loop broken at the MIN1 gate; T = -v(FB)/v(FBG).",
             "Swept: load 0-10 mA, MOS corners tt/ff/ss/fs/sf, -40/27/110 C, output capacitance 2 pF and 50 pF.", "",
             "| CL | worst-case PM | at | lowest UGF | highest UGF | min GM |", "|---|---|---|---|---|---|"]
    for cl in CLOADS:
        sel = [r for r in rows if r["cload"] == cl]
        w = worst[cl]
        lines.append(f"| {cl * 1e12:g} pF | {w['pm']:.1f} deg | {w['corner']}, {w['temp']} C, "
                     f"{w['iload'] * 1e3:g} mA | {min(r['ugf'] for r in sel) / 1e6:.2f} MHz | "
                     f"{max(r['ugf'] for r in sel) / 1e6:.2f} MHz | {min(r['gm'] for r in sel):.1f} dB |")
    lines += ["", "Typical corner, 27 C:", "", "| Load | CL | T(dc) | UGF | PM | GM |", "|---|---|---|---|---|---|"]
    for r in rows:
        if r["corner"] == "typical" and r["temp"] == 27:
            lines.append(f"| {r['iload'] * 1e3:g} mA | {r['cload'] * 1e12:g} pF | {r['dc_db']:.1f} dB | "
                         f"{r['ugf'] / 1e6:.2f} MHz | {r['pm']:.1f} deg | {r['gm']:.1f} dB |")
    lines += ["", "![loop gain](stability.png)"]
    (RES / "stability.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[5:9]))


if __name__ == "__main__":
    main()
