// Actual BF candidate; uncalibrated packaging hypothesis. Units mm.
// XY is bounded by the original source-module footprint. Default Z is assumed.
length=71.5; width=40.0; wall=1; pcb=1; cavity=4.5;
window=[50,30]; mount_d=2; cap=[20,18,2.1];
cap_centres=[[15, 12]];
mounts=[[4, 4], [67.5, 4], [4, 36.0], [67.5, 36.0]];
module lower_tray() {
 difference() {
  cube([length,width,cavity+wall]);
  translate([wall,wall,wall]) cube([length-2*wall,width-2*wall,cavity+1]);
  for(p=mounts) translate([p[0],p[1],-1]) cylinder(h=wall+2,d=mount_d,$fn=24);
 }
}
module body(x,y,dx,dy,dz) {translate([x-dx/2,y-dy/2,wall+pcb]) cube([dx,dy,dz]);}
lower_tray();
color("darkgreen") translate([wall,wall,wall]) cube([length-2*wall,width-2*wall,pcb]);
for(p=cap_centres) color("silver") body(p[0],p[1],cap[0],cap[1],cap[2]);
color("black") body(52,12,4,4,1); // MSP430 VQFN nominal XY; Z assumed
color("black") body(60,12,3.5,3.5,1); // BQ25570 nominal XY; Z assumed
color("red") body(63,31,2,2,1); // TMP117 WSON nominal XY; Z assumed
// The window is an alignment plane, not an asserted installed irradiance gain.
%translate([(length-window[0])/2,(width-window[1])/2,cavity+wall]) cube([window[0],window[1],0.2]);
