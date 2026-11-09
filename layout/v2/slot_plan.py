#!/usr/bin/env python3
"""Layout v2: planned position of the LDO in a Chipalooza slot, pin assignment
and the power / signal wiring to the harness pins (a plan -- nothing is drawn
in GDS yet).

    cd layout/v2 && python3 place_v2.py top && python3 slot_plan.py [slot]

Harness pins come from harness_slot_pins.json (extracted from the harness
repo's gds/slot<N>_wrapper.gds). Slots 1-9 have the shared pins (power, bias,
enable, analog buses) on the left edge and the dedicated pads on the right;
slots 10-18 are mirror images. This plan handles slots with two or three
dedicated pads on the right (1-7, 9).

Pin assignment:
    VIN       <- vdd_5v0     (metal5, left edge)  gated 5 V project supply
    VSS       <- vss_5v0     (metal5, left edge)
    EN        <- enable      (metal3, left edge)  project enable (3.3 V logic)
    FB_BUF    -> analog_bus0 (metal3, left edge)  test buffer outputs
    EAOUT_BUF -> analog_bus1
    VOUT      -> upper dedicated pad (metal3, right edge)
    VREF      <- lower dedicated pad (metal3, right edge), external reference
The block is mirrored top-to-bottom to follow the harness pin order: VSS bus on
top (straight into vss_5v0), pass device at the bottom with the VOUT bus and the
VIN trunk under it (straight into the VOUT pad and vdd_5v0).
The LDO sits against the right edge so the 10 mA VOUT path to its pad is short;
the 10 mA VIN supply crosses the slot on a wide metal5 trunk instead (an IR drop
on VIN only eats into the 1.4 V of dropout headroom). Writes slot_plan.png,
slot_plan_zoom.png and slot_plan.md (wire sizes, lengths, IR drop).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLOT = sys.argv[1] if len(sys.argv) > 1 else "1"

RS_M5, RS_M3 = 0.049, 0.104          # ohm / square, high corner (magic gf180mcuD.tech)
EM_M5, EM_M3, EM_VIA = 2.2, 1.0, 0.28  # mA/um, mA/um, mA per cut at 110 C (GF180 DRM 14.2)
I_LOAD = 10.0                        # mA

# wiring plan (um)
EDGE_GAP = 20.0      # LDO right edge to the slot's right edge (pad landing + VOUT via stack)
VOUT_W = 12.0        # metal5 VOUT bus above the pass device
VIN_W = 30.0         # metal5 VIN trunk, harness pin -> top of the block
VSS_BUS_W = 10.0     # metal5 VSS trunk + bus along the top of the block (quiescent current only)
CHAN = 8.0           # signal channel between the devices and the VSS bus
GAP = 2.0
SIG_W = {"VREF": 1.0, "EN": 0.5, "FB_BUF": 1.0, "EAOUT_BUF": 1.0}

C = {"VIN": "#eb6834", "VSS": "#6250d6", "VOUT": "#1baf7a", "VREF": "#2a78d6",
     "EN": "#c98500", "FB_BUF": "#d55181", "EAOUT_BUF": "#d55181"}
INK, INK2, SURF = "#0b0b0b", "#52514e", "#fcfcfb"


def load():
    pins = json.loads((HERE / "harness_slot_pins.json").read_text())
    slot = {p["name"]: p for p in pins["slots"][SLOT]}
    place = json.loads((HERE / "ldo_v2_place_top.json").read_text())
    return pins["slot_size"], slot, place


def plan(size, pins, place):
    W, H = size
    pads = sorted((p for n, p in pins.items() if "_an[" in n), key=lambda p: p["box"][1])
    assert len(pads) >= 2 and all(p["box"][0] > W / 2 for p in pads), \
        "plan needs two dedicated pads on the right edge (slots 1-7, 9)"
    vref_pad, vout_pad = pads[0], pads[1]           # lower pad: VREF, next one up: VOUT
    buf = {"RrefEA", "MREFEA_MBIAS", "MPDEA", "MFBBUF", "MEAOUTBUF"}
    # The block is mirrored top-to-bottom to match the harness pin order (vss_5v0 above
    # vdd_5v0): VSS bus on top, pass device at the bottom with VOUT and VIN under it.
    # Bottom-up: VIN trunk (meets vdd_5v0), VOUT bus (runs into the VOUT pad), LDO,
    # signal channel, VSS bus (meets vss_5v0).
    def tf(b):                                      # mirror in y, then move into the slot
        return [b[0] + dx, -b[3] + dy, b[2] + dx, -b[1] + dy]
    ldo = [v["box"] for k, v in place.items() if k not in buf]
    lx1, ly1 = max(b[2] for b in ldo), max(b[3] for b in ldo)
    vdd_pin, vss_pin = pins["vdd_5v0"]["box"], pins["vss_5v0"]["box"]
    vin_y = (vdd_pin[1] + 1.0, vdd_pin[1] + 1.0 + VIN_W)
    vout_y = (vin_y[1] + GAP, vin_y[1] + GAP + VOUT_W)
    dx, dy = (W - EDGE_GAP) - lx1, (vout_y[1] + GAP) + ly1     # LDO bottom 2 um above the VOUT bus
    cells = {k: tf(v["box"]) for k, v in place.items()}
    X0 = min(cells[k][0] for k in cells if k not in buf)
    X1 = max(cells[k][2] for k in cells if k not in buf)
    Y0 = min(cells[k][1] for k in cells if k not in buf)
    Y1 = max(cells[k][3] for k in cells if k not in buf)
    bx0 = min(b[0] for b in cells.values())         # left edge incl. test buffers
    by0, by1 = min(b[1] for b in cells.values()), max(b[3] for b in cells.values())
    vss_bus_y = (by1 + CHAN, by1 + CHAN + VSS_BUS_W)
    chan_y = by1 + CHAN / 2
    vp = vout_pad["box"]
    assert by0 > vout_y[1], "test buffers overlap the VOUT bus"
    assert min(vout_y[1], vp[3]) - max(vout_y[0], vp[1]) >= 5, "VOUT bus must overlap the VOUT pad (else add a jog)"
    assert vss_pin[1] <= vss_bus_y[0] and vss_bus_y[1] <= vss_pin[3], "VSS bus must meet the vss_5v0 pin"
    assert vin_y[1] <= vdd_pin[3] and vss_bus_y[1] < H, "rails outside the pin / slot"
    xv = bx0 - 25.0                                 # left end of the block's rails
    shapes = {   # (net, layer, x0, y0, x1, y1, label)
        "vin_trunk": ("VIN", "metal5", 0.0, vin_y[0], X1, vin_y[1], f"VIN trunk  metal5 {VIN_W:.0f} µm"),
        "vout_bus": ("VOUT", "metal5", X0, vout_y[0], vp[2], vout_y[1], f"VOUT bus  metal5 {VOUT_W:.0f} µm"),
        "vout_land": ("VOUT", "metal3", vp[0] - 6.0, vp[1], vp[2], vp[3], "metal3 landing on the pad"),
        "vss_trunk": ("VSS", "metal5", 0.0, vss_bus_y[0], X1, vss_bus_y[1],
                      f"VSS trunk + bus  metal5 {VSS_BUS_W:.0f} µm"),
    }

    def centre(name, side=None):
        b = cells[name]
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    groups = json.loads((HERE / "gl" / "groups.json").read_text())
    org = place["v2_nmos_core"]["origin"]

    def dev(name):                                  # device box inside the NMOS group
        d = next(d for d in groups["v2_nmos_core"]["devices"] if d["name"] == name)
        return tf([d["box"][0] + org[0], d["box"][1] + org[1], d["box"][2] + org[0], d["box"][3] + org[1]])
    min_b, mn1_b = dev("MIN1_MIN2"), dev("MN1")
    core_r = max(cells["v2_nmos_core"][2], cells["v2_pmos_core"][2])
    vref_x = (core_r + cells["Cc"][0]) / 2          # channel between the core and Cc
    vpin = (vref_pad["box"][0], (vref_pad["box"][1] + vref_pad["box"][3]) / 2)
    en_pin = pins["enable"]["box"]
    jog = bx0 - 8.0
    col_l = min(cells[g][0] for g in ("v2_nmos_core", "v2_pmos_core"))
    en_x = (col_l + cells["Rref"][0]) / 2           # free strip beside Rref (keeps EN off the resistor)
    ymin, ymn1 = (min_b[1] + min_b[3]) / 2, (mn1_b[1] + mn1_b[3]) / 2
    routes = {   # net: polyline. VREF comes up the strip right of the block (it may not
                 # cross the pass device), along the top channel and down beside Cc
        "VREF": [vpin, (X1 + 4.0, vpin[1]), (X1 + 4.0, chan_y + 1.5), (vref_x, chan_y + 1.5), (vref_x, ymin),
                 (min_b[2], ymin)],
        "EN": [(en_pin[2], (en_pin[1] + en_pin[3]) / 2), (jog, (en_pin[1] + en_pin[3]) / 2), (jog, chan_y),
               (en_x, chan_y), (en_x, ymn1), (mn1_b[0], ymn1)],
    }
    for k, (net, bus) in enumerate((("FB_BUF", "analog_bus0"), ("EAOUT_BUF", "analog_bus1"))):
        pb = pins[bus]["box"]
        src = cells["MFBBUF" if net == "FB_BUF" else "MEAOUTBUF"]
        yb = (pb[1] + pb[3]) / 2
        xj = jog - 3.0 * (k + 1)
        ys = chan_y - 1.2 * (k + 1)
        routes[net] = [(pb[2], yb), (xj, yb), (xj, ys), ((src[0] + src[2]) / 2, ys), ((src[0] + src[2]) / 2, src[3])]
    return dict(cells=cells, ldo=(X0, Y0, X1, Y1), shapes=shapes, routes=routes,
                vout_pad=vout_pad, vref_pad=vref_pad, block_left=xv)


def length(poly):
    return sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(poly, poly[1:]))


def report(p):
    s = p["shapes"]
    L_vin = s["vin_trunk"][4] - s["vin_trunk"][2]
    R_vin = L_vin / VIN_W * RS_M5
    L_vss = s["vss_trunk"][4] - s["vss_trunk"][2]
    L_vout = s["vout_bus"][4] - s["vout_bus"][2]
    rows = [
        ("VIN", "vdd_5v0", f"metal5 {VIN_W:.0f} µm", f"{L_vin:.0f}", f"{R_vin:.2f} Ω -> {R_vin * I_LOAD:.0f} mV at 10 mA",
         f"{I_LOAD / VIN_W:.2f} of {EM_M5} mA/µm"),
        ("VSS", "vss_5v0", f"metal5 {VSS_BUS_W:.0f} µm", f"{L_vss:.0f}", f"{L_vss / VSS_BUS_W * RS_M5:.1f} Ω, ~0.1 mA -> <1 mV",
         "-"),
        ("VOUT", p["vout_pad"]["name"], f"metal5 {VOUT_W:.0f} µm + metal3 pad landing", f"{L_vout:.0f}",
         f"{L_vout / VOUT_W * RS_M5:.2f} Ω -> {L_vout / VOUT_W * RS_M5 * I_LOAD:.1f} mV (worst end)",
         f"{I_LOAD / VOUT_W:.2f} of {EM_M5} mA/µm; >= {I_LOAD / EM_VIA:.0f} cuts per via level"),
    ]
    for net, poly in p["routes"].items():
        pin = {"VREF": p["vref_pad"]["name"], "EN": "enable", "FB_BUF": "analog_bus0", "EAOUT_BUF": "analog_bus1"}[net]
        rows.append((net, pin, f"metal3 {SIG_W[net]} µm", f"{length(poly):.0f}", "signal (µA or none)", "-"))
    md = ["| LDO net | harness pin | wire | length (µm) | resistance / IR drop | current density |",
          "|---|---|---|---:|---|---|"] + ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(md)


def draw(size, pins, p):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    W, H = size
    used = {"vdd_5v0": "VIN", "vss_5v0": "VSS", "enable": "EN", "analog_bus0": "FB_BUF",
            "analog_bus1": "EAOUT_BUF", p["vout_pad"]["name"]: "VOUT", p["vref_pad"]["name"]: "VREF"}
    zoom = (p["block_left"] - 25, p["vref_pad"]["box"][1] - 8, W + 4, p["shapes"]["vss_trunk"][5] + 8)
    figs, axes = [], []
    for (x0, y0, x1, y1), title, wid in (
            ((-15, -12, W + 15, H + 12), f"Slot {SLOT} ({W:.2f} × {H:.2f} µm): LDO position and wiring to the harness pins", 22),
            (zoom, f"Slot {SLOT}, zoom: LDO, test buffers, power rails and pin wiring (plan — not drawn in GDS yet)", 16)):
        f, ax = plt.subplots(figsize=(wid, wid * (y1 - y0) / (x1 - x0) + 1.2), dpi=120)
        f.patch.set_facecolor(SURF)
        figs.append(f)
        axes.append(ax)
        ax.set_facecolor(SURF)
        ax.add_patch(Rectangle((0, 0), W, H, fc="#f4f3ef", ec="#9a9893", lw=1.2, zorder=0))
        for name, pin in pins.items():          # harness pins
            b = pin["box"]
            net = used.get(name)
            ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fc=C[net] if net else "#c3c2b7",
                                   ec=INK if net else "#9a9893", lw=0.8, zorder=4))
        for k, (net, layer, a, b, c, d, lab) in p["shapes"].items():
            ax.add_patch(Rectangle((a, b), c - a, d - b, fc=C[net], alpha=0.55 if layer == "metal5" else 0.35,
                                   ec=C[net], lw=0.8, hatch=None if layer == "metal5" else "//", zorder=2))
        for net, poly in p["routes"].items():
            ax.plot([q[0] for q in poly], [q[1] for q in poly], color=C[net], lw=2.2 if wid == 16 else 1.4,
                    zorder=3, solid_joinstyle="miter")
        for k, b in p["cells"].items():
            buf = k in {"RrefEA", "MREFEA_MBIAS", "MPDEA", "MFBBUF", "MEAOUTBUF"}
            ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fc="#ece9e1" if buf else "#d5dfec",
                                   ec="#9a9893" if buf else "#6f8db5", lw=0.7, zorder=1))
        X0, Y0, X1, Y1 = p["ldo"]
        ax.add_patch(Rectangle((X0, Y0), X1 - X0, Y1 - Y0, fill=False, ec="#2a5ea8", lw=1.6, ls="--", zorder=5))
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        ax.set_title(title, loc="left", color=INK, fontsize=13)
        ax.tick_params(colors=INK2, labelsize=9)
        ax.set_xlabel("x (µm)", color=INK2)
        for sp in ax.spines.values():
            sp.set_color("#c3c2b7")
    a0, a1 = axes
    # overview labels: pins
    side = {}
    for name, pin in pins.items():
        b = pin["box"]
        net = used.get(name)
        if name.startswith(("dig_", "clk", "reset", "vbias", "ibias", "analog_bus2", "analog_bus3")):
            continue
        txt = f"{name} → {net}" if net else name
        x = b[2] + 6 if b[0] < W / 2 else b[0] - 6
        a0.text(x, (b[1] + b[3]) / 2 + {"analog_bus0": 9, "analog_bus1": 0, "enable": -9}.get(name, 0), txt, fontsize=8.5, va="center", ha="left" if b[0] < W / 2 else "right",
                color=INK if net else INK2, fontweight="bold" if net else "normal", zorder=6)
    a0.text(8, 150, "unused: dig_out[0:11], dig_in[0:23], reset, clk, vbias, ibias0/1, analog_bus2/3",
            fontsize=8, color=INK2, va="center")
    a0.text(p["ldo"][0] - 120, p["ldo"][3] - 40, "LDO + test\nbuffers", fontsize=10, color="#2a5ea8", ha="center")
    # zoom labels
    for k, (net, layer, a, b, c, d, lab) in p["shapes"].items():
        if k == "vout_land":
            continue
        xm = max(a, zoom[0]) + 4
        a1.text(xm, (b + d) / 2, lab, fontsize=10, color=INK, va="center", zorder=7, clip_on=True,
                bbox=dict(boxstyle="round,pad=0.2", fc=SURF, ec=C[net], lw=1.0, alpha=0.9))
    for net, poly in p["routes"].items():
        q = poly[1] if net == "VREF" else poly[-2]
        a1.text(q[0] + 2, q[1] + (2.5 if net != "EAOUT_BUF" else -3.5), f"{net}  metal3 {SIG_W[net]} µm",
                fontsize=9.5, color=INK, zorder=7, bbox=dict(boxstyle="round,pad=0.2", fc=SURF, ec=C[net], lw=1.0))
    for name, pin in pins.items():
        net = used.get(name)
        b = pin["box"]
        if net and zoom[0] <= b[0] <= zoom[2] and zoom[1] <= b[1] <= zoom[3]:
            a1.text(b[0] - 2, (b[1] + b[3]) / 2, f"{name}\n→ {net}", fontsize=9.5, ha="right", va="center",
                    color=INK, fontweight="bold", zorder=7)
    for k in ("R1R2", "Cc", "MPASS", "v2_nmos_core", "v2_pmos_core", "Rref", "RrefEA"):
        b = p["cells"][k]
        a1.text(b[0] + 1, b[3] - 1.5, {"v2_nmos_core": "NMOS", "v2_pmos_core": "PMOS", "R1R2": "R1/R2",
                                       "RrefEA": "RrefEA (test buffer bias)"}.get(k, k),
                fontsize=8.5, color=INK2, va="top", zorder=6)
    from matplotlib.lines import Line2D
    a1.legend(handles=[Line2D([], [], color=C[n], lw=6 if n in ("VIN", "VSS", "VOUT") else 2.2, label=n)
                       for n in ("VIN", "VOUT", "VSS", "VREF", "EN", "FB_BUF")],
              labels=["VIN (metal5)", "VOUT (metal5)", "VSS (metal5)", "VREF", "EN",
                      "FB_BUF / EAOUT_BUF (test)"],
              loc="lower left", ncol=6, frameon=False, fontsize=10, labelcolor=INK)
    for f, name in zip(figs, ("slot_plan.png", "slot_plan_zoom.png")):
        f.tight_layout()
        f.savefig(HERE / name, facecolor=SURF)


def main():
    size, pins, place = load()
    p = plan(size, pins, place)
    md = report(p)
    (HERE / "slot_plan.md").write_text(f"Slot {SLOT} wiring plan\n\n" + md + "\n")
    print(md)
    print("LDO rectangle in the slot: x {:.1f}..{:.1f}, y {:.1f}..{:.1f}".format(*[p["ldo"][i] for i in (0, 2, 1, 3)]))
    draw(size, pins, p)


if __name__ == "__main__":
    main()
