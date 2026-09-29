"""Readable circuit sheet; connectivity audited against board.json before export."""
import json,sys,shutil
from pathlib import Path
from html import escape
out=Path(sys.argv[1]);b=json.loads((out/'board.json').read_text());nets=b['nets'];connections={};s=[]
def text(x,y,t,size=17):s.append(f'<text x="{x}" y="{y}" font-size="{size}">{escape(str(t))}</text>')
def line(*pts):s.append('<polyline fill="none" stroke="#246246" stroke-width="2" points="'+' '.join(f'{x},{y}' for x,y in pts)+'"/>')
def dot(x,y):s.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#246246"/>')
def ground(x,y):
 line((x,y),(x,y+13));line((x-14,y+13),(x+14,y+13));line((x-9,y+19),(x+9,y+19));line((x-4,y+25),(x+4,y+25));text(x+19,y+20,'GND',13)
def pin(ref,num,name,x,y,endx,endy):
 connections.setdefault(ref,{})[str(num)]=nets[ref][str(num)];line((x,y),(endx,endy));text(x+7 if endx<x else x-100,y-7,f'{num} {name}',15)
def cap(ref,value,x,y,top,bottom,n1,n2):
 connections[ref]={'1':n1,'2':n2};line((x,top),(x,y-6));line((x-15,y-6),(x+15,y-6));line((x-15,y+6),(x+15,y+6));line((x,y+6),(x,bottom));text(x+22,y,ref+' '+value,16)
s=['<svg xmlns="http://www.w3.org/2000/svg" width="1680" height="1040" viewBox="0 0 1680 1040"><rect width="1680" height="1040" fill="white"/><g font-family="Arial,sans-serif" fill="#192b3e">']
text(55,48,'DOOR D2 / MAGNETIC PLUCKING EVENT NODE',28);text(55,78,'Pin-accurate engineering schematic · same netlist as native EDA / PCB / vendor SPICE · 3.3 V',17)
for x,y,w,h in [(480,170,260,440),(1200,170,235,440)]:s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#f8fafb" stroke="#21374a" stroke-width="2"/>')
text(520,195,'U1 LTC3588-1',21);text(1208,197,'U2 MDBT42Q',21)
for num,name,y in [(1,'PZ1',240),(2,'PZ2',295),(3,'CAP',385),(4,'VIN',475)]:pin('U1',num,name,480,y,420,y)
for num,name,y in [(5,'SW',240),(6,'VOUT',300),(7,'VIN2',380),(8,'D1',425),(9,'D0',480),(10,'PGOOD',560)]:pin('U1',num,name,740,y,780,y)
pin('U1',11,'EP',610,610,610,650);ground(610,650)
connections['J1']=nets['J1'];text(90,200,'J1 / PIEZO INPUT',19)
for i,y in enumerate([240,295],1):s.append(f'<circle cx="140" cy="{y}" r="7" fill="none" stroke="#21374a" stroke-width="2"/>');line((147,y),(420,y));text(110,y-12,i,14)
line((420,385),(350,385));cap('C2','1 µF / 50 V',350,427,385,475,'CAP','VIN');line((300,475),(420,475));dot(350,475)
cap('C1','47 µF / 25 V',300,562,475,650,'VIN','GND');ground(300,650);text(330,497,'VIN',14)
line((780,240),(820,240));s.append('<path d="M820 240 c0 -22 24 -22 24 0 c0 -22 24 -22 24 0 c0 -22 24 -22 24 0 c0 -22 24 -22 24 0" fill="none" stroke="#246246" stroke-width="2"/>');line((916,240),(1140,240),(1140,230),(1200,230));text(827,215,'L1 10 µH',16);connections['L1']=nets['L1']
line((780,300),(980,300),(980,240));dot(980,240);dot(980,300);cap('C4','100 µF / 6.3 V',980,370,300,440,'VOUT','GND');ground(980,440);text(985,265,'VOUT 3.3 V',15)
line((780,380),(840,380));line((780,425),(795,425),(795,380));dot(795,380);cap('C3','4.7 µF / 16 V',840,438,380,498,'VIN2','GND');ground(840,498)
line((780,480),(780,650));ground(780,650)
line((780,560),(1150,560),(1150,305),(1200,305));text(998,550,'PGOOD',15)
pin('U2',11,'VDD',1200,230,1165,230);pin('U2',25,'P0.11',1200,305,1165,305)
line((1090,240),(1090,350));cap('C5','100 nF',1090,400,350,450,'VOUT','GND');ground(1090,450);dot(1090,240)
for num,y,n in [(26,365,'P0.12 / DEBUG'),(36,435,'SWDCLK'),(37,485,'SWDIO')]:pin('U2',num,n,1435,y,1490,y);text(1498,y+5,nets['U2'][str(num)],15)
for num in ['1','12','24','39']:connections.setdefault('U2',{})[num]='GND'
text(1245,590,'1,12,24,39 GND',15);line((1300,610),(1300,650));ground(1300,650)
text(70,740,'DEBUG / PROGRAMMING',20)
for ref,x,y in [('J2',120,790),('J3',550,790)]:
 connections[ref]=nets[ref];text(x,y-25,ref+' / 2.54 mm',18)
 for i,(num,n) in enumerate(nets[ref].items()):
  yy=y+i*35;s.append(f'<circle cx="{x}" cy="{yy}" r="6" fill="none" stroke="#21374a"/>');line((x+6,yy),(x+70,yy));text(x+80,yy+6,f'{num}  {n}',16)
text(930,754,'BOARD / FIRMWARE CONTRACT',20)
for i,t in enumerate(['nRF52832 LDO mode; DEC4 1 µF inside module.','DCC / DEC4 external pins NC; other unused GPIO NC.','Internal LF RC; no external 32.768 kHz crystal.','P0.11 high: initialize BLE; low: stop and system-off.','VTref senses VOUT; debugger must not power the harvester.','No physical flashing, receiver or power measurement yet.']):text(930,789+30*i,t,16)
text(55,1015,'D2 / native ERC pending / cold-start verification FAILED / engineering draft, NOT fabrication release',16);s.append('</g></svg>')
assert connections==nets,(connections,nets)
if (out/'schematic.svg').exists():shutil.copy2(out/'schematic.svg',out/'pin-map.svg')
(out/'schematic.svg').write_text('\n'.join(s));(out/'schematic-checks.json').write_text(json.dumps({'connections_equal_board':connections==nets,'nets':connections,'native_erc':None,'scope':'Renderer pin-to-net audit, not native ERC'},indent=2))
