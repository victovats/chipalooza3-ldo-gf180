# Parasitic extraction of the v2 LDO layout (run from layout/v2/pex; see ../route_v2.py).
# The layout is flattened first so wire coupling across cell boundaries extracts cleanly.
addpath ..
addpath ../mag
addpath ../../mag
load ldo_v2
flatten ldo_flat
load ldo_flat
select top cell
# 1) C-only: devices + wire capacitance to substrate + wire-to-wire coupling
extract do capacitance
extract do coupling
extract no resistance
extract all
ext2spice format ngspice
ext2spice scale off
ext2spice cthresh 0
ext2spice subcircuit top on
ext2spice -o ldo_pex_c.spice
# 2) RC: also split every wire with significant resistance into resistor segments
extract do resistance
extract all
ext2sim labels on
ext2sim
extresist tolerance 0.01
extresist simplify off
extresist all
ext2spice extresist on
ext2spice -o ldo_pex_rc.spice
quit -noprompt
