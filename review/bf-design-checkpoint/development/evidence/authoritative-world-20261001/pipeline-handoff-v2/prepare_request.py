"""Non-solving preflight and exact kwargs for the existing native pipeline.

No imports of native.py, commercial solvers, or pipeline execution occur here.
Tool identities must be freshly rechecked at execution; a prepared request is not
an execution authorization or a native-qualified model.
"""
import argparse, copy, json
from pathlib import Path
import sys
WORLD_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WORLD_ROOT/'src'))
import authoritative_world as aw
FROZEN_RECEIPT_SHA256='0434005d13c1e33ab55bf28ed5d1814b8e93c2bcef08baf27d2bdc4281e187e1'
TRANSITIVE_LOCK_SHA256='815d97dadfda079d9b3c12856519505d28d324ddde565df154b061d12fe465d9'
DEFAULT_PIPELINE_ROOT=Path('/workspace/shared/current-cache-integration-20261001/working/battery-world/packages/python/bfworld/src/bfworld/agentlab/simulation_chain')


def transitive_sources(pipeline_root):
    lock_path=Path(__file__).with_name('TRANSITIVE-SOURCES.json')
    if aw.file_hash(lock_path)!=TRANSITIVE_LOCK_SHA256:
        raise aw.ContractError('TRANSITIVE_LOCK_CHANGED')
    expected=aw.read_json(lock_path)['files']
    repo=Path(pipeline_root).resolve().parents[6]
    for relative,ref in expected.items():
        path=repo/relative
        if not path.is_file() or path.is_symlink() or path.stat().st_size!=ref['bytes'] or aw.file_hash(path)!=ref['sha256']:
            raise aw.ContractError('TRANSITIVE_SOURCE_CHANGED:'+relative)
    return expected


REQUIRED_TOOL_HASHES=('pmic_model','ltspice_launcher','ltspice_executable','comsol_launcher',
                      'comsol_binary','arm_compiler','host_compiler','cad_python','comsol_piezo_library')


def collect_runtime_identity(pipeline):
    # Call only in the intended runtime. Missing paths fail; do not replace them
    # with synthetic test hashes. The material path is literally used by DoorBeam.
    tools=dict(pipeline.tool_identity())
    tools['cad_python']=aw.file_hash(pipeline.native.CAD)
    tools['comsol_piezo_library']=aw.file_hash('/Applications/COMSOL62/Multiphysics/data/comsol_piezo_lib.mph')
    return tools


def validate_tools(tools):
    for key in REQUIRED_TOOL_HASHES:
        value=tools.get(key)
        if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise aw.ContractError('TOOL_IDENTITY_MISSING_OR_INVALID:'+key)
    if not tools.get('python') or not isinstance(tools.get('libraries'),dict) or not tools['libraries']:
        raise aw.ContractError('RUNTIME_VERSIONS_MISSING')


