#!/usr/bin/env python3
"""Layout v2: block-level wiring of the "snug" floorplan, built up step by step.

    cd layout && python3 place_v2.py snug && python3 route_v2.py

Reads the placement (ldo_v2_place_snug.mag / .json), the group pins
(gl/groups.json) and the device terminals (pass-device bars, resistor
contacts, R1/R2 stubs, MIM cap plates), paints the wiring into a new top
cell ldo_v2.mag, then runs magic (DRC count, GDS) and the KLayout DRC deck.

Coordinates are the unflipped placement (pass device at the top); the slot
view is this block mirrored top-to-bottom.

Step 1 (signal nets around the amplifier core):
  * the six shared nets between the NMOS and PMOS groups: straight metal3
    bridges across the 1.2 um gap (EAOUT, EAREF, EN_5V, ENB_5V, VOUT, VREF)
  * channel between the core / Cc and the pass device (metal4, 4 tracks, all
    1.6 um or more above Cc's plate -- MIMTM.1):
      VOUT    PMOS top pin -> metal4 strap in the strip right of the pass
              device, which also lands on Cc's bottom plate (VOUT)
      EAOUT   straight up into the pass-device gate bar; across to Cc's top
              plate (metal5 strap through the plate contact, via4 1.6 um clear
              of the plate as in v1)
      VREF    out to the strip right of the pass device, up toward the VREF pin
      VIN_BIAS over the channel on metal5, down the right side of Cc to
              Rref's right contact
      VSS     MP1 gate -> out of the PMOS group's bottom, straight onto the NMOS ring
  * bottom channel (metal4): IREF to Rref's left contact; FB left and up
    through the free pocket to R1/R2's two FB stubs.

Step 2 (power):
  * VOUT bus (metal5, 6 um) right above the pass device, out to the right edge;
    VIN bus (6 um) above it and the VSS bus (6 um) on the other side, both edge
    to edge across the whole block (a supply grid the slot trunks can join); pass-device straps as in v1 (metal4, 2.6 um wide, 3.2 um pitch,
    alternating VIN / VOUT, via arrays on every row's bar). Cc's VOUT strap
    lands on the VOUT bus; R1/R2's VOUT end is a sense line (Kelvin) that joins the
    bus only at the VOUT pin; VREF continues to the top edge.
  * PMOS ring (VIN) -> metal3 jumps across the channel -> the pass device's
    bulk bar (VIN, on the VIN straps).
  * VSS bus (metal5, 6 um) along the bottom: NMOS ring, Rref's ring, R1/R2's
    VSS end and ring. Power drops / risers / jumps are 1 um
    metal3 (VIN riser to the test buffers 2 um) with via arrays at both ends.

Step 3 (test buffers, block ports):
  * a channel above the buffer row (VSS, IREF_EA, EAOUT_BUF, FB_BUF, VIN) and one
    below it (VSS, IREF_EA, ENB_5V, EAOUT); metal3 stubs from the buffer cells'
    metal2 bars. VIN rises beside RrefEA to the VIN bus; VSS drops to the VSS bus.
  * FB from the bottom-channel FB track; EAOUT and ENB_5V come down the left
    channel (R1/R2 | core); VIN_BIAS runs along the bottom, up beside the
    cluster and over (metal5) to RrefEA's contact.
  * ports: VIN, VSS, VOUT (metal5 buses), VREF (top), EN (bottom), FB_BUF and
    EAOUT_BUF (left edge).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_layout as bl  # noqa: E402
import report_summary  # noqa: E402

TOP = "ldo_v2"
PLACE = "ldo_v2_place_snug"
W = 0.38                 # signal track width (metal3 / metal4)
PW = 1.0                 # power drops / risers / jumps (metal3)
PSTRAP = 1.5             # Cc's VOUT strap (metal4)
PITCH = 0.70             # signal track pitch
DRC_DECK = "/foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc"
DENSITY = re.compile(r"^M\d\.4$|^MT\.3$|^DCF\.1b$|^PL\.8$")


class Painter:
    def __init__(self):
        self.L = bl.Layout()
        self.labels = []
        self.ports = []

    def rect(self, layer, x0, y0, x1, y1):
        self.L.rect(layer, bl.um(x0), bl.um(y0), bl.um(x1), bl.um(y1))

    def h(self, layer, y, xa, xb, w=W):        # horizontal wire, centred on y
        self.rect(layer, min(xa, xb) - w / 2, y - w / 2, max(xa, xb) + w / 2, y + w / 2)

    def v(self, layer, x, ya, yb, w=W):        # vertical wire, centred on x
        self.rect(layer, x - w / 2, min(ya, yb) - w / 2, x + w / 2, max(ya, yb) + w / 2)

    def label(self, net, layer, x, y):
        self.labels.append((net, layer, x, y))

    def port(self, net, layer, x, y):
        self.ports.append((net, layer, x, y))

    def wvia(self, lo, hi, x, y, w=1.0):
        """Wide via stack (via arrays) from metal<lo> to metal<hi>: w x w pads on every metal,
        via regions inset 0.1 um (magic fills them with cut arrays)."""
        for k in range(lo, hi + 1):
            self.rect(f"metal{k}", x - w / 2 - 0.05, y - w / 2 - 0.05, x + w / 2 + 0.05, y + w / 2 + 0.05)
        for k in range(lo, hi):
            self.rect(f"via{k}", x - w / 2 + 0.05, y - w / 2 + 0.05, x + w / 2 - 0.05, y + w / 2 - 0.05)

    def via(self, lo, hi, x, y):
        """Via stack from metal<lo> to metal<hi> at (x, y)."""
        kinds = [f"via{k}" for k in range(lo, hi)]
        for k in kinds:
            self.L.via(k, bl.um(x), bl.um(y), stack=len(kinds) > 1)


def load():
    pl = json.loads((HERE / f"{PLACE}.json").read_text())
    gr = json.loads((HERE / "gl" / "groups.json").read_text())
    terms = json.loads((bl.GL / "terms.json").read_text())

    def pins(g, net):
        o = pl[g]["origin"]
        return sorted((p[0] + o[0], p[1] + o[1]) for p in gr[g]["pins"][net])

    def bars(inst):
        o = pl[inst]["origin"]
        return {k: (v[0] + o[0], v[1] + o[0], v[2] + o[1]) for k, v in terms[pl[inst]["cell"]].items()}

    def mag(inst):
        f = HERE / "mag" / f"{pl[inst]['cell']}.mag"           # the core groups live in v2/mag
        r, _ = bl.parse_mag(f if f.exists() else bl.MAG / f"{pl[inst]['cell']}.mag")
        o = pl[inst]["origin"]
        return {k: [(a / bl.UM + o[0], b / bl.UM + o[1], c / bl.UM + o[0], d / bl.UM + o[1]) for a, b, c, d in v]
                for k, v in r.items()}
    cache = json.loads((bl.MAG / "devices.json").read_text())
    spec = next(s for row in bl.ROWS for i, k, s, n in row if i == "R1R2")
    tl, _ = bl.make_res_array(cache["|".join(spec)])
    o = pl["R1R2"]["origin"]
    r1r2 = {k: (x / bl.UM + o[0], y / bl.UM + o[1]) for k, x, y, d in tl}
    return pl, pins, bars, mag, r1r2


def route():
    pl, pins, bars, mag, r1r2 = load()
    P = Painter()
    box = {k: v["box"] for k, v in pl.items()}
    N, Pm = "v2_nmos_core", "v2_pmos_core"

    # ---- bridges between the groups (the pins already line up)
    for net in ("EAOUT", "EAREF", "EN_5V", "ENB_5V", "VOUT", "VREF"):
        (xn, yn), (xp, yp) = pins(N, net)[-1], pins(Pm, net)[0]
        assert abs(xn - xp) < 0.01, f"{net} pins do not line up ({xn} vs {xp})"
        P.rect("metal3", xn - 0.25, yn, xn + 0.25, yp)

    # ---- channel under the pass device: 4 metal4 tracks above Cc's plate
    cc_l, cc_b, cc_r, cc_t = box["Cc"]
    mp_l, mp_b, mp_r, mp_t = box["MPASS"]
    # MIMTM.1: every other metal4 (any net) stays 1.2 um from the "virtual" bottom plate
    # (metal4 within 1.06 um of the top plate); a strap leaving the plate at a right angle
    # is fine, a track parallel to the plate edge is not
    y_ea = cc_t + 1.6
    y_vout = y_ea + PITCH
    y_vref = y_vout + PITCH
    y_vb = y_vref + PITCH
    assert y_vb + W / 2 + 0.3 <= mp_b, "channel under the pass device too small"
    top_pin = {net: pins(Pm, net)[-1] for net in ("EAOUT", "VOUT", "VREF", "VIN_BIAS", "VSS")}
    x_vs = (mp_r + cc_r) / 2             # VOUT strap: strip right of the pass device, over Cc's plate edge
    x_vr = mp_r + 0.85                   # VREF riser, between the pass device and the VOUT strap

    # VOUT: PMOS top pin -> track -> strap (metal4, lands on Cc's metal4 bottom plate)
    x, y = top_pin["VOUT"]
    P.v("metal3", x, y, y_vout)
    P.via(3, 4, x, y_vout)
    P.h("metal4", y_vout, x, x_vs)
    P.v("metal4", x_vs, cc_t - 0.5, mp_t + 1.0, w=PSTRAP)   # leaves the plate at a right angle
    P.label("VOUT", "metal4", x_vs, mp_t)

    # EAOUT: straight up into the pass-device gate bar, and across to Cc's top plate
    g_xl, g_xr, g_y = bars("MPASS")["G"]
    x, y = top_pin["EAOUT"]
    P.v("metal3", x, y, g_y)
    P.via(2, 3, x, g_y)
    P.via(3, 4, x, y_ea)
    contact = mag("Cc")["mimcapcontact"][0]
    x_cc = contact[0] + 3.0
    P.h("metal4", y_ea, x, x_cc)
    P.label("EAOUT", "metal4", (x + x_cc) / 2, y_ea)
    P.via(4, 5, x_cc, y_ea)
    P.v("metal5", x_cc, cc_t - 2.0, y_ea, w=0.44)

    # VREF: out to the strip right of the pass device, then up (pin side of the block)
    x, y = top_pin["VREF"]
    P.v("metal3", x, y, y_vref)
    P.via(3, 4, x, y_vref)
    P.h("metal4", y_vref, x, x_vr)
    P.via(3, 4, x_vr, y_vref)
    P.v("metal3", x_vr, y_vref, mp_t + 1.0)
    P.label("VREF", "metal3", x_vr, mp_t)

    # VIN_BIAS: over the channel on metal5 (crosses the VREF riser and the VOUT strap),
    # down the right side of Cc and Rref on metal3, into Rref's right contact
    rc = sorted(mag("Rref")["polycontact"])
    (ra, rb) = [((c[0] + c[2]) / 2, (c[1] + c[3]) / 2) for c in rc]          # A = IREF, B = VIN_BIAS
    y_b1, y_b2 = box[N][1] - 0.8, box[N][1] - 0.8 - PITCH                 # bottom channel tracks
    x_rb = max(cc_r, box["Rref"][2]) + 1.7
    x, y = top_pin["VIN_BIAS"]
    P.v("metal3", x, y, y_vb)
    P.via(3, 5, x, y_vb)
    P.h("metal5", y_vb, x, x_rb, w=0.44)
    P.via(3, 5, x_rb, y_vb)
    P.v("metal3", x_rb, y_vb, y_b1)
    P.label("VIN_BIAS", "metal3", x_rb, (y_vb + y_b1) / 2)
    P.via(3, 4, x_rb, y_b1)
    P.h("metal4", y_b1, x_rb, rb[0])
    P.via(3, 4, rb[0], y_b1)
    P.v("metal3", rb[0], y_b1, rb[1])
    P.via(1, 3, rb[0], rb[1])

    # IREF: NMOS bottom pin -> bottom channel -> Rref's left contact
    x, y = pins(N, "IREF")[0]
    P.v("metal3", x, y, y_b1)
    P.via(3, 4, x, y_b1)
    P.h("metal4", y_b1, x, ra[0])
    P.label("IREF", "metal4", (x + ra[0]) / 2, y_b1)
    P.via(3, 4, ra[0], y_b1)
    P.v("metal3", ra[0], y_b1, ra[1])
    P.via(1, 3, ra[0], ra[1])

    # FB: NMOS bottom pin -> bottom channel (left) -> up through the pocket to R1/R2's FB stubs
    x, y = pins(N, "FB")[0]
    P.v("metal3", x, y, y_b2)
    P.via(3, 4, x, y_b2)
    fb_x = [r1r2["A_start"][0], r1r2["B_end"][0]]
    P.h("metal4", y_b2, min(fb_x), x)
    P.label("FB", "metal4", (min(fb_x) + x) / 2, y_b2)
    for k in ("A_start", "B_end"):
        sx, sy = r1r2[k]
        P.via(3, 4, sx, y_b2)
        P.v("metal3", sx, y_b2, sy)
        P.via(2, 3, sx, sy)

    # VSS for MP1's gate: the PMOS group exports it at its bottom; 1.2 um straight down onto
    # the NMOS ring (p+ tap = VSS) right below
    x, y = pins(Pm, "VSS")[0]
    nring_top = max((r for r in mag(N)["metal2"] if r[2] - r[0] > 20), key=lambda r: r[3])
    yrt = (nring_top[1] + nring_top[3]) / 2
    P.v("metal3", x, y, yrt)             # a gate tie (no current); one riser pitch from ENB_5V
    P.via(2, 3, x, yrt)
    P.label("VSS", "metal3", x, (y + yrt) / 2)
    # left channel (R1/R2 | core): EAOUT inner, ENB_5V outer -- EAOUT turns lower at the
    # bottom, so the two only cross once (ENB_5V's tap from the group gap)
    x_le = min(box[N][0], box[Pm][0]) - 0.9
    x_lb = x_le - 0.9
    assert x_lb - W / 2 >= box["R1R2"][2] + 1.0, "left channel too narrow"

    # ================= step 2: power =================
    # --- top: VOUT bus right above the pass device, VIN bus above it (metal5, 6 um each:
    # 10 mA / 6 um = 1.7 mA/um, EM limit 2.2 at 110 C)
    BUS = 6.0
    y_vo = (mp_t + 1.0, mp_t + 1.0 + BUS)
    y_vi = (y_vo[1] + 1.0, y_vo[1] + 1.0 + BUS)
    pb = bars("MPASS")
    a_end = r1r2["A_end"]
    # VIN and VSS run edge to edge (a block-wide grid the slot's supply trunks can join from
    # either side); VOUT runs from R1/R2's VOUT end out to the right edge (the VOUT pad side)
    bufs = ("RrefEA", "MREFEA_MBIAS", "MPDEA", "MFBBUF", "MEAOUTBUF")
    bx_l = min(box[k][0] for k in bufs) - 1.0
    bx_r = max(max(b[2] for b in box.values()), x_rb + W / 2) + 1.0
    P.rect("metal5", a_end[0] - 1.0, y_vo[0], bx_r, y_vo[1])
    P.rect("metal5", bx_l, y_vi[0], bx_r, y_vi[1])
    P.label("VOUT", "metal5", (a_end[0] + x_vs) / 2, sum(y_vo) / 2)
    P.label("VIN", "metal5", (box["R1R2"][0] + mp_r) / 2, sum(y_vi) / 2)
    # pass-device straps (v1 scheme): metal4, 2.6 um wide, 3.2 um pitch, alternating source
    # (VIN) / drain (VOUT); via2 + via3 arrays across the strap on every row's bar, via4
    # array into the bus. Source straps also take the bulk bar (VIN).
    nrow = sum(1 for k in pb if re.match(r"S\d+$", k))
    xl, xr = pb["S0"][0], pb["S0"][1]
    SW, SPP = 2.6, 3.2
    straps, x, k = [], xl + 1.0 + SW / 2, 0
    while x + SW / 2 <= xr - 1.0:
        straps.append((x, "S" if k % 2 == 0 else "D"))
        x += SPP
        k += 1
    x_ea = top_pin["EAOUT"][0]           # EAOUT rises through the bulk row to the gate bar
    for x, t in straps:
        ys = [pb[f"{t}{i}"][2] for i in range(nrow)]
        if t == "S" and abs(x - x_ea) > SW / 2 + 0.8:
            ys.append(pb["B"][2])        # source straps also take the bulk bar (VIN)
        bus = y_vi if t == "S" else y_vo
        for by in ys:
            P.rect("metal3", x - SW / 2, by - 0.25, x + SW / 2, by + 0.25)
            P.rect("via2", x - SW / 2 + 0.05, by - 0.2, x + SW / 2 - 0.05, by + 0.2)
            P.rect("via3", x - SW / 2 + 0.05, by - 0.2, x + SW / 2 - 0.05, by + 0.2)
        P.rect("metal4", x - SW / 2, min(ys) - 0.25, x + SW / 2, bus[1])
        P.rect("via4", x - SW / 2 + 0.05, bus[0] + 0.05, x + SW / 2 - 0.05, bus[1] - 0.05)
    # Cc's VOUT strap and R1/R2's VOUT end into the VOUT bus; VREF on to the top edge (its pin)
    P.v("metal4", x_vs, mp_t, sum(y_vo) / 2, w=PSTRAP)
    P.wvia(4, 5, x_vs, sum(y_vo) / 2, w=PSTRAP)
    # R1/R2's VOUT end is a SENSE line (Kelvin): it does not touch the VOUT bus here, but
    # rises through both buses (metal3, no contact), runs along the top edge on metal4 and
    # lands on the VOUT bus at the VOUT pin, so the bus resistance between the pass device
    # and the pin is inside the regulation loop
    y_sense = y_vi[1] + 1.2
    x_sense = bx_r - 1.0
    P.via(2, 3, a_end[0], a_end[1])
    P.v("metal3", a_end[0], a_end[1], y_sense)
    P.via(3, 4, a_end[0], y_sense)
    P.h("metal4", y_sense, a_end[0], x_sense)
    P.via(3, 4, x_sense, y_sense)
    P.v("metal3", x_sense, y_sense, sum(y_vo) / 2)
    P.via(3, 5, x_sense, sum(y_vo) / 2)
    y_top = y_vi[1] + 1.0
    P.v("metal3", x_vr, mp_t, y_top)
    # PMOS ring (n-well tap = VIN) -> metal3 across the channel -> the pass device's bulk bar
    pr = mag(Pm)
    ring_top = max((r for r in pr["metal2"] if r[2] - r[0] > 20), key=lambda r: r[3])
    # on source-strap centres, so the jump lands inside the strap's via array on the bulk bar;
    # clear of the group's metal3 pins on the ring top
    busy = [p_[0] for net in ("VSS", "VIN_BIAS", "EAOUT", "VOUT", "VREF") for p_ in pins(Pm, net)]
    jx = [x for x, t in straps if t == "S" and abs(x - x_ea) > SW / 2 + 0.8
          and ring_top[0] + 1 < x < ring_top[2] - 1 and all(abs(x - b) > 2.0 for b in busy)]
    for xj in jx[::max(1, len(jx) // 3)][:3]:
        yr = (ring_top[1] + ring_top[3]) / 2
        P.wvia(2, 3, xj, yr, w=0.8)
        P.v("metal3", xj, yr, pb["B"][2], w=PW)

    # --- bottom: VSS bus (metal5, 6 um like the VIN / VOUT buses)
    y_vs = (y_b2 - PITCH - 7.0, y_b2 - PITCH - 1.0)
    yv = sum(y_vs) / 2
    P.rect("metal5", bx_l, y_vs[0], bx_r, y_vs[1])
    P.label("VSS", "metal5", (box["R1R2"][0] + box["Rref"][2]) / 2, yv)

    def to_vss(x, y, lo):                # metal<lo> point -> 1 um metal3 down -> VSS bus
        if lo == 1:
            P.via(1, 3, x, y)            # resistor rings: narrow metal1 bar, single via stack
        else:
            P.wvia(lo, 3, x, y, w=0.8)
        P.v("metal3", x, y, yv, w=PW)
        P.wvia(3, 5, x, yv, w=PW)
    nr = mag(N)
    ring_bot = min((r for r in nr["metal2"] if r[2] - r[0] > 20), key=lambda r: r[1])
    bot_pins = [p_[0] for net in ("IREF", "FB", "EN") for p_ in pins(N, net)]
    span = ring_bot[2] - ring_bot[0]
    cand = [ring_bot[0] + span * (i + 0.5) / 8 for i in range(8)]
    drops = [x for x in cand if all(abs(x - b) > 2.5 for b in bot_pins)][:5]
    for xj in drops:                                              # NMOS ring (p+ tap = VSS)
        to_vss(xj, (ring_bot[1] + ring_bot[3]) / 2, 2)
    rr = mag("Rref")
    rbot = min(rr["metal1"], key=lambda r: r[1])                  # Rref's guard ring
    to_vss((box["Rref"][0] + box["Rref"][2]) / 2, (rbot[1] + rbot[3]) / 2, 1)
    for k in ("B_start", "BULK"):                                 # R1/R2: R2's bottom end, ring
        to_vss(r1r2[k][0], r1r2[k][1], 2)

    # ================= step 3: test buffers, block ports =================
    tb = {k: bars(k) for k in ("MREFEA_MBIAS", "MPDEA", "MFBBUF", "MEAOUTBUF")}
    row_t = max(box[k][3] for k in tb)
    row_b = min(box[k][1] for k in tb)
    U = [row_t + 0.7 + i * PITCH for i in range(5)]        # above the row: VSS IREF_EA EAOUT_BUF FB_BUF VIN
    Lw = [row_b - 0.7 - i * PITCH for i in range(4)]       # below the row: VSS IREF_EA ENB_5V EAOUT
    assert U[-1] + W / 2 + 0.5 <= box["RrefEA"][1], "buffer channel too small"
    assert Lw[-1] - W / 2 - 0.3 >= box[N][1] - 0.8 + W / 2, "buffer channel overlaps the bottom channel"
    ch = {"VSS": U[0], "IREF_EA": U[1], "EAOUT_BUF": U[2], "FB_BUF": U[3], "VIN": U[4]}
    cl = {"VSS": Lw[0], "IREF_EA": Lw[1], "ENB_5V": Lw[2], "EAOUT": Lw[3]}
    xs_u, xs_l = {}, {}

    def stub(x, bar_ys, y_track, tracks_x, net):
        """metal3 stub at x through the given metal2 bars (via2 on each) to a track."""
        for by in bar_ys:
            P.via(2, 3, x, by)
        P.v("metal3", x, min(bar_ys + [y_track]), max(bar_ys + [y_track]))
        P.via(3, 4, x, y_track)
        tracks_x.setdefault(net, []).append(x)
    m = tb["MREFEA_MBIAS"]                 # BACCAB: A = MREFEA (diode), B = MBIASEA, C = MBIASFB
    stub(min(m["A_G"][1], m["B_G"][1], m["C_G"][1]) - 0.5, [m["A_G"][2], m["B_G"][2], m["C_G"][2]],
         cl["IREF_EA"], xs_l, "IREF_EA")
    stub(m["B"][0] + 0.6, [m["B"][2]], cl["VSS"], xs_l, "VSS")
    stub(min(m["A_S"][1], m["B_S"][1], m["C_S"][1]) - 0.3, [m["A_S"][2], m["B_S"][2], m["C_S"][2]],
         ch["VSS"], xs_u, "VSS")
    stub(m["A_D"][0] + 0.56, [m["A_D"][2]], ch["IREF_EA"], xs_u, "IREF_EA")
    stub(m["B_D"][0] + 0.6, [m["B_D"][2]], ch["EAOUT_BUF"], xs_u, "EAOUT_BUF")
    stub(m["C_D"][0] + 1.0, [m["C_D"][2]], ch["FB_BUF"], xs_u, "FB_BUF")
    for inst, gnet, snet, dnet in (("MPDEA", "ENB_5V", "VSS", "IREF_EA"), ("MFBBUF", "FB", "FB_BUF", "VIN"),
                                   ("MEAOUTBUF", "EAOUT", "EAOUT_BUF", "VIN")):
        b = tb[inst]
        stub(b["B"][0] + 0.5, [b["B"][2]], cl["VSS"], xs_l, "VSS")
        stub(b["S"][0] + 0.35, [b["S"][2]], ch[snet], xs_u, snet)
        stub(b["D"][1] - 0.35, [b["D"][2]], ch[dnet], xs_u, dnet)
        gx = (b["G"][0] + b["G"][1]) / 2
        if gnet == "FB":                                  # down to the bottom-channel FB track
            P.via(2, 3, gx, b["G"][2])
            P.v("metal3", gx, b["G"][2], y_b2)
            P.via(3, 4, gx, y_b2)
            P.h("metal4", y_b2, gx, min(fb_x))
        else:
            stub(gx, [b["G"][2]], cl[gnet], xs_l, gnet)
    # RrefEA: A (left) = IREF_EA, B (right) = VIN_BIAS, ring = VSS
    rc2 = sorted(mag("RrefEA")["polycontact"])
    (ea, eb) = [((c[0] + c[2]) / 2, (c[1] + c[3]) / 2) for c in rc2]
    P.via(1, 3, ea[0], ea[1])
    P.v("metal3", ea[0], ea[1], ch["IREF_EA"])
    P.via(3, 4, ea[0], ch["IREF_EA"])
    xs_u["IREF_EA"].append(ea[0])
    rbe = min(mag("RrefEA")["metal1"], key=lambda r: r[1])
    x_rv = min(xs_u["VSS"]) + 1.5
    P.via(1, 3, x_rv, (rbe[1] + rbe[3]) / 2)
    P.v("metal3", x_rv, (rbe[1] + rbe[3]) / 2, ch["VSS"])
    P.via(3, 4, x_rv, ch["VSS"])
    xs_u["VSS"].append(x_rv)
    # VIN_BIAS: bottom channel level 3, from the right side of Rref all the way to RrefEA's B end
    y_b3 = y_b2 - PITCH
    P.via(3, 4, x_rb, y_b1)
    P.v("metal3", x_rb, y_b1, y_b3)
    P.via(3, 4, x_rb, y_b3)
    # RrefEA's contacts sit right above the buffer row: from the B contact, drop only into the
    # gap above the channel tracks, cross right on metal5 and go down beside the cluster
    x_vb2 = max(box[k][2] for k in bufs) + 1.5
    y_h = (U[-1] + box["RrefEA"][1]) / 2
    P.via(1, 3, eb[0], eb[1])
    P.v("metal3", eb[0], eb[1], y_h)
    P.via(3, 5, eb[0], y_h)
    P.h("metal5", y_h, eb[0], x_vb2, w=0.44)
    P.via(3, 5, x_vb2, y_h)
    P.v("metal3", x_vb2, y_h, y_b3)
    P.via(3, 4, x_vb2, y_b3)
    P.h("metal4", y_b3, x_vb2, x_rb)
    # links between the two buffer channels and to the LDO
    x_ir = box["MREFEA_MBIAS"][0] - 1.5                    # IREF_EA: upper <-> lower, left of the row
    P.v("metal3", x_ir, cl["IREF_EA"], ch["IREF_EA"])
    P.via(3, 4, x_ir, cl["IREF_EA"])
    P.via(3, 4, x_ir, ch["IREF_EA"])
    xs_u["IREF_EA"].append(x_ir)
    xs_l["IREF_EA"].append(x_ir)
    x_vsr = (box["MREFEA_MBIAS"][2] + box["MPDEA"][0]) / 2  # VSS: upper <-> lower, between cells
    P.v("metal3", x_vsr, cl["VSS"], ch["VSS"])
    P.via(3, 4, x_vsr, cl["VSS"])
    P.via(3, 4, x_vsr, ch["VSS"])
    xs_u["VSS"].append(x_vsr)
    xs_l["VSS"].append(x_vsr)
    x_vd = x_ir + 1.2                                      # lower VSS -> the VSS bus
    P.v("metal3", x_vd, cl["VSS"], yv, w=PW)
    P.via(3, 4, x_vd, cl["VSS"])
    P.wvia(3, 5, x_vd, yv, w=PW)
    xs_l["VSS"].append(x_vd)
    x_vin = (box["RrefEA"][2] + box["R1R2"][0]) / 2        # VIN: up beside RrefEA to the VIN bus
    P.v("metal3", x_vin, ch["VIN"], sum(y_vi) / 2, w=2.0)
    P.via(3, 4, x_vin, ch["VIN"])
    P.wvia(3, 5, x_vin, sum(y_vi) / 2, w=1.8)
    xs_u["VIN"].append(x_vin)
    # EAOUT: tap the EAOUT riser at the VOUT level, left over the core, down the left channel
    P.via(3, 4, x_ea, y_vout)
    P.h("metal4", y_vout, x_le, x_ea)
    P.via(3, 4, x_le, y_vout)
    P.v("metal3", x_le, y_vout, cl["EAOUT"])
    P.via(3, 4, x_le, cl["EAOUT"])
    xs_l["EAOUT"].append(x_le)
    # ENB_5V: tap the bridge between the groups, left, down the left channel
    xb_, yb_ = pins(N, "ENB_5V")[-1]
    y_gap = (yb_ + pins(Pm, "ENB_5V")[0][1]) / 2
    P.via(3, 4, xb_, y_gap)
    P.h("metal4", y_gap, x_lb, xb_)
    P.via(3, 4, x_lb, y_gap)
    P.v("metal3", x_lb, y_gap, cl["ENB_5V"])
    P.via(3, 4, x_lb, cl["ENB_5V"])
    xs_l["ENB_5V"].append(x_lb)
    # the channel tracks; FB_BUF / EAOUT_BUF out to the left edge (ports)
    for net, xs in xs_u.items():
        xa, xb2 = min(xs), max(xs)
        if net in ("FB_BUF", "EAOUT_BUF"):
            xa = bx_l
            P.port(net, "metal4", bx_l + 0.2, ch[net])
        P.h("metal4", ch[net], xa, xb2)
    for net, xs in xs_l.items():
        P.h("metal4", cl[net], min(xs), max(xs))
    # remaining ports
    x, y = pins(N, "EN")[0]
    P.v("metal3", x, y, y_vs[0] - 1.0)
    P.port("EN", "metal3", x, y_vs[0] - 0.8)
    P.port("VREF", "metal3", x_vr, y_top - 0.2)
    P.port("VIN", "metal5", bx_l + 1.0, sum(y_vi) / 2)
    P.port("VOUT", "metal5", bx_r - 1.0, sum(y_vo) / 2)
    P.port("VSS", "metal5", bx_l + 1.0, yv)
    return P


def write(P):
    place = (HERE / f"{PLACE}.mag").read_text().splitlines()
    assert place[:3] == ["magic", f"tech {bl.PDK}", "magscale 1 10"] and place[-1] == "<< end >>"
    uses = place[4:-1]                   # the placement's "use" records
    hdr = ["magic", f"tech {bl.PDK}", "magscale 1 10", "timestamp 0"]
    (HERE / f"{TOP}.mag").write_text("\n".join(hdr + uses + ["<< end >>"]) + "\n")
    t = ["addpath mag", f"load {TOP}", "snap internal"]
    for layer in ["metal1", "metal2", "metal3", "metal4", "metal5", "via1", "via2", "via3", "via4"]:
        for r in P.L.paint.get(layer, []):
            t += [f"box values {r[0]} {r[1]} {r[2]} {r[3]}", f"paint {layer}"]
    for net, layer, x, y in P.labels:
        t += [f"box values {bl.um(x)} {bl.um(y)} {bl.um(x)} {bl.um(y)}", f"label {net} c {layer}"]
    for i, (net, layer, x, y) in enumerate(P.ports, 1):
        t += [f"box values {bl.um(x)} {bl.um(y)} {bl.um(x)} {bl.um(y)}", f"label {net} c {layer}",
              f"port make {i}"]
    t += ["select top cell", "save", f"gds write {TOP}.gds",
          "extract unique",            # same-name labels on unconnected metal get distinct names:
          "extract all", "ext2spice lvs",   # no connection by label name alone "ext2spice hierarchy off", f"ext2spice -o lvs/{TOP}_lay.spice",
          "quit -noprompt"]
    (HERE / "_route.tcl").write_text("\n".join(t) + "\n")
    p = subprocess.run([bl.MAGIC, "-dnull", "-noconsole", "-rcfile", bl.RC, "_route.tcl"], cwd=HERE,
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    (HERE / "_route.tcl").unlink()
    if not (HERE / f"{TOP}.gds").exists():
        sys.exit(p.stdout[-2000:] + p.stderr[-2000:])


def drc():
    import collections
    rep = HERE / "lvs" / f"{TOP}.lyrdb"
    subprocess.run(["/foss/tools/klayout/klayout", "-b", "-r", DRC_DECK, "-rd", f"input={HERE / (TOP + '.gds')}",
                    "-rd", f"report={rep}", "-rd", "variant=gf180mcuD", "-rd", "run_mode=flat",
                    "-rd", f"topcell={TOP}"], capture_output=True, text=True)
    t = rep.read_text()
    cats = collections.Counter(c.strip("'") for c in re.findall(r"<item>.*?<category>(.*?)</category>", t, re.S))
    return {k: v for k, v in cats.items() if not DENSITY.match(k)}


def connectivity():
    """Which device terminals each labelled net reaches in the extracted layout (a check of
    the nets routed so far; full LVS once every net is wired)."""
    import collections
    text = (HERE / "lvs" / f"{TOP}_lay.spice").read_text().replace("\n+", " ")
    use = collections.defaultdict(collections.Counter)
    for line in text.splitlines():
        f = line.split()
        if not f or not f[0].upper().startswith("X") or len(f) < 4:
            continue
        model = next((t for t in f[1:] if re.match(r"[np]fet_0[356]v0$|ppolyf|cap_mim", t)), None)
        if model is None:
            continue
        nodes = f[1:f.index(model)]
        if model.startswith(("nfet", "pfet")):
            names = ("D", "G", "S", "B")
        elif model.startswith("cap"):
            names = ("TOP", "BOT")
        else:
            names = ("A", "B", "BULK")
        for n, t in zip(nodes, names):
            use[n][f"{model}.{t}"] += 1
    return use


def lvs():
    """Full LVS: extracted layout (dummies removed) against the schematic netlist."""
    src = HERE / "lvs" / f"{TOP}_lay.spice"
    text = src.read_text().replace("\n+", " ")
    out, n = [], 0
    for line in text.splitlines():
        f = line.split()
        if f and f[0].upper().startswith("X") and len(f) > 5:
            mos = re.match(r"[np]fet_0[356]v0$", f[5])
            res_ = f[4].startswith("ppolyf") and len({f[1], f[2], f[3]}) == 1
            if (mos and (len({f[1], f[2], f[3], f[4]}) == 1 or f[2] == f[4])) or res_:
                n += 1                 # dummy: all terminals on one net, or gate tied to bulk (off)
                continue
        out.append(line)
    body = [l for l in out if l.strip() and not l.startswith(("*", ".end", ".subckt", ".ends"))]
    ports = "VIN VREF EN VOUT FB_BUF EAOUT_BUF VSS"           # the schematic's port order
    (HERE / "lvs" / f"{TOP}_lvs.spice").write_text(f".subckt {TOP} {ports}\n" + "\n".join(body) + "\n.ends\n")
    p = subprocess.run([bl.NETGEN, "-batch", "lvs", f"{TOP}_lvs.spice {TOP}", f"{bl.SCH_NETLIST} ldo",
                        bl.NETGEN_SETUP, f"{TOP}.out"], cwd=HERE / "lvs", capture_output=True, text=True)
    res = (HERE / "lvs" / f"{TOP}.out").read_text()
    ok = "Circuits match uniquely" in res or "Netlists match uniquely" in res
    tail = [l.strip() for l in res.splitlines() if "match" in l.lower()][-3:]
    return n, ok, tail


def main():
    P = route()
    write(P)
    for f in HERE.glob("*.ext"):
        f.unlink()
    real = drc()
    print("KLayout DRC:", "clean" if not real else real)
    report_summary.drc_errors(HERE / "lvs" / f"{TOP}.lyrdb", HERE / "lvs" / f"{TOP}_drc_errors.txt")
    n, ok, tail = lvs()
    report_summary.lvs_result(HERE / "lvs" / f"{TOP}.out", HERE / "lvs" / f"{TOP}_lvs_result.txt", n,
                              "Extracted with 'extract unique': same-name labels count as one net only "
                              "if the metal is connected.")
    print(f"LVS vs schematic (ldo): {'MATCH' if ok else 'MISMATCH'}  ({n} dummies removed)", *tail, sep="\n  ")
    if not ok:
        use = connectivity()
        for net, _l, _x, _y in P.labels + P.ports:
            print(f"  {net:9s}", dict(use.get(net, {})))


if __name__ == "__main__":
    main()
