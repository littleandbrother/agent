"""macOS Seatbelt participant process: no network, private read, write or forks.

Only the passed code/context enter the child; no API credentials or reference
source. This is a tested local research boundary, not a universal exploit-proof VM.
"""
import json
import os
import resource
import subprocess
import tempfile
from pathlib import Path
PYTHON='/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11'

def profile(workspace:Path):
    escaped=str(workspace.resolve()).replace('\\','\\\\').replace('"','\\"')
    private=' '.join(f'(subpath "{p}")' for p in ['/Users','/private','/Volumes','/opt','/Applications','/usr/local','/Library/Application Support','/Library/Preferences','/Library/Keychains'])
    return f'''(version 1)(allow default)(deny network*)
      (deny file-read* (require-all (require-any {private}) (require-not (subpath "{escaped}"))))
      (deny file-write* (require-not (require-any (subpath "{escaped}") (subpath "/dev"))))
      (deny process-fork)'''

def execute(code:str,context:dict,base:Path):
    if len(code.encode())>24000:raise ValueError('program too large')
    base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='participant-',dir=base) as temp:
        workspace=Path(temp).resolve()
        wrapper='import json,sys\nctx=json.loads(sys.stdin.read())\n'+code+'\nprint(json.dumps(plan(ctx),allow_nan=False))\n'
        (workspace/'program.py').write_text(wrapper)
        def limits():
            resource.setrlimit(resource.RLIMIT_CPU,(2,2));resource.setrlimit(resource.RLIMIT_FSIZE,(262144,262144));resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
            process=subprocess.Popen(['/usr/bin/sandbox-exec','-p',profile(workspace),PYTHON,'-I','-S',str(workspace/'program.py')],
              stdin=subprocess.PIPE,stdout=out,stderr=err,cwd=workspace,env={'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8'},preexec_fn=limits)
            try:process.communicate(json.dumps(context).encode(),timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise ValueError('participant timeout')
            out.seek(0);err.seek(0);output=out.read(262144).decode(errors='replace');error=err.read(4096).decode(errors='replace')
        if process.returncode:raise ValueError('participant failed: '+error[-600:])
        if len(output)>200000:raise ValueError('participant output limit')
        return json.loads(output)

def preflight(base:Path,protected:Path):
    checks={}
    checks['program_executes']=execute('def plan(ctx): return {"answer":ctx["n"]+1}',{'n':2},base)=={'answer':3}
    code='''def plan(ctx):
 import socket,subprocess
 checks={}
 try:
  open(ctx['protected']).read();checks['private_read_denied']=False
 except PermissionError:checks['private_read_denied']=True
 try:
  open(ctx['write_target'],'w').write('bad');checks['external_write_denied']=False
 except PermissionError:checks['external_write_denied']=True
 try:
  socket.create_connection(('127.0.0.1',8766),timeout=.2);checks['network_denied']=False
 except PermissionError:checks['network_denied']=True
 except OSError:checks['network_denied']=False
 try:
  subprocess.run(['/usr/bin/true']);checks['fork_denied']=False
 except PermissionError:checks['fork_denied']=True
 return checks'''
    checks.update(execute(code,{'protected':str(protected),'write_target':str(base.parent/'forbidden-write')},base))
    if not all(checks.values()):raise RuntimeError('participant isolation preflight failed: '+json.dumps(checks))
    return {'status':'pass','checks':checks,'boundary':'OS Seatbelt; private directories and network blocked; clean environment; CPU/output limits','separate_filesystem':True}