def prepare_request(candidate, model, tools, pipeline_root=DEFAULT_PIPELINE_ROOT, task_name='DEV-FEASIBLE-01'):
    validate_tools(tools)
    if aw.file_hash(WORLD_ROOT/'FREEZE-RECEIPT.json')!=FROZEN_RECEIPT_SHA256:
        raise aw.ContractError('FROZEN_RECEIPT_MISMATCH')
    if not aw.verify_freeze()['verified']:
        raise aw.ContractError('FROZEN_CORE_MISMATCH')
    world=aw.load_world();tasks=aw.read_json(WORLD_ROOT/'contracts/tasks-v2.json')['tasks']
    task=next((t for t in tasks if t['task_id']==task_name),None)
    if task is None:raise aw.ContractError('UNKNOWN_TASK')
    if task['experimental_unit']=='same_state_continuation':
        raise aw.ContractError('CANONICAL_CONTINUATION_CHECKPOINT_MISSING')
    if model.get('world_provider')!=world['circuit']['model']:
        raise aw.ContractError('PROVIDER_NOT_CANONICAL_NATIVE_CHAIN')
    pipeline_root=Path(pipeline_root)
    registry=aw.read_json(WORLD_ROOT/'contracts/source-registry.json')
    for name,filename in [('upstream_contracts','contracts.py'),('upstream_native','native.py'),('upstream_solver','solver.py'),('upstream_program','program.c')]:
        if aw.file_hash(pipeline_root/filename)!=registry['sources'][name]['sha256']:
            raise aw.ContractError('INSTALLED_SOURCE_MISMATCH:'+filename)
    # Derive scientific settings from exactly the candidate given to production;
    # independently supplied settings cannot drift from it.
    spec=aw.migrate_upstream_spec(candidate,'upstream-338d603')
    solver={'solver_version':'upstream-native-fixed-point-338d603','settings':spec['solver'],'tool_hashes':tools}
    sources=aw.source_identity(registry)
    impl={p.name:aw.file_hash(p) for p in sorted(pipeline_root.glob('*')) if p.suffix in ('.py','.c')}
    sources['installed_pipeline_implementation']={'sha256':aw.digest(impl),'files':impl}
    transitive=transitive_sources(pipeline_root)
    sources['installed_transitive_sources']={'sha256':aw.digest(transitive),'files':transitive}
    identity=aw.make_run_identity(world,spec,task,model,solver,sources)
    keys=aw.stage_keys(world,spec,task,model,solver,sources)
    request={'schema':'bf-existing-pipeline-handoff-v2','task_name':task_name,'candidate':spec,'identity':identity,'stage_keys':keys,
            'callable':'bfworld.agentlab.simulation_chain.pipeline.submit_candidate',
            'installed_pipeline_root':str(pipeline_root),'installed_implementation':impl,'transitive_sources':transitive,
            'tool_identity_to_recheck_at_execution':copy.deepcopy(tools),'solver':copy.deepcopy(solver),'model':copy.deepcopy(model),
            'cache_namespace':identity['run_identity'],'confirm':True,
            'prepared_only':True,'execution_authorized_by_this_request':False,
            'physical_qualified':False,'formal_trial_admitted':False,
            'result_rule':'Retain original result, add identity companion; never map cold_start/received_groups to attributed mission or physical qualification.'}

    request['request_id']=aw.digest(request)
    return request


def validate_request(request):
    if not isinstance(request,dict) or request.get('request_id')!=aw.digest({k:v for k,v in request.items() if k!='request_id'}):
        raise aw.ContractError('REQUEST_INTEGRITY_MISMATCH')
    reconstructed=prepare_request(request['candidate'],request['model'],request['tool_identity_to_recheck_at_execution'],
                                  request['installed_pipeline_root'],request['task_name'])
    if reconstructed!=request:
        raise aw.ContractError('REQUEST_RECONSTRUCTION_MISMATCH')
    return True


def verify_runtime(request, actual_tools, actual_implementation):
    validate_request(request)
    if request['tool_identity_to_recheck_at_execution']!=actual_tools:
        raise aw.ContractError('EXECUTION_TOOLS_CHANGED')
    if request['installed_implementation']!=actual_implementation:
        raise aw.ContractError('EXECUTION_IMPLEMENTATION_CHANGED')
    return True


def pipeline_kwargs(request, new_run_output, cache_parent):
    """Pass to submit_candidate only after user permission and verify_runtime.

    This function returns data and does not create paths or call the provider.
    """
    validate_request(request)
    output=Path(new_run_output);cache=Path(cache_parent)/request['cache_namespace']
    if output.exists():raise aw.ContractError('NEW_RUN_OUTPUT_REQUIRED')
    if output.resolve().is_relative_to(WORLD_ROOT.resolve()) or cache.resolve().is_relative_to(WORLD_ROOT.resolve()):
        raise aw.ContractError('FROZEN_PACKAGE_CANNOT_BE_RUNTIME_OUTPUT')
    return {'candidate':copy.deepcopy(request['candidate']),'output':output,'cache_root':cache,'confirm':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--tools',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--pipeline-root',type=Path,default=DEFAULT_PIPELINE_ROOT)
    a=p.parse_args()
    request=prepare_request(aw.read_json(a.candidate),aw.read_json(a.model),aw.read_json(a.tools),a.pipeline_root)
    # New output only; original requests and evidence are immutable.
    with a.output.open('x') as f:f.write(json.dumps(request,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'prepared':True,'run_identity':request['identity']['run_identity'],'executed':False}))

if __name__=='__main__':main()
