# GF180MCU Low-Dropout Regulator (Capless, 5.0V → 3.3V)

## 1. Type of IP Block

Capless linear voltage regulator (LDO), 5.0V analog supply in, regulated 3.3V
analog supply out.


## 2. I/O List, Including Test Ports

| Pin | Direction | Type | Description |
|---|---|---|---|
| `VIN` | in | analog  | 5.0V analog supply input |
| `VOUT` | out | analog  | Regulated 3.3V analog output |
| `EN` | in | digital (3.3V logic) | Enables/disables regulator (high = on) |
| `FB_BUF` | out | analog | Buffered tap of the feedback node. |
| `EAOUT_BUF` | out | analog |Buffered error amplifier output (pass transistor gate). |
| `VREF` | in | external resource | Chipalooza's shared bandgap-reference bias voltage.|
| `VSS` | inout | ground | Ground |



## 3. Functional Description

Provides a locally-regulated, low-noise 3.3V rail, isolated from the noise on the shared 5.0V rail.


## 4. Target Specification

| Parameter | Min | Typ | Max |
|---|---|---|---|
| Input voltage (`VIN`) | 4.5V | 5.0V | 5.5V |
| Output voltage (`VOUT`) | 3.201V | 3.3V | 3.399V |
| Dropout voltage | — | — | 300 mV |
| Load current | 0 mA | — | 10 mA |
| Quiescent current | — | — | 100 µA |
| Line regulation (ΔVOUT) | — | — | 1% |
| Load regulation (ΔVOUT) | — | — | 1% |
| PSRR (low frequency) | 40 dB | — | — |

*Specifications are subject to change upon further circuit design :)*

## 5. Test Plan Outline

1. **Line regulation.**
   - Set `EN` high, load current fixed at 5 mA.
   - Step `VIN` from 4.5V to 5.5V.
   - Record `VOUT` at each step.
2. **Load regulation.**
   - Set `EN` high, `VIN` fixed at 5.0V.
   - Step load current from 0 mA to 10 mA.
   - Record `VOUT` at each step.
3. **Transient response.**
   - Set `EN` high, `VIN` fixed at 5.0V.
   - Apply a load step, 0 mA to 10 mA, with a 1 µs rise/fall time.
   - Separately, apply a `VIN` step, 5.0V to 4.5V, with a 1 µs rise/fall time, at fixed 5 mA load.
   - Capture `VOUT` in both cases; report overshoot/undershoot and settling time.
4. **PSRR.** Apply a ripple, a small AC signal added on top of the DC input, standing in for supply noise.
   - Set `EN` high, load current fixed at 5 mA.
   - Hold `VIN` at 5.0V DC, add a 50 mV AC ripple, swept 10 Hz to 1 MHz.
   - Measure ripple amplitude at `VOUT`; report attenuation (dB) vs. frequency.
5. **EN control.**
   - Set `VIN` at 5.0V, load current fixed at 5 mA.
   - Drive `EN` high; confirm `VOUT` rises cleanly to 3.3V with no glitches.
   - Drive `EN` low again; confirm `VOUT=0`. 
6. **Quiescent current.**
   - Set `EN` high, `VIN` at 5.0V, and load current at 0 mA (no load).
   - Measure current drawn from `VIN`


---

## 6. Harness Resources Required

| Resource | Use |
|---|---|
| 5.0V analog supply | `VIN` (supply and pass-device input) |
| Ground | `VSS` |
| Bandgap-referenced bias voltage | `VREF` (1.2V assumed in simulation) |
| 1 digital control (3.3V) | `EN` |
| Analog output pin | `VOUT` (for measuring regulation under external load) |
| 2 shared analog lines | `FB_BUF`, `EAOUT_BUF` test outputs |
| Bandgap-referenced current sources | none (biasing is internal) |

All devices are GF180MCU PDK devices rated for the 5.0V `VIN` domain:
transistors are `pfet_06v0`, `nfet_06v0` (long-channel) and `nfet_05v0` (L = 0.6 um),
resistors are high-resistance poly `ppolyf_u_1k_6p0`, and the compensation
capacitor is a MIM `cap_mim_2f0fF`. `EN` comes from the harness's 3.3V logic, so it passes through an
internal 3.3V-to-`VIN` level shifter (`xschem/ldo_levelshift.sch`).

When `EN` is low the whole block is shut down, not just the pass device: a PMOS
switch (`MBIASSW`) disconnects the bias resistors `Rref` and `RrefEA`
from `VIN`, NMOS pulldowns (`MPDREF`, `MPDEA`) clamp the bias nodes to
`VSS`, and `MENPASSOFF` holds the pass-transistor gate at `VIN`. `VOUT` is then
discharged to 0V by the feedback divider and the block draws only leakage from
`VIN` (sub-nA in simulation).

