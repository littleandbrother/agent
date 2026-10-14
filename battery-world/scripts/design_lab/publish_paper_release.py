#!/usr/bin/env python3
"""Publish a tested, owner-preserving continuation release; no model dispatch."""
import argparse
from pathlib import Path
import sys
import time
import sqlite3

APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP/'packages/python/bfworld/src'))
from bfworld.agentlab import engineering_projects, literature_native
from bfworld.agentlab.literature_campaign import DEFAULT_ROOT, bound_file, digest, put_once, read
from bfworld.agentlab.literature_continuation import load_authority, retained_unknowns
from bfworld.agentlab.design_lab.contracts import sealed
from bfworld.agentlab.store import canonical
from bfworld.agentlab.runtime_config import eda_policy

parser=argparse.ArgumentParser();parser.add_argument('--tests',type=Path,required=True)
parser.add_argument('--p01-output64',action='store_true',help='Opt only the original P01 owner into the 64K output profile; model and thinking stay fixed')
parser.add_argument('--p01-active-context',action='store_true',help='Keep the 220K projection target but admit a bounded active reasoning/tool exchange up to 1MiB for the original P01 owner')
parser.add_argument('--p01-efficient',action='store_true',help='Original P01: one closed-stage index and deduplicated on-demand skills; same model, thinking and capacity')
parser.add_argument('--root',type=Path,default=DEFAULT_ROOT);args=parser.parse_args();root=args.root
tests=read(args.tests);current,modules=literature_native.apparatus_identity()
if (tests['status']!='PASS' or tests['failures'] or tests['errors'] or tests['tests']<200 or
    not tests.get('test_sources_unchanged') or
    any(digest(APP/'tests/agentlab'/(name+'.py'))!=value for name,value in tests['test_source_sha256'].items()) or
    not tests['controller_unchanged'] or tests['apparatus_identity']!=current or
    tests['controller_sha256']!=digest(literature_native.__file__) or
    tests['log_sha256']!=digest(args.tests.parent/'tests.log') or
    tests.get('native_transport',{}).get('exit_code') != 0 or
    not tests['native_transport'].get('source_unchanged') or
    tests['native_transport']['log_sha256'] != digest(args.tests.parent/'native-transport-tests.log') or
    any(digest(APP/name) != value for name,value in tests['native_transport']['source_sha256'].items()) or
    tests.get('current_context_interface',{}).get('exit_code') != 0 or
    tests['current_context_interface'].get('caller_build_exit_code') != 0 or
    not tests['current_context_interface'].get('source_unchanged') or
    any(digest(name) != value for name,value in tests['current_context_interface']['source_sha256'].items()) or
    tests['current_context_interface']['log_sha256'] != digest(args.tests.parent/'current-context-tests.log') or
    tests['current_context_interface']['caller_build_log_sha256'] != digest(args.tests.parent/'pi-caller-build.log') or
    modules.get('tool/native-eda-adapter') != modules.get('tool/native-eda-adapter-source')):
    raise ValueError('CURRENT_RELEASE_TESTS_REQUIRED')
authority=load_authority(root)
if authority['schema_version']!='bf-ten-paper-continuation-authority-v2':
    raise ValueError('DIRECT_UNBOUNDED_TIME_AUTHORITY_REQUIRED')
