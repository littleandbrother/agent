#!/usr/bin/env python3
"""Read-only P01 whole-chain inventory; no Workbench, solver or design writer."""
import argparse
import contextlib
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT, read, digest, bound_file
from bfworld.agentlab.design_lab.contracts import sealed
from bfworld.agentlab.design_lab.paper_mainline import process_alive, project_snapshot, reusable_job
from bfworld.agentlab.literature_eda import runtime_alias_project, local_destination, verify_native_documents, open_local_destination
from bfworld.agentlab.eda_cli import CLI, read_health, select_window
from bfworld.agentlab.runtime_config import eda_policy
from bfworld.agentlab.engineering_projects import KINDS
from bfworld.agentlab.references import References
from bfworld.agentlab.literature_native import native_reference_enabled, native_reference_preflight

OWNER = 'pi-chat-b47a35e335bc68d4'
PROJECTS = ['project-cad/project.json', 'project-spice/project.json',
            'project-spice-source/project.json', 'project-fw/project.json', 'project-fw-s132/project.json']


def worker_lock_held(queue):
    """A terminal PID can be reused; the original worker owns this flock."""
    path = Path(queue)/'worker.lock'
    if path.is_symlink() or not path.is_file():
        raise ValueError('ORIGINAL_WORKER_LOCK_REQUIRED')
    with path.open('r') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
    return False


def source_capability_inventory(db, owner, phase):
    """Check actual installed source authority through a caller-owned RO DB.

    Deliberately bypasses Workbench construction and References.__init__:
    inventory must not recover sessions or create directories/database state.
    """
    enabled = native_reference_enabled(phase)
    context = db.execute('SELECT config FROM chat_contexts WHERE owner=?',(owner,)).fetchone()
    tools = json.loads(context['config']).get('tools',[]) if context else []
    service = References.__new__(References)
    service.store = SimpleNamespace(connect=lambda: contextlib.nullcontext(db))
    try:
        facts = native_reference_preflight(SimpleNamespace(references=service),owner,enabled)
    except (PermissionError,ValueError) as exc:
        facts = {'schema_version':'bf-native-source-preflight-v1','owner':owner,
                 'enabled':enabled,'status':'REFUSED','error':str(exc),
                 'model_calls':0,'network_calls':0,'grant_mutations':0,
                 'source_acquisition_verified':False,'full_product_passed':False}
    return {**facts,'installed_tool': 'bf_reference' in tools,'database_mode':'ro'}


