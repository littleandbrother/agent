"""Relocate only known historical paths; execute preserved code bytes unchanged.

This is a delivery/test adapter, not a physics or scientific-model adapter.
The original checks are run against included exact source snapshots. They do
not check the current remote upstream repository or an unavailable solver binary.
"""
import os
import pathlib
import runpy
import subprocess
import sys
import types

NativePath=type(pathlib.Path())
BUNDLE=NativePath(__file__).resolve().parents[1]
HISTORICAL='/workspace/shared/'
MAIN=('authoritative-world-20261001','causal-evaluator-repair-20261001',
      'controlled-agent-protocol-20261001','world-evaluator-independent-review-20261001')

def replay_path(*args,**kwargs):
        p=NativePath(*args,**kwargs)
        if p.is_absolute() and p.is_relative_to(BUNDLE):return p
        # Interpreter/dependency files belong to the chosen local runtime,
        # even when that runtime happens to be installed beneath /workspace.
        if p.is_absolute() and any(p.is_relative_to(NativePath(x)) for x in (sys.prefix,sys.base_prefix)):
            return p
        s=str(p)
        prefix=HISTORICAL+MAIN[3]+'/snapshots/protocol'
        world_prefix=HISTORICAL+MAIN[3]+'/snapshots/world'
        if s==prefix or s.startswith(prefix+'/'):
            p=BUNDLE/'evidence'/MAIN[2]/s[len(prefix):].lstrip('/')
        elif s==world_prefix or s.startswith(world_prefix+'/'):
            p=BUNDLE/'evidence'/MAIN[0]/s[len(world_prefix):].lstrip('/')
        elif s.startswith(HISTORICAL):
            suffix=s[len(HISTORICAL):]
            head=suffix.split('/')[0]
            if head in MAIN:p=BUNDLE/'evidence'/suffix
            else:p=BUNDLE/'provenance/workspace-shared'/suffix
        return p

class ReplayPath(NativePath):
    def __new__(cls,*args,**kwargs):
        return super().__new__(cls,replay_path(*args,**kwargs))
    def __init__(self,*args,**kwargs):
        if sys.version_info>=(3,12):
            super().__init__(replay_path(*args,**kwargs))

def main():
    if len(sys.argv)<2:raise SystemExit('Provide a preserved script path and its arguments')
    script=NativePath(sys.argv[1]).resolve()
    if not script.is_relative_to(BUNDLE/'evidence'):raise SystemExit('Only preserved evidence scripts may run')
    blocked={'run_diagnostics.py','build_repair.py','build_rail_contract.py','freeze_plan.py','finish_manifest.py','build_contracts.py','seal.py'}
    if script.name in blocked:raise SystemExit('Generation/scientific execution is outside replay scope')
    sys.argv=[str(script),*sys.argv[2:]]
    sys.path.insert(0,str(script.parent))
    if script.parent.name=='tests':sys.path.insert(0,str(script.parent.parent))
    os.chdir(script.parent)
    # A proxy avoids changing pathlib's own class-dispatch globals. New imports
    # receive the mapper; native Path methods retain their original module.
    proxy=types.ModuleType('pathlib')
    proxy.__dict__.update(pathlib.__dict__)
    proxy.Path=ReplayPath
    sys.modules['pathlib']=proxy
    original_run=subprocess.run
    def relocated_run(command,*args,**kwargs):
        # One audit starts a child preflight. Preserve that child process and
        # carry the same source-path adapter into it; isolated fixture probes
        # and host-C compiler calls retain their exact original commands.
        if isinstance(command,list) and len(command)>=3 and command[:2]==[sys.executable,'-B']:
            candidate=NativePath(command[2])
            if candidate==BUNDLE/'evidence'/MAIN[2]/'preflight.py':
                command=command[:2]+[str(BUNDLE/'tools/replay_entry.py')]+command[2:]
        return original_run(command,*args,**kwargs)
    subprocess.run=relocated_run
    def reject_original_source_reads(event,args):
        if event!='open' or not args or not isinstance(args[0],(str,bytes,os.PathLike)):return
        raw=os.fsdecode(args[0]);path=NativePath(raw)
        if not path.is_absolute():path=(NativePath.cwd()/path).resolve()
        if not str(path).startswith(HISTORICAL):return
        if path.is_relative_to(BUNDLE) or any(path.is_relative_to(NativePath(x)) for x in (sys.prefix,sys.base_prefix)):return
        raise RuntimeError('UNBUNDLED_HISTORICAL_SOURCE_READ:'+str(path))
    # A regression guard, not a participant sandbox or OS isolation claim.
    sys.addaudithook(reject_original_source_reads)
    runpy.run_path(str(script),run_name='__main__')

if __name__=='__main__':main()
