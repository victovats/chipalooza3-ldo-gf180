#!/usr/bin/env python3
"""DRC + LVS of the wired core groups (gl/<group>.gds from core_groups.py).

    cd layout && python3 check_groups.py [group ...]

DRC: the official GF180MCU KLayout deck (gf180mcuD); the whole-die density
rules (Mx.4, MT.3, DCF.1b, PL.8: met by chip-level fill) are reported separately.
LVS: magic extraction, dummy devices removed (MOS whose gate is tied to its
own bulk: always off -- no real device of the LDO is wired that way), then
netgen against a reference netlist built from build_layout.ROWS: every
finger of every device in the group, with the group's pins as ports.
Writes lvs/<group>_{lay,ref}.spice and lvs/<group>.out.
"""
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_layout as bl  # noqa: E402

DRC_DECK = "/foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc"
KLAYOUT = "/foss/tools/klayout/klayout"
LVS = HERE / "lvs"
DENSITY = re.compile(r"^M\d\.4$|^MT\.3$|^DCF\.1b$|^PL\.8$")   # whole-die density rules


def drc(group):
    rep = LVS / f"{group}.lyrdb"
    subprocess.run([KLAYOUT, "-b", "-r", DRC_DECK, "-rd", f"input={HERE / 'gl' / (group + '.gds')}",
                    "-rd", f"report={rep}", "-rd", "variant=gf180mcuD", "-rd", "run_mode=flat"],
                   capture_output=True, text=True)
    t = rep.read_text()
    cats = collections.Counter(c.strip("'") for c in re.findall(r"<item>.*?<category>(.*?)</category>", t, re.S))
    real = {k: v for k, v in cats.items() if not DENSITY.match(k)}
    return real, {k: v for k, v in cats.items() if DENSITY.match(k)}


def nets_of(name):
    for row in bl.ROWS:
        for inst, _k, _s, nets in row:
            if inst == name:
                return nets
    raise KeyError(name)


def reference(group, info):
    """Reference subcircuit: one MOS per finger, nets from the schematic."""
    nfet, bulk = info["nfet"], info["bulk"]
    lines = []
    count = collections.Counter()
    for d in info["devices"]:
        n = nets_of(d["name"])
        model = ("nfet_05v0" if d["v5"] else "nfet_06v0") if nfet else "pfet_06v0"
        if d["pattern"] == "P":
            devs = [(d["name"], n["D"], n["G"], n["S"], d["fingers"])]
        else:
            parts = d["name"].split("_")
            c = collections.Counter(ch for ch in d["pattern"] if ch in "AB")
            devs = [(parts[i], n[f"{L}_D"], n[f"{L}_G"], n[f"{L}_S"], c[L]) for i, L in enumerate("AB")]
        for dev, D, G, S, k in devs:
            for _ in range(k):
                count[dev] += 1
                lines.append(f"X{dev}_{count[dev]} {D} {G} {S} {bulk} {model} w={d['w']}u l={d['l']}u")
    ports = sorted(info["pins"])
    return f".subckt {group} {' '.join(ports)}\n" + "\n".join(lines) + "\n.ends\n"


def extract(group, ports):
    tcl = LVS / f"_ext_{group}.tcl"
    tcl.write_text("\n".join([
        f"gds read {HERE / 'gl' / (group + '.gds')}", f"load {group}", "select top cell", "extract all",
        "ext2spice lvs", "ext2spice hierarchy off", f"ext2spice -o {group}_lay.spice", "quit -noprompt"]) + "\n")
    subprocess.run([bl.MAGIC, "-dnull", "-noconsole", "-rcfile", bl.RC, tcl.name], cwd=LVS,
                   stdin=subprocess.DEVNULL, capture_output=True, text=True)
    tcl.unlink()
    for f in LVS.glob("*.ext"):
        f.unlink()
    text = (LVS / f"{group}_lay.spice").read_text().replace("\n+", " ")
    out, n = [], 0
    for line in text.splitlines():
        f = line.split()
        if f and f[0].upper().startswith("X") and len(f) > 5 and re.match(r"[np]fet_0[356]v0$", f[5]) \
                and f[2] == f[4]:                     # gate == bulk: an always-off dummy
            n += 1
            continue
        out.append(line)
    body = [l for l in out if l.strip() and not l.startswith("*") and not l.startswith(".end")]
    (LVS / f"{group}_lay_lvs.spice").write_text(f".subckt {group} {' '.join(ports)}\n" + "\n".join(body)
                                                + "\n.ends\n")
    return n


def lvs(group):
    p = subprocess.run([bl.NETGEN, "-batch", "lvs", f"{group}_lay_lvs.spice {group}", f"{group}_ref.spice {group}",
                        bl.NETGEN_SETUP, f"{group}.out"], cwd=LVS, capture_output=True, text=True)
    res = (LVS / f"{group}.out").read_text() if (LVS / f"{group}.out").exists() else p.stdout
    ok = "Netlists match uniquely" in res or "Circuits match uniquely" in res
    tail = [l.strip() for l in res.splitlines() if "match" in l.lower() or "mismatch" in l.lower()]
    return ok, tail[-3:]


def main():
    LVS.mkdir(exist_ok=True)
    info = json.loads((HERE / "gl" / "groups.json").read_text())
    for group in sys.argv[1:] or list(info):
        real, dens = drc(group)
        print(f"{group}: DRC {'clean' if not real else real}  (chip-level density: {sorted(dens)})")
        (LVS / f"{group}_ref.spice").write_text(reference(group, info[group]))
        n = extract(group, sorted(info[group]["pins"]))
        ok, tail = lvs(group)
        print(f"{group}: {n} dummy devices removed; LVS {'MATCH' if ok else 'MISMATCH'}", *tail, sep="\n    ")


if __name__ == "__main__":
    main()
