from pathlib import Path
import hashlib,json,datetime
ROOT=Path(__file__).resolve().parent
out=ROOT/'PLAN-SEAL.json'
if out.exists():raise RuntimeError('refuse to overwrite frozen plan seal')
files=[p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in str(p) and 'revisions' not in p.relative_to(ROOT).parts and p not in [ROOT/'PLAN-SEAL.json',ROOT/'DYNAMIC-AUTHORIZATION.json']]
bindings={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
out.write_text(json.dumps({'version':'passive-study-plan-seal-v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bindings':bindings,'dynamic_trajectories_executed':0},indent=2)+'\n')
print(hashlib.sha256(out.read_bytes()).hexdigest())
