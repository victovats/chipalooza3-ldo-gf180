"""Plain-text summaries of the DRC and LVS reports (written by route_v2.py and check_groups.py).

    <name>_drc_errors.txt   every violation in the KLayout DRC report (<name>.lyrdb):
                            rule, description, location; whole-die density rules marked
    <name>_lvs_result.txt   the netgen verdict from <name>.out, with device / net counts
"""
import re
import xml.etree.ElementTree as ET

DENSITY = re.compile(r"^M\d\.4$|^MT\.3$|^DCF\.1b$|^PL\.8$")    # met by the harness's chip-level fill


def _categories(node, prefix="", out=None):
    out = {} if out is None else out
    for c in node.findall("category"):
        name = prefix + c.findtext("name")
        out[name] = " ".join((c.findtext("description") or "").split())
        sub = c.find("categories")
        if sub is not None:
            _categories(sub, name + ".", out)
    return out


def drc_errors(lyrdb, out):
    root = ET.parse(lyrdb).getroot()
    desc = _categories(root.find("categories"))
    items = []
    for it in root.find("items"):
        rule = it.findtext("category").strip("'")
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", " ".join(
            v.text or "" for v in it.iter("value")))]
        xs, ys = nums[0::2], nums[1::2]
        where = f"({min(xs):.2f}, {min(ys):.2f}) - ({max(xs):.2f}, {max(ys):.2f}) um" if xs else "-"
        items.append((rule, it.findtext("cell"), where))
    real = [i for i in items if not DENSITY.match(i[0])]
    lines = [f"DRC violations: {lyrdb.name} (official GF180MCU KLayout deck, {len(desc)} rules checked)",
             "",
             f"Geometry violations: {len(real)}",
             f"Whole-die density entries: {len(items) - len(real)} (met by the harness's chip-level fill)",
             "",
             f"{'rule':8s} {'type':9s} {'cell':14s} location / description"]
    for rule, cell, where in sorted(items):
        kind = "density" if DENSITY.match(rule) else "GEOMETRY"
        lines += [f"{rule:8s} {kind:9s} {cell:14s} {where}", f"{'':33s}{desc.get(rule, '')}"]
    lines += ["", "Every other rule: 0 violations.",
              "RESULT: " + ("DRC clean (density entries only)" if not real else f"{len(real)} GEOMETRY VIOLATION(S)")]
    out.write_text("\n".join(lines) + "\n")
    return real


def lvs_result(report, out, dummies, extra=""):
    text = report.read_text()
    final = [l.strip() for l in text.splitlines() if l.startswith("Final result")]
    counts = [l for l in text.splitlines() if l.startswith(("Number of devices", "Number of nets"))][-2:]
    ok = bool(final) and "match uniquely" in final[-1] and "property errors" not in text.lower()
    lines = [f"LVS result: {report.name} (magic extraction vs the schematic, netgen)",
             "",
             f"RESULT: {'PASS' if ok else 'FAIL'} - {final[-1] if final else 'no final result in report'}",
             "Property (W / L / value) errors: " + ("yes" if "property errors" in text.lower() else "none"),
             ""]
    lines += ["layout                                     | schematic"] + [l.rstrip() for l in counts]
    lines += ["", f"{dummies} dummy devices (gate tied to the bulk, always off) removed before the compare."]
    if extra:
        lines += [extra]
    lines += [f"Full netgen report: {report.name}"]
    out.write_text("\n".join(lines) + "\n")
    return ok
