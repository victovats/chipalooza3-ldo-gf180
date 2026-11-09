#!/usr/bin/env python3
"""Render the screenshots for layout/README.md into layout/doc/.

    cd layout && python3 make_doc_images.py

Block-level views are shown mirrored top-to-bottom, the way the block sits in
the Chipalooza slot (VSS rail on top, pass device and VIN / VOUT at the bottom).
Each layer is drawn as a flat translucent colour (wells, implants and markers are left out).
"""
import json
from pathlib import Path

import klayout.db as db

HERE = Path(__file__).resolve().parent
DOC = HERE / "doc"
LYP = "/foss/pdks/gf180mcuD/libs.tech/klayout/tech/gf180mcu.lyp"
ROUTING = {(42, 0), (46, 0), (40, 0), (75, 0)}                                    # metal3, metal4, via3
POWER = {(81, 0), (41, 0), (46, 0)}                                      # metal5, via4, metal4
PLACE = json.loads((HERE / "ldo_v2_place_snug.json").read_text())
GROUPS = json.loads((HERE / "gl" / "groups.json").read_text())


def flipped_layout(src="ldo_v2.gds", name="_flipped.gds"):
    l = db.Layout()
    l.read(str(HERE / src))
    top = l.top_cell()
    f = l.create_cell("flipped")
    f.insert(db.CellInstArray(top.cell_index(), db.Trans(db.Trans.M0, 0, 0)))
    path = DOC / name
    l.write(str(path))
    return path, l.cell("flipped").dbbox()


# drawn bottom to top: (layer, datatype): (RGB, fill alpha)
STYLE = {(22, 0): ((0, 150, 60), 90),        # COMP (diffusion)
         (30, 0): ((210, 40, 40), 120),      # poly
         (34, 0): ((40, 90, 220), 60),       # metal1
         (36, 0): ((200, 140, 0), 60),       # metal2
         (42, 0): ((0, 150, 150), 60),       # metal3
         (46, 0): ((150, 60, 200), 60),      # metal4
         (75, 0): ((90, 90, 90), 50),        # MIM top plate
         (81, 0): ((235, 120, 20), 55),      # metal5
         (33, 0): ((30, 30, 30), 200),       # contact
         (35, 0): ((20, 40, 120), 200),      # via1
         (38, 0): ((120, 80, 0), 200),       # via2
         (40, 0): ((0, 90, 90), 200),        # via3
         (41, 0): ((120, 40, 0), 200)}       # via4
SS = 2                                        # supersampling factor


