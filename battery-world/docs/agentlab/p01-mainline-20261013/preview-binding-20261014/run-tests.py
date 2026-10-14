import hashlib, json, pathlib, time, unittest
from bfworld.agentlab import literature_native
from bfworld.agentlab.literature_campaign import digest
out=pathlib.Path("/Users/depengsu/Documents/Long-Horizon AI Agent/workbench/bf-refactor-r0-r2-20261011/battery-world/docs/agentlab/p01-mainline-20261013/preview-binding-20261014")/'release-tests-reportfix'
out.mkdir(exist_ok=True)
names=['test_candidate_results','test_product_results','test_paper_sessions','test_engineering_cases','test_cad_preview','test_execution_progress','test_eda_cli','test_runtime_architecture','test_context_recovery','test_current_working_context','test_round2_efficiency','test_literature_native','test_literature_eda','test_literature_package','test_literature_continuation','test_design_lab_paper','test_design_lab_mainline','test_design_lab_ingress','test_design_lab_trace_ingest','test_design_lab_operator_restore','test_design_lab_eda_migration','test_design_lab_native_context','test_design_lab_phase_goal','test_candidate_queue_outcome','test_result_selection','test_session_receipt']
# Keep only existing modules; list is recorded with their exact bytes.
names=[n for n in names if (pathlib.Path('tests/agentlab')/(n+'.py')).is_file()] + ['test_studio_delivery']
suite=unittest.defaultTestLoader.loadTestsFromNames(['tests.agentlab.'+n for n in names])
before={n:digest(pathlib.Path('tests/agentlab')/(n+'.py')) for n in names}
app_id,modules=literature_native.apparatus_identity(); controller=digest(literature_native.__file__)
start=time.time()
with (out/'tests.log').open('w') as f:result=unittest.TextTestRunner(stream=f,verbosity=1,buffer=True).run(suite)
after={n:digest(pathlib.Path('tests/agentlab')/(n+'.py')) for n in names}
v={'status':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'seconds':time.time()-start,'suites':names,
'apparatus_identity':app_id,'apparatus_modules':modules,'controller_sha256':controller,'controller_unchanged':controller==digest(literature_native.__file__),'test_source_sha256':before,'test_sources_unchanged':before==after,'log_sha256':digest(out/'tests.log'),
'external_model_calls':0,'new_native_solver_runs':0,'scope':'Readonly candidate/artifact binding, preview integrity, unchanged original-owner recovery; temporary unit-test states only.'}
(out/'tests.json').write_text(json.dumps(v,indent=2))
print(json.dumps({k:v[k] for k in ('status','tests','errors','failures','seconds')}))

