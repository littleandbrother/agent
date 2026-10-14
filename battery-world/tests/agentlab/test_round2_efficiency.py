"""Real P01 failure shapes, exact recovery and public consumer contracts."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab import continuation_context as cc, interface_facts as interfaces
from bfworld.agentlab.context import ContextArchive, project_interactive
from bfworld.agentlab.store import canonical, identity
from bfworld.agentlab.design_lab import paper_candidate as pc
from bfworld.agentlab import literature_package as package
from bfworld.agentlab.provider import usage_costs
import test_closed_continuation_context as closed_cases
import test_design_lab_paper as paper_cases
from test_closed_continuation_context import user, OWNER


class EfficiencyControls(unittest.TestCase):
    def test_p01_parameter_dictionary_dimensions_counts_and_expressions(self):
        text='P = {"pcb_l":40.0,"pcb_w":70.0,"idt_n":20,"enabled":True,"label":"PCB"}\nZ = P["pcb_l"] / 2\n'
        facts=interfaces.cad_parameters(text,'teng_assembly.py',interfaces.digest(text.encode()),'mm')
        observed={f['id']:f for f in facts}
        self.assertEqual({'cad.P.pcb_l','cad.P.pcb_w','cad.P.idt_n'},set(observed))
        self.assertEqual(40,observed['cad.P.pcb_l']['value'])
        self.assertEqual(70,observed['cad.P.pcb_w']['value'])
        self.assertEqual('mm',observed['cad.P.idt_n']['declared_project_units'])
        self.assertIsNone(observed['cad.P.idt_n']['unit'])
        self.assertEqual(1,observed['cad.P.pcb_l']['source']['line'])

    def test_many_closed_stages_one_index_keeps_distinct_constraints_and_live_tools(self):
        f = closed_cases.ClosedContinuationTests('runTest'); f.setUp(); self.addCleanup(f.tearDown)
        second = copy.deepcopy(f.manifest['closed_messages'][0])
        second.update(id='second', text='A second completed machine stage', text_sha256=interfaces.digest(b'A second completed machine stage'))
        manifest = {**f.manifest, 'closed_messages': [f.manifest['closed_messages'][0], second]}
        messages = [f.messages[0], user(f.old_text), user(second['text'], requirements=['Distinct operator condition']),
                    f.messages[2], f.messages[3],
                    {'role':'assistant','tool_calls':[{'id':'pending','function':{'name':'read','arguments':'{}'}}]}]
        payload = {'messages':messages}
        out, audit = project_interactive(payload, f.archive, request_bytes=32000, target_bytes=24000,
                                        closed_continuations=manifest, aggregate_closed=True)
        self.assertEqual(1, sum('历史控制器索引' in canonical(m) for m in out['messages']))
        self.assertIn('Distinct operator condition', canonical(out))
        for index in (0, 3, 4, 5): self.assertIn(messages[index], out['messages'])
        index = next(x for x in audit['archived_messages'] if x['kind']=='closed_controller_index')
        content = json.loads((f.home/'participants'/OWNER/index['record_file']).read_text())
        self.assertEqual(2, len(content['records']))
        for item in content['records']:
            self.assertEqual(item['sha256'], identity(json.loads((f.home/'participants'/OWNER/item['record_file']).read_text())))
        self.assertEqual(messages, payload['messages'])

    def test_activated_skill_one_body_and_conflicting_versions_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = ContextArchive(Path(directory), OWNER)
            skill = {'id':'test-method','content':'Exact professional method '*200, 'sha256':'a'*64,
                     'manifest_sha256':'b'*64,'version':'v1'}
            payload={'messages':[{'role':'system','content':'Fixed rules'}, {'role':'user','content':'Current user goal'},
                {'role':'assistant','tool_calls':[{'id':'activation','function':{'name':'bf_skill','arguments':'{}'}}]},
                {'role':'tool','tool_call_id':'activation','content':canonical({'schema_version':'bf-skill-activation-v1',**skill})}]}
            out, _ = project_interactive(payload, archive, request_bytes=50000,target_bytes=40000,
                                         active_skills=[skill,skill],deduplicate_skills=True)
            self.assertEqual(1, canonical(out).count(skill['content']))
            self.assertIn('body_in_protected_skill_context', canonical(out))
            with self.assertRaisesRegex(ValueError,'VERSION_CONFLICT'):
                project_interactive(payload,archive,active_skills=[skill,{**skill,'sha256':'c'*64}],deduplicate_skills=True)

    def test_cache_costs_preserve_independent_ledger_semantics(self):
        result=usage_costs({'prompt_tokens':1000,'completion_tokens':100,'prompt_cache_hit_tokens':750,'prompt_cache_miss_tokens':250})
        self.assertAlmostEqual(.0001995,result['cache_aware_estimate_usd'])
        self.assertIsNone(usage_costs({'prompt_tokens':1000,'completion_tokens':100})['cache_aware_estimate_usd'])

    def test_delivery_recovers_interruption_between_two_metadata_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'delivery').mkdir()
            before={'native-report.json':b'old report','delivery/manifest.json':b'old manifest'}
            for name,raw in before.items():(root/name).write_bytes(raw)
            hashes={name:interfaces.digest(raw) for name,raw in before.items()}
            replace=Path.replace
            def interrupt(path,target):
                if path.name=='manifest.metadata-next':raise RuntimeError('Injected process exit')
                return replace(path,target)
            with patch.object(Path,'replace',interrupt), self.assertRaisesRegex(RuntimeError,'Injected'):
                package.install(root,'interrupted',b'new report',b'new manifest',recovery_inputs=hashes)
            receipt=package.install(root,'interrupted',b'new report',b'new manifest',recovery_inputs=hashes)
            self.assertEqual(2,len(receipt['previous']))
            self.assertEqual(b'new report',(root/'native-report.json').read_bytes())
            self.assertEqual(b'new manifest',(root/'delivery/manifest.json').read_bytes())
            self.assertEqual(receipt,package.install(root,'interrupted',b'new report',b'new manifest',recovery_inputs=hashes))

    def test_actual_timing_and_pin_unit_mismatch(self):
        text='#define APP_ADV_INTERVAL 300\n#define MIN_CONN_INTERVAL MSEC_TO_UNITS(100, UNIT_1_25_MS)\n#define MAX_CONN_INTERVAL MSEC_TO_UNITS(200, UNIT_1_25_MS)\n .adv_period_ms = 5000,\n'
        facts=interfaces.firmware_timing(text,'main.c',interfaces.digest(text.encode()))
        self.assertEqual(187.5,facts[0]['value']); self.assertEqual(1,facts[0]['source']['line'])
        links=[{'left':'ble.advertising_ms','right':'policy.advertising_ms','affected':['power']}]
        self.assertEqual('FAIL',interfaces.compare_bindings(links,facts)[0]['status'])
        facts=[{'id':'pcb.gpio','value':27,'unit':'GPIO'}, {'id':'firmware.gpio','value':26,'unit':'GPIO'}]
        link={'left':'pcb.gpio','right':'firmware.gpio','affected':['firmware','power']}
        self.assertEqual('FAIL',interfaces.compare_bindings([link],facts)[0]['status'])
        facts[1].update(value=27,unit='pad'); self.assertEqual('FAIL',interfaces.compare_bindings([link],facts)[0]['status'])
        facts[1]['unit']='GPIO'; self.assertEqual('PASS',interfaces.compare_bindings([link],facts)[0]['status'])

    def test_fact_reference_resolves_value_and_rejects_unsupported_location(self):
        self.assertEqual((40,None),interfaces.referenced_value(b'P={"pcb_l":40}\n','model.py',{'symbol':'P.pcb_l'}))
        self.assertEqual((40,None),interfaces.referenced_value(b'P={"pcb_l":40}\n','model.py',{'fact_id':'cad.P.pcb_l'}))
        with self.assertRaisesRegex(ValueError,'SELECTOR_CONFLICT.*model.py'):
            interfaces.referenced_value(b'P={"pcb_l":40}\n','model.py',{'symbol':'P.pcb_w','fact_id':'cad.P.pcb_l'})
        self.assertEqual((27,None),interfaces.referenced_value(b'{"pins":[26,27]}','pins.json',{'json_pointer':'/pins/1'}))
        self.assertEqual((187.5,'ms'),interfaces.referenced_value(b'#define APP_ADV_INTERVAL 300\n','main.c',{'fact_id':'ble.advertising_ms'}))
        with self.assertRaisesRegex(ValueError,'SELECTOR_REQUIRED.*pins.json.*json_pointer'):
            interfaces.referenced_value(b'{"value":40}','pins.json',{'line':1})


class ActualRoundTwoEntry(unittest.TestCase):
    def setUp(self):
        self.f=paper_cases.OriginalPaperConsumer('runTest');self.f.setUp();self.addCleanup(self.f.tearDown)
        self.lab=self.f.app.design_lab

    def test_current_fields_http_and_no_automatic_full_sources(self):
        status,value=self.f.request('/api/design-lab',{'action':'inspect'})
        self.assertEqual(200,status,value)
        self.assertEqual('bf-paper-current-view-v2',value['view_schema'])
        self.assertNotIn('input_manifest',value)
        self.assertEqual(self.f.view['working_design'],value['working_design'])
        status,value=self.f.request('/api/design-lab',{'action':'inspect','fields':['input_manifest']})
        self.assertEqual(200,status,value);self.assertIn('plan.md',value['input_manifest'])

    def test_interfaces_live_hash_and_current_candidate(self):
        path=self.f.workspace/'project/main.c';path.write_text('#define APP_ADV_INTERVAL 300\n .adv_period_ms = 5000,\n')
        choice={**self.f.choice,'files':self.f.choice['files']+['project/main.c']}
        design=pc.handle(self.lab,self.f.owner,{'action':'freeze','parent':self.f.view['working_design'],
                         'sources':{'candidate.json':canonical(choice)}})
        status,value=self.f.request('/api/design-lab',{'action':'interfaces','files':['project/main.c']})
        self.assertEqual(200,status,value);self.assertEqual(design['design_id'],value['design_id'])
        self.assertEqual(4812.5,value['parameter_contrasts'][0]['difference_ms'])
        path.write_text('#define APP_ADV_INTERVAL 301\n')
        status,value=self.f.request('/api/design-lab',{'action':'interfaces','files':['project/main.c']})
        self.assertEqual(400,status,value);self.assertIn('RECHECK_REQUIRED',canonical(value))

    def test_default_interface_entry_consumes_real_project_snapshot_source_files(self):
        f=self.f;cad=f.workspace/'cad';cad.mkdir()
        (cad/'model.py').write_text('P={"pcb_l":40.0,"pcb_w":70.0,"count":20}\n')
        (cad/'project.json').write_text(canonical({'schema_version':'bf-engineering-project-v1','kind':'cadquery',
            'entrypoint':'model.py','files':['model.py'],'interfaces':{'units':'mm'}}))
        choice={**f.choice,'projects':f.choice['projects']+['cad/project.json']}
        design=pc.handle(self.lab,f.owner,{'action':'freeze','parent':f.view['working_design'],
            'sources':{'candidate.json':canonical(choice)}})
        status,value=f.request('/api/design-lab',{'action':'interfaces'})
        self.assertEqual(200,status,value)
        self.assertEqual(design['design_id'],value['design_id'])
        self.assertEqual([40,70,20],[x['value'] for x in value['facts']])
        self.assertEqual('cad/model.py',value['sources'][0]['path'])
        (cad/'model.py').write_text('P={"pcb_l":41.0}\n')
        status,value=f.request('/api/design-lab',{'action':'interfaces'})
        self.assertEqual(400,status,value);self.assertIn('RECHECK_REQUIRED',canonical(value))

    def test_http_binding_rejects_invented_value_with_correct_source_hash(self):
        f=self.f;source=f.workspace/'project/pins.json';source.write_text('{"gpio":27}')
        record={'schema_version':'bf-interface-bindings-v1','facts':[{'id':'pcb.scl','value':26,'unit':'GPIO',
            'source':{'path':'project/pins.json','sha256':interfaces.digest(source.read_bytes()),'json_pointer':'/gpio'}}],'bindings':[]}
        target=f.workspace/'interface-bindings.json';target.write_text(canonical(record))
        choice={**f.choice,'files':f.choice['files']+['project/pins.json','interface-bindings.json']}
        first=pc.handle(self.lab,f.owner,{'action':'freeze','parent':f.view['working_design'],
            'sources':{'candidate.json':canonical(choice)}})
        status,value=f.request('/api/design-lab',{'action':'interfaces','files':['interface-bindings.json']})
        self.assertEqual(400,status,value);self.assertIn('VALUE_MISMATCH',canonical(value))
        record['facts'][0]['value']=27;target.write_text(canonical(record))
        pc.handle(self.lab,f.owner,{'action':'freeze','parent':first['design_id'],'sources':{'candidate.json':canonical(choice)}})
        status,value=f.request('/api/design-lab',{'action':'interfaces','files':['interface-bindings.json']})
        self.assertEqual(200,status,value);self.assertTrue(value['facts'][0]['value_verified'])

    def test_nested_eda_result_and_exact_response_fields(self):
        response={'id':'eda-fixed','status':'SUCCEEDED','result':{'stdout':canonical({'ok':True,'result':{'pins':[27,26],'device':None}}),
                    'receipt_path':'eda-receipts/eda-fixed.json','receipt_sha256':'a'*64}}
        bridge=self.f.app.engineering.responses
        out=bridge.wrap(self.f.owner,response)
        self.assertEqual([27,26],out['native']['result']['pins'])
        self.assertNotIn('stdout',out['result'])
        ref=out['_response'];view=bridge.view(self.f.owner,{'response_id':ref['response_id'],
                            'response_sha256':ref['sha256'],'fields':['result.stdout']})
        self.assertEqual(response['result']['stdout'],view['fields']['result.stdout'])

    def test_help_cache_real_command_route_pins_cli_and_preserves_operations(self):
        f=self.f
        with patch.object(f.app.engineering,'authorize'), patch('bfworld.agentlab.eda_cli.subprocess.run',return_value=subprocess.CompletedProcess([],0,'Exact CLI help','')) as invoked:
            values=[]
            for operation in ('first-help','second-help'):
                status,value=f.request('/api/eda-cli',{'action':'command','argv':['sch','read','--help'],
                    'operation_id':operation,'candidate_id':f.view['working_design'],'candidate_revision':f.view['revision'],
                    'decision_use':'Read current command contract'})
                self.assertEqual(200,status,value);self.assertEqual('SUCCEEDED',value['status'],value)
                values.append(value)
            self.assertEqual(1,invoked.call_count)
            self.assertFalse(values[0]['result']['help_cache']['hit']);self.assertTrue(values[1]['result']['help_cache']['hit'])
            self.assertNotEqual(values[0]['id'],values[1]['id'])

    def test_prepare_delivery_real_entry_idempotent_conflict_and_changed_source(self):
        f=self.f;assembly=f.app.assemblies.get(f.owner)
        project={'manifest':f.project,'sources':{'model.cir':(f.workspace/'project/model.cir').read_text()}}
        job={'id':'eng-current','owner':f.owner,'engine':'engineering-project','status':'SUCCEEDED',
             'parameters':{'project_path':'project/project.json'},'project':project,'project_sha256':identity(project),
             'assembly':{'revision':assembly['revision']},'assembly_hashes':assembly['hashes'],
             'result':{'kind':'spice','readback_passed':True,'project_sha256':identity(project)}}
        report={'paper_id':'P01','source_identity':'original-source','assembly_revision':assembly['revision'],
                'assembly_physical_hash':assembly['hashes']['physical_hash']}
        (f.workspace/'native-report.json').write_text(canonical(report));(f.workspace/'delivery').mkdir()
        (f.workspace/'delivery/UNVERIFIED.md').write_text('Current unresolved conditions')
        choice={**f.choice,'files':f.choice['files']+['native-report.json','delivery/UNVERIFIED.md'],'selected_jobs':['eng-current']}
        with patch.object(f.app.engineering,'get',return_value=job):
            design=pc.handle(self.lab,f.owner,{'action':'freeze','parent':f.view['working_design'],
                            'sources':{'candidate.json':canonical(choice)}})
            body={'action':'prepare_delivery','operation_id':'actual-metadata','design_id':design['design_id'],
                  'engineering_jobs':['eng-current'],'files':['delivery/UNVERIFIED.md'],'eda_receipts':[],
                  'report_path':'native-report.json','unresolved_gates':['power']}
            original_install=package.install
            def interrupted(*args,**kwargs):
                original_install(*args,**kwargs)
                raise RuntimeError('Injected exit before protected receipt')
            with patch.object(package,'install',interrupted), self.assertRaisesRegex(RuntimeError,'protected receipt'):
                pc.handle(self.lab,f.owner,body)
            status,value=f.request('/api/design-lab',body)
            self.assertEqual(200,status,value);self.assertEqual(0,value['engineering_source_edits'])
            status,retry=f.request('/api/design-lab',body);self.assertEqual(200,status,retry);self.assertEqual(value,retry)
            status,error=f.request('/api/design-lab',{**body,'unresolved_gates':['new']})
            self.assertEqual(400,status,error);self.assertIn('CONFLICT',canonical(error))
            (f.workspace/'project/model.cir').write_text('changed input')
            status,error=f.request('/api/design-lab',body)
            self.assertEqual(400,status,error);self.assertIn('INPUT_CHANGED',canonical(error))

    def test_delivery_defaults_consume_only_frozen_pi_selection_and_preserve_explicit_subset(self):
        f=self.f;assembly=f.app.assemblies.get(f.owner)
        project={'manifest':f.project,'sources':{'model.cir':(f.workspace/'project/model.cir').read_text()}}
        job={'id':'eng-current','owner':f.owner,'engine':'engineering-project','status':'SUCCEEDED',
             'parameters':{'project_path':'project/project.json'},'project':project,'project_sha256':identity(project),
             'assembly':{'revision':assembly['revision']},'assembly_hashes':assembly['hashes'],
             'result':{'kind':'spice','readback_passed':True,'project_sha256':identity(project)}}
        report={'paper_id':'P01','source_identity':'original-source','assembly_revision':assembly['revision'],
                'assembly_physical_hash':assembly['hashes']['physical_hash']}
        (f.workspace/'native-report.json').write_text(canonical(report));(f.workspace/'delivery').mkdir()
        (f.workspace/'delivery/UNVERIFIED.md').write_text('Unresolved current conditions')
        (f.workspace/'delivery/manifest.json').write_text('{}')
        (f.workspace/'unselected.txt').write_text('Never auto-discover workspace files')
        receipts=f.workspace/'eda-receipts';receipts.mkdir()
        receipt={'job_id':'eda-selected','owner':f.owner,'project':'original-native-project','status':'SUCCEEDED'}
        (receipts/'eda-selected.json').write_text(canonical(receipt))
        (receipts/'eda-unselected.json').write_text(canonical({**receipt,'job_id':'eda-unselected'}))
        choice={**f.choice,'files':f.choice['files']+['native-report.json','delivery/UNVERIFIED.md','delivery/manifest.json'],
                'selected_jobs':['eng-current'],'eda_receipts':['eda-selected']}
        with patch.object(f.app.engineering,'get',return_value=job) as get_job:
            design=pc.handle(self.lab,f.owner,{'action':'freeze','parent':f.view['working_design'],
                    'sources':{'candidate.json':canonical(choice)}})
            body={'action':'prepare_delivery','operation_id':'selection-defaults','design_id':design['design_id'],
                  'unresolved_gates':['power']}
            status,value=f.request('/api/design-lab',body);self.assertEqual(200,status,value)
            status,retry=f.request('/api/design-lab',body);self.assertEqual(200,status,retry);self.assertEqual(value,retry)
            manifest=json.loads((f.workspace/'delivery/manifest.json').read_text())
            self.assertEqual(set(design['files'])-{'delivery/manifest.json'},{x['path'] for x in manifest['files']})
            self.assertEqual(['eng-current'],[x['job_id'] for x in manifest['trusted_jobs']])
            self.assertEqual(['eda-selected'],[x['job_id'] for x in manifest['eda_receipts']])
            self.assertEqual({'eng-current'},{call.args[1] for call in get_job.call_args_list})
            current=pc.handle(self.lab,f.owner,{'action':'freeze','parent':design['design_id'],
                              'sources':{'candidate.json':canonical(choice)}})
            explicit={**body,'design_id':current['design_id'],'operation_id':'explicit-subset',
                      'files':['delivery/UNVERIFIED.md'],'eda_receipts':[]}
            status,value=f.request('/api/design-lab',explicit);self.assertEqual(200,status,value)
            manifest=json.loads((f.workspace/'delivery/manifest.json').read_text())
            self.assertEqual([],manifest['eda_receipts'])
            self.assertNotIn('plan.md',{x['path'] for x in manifest['files']})
            status,error=f.request('/api/design-lab',{**explicit,'operation_id':'malformed','files':None})
            self.assertEqual(400,status,error);self.assertIn('SELECTION_LISTS_REQUIRED',canonical(error))


if __name__=='__main__':unittest.main()