### Passive Devices

| Instance | Value | Device | W x L |
|---|---|---|---|
| `Rref` (error-amp tail bias) | 200 kOhm | `ppolyf_u_1k_6p0` | 1 x 194.27 um |
| `RrefEA` (bias for both test buffers, mirrored by `MBIASFB` / `MBIASEA`) | 2 MOhm | `ppolyf_u_1k_6p0` | 1 x 1944.26 um |
| `R1` / `R2` (feedback divider) | 175 / 100 kOhm | `ppolyf_u_1k_6p0` | 2 x 345.30 / 2 x 197.24 um |
| `Cc` (Miller compensation) | 3.0 pF | `cap_mim_2f0fF` | 27.35 x 54.5 um |

`R1` and `R2` use the same resistor type and width, so their ratio (which sets
`VOUT`) is independent of sheet-resistance and width variation and temperature.

## 7. Simulation Results (schematic and final layout)

Typical corner, 27 C, `VIN` = 5.0V, `VREF` = 1.2V, `EN` = 3.3V; the value in
brackets is the worst of 45 process/temperature corners. "Schematic" is the
pre-layout circuit; "Final layout" is the v2 layout's RC-extracted netlist (every
wire's resistance and capacitance included) run through the same testbenches.
Full results, plots and corner tables:
[`simulations/results/summary.md`](simulations/results/summary.md) (schematic) and
[`simulations/results_v2_pex_rc/summary.md`](simulations/results_v2_pex_rc/summary.md)
(final layout).

All testbenches drive the LDO with ideal sources: `VIN` and `VREF` are ideal
voltage sources, `EN` is an ideal 3.3V source, and `VOUT` is loaded by an ideal
DC current sink to ground (or a 660 Ohm resistor for the `EN` tests, so `VOUT`
can rest at 0V when off) in parallel with a 2 pF capacitor. Every plot in
`simulations/results/` carries a "Test conditions" panel with the exact load,
sweep and metric used.

| Parameter | Spec | How it is tested | Schematic | Final layout (v2, RC-extracted) |
|---|---|---|---|---|
| Output voltage | 3.201V - 3.399V | DC, 5 mA current-sink load | 3.309V (3.308 - 3.312V) | 3.309V (3.308 - 3.312V) |
| Dropout voltage | max 300 mV | DC sweep `VIN` 3.3 -> 5.5V, 10 mA current-sink load | 152 mV (262 mV) | 162 mV (273 mV) |
| Quiescent current | max 100 uA | DC operating point, no load (0 mA) | 60 uA (87 uA) | 60 uA (87 uA) |
| Line regulation | max 1% | DC sweep `VIN` 4.5 -> 5.5V, 5 mA current-sink load | 0.042% (0.085%) | 0.042% (0.084%) |
| Load regulation | max 1% | DC sweep of current-sink load 0 -> 10 mA, `VIN` = 5.0V | 0.269% (0.74%) | 0.271% (0.75%) |
| PSRR (low frequency) | min 40 dB | AC small-signal on `VIN`, 5 mA current-sink load | 59 dB at 100 Hz (53 dB) | 59 dB at 100 Hz (53 dB) |
| Shutdown current | - | DC operating point, `EN` = 0V, no load | 0.19 nA (3.3 nA) | 1.3 nA (4.5 nA) |
| Phase margin, 2 pF load | - | Loop gain, loads 0 - 10 mA, MOS corners, -40/27/110 C | 70.6 deg worst | 64.4 deg worst |

All specs pass in every corner, both before and after layout. Worst corners:
dropout at slow MOS / slow resistors / 110 C; quiescent current and load
regulation at fast MOS / fast resistors / 110 C; shutdown current at fast MOS /
110 C (leakage); phase margin at fs / 110 C / no load.

## 8. Repository Layout

