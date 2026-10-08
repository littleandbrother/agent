"""Attributed local reference atlas. Publisher panels never become case evidence.

Crop rectangles are normalized to each full primary figure, not to a page.
Extraction is deterministic and supports recorded manual bounding-box review.
"""
import argparse, hashlib, html, json, re, shutil, subprocess
from pathlib import Path

PAPERS = {
 'mo': {'doi':'10.1038/s41467-024-51245-5','pages':[3,4,5,6,8],'counts':[8,13,7,10,17], 'title':'A rolling-mode triboelectric nanogenerator with multi-tunnel grating electrodes and opposite-charge-enhancement for wave energy harvesting'},
 'abyss': {'doi':'10.1038/s41467-024-50581-w','pages':[3,4,5,6,8],'counts':[6,7,9,7,11], 'title':'Self-powered and speed-adjustable sensor for abyssal ocean current measurements based on triboelectric nanogenerators'},
 'pump': {'doi':'10.1038/s41467-025-56679-z','pages':[2,4,6,7,8],'counts':[4,9,8,9,7], 'title':'A self-powered soft triboelectric-electrohydrodynamic pump'},
 'ids': {'doi':'10.1038/s41467-025-61166-6','pages':[2,4,5,6,7],'counts':[3,8,6,8,5], 'title':'Impedance decoupling strategy to enhance the real-time powering performance of TENG for multi-mode sensing'},
 'rattle': {'doi':'10.1038/s41467-025-64575-9','pages':[3,6,7,9,11],'counts':[10,5,9,7,7], 'title':'Rattle drum-inspired triboelectric nanogenerator with enhanced output using charge dispatch and magnetic repulsion pendulum'},
 'road': {'doi':'10.1126/sciadv.adv9379','counts':[11,12,7,12,8], 'title':'Self-powered smart transportation using triboelectric nanogenerators', 'url':'https://pmc.ncbi.nlm.nih.gov/articles/PMC13112539/'}}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def build(source,out,layouts=None):
 import pdfplumber
 from PIL import Image,ImageOps,ImageDraw
 source,out=Path(source),Path(out);out.mkdir(parents=True,exist_ok=True)
 layouts=json.loads(Path(layouts).read_text()) if layouts else {}
 figures=[];panels=[];sources=[]
 for key,meta in PAPERS.items():
  folder=out/key;folder.mkdir(exist_ok=True)
  captions=[]
  if key!='road':
   p=source/(key+'.pdf');target=folder/'paper.pdf'
   if not target.exists():shutil.copyfile(p,target)
   sources.append({'id':key,'path':str(target.relative_to(out)),'sha256':sha(target),**meta,'scope':'Reference display, not our engineering result.'})
   with pdfplumber.open(p) as pdf:
    for i,n in enumerate(meta['pages'],1):
     page=pdf.pages[n-1];words=page.extract_words()
     cap=next(w for w in words if re.match(r'Fig\.'+str(i)+r'\|',w['text']))
     top=312 if key=='pump' and i==1 else 46
     png=folder/('page-'+str(n)+'.png')
     if not png.exists():subprocess.run(['pdftoppm','-f',str(n),'-l',str(n),'-r','200','-singlefile','-png',str(p),str(png.with_suffix(''))],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
     image=Image.open(png);sx=image.width/page.width;sy=image.height/page.height
     image=image.crop((54*sx,top*sy,548*sx,(cap['top']-4)*sy))
     name=f'figure-{i}.png';image.save(folder/name)
     captions.append(' '.join(w['text'] for w in words if cap['top']-1<=w['top']<cap['top']+95))
  else:
   shutil.copyfile(source/'road.html',folder/'paper.html')
   text=(source/'road.html').read_text()
   clean=lambda s:html.unescape(re.sub('<[^>]+>',' ',s)).strip()
   actual_title=re.search(r'<h1[^>]*>(.*?)</h1>',text,re.S)
   if actual_title:meta['title']=clean(actual_title[1])
   for i in range(1,6):
    Image.open(source/f'road-f{i}.jpg').convert('RGB').save(folder/f'figure-{i}.png')
    element=re.search(r'<(?:figure|section)[^>]*id="F'+str(i)+'".*?</(?:figure|section)>',text,re.S)
    captions.append(clean(element[0]) if element else 'See primary source caption at '+meta['url'])
   sources.append({'id':key,'path':'road/paper.html','sha256':sha(folder/'paper.html'),**meta,'scope':'Reference display only; verify CC BY-NC license before redistribution.'})
  thumbs=[]
  for i,count in enumerate(meta['counts'],1):
   file=folder/f'figure-{i}.png';image=Image.open(file)
   fid=key+'-'+str(i);layout=layouts.get(fid,{})
   figures.append({'id':fid,'paper':key,'number':i,'path':str(file.relative_to(out)),'sha256':sha(file),'panels':count,'caption':captions[i-1], 'crop_review':layout.get('review','pending')})
   rects=layout.get('rects',{})
   for j in range(count):
    label=chr(97+j);pid=fid+label;rect=rects.get(label)
    record={'id':pid,'paper':key,'figure':i,'label':label,'reference_only':True,'primary_figure':str(file.relative_to(out)),
       'caption':captions[i-1],'source_sha256':sha(file),'crop_status':'pending' if rect is None else 'manual-bounds',
       'expression':layout.get('expressions',{}).get(label,'Read labelled primary panel and caption; never infer absent data.'),
       'scope':'First-level labelled panel; internal i/ii, insets, supplementary figures not included.'}
    if rect is not None:
     if len(rect)!=4 or not (0<=rect[0]<rect[2]<=1 and 0<=rect[1]<rect[3]<=1):raise ValueError('INVALID_REFERENCE_RECT:'+pid)
     crop=image.crop(tuple(int(v*(image.width if k%2==0 else image.height)) for k,v in enumerate(rect)))
     dest=folder/(pid+'.png');crop.save(dest);record.update(path=str(dest.relative_to(out)),bbox=rect,sha256=sha(dest))
    panels.append(record)
   thumb=ImageOps.contain(image,(640,760));tile=Image.new('RGB',(660,800),'white');tile.paste(thumb,(10,25));ImageDraw.Draw(tile).text((10,5),fid+' / '+str(count)+' labelled panels',fill='black');thumbs.append(tile)
  contact=Image.new('RGB',(660*3,800*2),'white')
  for j,tile in enumerate(thumbs):contact.paste(tile,((j%3)*660,(j//3)*800))
  contact.save(folder/'contact.png')
 result={'schema_version':'bf-literature-panel-atlas-v1','papers':sources,'figures':figures,'panels':panels,
  'counts':{'papers':len(sources),'primary_figures':len(figures),'labelled_panels':len(panels),'extracted':sum('path' in p for p in panels)},
  'claim_boundary':'Local attributed reference for scientific expression. Not device replication; no supplementary completeness claim.'}
 save(out/'atlas-index.json',result)
 esc=html.escape
 sections=[]
 for f in figures:
  children=[p for p in panels if p['paper']==f['paper'] and p['figure']==f['number']]
  sub=''.join(f'<details><summary>{esc(p["id"])} · {esc(p["expression"])}</summary><img src="{p.get("path",p["primary_figure"])}"><p>{esc(p["crop_status"])}</p></details>' for p in children)
  sections.append(f'<section><h2>{esc(f["id"])} — {f["panels"]} panels</h2><img src="{f["path"]}"><p>{esc(f["caption"])}</p>{sub}</section>')
 (out/'index.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><style>body{font:16px/1.6 system-ui;margin:32px auto;max-width:1200px}img{display:block;max-width:100%;max-height:950px;margin:auto}section{border-top:1px solid #ccc;padding:24px}summary{cursor:pointer}details{padding:12px}</style><h1>Scientific expression reference atlas</h1><p>250 primary labelled panels. Reference-only, with original captions and crop review status.</p>'+''.join(sections)+'</html>')
 return result

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--out',required=True);a.add_argument('--layouts');v=a.parse_args();print(json.dumps(build(v.source,v.out,v.layouts)['counts']))