def preflight(root, output, live_eda=False):
    index_path = root/'campaign/parallel-20261009/pi-session-index.json'
    session = next(x for x in read(index_path)['sessions'] if x['paper_id'] == 'P01')
    if session['owner'] != OWNER or session['session_id'] != OWNER:
        raise ValueError('P01_ORIGINAL_OWNER_REQUIRED')
    workspace = root/'runtime/participants'/OWNER
    if Path(session['workspace']).resolve() != workspace.resolve():
        raise ValueError('P01_WORKSPACE_IDENTITY')
    contract = read(workspace/'contract.json')
    if contract['paper_id'] != 'P01': raise ValueError('P01_CONTRACT_REQUIRED')
    sources = [{**a, 'hash_verified': bool(bound_file(root, a['path'], a['sha256']))}
               for a in contract['assets']]
    output.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect('file:'+str(root/'runtime/state/workbench.sqlite')+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        jobs = [dict(row) for row in db.execute('SELECT * FROM engineering_jobs WHERE owner=? ORDER BY created DESC', (OWNER,))]
        assembly = db.execute('SELECT * FROM assembly_revisions WHERE owner=? ORDER BY revision DESC LIMIT 1', (OWNER,)).fetchone()
        hashes = json.loads(assembly['hashes']) if assembly else {}
        conversation = dict(db.execute('SELECT id,status,error,updated FROM conversations WHERE id=?', (OWNER,)).fetchone())
        active = [dict(row) for row in db.execute("SELECT id,owner,status FROM engineering_jobs WHERE status IN ('PENDING','RUNNING')")]
        active_conversations = [dict(row) for row in db.execute("SELECT id,status FROM conversations WHERE status='RUNNING'")]
        binding_row = db.execute('SELECT * FROM eda_cli_binding_revisions WHERE owner=? ORDER BY created DESC LIMIT 1', (OWNER,)).fetchone()
        if not binding_row: binding_row = db.execute('SELECT * FROM eda_cli_bindings WHERE owner=?', (OWNER,)).fetchone()
        binding = dict(binding_row) if binding_row else None
        eda_counts = [dict(row) for row in db.execute('SELECT status,count(*) AS count FROM eda_cli_jobs WHERE owner=? GROUP BY status', (OWNER,))]
        unknown_native = [dict(row) for row in db.execute("SELECT id,operation,status FROM eda_cli_jobs WHERE owner=? AND status IN ('UNKNOWN','RUNNING')", (OWNER,))]
        ledger = [dict(row) for row in db.execute('SELECT status,count(*) AS requests,sum(charged) AS local_charge_usd,sum(reserved) AS full_reserved_usd FROM model_requests WHERE owner=? GROUP BY status', (OWNER,))]
        current_phase = read(root/'campaign/recovery/P01/phases/engineering-review.json')
        source_capability = source_capability_inventory(db,OWNER,current_phase)
    projects = []
    for relative in PROJECTS:
        try: snapshot = project_snapshot(workspace, relative)
        except (ValueError, OSError, KeyError) as exc:
            projects.append({'path': relative, 'status': 'SOURCE_UNAVAILABLE', 'error': str(exc)})
            continue
        candidates = []
        for job in jobs:
            request = json.loads(job['request'])
            if request.get('parameters', {}).get('project_path') != relative: continue
            result = json.loads(job['result']) if job['result'] else {}
            artifacts = result.get('artifacts', [])
            valid = bool(artifacts)
            for artifact in artifacts:
                file = root/'runtime/engineering'/job['id']/artifact['name']
                valid = valid and file.is_file() and not file.is_symlink() and digest(file) == artifact['sha256']
            candidates.append({'job_id': job['id'], 'status': job['status'], 'error': job['error'],
                               **reusable_job(snapshot, request, job['status'], hashes, valid)})
        projects.append({**snapshot, 'status': 'SOURCE_AVAILABLE', 'executions': candidates})
    pointer = read(root/'campaign/acceptance/current.json')
    acceptance_path = bound_file(root, pointer['path'], pointer['sha256'])
    acceptance = next(p for p in read(acceptance_path)['papers'] if p['paper'] == 'P01')
    worker = read(root/'campaign/parallel-20261009/pi-queue/worker.json')
    native = {'status': 'NOT_PROBED', 'binding': binding, 'historical_jobs': eda_counts,
              'unknown_native_operations': unknown_native, 'native_design_accepted': False}
    if live_eda:
        if active or active_conversations or worker_lock_held(root/'campaign/parallel-20261009/pi-queue'):
            raise ValueError('LIVE_PREFLIGHT_REQUIRES_IDLE_SHARED_SERVICES')
        try:
            record = read(root/'campaign/eda/P01/binding.json')
            creation = read(bound_file(root, record['creation']['path'], record['creation']['sha256']))
            project = runtime_alias_project(root, 'P01', record, creation, binding)
            # Exercise the production local-destination gate, with opening
            # forbidden. Healthy daemon discovery alone cannot prove startup.
            window, _ = open_local_destination(record, creation, project, eda_policy(), allow_open_missing=False)
            receipts = []
            commands = [('project-info', ['project','info']), ('board-list',['board','list'])]
            for name, argv in commands:
                proc = subprocess.run([CLI, *argv, '--window', window['windowId']], capture_output=True, text=True, timeout=20)
                if proc.returncode: raise ValueError('EDA_READBACK_FAILED:'+name)
                data = json.loads(proc.stdout)
                if data.get('ok') is not True: raise ValueError('EDA_READBACK_REJECTED:'+name)
                (output/(name+'.json')).write_text(proc.stdout)
                receipts.append({'path': name+'.json', 'sha256': digest(output/(name+'.json'))})
                if name == 'project-info' and (data['result']['uuid'] != project or data['result']['friendlyName'] != creation['name']):
                    raise ValueError('EDA_EXACT_PROJECT_MISMATCH')
                if name == 'board-list':
                    verify_native_documents(local_destination(record, creation), data)
                    boards = data['result']['boards']
            native.update(status='EXACT_LOCAL_PROJECT_READABLE', project_uuid=project,
                          window_id=window['windowId'], local_project=record['local_project'],
                          local_file_sha256=digest(Path(record['local_project'])), boards=boards, read_only_receipts=receipts)
        except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
            native.update(status='EXECUTION_UNAVAILABLE', error=str(exc))
    # Current public acceptance remains a historical, hash-bound verdict. It
    # is not promoted by capability availability, a native build or packaging.
    result = {'schema_version':'bf-p01-whole-chain-preflight-v2', 'created':time.time(),
              'owner':OWNER, 'paper_id':'P01', 'source_identity':contract['source_identity'],
              'original_index_sha256':digest(index_path), 'sources':sources, 'projects':projects,
              'execution':conversation, 'active_native_jobs':active, 'active_conversations':active_conversations,
        'worker':{**worker,'recorded_pid_alive':process_alive(worker.get('pid')),
                  'process_alive':worker_lock_held(root/'campaign/parallel-20261009/pi-queue')},
              'execution_capabilities':{k:{'executable':str(v),'present':Path(v).is_file()} for k,v in KINDS.items()},
              'local_eda':native, 'ledger':ledger,
              'source_capability':source_capability,
              'existing_acceptance':{'path':pointer['path'],'sha256':pointer['sha256'],
                                     'created':read(acceptance_path)['created'],'gates':acceptance['functional_gates']},
              'chain_requirements':['source_domain','schematic_bom_pins','pcb_connectivity_drc','geometry_fit',
                                    'firmware_event_logic','board_firmware_interfaces','power_load_chain','delivery_version'],
              'source_decision_record':{'path':'docs/interface-chain.md','sha256':digest(workspace/'docs/interface-chain.md')},
              'database_mode':'ro','model_calls':0,'solver_runs':0,'participant_engineering_edits':0,
              'scope':'Actual execution availability and exact-input reuse; core function remains independently checked.',
              'functional_passed':False,'full_product_passed':False,'physical_verified':False}
    sealed(output/'preflight.json',result)
    return output/'preflight.json'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--live-eda',action='store_true')
    args=parser.parse_args();print(preflight(args.root,args.out,args.live_eda))


if __name__=='__main__': main()
