import copy
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E

from bfworld.agentlab.store import canonical, identity
from bfworld.agentlab.design_lab.report_assets import verify_input, check_author, connected_circuits, energy_ledger, native_svg_xy
from bfworld.agentlab.design_lab.repository_reports import check_build, document_schema
from bfworld.agentlab.design_lab.repository import file_hash


class ReportCase(unittest.TestCase):
    def test_pcb_markers_follow_the_native_top_and_bottom_view_transforms(self):
        root=E.fromstring('<svg><g transform="translate(5 3)"><g id="l-top-copper" transform="translate(0 70) scale(1 -1)"/><g id="l-bottom-copper" transform="translate(40 70) scale(-1 -1)"/></g></svg>')
        self.assertEqual(native_svg_xy(root,'l-top-copper',33,47),(38,26))
        self.assertEqual(native_svg_xy(root,'l-bottom-copper',33,47),(12,26))
        with self.assertRaisesRegex(ValueError,'NATIVE_LAYER_MISSING'):
            native_svg_xy(root,'missing',33,47)

    def test_energy_report_changes_with_actual_voltage_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);c=folder/'sources/candidate/project-chain';c.mkdir(parents=True)
            (c/'interface-params.json').write_text(json.dumps({'sece':{'g_se_s':1e-5},'storage':{'c_store_f':1e-4,'r_leak_ohm':1e6}}))
            (c/'chain_joint.cir').write_text('Iload mcu_rail 0 PWL(0 0.001 1 0.001)\n')
            job=folder/'sources/jobs/existing';job.mkdir(parents=True)
            (job/'project-trace.raw').write_text('unit-test RAW identity')
            channels={'time':[0,1],'v(storage_rail)':[4,3],'v(mcu_rail)':[2,-2],
                      'v(teng_rect)':[5,5],'v(teng_oc)':[6,6],'i(bvoc)':[-.001,-.001],
                      'v(supply_1v8)':[1.8,.8]}
            bad=energy_ledger(folder,channels)
            self.assertEqual(bad['negative_mcu_samples'],1)
            self.assertAlmostEqual(bad['load_port_absorbed_J'],0)
            self.assertAlmostEqual(bad['minimum_supply_V'],.8)
            channels['v(mcu_rail)'][1]=1
            clean=energy_ledger(folder,channels)
            self.assertEqual(clean['negative_mcu_samples'],0)
            self.assertIn('No negative MCU-rail',clean['conclusion'])
            self.assertAlmostEqual(clean['load_port_absorbed_J'],.0015)

    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        c=self.root/'input/sources/candidate';(c/'native').mkdir(parents=True);(c/'fw').mkdir()
        (c/'fw/main.c').write_text('void boot(void) {}\nvoid sample(void) {}\nvoid notify(void) {}\nvoid disconnect(void) {}')
        parts=[]
        for ref,x in [('R1',200),('R2',500),('C1',800)]:
            parts.append({'componentType':'part','designator':ref,'primitiveId':ref,'x':x,'y':100,'manufacturerId':'value',
                          'bbox':{'minX':x-10,'maxX':x+10,'minY':95,'maxY':105},
                          'pins':[{'pinNumber':'1','pinName':'1','net':'signal','noConnected':False,'x':x-20,'y':100,'rotation':180},
                                  {'pinNumber':'2','pinName':'2','net':'GND','noConnected':False,'x':x+20,'y':100,'rotation':0}]})
        (c/'native/schematic-readback.json').write_text(canonical({'result':{'components':parts}}))
        previews=self.root/'input/sources/previews';previews.mkdir()
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 500">'
        for part in parts:svg+=f'<g c_partid="part"><g id="{part["primitiveId"]}-pin"><path d="M{part["x"]-20} -100 h40"/></g></g>'
        (previews/'schematic.svg').write_text(svg+'</svg>')
        assets=[]
        for p in (self.root/'input/sources').rglob('*'):
            if p.is_file():assets.append({'system_commit':'SC-test','local_path':str(p.relative_to(self.root/'input')),'sha256':file_hash(p)})
        self.value={'system':{'id':'SC-test','validations':{'firmware':'PASS'}},'assets':assets}
        self.value['report_id']='RP-'+identity(self.value)
        (self.root/'input/report-input.json').write_text(canonical(self.value))

    def firmware(self):
        return {'participants':[{'id':x,'label':x} for x in ('mcu','cdc','ble','pc')],
                'messages':[{'from':'mcu','to':'cdc','label':'event','time':'condition','kind':kind,
                             'source':{'path':'fw/main.c','symbol':'sample'}}
                            for kind in ['start','sample','notify','error','disconnect']+['sample']*7],
                'explanations':['actual source events']}

    def test_input_hash_and_candidate_tampering_rejected(self):
        verify_input(self.root/'input')
        p=self.root/'input/sources/candidate/fw/main.c';p.write_text('stale')
        with self.assertRaisesRegex(ValueError,'ASSET_HASH'):verify_input(self.root/'input')

    def test_sequence_requires_all_branches_and_current_source(self):
        d=self.firmware();check_author(d,'firmware',self.value,self.root/'input')
        bad=copy.deepcopy(d);bad['messages'][0]['source']['symbol']='old_missing_function'
        with self.assertRaisesRegex(ValueError,'SOURCE_LOCATOR_STALE'):check_author(bad,'firmware',self.value,self.root/'input')
        bad=copy.deepcopy(d);bad['messages'][3]['kind']='sample'
        with self.assertRaisesRegex(ValueError,'BRANCHES_REQUIRED'):check_author(bad,'firmware',self.value,self.root/'input')

    def test_connected_diagram_uses_native_symbols_and_all_pins(self):
        power={'circuit_groups':[{'id':'all','title':'actual circuit','refs':['R1','R2','C1'],'notes':['actual']} ]}
        graph=connected_circuits(self.root/'input',power,self.root/'out')
        self.assertTrue(graph['graph_equal']);self.assertEqual(6,graph['pin_count']);self.assertEqual(3,graph['components'])
        svg=E.parse(self.root/'out/all.svg');paths=[p for p in svg.getroot().iter() if p.tag.endswith('path') and p.get('data-net')=='signal']
        self.assertGreater(len(paths),3)  # real routed wires, not isolated labelled components
        signal=next(x for x in graph['groups'][0]['nets'] if x['net']=='signal')
        self.assertEqual(2,len(signal['routes']))

    def test_full_sheet_wires_real_cross_module_nets(self):
        power={'circuit_groups':[{'id':r,'title':r,'refs':[r],'notes':['actual']} for r in ('R1','R2','C1')]}
        graph=connected_circuits(self.root/'input',power,self.root/'out')
        self.assertEqual(1,len(graph['cross_module_wires']))
        self.assertEqual('signal',graph['cross_module_wires'][0]['net'])
        self.assertEqual(['R1','R2','C1'],graph['cross_module_wires'][0]['groups'])
        full=E.parse(self.root/'out/schematic-connected.svg')
        buses=[x for x in full.getroot() if x.tag.endswith('path') and x.get('data-net')=='signal']
        self.assertEqual(4,len(buses))

    def test_author_coverage_rejects_dropped_or_duplicate_part(self):
        d={'circuit_groups':[{'id':'a','title':'a','refs':['R1'],'notes':['a']},
                            {'id':'b','title':'b','refs':['R2'],'notes':['b']},
                            {'id':'c','title':'c','refs':['R2'],'notes':['c']} ]}
        with self.assertRaisesRegex(ValueError,'CIRCUIT_COVERAGE'):check_author(d,'power',self.value,self.root/'input')

    def test_quality_requires_build_and_detects_output_mutation(self):
        with self.assertRaisesRegex(ValueError,'REPORT_MISSING'):check_build(self.root,self.value)
        build=self.root/'builds/RB-unit';build.mkdir(parents=True);(build/'simple.pdf').write_bytes(b'fixture')
        (self.root/'authors').mkdir();record={'scope':'lead','sha256':'author-hash'};(self.root/'authors/lead.json').write_text(canonical(record))
        q={'system_commit':'SC-test','report_id':self.value['report_id'],'authors':{'lead':'author-hash'},'status':'PASS',
           'outputs':{'simple.pdf':{'sha256':file_hash(build/'simple.pdf')}}}
        (build/'quality.json').write_text(canonical(q));(self.root/'CURRENT-BUILD.json').write_text(canonical({'id':'RB-unit','quality_sha256':identity(q)}))
        check_build(self.root,self.value);(build/'simple.pdf').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'OUTPUT_TAMPER'):check_build(self.root,self.value)

    def test_tool_schema_and_example_share_required_identity(self):
        for scope in ('power','firmware','lead'):
            d=document_schema(scope);self.assertEqual(scope,d['example']['scope']);self.assertIn('system_commit',d['example']);self.assertIn('report_id',d['example'])