def render(gds, cell, box, out, width=2600, hide=None, only=None):
    """Flat-colour render straight from the polygons: each layer merged, filled with a
    translucent solid colour and outlined (no hatch patterns, so nothing aliases)."""
    from PIL import Image, ImageDraw
    l = db.Layout()
    l.read(str(gds))
    c = l.cell(cell)
    W, H = width, int(width * box.height() / box.width())
    sx = W * SS / box.width()
    img = Image.new("RGBA", (W * SS, H * SS), (255, 255, 255, 255))
    clip = db.Region(box.to_itype(l.dbu))
    for key, (rgb, alpha) in STYLE.items():
        if only is not None and key not in only:
            continue
        li = l.find_layer(*key)
        if li is None:
            continue
        reg = (db.Region(c.begin_shapes_rec(li)) & clip).merged()
        if reg.is_empty():
            continue
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        edge = tuple(int(v * 0.7) for v in rgb) + (255,)

        def pts(it):
            return [((p.x * l.dbu - box.left) * sx, (box.top - p.y * l.dbu) * sx) for p in it]
        for poly in reg.each():
            hull = pts(poly.each_point_hull())
            d.polygon(hull, fill=rgb + (alpha,))
            for h in range(poly.holes()):
                d.polygon(pts(poly.each_point_hole(h)), fill=(0, 0, 0, 0))
            d.line(hull + hull[:1], fill=edge, width=SS)
            for h in range(poly.holes()):
                hp = pts(poly.each_point_hole(h))
                d.line(hp + hp[:1], fill=edge, width=SS)
        img.alpha_composite(ov)
    img = img.convert("RGB").resize((W, H), Image.LANCZOS)
    # 10 um scale bar, bottom left
    d = ImageDraw.Draw(img)
    from PIL import ImageFont
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(14, W // 120))
    bar = 10 * W / box.width()
    y = H - max(20, H // 40)
    d.rectangle((20, y, 20 + bar, y + max(4, W // 600)), fill="black")
    d.text((20 + bar + 8, y + 2), "10 µm", font=f, fill="black", anchor="lm")
    img.save(DOC / out)
    print("wrote", out)


def fbox(inst, pad=1.5):
    """A placed cell's box in the flipped view."""
    b = PLACE[inst]["box"]
    return db.DBox(b[0] - pad, -b[3] - pad, b[2] + pad, -b[1] + pad)


def main():
    DOC.mkdir(exist_ok=True)
    fg, bb = flipped_layout()
    full = db.DBox(bb.left - 2, bb.bottom - 2, bb.right + 2, bb.top + 2)
    render(fg, "flipped", full, "v2_overview.png", 2800)
    render(fg, "flipped", full, "v2_power_grid.png", 2800, only=POWER)
    render(fg, "flipped", full, "v2_signal_routing.png", 2800, only=ROUTING | {(22, 0)})
    # transistor groups (their own GDS, as built)
    for g, out in (("v2_nmos_core", "v2_nmos_group.png"), ("v2_pmos_core", "v2_pmos_group.png")):
        gl = db.Layout()
        gl.read(str(HERE / "gl" / f"{g}.gds"))
        b = gl.top_cell().dbbox()
        render(HERE / "gl" / f"{g}.gds", g, db.DBox(b.left - 1, b.bottom - 1, b.right + 1, b.top + 1), out, 2400)
    # folded input pair (two rows, A B B A over B A A B) inside the NMOS group
    o = PLACE["v2_nmos_core"]["origin"]
    bs = [x["box"] for x in GROUPS["v2_nmos_core"]["devices"] if x["name"] == "MIN1_MIN2"]   # both rows
    b = [min(q[0] for q in bs), min(q[1] for q in bs), max(q[2] for q in bs), max(q[3] for q in bs)]
    pair = db.DBox(b[0] + o[0] - 2, -(b[3] + o[1]) - 3, b[2] + o[0] + 2, -(b[1] + o[1]) + 3)
    render(fg, "flipped", pair, "v2_input_pair.png", 2400)
    # left side of the core: the riser bundle and the left channel
    n, p = PLACE["v2_nmos_core"]["box"], PLACE["v2_pmos_core"]["box"]
    x0 = PLACE["R1R2"]["box"][2] - 1
    render(fg, "flipped", db.DBox(x0, -p[3] - 6, (n[0] + n[2]) / 2 - 4, -n[1] + 4), "v2_core_left.png", 1800)
    # pass device, straps and buses
    m = PLACE["MPASS"]["box"]
    render(fg, "flipped", db.DBox(m[0] - 3, bb.bottom - 1, m[2] + 4, -m[3] + 3), "v2_pass_device.png", 2800)
    # Cc, Rref and the channel to the pass device (EAOUT / VOUT / VREF / VIN_BIAS)
    c, r = PLACE["Cc"]["box"], PLACE["Rref"]["box"]
    render(fg, "flipped", db.DBox(p[2] - 8, -m[1] - 3, bb.right + 1, -r[1] + 2), "v2_cc_channel.png", 2000)
    # test buffers
    tb = [PLACE[k]["box"] for k in ("RrefEA", "MREFEA_MBIAS", "MPDEA", "MFBBUF", "MEAOUTBUF")]
    render(fg, "flipped", db.DBox(min(q[0] for q in tb) - 2, -max(q[3] for q in tb) - 2,
                                  max(q[2] for q in tb) + 10, -min(q[1] for q in tb) + 2), "v2_test_buffers.png", 2000)
    (DOC / "_flipped.gds").unlink()
    labelled(full)
    print("wrote v2_labelled.png")
    # placement before wiring (place_v2.py output), same rendering as the rest
    pg, pb = flipped_layout("ldo_v2_place_snug.gds", "_placed.gds")
    render(pg, "flipped", db.DBox(pb.left - 2, pb.bottom - 2, pb.right + 2, pb.top + 2), "v2_placement.png", 2800)
    (DOC / "_placed.gds").unlink()


def labelled(full):
    """Component names drawn straight onto the overview screenshot (native resolution,
    nothing resampled or faded)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(DOC / "v2_overview.png").convert("RGB")
    W, H = img.size
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)

    def px(x, y):
        return ((x - full.left) / full.width() * W, (full.top - y) / full.height() * H)

    def tag(x, y, text, f, edge):
        l, t, r, b = d.multiline_textbbox((0, 0), text, font=f, align="center", spacing=6)
        w_, h_ = r - l + 28, b - t + 20
        d.rounded_rectangle((x - w_ / 2, y - h_ / 2, x + w_ / 2, y + h_ / 2), radius=10, fill="white",
                            outline=edge, width=4)
        d.multiline_text((x, y), text, font=f, fill="black", anchor="mm", align="center", spacing=6)
    big = {"RrefEA": "RrefEA\n2 MΩ resistor\n(test-buffer bias)", "R1R2": "R1 / R2\nfeedback divider",
           "v2_nmos_core": "NMOS group", "v2_pmos_core": "PMOS group", "Rref": "Rref",
           "Cc": "Cc\n3 pF Miller cap", "MPASS": "MPASS (pass transistor)"}
    for k, txt in big.items():
        b = fbox(k, 0)
        tag(*px((b.left + b.right) / 2, (b.bottom + b.top) / 2), txt, font, "#1f5fb4")
    for k, txt, (dx, dy) in (("MREFEA_MBIAS", "bias mirror", (0, -150)), ("MPDEA", "MPDEA", (40, -230)),
                             ("MFBBUF", "MFBBUF", (150, -300)), ("MEAOUTBUF", "MEAOUTBUF", (330, -170))):
        b = fbox(k, 0)
        x, y = px((b.left + b.right) / 2, (b.bottom + b.top) / 2)
        d.line((x, y, x + dx, y - dy), fill="#c2185b", width=4)
        tag(x + dx, y - dy, txt, small, "#c2185b")
    tag(W / 2, px(0, full.top - 4.5)[1], "VSS rail (6 µm metal5, edge to edge)", small, "#5e35b1")
    tag(W / 2, px(0, full.bottom + 4.0)[1], "VIN rail (6 µm metal5, edge to edge); VOUT bus just above it",
        small, "#e65100")
    img.save(DOC / "v2_labelled.png")


if __name__ == "__main__":
    main()
