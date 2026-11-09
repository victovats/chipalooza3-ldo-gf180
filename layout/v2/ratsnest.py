#!/usr/bin/env python3
"""Layout v2: rat's nest of the current placement (before wiring).

    cd layout/v2 && python3 place_v2.py [top] && python3 ratsnest.py [top]

Every schematic net (from ../build_layout.py ROWS) is drawn as a minimum
spanning tree over its device terminals, with Manhattan edge lengths -- a
close estimate of the wire length a router will need. Terminal points:

  * transistors in a core group: the centre of that device's fingers
    (gl/groups.json "box"); both halves of a matched pair share the centroid
  * other transistors, Cc, MPASS: the cell centre
  * Rref / RrefEA: the two contacts at the bottom corners (A left, B right)
  * R1R2: the chain-end stubs from make_res_array

VSS and the bulks are left out (rings and the bottom bus carry them). VIN is
drawn thin (it is the top bus). Test-buffer branches are drawn grey: they are
not part of the LDO. Writes ratsnest[_top].png and ratsnest[_top].md (length table).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUFFIX = "_" + sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "side" else ""
sys.path.insert(0, str(HERE.parent))
import build_layout as bl  # noqa: E402

BUFFERS = {"RrefEA", "MREFEA_MBIAS", "MPDEA", "MFBBUF", "MEAOUTBUF"}
SKIP_NETS = {"VSS"}
SKIP_TERMS = {"B", "BULK"}                   # transistor bulk; for resistors "B" is a terminal
STATIC = {"ENB_5V", "EN_5V", "VIN_BIAS"}          # enable / bias: DC after start-up
# colours: reference categorical slots 1-2, muted ink for buffers / VIN
C_SIG, C_STATIC, C_BUF, C_VIN = "#2a78d6", "#eb6834", "#9a9893", "#c3c2b7"
INK, INK2, SURF = "#0b0b0b", "#52514e", "#fcfcfb"


def terminals():
    place = json.loads((HERE / f"ldo_v2_place{SUFFIX}.json").read_text())
    groups = json.loads((HERE / "gl" / "groups.json").read_text())
    sub = {}                                       # device inside a group -> (group, box)
    for g, v in groups.items():
        for d in v["devices"]:                     # a folded device spans both of its rows
            b = sub[d["name"]][1] if d["name"] in sub else d["box"]
            sub[d["name"]] = (g, [min(b[0], d["box"][0]), min(b[1], d["box"][1]),
                                  max(b[2], d["box"][2]), max(b[3], d["box"][3])])
    pts = []                                       # (net, inst, term, x, y)
    for row in bl.ROWS:
        for inst, kind, spec, nets in row:
            if inst in sub:
                g, b = sub[inst]
                ox, oy = place[g]["origin"]
                c = ((b[0] + b[2]) / 2 + ox, (b[1] + b[3]) / 2 + oy)
                pos = {t: c for t in nets}
            else:
                x0, y0, x1, y1 = place[inst]["box"]
                c = ((x0 + x1) / 2, (y0 + y1) / 2)
                pos = {t: c for t in nets}
                if kind == "res":
                    pos.update(A=(x0 + 1.5, y0 + 1.5), B=(x1 - 1.5, y0 + 1.5))
                elif kind == "resarray":
                    ox, oy = place[inst]["origin"]
                    cache = json.loads((bl.MAG / "devices.json").read_text())
                    tl, _ = bl.make_res_array(cache["|".join(spec)])
                    for key, x, y, _d in tl:
                        pos[key] = (x / bl.UM + ox, y / bl.UM + oy)
            for t, net in nets.items():
                if net in SKIP_NETS or t == "BULK" or (t == "B" and kind not in ("res", "resarray")):
                    continue
                pts.append((net, inst, t, *pos[t]))
    return place, sub, pts


def mst(nodes):
    """Prim's MST with Manhattan distance. nodes: [(x, y, inst)] -> [(i, j, length)]"""
    if len(nodes) < 2:
        return []
    inside, edges = {0}, []
    while len(inside) < len(nodes):
        best = min(((abs(nodes[i][0] - nodes[j][0]) + abs(nodes[i][1] - nodes[j][1]), i, j)
                    for i in inside for j in range(len(nodes)) if j not in inside))
        edges.append((best[1], best[2], best[0]))
        inside.add(best[2])
    return edges


