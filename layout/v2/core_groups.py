#!/usr/bin/env python3
"""Layout v2: compact, internally wired device groups for the LDO core
(run in the gLayout environment).

    glpy core_groups.py <outdir>

Techniques (compared with v1, where every device had its own guard ring):

  * diffusion sharing -- each row is ONE diffusion with N gate fingers
    (gLayout multiplier, routing off). Adjacent fingers share a source/drain
    strip, so devices with a common source (input pair: TAIL, tail mirror:
    VSS, mirror load: VIN) sit in the same diffusion.
  * common centroid -- the long-channel pairs (input pair, mirror load) are
    folded into two rows, A B B A over B A A B (2-D common centroid, each
    device owns the end fingers of one row); the tail mirror is A A B B B B A A.
    Every matched device is centred on the group axis.
  * dummies -- every matched row ends in two dummy fingers; devices with no
    common node in one row (the cascodes) are separated by a shared dummy
    instead of a diffusion break: x A A x B B B B x A A x. Dummy gates are tied
    to the bulk (always off).
  * shared well / guard ring + tap rows -- every NMOS shares one p+ ring and
    every PMOS except the pass device one n-well and ring; tap rows between
    rows replace per-device rings (the input pair is kept apart from the bias /
    enable row by a tap row).
  * abutment -- separate devices in a row sit at the minimum diffusion spacing.

Wiring (all inside the group, nothing over another group):
  * each row has a gate side and a source/drain side (GROUPS "gate": N / S).
    Gates: poly extended into the gate channel, poly contact, metal1 gate
    track per net. Source/drain: metal1 strips extended into the S/D channel,
    via1, metal2 track per net. Tracks of one channel are packed by interval
    colouring. Bulk strips and dummy gates drop straight onto the facing tap
    row / ring on metal1.
  * the two rows of a folded pair face ONE shared S/D channel ("abut"), so
    their drains / sources are joined on common tracks (the cross-coupling).
    Both rows' strips sit at the same x, so the lower row reaches the tracks
    on metal1 and the upper row on metal3.
  * a net that leaves its channel gets a metal3 riser in a side margin of the
    ring (never over a device) and, if exported, leaves the group through the
    top or bottom ring edge as a metal3 pin. A net in a channel that faces the
    ring on its export side drops straight out on metal3 instead.

Each group is converted to 6 V devices with one DUALGATE box; the L = 0.6 um
NMOS get their own V5_XTOR box (nfet_05v0), which never reaches a tap.
Writes <outdir>/<group>.gds and <outdir>/groups.json (sizes, per-device boxes,
pins {net: [[x, y], ...]} in group coordinates, riser columns).
"""
import itertools
import json
import sys
from pathlib import Path

import gdsfactory as gf
import klayout.db as kdb
from glayout import gf180
from glayout.backend import Component, rectangle
from glayout.primitives.fet import multiplier
from glayout.primitives.guardring import tapring
from glayout.primitives.via_gen import via_array, via_stack
from glayout.util.comp_utils import evaluate_bbox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_layout as bl  # noqa: E402  (schematic nets of every device: bl.ROWS)

PDK = gf180
DUALGATE, V5_XTOR, MARGIN = (55, 0), (112, 1), 1.0
LABEL = {"met1": (34, 10), "met2": (36, 10), "met3": (42, 10)}

