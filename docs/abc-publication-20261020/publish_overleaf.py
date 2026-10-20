"""Sync accepted ABC compile dependencies to the two explicitly authorized projects.
Reuse existing credential helpers and checkouts. Never print/store credentials.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,subprocess,tempfile,xml.etree.ElementTree as ET,shutil
ROOT=Path(__file__).resolve().parents[2]
APP=ROOT/'workbench/bf-campaign-s0-20261019/battery-world'
HERE=Path(__file__).resolve().parent
SPECS={'rsi':('method-reexecution-20261019','main.pdf','6ad5fb6e87c3ac6782d05b2c',16),'interface':('interface-sufficiency-20261019','interface-sufficiency-abc.pdf','6ad5fbda856b284d5d917ffd',23)}
def run(args,cwd=None,timeout=60):
 p=subprocess.run(args,cwd=cwd,env={**os.environ,'GIT_TERMINAL_PROMPT':'0','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError(f'{args[0]} {args[1]} exited {p.returncode}; stdout/stderr suppressed to protect credentials')
 return p.stdout

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n')
def words(p):
 t=run(['/opt/homebrew/bin/pdftotext','-bbox-layout',str(p),'-']).decode()
 t=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',lambda m:f'__PDF_U{ord(m[0]):04X}__',t)
 doc=ET.fromstring(t)
 return [{'dimensions':dict(page.attrib),'words':[[dict(w.attrib),w.text] for w in page.iter() if w.tag.rsplit('}',1)[-1]=='word']} for page in doc.iter() if page.tag.rsplit('}',1)[-1]=='page']
def main(key,publish):
 folder,pdf,project,pages=SPECS[key];source=APP/'papers'/folder/'abc-20261020';dest=Path('/Users/depengsu/.local/share/bf-agent-manuscripts/overleaf')/project;out=HERE/'overleaf'/key;out.mkdir(parents=True,exist_ok=True)
 prepared=out/'prepared.json'
 if not publish:
  assert not prepared.exists(),'ALREADY_PREPARED'
  dirty=run(['git','status','--porcelain','-uall'],dest).decode().splitlines()
  # A failed preflight may already have written exactly this source set. Resume
  # only byte-identical intended writes and the known rebuildable PDF removal.
  for line in dirty:
   rel=line[3:];q=dest/rel;p=source/rel
   assert (rel=='example_paper.pdf' and line[:2]==' D') or (p.is_file() and q.is_file() and p.read_bytes()==q.read_bytes()),('UNEXPECTED_DIRTY_FILE',rel)
  run(['git','merge','--ff-only','FETCH_HEAD'],dest)
  before=run(['git','rev-parse','HEAD'],dest).decode().strip();remote=run(['git','ls-remote','origin','refs/heads/main'],dest).decode().split()[0];assert before==remote
  selected=[]
  for p in sorted(source.rglob('*')):
   rel=p.relative_to(source)
   if not p.is_file() or any(x in rel.parts for x in ['.build','data','qa','tmp','__pycache__']):continue
   include=p.suffix in ['.tex','.bib','.sty'] or (p.suffix in ['.pdf','.png','.jpg','.jpeg','.svg','.eps'] and rel.parts[0] in ['assets','figures'])
   if not include:continue
   data=p.read_bytes();assert not re.search(rb'(?:olp_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,})',data),'SECRET_PATTERN'
   q=dest/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data);selected.append(str(rel))
  (dest/'example_paper.tex').write_text('\\input{main.tex}\n');selected.append('example_paper.tex')
  # TeX's recorder can resolve the package name from ProvidesPackage to this
  # compatibility path. Bind both existing paths to the accepted source bytes.
  (dest/'hkustgz-paper.sty').write_bytes((source/'style/hkustgz-paper.sty').read_bytes());selected.append('hkustgz-paper.sty')
  removed=[]
  if (dest/'example_paper.pdf').exists():
   removed.append({'path':'example_paper.pdf','bytes':(dest/'example_paper.pdf').stat().st_size,'sha256':sha(dest/'example_paper.pdf'),'restore_commit':before});(dest/'example_paper.pdf').unlink()
  elif run(['git','ls-files','--','example_paper.pdf'],dest).strip():
   previous=run(['git','show',before+':example_paper.pdf'],dest)
   removed.append({'path':'example_paper.pdf','bytes':len(previous),'sha256':hashlib.sha256(previous).hexdigest(),'restore_commit':before})
  build=[]
  with tempfile.TemporaryDirectory(prefix='bf-abc-overleaf-') as tmp:
   for n in [1,2]:
    p=subprocess.run(['/Library/TeX/texbin/pdflatex','-interaction=nonstopmode','-halt-on-error','-file-line-error','-recorder','-output-directory='+tmp,'example_paper.tex'],cwd=dest,capture_output=True,timeout=60)
    build.append({'pass':n,'exit_code':p.returncode})
    if p.returncode:
     (out/'failed-build.log').write_bytes(p.stdout);raise RuntimeError('LOCAL_PORTABLE_ENTRY_BUILD_FAILED; log saved')
   log=(Path(tmp)/'example_paper.log').read_text(errors='replace');material=[x for x in log.splitlines() if any(y in x for y in ['Overfull','Underfull','Missing character','undefined references','undefined citations','multiply defined'])];assert not material,material
   built=Path(tmp)/'example_paper.pdf';word_view=words(built);assert len(word_view)==pages and word_view==words(source/pdf),'WORD_LAYOUT_MISMATCH'
   fonts=run(['/opt/homebrew/bin/pdffonts',str(built)]).decode().splitlines()[2:];assert fonts and all(re.search(r'\byes\s+yes\s+yes\s+\d+\s+\d+\s*$',x) for x in fonts),'FONT_NOT_EMBEDDED'
   fls=(Path(tmp)/'example_paper.fls').read_text().splitlines();inputs=[]
   for line in fls:
    if line.startswith('INPUT '):
     x=Path(line[6:]);x=(dest/x).resolve() if not x.is_absolute() else x.resolve()
     if x.is_relative_to(dest) and x.is_file() and not x.is_relative_to(Path(tmp)):
      rel=str(x.relative_to(dest));
      if rel not in inputs:inputs.append(rel)
   # Every project-local compile dependency must be one of the selected new files.
   assert set(inputs).issubset(set(selected)),('UNSELECTED_COMPILE_INPUT',set(inputs)-set(selected))
  manifest={'schema':'bf-abc-overleaf-dependencies-v1','source_pdf_sha256':sha(source/pdf),'pages':pages,'project':project,'source':'Accepted ABC manuscript, compile dependencies only.','files':{n:sha(dest/n) for n in selected},'cloud_compile_verified':False}
  (dest/'abc-publication.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');selected.append('abc-publication.json')
  run(['git','diff','--check'],dest)
  record={'status':'PREPARED','key':key,'project':project,'checkout':str(dest),'before_head':before,'selected_files':selected,'file_sha256':{n:sha(dest/n) for n in selected},'retired_rebuildable_files':removed,'compile_dependencies':inputs,'actual_pdflatex_passes':build,'page_count':pages,'all_word_coordinates_equal_to_accepted_pdf':True,'all_fonts_embedded':True,'material_warnings':material,'temporary_build_removed':True,'cloud_compile_verified':False,'source_pdf_sha256':sha(source/pdf)};write(prepared,record);print(json.dumps({'key':key,'status':'PREPARED','files':len(selected),'pages':pages,'retired_rebuildable_files':len(removed)}))
 else:
  record=json.loads(prepared.read_text());assert not (out/'pushed.json').exists(),'ALREADY_PUSHED'
  assert run(['git','rev-parse','HEAD'],dest).decode().strip()==record['before_head']
  assert run(['git','ls-remote','origin','refs/heads/main'],dest).decode().split()[0]==record['before_head'],'REMOTE_CHANGED'
  for n,h in record['file_sha256'].items():assert sha(dest/n)==h,n
  names=record['selected_files']+[x['path'] for x in record['retired_rebuildable_files']]
  run(['git','add','--',*names],dest);run(['git','diff','--cached','--check'],dest)
  staged=run(['git','diff','--cached','--name-only'],dest).decode().splitlines();assert staged and set(staged).issubset(set(names))
  run(['git','commit','-m','Update accepted ABC '+key+' manuscript and HKUST-GZ layout'],dest)
  head=run(['git','rev-parse','HEAD'],dest).decode().strip();run(['git','push','origin','HEAD:main'],dest,timeout=60)
  run(['git','fetch','--no-tags','origin','main'],dest,timeout=60);assert run(['git','rev-parse','FETCH_HEAD'],dest).decode().strip()==head
  for n,h in record['file_sha256'].items():assert hashlib.sha256(run(['git','show','FETCH_HEAD:'+n],dest)).hexdigest()==h,n
  assert not run(['git','status','--porcelain'],dest).strip()
  write(out/'pushed.json',{'status':'PUSHED_READBACK_PASS','project':project,'head':head,'previous_head':record['before_head'],'remote_source_files_read_back':len(record['file_sha256']),'pages':pages,'cloud_compile_verified':False,'at':datetime.datetime.now(datetime.timezone.utc).isoformat()});print(json.dumps({'key':key,'status':'PUSHED_READBACK_PASS','head':head}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','push']);p.add_argument('key',choices=SPECS);args=p.parse_args();main(args.key,args.action=='push')
