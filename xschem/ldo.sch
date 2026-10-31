v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
T {EN level shifter: 3.3V logic -> VIN domain} 1260 -1040 0 0 0.3 0.3 {}
T {Buffer to test EAOUT} 710 -730 0 0 0.4 0.4 {}
T {Buffer to test feedback potential} 710 -430 0 0 0.4 0.4 {}
T {-Uses pdk resistors and caps
-pdk transistors
} 190 -670 0 0 0.4 0.4 {}
N 750 -160 890 -160 {lab=IREF_EA}
N 1740 -530 1740 -460 {lab=CASCB2}
N 1390 -530 1390 -460 {lab=CASCB1}
N 1430 -560 1700 -560 {lab=CASCB1}
N 1390 -400 1390 -350 {lab=EAREF}
N 1740 -400 1740 -350 {lab=EAOUT}
N 1560 -290 1560 -140 {lab=TAIL}
N 2170 -290 2170 -230 {lab=FB}
N 1390 -290 1740 -290 {lab=TAIL}
N 1300 -140 1300 -110 {lab=IREF}
N 1260 -140 1300 -140 {lab=IREF}
N 1260 -260 1260 -250 {lab=VIN}
N 720 -340 930 -340 {lab=VIN}
N 940 -590 940 -520 {lab=EAOUT_BUF}
N 720 -590 720 -530 {lab=IREF_EA}
N 760 -530 760 -500 {lab=IREF_EA}
N 720 -530 760 -530 {lab=IREF_EA}
N 1430 -430 1700 -430 {lab=EAREF}
N 1390 -380 1460 -380 {lab=EAREF}
N 1460 -430 1460 -380 {lab=EAREF}
N 1780 -320 1820 -320 {lab=VREF}
N 1820 -320 1850 -320 {lab=VREF}
N 760 -500 900 -500 {lab=IREF_EA}
N 730 -650 940 -650 {lab=VIN}
N 930 -280 930 -190 {lab=FB_BUF}
N 1190 -320 1350 -320 {lab=FB}
N 1850 -320 1940 -320 {lab=VREF}
N 1390 -700 1390 -590 {lab=VIN}
N 1390 -700 1740 -700 {lab=VIN}
N 1740 -700 1740 -590 {lab=VIN}
N 1740 -380 1880 -380 {lab=EAOUT}
N 1880 -380 1940 -380 {lab=EAOUT}
N 2170 -570 2170 -530 {lab=VIN}
N 2010 -500 2130 -500 {lab=EAOUT}
N 2170 -400 2170 -350 {lab=VOUT}
N 1260 -170 1260 -140 {lab=IREF}
N 1300 -110 1520 -110 {lab=IREF}
N 2120 -380 2170 -380 {lab=VOUT}
N 2010 -380 2060 -380 {lab=EAOUT}
N 2170 -410 2170 -400 {lab=VOUT}
N 2170 -380 2380 -380 {lab=VOUT}
N 2010 -440 2010 -380 {lab=EAOUT}
N 1960 -840 2060 -840 {lab=EN_5V}
N 1920 -980 1920 -870 {lab=VIN}
N 1940 -380 2010 -380 {lab=EAOUT}
N 2010 -500 2010 -440 {lab=EAOUT}
N 2170 -470 2170 -410 {lab=VOUT}
N 1920 -810 1920 -380 {lab=EAOUT}
N 2380 -380 2550 -380 {lab=VOUT}
C {devices/title.sym} 160 90 0 0 {name=l1 author="Capless LDO, 5.0V to 3.3V (GF180MCU)"}
C {symbols/ppolyf_u_1k_6p0.sym} 1260 -200 0 0 {name=Rref
W=1e-6
L=194.27e-6
model=ppolyf_u_1k_6p0
spiceprefix=X
m=1}
C {devices/lab_pin.sym} 1240 -200 0 0 {name=lbRref sig_type=std_logic lab=VSS}
C {symbols/nfet_05v0.sym} 1280 -110 2 0 {name=MREF
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
C {symbols/nfet_05v0.sym} 1540 -110 0 0 {name=MTAIL
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
C {devices/lab_pin.sym} 2060 -840 2 0 {name=lenvng sig_type=std_logic lab=EN_5V}
C {symbols/pfet_06v0.sym} 1940 -840 2 0 {name=MENPASSOFF
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
C {devices/lab_pin.sym} 1920 -840 0 0 {name=lenpob sig_type=std_logic lab=VIN}
C {symbols/nfet_05v0.sym} 2530 -350 0 0 {name=MENDISCHARGE
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
C {devices/lab_pin.sym} 2550 -320 0 0 {name=lendcs sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 2550 -350 2 0 {name=lendcb sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 820 -340 1 0 {name=lrreffbp sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 820 -160 1 0 {name=lreffbg sig_type=std_logic lab=IREF_EA}
C {symbols/nfet_05v0.sym} 950 -310 2 0 {name=MFBBUF
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
C {devices/lab_pin.sym} 930 -310 0 0 {name=lfbbufb sig_type=std_logic lab=VSS}
C {symbols/nfet_05v0.sym} 910 -160 0 0 {name=MBIASFB
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
C {devices/lab_pin.sym} 930 -220 2 0 {name=lbiasfbd sig_type=std_logic lab=FB_BUF}
C {devices/lab_pin.sym} 930 -130 0 0 {name=lbiasfbs sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 930 -160 2 0 {name=lbiasfbb sig_type=std_logic lab=VSS}
C {symbols/ppolyf_u_1k_6p0.sym} 720 -620 0 0 {name=RrefEA
W=1e-6
L=1944.26e-6
model=ppolyf_u_1k_6p0
spiceprefix=X
m=1}
C {devices/lab_pin.sym} 700 -620 0 0 {name=lbRrefEA sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 830 -500 1 0 {name=lrrefeam sig_type=std_logic lab=IREF_EA}
C {symbols/nfet_05v0.sym} 740 -500 2 0 {name=MREFEA
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
C {devices/lab_pin.sym} 720 -470 2 0 {name=lrefeas sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 720 -500 2 0 {name=lrefeab sig_type=std_logic lab=VSS}
C {symbols/nfet_05v0.sym} 960 -620 2 0 {name=MEAOUTBUF
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
C {devices/lab_pin.sym} 830 -650 1 0 {name=leabufd sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 980 -620 2 0 {name=leabufg sig_type=std_logic lab=EAOUT}
C {devices/lab_pin.sym} 940 -620 0 0 {name=leabufb sig_type=std_logic lab=VSS}
C {symbols/nfet_05v0.sym} 920 -500 0 0 {name=MBIASEA
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
C {devices/lab_pin.sym} 940 -560 2 0 {name=lbiaseadaux sig_type=std_logic lab=EAOUT_BUF}
C {devices/lab_pin.sym} 940 -470 0 0 {name=lbiaseas sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 940 -500 2 0 {name=lbiaseab sig_type=std_logic lab=VSS}
C {symbols/nfet_06v0.sym} 1370 -320 0 0 {name=MIN1
L=3u
W=20u
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
C {symbols/nfet_06v0.sym} 1760 -320 2 0 {name=MIN2
L=3u
W=20u
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
C {symbols/pfet_06v0.sym} 1410 -560 2 0 {name=MLOAD1
L=3u
W=10u
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
C {symbols/pfet_06v0.sym} 1720 -560 0 0 {name=MLOAD2
L=3u
W=10u
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
C {symbols/pfet_06v0.sym} 2150 -500 0 0 {name=MPASS
L=0.55u
W=90u
nf=30
m=7
ad="'int((nf+1)/2) * W/nf * 0.18u'"
pd="'2*int((nf+1)/2) * (W/nf + 0.18u)'"
as="'int((nf+2)/2) * W/nf * 0.18u'"
ps="'2*int((nf+2)/2) * (W/nf + 0.18u)'"
nrd="'0.18u / W'" nrs="'0.18u / W'"
sa=0 sb=0 sd=0
model=pfet_06v0
spiceprefix=X
}
C {symbols/cap_mim_2f0fF.sym} 2090 -380 3 0 {name=Cc
W=38.6e-6
L=38.6e-6
model=cap_mim_2f0fF
spiceprefix=X
m=1}
C {symbols/ppolyf_u_1k_6p0.sym} 2170 -320 0 0 {name=R1
W=2e-6
L=345.30e-6
model=ppolyf_u_1k_6p0
spiceprefix=X
m=1}
C {devices/lab_pin.sym} 2150 -320 0 0 {name=lbR1 sig_type=std_logic lab=VSS}
C {symbols/ppolyf_u_1k_6p0.sym} 2170 -200 0 0 {name=R2
W=2e-6
L=197.24e-6
model=ppolyf_u_1k_6p0
spiceprefix=X
m=1}
C {devices/lab_pin.sym} 2150 -200 0 0 {name=lbR2 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 970 -310 2 0 {name=lfb sig_type=std_logic lab=FB}
C {symbols/pfet_06v0.sym} 1410 -430 2 0 {name=MCASC1
L=0.55u
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
C {devices/lab_pin.sym} 1570 -430 1 0 {name=lcasc1g sig_type=std_logic lab=EAREF}
C {devices/lab_pin.sym} 1390 -490 2 0 {name=lcasc1s sig_type=std_logic lab=CASCB1}
C {devices/lab_pin.sym} 1390 -430 0 0 {name=lcasc1b sig_type=std_logic lab=VIN}
C {symbols/pfet_06v0.sym} 1720 -430 0 0 {name=MCASC2
L=0.55u
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
C {devices/lab_pin.sym} 1740 -490 0 0 {name=lcasc2s sig_type=std_logic lab=CASCB2}
C {devices/lab_pin.sym} 1740 -430 2 0 {name=lcasc2b sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1260 -260 0 0 {name=lvisual2 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1260 -80 2 0 {name=lvisual3 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 1260 -110 0 0 {name=lvisual4 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 1560 -80 0 0 {name=lvisual5 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 1560 -110 0 0 {name=lvisual6 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 1390 -320 2 0 {name=lvisual7 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 1740 -320 0 0 {name=lvisual8 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 1390 -590 2 0 {name=lvisual9 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1390 -560 0 0 {name=lvisual10 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1740 -590 0 0 {name=lvisual11 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1740 -560 2 0 {name=lvisual12 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 2170 -500 2 0 {name=lvisual15 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 2170 -170 0 0 {name=lvisual18 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 1560 -220 0 0 {name=lvisual26 sig_type=std_logic lab=TAIL}
C {devices/lab_pin.sym} 1190 -320 0 0 {name=lvisual29 sig_type=std_logic lab=FB}
C {devices/lab_pin.sym} 1570 -560 1 0 {name=lvisual34 sig_type=std_logic lab=CASCB1}
C {devices/lab_pin.sym} 2170 -260 0 0 {name=lvisual28 sig_type=std_logic lab=FB}
C {devices/lab_pin.sym} 1940 -320 2 0 {name=lvrefp1 sig_type=std_logic lab=VREF}
C {devices/lab_pin.sym} 1570 -700 1 0 {name=lvisual30 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1920 -790 0 0 {name=lcasc1 sig_type=std_logic lab=EAOUT}
C {devices/lab_pin.sym} 2170 -570 1 0 {name=lvisual14 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1860 -380 1 0 {name=lcasc2d sig_type=std_logic lab=EAOUT}
C {devices/lab_pin.sym} 1440 -110 1 0 {name=lvisual23 sig_type=std_logic lab=IREF}
C {devices/lab_pin.sym} 2510 -350 0 0 {name=lenvnd1 sig_type=std_logic lab=ENB_5V}
C {devices/lab_pin.sym} 2550 -380 1 0 {name=lvisual13 sig_type=std_logic lab=VOUT}
C {devices/ipin.sym} 260 -1060 0 0 {name=p1 lab=VIN}
C {devices/ipin.sym} 260 -1020 0 0 {name=p2 lab=VREF}
C {devices/ipin.sym} 260 -980 0 0 {name=p3 lab=EN}
C {devices/opin.sym} 260 -940 0 0 {name=p4 lab=VOUT}
C {devices/opin.sym} 260 -900 0 0 {name=p5 lab=FB_BUF}
C {devices/opin.sym} 260 -860 0 0 {name=p6 lab=EAOUT_BUF}
C {devices/iopin.sym} 260 -820 0 0 {name=p7 lab=VSS}
C {ldo_levelshift.sym} 1410 -960 0 0 {name=xls}
C {devices/lab_pin.sym} 1260 -980 0 0 {name=lls0 sig_type=std_logic lab=EN}
C {devices/lab_pin.sym} 1260 -960 0 0 {name=lls1 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1560 -980 2 0 {name=lls2 sig_type=std_logic lab=EN_5V}
C {devices/lab_pin.sym} 1560 -960 2 0 {name=lls3 sig_type=std_logic lab=ENB_5V}
C {devices/lab_pin.sym} 1560 -940 2 0 {name=lls4 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 1920 -980 0 0 {name=lenpassvin sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 1260 -230 0 0 {name=lbo1 sig_type=std_logic lab=VIN_BIAS}
C {devices/lab_pin.sym} 720 -650 0 0 {name=lbo3 sig_type=std_logic lab=VIN_BIAS}
C {symbols/pfet_06v0.sym} 300 -1000 0 0 {name=MBIASSW
L=0.6u
W=10u
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
C {devices/lab_pin.sym} 320 -970 2 0 {name=lbo4 sig_type=std_logic lab=VIN_BIAS}
C {devices/lab_pin.sym} 320 -1030 2 0 {name=lbo5 sig_type=std_logic lab=VIN}
C {devices/lab_pin.sym} 280 -1000 0 0 {name=lbo6 sig_type=std_logic lab=ENB_5V}
C {devices/lab_pin.sym} 320 -1000 2 0 {name=lbo7 sig_type=std_logic lab=VIN}
C {symbols/nfet_05v0.sym} 300 -860 0 0 {name=MPDREF
L=0.6u
W=1u
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
C {devices/lab_pin.sym} 320 -890 2 0 {name=lbo8 sig_type=std_logic lab=IREF}
C {devices/lab_pin.sym} 320 -830 2 0 {name=lbo9 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 280 -860 0 0 {name=lbo10 sig_type=std_logic lab=ENB_5V}
C {devices/lab_pin.sym} 320 -860 2 0 {name=lbo11 sig_type=std_logic lab=VSS}
C {symbols/nfet_05v0.sym} 540 -860 0 0 {name=MPDEA
L=0.6u
W=1u
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
C {devices/lab_pin.sym} 560 -890 2 0 {name=lbo16 sig_type=std_logic lab=IREF_EA}
C {devices/lab_pin.sym} 560 -830 2 0 {name=lbo17 sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 520 -860 0 0 {name=lbo18 sig_type=std_logic lab=ENB_5V}
C {devices/lab_pin.sym} 560 -860 2 0 {name=lbo19 sig_type=std_logic lab=VSS}
T {Bias shutdown: EN low opens MBIASSW and grounds the mirror gates} 240 -1090 0 0 0.3 0.3 {}