# Each group: rows listed bottom-up, separated by "tap" (a tap row between them) or "abut"
# (the two halves of a folded matched device, facing one shared S/D channel).
# Row: dict(gate="N"|"S", devs=[(name, width per finger, L, fingers, pattern, v5, side)]).
# Pattern letters per finger: A/B = device, x = dummy (gate tied to the bulk), P = a single
# (unmatched) device, drawn without end dummies. Matched devices also get one gLayout dummy
# per end, so "xABBAx" has two dummies at each end. v5 = True: nfet_05v0 (L = 0.6) -- a
# V5_XTOR marker around that device only; the rest of the group stays 6 V. side: "C" =
# centred on the group axis (all matched devices share it), "L" / "R" = packed against the
# left / right end of the row, first listed outermost. The name keys the device's nets in
# build_layout.ROWS. spine: side of each metal3 riser; export: pins leaving the group (N, S
# or NS); feed: nets passing straight through the group (pins on both edges, no devices).
# Riser columns are allocated automatically (allocate()): the innermost column on the given
# side that crosses no device diffusion and no other metal3, so most risers run in the free
# space beside the narrow rows. A net shared by both groups gets the same column in both, so
# with the groups centred on one axis their pins line up.
GROUPS = {
    "v2_nmos_core": dict(nfet=True, bulk="VSS", rows=[
        dict(gate="S", devs=[
            ("MN1", 0.5, 5.0, 1, "P", False, "L"), ("MPDREF", 1.0, 0.6, 1, "P", True, "L"),
            ("MREF_MTAIL", 1.25, 0.6, 10, "xAABBBBAAx", True, "C"),
            ("MENDISCHARGE", 5.0, 0.6, 1, "P", True, "R"), ("MN2", 5.0, 0.6, 1, "P", True, "R")]),
        "tap",
        dict(gate="S", devs=[("MIN1_MIN2", 5.0, 3.0, 6, "xABBAx", False, "C")]),
        "abut",
        dict(gate="N", devs=[("MIN1_MIN2", 5.0, 3.0, 6, "xBAABx", False, "C")])],
        spine=dict(EN_5V="L", ENB_5V="L", TAIL="L", FB="L", IREF="L", EAREF="L",
                   EAOUT="R", VOUT="R", VREF="R"),
        export=dict(EAOUT="N", EAREF="N", EN_5V="N", ENB_5V="N", VREF="N", VOUT="N",
                    FB="S", IREF="S", EN="S")),
    "v2_pmos_core": dict(nfet=False, bulk="VIN", rows=[
        dict(gate="S", devs=[("MLOAD1_MLOAD2", 2.5, 3.0, 6, "xABBAx", False, "C")]),
        "abut",
        dict(gate="N", devs=[("MLOAD1_MLOAD2", 2.5, 3.0, 6, "xBAABx", False, "C")]),
        "tap",
        dict(gate="N", devs=[
            ("MCASC1_MCASC2", 1.25, 0.55, 12, "xAAxBBBBxAAx", False, "C"),
            ("MENPASSOFF", 5.0, 0.6, 1, "P", False, "R"), ("MP2", 5.0, 0.6, 1, "P", False, "R"),
            ("MBIASSW", 5.0, 0.6, 2, "P", False, "R")]),
        "tap",
        dict(gate="N", devs=[("MP1", 1.0, 40.0, 1, "P", False, "C")])],
        spine=dict(EN_5V="L", ENB_5V="L", CASCB1="L", CASCB2="L", EAREF="L", VSS="L",
                   EAOUT="R", VIN_BIAS="R", VOUT="R", VREF="R"),
        export=dict(EAOUT="NS", EAREF="S", EN_5V="S", ENB_5V="S", VIN_BIAS="N", VSS="S"),
        feed=["VOUT", "VREF"]),
}

GRID = 0.005
GATE_OFF, GATE_PITCH, GATE_W = 0.53, 0.76, 0.46   # gate contact levels (metal1), from the diff edge
SD_OFF, SD_PITCH, SD_W = 1.30, 0.80, 0.50         # S/D track levels (metal2), clear of dummy bars
SPINE_PITCH, SPINE_W, SPINE_GAP = 0.80, 0.50, 0.80
CLEAR = 0.45                                      # last track to a facing tap row / ring
PIN_OUT = 0.5                                     # metal3 pins end this far beyond the ring
COL0 = 0.6                                        # first riser column, from the axis


def g(v):
    return round(v / GRID) * GRID


def sep_to_tap(sdlayer):
    s = max(PDK.util_max_metal_seperation(), PDK.get_grule("active_diff", "active_tap")["min_separation"])
    return s + PDK.get_grule(sdlayer, "active_tap")["min_enclosure"]


def tap_width():
    from glayout.primitives.via_gen import via_stack as vs
    tw = max(PDK.get_grule("active_tap")["min_width"],
             2 * PDK.get_grule("active_tap", "mcon")["min_enclosure"] + PDK.get_grule("mcon")["width"])
    return PDK.snap_to_2xgrid(max(tw, evaluate_bbox(vs(PDK, "active_tap", "met1"))[0]))


def tap_row(length, tap_sd):
    """A straight substrate / well tap strip with contacts to metal1."""
    c = Component()
    tw = tap_width()
    c << rectangle(size=(length, tw), layer=PDK.get_glayer("active_tap"), centered=True)
    enc = PDK.get_grule("active_tap", tap_sd)["min_enclosure"]
    c << rectangle(size=(length + 2 * enc, tw + 2 * enc), layer=PDK.get_glayer(tap_sd), centered=True)
    c << via_array(PDK, "active_tap", "met1", size=(length, tw))
    return c


