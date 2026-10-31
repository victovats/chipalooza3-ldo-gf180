#!/usr/bin/env python3
"""Build the LDO layout: gLayout transistors + PDK resistors/cap, channel-routed in magic.

    cd layout && python3 build_layout.py

Devices:
  * transistors come from gLayout (gl_devices.py, run in the gLayout Python
    environment), converted to 5/6 V devices with the DUALGATE / V5_XTOR
    markers. gLayout already joins the fingers of each device onto metal2
    bars (gate bar below the device, source/drain bars above) and draws the
    bulk tap ring. Matched pairs (input pair, mirror load, cascodes, bias mirrors) use
    common-centroid ABBA finger order with a dummy finger at each end.
  * poly resistors and the MIM capacitor come from the PDK's magic generator.

Routing: devices sit in horizontal rows. From each terminal bar a metal3 stub
runs vertically into the routing channel above or below the row (whichever
side the bar is on). In each channel every net gets its own metal2 track;
nets that touch several channels, and the block pins, are joined by metal3
trunks in a spine on the left edge, where the pins are labelled.

Outputs:
    mag/ldo.mag (+ device cells)   magic layout
    gds/ldo.gds                    GDS
    drc.txt                        magic DRC report
    lvs/ldo_lay.spice              extracted netlist
    lvs/comp.out                   netgen LVS report vs netlist/schematic/ldo.spice
"""
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MAG, GDS, LVS, GL = HERE / "mag", HERE / "gds", HERE / "lvs", HERE / "gl"
PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")
PDK = "gf180mcuD"
RC = f"{PDK_ROOT}/{PDK}/libs.tech/magic/{PDK}.magicrc"
NETGEN_SETUP = f"{PDK_ROOT}/{PDK}/libs.tech/netgen/{PDK}_setup.tcl"
MAGIC = shutil.which("magic") or "/foss/tools/magic/bin/magic"
NETGEN = shutil.which("netgen") or "/foss/tools/netgen/bin/netgen"
# Python with gLayout installed (gLayout needs Python <= 3.11 and gdsfactory 7)
GLPY = os.environ.get("GLAYOUT_PYTHON", "/headless/glayout-venv311/bin/glpy")
SCH_NETLIST = REPO / "netlist" / "schematic" / "ldo.spice"
TOP = "ldo"

UM = 200                       # magic internal units per micron (5 nm grid)
def um(x):
    return int(round(x * UM))

# via / pad geometry (internal units), from the gf180mcuD magic DRC deck
V12, V = 52, 56                # via1 cut region 0.26 um; via2/3/4 0.28 um
PADX, PADY = 76, 68            # 0.38 x 0.34 um metal pad around a via (0.06 / 0.04 surround)
SP = 60                        # metal2/3/4 spacing 0.28 um, rounded up
STUB_GAP = PADX + SP + 4       # minimum x distance between two vertical stubs
SIG_W, PWR_W = 76, 200         # track widths (power tracks carry only bias currents; the
                               # 10 mA load current goes pass device -> straps -> metal5 buses)
POWER = {"VIN", "VOUT", "VSS"}
PORTS = ["VIN", "VSS", "VOUT", "VREF", "EN", "FB_BUF", "EAOUT_BUF"]
INTERNAL_LABELS = ["FB", "EAOUT"]     # named (not pins) for post-layout simulation probes
BUS_W = um(4.0)                # metal5 VSS bus along the bottom edge
BUS_W_TOP = um(6.0)            # metal5 VIN / VOUT buses over the pass-device corner: 10 mA / 6 um
                               # = 1.7 mA/um (EM limit 2.2 at 110 C), short so the IR drop is small
PWR_TRUNK, SIG_TRUNK = um(1.0), 100   # metal4 trunk widths
PASS_STRAP, PASS_PITCH = um(2.6), um(3.2)  # pass-device metal4 straps (alternating VIN / VOUT):
                                           # ~2 mA each -> <1.0 mA/um, 4 vias per row
DEV_GAP = um(2.0)              # spacing between device bounding boxes in a row
# extra space left of a device: a corridor for the VIN / VOUT trunks to reach the
# top buses between devices instead of over them (cap keep-out + 2 power trunks)
EXTRA_GAP = {"MPASS": um(7.5)}

RES, CAP = "gf180mcu::ppolyf_u_1k_6p0", "gf180mcu::cap_mim_2p0fF"

# magic extracts a snake resistor shorter than its drawn length: each bend
# counts BEND_LOSS[w] um less. Segment length is lengthened to compensate so
# the extracted r_length matches the schematic, then snapped to the 5 nm grid.
BEND_LOSS = {1: 0.5725, 2: 1.549}


def res(w, total_l, nx):
    seg = (total_l + BEND_LOSS[w] * (nx - 1)) / nx
    return RES, f"w {w} l {round(seg / 0.005) * 0.005:.3f} nx {nx} snake 1"


def fet(t, w, l, nf=1, stubs=None, mult=1):
    """gLayout single device (mult > 1: that many rows of nf fingers in one
    guard ring). 5 V marker for L below the 6 V minimum (nfet 0.7, pfet 0.55)."""
    return dict(type=t, w=w, l=l, nf=nf, mult=mult, numcols=1, v5=l < (0.7 if t == "nmos" else 0.55),
                stubs=stubs or {})


def match(t, w, l, pattern="ABBA"):
    """Matched pair (gl_devices.pattern_pair): unit fingers of width w placed in
    `pattern` (ABBA = common centroid), a dummy finger at each end tied to bulk."""
    return dict(type=t, w=w, l=l, nf=1, numcols=1, pattern=pattern,
                v5=l < (0.7 if t == "nmatch" else 0.55), stubs={})


# Feedback divider: R1 = 7 units, R2 = 4 units of one 2 x 49.33 um strip
# (R1 345.31 um, R2 197.32 um vs 345.30 / 197.24 in the schematic). Unit order
# is symmetric, so both resistors share the same centroid (unit 6); D = dummy.
RDIV_PATTERN = "DAABABABABAAD"
RDIV_UNIT_L = 49.33
RDIV_CELL = "res_r1r2_array"


