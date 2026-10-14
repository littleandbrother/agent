"""Operator-certified native waveform reuse; no participant verdicts.

Reuse requires identical physical inputs AND the actual freshly compiled
program's complete current/state trace on both native waveforms. A new source
or protocol may still fail independent application checks. This never promotes
a Cortex-M4 object or virtual receiver to target/RF qualification.
"""
import ast
import json
from pathlib import Path, PurePosixPath
import shutil
from .contracts import sha, sealed
from ..store import identity

VERSION='bf-native-waveform-witness-v1'


def function_text(path,name):
    text=Path(path).read_text()
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return ast.get_source_segment(text,node)


def kernel_identity(producer=None):
    from . import native_solver
    from ..door_selfpower import solver as legacy
    path=Path(producer) if producer else Path(native_solver.__file__)
    helpers=Path(producer) if producer else Path(legacy.__file__)
    return identity({'solve':function_text(path,'solve'),
                     'helpers':{n:function_text(helpers,n) for n in ('deck','native_solve','gate_observation')}})


def model_identity(env,physical):
    from . import case_c
    model=env['native_model']
    return identity({'physical_design':physical,
        'assets':{k:model[k]['sha256'] for k in ('rom','force','force_domain')},
        'dependencies':model['source_dependencies'],
        'stage_current':case_c.CURRENT,
        'runner_source':identity(case_c.RUNNER)})


def bound(root,name,digest):
    name=PurePosixPath(name)
    if name.is_absolute() or '..' in name.parts or not name.parts:
        raise ValueError('NATIVE_WITNESS_PATH_DENIED')
    path=Path(root)/str(name)
    if (any((Path(root)/Path(*name.parts[:i])).is_symlink() for i in range(1,len(name.parts)+1)) or
        not path.resolve().is_relative_to(Path(root).resolve()) or not path.is_file() or sha(path)!=digest):
        raise ValueError('NATIVE_WITNESS_ARTIFACT_DRIFT:'+str(name))
    return path


def original(certificate):
    root=Path(certificate['producer_root'])
    for name,digest in certificate['producer_files'].items():bound(root,name,digest)
    q=json.loads((root/'qualification.json').read_text())
    if not q['passed'] or q['new_native_solver_calls']<=0:raise ValueError('NATIVE_WITNESS_NOT_QUALIFIED')
    folder=root/'changed-TX-6ms'
    execution=json.loads((folder/'execution.json').read_text())
    if (execution['execution_id']!='X-'+identity({k:v for k,v in execution.items() if k!='execution_id'}) or
        not execution['power_fixed_point'] or not all(execution['native_checks'].values())):
        raise ValueError('NATIVE_WITNESS_EXECUTION_INVALID')
    for name,digest in execution['observations'].items():bound(folder,name,digest)
    verify_archives(execution['native_dependencies'],folder)
    return folder,execution


def verify_archives(items,root=None):
    seen=set();digests=set()
    for item in items:
        path=Path(item['path'])
        if ((root is not None and not path.resolve().is_relative_to(Path(root).resolve())) or
            path.is_symlink() or not path.is_file() or not item['readback_verified']):
            raise ValueError('NATIVE_WITNESS_RAW_PROVENANCE')
        # Equal declared digests do not prove two distinct files are equal.
        # Avoid re-reading only the same resolved file with the same digest.
        key=(path.resolve(),item['sha256'])
        if key not in seen:
            if not path.is_file() or sha(path)!=item['sha256']:raise ValueError('NATIVE_WITNESS_RAW_DRIFT')
            seen.add(key)
        digests.add(item['sha256'])
    return {'archives':len(items),'unique_sha256':len(digests),'files_hashed':len(seen),'verified':True}


def reuse(descriptor,task,design,build,directory,env,physical):
    from . import case_c,coupled_c
    if descriptor is None:return None
    path=Path(descriptor['path'])
    if path.is_symlink() or sha(path)!=descriptor['sha256']:raise ValueError('NATIVE_WITNESS_CERTIFICATE_DRIFT')
    cert=json.loads(path.read_text())
    producer=cert.get('producer_kernel',{})
    producer_path=Path(producer.get('path',''))
    if (not producer_path.is_file() or producer_path.is_symlink() or
        sha(producer_path)!=producer.get('sha256') or
        kernel_identity(producer_path)!=cert.get('kernel_identity')):
        raise ValueError('NATIVE_WITNESS_PRODUCER_KERNEL_DRIFT')
    if (cert.get('schema_version')!=VERSION or cert.get('issuer')!='operator-no-agent-qualification' or
        cert.get('environment_id')!=env['environment_id'] or
        cert.get('validation_id')!=task['validation_id'] or cert.get('kernel_identity')!=kernel_identity()):
        raise ValueError('NATIVE_WITNESS_CERTIFICATE_BINDING')
    if cert['model_identity']!=model_identity(env,physical):return None
    source,old=original(cert)
    directory=Path(directory)
    # Both observations are replayed through this candidate's actual executable.
    # Comparing complete state/current samples proves the circuit load input is
    # equal; source similarity or a participant's claimed current does not.
    replay=[]
    for name in ('joint','time-step'):
        shutil.copyfile(source/name/'program.csv',directory/'program.csv')
        witness={**env,'root':str(directory),'files':{'program.csv':sha(directory/'program.csv')}}
        value=case_c.execute(task,design,build,directory,witness)
        replay.append(value['power_fixed_point'])
    if not all(replay):return None
    for name,digest in old['observations'].items():
        if name in ('execution.csv','execution-tx.csv'):continue
        target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(bound(source,name,digest),target)
    # Authoritative mission observations always use the coarse converged trace.
    shutil.copyfile(source/'joint/program.csv',directory/'program.csv')
    witness={**env,'root':str(directory),'files':{'program.csv':sha(directory/'program.csv')}}
    final=case_c.execute(task,design,build,directory,witness)
    reuse={'certificate_sha256':descriptor['sha256'],'producer_execution_id':old['execution_id'],
           'original_native_solver_calls':old['new_native_solver_calls'],
           'complete_current_state_equal_on_coarse_and_fine':True,
           'kernel_semantics_equal':True,'new_native_solver_calls':0,
           'scope':'Exact native physical/load inputs only; application protocol, target execution and physical verification remain separate.'}
    sealed(directory/'native-witness-reuse.json',reuse)
    final.update(schema_version=coupled_c.VERSION,scope=coupled_c.SCOPE,
        native_solve='REUSED_QUALIFIED_NATIVE_WITNESS',new_native_solver_calls=0,
        native_checks=old['native_checks'],native_metrics=old['native_metrics'],
        native_dependencies=old['native_dependencies'],provisional_events_committed=False,
        solver_input_design_id=physical['design_id'],native_witness_reuse=reuse)
    final['observations'].update({name:sha(directory/name) for name in old['observations']
                                if name not in ('execution.csv','execution-tx.csv')})
    final['observations']['native-witness-reuse.json']=sha(directory/'native-witness-reuse.json')
    final.pop('execution_id')
    return {**final,'execution_id':'X-'+identity(final)}