| Path | Contents |
|---|---|
| `xschem/ldo.sch`, `ldo.sym` | LDO IP block schematic and symbol |
| `xschem/ldo_levelshift.sch`, `.sym` | 3.3V-to-`VIN` level shifter for `EN` |
| `simulations/tb_*.sch` | One xschem testbench per test in the test plan |
| `simulations/run_sims.py` | Runs all testbenches, plots results, checks against spec |
| `simulations/results/` | Result plots and summary table (schematic) |
| `simulations/stability.py` | Loop-gain / phase-margin sweep |
| `simulations/results_v2_pex_c/`, `results_v2_pex_rc/` | Post-layout results, final (v2) layout, extracted C / RC netlists |
| `simulations/results_pex_c/`, `results_pex_rc/` | Post-layout results, first (v1) layout, extracted C / RC netlists |
| `simulations/README.md` | Schematic simulation results |
| `netlist/schematic/ldo.spice` | Exported schematic netlist |
| `layout/` | **Final (v2) layout**: `ldo_v2.gds` (184.1 x 121.4 um) and the scripts that build it |
| `layout/build_layout.py`, `gl_devices.py`, `gl/`, `mag/` | Device generator (gLayout transistors + magic resistors / MIM cap) and the device cells |
| `layout/core_groups.py`, `place_v2.py`, `route_v2.py` | Transistor groups, placement, wiring (with DRC and LVS) |
| `layout/lvs/`, `layout/pex/` | LVS reports; parasitic extraction (C / RC) and EM/IR check |
| `layout/README.md` | Final layout: floorplan, screenshots, verification and post-layout results |
| `layout_v1/` | First (v1) layout, kept for reference: GDS (188.3 x 146.9 um), LVS, PEX, EM/IR and its own copy of the generator |
| `layout_v1/README.md` | First layout and its post-layout results |

## 9. Reproducing the Results

Requires [xschem](https://xschem.sourceforge.io/), [ngspice](https://ngspice.sourceforge.io/),
the gf180mcuD PDK with `PDK_ROOT` set, and Python 3 with numpy and matplotlib
(all included in [IIC-OSIC-TOOLS](https://github.com/iic-jku/IIC-OSIC-TOOLS)).

```sh
cd simulations
python3 run_sims.py --corners      # spec tests, typical + 45 corners
python3 stability.py               # loop gain / phase margin
```

Layout, DRC and LVS use magic, netgen and KLayout (also in IIC-OSIC-TOOLS). The
transistors are generated with [gLayout](https://github.com/ReaLLMASIC/gLayout),
which needs its own Python 3.10/3.11 environment; point `GLAYOUT_PYTHON` at it.
The final layout is built, verified and extracted with the scripts in `layout/`;
the steps are in [`layout/README.md`](layout/README.md#7-reproduce). In short:

```sh
cd layout
python3 route_v2.py                # wiring, DRC, LVS -> ldo_v2.gds
cd pex
magic -dnull -noconsole -rcfile $PDK_ROOT/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc pex.tcl
python3 emir_check.py              # EM / IR
cd ../../simulations
python3 run_sims.py --pex rc       # post-layout spec tests -> results_v2_pex_rc/
python3 stability.py --pex rc      # post-layout loop gain
```

The first layout is in `layout_v1/` (steps in [`layout_v1/README.md`](layout_v1/README.md);
add `--layout v1` to the simulation commands).

Testbenches can also be opened and simulated individually in xschem
(`cd simulations && xschem tb_line_reg.sch`). Schematics reference only files
in this repository or in the PDK via `$PDK_ROOT`.

## 10. Open Items

- **Harness integration.** The slot number is not assigned yet. The pin positions
  of all 18 slots are already extracted
  ([`layout/harness_slot_pins.json`](layout/harness_slot_pins.json)), and the
  v2 block's VIN / VSS rails run edge to edge so they can join the harness supply
  from either side. Once a slot is assigned, the block goes into the
  `slot<N>_wrapper` template (1274.3 x 412.7 um), is delivered as
  `gds/slot_<N>.gds` with top cell `slot_<N>`, and DRC/LVS are re-run on the
  wrapped cell.
- **Fill exclusion.** The harness adds dummy metal and poly fill over the whole
  chip. The input pair, `Cc` and `R1`/`R2` still need fill-exclusion marker
  layers so the fill does not disturb their matching or capacitance.
- **Quiescent-current margin.** 87 uA against the 100 uA limit at the fast-resistor /
  110 C corner (~13% margin, schematic and final layout alike); the bias currents
  are set by poly resistors from `VIN`.
- **Large output capacitance.** With 2 pF on `VOUT` the worst-case phase margin
  is 64 deg. With 50 pF it drops to 26 deg at no load (worst corner); at the
  typical corner it is above 45 deg only from about 0.1 mA of load. Loads with
  large decoupling capacitors need a minimum load current, or adaptive biasing
  of the error amplifier.
- **Fast load steps.** The 0 - 10 mA load step in 1 us gives -249 / +343 mV on
  the final layout. This is not specified; loads with fast (ns) current edges
  need their own decoupling.
