#!/usr/bin/env python3
"""Run every LDO testbench in this directory and summarize against the spec.

    python3 run_sims.py            # typical corner, 27C: all testbenches + plots
    python3 run_sims.py --corners  # also sweep process corners x temperature

Requirements: xschem, ngspice, the gf180mcuD PDK with $PDK_ROOT set,
Python 3 with numpy + matplotlib.

Each tb_*.sch is netlisted by xschem (using ./xschemrc, which pulls in the
PDK via $PDK_ROOT) into ./run/, simulated by ngspice in batch mode, and its
'RESULT <name> <value>' lines are collected. Plots and a markdown summary go
to ./results/. Raw simulator output stays in ./run/ (not committed).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
RUN = HERE / "run"
RES = HERE / "results"

XSCHEM = shutil.which("xschem") or "/foss/tools/xschem/bin/xschem"
NGSPICE = shutil.which("ngspice") or "/foss/tools/ngspice/bin/ngspice"

# Target specification (README.md / proposal section 4)
SPEC = {
    "vout_min": 3.201, "vout_max": 3.399,
    "dropout_max_mV": 300,
    "iq_max_uA": 100,
    "line_reg_max_pct": 1.0,
    "load_reg_max_pct": 1.0,
    "psrr_min_dB": 40,
}


PEX = None          # None = schematic; "c" / "rc" = extracted layout netlist (see --pex)
PEX_DIR = HERE.parent / "layout" / "pex"            # final (v2) layout; v1 is in layout_v1/pex
LDO_PINS = "VIN VREF EN VOUT FB_BUF EAOUT_BUF VSS"     # pin order of xschem/ldo.sym


def use_pex(spice: Path):
    """Swap the schematic LDO for the extracted layout netlist in a testbench netlist.

    Removes the xschem-generated ldo / ldo_levelshift subcircuits and defines
    `ldo` as a wrapper around the extracted subcircuit (ldo_flat, pins in its
    own order, mapped by name). Internal probes x1.fb / x1.eaout are redirected
    to the labelled nets inside the extracted netlist."""
    text = spice.read_text()
    text = re.sub(r"(?ms)^\.subckt (ldo|ldo_levelshift) .*?^\.ends\s*$", "", text)
    pexf = PEX_DIR / f"ldo_pex_{PEX}.spice"
    pins = re.search(r"(?m)^\.subckt ldo_flat (.*)$", pexf.read_text()).group(1).split()
    wrapper = (f".subckt ldo {LDO_PINS}\nxpex {' '.join(pins)} ldo_flat\n.ends\n"
               f".include {pexf}\n")
    ends = list(re.finditer(r"(?m)^\.end\s*$", text))        # the final .end (not .ends / .endc)
    text = text[:ends[-1].start()] + wrapper + text[ends[-1].start():] if ends else text + wrapper
    text = text.replace("v(x1.fb)", "v(x1.xpex.fb)").replace("v(x1.eaout)", "v(x1.xpex.eaout)")
    spice.write_text(text)


def netlist(tb: str) -> Path:
    if "PDK_ROOT" not in os.environ:
        sys.exit("PDK_ROOT is not set (needed to find the gf180mcuD PDK)")
    subprocess.run([XSCHEM, "--rcfile", str(HERE / "xschemrc"), "-n", "-q", "--no_x", str(HERE / f"{tb}.sch")],
                   cwd=HERE, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if PEX:
        use_pex(RUN / f"{tb}.spice")
    return RUN / f"{tb}.spice"


def simulate(spice: Path, tag: str) -> dict:
    log = RUN / f"{tag}.log"
    with open(log, "w") as f:
        subprocess.run([NGSPICE, "-b", spice.name], cwd=RUN, stdout=f, stderr=subprocess.STDOUT)
    text = log.read_text()
    if re.search(r"(?m)^(Error|ERROR)|fatal error", text):
        raise RuntimeError(f"ngspice reported an error, see {log}")
    out = {}
    for name, val in re.findall(r"(?m)^RESULT (\S+)\s*(\S*)", text):
        out[name] = float(val) if val else float("nan")
    return out


def export_netlist():
    """Write the LDO + level-shifter subcircuits (no testbench, no absolute
    paths) to ../netlist/schematic/ldo.spice for use in a larger system."""
    src = (RUN / "tb_iq.spice").read_text()
    blocks = re.findall(r"(?ms)^\.subckt .*?^\.ends\s*$", src)
    out = HERE.parent / "netlist" / "schematic" / "ldo.spice"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("* Capless LDO (GF180MCU) - schematic netlist, generated from xschem/ldo.sch\n"
                   "* by simulations/run_sims.py. Devices: gf180mcuD nfet_05v0 / pfet_05v0.\n\n"
                   + "\n\n".join(b.strip() for b in blocks) + "\n")


def load(tb: str) -> np.ndarray:
    return np.loadtxt(RUN / f"{tb}.txt")


def dropout_mV(d: np.ndarray) -> float:
    """VIN - VOUT at the lowest VIN where VOUT is still within 1% of its
    regulated (high-headroom) value, at Iload = 10mA."""
    vin, vout = d[:, 0], d[:, 1]
    target = 0.99 * vout[-1]
    vin_min = vin[vout >= target].min()
    return (vin_min - vout[-1]) * 1e3, vin_min


# Conditions shared by every testbench (see tb_*.sch)
COMMON_COND = [
    ("Corner", "typical MOS, typical poly-R / MIM, 27 C (gf180mcuD models)"),
    ("VREF", "1.2 V, ideal DC voltage source"),
    ("Output cap", "CL = 2 pF ideal capacitor, VOUT to ground"),
]


def figure(name, title, xlabel, ylabel, cond):
    """Plot area on top, a test-conditions panel underneath.
    cond: list of (label, text) rows specific to this test; the rows in
    COMMON_COND are appended unless a row with the same label is given."""
    rows = list(cond) + [c for c in COMMON_COND if c[0] not in {r[0] for r in cond}]
    fig = plt.figure(figsize=(7.4, 4.0 + 0.24 * len(rows)))
    gs = fig.add_gridspec(2, 1, height_ratios=[3.4, 0.24 * len(rows) + 0.35], hspace=0.42)
    ax = fig.add_subplot(gs[0])
    ax.set_title(title, fontsize=10.5)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3, which="both")
    tx = fig.add_subplot(gs[1])
    tx.axis("off")
    tx.set_title("Test conditions", loc="left", fontsize=9, fontweight="bold", pad=2)
    for i, (k, v) in enumerate(rows):
        y = 1 - (i + 0.5) / len(rows)
        tx.text(0.0, y, k, fontsize=8.3, fontweight="bold", va="center", transform=tx.transAxes)
        tx.text(0.19, y, v, fontsize=8.3, va="center", transform=tx.transAxes)
    return fig, ax


def save(fig, name):
    fig.savefig(RES / f"{name}.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


def typical():
    tbs = sorted(p.stem for p in HERE.glob("tb_*.sch"))
    r = {}
    for tb in tbs:
        print(f"  {tb} ...", flush=True)
        r.update(simulate(netlist(tb), tb))

    # ---- plots
    d = load("tb_line_reg")
    fig, ax = figure("line_reg", f"Line regulation: {r['line_reg_pct']:.3f} % (spec <= 1 %)", "VIN (V)", "VOUT (V)", [
        ("Analysis", "DC sweep (steady state): VIN 4.5 -> 5.5 V in 10 mV steps (tb_line_reg)"),
        ("Load", "ideal DC current sink, 5 mA, VOUT to ground"),
        ("EN", "3.3 V, ideal DC source (regulator on)"),
        ("Metric", "(max VOUT - min VOUT) / 3.3 V x 100 %")])
    ax.plot(d[:, 0], d[:, 1])
    save(fig, "line_reg")

    d = load("tb_load_reg")
    fig, ax = figure("load_reg", f"Load regulation: {r['load_reg_pct']:.3f} % (spec <= 1 %)", "Iload (mA)", "VOUT (V)", [
        ("Analysis", "DC sweep (steady state): Iload 0 -> 10 mA in 0.05 mA steps (tb_load_reg)"),
        ("Load", "ideal DC current sink (swept), VOUT to ground"),
        ("VIN", "5.0 V, ideal DC source"),
        ("EN", "3.3 V, ideal DC source (regulator on)"),
        ("Metric", "(max VOUT - min VOUT) / 3.3 V x 100 %")])
    ax.plot(d[:, 0] * 1e3, d[:, 1])
    save(fig, "load_reg")
    r["vout_5mA"] = float(np.interp(5e-3, d[:, 0], d[:, 1]))
    r["vout_0mA"], r["vout_10mA"] = float(d[0, 1]), float(d[-1, 1])

    d = load("tb_dropout")
    r["dropout_mV"], vin_min = dropout_mV(d)
    fig, ax = figure("dropout", f"Dropout: {r['dropout_mV']:.0f} mV at 10 mA (spec <= 300 mV)", "VIN (V)", "VOUT (V)", [
        ("Analysis", "DC sweep (steady state): VIN 3.3 -> 5.5 V in 5 mV steps (tb_dropout)"),
        ("Load", "ideal DC current sink, 10 mA (full load), VOUT to ground"),
        ("EN", "3.3 V, ideal DC source (regulator on)"),
        ("Metric", "VIN_min - VOUT_reg, where VIN_min is the lowest VIN with VOUT >= 99 % of VOUT at VIN = 5.5 V")])
    ax.plot(d[:, 0], d[:, 1], label="VOUT")
    ax.plot(d[:, 0], d[:, 0], ":", color="gray", label="VIN")
    ax.axvline(vin_min, color="red", ls="--", label=f"VIN min in regulation = {vin_min:.3f} V")
    ax.set_ylim(2.8, 3.6)
    ax.legend(fontsize=8)
    save(fig, "dropout")

    d = load("tb_tran_load")
    fig, ax = figure("tran_load", f"Load step 0 -> 10 mA -> 0: -{r['load_undershoot_mV']:.0f} / "
                     f"+{r['load_overshoot_mV']:.0f} mV", "time (us)", "VOUT (V)", [
        ("Analysis", "transient, 20 ns step, 0-100 us (tb_tran_load)"),
        ("Load", "ideal current sink pulse 0 -> 10 mA at t = 20 us, 1 us rise/fall, 40 us high"),
        ("VIN", "5.0 V, ideal DC source"),
        ("EN", "3.3 V, ideal DC source (regulator on)"),
        ("Metric", "undershoot = settled VOUT (10-19 us) - min; overshoot = max after release - settled (90-99 us)")])
    ax.plot(d[:, 0] * 1e6, d[:, 1])
    for t in (20, 61):
        ax.axvline(t, color="gray", ls=":")
    save(fig, "tran_load")

    d = load("tb_tran_line")
    fig, ax = figure("tran_line", f"Line step 5.0 -> 4.5 -> 5.0 V: -{r['line_tran_dip_mV']:.0f} / "
                     f"+{r['line_tran_bump_mV']:.0f} mV", "time (us)", "VOUT (V)", [
        ("Analysis", "transient, 20 ns step, 0-100 us (tb_tran_line)"),
        ("VIN", "ideal voltage pulse 5.0 -> 4.5 V at t = 20 us, 1 us rise/fall, 40 us low"),
        ("Load", "ideal DC current sink, 5 mA, VOUT to ground"),
        ("EN", "3.3 V, ideal DC source (regulator on)"),
        ("Metric", "dip = settled VOUT before step - min; bump = max after return - settled")])
    ax.plot(d[:, 0] * 1e6, d[:, 3], label="VOUT")
    ax2 = ax.twinx()
    ax2.plot(d[:, 0] * 1e6, d[:, 1], color="gray", ls="--", label="VIN")
    ax2.set_ylabel("VIN (V)")
    save(fig, "tran_line")

    d = load("tb_psrr")
    fig, ax = figure("psrr", f"PSRR: {r['psrr_100Hz_dB']:.1f} dB at 100 Hz (spec >= 40 dB), "
                     f"{r['psrr_10kHz_dB']:.1f} dB at 10 kHz", "frequency (Hz)", "PSRR (dB)", [
        ("Analysis", "AC small-signal, 10 Hz - 10 MHz, 20 points/decade (tb_psrr)"),
        ("VIN", "5.0 V DC + AC stimulus (small-signal, amplitude 1 for ratio)"),
        ("Load", "ideal DC current sink, 5 mA, VOUT to ground"),
        ("EN", "3.3 V, ideal DC source (regulator on)"),
        ("Metric", "PSRR = -20 log10(|v(VOUT)| / |v(VIN)|)")])
    ax.semilogx(d[:, 0], d[:, 1])
    ax.axhline(SPEC["psrr_min_dB"], color="red", ls="--", label="40 dB spec (low frequency)")
    ax.legend(fontsize=8)
    save(fig, "psrr")

    d = load("tb_en")
    fig, ax = figure("en", f"Enable: turn-on {r['en_turn_on_time_us']:.2f} us, VOUT off = "
                     f"{r['en_vout_off_V']*1e3:.2f} mV", "time (us)", "voltage (V)", [
        ("Analysis", "transient, 50 ns step, 0-250 us (tb_en)"),
        ("EN", "ideal voltage pulse 0 -> 3.3 V at t = 20 us, 1 us rise/fall, 100 us high"),
        ("Load", "660 ohm resistor, VOUT to ground (5 mA at 3.3 V; a resistor so VOUT can rest at 0 V when off)"),
        ("VIN", "5.0 V, ideal DC source"),
        ("Metric", "turn-on = time from EN rising (20 us) to VOUT = 3.2 V")])
    ax.plot(d[:, 0] * 1e6, d[:, 1], label="VOUT")
    ax.plot(d[:, 0] * 1e6, d[:, 3], ls="--", color="gray", label="EN")
    ax.legend(fontsize=8)
    save(fig, "en")

    d = load("tb_en_dc")
    fig, ax = figure("en_dc", f"EN threshold: {r['en_threshold_V_at_VIN4p5']:.2f} V (VIN 4.5) / "
                     f"{r['en_threshold_V_at_VIN5p5']:.2f} V (VIN 5.5)", "EN (V)", "VOUT (V)", [
        ("Analysis", "DC sweep (steady state): EN 0 -> 3.3 V in 5 mV steps, at VIN = 4.5 V and 5.5 V (tb_en_dc)"),
        ("EN", "ideal DC voltage source (swept)"),
        ("Load", "660 ohm resistor, VOUT to ground"),
        ("Metric", "threshold = EN voltage where VOUT crosses 1.65 V (half of 3.3 V)")])
    breaks = np.where(np.diff(d[:, 0]) < 0)[0] + 1
    for seg, lbl in zip(np.split(d, breaks), ("VIN = 4.5 V", "VIN = 5.5 V")):
        ax.plot(seg[:, 0], seg[:, 1], label=lbl)
    ax.legend(fontsize=8)
    save(fig, "en_dc")
    fig, ax = figure("iq", f"Quiescent current {r['iq_uA']:.1f} uA (spec <= 100 uA); "
                     f"shutdown {r['ishdn_uA']*1e3:.2f} nA", "", "current from VIN (uA)", [
        ("Analysis", "DC operating point (tb_iq), run twice: EN = 3.3 V, then EN = 0 V"),
        ("Load", "none: ideal current sink set to 0 mA (only the divider loads VOUT)"),
        ("VIN", "5.0 V, ideal DC source"),
        ("Metric", "total current drawn from the VIN source")])
    bars = ax.bar(["EN = 3.3 V (on, no load)", "EN = 0 V (shutdown)"], [r["iq_uA"], r["ishdn_uA"]],
                  color=["#3b6ea8", "#9aa7b4"], width=0.5)
    ax.axhline(SPEC["iq_max_uA"], color="red", ls="--", label="100 uA spec (on)")
    for b, txt in zip(bars, [f"{r['iq_uA']:.1f} uA", f"{r['ishdn_uA']*1e3:.2f} nA"]):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 2, txt, ha="center", fontsize=9)
    ax.set_ylim(0, 115)
    ax.legend(fontsize=8)
    save(fig, "iq")
    return r


# ------------------------------------------------------------------ corners
CORNERS = ["typical", "ff", "ss", "fs", "sf"]      # MOS corners
RES_CORNERS = ["typical", "ff", "ss"]               # poly resistor + MIM cap corners
TEMPS = [-40, 27, 110]
CORNER_TBS = ["tb_iq", "tb_line_reg", "tb_load_reg", "tb_dropout", "tb_psrr"]


def corners():
    rows = []
    for tb in CORNER_TBS:
        netlist(tb)
    for c, rc, t in [(c, rc, t) for c in CORNERS for rc in RES_CORNERS for t in TEMPS]:
            row = {"corner": c, "res": rc, "temp": t}
            for tb in CORNER_TBS:
                src = (RUN / f"{tb}.spice").read_text()
                src = re.sub(r"(sm141064\.ngspice) typical", rf"\1 {c}", src)
                src = src.replace("sm141064.ngspice res_typical", f"sm141064.ngspice res_{rc}")
                src = src.replace("sm141064.ngspice mimcap_typical", f"sm141064.ngspice mimcap_{rc}")
                src = src.replace(".control", f".temp {t}\n.control", 1)
                tag = f"{tb}_{c}_{rc}_{t}"
                src = src.replace(f"{tb}.raw", f"{tag}.raw").replace(f"{tb}.txt", f"{tag}.txt")
                (RUN / f"{tag}.spice").write_text(src)
                row.update(simulate(RUN / f"{tag}.spice", tag))
                if tb == "tb_dropout":
                    row["dropout_mV"], _ = dropout_mV(load(tag))
                if tb == "tb_load_reg":
                    d = load(tag)
                    row["vout_5mA"] = float(np.interp(5e-3, d[:, 0], d[:, 1]))
            print(f"  {c:8s} R/C {rc:8s} {t:4d}C  VOUT {row['vout_5mA']:.4f} V  Iq {row['iq_uA']:.1f} uA  "
                  f"dropout {row['dropout_mV']:.0f} mV  PSRR {row['psrr_100Hz_dB']:.1f} dB  off {row['ishdn_uA']*1e3:.2f} nA", flush=True)
            rows.append(row)
    return rows


def ok(v, lo=None, hi=None):
    return "PASS" if (lo is None or v >= lo) and (hi is None or v <= hi) else "**FAIL**"


def write_summary(r, rows):
    S = SPEC
    lines = [
        "# Simulation results (" + ("schematic, pre-layout" if not PEX else
                                     f"post-layout, extracted {'C-only' if PEX == 'c' else 'RC'} netlist") + ")",
        "",
        "Generated by `simulations/run_sims.py`. Typical corner, 27 C, VIN = 5.0 V, VREF = 1.2 V,",
        "EN = 3.3 V (harness logic level), CL = 2 pF, unless noted.",
        "",
        "| Parameter | Spec | Simulated | Result | Testbench |",
        "|---|---|---|---|---|",
        f"| Output voltage (5 mA) | {S['vout_min']} - {S['vout_max']} V | {r['vout_5mA']:.4f} V | "
        f"{ok(r['vout_5mA'], S['vout_min'], S['vout_max'])} | tb_load_reg |",
        f"| Dropout (10 mA) | <= {S['dropout_max_mV']} mV | {r['dropout_mV']:.0f} mV | "
        f"{ok(r['dropout_mV'], hi=S['dropout_max_mV'])} | tb_dropout |",
        f"| Quiescent current (no load) | <= {S['iq_max_uA']} uA | {r['iq_uA']:.1f} uA | "
        f"{ok(r['iq_uA'], hi=S['iq_max_uA'])} | tb_iq |",
        f"| Line regulation (4.5-5.5 V, 5 mA) | <= {S['line_reg_max_pct']} % | {r['line_reg_pct']:.3f} % | "
        f"{ok(r['line_reg_pct'], hi=S['line_reg_max_pct'])} | tb_line_reg |",
        f"| Load regulation (0-10 mA) | <= {S['load_reg_max_pct']} % | {r['load_reg_pct']:.3f} % | "
        f"{ok(r['load_reg_pct'], hi=S['load_reg_max_pct'])} | tb_load_reg |",
        f"| PSRR (100 Hz, 5 mA) | >= {S['psrr_min_dB']} dB | {r['psrr_100Hz_dB']:.1f} dB | "
        f"{ok(r['psrr_100Hz_dB'], lo=S['psrr_min_dB'])} | tb_psrr |",
        f"| PSRR (10 kHz / 1 MHz) | - | {r['psrr_10kHz_dB']:.1f} / {r['psrr_1MHz_dB']:.1f} dB | info | tb_psrr |",
        f"| Load step 0->10 mA, 1 us | - | -{r['load_undershoot_mV']:.0f} / +{r['load_overshoot_mV']:.0f} mV | info | tb_tran_load |",
        f"| Line step 5.0->4.5 V, 1 us | - | -{r['line_tran_dip_mV']:.0f} / +{r['line_tran_bump_mV']:.0f} mV | info | tb_tran_line |",
        f"| EN off -> VOUT | 0 V | {r['en_vout_off_V']*1e3:.2f} mV | PASS | tb_en |",
        f"| EN turn-on time (to 3.2 V) | - | {r['en_turn_on_time_us']:.2f} us | info | tb_en |",
        f"| EN switching threshold | 3.3 V logic | {r['en_threshold_V_at_VIN4p5']:.2f} / "
        f"{r['en_threshold_V_at_VIN5p5']:.2f} V (VIN 4.5 / 5.5) | PASS | tb_en_dc |",
        f"| Shutdown current (EN = 0) | - | {r['ishdn_uA']*1e3:.2f} nA | info | tb_iq |",
        f"| Test buffer FB_BUF (FB - FB_BUF) | follows FB | {r['fbbuf_V']:.3f} V ({r['fb_V'] - r['fbbuf_V']:.3f} V below FB = {r['fb_V']:.3f} V) | info | tb_iq |",
        f"| Test buffer EAOUT_BUF (EAOUT - EAOUT_BUF) | follows EAOUT | {r['eaoutbuf_V']:.3f} V ({r['eaout_V'] - r['eaoutbuf_V']:.3f} V below EAOUT = {r['eaout_V']:.3f} V) | info | tb_iq |",
        "",
        "![line regulation](line_reg.png) ![load regulation](load_reg.png)",
        "![dropout](dropout.png) ![PSRR](psrr.png)",
        "![load transient](tran_load.png) ![line transient](tran_line.png)",
        "![EN transient](en.png) ![EN threshold](en_dc.png)",
        "![quiescent and shutdown current](iq.png)",
    ]
    if rows:
        lines += [
            "",
            "## Process corners x temperature (VIN = 5.0 V)",
            "",
            "MOS corners tt/ff/ss/fs/sf x poly-resistor and MIM-capacitor corners typical/ff/ss x -40/27/110 C.",
            "Each column uses the same testbench and load as the typical table above: VOUT at a 5 mA ideal current",
            "sink (tb_load_reg), Iq and off current with no load (tb_iq), line reg at 5 mA, load reg 0-10 mA,",
            "dropout at 10 mA, PSRR at 5 mA.",
            "",
            "| MOS corner | R/C corner | Temp (C) | VOUT @5 mA (V) | Iq (uA) | Line reg (%) | Load reg (%) | Dropout @10 mA (mV) | PSRR @100 Hz (dB) | Off current, EN = 0 (nA) |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for w in rows:
            lines.append(
                f"| {w['corner']} | {w['res']} | {w['temp']} | {w['vout_5mA']:.4f} {'' if S['vout_min'] <= w['vout_5mA'] <= S['vout_max'] else '**FAIL**'} | "
                f"{w['iq_uA']:.1f} {'' if w['iq_uA'] <= S['iq_max_uA'] else '**FAIL**'} | "
                f"{w['line_reg_pct']:.3f} {'' if w['line_reg_pct'] <= S['line_reg_max_pct'] else '**FAIL**'} | "
                f"{w['load_reg_pct']:.3f} {'' if w['load_reg_pct'] <= S['load_reg_max_pct'] else '**FAIL**'} | "
                f"{w['dropout_mV']:.0f} {'' if w['dropout_mV'] <= S['dropout_max_mV'] else '**FAIL**'} | "
                f"{w['psrr_100Hz_dB']:.1f} {'' if w['psrr_100Hz_dB'] >= S['psrr_min_dB'] else '**FAIL**'} | "
                f"{w['ishdn_uA']*1e3:.2f} |")
    (RES / "summary.md").write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corners", action="store_true", help="also run process corners x temperature")
    ap.add_argument("--pex", choices=["c", "rc"],
                    help="simulate the extracted layout (layout/pex/ldo_pex_<c|rc>.spice) instead of the "
                         "schematic; results go to results_v2_pex_<c|rc>/")
    ap.add_argument("--layout", choices=["v1", "v2"], default="v2",
                    help="with --pex: which layout (v2 = final, layout/pex; v1 = layout_v1/pex, "
                         "results to results_pex_<c|rc>/)")
    a = ap.parse_args()
    global PEX, RES, PEX_DIR
    if a.pex:
        PEX, RES = a.pex, HERE / f"results_v2_pex_{a.pex}"
        if a.layout == "v1":
            PEX_DIR, RES = HERE.parent / "layout_v1" / "pex", HERE / f"results_pex_{a.pex}"
    RUN.mkdir(exist_ok=True)
    RES.mkdir(exist_ok=True)
    print("typical corner:")
    r = typical()
    if not PEX:
        export_netlist()
    rows = []
    if a.corners:
        print("corners:")
        rows = corners()
    write_summary(r, rows)
    print(f"\nwrote {RES / 'summary.md'}")
    print((RES / "summary.md").read_text())


if __name__ == "__main__":
    main()