def nets_tree(pts):
    """Per net: LDO-only tree, then each test-buffer terminal hooked to the nearest node."""
    out = {}
    for net in sorted({p[0] for p in pts}):
        uniq = {}
        for _, inst, _t, x, y in (p for p in pts if p[0] == net):
            uniq[(round(x, 2), round(y, 2))] = inst
        ldo = [(x, y, i) for (x, y), i in uniq.items() if i not in BUFFERS]
        buf = [(x, y, i) for (x, y), i in uniq.items() if i in BUFFERS]
        e_ldo = [(ldo[i], ldo[j], d) for i, j, d in mst(ldo)]
        e_buf = []
        if ldo:
            for b in buf:
                n = min(ldo, key=lambda a: abs(a[0] - b[0]) + abs(a[1] - b[1]))
                e_buf.append((n, b, abs(n[0] - b[0]) + abs(n[1] - b[1])))
        else:
            e_buf = [(buf[i], buf[j], d) for i, j, d in mst(buf)]
        devs = sorted({i for *_, i in ldo + buf})
        out[net] = dict(ldo=e_ldo, buf=e_buf, devs=devs, buffer_only=not ldo)
    return out


def draw(place, sub, trees):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    ldo = [p for i, p in place.items() if i not in BUFFERS]     # the plot shows the LDO rectangle;
    xs = [v for p in ldo for v in (p["box"][0], p["box"][2])]  # buffer branches leave to the left
    ys = [v for p in ldo for v in (p["box"][1], p["box"][3])]
    W, H = max(xs) - min(xs), max(ys) - min(ys)
    fig, ax = plt.subplots(figsize=(22, 22 * (H + 16) / (W + 14)), dpi=120)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for inst, p in place.items():                  # cells
        x0, y0, x1, y1 = p["box"]
        buf = inst in BUFFERS
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="#f0efea" if buf else "#e9eef5",
                               ec="#c3c2b7" if buf else "#8fa6c4", lw=1.0, zorder=1))
        if not inst.startswith("v2_"):
            ax.text(x0 + 0.6, y1 - 0.6, inst, fontsize=8, color=INK2, va="top", zorder=5, clip_on=True)
    for name, (g, b) in sub.items():               # devices inside the shared rings
        ox, oy = place[g]["origin"]
        ax.add_patch(Rectangle((b[0] + ox, b[1] + oy), b[2] - b[0], b[3] - b[1],
                               fc="#d5dfec", ec="#6f8db5", lw=0.8, zorder=2))
        ax.text(b[0] + ox + 0.3, b[3] + oy + 0.25, name, fontsize=6.5, color=INK2, zorder=5)

    def seg(a, b, col, lw, ls="-"):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=col, lw=lw, ls=ls, zorder=3, solid_capstyle="round")
        for p in (a, b):
            ax.add_patch(plt.Circle(p[:2], 0.45, color=col, zorder=4))

    ax.set_xlim(min(xs) - 12, max(xs) + 2)
    ax.set_ylim(min(ys) - 2, max(ys) + 12)
    ax.set_aspect("equal")
    labels = []
    for net, t in trees.items():
        if net == "VIN":
            col, lw = C_VIN, 1.2
        elif t["buffer_only"]:
            col, lw = C_BUF, 1.6
        else:
            col, lw = (C_STATIC if net in STATIC else C_SIG), 2.0
        for a, b, _ in t["ldo"]:
            seg(a, b, col, lw)
        for a, b, _ in t["buf"]:
            seg(a, b, C_BUF, 1.4, "--")
        if net != "VIN":                          # direct label near the longest edge
            edges = t["ldo"] or t["buf"]
            if edges:
                a, b, _ = max(edges, key=lambda e: e[2])
                L = sum(e[2] for e in t["ldo"])
                Lb = sum(e[2] for e in t["buf"])
                txt = f"{net} {L:.0f} µm" + (f" (+{Lb:.0f} to buffer)" if Lb and L else "")
                if t["buffer_only"]:              # buffer-only nets: in the table, off the plot
                    continue
                labels.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, txt, col))
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    placed = []
    for x, y, txt, col in sorted(labels, key=lambda l: -l[1]):
        for dx, dy in [(0, 0), (0, 2.2), (0, -2.2), (0, 4.4), (0, -4.4), (9, 0), (-9, 0), (9, 2.2),
                       (-9, 2.2), (9, -2.2), (-9, -2.2), (0, 6.6), (0, -6.6), (14, 0), (-14, 0)]:
            tx = ax.text(x + dx, y + dy, txt, fontsize=10, color=INK, ha="center", va="center", zorder=6,
                         bbox=dict(boxstyle="round,pad=0.25", fc=SURF, ec=col, lw=1.2, alpha=0.95))
            bb = tx.get_window_extent(rend).expanded(1.05, 1.15)
            if not any(bb.overlaps(o) for o in placed):
                placed.append(bb)
                if (dx, dy) != (0, 0):
                    ax.plot([x, x + dx], [y, y + dy], color=col, lw=0.8, zorder=5)
                break
            tx.remove()
        else:
            ax.text(x, y, txt, fontsize=10, color=INK, ha="center", zorder=6)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], color=C_SIG, lw=2.5, label="LDO signal net"),
                       Line2D([], [], color=C_STATIC, lw=2.5, label="enable / bias net (DC after start-up)"),
                       Line2D([], [], color=C_BUF, lw=1.6, ls="--", label="test-buffer branch (not part of the LDO)"),
                       Line2D([], [], color=C_VIN, lw=1.2, label="VIN (will be the top bus)")],
              loc="upper left", bbox_to_anchor=(0, 1.0), ncol=4, frameon=False, fontsize=11,
              labelcolor=INK)
    ax.set_xlim(min(xs) - 12, max(xs) + 2)
    ax.text(min(xs) - 11, min(ys) + 1, "← to the test\nbuffers", fontsize=10, color=INK2)
    ax.set_ylim(min(ys) - 2, max(ys) + 12)
    ax.set_aspect("equal")
    ax.tick_params(colors=INK2, labelsize=9)
    for s in ax.spines.values():
        s.set_color("#c3c2b7")
    ax.set_xlabel("x (µm)", color=INK2)
    ax.set_ylabel("y (µm)", color=INK2)
    ax.set_title(f"LDO v2 placement ({SUFFIX[1:] or 'side'} floorplan) — rat's nest (minimum spanning tree per net, Manhattan length; "
                 "VSS and bulks via rings / bottom bus, not shown)", color=INK, fontsize=13, loc="left")
    fig.tight_layout()
    fig.savefig(HERE / f"ratsnest{SUFFIX}.png", facecolor=SURF)


def main():
    place, sub, pts = terminals()
    trees = nets_tree(pts)
    rows = []
    for net, t in trees.items():
        L = sum(e[2] for e in t["ldo"])
        Lb = sum(e[2] for e in t["buf"])
        rows.append((net, L, Lb, ", ".join(t["devs"])))
    rows.sort(key=lambda r: -(r[1] or r[2]))
    md = ["| net | LDO length (µm) | test-buffer branch (µm) | devices |", "|---|---:|---:|---|"]
    md += [f"| {n} | {L:.0f} | {Lb:.0f} | {d} |" for n, L, Lb, d in rows]
    (HERE / f"ratsnest{SUFFIX}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    draw(place, sub, trees)


if __name__ == "__main__":
    main()