def make_res_array(gencell_name, nets_order=("A", "B")):
    """Wrap the PDK unit-resistor array in a cell that chains the units in series.

    Each unit end leaves the guard ring on a metal2 stub; consecutive units of
    the same resistor are joined by metal3 straps above / below the array
    (alternating, so each chain snakes), with straps sorted onto levels so they
    never overlap. Dummy units are shorted to the guard ring (the bulk). The
    chain ends and the bulk come out on metal2 stubs beyond the straps.
    Writes mag/<RDIV_CELL>.mag; returns (terminals, bbox) where terminals are
    [(key, x, y, dir)] with keys A_start, A_end, B_start, B_end, BULK."""
    rects, props = parse_mag(MAG / f"{gencell_name}.mag")
    pcs = sorted(rects["polycontact"])
    tops = sorted([r for r in pcs if r[1] > 0], key=lambda r: r[0])
    bots = sorted([r for r in pcs if r[1] < 0], key=lambda r: r[0])
    assert len(tops) == len(bots) == len(RDIV_PATTERN)
    cx = [(r[0] + r[2]) // 2 for r in tops]
    ty, by = (tops[0][1] + tops[0][3]) // 2, (bots[0][1] + bots[0][3]) // 2
    m1 = rects["metal1"]
    ring_top, ring_bot = max(r[3] for r in m1), min(r[1] for r in m1)
    subc = sorted((r for k, v in rects.items() if k.endswith("subdiffcont") for r in v), key=lambda r: r[0])
    ringL, ringR = subc[0], subc[-1]

    paint = defaultdict(list)
    def pad(layer, x, y, w=PADX, h=PADY):
        paint[layer].append((x - w // 2, y - h // 2, x + w // 2, y + h // 2))
    def via(kind, x, y):
        c = V12 if kind == "via1" else V
        lo, hi = ("metal1", "metal2") if kind == "via1" else ("metal2", "metal3")
        pad(lo, x, y); pad(hi, x, y)
        paint[kind].append((x - c // 2, y - c // 2, x + c // 2, y + c // 2))

    # series links: chain units of each resistor in pattern order, alternating top / bottom
    links, ends = [], {}
    for dev in nets_order:
        idx = [i for i, d in enumerate(RDIV_PATTERN) if d == dev]
        side = "top"
        for a_, b_ in zip(idx, idx[1:]):
            links.append((side, a_, b_))
            side = "bot" if side == "top" else "top"
        ends[f"{dev}_start"] = (idx[0], "bot")
        ends[f"{dev}_end"] = (idx[-1], side)    # the side the last link did not use
    # strap levels per side (interval colouring)
    level = {}
    for side in ("top", "bot"):
        last = []
        for lk in sorted((l for l in links if l[0] == side), key=lambda l: cx[l[1]]):
            x1 = cx[lk[1]] - PADX // 2
            k = next((i for i, e in enumerate(last) if e + SP + 10 < x1), None)
            if k is None:
                last.append(0); k = len(last) - 1
            last[k] = cx[lk[2]] + PADX // 2
            level[lk] = k
    nlev = {side: 1 + max([v for l, v in level.items() if l[0] == side], default=-1) for side in ("top", "bot")}
    pitch = PADX + SP + 10
    def lev_y(side, k):
        return ring_top + SP + PADX // 2 + k * pitch if side == "top" else ring_bot - SP - PADX // 2 - k * pitch
    term_y = {side: lev_y(side, nlev[side]) + (SP if side == "top" else -SP) for side in ("top", "bot")}

    reach = {}                               # (unit, side) -> outermost y its metal2 stub must reach
    for lk, k in level.items():
        side, a_, b_ = lk
        y = lev_y(side, k)
        for u in (a_, b_):
            reach[(u, side)] = y
            via("via2", cx[u], y)
        paint["metal3"].append((cx[a_] - PADX // 2, y - PADY // 2, cx[b_] + PADX // 2, y + PADY // 2))
    terms = []
    for key, (u, side) in ends.items():
        reach[(u, side)] = term_y[side]
        terms.append((key, cx[u], term_y[side], "up" if side == "top" else "down"))
    for (u, side), y in reach.items():
        cy = ty if side == "top" else by
        via("via1", cx[u], cy)
        y1, y2 = (cy, y + PADY // 2) if side == "top" else (y - PADY // 2, cy)
        paint["metal2"].append((cx[u] - PADX // 2, y1, cx[u] + PADX // 2, y2))
    # dummies: both ends shorted to the nearest guard-ring contact column on metal1
    for i, d in enumerate(RDIV_PATTERN):
        if d != "D":
            continue
        col = ringL if i == 0 else ringR
        for c in (tops[i], bots[i]):
            paint["metal1"].append((min(col[0], c[0]), c[1], max(col[2], c[2]), c[3]))
    # bulk: guard-ring corner -> metal2 stub out below the bottom straps
    bx, bcy = (ringL[0] + ringL[2]) // 2, (min(m1, key=lambda r: r[1])[1] + min(m1, key=lambda r: r[1])[3]) // 2
    via("via1", bx, bcy)
    paint["metal2"].append((bx - PADX // 2, term_y["bot"] - PADY // 2, bx + PADX // 2, bcy))
    terms.append(("BULK", bx, term_y["bot"], "down"))

    allr = [r for v in paint.values() for r in v] + [r for v in rects.values() for r in v]
    bb = bbox(allr)
    out = ["magic", f"tech {PDK}", "magscale 1 10", "timestamp 0"]
    for layer in ("metal1", "metal2", "metal3", "via1", "via2"):
        if paint[layer]:
            out.append(f"<< {layer} >>")
            out += [f"rect {r[0]} {r[1]} {r[2]} {r[3]}" for r in paint[layer]]
    fb = props.get("FIXED_BBOX", " ".join(map(str, bbox([r for v in rects.values() for r in v]))))
    out += [f"use {gencell_name}  units", f"timestamp {props.get('timestamp', '0')}",
            "transform 1 0 0 0 1 0", f"box {fb}",
            "<< properties >>", f"string FIXED_BBOX {' '.join(map(str, bb))}", "<< end >>"]
    (MAG / f"{RDIV_CELL}.mag").write_text("\n".join(out) + "\n")
    return terms, bb


# (instance, kind, spec, nets). Values match xschem/ldo.sch.
# fet nets: D, G, S, B. Pair nets: A_D, A_G, A_S (device A), B_D, B_G, B_S, B (bulk).
ROWS = [
    # row 0 (bottom): NMOS. Level shifter + enable pulldowns on the left, test
    # buffers and bias mirrors in the middle, error-amp input pair on the right
    # (under its PMOS load and the pass device).
    [("MN1", "gl", fet("nmos", 0.5, 5), dict(D="ENB_5V", G="EN", S="VSS", B="VSS")),
     ("MN2", "gl", fet("nmos", 5, 0.6), dict(D="EN_5V", G="ENB_5V", S="VSS", B="VSS")),
     ("MENDISCHARGE", "gl", fet("nmos", 5, 0.6), dict(D="VOUT", G="ENB_5V", S="VSS", B="VSS")),
     ("MPDEA", "gl", fet("nmos", 1, 0.6), dict(D="IREF_EA", G="ENB_5V", S="VSS", B="VSS")),
     ("MFBBUF", "gl", fet("nmos", 5, 0.6), dict(D="VIN", G="FB", S="FB_BUF", B="VSS")),
     ("MEAOUTBUF", "gl", fet("nmos", 5, 0.6), dict(D="VIN", G="EAOUT", S="EAOUT_BUF", B="VSS")),
     # buffer bias mirror: MREFEA (A, diode) -> MBIASEA (B), MBIASFB (C)
     ("MREFEA_MBIAS", "gl", match("nmatch", 2.5, 0.6, "BACCAB"),
      dict(A_D="IREF_EA", A_G="IREF_EA", A_S="VSS", B_D="EAOUT_BUF", B_G="IREF_EA", B_S="VSS",
           C_D="FB_BUF", C_G="IREF_EA", C_S="VSS", B="VSS")),
     ("MPDREF", "gl", fet("nmos", 1, 0.6), dict(D="IREF", G="ENB_5V", S="VSS", B="VSS")),
     # Rref sets IREF: placed between its pulldown and the tail mirror it feeds
     ("Rref", "res", res(1, 194.27, 20), dict(A="IREF", B="VIN_BIAS", BULK="VSS")),
     # tail-current mirror: MREF (A, diode) / MTAIL (B)
     ("MREF_MTAIL", "gl", match("nmatch", 2.5, 0.6),
      dict(A_D="IREF", A_G="IREF", A_S="VSS", B_D="TAIL", B_G="IREF", B_S="VSS", B="VSS")),
     # input pair: MIN1 (A) D=EAREF G=FB, MIN2 (B) D=EAOUT G=VREF, common source TAIL
     ("MIN1_MIN2", "gl", match("nmatch", 10, 3),
      dict(A_D="EAREF", A_G="FB", A_S="TAIL", B_D="EAOUT", B_G="VREF", B_S="TAIL", B="VSS"))],
    # row 1: PMOS. Level shifter / bias switch on the left,
    # EAOUT pull-up, cascodes and mirror load on the right.
    [("MP1", "gl", fet("pmos", 1, 40), dict(D="ENB_5V", G="VSS", S="VIN", B="VIN")),
     ("MP2", "gl", fet("pmos", 5, 0.6), dict(D="EN_5V", G="ENB_5V", S="VIN", B="VIN")),
     ("MBIASSW", "gl", fet("pmos", 5, 0.6, 2), dict(D="VIN_BIAS", G="ENB_5V", S="VIN", B="VIN")),
     ("MENPASSOFF", "gl", fet("pmos", 5, 0.6), dict(D="VIN", G="EN_5V", S="EAOUT", B="VIN")),
     # cascodes: MCASC1 (A) / MCASC2 (B), shared gate EAREF
     ("MCASC1_MCASC2", "gl", match("pmatch", 2.5, 0.55),
      dict(A_D="CASCB1", A_G="EAREF", A_S="EAREF", B_D="EAOUT", B_G="EAREF", B_S="CASCB2", B="VIN")),
     # mirror load: MLOAD1 (A, diode-connected) / MLOAD2 (B)
     ("MLOAD1_MLOAD2", "gl", match("pmatch", 5, 3),
      dict(A_D="CASCB1", A_G="CASCB1", A_S="VIN", B_D="CASCB2", B_G="CASCB1", B_S="VIN", B="VIN"))],
    # row 2 (top): buffer-bias resistor, feedback divider, Miller cap next to
    # the pass device (short EAOUT / VOUT), pass device under the power buses.
    [("RrefEA", "res", res(1, 1944.26, 40), dict(A="IREF_EA", B="VIN_BIAS", BULK="VSS")),
     # feedback divider R1 (A, 7 units) / R2 (B, 4 units) interleaved, see make_res_array
     ("R1R2", "resarray", (RES, f"w 2 l {RDIV_UNIT_L} nx {len(RDIV_PATTERN)} snake 0"),
      dict(A_start="FB", A_end="VOUT", B_start="VSS", B_end="FB", BULK="VSS")),
     ("Cc", "cap", (CAP, "w 38.6 l 38.6"), dict(TOP="EAOUT", BOT="VOUT")),
     # pass device: 7 rows x 30 fingers x 3 um = 630 um in one guard ring; every
     # row's source / drain bar is strapped up to the VIN / VOUT buses (PASS_STRAP)
     ("MPASS", "gl", fet("pmos", 3, 0.55, 30, mult=7), dict(D="VOUT", G="EAOUT", S="VIN", B="VIN"))],
]


def gl_cell(spec):
    tag = f"{spec['w']}x{spec['l']}_{spec['nf'] if spec['type'] in ('nmos', 'pmos') else spec['pattern']}"
    if spec.get("mult", 1) > 1:
        tag += f"x{spec['mult']}"
    return f"gl_{spec['type']}_{tag}".replace(".", "p")


# --------------------------------------------------------------------- magic
def run_magic(script, cwd):
    p = subprocess.run([MAGIC, "-dnull", "-noconsole", "-rcfile", RC, script], cwd=cwd,
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1800)
    return p.stdout + p.stderr


def gen_devices():
    """Create every device cell in mag/. Returns {instance: cellname}, gLayout terminal bars."""
    cache_f = MAG / "devices.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}

    # gLayout transistors -> gl/<cell>.gds -> mag/<cell>.mag
    gl_specs = {gl_cell(s): {k: v for k, v in s.items() if k != "stubs"}
                for row in ROWS for (_, kind, s, _) in row if kind == "gl"}
    terms_f = GL / "terms.json"
    terms = json.loads(terms_f.read_text()) if terms_f.exists() else {}
    need = {c: s for c, s in gl_specs.items() if c not in terms or not (MAG / f"{c}.mag").exists()
            or cache.get(c) != s}
    if need:
        GL.mkdir(exist_ok=True)
        (GL / "_spec.json").write_text(json.dumps(need))
        p = subprocess.run([GLPY, str(HERE / "gl_devices.py"), str(GL / "_spec.json"), str(GL)],
                           capture_output=True, text=True)
        done = set(re.findall(r"^GL (\S+)", p.stdout, re.M))
        if done != set(need):
            sys.exit(f"gLayout generation failed for {set(need) - done}\n{p.stdout[-1500:]}{p.stderr[-3000:]}")
        (GL / "_spec.json").unlink()
        lines = [f"gds read ../gl/{c}.gds" for c in need] + ["writeall force", "quit -noprompt"]
        (MAG / "_gds.tcl").write_text("\n".join(lines) + "\n")
        run_magic("_gds.tcl", MAG)
        (MAG / "_gds.tcl").unlink()
        cache.update(need)
        terms = json.loads(terms_f.read_text())

    # PDK resistors and cap via magic gencell
    pdk_keys = {"|".join(spec) for row in ROWS for (_, kind, spec, _) in row if kind != "gl"}
    need = sorted(pdk_keys - set(cache))
    if need:
        lines = []
        for i, key in enumerate(need):
            g, p = key.split("|")
            lines += [f"load hold{i} -silent", "box 0 0 0 0", f"magic::gencell {g} d{i} {p}",
                      f'puts "CELL {i} [cellname list children hold{i}]"']
        lines += ["writeall force", "quit -noprompt"]
        (MAG / "_gen.tcl").write_text("\n".join(lines) + "\n")
        out = run_magic("_gen.tcl", MAG)
        for m in re.finditer(r"^CELL (\d+) (\S+)", out, re.M):
            cache[need[int(m.group(1))]] = m.group(2)
        missing = [k for k in need if k not in cache]
        if missing:
            sys.exit(f"device generation failed for {missing}\n{out[-3000:]}")
        for f in MAG.glob("hold*.mag"):
            f.unlink()
        (MAG / "_gen.tcl").unlink()

    # drop cells no longer used
    used = set(gl_specs) | pdk_keys
    for k in [k for k in cache if k not in used]:
        v = cache.pop(k)
        (MAG / f"{k if k.startswith('gl_') else v}.mag").unlink(missing_ok=True)
    cache_f.write_text(json.dumps(cache, indent=1) + "\n")

    cells = {}
    for row in ROWS:
        for inst, kind, spec, _ in row:
            cells[inst] = gl_cell(spec) if kind == "gl" else cache["|".join(spec)]
            if kind == "resarray":
                cells[inst] = (RDIV_CELL, cache["|".join(spec)])
    return cells, terms


def parse_mag(path):
    rects, props, layer = defaultdict(list), {}, None
    for line in path.read_text().splitlines():
        m = re.match(r"<< (\S+) >>", line)
        if m:
            layer = m.group(1)
        elif line.startswith("rect ") and layer != "checkpaint":
            rects[layer].append(tuple(map(int, line.split()[1:5])))
        elif line.startswith("string "):
            _, k, v = line.split(None, 2)
            props[k] = v
        elif line.startswith("timestamp"):
            props.setdefault("timestamp", line.split()[1])
    return rects, props


def bbox(rs):
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


# ------------------------------------------------------------ terminals
def gl_terms(bars, nets, cy, kmap):
    """Pick stub positions on gLayout metal2 bars -> [(net, x, y, dir, 'm2')].

    Bars above the device centre exit up, bars below exit down. Within each
    side, stubs keep STUB_GAP apart; narrow bars choose first."""
    groups = defaultdict(list)
    for t, (xl, xr, y) in bars.items():
        groups["up" if um(y) > cy else "down"].append((t, um(xl), um(xr), um(y)))
    out = []
    for dr, lst in groups.items():
        # slots interleave the terminals (S, D, S, D, ...) and spread end to end
        ks = {t: kmap.get(t, 1) for t, *_ in lst}
        slots = [t for i in range(max(ks.values())) for t, *_ in lst if i < ks[t]]
        info = {t: (xl, xr, y) for t, xl, xr, y in lst}
        taken = []
        for j, t in enumerate(slots):
            xl, xr, y = info[t]
            lo, hi = xl + PADX // 2 + 10, xr - PADX // 2 - 10
            if hi < lo:
                lo = hi = (xl + xr) // 2
            pref = (lo + hi) // 2 if len(slots) == 1 else lo + j * (hi - lo) // (len(slots) - 1)
            cands = sorted(range(lo, hi + 1, 5), key=lambda x: abs(x - pref)) or [lo]
            x = next((c for c in cands if all(abs(c - q) >= STUB_GAP for q in taken)), None)
            if x is None:
                sys.exit(f"no room for a stub on bar {t}")
            taken.append(x)
            out.append((nets[t], x, y, dr, "m2"))
    return out


def ring_corner(rects):
    """Bulk tap point of a magic-generated guard ring: left contact column x, bottom metal1 bar y."""
    subc = [r for k, v in rects.items() if k.endswith("subdiffcont") for r in v]
    left = min(subc, key=lambda r: r[0])
    bot = min(rects["metal1"], key=lambda r: r[1])
    return (left[0] + left[2]) // 2, (bot[1] + bot[3]) // 2


def res_terms(rects, nets):
    pcs = sorted(rects["polycontact"])
    assert len(pcs) == 2 and pcs[0][1] == pcs[1][1], "resistor ends not both at the bottom"
    terms = [(nets[k], (p[0] + p[2]) // 2, (p[1] + p[3]) // 2, "down", "m1") for k, p in zip("AB", pcs)]
    bx, by = ring_corner(rects)
    return terms + [(nets["BULK"], bx, by, "down", "m1")]


# ------------------------------------------------------------ build
class Layout:
    def __init__(self):
        self.paint = defaultdict(list)      # layer -> rects (top-cell coords)
        self.uses = []                      # (cell, inst, tx, ty, fixed_bbox, timestamp)

    def rect(self, layer, x1, y1, x2, y2):
        self.paint[layer].append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))

    def pad(self, layer, x, y, w=PADX, h=PADY):
        self.rect(layer, x - w // 2, y - h // 2, x + w // 2, y + h // 2)

    def via(self, kind, x, y, stack=False):
        """stack=True: 0.4 x 0.4 um pads, so a metal square between two stacked
        vias meets the 0.1444 um^2 minimum area."""
        lo, hi = {"via1": ("metal1", "metal2"), "via2": ("metal2", "metal3"),
                  "via3": ("metal3", "metal4"), "via4": ("metal4", "metal5")}[kind]
        c = V12 if kind == "via1" else V
        pw, ph = (80, 80) if stack else (PADX, PADY)
        self.pad(lo, x, y, pw, ph)
        self.pad(hi, x, y, *((88, 88) if hi == "metal5" else (pw, ph)))
        self.rect(kind, x - c // 2, y - c // 2, x + c // 2, y + c // 2)


def build(cells, gl_bars):
    L = Layout()
    devs = {}
    for row in ROWS:
        for inst, kind, spec, nets in row:
            if kind == "resarray":
                wrapper, units = cells[inst]
                terms, bb = make_res_array(units)
                rects, props = parse_mag(MAG / f"{wrapper}.mag")
                devs[inst] = dict(kind=kind, spec=spec, cell=wrapper, rects=rects, props=props, nets=nets,
                                  bb=bb, terms=terms)
                continue
            rects, props = parse_mag(MAG / f"{cells[inst]}.mag")
            devs[inst] = dict(kind=kind, spec=spec, cell=cells[inst], rects=rects, props=props, nets=nets,
                              bb=bbox([r for v in rects.values() for r in v]))
    row_h = [max(devs[d[0]]["bb"][3] - devs[d[0]]["bb"][1] for d in row) for row in ROWS]
    NCH = len(ROWS)                       # channel c lies below row c; channel NCH is above the top row

    row_w = [sum(devs[d[0]]["bb"][2] - devs[d[0]]["bb"][0] + EXTRA_GAP.get(d[0], 0) for d in row)
             + DEV_GAP * (len(row) - 1) for row in ROWS]
    WMAX = max(row_w)

    def place_terms(shift):
        stubs = defaultdict(list)         # channel -> [net, x, y(cell), dir, from-layer, inst]
        pos = {}
        for r, row in enumerate(ROWS):
            # rows below the top row are spread over the full width: the extra space
            # goes into the gaps between devices, which become corridors for the
            # vertical wires so nothing is routed over a device
            spread = (WMAX - row_w[r]) // (len(row) - 1) if r < len(ROWS) - 1 and len(row) > 1 else 0
            x = (0 if spread else WMAX - row_w[r]) - shift.get(r, 0)
            for inst, kind, spec, nets in row:
                d = devs[inst]
                x += EXTRA_GAP.get(inst, 0)
                tx = x - d["bb"][0]
                pos[inst] = (tx, r)
                x += d["bb"][2] - d["bb"][0] + DEV_GAP + spread
                if kind == "gl":
                    bars = gl_bars[d["cell"]]
                    if spec.get("mult", 1) > 1:      # row bars are strapped to the buses instead
                        bars = {k: v for k, v in bars.items() if k in ("G", "B")}
                    terms = gl_terms(bars, nets, (d["bb"][1] + d["bb"][3]) // 2, spec["stubs"])
                elif kind == "res":
                    terms = res_terms(d["rects"], nets)
                elif kind == "resarray":
                    terms = [(nets[k], x, y, dr, "m2") for k, x, y, dr in d["terms"]]
                else:
                    m4b = min(d["rects"]["metal4"], key=lambda q: q[1])
                    mcc = d["rects"]["mimcapcontact"][0]
                    terms = [(nets["BOT"], m4b[0] + um(2), None, "down", "m4b"),
                             (nets["TOP"], mcc[2] - um(3), None, "down", "m4t")]
                for net, sx, sy, dr, lay in terms:
                    stubs[r if dr == "down" else r + 1].append([net, tx + sx, sy, dr, lay, inst])
        return stubs, pos

    def track_order(stubs_c):
        downs = [s for s in stubs_c if s[3] == "down" and s[4] in ("m1", "m2")]
        ups = [s for s in stubs_c if s[3] == "up"]
        nets = list(dict.fromkeys(s[0] for s in stubs_c))
        below = defaultdict(set)
        for a in downs:
            for b in ups:
                if a[0] != b[0] and abs(a[1] - b[1]) < STUB_GAP:
                    below[a[0]].add(b[0])
        indeg = {n: 0 for n in nets}
        for a in below:
            for b in below[a]:
                indeg[b] += 1
        order, ready = [], [n for n in nets if indeg[n] == 0]
        while ready:
            ready.sort(key=lambda n: (n not in POWER, n))
            n = ready.pop(0)
            order.append(n)
            for b in below[n]:
                indeg[b] -= 1
                if indeg[b] == 0:
                    ready.append(b)
        return order if len(order) == len(nets) else None

    # shift rows 1 and 2 sideways until every channel's constraint graph is acyclic
    for s1 in range(0, um(8), um(0.5)):
        for s2 in range(0, um(4), um(0.5)):
            shift = {0: s2, 1: s1}
            stubs, pos = place_terms(shift)
            orders = {c: track_order(stubs[c]) for c in range(NCH + 1)}
            if all(o is not None for o in orders.values()):
                break
        else:
            continue
        break
    else:
        sys.exit("could not find an acyclic track order")

    def tw(net, c):
        return PWR_W if net in POWER else SIG_W

    BOT_BUS = ("VSS",)                            # metal5 bus(es) along the bottom edge
    bus_y = {}
    y = um(1.0)
    for n in BOT_BUS:
        bus_y[n] = y + BUS_W // 2
        y += BUS_W + um(1.2)
    track_y, row_base = {}, []
    for c in range(NCH + 1):
        top_margin = um(2.6) if c == 2 else um(0.8)     # channel 2 also holds the cap's via4
        y += um(0.8)
        ys = []
        for net in reversed(orders[c]):                  # orders run top -> bottom
            w = tw(net, c)
            ys.append((net, y + w // 2))
            y += w + SP
        y += top_margin
        for net, cy in ys:
            track_y[(c, net)] = cy
        if c < NCH:
            row_base.append(y)
            y += row_h[c]
    # metal5 power buses across the top edge; signal pins come out above them
    yb = y + um(1.5)
    bus_w = {"VSS": BUS_W, "VOUT": BUS_W_TOP, "VIN": BUS_W_TOP}
    for n in ("VOUT", "VIN"):
        bus_y[n] = yb + BUS_W_TOP // 2
        yb += BUS_W_TOP + um(1.2)
    y_top = yb + um(1.0)
    ch_nets = defaultdict(set)
    for (c, net) in track_y:
        ch_nets[net].add(c)

    X0 = um(2)                                   # left margin
    x_right = X0 + max(tx + devs[i]["bb"][2] for i, (tx, r) in pos.items()) + um(2)   # right margin
    for inst, (tx, r) in pos.items():
        d = devs[inst]
        ty = row_base[r] - d["bb"][1]
        L.uses.append((d["cell"], inst, X0 + tx, ty, d["props"].get("FIXED_BBOX"), d["props"].get("timestamp", "0")))
        d["origin"] = (X0 + tx, ty)
    for c in stubs:
        for st in stubs[c]:
            st[1] += X0

    obstacles = []                               # metal4 rectangles trunks must keep clear of

    # --- pass device: metal4 straps from every row's source / drain bar to the VIN / VOUT buses
    pinst = next(i for row in ROWS for i, k, sp, _ in row if k == "gl" and sp.get("mult", 1) > 1)
    pd = devs[pinst]
    pbars = gl_bars[pd["cell"]]
    ox, oy = pd["origin"]
    xl, xr = um(pbars["S0"][0]), um(pbars["S0"][1])
    nrow = pd["spec"]["mult"]
    xs, x, k = [], xl + um(1.0) + PASS_STRAP // 2, 0
    while x + PASS_STRAP // 2 <= xr - um(1.0):
        xs.append((x, "S" if k % 2 == 0 else "D"))
        x += PASS_PITCH
        k += 1
    for sx, t in xs:
        net = pd["nets"][t]
        bars_y = [um(pbars[f"{t}{i}"][2]) for i in range(nrow)]
        gx = ox + sx
        for by_ in bars_y:              # via2 + via3 arrays across the strap width on each row's bar
            gy = oy + by_
            x1, x2 = gx - PASS_STRAP // 2, gx + PASS_STRAP // 2
            L.rect("metal3", x1, gy - 50, x2, gy + 50)
            L.rect("via2", x1 + 10, gy - 40, x2 - 10, gy + 40)
            L.rect("via3", x1 + 10, gy - 40, x2 - 10, gy + 40)
        top = bus_y[net] + BUS_W_TOP // 2
        L.rect("metal4", gx - PASS_STRAP // 2, oy + min(bars_y) - 50, gx + PASS_STRAP // 2, top)
        L.rect("via4", gx - PASS_STRAP // 2 + 10, bus_y[net] - BUS_W_TOP // 2 + 10, gx + PASS_STRAP // 2 - 10, top - 10)
    obstacles.append((ox + pd["bb"][0] - SP, oy + pd["bb"][1], ox + pd["bb"][2] + SP, y_top))

    # --- stubs: metal3 from the terminal to the net's metal2 track
    xs_net = defaultdict(list)
    track_vias = defaultdict(list)        # (channel, net) -> x of metal3 stubs landing on the track
    for c, lst in stubs.items():
        for net, sx, sy, dr, lay, inst in lst:
            ox, oy = devs[inst]["origin"]
            ty = track_y[(c, net)]
            xs_net[(c, net)].append(sx)
            if lay in ("m1", "m2"):
                vy = oy + sy
                if lay == "m1":
                    L.via("via1", sx, vy, stack=True)
                L.via("via2", sx, vy, stack=lay == "m1")
                y1, y2 = (ty - PADY // 2, vy) if dr == "down" else (vy, ty + PADY // 2)
                L.rect("metal3", sx - PADX // 2, y1, sx + PADX // 2, y2)
                track_vias[(c, net)].append((sx, False))
            else:   # MIM cap plates come down on metal4, then via3 + via2 onto the track
                d = devs[inst]
                m4b = min(d["rects"]["metal4"], key=lambda q: q[1])
                if lay == "m4b":
                    top = oy + m4b[3]
                    L.rect("metal4", sx - PADX // 2, ty - PADY // 2, sx + PADX // 2, top)
                else:
                    mcc = d["rects"]["mimcapcontact"][0]
                    vy = oy + m4b[1] - um(1.6)   # MIMTM.1: 1.2 um from the bottom plate
                    L.rect("metal5", sx - 44, vy - 44, sx + 44, oy + (mcc[1] + mcc[3]) // 2)
                    L.via("via4", sx, vy)
                    L.rect("metal4", sx - PADX // 2, ty - PADY // 2, sx + PADX // 2, vy)
                    top = vy + 44
                obstacles.append((sx - PADX // 2 - SP, ty - PADY // 2, sx + PADX // 2 + SP, top))
                L.via("via3", sx, ty, stack=True)
                L.via("via2", sx, ty, stack=True)
                track_vias[(c, net)].append((sx, True))     # has its own via2 already
    for inst, d in devs.items():                 # nothing routed over any device
        if d["kind"] in ("res", "resarray", "gl"):
            ox, oy = d["origin"]
            m = um(1.0) if d["kind"] != "gl" else SP
            obstacles.append((ox + d["bb"][0] - m, oy + d["bb"][1] - m, ox + d["bb"][2] + m, oy + d["bb"][3] + m))
    for inst, d in devs.items():                 # MIM cap bottom plate is metal4
        if d["kind"] == "cap":
            ox, oy = d["origin"]
            m = um(1.25)                         # MIMTM.1: 1.2 um from unrelated metal
            obstacles.append((ox + d["bb"][0] - m, oy + d["bb"][1] - m, ox + d["bb"][2] + m, oy + d["bb"][3] + m))

    # via2 where metal3 stubs land on their track. Same-net stubs closer than the
    # metal3 spacing are bridged on metal3; if also closer than the via2 spacing,
    # they share one via.
    for (c, net), xs_ in track_vias.items():
        ty = track_y[(c, net)]
        last = None
        for x, has_via in sorted(xs_):
            if last is not None and x - last < STUB_GAP + 4:
                L.rect("metal3", last, ty - 40, x, ty + 40)    # as tall as a stacked-via pad (no notch)
                if x - last < V + 48 + 4 and not has_via:
                    continue
            if not has_via:
                L.via("via2", x, ty)
            last = x

    # --- local metal4 trunks: one per net that spans channels, is a pin, or must reach a bus.
    # Each sits at the x closest to the middle of its own stubs that keeps clear of
    # other trunks, the cap, the pass-device straps and other nets' metal3 stubs.
    need = sorted({n for n in ch_nets if len(ch_nets[n]) > 1 or n in PORTS or n in POWER},
                  key=lambda n: (n not in POWER, -len(ch_nets[n]), n))
    m3_by_ch = defaultdict(list)               # channel -> (x, dir, y of the track it lands on)
    for c, lst in stubs.items():
        for net, sx, sy, dr, lay, inst in lst:
            m3_by_ch[c].append((sx, dr, track_y[(c, net)]))
    trunk = {}
    for net in need:
        w = PWR_TRUNK if net in POWER else SIG_TRUNK
        tys = sorted(track_y[(c, net)] for c in ch_nets[net])
        y1, y2 = tys[0] - tw(net, 0) // 2, tys[-1] + tw(net, 0) // 2
        if net in BOT_BUS:
            y1 = bus_y[net] - bus_w[net] // 2
        elif net in POWER:
            y2 = bus_y[net] + bus_w[net] // 2
        elif net in PORTS:                  # signal pins on the bottom edge
            y1 = 0
        allx = sorted(x for c in ch_nets[net] for x in xs_net[(c, net)])
        pref = allx[len(allx) // 2]
        if net in ("VOUT", "VIN"):          # corridor beside the pass device: VOUT cap side, VIN pass side
            cx = pd["origin"][0] + pd["bb"][0] - EXTRA_GAP["MPASS"] - DEV_GAP
            pref = cx + um(2.5) if net == "VOUT" else pd["origin"][0] + pd["bb"][0] - um(2)

        def ok(x):
            r = (x - w // 2 - SP, y1, x + w // 2 + SP, y2)
            if any(r[0] < o[2] and o[0] < r[2] and r[1] < o[3] and o[1] < r[3] for o in obstacles):
                return False
            for c in ch_nets[net]:          # via-stack metal3 pad vs metal3 stubs passing that height
                ty = track_y[(c, net)]
                half = max(tw(net, c), 80) // 2
                for sx, dr, sty in m3_by_ch[c]:
                    if abs(sx - x) >= max(w, 80) // 2 + PADX // 2 + SP + 4:
                        continue
                    # a down stub spans [its track, channel top]; an up stub [channel bottom, its track]
                    if (dr == "down" and ty + half + SP > sty - PADY // 2) or \
                       (dr == "up" and ty - half - SP < sty + PADY // 2):
                        return False
            return True
        cands = sorted(range(um(1) + w // 2, x_right - um(1) - w // 2, 10), key=lambda x: abs(x - pref))
        x = next((c for c in cands if ok(c)), None)
        if x is None:
            capx = [devs[i]["origin"][0] + devs[i]["bb"][2] for i in devs if devs[i]["kind"] == "cap"]
            px = pd["origin"][0] + pd["bb"][0]
            msg = [f"no room for the {net} trunk (w={w}, y {y1}..{y2}); corridor {capx} .. {px}"]
            for cx_ in range(min(capx), px, 100):
                r = (cx_ - w // 2 - SP, y1, cx_ + w // 2 + SP, y2)
                hit = [o for o in obstacles if r[0] < o[2] and o[0] < r[2] and r[1] < o[3] and o[1] < r[3]]
                m3 = [(c, sx, dr, sty) for c in ch_nets[net] for sx, dr, sty in m3_by_ch[c]
                      if abs(sx - cx_) < max(w, 80) // 2 + PADX // 2 + SP + 4]
                msg.append(f"  x={cx_}: obstacles {hit[:3]}  nearby m3 stubs {m3[:4]}  tracks {[(c, track_y[(c, net)]) for c in ch_nets[net]]}")
            msg.append(f"placed: {trunk}")
            sys.exit("\n".join(msg))
        trunk[net] = (x, w)
        obstacles.append((x - w // 2, y1, x + w // 2, y2))
        L.rect("metal4", x - w // 2, y1, x + w // 2, y2)
        for c in ch_nets[net]:              # via2 + via3 stack onto the net's metal2 track
            ty, th = track_y[(c, net)], tw(net, c)
            ix1, ix2 = x - w // 2, x + w // 2
            L.rect("metal3", ix1, ty - max(th, 80) // 2, ix2, ty + max(th, 80) // 2)
            L.rect("via2", ix1 + 10, ty - th // 2 + 10, ix2 - 10, ty + th // 2 - 10)
            L.rect("via3", ix1 + 10, ty - th // 2 + 10, ix2 - 10, ty + th // 2 - 10)
        if net in POWER:                    # via4 onto the bus
            L.rect("via4", x - w // 2 + 10, bus_y[net] - bus_w[net] // 2 + 10, x + w // 2 - 10, bus_y[net] + bus_w[net] // 2 - 10)
        
    # metal2 tracks, reaching the trunk where there is one
    for (c, net), xs_ in xs_net.items():
        cy, w = track_y[(c, net)], tw(net, c)
        lo, hi = min(xs_) - PADX // 2, max(xs_) + PADX // 2
        if net in trunk:
            lo, hi = min(lo, trunk[net][0] - trunk[net][1] // 2), max(hi, trunk[net][0] + trunk[net][1] // 2)
        L.rect("metal2", lo, cy - w // 2, hi, cy + w // 2)

    # metal5 buses (also the power pins) and pin labels
    bus_x = {"VSS": (0, x_right)}
    corridor_l = min(trunk[n][0] - trunk[n][1] // 2 for n in ("VIN", "VOUT")) - um(2)
    bus_x["VIN"] = bus_x["VOUT"] = (corridor_l, x_right)
    for n, by_ in bus_y.items():
        L.rect("metal5", bus_x[n][0], by_ - bus_w[n] // 2, bus_x[n][1], by_ + bus_w[n] // 2)
    labels = [(n, bus_x[n][0], bus_y[n] - bus_w[n] // 2, bus_x[n][1], bus_y[n] + bus_w[n] // 2, "metal5")
              for n in ("VIN", "VOUT", "VSS")]
    labels += [(n, trunk[n][0] - trunk[n][1] // 2, 0, trunk[n][0] + trunk[n][1] // 2, um(1), "metal4")
               for n in PORTS if n not in POWER]
    # plain (non-pin) labels on internal nets, so extraction / post-layout sims can name them
    for n in INTERNAL_LABELS:
        x, w = trunk[n]
        ty = min(track_y[(c, n)] for c in ch_nets[n])
        labels.append((n, x - w // 2, ty - 40, x + w // 2, ty + 40, "metal4:noport"))
    return L, labels, orders


def write_top(L, labels):
    s = ["magic", f"tech {PDK}", "magscale 1 10", "timestamp 0"]
    for cell, inst, tx, ty, fb, ts in L.uses:
        b = list(map(int, fb.split())) if fb else [0, 0, 0, 0]
        s += [f"use {cell}  {inst}", f"timestamp {ts}", f"transform 1 0 {tx} 0 1 {ty}", "box " + " ".join(map(str, b))]
    s.append("<< end >>")
    (MAG / f"{TOP}.mag").write_text("\n".join(s) + "\n")

    t = [f"load {TOP}", "snap internal"]
    for layer in ["metal1", "metal2", "metal3", "metal4", "metal5", "via1", "via2", "via3", "via4"]:
        for r in L.paint.get(layer, []):
            t += [f"box values {r[0]} {r[1]} {r[2]} {r[3]}", f"paint {layer}"]
    i = 0
    for n, x1, y1, x2, y2, layer in labels:
        layer, _, noport = layer.partition(":")
        t += [f"box values {x1} {y1} {x2} {y2}", f"label {n} c {layer}"]
        if not noport:
            i += 1
            t.append(f"port make {i}")
    t += [
        "select top cell", "save", "drc euclidean on", "drc style drc(full)", "drc check", "drc catchup",
        'set f [open ../drc.txt w]', 'set n 0',
        'foreach {why boxes} [drc listall why] { incr n [llength $boxes]; puts $f "[llength $boxes]  $why"; '
        'foreach b [lrange $boxes 0 4] { puts $f "      [lmap v $b {expr {$v/200.0}}]" } }',
        'puts $f "TOTAL $n"', "close $f", 'puts "DRC_TOTAL $n"',
        f"gds write ../gds/{TOP}.gds",
        "extract all", "ext2spice lvs", "ext2spice hierarchy off", f"ext2spice -o ../lvs/{TOP}_lay.spice", "quit -noprompt"]
    (MAG / "_build.tcl").write_text("\n".join(t) + "\n")


def strip_dummies(src, dst):
    """Copy the extracted netlist without dummy devices: MOS whose drain, gate,
    source and bulk are all one net (matched pairs' end fingers, tied to the
    bulk ring) and resistors whose ends and body are all one net (divider
    end units). Returns how many were removed."""
    text = src.read_text().replace("\n+", " ")
    out, n = [], 0
    for line in text.splitlines():
        f = line.split()
        mos = len(f) > 5 and re.match(r"[np]fet_0[356]v0$", f[5]) and len({f[1], f[2], f[3], f[4]}) == 1
        res_ = len(f) > 4 and f[4].startswith("ppolyf") and len({f[1], f[2], f[3]}) == 1
        if f and f[0].upper().startswith("X") and (mos or res_):
            n += 1
            continue
        out.append(line)
    dst.write_text("\n".join(out) + "\n")
    return n


def main():
    for d in (MAG, GDS, LVS):
        d.mkdir(exist_ok=True)
    cells, gl_bars = gen_devices()
    L, labels, orders = build(cells, gl_bars)
    for c, o in orders.items():
        print(f"channel {c}: {len(o)} tracks  {' '.join(o)}")
    write_top(L, labels)
    out = run_magic("_build.tcl", MAG)
    m = re.search(r"DRC_TOTAL (\d+)", out)
    print("magic DRC errors:", m.group(1) if m else "?\n" + out[-2000:])
    for f in MAG.glob("*.ext"):
        f.unlink()
    (MAG / "_build.tcl").unlink()
    ndummy = strip_dummies(LVS / f"{TOP}_lay.spice", LVS / f"{TOP}_lay_lvs.spice")
    print(f"removed {ndummy} dummy devices (all terminals on one net) before LVS")
    p = subprocess.run([NETGEN, "-batch", "lvs", f"{TOP}_lay_lvs.spice {TOP}", f"{SCH_NETLIST} {TOP}",
                        NETGEN_SETUP, "comp.out"], cwd=LVS, capture_output=True, text=True)
    res_ = (LVS / "comp.out").read_text() if (LVS / "comp.out").exists() else p.stdout
    tail = [l for l in res_.splitlines() if "match" in l.lower() or "Netlists" in l]
    print("LVS:", *tail[-4:], sep="\n  ")


if __name__ == "__main__":
    main()