with sqlite3.connect('file:'+str(root/'runtime/state/workbench.sqlite')+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    unknown_rows=[dict(row) for row in db.execute("SELECT * FROM model_requests WHERE status='UNKNOWN'")]
historical=read(root/'revisions/active-integration-v3/authorized-liabilities.json')['requests']
unknown=retained_unknowns(unknown_rows,historical,authority,time.time())
old_path=root/'campaign/native-qualification.json';old=read(old_path)
calibrations=[]
for item in old['native_worker_calibrations']:
    path=bound_file(root,item['result'],item['sha256']);value=read(path)
    # Retain byte-exact successful worker artifacts; do not recompute targets or
    # physical models merely because an authority/context wrapper changed.
    if value.get('readback_passed') is False:raise ValueError('OLD_CALIBRATION_FAILED')
    for output in value.get('outputs',[]):
        bound_file(root,str((path.parent/output['name']).relative_to(root)),output['sha256'])
    calibrations.append(item)
for name in ('firmware_targets','nordic_sdk','stm32_l432','spice_observation'):
    key='bfworld.agentlab.'+name
    if modules[key]!=old['apparatus_modules'][key]:raise ValueError('NATIVE_MODEL_OR_BUILD_CHANGED:'+key)
for key,value in old['apparatus_modules'].items():
    if key.startswith(('vendor/','compiler/')) and modules.get(key)!=value:
        raise ValueError('PINNED_VENDOR_OR_COMPILER_CHANGED:'+key)
folder=root/'deployment/executable-lab-20261012'/('paper-release-'+str(time.time_ns()))
folder.mkdir(parents=True,exist_ok=False)
for path,name in ((old_path,'previous-native-qualification.json'),
                  (root/'campaign/parallel-20261009/READY.json','previous-READY.json'),
                  (args.tests,'tests.json'),(args.tests.parent/'tests.log','tests.log'),
                  (args.tests.parent/'native-transport-tests.log','native-transport-tests.log'),
                  (args.tests.parent/'current-context-tests.log','current-context-tests.log'),
                  (args.tests.parent/'pi-caller-build.log','pi-caller-build.log')):
    (folder/name).write_bytes(path.read_bytes())
eda=APP/'docs/agentlab/local-desktop-eda-20261012/native-closeout.json'
if read(eda)['status']!='PASS_IN_DECLARED_SCOPE':raise ValueError('DESKTOP_NATIVE_CAPABILITY_RECEIPT_REQUIRED')
(folder/'desktop-native-capability.json').write_bytes(eda.read_bytes())
qualified={**old,'schema_version':'bf-paper-native-qualification-v38',
           'created':time.time(),'status':'PASS','controller_sha256':digest(literature_native.__file__),
           'apparatus_sha256':digest(engineering_projects.__file__),
           'apparatus_identity':current,'apparatus_modules':modules,
           'historical_qualification':str((folder/'previous-native-qualification.json').relative_to(root)),
           'historical_qualification_sha256':digest(folder/'previous-native-qualification.json'),
           'targeted_tests':tests['tests'],'test_count_basis':'Current complete release test run; older runs are not added to this count.',
           'test_source_sha256':tests['test_source_sha256'],
           'native_worker_calibrations':calibrations,'model_calls':0,'new_solver_runs':0,
           'old_successful_calculations_replayed':0,'new_native_geometry_generation':0,
           'scope':'Original paper owner continuation, exact authority/history, version/file/core acceptance separation and desktop typed interface. Native C joint qualification is a separate apparatus scope.',
           'reuse_basis':'Eight byte-exact successful worker artifacts and their output files, unchanged target/vendor/compiler and SPICE-reader code pins. Authority/dispatcher/interface changes tested independently; no old physics recomputed.',
           'common_repairs':list(dict.fromkeys(old['common_repairs']+[
                'Original-candidate inspection returns its exact stored candidate selector and complete file/hash manifest alongside the retained count. Recovery callers can revise the current selection without reconstructing it from historical tool records; inspection does not mutate the design or award acceptance',
                'Original-owner candidate queue outcomes use only a decision event created in the current attempt; execution failure remains RUN_FAILED instead of inheriting old CONTINUE. Main-service operator package downloads use the existing registered paper readonly adapter, current submission/check/hash verification and original project paths without a second Workbench or database writes',
                'The actual sandboxed SPICE executor uses ngspice binary raw output instead of forcing ASCII; double-precision samples, original solver input and 64MiB bound remain. Existing ASCII/binary/multiplot/complex/truncated/nonfinite readback checks and the real executor environment contract are included in this release; old successful product simulations are reused',
                'SPICE accepts local .meas/.measure observations. Original candidate engineering admission validates the actual project before recording dispatch, so rejected directives create no UNKNOWN. Operator reconciliation of the historical pre-queue refusal binds its original immutable result, frozen circuit, prior qualified validator/dispatcher and absence of a native job; it retains the original UNKNOWN receipt and all model fee rows without replay',
                'Candidate recovery stages the exact registered current work into the original TASK.md and CURRENT-CANDIDATE-WORK.json, exposes its hash-bound reference through the actual product-context consumer, and archives stale phase instructions. The frozen product contract, engineering sources, owner and historical conversations remain intact',
                'Original paper candidate submit and download consume its recorded independent check, exact frozen editable inputs and matching successful native outputs. Failed gates remain in the review bundle; no C-case execution, adoption or acceptance rewrite. Actual Pi submit schema, idempotent HTTP round-trip, tampered check/output/ZIP rejection and stale-candidate download are tested; paper delivery code is pinned in apparatus identity',
               'Schematic-to-PCB import uses schematic-authoritative attributes and records effective --no-sync-attrs in the native receipt; the original desktop P01 reproduced library backfill introducing a Netlist Error and exact-source reimport clearing it, without changing its 39 components, board geometry or copper',
               'Original native job queries and candidate resume inspection settle the matching waiting operation from its existing terminal receipt without redispatch. Serialized settlement emits one completion event for concurrent/repeated observations. Schematic connectivity is admitted as a read while unresolved writes remain blocked. Read-only federated paper views stay read-only',
               'The actual Studio original-owner recovery endpoint atomically publishes the canonical queue file consumed by the serial worker, retains immutable request and terminal history, reports current completion on exact retries, and refuses overwriting queued/running work',
               'Registered finished controller stages become archived request history at every context size; current scope, genuine user instructions, differing constraints and raw SDK history remain exact. Legacy terminal queue receipts override immutable prior queued snapshots and remain owner-isolated',
               'Actual archived-tool decoding counterexample: retain byte-exact raw messages plus hash-bound directly readable tool text, never assistant reasoning. Original P01 candidate recovery enables the existing completed-controller provenance filter using its registered recovery message; distinct original constraints and unregistered human messages remain. Candidate inspection exposes the actual frozen Skill catalog. No engineering source, evaluator semantics, ledger or original job is changed',
               'Pinned complete upstream EasyEDA Skill package, with its entry manual included in activation and all references paged. Actual EDA-enabled Pi resumes explicitly activate the current Skill rather than inherit stale manifest rows; package/source/helper hashes and caller tests are frozen. Operator-only desktop generation reconciliation retains the original native failure and UNKNOWN import history, confirms stable persisted files and fresh scene, and never replays the interrupted replacement',
               'Original P01 actual HTTP/native tool and queue consumers enter the existing DesignLab candidate ledger. Fixed eight-gate paper scope and evaluator remain authoritative; unknown writes prevent mutation/retry and case-C routing is refused. Pi records its own candidate decision instead of the legacy twelve-step delivery observer. Existing exact selected jobs reuse their original immutable outputs; integration tests and actual Pi caller are pinned, no automatic product/method/physical claim',
               'Explicit original-phase closed-stage context policy archives only exact database-bound native-controller messages with immutable ended-attempt receipts; current stage, unregistered human instructions, distinct inherited constraints, original SDK/ledger and protected core/method bytes remain. Manifest proof is rechecked before each paid request, default-disabled and no-pressure behavior remain compatible; archives are owner-local facts, not acceptance',
               'Historical complete tool pairs evict before current work; current completed evidence is hash-archived before current-turn pair eviction, preserving more exact call/result identities under the original caps. Explicit tagged startup copies deduplicate only under byte pressure when every copied human text remains verbatim in user history; unique core/method/instruction and partial batches stay exact',
               'Opted-in source research honors the same explicit original-owner unlimited wall authority as Engineering and model execution while retaining existing grants, leases and ledger rows; mandatory authorization preflight precedes paid dispatch and read-only whole-chain inventory reports refusals without constructing a Workbench',
               'Explicit original-phase source research enables the existing owner/grant-scoped bf_reference tool and native route, pins reference code, and preserves exact external bytes without changing frozen task or acceptance',
               'Completed parallel tool replies below the old 8000-byte threshold are archived with bounded previews only under aggregate pressure; original evidence, every call/result identity and protected text survive the unchanged request cap',
               'Owner-scoped latest native-phase machine snapshot retains exact constraints once; older generated snapshots are hash-bound historical references, with all human suffixes unchanged',
               'Explicit user-issued unlimited wall time; retain old expiries, reservations, fees and owners',
               'One cross-process native lease for ordinary engineering, design tasks and original paper phases; thread handoff retains phase exclusion',
               'Pin effective runtime host/paths and both actual queue entry scripts',
               'Scoped defect resolution does not grant core function or full product acceptance',
               'Desktop ARM typed read/edit/save/reload evidence remains bounded to isolated native project',
               'Bounded Bash failures, incremental trace ingestion and lock-resilient passive observation',
               'Native persistent-file and document identity; runtime UUID aliases retain original binding history',
               'Exact current phase and vendor-reference pointer restored; large previous results stay hash-bound history',
               'Canonical original-owner queue files only; waiting states are not phase completion',
               'Real S132 recovery objective rejects substitution by an old bare-metal build',
               'Native phase context separates current local binding/jobs from exact hash-bound generic history; project kind is not a skill_id',
               'Authenticated 64MiB raw SDK ingress still uses unchanged pinned provider projection and wire cap; original history retained',
               'Missing native file-session identity waits within the existing deadline; nonempty wrong project and document identities reject',
               'Bounded read-only progress projection revalidates public checks and live inputs; assembly sequence never fabricates ancestry; operator design restore requires idle known operations',
               'Single-product queue selection occurs before any mutation of unselected canonical original-owner records',
               'EDA is resolved at actual tool use; offline help/skill/job reads and unrelated phases do not require a connected application',
               'Already-proved exact local file/runtime UUID is read back without reopening the same project; foreign owner, proof and document identities reject',
               'Read-only whole-chain preflight distinguishes executable availability, exact-input reusable jobs and unverified product gates; dead worker is never automatic replay authority',
               'Unlimited-time original-owner recovery reads exact protocol liability carryforwards after finite-study expiry; ledger rows, full reservations and UNKNOWN statuses remain byte-exact, foreign/altered claims reject',
               'One kernel lease prevents managed/manual native connector duplication; all official CLI invocations serialize, idle polls are disposable and bounded',
               'An entered unknown native write remains quarantined until an operator closes its exact headless generation and proves byte-exact persisted files plus same-scene fresh readback in the new generation; original failure and unknown remain history, no request replay',
               'Failed read-only project probes retain the actual transport refusal and never dispatch the design command; entered command timeouts remain UNKNOWN without replay',
               'Fixed identity diagnostic reads execute without a recursive project probe, but fresh project and desktop host identity must still match before success',
               'P01-only native file scope, event-driven context and payload-free request lifecycle diagnostics reduce unrelated discovery without weakening on-use project checks',
               'Current session receipt pointers publish through flushed atomic replacement; observers see complete old or new facts, sealed attempts and failures remain history',
               'Native identity diagnostics finish below upstream deadlines, refuse busy/expired bypass reads before SDK entry, and never accumulate a second native invocation queue',
               'Readonly native diagnostic timeout does not enter write UNKNOWN/quarantine; entered mutating timeouts and no-replay semantics remain unchanged under actual-connector injected stalls',
               'On-use EDA failures retain bounded actual cause and design-not-dispatched fact in the error text consumed by the current Pi client; failed transport is not foreign identity',
               'An operator-pinned receiver environment and bundled Python tree are readonly only for the exact original P01 workspace; tree/manifest changes reject qualification and foreign owners do not inherit access',
               'Receiver dependency preflight uses the identical Pi seatbelt before paid dispatch; public task resource paths and hashes are visible without front-loading their contents',
               'Native refusal envelopes normalize error.detail to the actual Go protocol string schema; real-package decode tests reject historical object detail while preserving cause and UNKNOWN/no-replay semantics',
               'P01 production EDA uses the existing ARM desktop Connect with exact local project identity and desktop half-offline/offline policy; intermittent headless CLI bridge remains a stopped candidate, no Web fallback',
               'Unrelated owners get neither receiver read grants nor repeated tree audits; full dependency validation remains mandatory for the exact qualified original caller',
               'Original-owner live context exposes hash-bound native job metadata; a frozen public utility prepares only explicit Pi-selected delivery metadata and archives previous bytes, rejecting stale inputs, foreign jobs and unsafe paths; independent acceptance remains unchanged',
               'EDA operation and job retrieval explicitly identify historical observations and never replay commands or award current-design acceptance',
               'Current original-owner context restores bounded latest EDA read/save/PCB observation pointers with exact workspace receipt hashes; failed/UNKNOWN newest attempts remain visible, foreign/corrupt records do not become verified observations, no SDK call or acceptance inferred',
               'Pi exposes the existing current owner-bound task/job/EDA receipt projection through explicit bf_product context_inspect during a long turn; each GET is uncached, refuses extra mutation/scope arguments and retains real server failures, no native call or acceptance inferred; actual caller/helper pins and interface/build evidence are qualified'])),
           'eda_execution_policy':eda_policy(),
           'test_evidence':[{'path':str((folder/name).relative_to(root)),'sha256':digest(folder/name)}
                            for name in ('tests.json','tests.log','native-transport-tests.log','current-context-tests.log','pi-caller-build.log','desktop-native-capability.json')],
           'native_transport_tests': tests['native_transport'],
           'current_context_interface_tests': tests['current_context_interface'],
           'canary_allowed_owners':[],'profile_scope':'engineering-reasoning-v1 for the ten original owners; no compact-v2 rollout or method-benefit claim',
           'retained_unknown_count':len(unknown),'full_product_passed':False,'physical_verified':False}
if args.p01_output64:
    from bfworld.agentlab.model_profile import OUTPUT64
    owners=[r['owner'] for r in read(root/'campaign/parallel-20261009/pi-session-index.json')['sessions'] if r['paper_id']=='P01']
    if len(owners)!=1:raise ValueError('ORIGINAL_P01_PROFILE_OWNER_REQUIRED')
    qualified['original_owner_output_profiles']={**old.get('original_owner_output_profiles',{}),owners[0]:OUTPUT64['version']}
    qualified['profile_scope']='Original profiles retained; only the original P01 candidate uses explicit output64-v3. Same deepseek-flash, thinking enabled/high and unchanged request-context caps.'
    qualified['output_profile_repair']={'owner':owners[0],'previous_output_tokens':32768,'output_tokens':65536,
        'trigger':'Actual P01 SETTLED request ended length with 32768 reasoning tokens and zero actions',
        'docs':'https://api-docs.deepseek.com/api/create-chat-completion/','model_changed':False,
        'thinking_changed':False,'other_owner_profiles_changed':False,'method_gain':'NOT_EVALUATED'}
if args.p01_active_context:
    from bfworld.agentlab.model_profile import ACTIVE
    owners=[r['owner'] for r in read(root/'campaign/parallel-20261009/pi-session-index.json')['sessions'] if r['paper_id']=='P01']
    if len(owners)!=1:raise ValueError('ORIGINAL_P01_PROFILE_OWNER_REQUIRED')
    qualified['original_owner_output_profiles']={**qualified.get('original_owner_output_profiles',{}),owners[0]:ACTIVE['version']}
    qualified['profile_scope']='Original profiles retained; only original P01 admits active tool/reasoning exchanges up to 1MiB. Projection still targets 220000 bytes; same deepseek-flash, thinking enabled/high and 65536 output tokens.'
    qualified['active_context_capacity_repair']={'owner':owners[0],
        'trigger':'Actual P01 request compressed from 28982602 to 307085 bytes and was rejected by the 256000 byte admission bound',
        'request_bytes':ACTIVE['request_bytes'],'target_bytes':ACTIVE['target_bytes'],
        'model_changed':False,'thinking_changed':False,'other_owner_profiles_changed':False,
        'history_deleted':False,'method_gain':'NOT_EVALUATED'}
if args.p01_efficient:
    from bfworld.agentlab.model_profile import EFFICIENT
    owners=[r['owner'] for r in read(root/'campaign/parallel-20261009/pi-session-index.json')['sessions'] if r['paper_id']=='P01']
    if len(owners)!=1:raise ValueError('ORIGINAL_P01_PROFILE_OWNER_REQUIRED')
    qualified['original_owner_output_profiles']={**qualified.get('original_owner_output_profiles',{}),owners[0]:EFFICIENT['version']}
    qualified['profile_scope']='Original owners retained; P01 round2 efficiency v5, fixed deepseek-flash/thinking high and output/context capacities.'
    qualified['round2_efficiency']={'owner':owners[0],'profile':EFFICIENT,
        'test_source':tests['test_source_sha256'].get('test_round2_efficiency'),
        'retained_unknown_count':len(unknown),'old_engineering_reused':True,'method_gain':'PENDING_REAL_MEASUREMENT'}
sealed(folder/'native-qualification.json',qualified)
ready={**read(folder/'previous-READY.json'),'created':time.time(),'updated':time.time(),
       'qualification':str(old_path),'qualification_sha256':digest(folder/'native-qualification.json'),
       'authorization':str(root/authority['authority_file']),
       'authorization_sha256':authority['authority_sha256'],
       'budget_authority':str(root/authority['budget_authority_file']),
       'budget_authority_sha256':authority['budget_authority_sha256'],
       'status':'PASS','targeted_tests':tests['tests'],
       'parent_ready':{'path':str((folder/'previous-READY.json').relative_to(root)),'sha256':digest(folder/'previous-READY.json')},
       'reason':'Current tested continuation release; direct unlimited-time user authority, preserved original ten owners and billing liabilities.',
       'scope':'Ten original independent Pi conversations. No cumulative USD/token/request/time cap; bounded individual operations and no-progress rules remain. Core/physical/method claims are separate.'}
ready['context_canary']={**ready.get('context_canary',{}),'status':'HISTORICAL_NO_ROLLOUT'}
for command in ready['commands'].values():
    command['phase']='engineering-review'
    command['resume_command']='rtk proxy env PYTHONPATH=.:packages/python/bfworld/src '+str(APP/'.venv/bin/python')+' scripts/literature_paper_resume.py '+next(p for p,c in ready['commands'].items() if c is command)+' --phase engineering-review'
sealed(folder/'READY.json',ready)
def publish(path,data):
    temporary=path.with_suffix('.next');temporary.write_bytes(data);temporary.replace(path)
publish(old_path,(folder/'native-qualification.json').read_bytes())
publish(root/'campaign/parallel-20261009/READY.json',(folder/'READY.json').read_bytes())
sealed(folder/'activation.json',{'status':'PASS','at':time.time(),'qualification_sha256':digest(old_path),
       'ready_sha256':digest(root/'campaign/parallel-20261009/READY.json'),
       'authority_sha256':authority['authority_sha256'],'unknown_rows_preserved':len(unknown),
       'database_writes':0,'model_calls':0,'native_calls':0,'participant_engineering_edits':0,
       'owner_policies':'Installed by the legitimate original-owner dispatch, not by a second query Workbench.'})
print(folder/'activation.json')
