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
| `Cc` (Miller compensation) | 3.0 pF | `cap_mim_2f0fF` | 38.6 x 38.6 um |

`R1` and `R2` use the same resistor type and width, so their ratio (which sets
`VOUT`) is independent of sheet-resistance and width variation and temperature.

## 7. Simulation Results (schematic, pre-layout)

Typical corner, 27 C, `VIN` = 5.0V, `VREF` = 1.2V, `EN` = 3.3V. Full results,
plots and the process/temperature corner table are in
[`simulations/results/summary.md`](simulations/results/summary.md).

All testbenches drive the LDO with ideal sources: `VIN` and `VREF` are ideal
voltage sources, `EN` is an ideal 3.3V source, and `VOUT` is loaded by an ideal
DC current sink to ground (or a 660 Ohm resistor for the `EN` tests, so `VOUT`
can rest at 0V when off) in parallel with a 2 pF capacitor. Every plot in
`simulations/results/` carries a "Test conditions" panel with the exact load,
sweep and metric used.

| Parameter | Spec | How it is tested | Simulated |
|---|---|---|---|
| Output voltage | 3.201V - 3.399V | DC, 5 mA current-sink load | 3.309V |
| Dropout voltage | max 300 mV | DC sweep `VIN` 3.3 -> 5.5V, 10 mA current-sink load | 152 mV (262 mV worst corner) |
| Quiescent current | max 100 uA | DC operating point, no load (0 mA) | 60 uA (87 uA worst corner) |
| Line regulation | max 1% | DC sweep `VIN` 4.5 -> 5.5V, 5 mA current-sink load | 0.042% (0.085% worst corner) |
| Load regulation | max 1% | DC sweep of current-sink load 0 -> 10 mA, `VIN` = 5.0V | 0.269% (0.73% worst corner) |
| PSRR (low frequency) | min 40 dB | AC small-signal on `VIN`, 5 mA current-sink load | 59 dB at 100 Hz (53 dB worst corner) |
| Shutdown current | - | DC operating point, `EN` = 0V, no load | 0.19 nA (3.3 nA worst corner) |

Worst corners: dropout at slow MOS / slow resistors / 110 C; quiescent current
and load regulation at fast MOS / fast resistors / 110 C; shutdown
current at fast MOS / 110 C (leakage).

## 8. Repository Layout

| Path | Contents |
|---|---|
| `xschem/ldo.sch`, `ldo.sym` | LDO IP block schematic and symbol |
| `xschem/ldo_levelshift.sch`, `.sym` | 3.3V-to-`VIN` level shifter for `EN` |
| `simulations/tb_*.sch` | One xschem testbench per test in the test plan |
| `simulations/run_sims.py` | Runs all testbenches, plots results, checks against spec |
| `simulations/results/` | Result plots and summary table (schematic) |
| `simulations/stability.py` | Loop-gain / phase-margin sweep |
| `simulations/results_pex_c/`, `results_pex_rc/` | Post-layout results on the extracted C / RC netlists |
| `simulations/README.md` | Schematic simulation results |
| `netlist/schematic/ldo.spice` | Exported schematic netlist |
| `layout/build_layout.py`, `gl_devices.py` | Generates the layout (gLayout transistors + magic), runs DRC, extraction and LVS |
| `layout/mag/`, `layout/gds/ldo.gds` | Layout (magic cells) and GDS, 188.3 x 146.9 um |
| `layout/lvs/` | Extracted netlist and netgen LVS report (`comp.out`) |
| `layout/pex/` | Parasitic extraction (C / RC) and EM/IR check |
| `layout/README.md` | Layout and post-layout results |

## 9. Reproducing the Results

Requires [xschem](https://xschem.sourceforge.io/), [ngspice](https://ngspice.sourceforge.io/),
the gf180mcuD PDK with `PDK_ROOT` set, and Python 3 with numpy and matplotlib
(all included in [IIC-OSIC-TOOLS](https://github.com/iic-jku/IIC-OSIC-TOOLS)).

```sh
cd simulations
python3 run_sims.py --corners      # spec tests, typical + 45 corners
python3 stability.py               # loop gain / phase margin
```

Layout, DRC and LVS (magic and netgen, also in IIC-OSIC-TOOLS). The transistors
are generated with [gLayout](https://github.com/ReaLLMASIC/gLayout), which needs
its own Python 3.10/3.11 environment; point `GLAYOUT_PYTHON` at it.

```sh
cd layout
python3 build_layout.py
```

Post-layout (parasitic extraction, simulation of the extracted netlist, EM/IR):

```sh
cd layout/pex
magic -dnull -noconsole -rcfile $PDK_ROOT/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc pex.tcl
python3 emir_check.py
cd ../../simulations
python3 run_sims.py --pex rc
python3 stability.py --pex rc
```

Testbenches can also be opened and simulated individually in xschem
(`cd simulations && xschem tb_line_reg.sch`). Schematics reference only files
in this repository or in the PDK via `$PDK_ROOT`.

## 10. Open Items

- Quiescent current has ~13% margin at the fast-resistor / 110 C corner
  (87 uA vs 100 uA); bias currents are set by poly resistors from `VIN`.
- Output capacitance on `VOUT` is limited for 45 deg phase margin
  (post-layout, worst corner): ~12 pF at no load, ~28 pF above 10 uA,
  ~100 pF above 100 uA. Adaptive biasing of the error amplifier would relax this.
- Load-step response (-244 / +340 mV post-layout for a 0-10 mA step in 1 us)
  is not specified; loads with fast (ns) current edges need their own decoupling.
- Harness integration: slot number not yet assigned. The block must be placed
  in the `slot<N>_wrapper` template (1274.3 x 412.7 um) and delivered as
  `gds/slot_<N>.gds` with top cell `slot_<N>`, then DRC/LVS re-run on the
  wrapped cell.