def nets_of(name):
    for row in bl.ROWS:
        for inst, _k, _s, nets in row:
            if inst == name:
                return nets
    raise KeyError(name)


def solve_strips(pattern, letter_nets, bulk):
    """Net of every S/D strip and gate of one multiplier. letter_nets: {letter: (S, D, G)}.
    Each device finger needs its source on one strip and drain on the other; strips shared
    by two fingers of the same device are made drains where possible (less drain area)."""
    nf, ns = len(pattern), len(pattern) + 1
    doms = []
    for j in range(ns):
        adj = [pattern[i] for i in (j - 1, j) if 0 <= i < nf and pattern[i] != "x"]
        doms.append(sorted(set.intersection(*[set(letter_nets[a][:2]) for a in adj])) if adj else [None])
    best = None
    for combo in itertools.product(*doms):
        if any(p != "x" and sorted((combo[i], combo[i + 1])) != sorted(letter_nets[p][:2])
               for i, p in enumerate(pattern)):
            continue
        score = sum(1 for j in range(1, ns - 1)
                    if pattern[j - 1] == pattern[j] != "x" and combo[j] == letter_nets[pattern[j]][1])
        if best is None or score > best[0]:
            best = (score, list(combo))
    assert best, f"no strip assignment for {pattern}"
    strips = best[1]
    for j in range(ns):                 # strips touching only dummies take a neighbour's net
        if strips[j] is None:
            near = [strips[k] for k in (j - 1, j + 1) if 0 <= k < ns and strips[k] is not None]
            strips[j] = near[0] if near else bulk
    gates = [bulk if p == "x" else letter_nets[p][2] for p in pattern]
    return strips, gates


def letter_nets_of(name, pattern):
    n = nets_of(name)
    if pattern == "P" or set(pattern) <= {"P"}:
        return {"P": (n["S"], n["D"], n["G"])}
    return {c: (n[f"{c}_S"], n[f"{c}_D"], n[f"{c}_G"]) for c in sorted(set(pattern) - {"x"})}


def colour(intervals, gap):
    """Greedy interval colouring: {net: (x0, x1)} -> {net: level}."""
    levels, ends = {}, []
    for net, (a, b) in sorted(intervals.items(), key=lambda kv: kv[1][0]):
        for k, e in enumerate(ends):
            if e + gap <= a:
                levels[net], ends[k] = k, b
                break
        else:
            levels[net] = len(ends)
            ends.append(b)
    return levels


