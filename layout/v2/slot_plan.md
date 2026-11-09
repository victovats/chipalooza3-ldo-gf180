Slot 1 wiring plan

| LDO net | harness pin | wire | length (µm) | resistance / IR drop | current density |
|---|---|---|---:|---|---|
| VIN | vdd_5v0 | metal5 30 µm | 1254 | 2.05 Ω -> 20 mV at 10 mA | 0.33 of 2.2 mA/µm |
| VSS | vss_5v0 | metal5 10 µm | 1254 | 6.1 Ω, ~0.1 mA -> <1 mV | - |
| VOUT | s1_an[1] | metal5 12 µm + metal3 pad landing | 131 | 0.53 Ω -> 5.3 mV (worst end) | 0.83 of 2.2 mA/µm; >= 36 cuts per via level |
| VREF | s1_an[0] | metal3 1.0 µm | 371 | signal (µA or none) | - |
| EN | enable | metal3 0.5 µm | 1418 | signal (µA or none) | - |
| FB_BUF | analog_bus0 | metal3 1.0 µm | 1286 | signal (µA or none) | - |
| EAOUT_BUF | analog_bus1 | metal3 1.0 µm | 1293 | signal (µA or none) | - |
