v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
T {3.3V -> VIN (5V) level shifter for EN} -60 -420 0 0 0.5 0.5 {}
T {EN = 3.3V: MN1 on, overpowers weak MP1 -> OUTB = 0V, OUT = VIN
EN = 0V:   MN1 off, MP1 pulls OUTB to VIN -> OUT = 0V
MN1 is long so EN switches near mid-rail (~1.4V); MP1 is a long-channel weak pull-up (~3uA static current only while enabled).
MP2/MN2 restore a full-swing VIN-domain OUT.} -60 -370 0 0 0.25 0.25 {}
C {symbols/pfet_06v0.sym} 100 -180 0 0 {name=MP1
L=40u
W=1u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=pfet_06v0
spiceprefix=X
}
C {devices/lab_pin.sym} 120 -150 2 0 {name=l1 sig_type=std_logic lab=OUTB}
C {devices/lab_pin.sym} 120 -210 2 0 {name=l2 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 80 -180 0 0 {name=l3 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 120 -180 2 0 {name=l4 sig_type=std_logic lab=VIN}
C {symbols/nfet_06v0.sym} 100 -60 0 0 {name=MN1
L=5u
W=0.5u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=nfet_06v0
spiceprefix=X
}
C {devices/lab_pin.sym} 120 -90 2 0 {name=l5 sig_type=std_logic lab=OUTB}
C {devices/lab_pin.sym} 120 -30 2 0 {name=l6 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 80 -60 0 0 {name=l7 sig_type=std_logic lab=EN}
C {devices/lab_pin.sym} 120 -60 2 0 {name=l8 sig_type=std_logic lab=VSS}
C {symbols/pfet_06v0.sym} 400 -180 0 0 {name=MP2
L=0.6u
W=5u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=pfet_06v0
spiceprefix=X
}
C {devices/lab_pin.sym} 420 -150 2 0 {name=l9 sig_type=std_logic lab=OUT}
C {devices/lab_pin.sym} 420 -210 2 0 {name=l10 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 380 -180 0 0 {name=l11 sig_type=std_logic lab=OUTB}
C {devices/lab_pin.sym} 420 -180 2 0 {name=l12 sig_type=std_logic lab=VIN}
C {symbols/nfet_05v0.sym} 400 -60 0 0 {name=MN2
L=0.6u
W=5u
nf=1
m=1
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=nfet_05v0
spiceprefix=X
}
C {devices/lab_pin.sym} 420 -90 2 0 {name=l13 sig_type=std_logic lab=OUT}
C {devices/lab_pin.sym} 420 -30 2 0 {name=l14 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 380 -60 0 0 {name=l15 sig_type=std_logic lab=OUTB}
C {devices/lab_pin.sym} 420 -60 2 0 {name=l16 sig_type=std_logic lab=VSS}
C {devices/ipin.sym} -40 40 0 0 {name=p1 lab=EN}
C {devices/ipin.sym} -40 70 0 0 {name=p2 lab=VIN}
C {devices/opin.sym} -40 100 0 0 {name=p3 lab=OUT}
C {devices/opin.sym} -40 130 0 0 {name=p4 lab=OUTB}
C {devices/iopin.sym} -40 160 0 0 {name=p5 lab=VSS}