def build_group(name, spec):
    nfet, bulk = spec["nfet"], spec["bulk"]
    sd = "n+s/d" if nfet else "p+s/d"
    tap_sd = "p+s/d" if nfet else "n+s/d"
    gap_x = PDK.snap_to_2xgrid(PDK.get_grule("active_diff")["min_separation"] + 0.3)
    rows = [r for r in spec["rows"] if not isinstance(r, str)]
    seps = [r for r in spec["rows"] if isinstance(r, str)]
    body = Component()
    meta = []

    def poly(layer, x0, y0, x1, y1):
        body.add_polygon([(g(x0), g(y0)), (g(x1), g(y0)), (g(x1), g(y1)), (g(x0), g(y1))],
                         layer=layer if isinstance(layer, tuple) else PDK.get_glayer(layer))

    def via(a, b, x, y):
        (body << via_stack(PDK, a, b)).move((g(x), g(y)))

    # ---- 1. devices of each row: multipliers and their x positions (rows centred on x = 0)
    built = []
    for row in rows:
        cells = []
        for dname, w, l, nf, pattern, v5, side in row["devs"]:
            dm = pattern != "P"
            m = multiplier(PDK, sd, width=w, length=l, fingers=nf, routing=False, dummy=(dm, dm))
            meta.append(dict(name=dname, w=w, l=l, fingers=nf, pattern=pattern, v5=v5))
            cells.append(dict(k=len(meta) - 1, m=m, w=evaluate_bbox(m)[0], side=side, dname=dname,
                              pattern=pattern if pattern != "P" else "P" * nf, wdiff=w, l=l))
        built.append(cells)

    def half_need(cells):
        wc = sum(c["w"] for c in cells if c["side"] == "C")
        return wc / 2 + max(sum(c["w"] + gap_x for c in cells if c["side"] == s_) for s_ in "LR")
    width = PDK.snap_to_2xgrid(2 * max(half_need(c) for c in built))
    for cells in built:
        xl, xr = -width / 2, width / 2
        for c in cells:
            if c["side"] == "C":
                c["x0"] = -c["w"] / 2
            elif c["side"] == "L":
                c["x0"], xl = xl, xl + c["w"] + gap_x
            else:
                c["x0"], xr = xr - c["w"], xr - c["w"] - gap_x
        xs = sorted((c["x0"], c["x0"] + c["w"]) for c in cells)
        assert all(a[1] + gap_x - 1e-6 <= b[0] for a, b in zip(xs, xs[1:])), f"{name}: row too full"

    # ---- 2. nets of every strip / gate; geometry relative to the multiplier (x shifted later)
    for ri, cells in enumerate(built):
        for c in cells:
            m = c["m"]
            ln = letter_nets_of(c["dname"], meta[c["k"]]["pattern"])
            strips, gates = solve_strips(c["pattern"], ln, bulk)
            nf = len(c["pattern"])
            dx = c["x0"] - m.xmin
            P = m.ports
            sx = [P["leftsd_top_met_N"].center[0]] + [P[f"row0_col{i}_rightsd_top_met_N"].center[0] for i in range(nf)]
            gx = [P[f"row0_col{i}_gate_N"].center[0] for i in range(nf)]
            c["strips"] = [(strips[j], sx[j] + dx) for j in range(nf + 1)]
            c["gates"] = [(gates[i], gx[i] + dx) for i in range(nf)]
            c["dummies"] = [(P[f"dummy_{s}_gsdcon_top_met_W"].center[0] + dx, P[f"dummy_{s}_gsdcon_top_met_E"].center[0] + dx,
                             P[f"dummy_{s}_gsdcon_top_met_S"].center[1], P[f"dummy_{s}_gsdcon_top_met_N"].center[1])
                            for s in ("L", "R") if f"dummy_{s}_gsdcon_top_met_N" in P]
            c["half"] = (P["diff_N"].center[1] - P["diff_S"].center[1]) / 2
    halfmax = [max(c["half"] for c in cells) for cells in built]

    # ---- 3. channels. Each row side faces the ring, a tap row or (abut) a shared S/D channel.
    chans = []                     # dict(kind gate|sd, rows=[(ri, sign)], face, items)

    def face(ri, top):
        if top:
            return "ring_top" if ri == len(rows) - 1 else seps[ri]
        return "ring_bot" if ri == 0 else seps[ri - 1]
    shared = {}
    for ri, row in enumerate(rows):
        for top in (False, True):
            is_gate = (row["gate"] == "N") == top
            f = face(ri, top)
            if f == "abut":
                assert not is_gate, f"{name}: a gate side faces an abut channel"
                key = ri if top else ri - 1
                if key not in shared:
                    shared[key] = dict(kind="sd", rows=[], face="abut")
                    chans.append(shared[key])
                shared[key]["rows"].append((ri, +1 if top else -1))
            else:
                chans.append(dict(kind="gate" if is_gate else "sd", rows=[(ri, +1 if top else -1)], face=f))
    for ch in chans:
        items = {}                 # net -> list of x
        for ri, sign in ch["rows"]:
            for c in built[ri]:
                for net, x in (c["gates"] if ch["kind"] == "gate" else c["strips"]):
                    items.setdefault(net, []).append(x)
        ch["items"] = items
    # which nets need a riser: nets in more than one channel, or exported but not straight out
    where = {}
    for ci, ch in enumerate(chans):
        for net in ch["items"]:
            if net != bulk:
                where.setdefault(net, []).append(ci)
    export = spec["export"]
    direct = {}
    for net, cis in where.items():
        if len(cis) == 1 and net in export:
            f = chans[cis[0]]["face"]
            if (export[net], f) in (("S", "ring_bot"), ("N", "ring_top")):
                direct[net] = cis[0]
    feed = spec.get("feed", [])
    risers = {net for net, cis in where.items() if (len(cis) > 1 or net in export) and net not in direct}
    risers |= set(feed)
    for net in risers:
        assert spec["spine"].get(net) in ("L", "R"), f"{name}: no spine side given for {net}"
    side_sign = {net: (-1 if spec["spine"][net] == "L" else 1) for net in risers}
    BIG = 1e6
    for ch in chans:               # track levels
        iv = {}
        for net, xs in ch["items"].items():
            if net == bulk and ch["face"] != "abut":
                continue
            a, b = min(xs) - 0.6, max(xs) + 0.6
            if net == bulk:
                a, b = -BIG, BIG
            elif net in side_sign:      # the track runs out to its riser on that side
                a, b = (-BIG, b) if side_sign[net] < 0 else (a, BIG)
            iv[net] = (a, b)
        lv = colour(iv, 0.5)
        n = max(lv.values()) + 1 if lv else 0
        if ch["kind"] == "gate" and bulk in ch["items"]:
            lv[bulk] = n            # dummy gates: outermost level, dropped onto the tap / ring
            n += 1
        ch["levels"], ch["n"] = lv, n
        off, pitch, w = (GATE_OFF, GATE_PITCH, GATE_W) if ch["kind"] == "gate" else (SD_OFF, SD_PITCH, SD_W)
        ch["off"], ch["pitch"], ch["tw"] = off, pitch, w
        ch["h"] = off + (n - 1) * pitch + w / 2 if n else 0.0

    # ---- 4. vertical stacking
    tw = tap_width()
    s_tap = sep_to_tap(sd)

    def chan_of(ri, top):
        for ch in chans:
            if (ri, +1 if top else -1) in ch["rows"]:
                return ch
    yrb = 0.0                                                     # ring inner edge, bottom
    y = yrb + max(s_tap, chan_of(0, False)["h"] + CLEAR)
    edges, taps = [], []
    for ri in range(len(rows)):
        bot = y
        top = bot + 2 * halfmax[ri]
        edges.append((bot, top))
        if ri < len(rows) - 1:
            if seps[ri] == "tap":
                yc = top + max(s_tap, chan_of(ri, True)["h"] + CLEAR) + tw / 2
                taps.append(yc)
                y = yc + tw / 2 + max(s_tap, chan_of(ri + 1, False)["h"] + CLEAR)
            else:
                ch = chan_of(ri, True)
                y = top + 2 * SD_OFF + max(ch["n"] - 1, 0) * SD_PITCH
    yrt = edges[-1][1] + max(s_tap, chan_of(len(rows) - 1, True)["h"] + CLEAR)

    # ---- 5. draw devices and tap rows (the ring comes after the riser columns are known)
    obst = []                      # metal3 keep-outs: device diffusion, other metal3
    for ri, cells in enumerate(built):
        yc = (edges[ri][0] + edges[ri][1]) / 2
        flip = rows[ri]["gate"] == "S"           # gsdcon (dummy bars) must be on the S/D side (N)
        for c in cells:
            m = c["m"]
            r = body << m
            if flip:
                r.mirror(p1=(0, 0), p2=(1, 0))
            r.movex(g(c["x0"] - m.xmin)).movey(g(yc))
            ymin, ymax = yc - c["half"], yc + c["half"]
            meta[c["k"]].setdefault("boxes", []).append([c["x0"], edges[ri][0], c["x0"] + c["w"], edges[ri][1]])
            c["edge_lo"], c["edge_hi"] = ymin, ymax
            c["bars"] = [(a, b, yc + (y0 if not flip else -y1), yc + (y1 if not flip else -y0))
                         for a, b, y0, y1 in c["dummies"]]
            obst.append((c["x0"] - 0.3, ymin - 0.3, c["x0"] + c["w"] + 0.3, ymax + 0.3))
    for yc in taps:
        (body << tap_row(width, tap_sd)).movey(g(yc))
    ring_cy, ring_h = (yrb + yrt) / 2, yrt - yrb
    ring_t = (evaluate_bbox(tapring(PDK, enclosed_rectangle=(20.0, 20.0), sdlayer=tap_sd,
                                    horizontal_glayer="met2", vertical_glayer="met1"))[1] - 20.0) / 2
    ybot_out, ytop_out = yrb - ring_t - PIN_OUT, yrt + ring_t + PIN_OUT

    def bulk_target(ch, sign, ri):  # y of the metal1 a bulk drop lands on
        f = ch["face"]
        if f == "ring_bot":
            return yrb - 0.25
        if f == "ring_top":
            return yrt + 0.25
        ti = ri if sign > 0 else ri - 1
        return taps[sum(1 for s_ in seps[:ti] if s_ == "tap")]

    # ---- 6. channels: strip / gate connections, bulk drops (tracks are drawn in finish())
    track_y = {}                   # (channel index, net) -> y
    side_bars = []                 # dummy bars in abut channels: sideways to the ring later
    for ci, ch in enumerate(chans):
        ri0, s0 = ch["rows"][0]
        base = edges[ri0][1] if s0 > 0 else edges[ri0][0]
        for net, lev in ch["levels"].items():
            track_y[(ci, net)] = base + s0 * (ch["off"] + lev * ch["pitch"])
        for ri, sign in ch["rows"]:
            for c in built[ri]:
                edge = c["edge_hi"] if sign > 0 else c["edge_lo"]
                if ch["kind"] == "gate":
                    gy = c["edge_hi"] + 0.24 if sign > 0 else c["edge_lo"] - 0.24   # poly end
                    for net, x in c["gates"]:
                        ty = track_y[(ci, net)]
                        poly("poly", x - c["l"] / 2, min(gy, ty), x + c["l"] / 2, max(gy, ty))
                        via("poly", "met1", x, ty)
                        if net == bulk:
                            tgt = bulk_target(ch, sign, ri)
                            poly("met1", x - 0.23, min(ty, tgt), x + 0.23, max(ty, tgt))
                else:
                    for net, x in c["strips"]:
                        if net == bulk and ch["face"] != "abut":
                            tgt = bulk_target(ch, sign, ri)
                            poly("met1", x - 0.23, min(edge, tgt), x + 0.23, max(edge, tgt))
                            continue
                        ty = track_y[(ci, net)]
                        if ch["face"] == "abut" and sign < 0:
                            # upper row of a folded pair: its strips sit at the same x as the
                            # lower row's, so it comes down on metal3 (via1+2 at its edge, via2
                            # at the track) and never overlaps the lower row's metal1
                            via("met1", "met3", x, edge - 0.25)
                            poly("met3", x - 0.25, ty, x + 0.25, edge - 0.25)
                            via("met2", "met3", x, ty)
                            obst.append((x - 0.55, ty - 0.55, x + 0.55, edge + 0.3))
                            continue
                        poly("met1", x - 0.23, min(edge, ty), x + 0.23, max(edge, ty))
                        via("met1", "met2", x, ty)
                    for a, b, y0, y1 in c["bars"]:                       # dummy islands -> bulk
                        if ch["face"] != "abut":
                            tgt = bulk_target(ch, sign, ri)
                            yb = y1 if sign > 0 else y0
                            poly("met1", (a + b) / 2 - 0.23, min(yb, tgt), (a + b) / 2 + 0.23, max(yb, tgt))
                        else:
                            side_bars.append((a, b, y0, y1))

    # nets straight out of a channel that faces the ring on their export side
    pins = {}
    for net, ci in direct.items():
        ch = chans[ci]
        ty = track_y[(ci, net)]
        x = min(ch["items"][net])
        via("met1" if ch["kind"] == "gate" else "met2", "met3", x, ty)
        lo, hi = (ybot_out, ty) if export[net] == "S" else (ty, ytop_out)
        poly("met3", x - SPINE_W / 2, lo, x + SPINE_W / 2, hi)
        pins[net] = [[x, ybot_out + 0.3 if export[net] == "S" else ytop_out - 0.3]]
        obst.append((x - 0.55, lo, x + 0.55, hi))

    # what each riser needs: its vertical span
    need = {}
    for net in risers:
        ys = [track_y[(ci, net)] for ci in where.get(net, [])]
        lo, hi = (min(ys), max(ys)) if ys else (ybot_out, ytop_out)
        e = export.get(net, "NS" if net in feed else "")
        if "S" in e:
            lo = ybot_out
        if "N" in e:
            hi = ytop_out
        need[net] = (lo - SPINE_W / 2, hi + SPINE_W / 2, side_sign[net])

    def finish(spine_x):
        # ring: just outside the outermost riser column (and never closer than s_tap)
        out = max([abs(x) + SPINE_W / 2 + 0.8 for x in spine_x.values()] + [width / 2 + s_tap])
        ring_x = PDK.snap_to_2xgrid(out)
        ring = body << tapring(PDK, enclosed_rectangle=(2 * ring_x, ring_h), sdlayer=tap_sd,
                               horizontal_glayer="met2", vertical_glayer="met1")
        ring.movey(g(ring_cy))
        enc_t = PDK.get_grule("active_tap", tap_sd)["min_enclosure"]
        for yc in taps:            # tap rows joined to the ring's sides
            L = 2 * ring_x + 1.0
            poly("active_tap", -L / 2, yc - tw / 2, L / 2, yc + tw / 2)
            poly(tap_sd, -L / 2 - enc_t, yc - tw / 2 - enc_t, L / 2 + enc_t, yc + tw / 2 + enc_t)
        for a, b, y0, y1 in side_bars:                                   # sideways to the ring
            o = -ring_x - 0.25 if (a + b) / 2 < 0 else ring_x + 0.25
            poly("met1", min(a, o), y0, max(b, o), y1)
        for ci, ch in enumerate(chans):                                  # the tracks
            for net, lev in ch["levels"].items():
                if net == bulk and ch["kind"] == "gate":
                    continue
                ty = track_y[(ci, net)]
                xs = ch["items"][net]
                a, b = min(xs), max(xs)
                if net == bulk:
                    a, b = -ring_x - 0.25, ring_x + 0.25
                elif net in spine_x:
                    a, b = min(a, spine_x[net]), max(b, spine_x[net])
                lay, hw = ("met1", GATE_W / 2) if ch["kind"] == "gate" else ("met2", SD_W / 2)
                poly(lay, a - hw, ty - hw, b + hw, ty + hw)
                if net == bulk:                                          # abut bulk track -> ring
                    via("met1", "met2", -ring_x - 0.25, ty)
                    via("met1", "met2", ring_x + 0.25, ty)
        for net, x in sorted(spine_x.items()):                           # risers and their pins
            lo, hi, _ = need[net]
            for ci in where.get(net, []):
                via("met1" if chans[ci]["kind"] == "gate" else "met2", "met3", x, track_y[(ci, net)])
            poly("met3", x - SPINE_W / 2, lo, x + SPINE_W / 2, hi)
            e = export.get(net, "NS" if net in feed else "")
            for side_, y_ in (("S", ybot_out + 0.3), ("N", ytop_out - 0.3)):
                if side_ in e:
                    body.add_label(net, position=(g(x), g(y_)), layer=LABEL["met3"])
                    pins.setdefault(net, []).append([x, y_])
        for net in direct:
            body.add_label(net, position=(g(pins[net][0][0]), g(pins[net][0][1])), layer=LABEL["met3"])
        body.add_label(bulk, position=(g(-ring_x - 0.15), g(ring_cy)), layer=LABEL["met1"])
        pins[bulk] = [[-ring_x - 0.15, ring_cy]]
        # markers: V5_XTOR around each 5 V device incl. its gate channel; well
        for ri, cells in enumerate(built):
            for c in cells:
                if not meta[c["k"]]["v5"]:
                    continue
                gch = chan_of(ri, rows[ri]["gate"] == "N")
                y0, y1 = edges[ri]
                if rows[ri]["gate"] == "N":
                    y1 += gch["h"] + 0.1
                else:
                    y0 -= gch["h"] + 0.1
                poly(V5_XTOR, c["x0"] - gap_x / 2, y0 - 0.1, c["x0"] + c["w"] + gap_x / 2, y1 + 0.1)
        well = "pwell" if nfet else "nwell"
        body.add_padding(layers=(PDK.get_glayer(well),), default=PDK.get_grule(well, "active_tap")["min_enclosure"])
        return body, meta, pins

    conn = {net: [track_y[(ci, net)] for ci in where.get(net, [])] for net in need}
    return dict(name=name, need=need, conn=conn, obst=obst, finish=finish, export=export, feed=feed)


def allocate(ctxs):
    """Riser columns for all groups at once, on a SPINE_PITCH grid from COL0 out on each
    net's side. A column is free for a riser if its span crosses no keep-out (device
    diffusion, other metal3) of its group.

    Order: on each side, the inner-to-outer order of the risers is chosen (exhaustively,
    over both groups together) to minimise crossings -- a track running out to an outer
    riser crosses every inner riser whose span covers the track's height. Risers are then
    placed in that order, each in the innermost free column outside every earlier riser it
    overlaps in height (risers with disjoint spans may share a column). A net present in
    several groups (shared pins, feed-throughs) gets one column that is free in all of them."""
    import itertools
    taken = {c["name"]: [] for c in ctxs}

    def free(ctx, x, lo, hi):
        r = (x - SPINE_W / 2 - 0.3, lo - 0.3, x + SPINE_W / 2 + 0.3, hi + 0.3)
        for o in ctx["obst"] + taken[ctx["name"]]:
            if r[0] < o[2] and o[0] < r[2] and r[1] < o[3] and o[1] < r[3]:
                return False
        return True
    users = {}
    for c in ctxs:
        for net in c["need"]:
            users.setdefault(net, []).append(c)
    sign = {}
    for net, cs in users.items():
        sides = {c["need"][net][2] for c in cs}
        assert len(sides) == 1, f"{net}: different sides in different groups"
        sign[net] = sides.pop()

    def crossings(order):
        n = 0
        for c in ctxs:
            for i, r in enumerate(order):
                if r not in c["need"]:
                    continue
                for q in order[:i]:
                    if q in c["need"]:
                        lo, hi = c["need"][q][:2]
                        n += sum(1 for y in c["conn"][r] if lo < y < hi)
        return n
    result = {c["name"]: {} for c in ctxs}
    for sgn in (-1, 1):
        nets = sorted(n for n in users if sign[n] == sgn)
        # fewest crossings; then nets with more connections further in (shorter tracks)
        order = min(itertools.permutations(nets),
                    key=lambda o: (crossings(o), sum(i * sum(len(c["conn"].get(n, [])) for c in users[n])
                                                     for i, n in enumerate(o)), o))
        col = {}
        for i, net in enumerate(order):
            kmin = 0
            for q in order[:i]:
                if any(q in c["need"] and c["need"][q][0] < c["need"][net][1] and c["need"][net][0] < c["need"][q][1]
                       for c in users[net]):
                    kmin = max(kmin, col[q] + 1)
            for k in range(kmin, 200):
                x = sgn * (COL0 + k * SPINE_PITCH)
                if all(free(c, x, c["need"][net][0], c["need"][net][1]) for c in users[net]):
                    break
            else:
                raise RuntimeError(f"no column for {net}")
            col[net] = k
            for c in users[net]:
                lo, hi = c["need"][net][:2]
                taken[c["name"]].append((x - SPINE_W / 2, lo, x + SPINE_W / 2, hi))
                result[c["name"]][net] = x
        print("side", "L" if sgn < 0 else "R", "order (inner -> outer):", " ".join(order),
              f"-- {crossings(order)} crossings", flush=True)
    return result


def write_hv(comp, name, path):
    c = gf.Component(name + "_wrap")
    r = c << comp
    (x0, y0), (x1, y1) = r.bbox
    box = [(x0 - MARGIN, y0 - MARGIN), (x1 + MARGIN, y0 - MARGIN), (x1 + MARGIN, y1 + MARGIN), (x0 - MARGIN, y1 + MARGIN)]
    c.add_polygon(box, layer=DUALGATE)
    c = c.flatten()
    raw = path.with_suffix(".raw.gds")
    c.write_gds(raw)
    lay = kdb.Layout()
    lay.read(str(raw))
    lay.top_cell().name = name
    opt = kdb.SaveLayoutOptions()
    opt.dbu = 0.001
    lay.write(str(path), opt)
    raw.unlink()
    return (x0 - MARGIN, y0 - MARGIN, x1 + MARGIN, y1 + MARGIN)


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    info = {}
    ctxs = [build_group(name, spec) for name, spec in GROUPS.items()]
    cols = allocate(ctxs)
    for ctx in ctxs:
        name = ctx["name"]
        comp, meta, pins = ctx["finish"](cols[name])
        bb = write_hv(comp, name, out / f"{name}.gds")
        size = (bb[2] - bb[0], bb[3] - bb[1])
        for d in meta:                 # device boxes: union of the rows it occupies, group coords
            bs = d.pop("boxes")
            d["box"] = [round(min(b[0] for b in bs), 3), round(min(b[1] for b in bs), 3),
                        round(max(b[2] for b in bs), 3), round(max(b[3] for b in bs), 3)]
        info[name] = dict(size=[round(v, 2) for v in size], devices=meta, nfet=GROUPS[name]["nfet"],
                          bulk=GROUPS[name]["bulk"], pins={k: [[round(v, 3) for v in q] for q in p] for k, p in pins.items()},
                          risers={k: round(v, 3) for k, v in cols[name].items()})
        print("GROUP", name, f"{size[0]:.1f} x {size[1]:.1f} um", "risers:",
              " ".join(f"{k}@{v:+.1f}" for k, v in sorted(cols[name].items(), key=lambda kv: kv[1])), flush=True)
    (out / "groups.json").write_text(json.dumps(info, indent=1) + "\n")


if __name__ == "__main__":
    main()
