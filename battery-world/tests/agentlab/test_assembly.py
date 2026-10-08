import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from bfworld.agentlab.server import Workbench
from bfworld.agentlab.assembly import validate, identities
from bfworld.agentlab.solar_companion import definition, changed
from bfworld.agentlab.product_energy import calculate, timeline


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'paid-window-closed.json').write_text('{}')
        self.app=Workbench(self.root/'state')
        self.owner=self.app.conversations.create('按假设设计无电池桌面陪伴器',None,'assembly-test')['id']
        self.source=self.app.conversations.detail(self.owner)['messages'][0]['id']

    def tearDown(self):
        self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.temp.cleanup()

    def write(self,p=None,rev=0,op='initial'):
        return self.app.assemblies.write(self.owner,{'source_message_id':self.source,'operation_id':op,'expected_revision':rev,'payload':p or definition()})

    def test_revision_conflict_idempotence_and_recalled_source(self):
        r=self.write();self.assertEqual(r,self.write())
        with self.assertRaisesRegex(ValueError,'REVISION_CONFLICT'):self.write(changed(definition(),width=100),op='stale')
        with self.assertRaisesRegex(ValueError,'OPERATION_CONFLICT'):self.write(changed(definition(),width=100))
        self.write(changed(definition(),width=100),1,'second')
        self.assertEqual(2,self.app.assemblies.get(self.owner)['revision'])
        with self.app.store.connect() as db:db.execute("UPDATE chat_messages SET status='WITHDRAWN' WHERE id=?",(self.source,))
        self.assertIsNone(self.app.assemblies.projection(self.owner)['current'])
        with self.assertRaisesRegex(ValueError,'SOURCE_MESSAGE_INVALID'):self.write(rev=2,op='recalled')

    def test_camera_negative_control_and_geometry_invalidation(self):
        p=definition();a=identities(p);b=identities(changed(p,camera=-35));c=identities(changed(p,width=100))
        self.assertNotEqual(a['definition_hash'],b['definition_hash'])
        for key in ('geometry_hash','physical_hash','energy_hash'):self.assertEqual(a[key],b[key])
        for key in ('geometry_hash','physical_hash'):self.assertNotEqual(a[key],c[key])
        self.assertEqual(c['energy_hash'],a['energy_hash'])
        v=copy.deepcopy(p);v['energy']['events_per_day']=1000
        self.assertNotEqual(identities(v)['energy_hash'],a['energy_hash'])

    def test_immutable_outputs_and_owner_isolation(self):
        self.write();base=self.root/'participants'/self.owner;base.mkdir(parents=True,exist_ok=True)
        f=base/'energy.json';f.write_text('{"unverified":true}')
        r=self.app.assemblies.register(self.owner,{'revision':1,'path':f.name,'kind':'energy'})
        f.write_text('changed');saved,_=self.app.assemblies.file(self.owner,r['id'])
        self.assertEqual('{"unverified":true}',saved.read_text())
        for bad in ('../secret','/etc/passwd','.pi/auth.json'):
            with self.assertRaises(PermissionError):self.app.assemblies.register(self.owner,{'revision':1,'path':bad})
        other=self.app.conversations.create('另一产品',None,'other')['id']
        with self.assertRaises(PermissionError):self.app.assemblies.file(other,r['id'])
        saved.write_text('corrupt')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):self.app.assemblies.file(self.owner,r['id'])

    def test_energy_negative_controls_and_parts(self):
        p=validate(definition());r=calculate(p['energy']);self.assertTrue(r['calculation_passed'])
        e={**p['energy'],'pv_power_mw':0};self.assertFalse(calculate(e)['checks']['daily_balance_positive'])
        e={**p['energy'],'leakage_ua':50};self.assertFalse(calculate(e)['calculation_passed'])
        e={**p['energy'],'capacitance_f':.1};self.assertFalse(calculate(e)['checks']['dark_interval_storage_sufficient'])
        p['parts']=[x for x in p['parts'] if x['role']!='solar'];p['allowed_contacts']=[x for x in p['allowed_contacts'] if 'solar' not in x];self.write(p)
        d=self.app.assemblies.projection(self.owner)
        self.assertIn('solar',d['checks'][0]['missing_roles']);self.assertFalse(d['digital_model_available']);self.assertFalse(d['engineering_verified'])

    def test_native_eda_netlist_delivery_preserves_bytes_and_private_path_boundary(self):
        self.write();base=self.root/'participants'/self.owner
        (base/'delivery').mkdir(parents=True,exist_ok=True)
        netlist=b'{"native":"EasyEDA Pro","nets":[]}'
        (base/'delivery/design.enet').write_bytes(netlist)
        record=self.app.assemblies.register(self.owner,{'revision':1,'path':'delivery/design.enet','kind':'electronics'})
        saved,_=self.app.assemblies.file(self.owner,record['id'])
        self.assertEqual(saved.read_bytes(),netlist)
        with self.assertRaises(PermissionError):
            self.app.assemblies.register(self.owner,{'revision':1,'path':'.easyeda/design.enet','kind':'electronics'})

    def test_invalid_round_geometry_and_contacts_rejected(self):
        p=definition();next(x for x in p['parts'] if x['id']=='supercap')['geometry']['size_mm'][1]=20
        with self.assertRaisesRegex(ValueError,'ROUND_DIMENSIONS'):validate(p)
        p=definition();p['allowed_contacts']=[['housing','forged']]
        with self.assertRaisesRegex(ValueError,'CONTACT_INVALID'):validate(p)

    def test_timeline_cold_dark_and_event_accounting(self):
        e=definition()['energy']
        cold=timeline(e,initial_v=0,seconds=3600)
        self.assertEqual(0,cold['accepted_events']);self.assertIsNone(cold['first_ready_s'])
        dark=timeline(e,light_scale=0)
        self.assertLess(dark['end_v'],e['v_high']);self.assertGreater(dark['unavailable_events']+dark['aborted_pulses'],0)
        fast=timeline({**e,'events_per_day':100000},seconds=100)
        self.assertEqual(115,fast['accepted_events']+fast['unavailable_events']+fast['aborted_pulses'])
        with self.assertRaisesRegex(ValueError,'HEADROOM'):calculate({**e,'v_high':3.5,'supply_v':3.6})

    def test_delivery_observer_rejects_absent_geometry_and_forged_files(self):
        goal={'required_roles':['housing','solar','storage','pcb'],'min_parts':10,'file_kinds':['source','document'],'max_continuations':3}
        empty=self.app.assemblies.set_goal(self.owner,{'goal':goal})
        self.assertFalse(empty['delivery']['passed']);self.assertIn('no_current_assembly',empty['delivery']['missing'])
        self.write();current=self.app.assemblies.projection(self.owner)
        self.assertIn('current_native_checks_not_passed',current['delivery']['missing'])
        self.assertIn('current_energy_screen_not_passed',current['delivery']['missing'])
        self.assertIn('missing_published_file:source',current['delivery']['missing'])
        self.assertEqual(3,current['delivery']['max_continuations'])

    def test_positive_daily_balance_cannot_hide_zero_successful_service_events(self):
        self.app.assemblies.set_goal(self.owner,{'goal':{'required_roles':['housing'],'min_parts':1,'file_kinds':['source'],'max_continuations':3}})
        current=self.write()
        energy={'calculation_passed':True,'scenarios':{'normal':{'accepted_events':0,'aborted_pulses':79}}}
        projected={'current':current,'digital_model_available':True,'jobs':[{'stale':False,'status':'SUCCEEDED','result':{'energy':energy}}],
                   'files':[{'stale':False,'integrity':True,'kind':'source'}]}
        observed=self.app.assemblies.observe_delivery(self.owner,projected)
        self.assertFalse(observed['passed'])
        self.assertIn('no_successful_service_event_in_normal_scenario',observed['missing'])
        energy['scenarios']['normal']['accepted_events']=1
        self.assertTrue(self.app.assemblies.observe_delivery(self.owner,projected)['passed'])
        self.app.assemblies.set_goal(self.owner,{'goal':{'required_roles':['housing'],'min_parts':1,'file_kinds':['source'],'max_continuations':3,'min_revision':2}})
        self.assertIn('requested_new_revision_not_published',self.app.assemblies.observe_delivery(self.owner,projected)['missing'])
        projected['current']={**current,'revision':2}
        self.assertTrue(self.app.assemblies.observe_delivery(self.owner,projected)['passed'])
        with self.assertRaisesRegex(ValueError,'PRODUCT_FILE_NOT_FOUND'):
            self.app.assemblies.register(self.owner,{'revision':1,'path':'does-not-exist.md','kind':'document'})

    def test_publication_requires_explicit_assembly_revision_and_is_idempotent(self):
        self.write();base=self.root/'participants'/self.owner;base.mkdir(parents=True,exist_ok=True)
        (base/'PRODUCT.md').write_text('Source-bound product report')
        for rev in [None,True,0,1.5]:
            with self.assertRaisesRegex(ValueError,'PRODUCT_FILE_REVISION_REQUIRED'):
                self.app.assemblies.register(self.owner,{'revision':rev,'path':'PRODUCT.md'})
        with self.assertRaisesRegex(ValueError,'PRODUCT_FILE_PATH_REQUIRED'):
            self.app.assemblies.register(self.owner,{'revision':1})
        body={'revision':1,'path':'PRODUCT.md','kind':'document'}
        self.assertEqual(self.app.assemblies.register(self.owner,body),self.app.assemblies.register(self.owner,body))
        with self.assertRaisesRegex(ValueError,'PRODUCT_FILE_KIND_CONFLICT'):
            self.app.assemblies.register(self.owner,{**body,'kind':'source'})
        self.assertEqual(1,len(self.app.assemblies.projection(self.owner)['files']))

    def test_new_delivery_file_cannot_be_satisfied_by_old_document(self):
        current=self.write()
        goal={'required_roles':['housing'],'min_parts':1,'file_kinds':['document'],'max_continuations':3,'required_paths':['delivery/reviewed.md']}
        self.app.assemblies.set_goal(self.owner,{'goal':goal})
        energy={'calculation_passed':True,'scenarios':{'normal':{'accepted_events':1}}}
        p={'current':current,'digital_model_available':True,'jobs':[{'stale':False,'status':'SUCCEEDED','result':{'energy':energy}}],
           'files':[{'stale':False,'integrity':True,'kind':'document','source':'delivery/old.md'}]}
        expected='missing_published_path:delivery/reviewed.md'
        self.assertIn(expected,self.app.assemblies.observe_delivery(self.owner,p)['missing'])
        p['files'][0]['source']='delivery/reviewed.md'
        self.assertTrue(self.app.assemblies.observe_delivery(self.owner,p)['passed'])
        for field in ['stale','integrity']:
            p['files'][0][field]=field=='stale'
            self.assertIn(expected,self.app.assemblies.observe_delivery(self.owner,p)['missing'])
            p['files'][0][field]=field=='integrity'
        for path in ['/etc/test.md','../reviewed.md','.pi/test.json','delivery/./reviewed.md','delivery/x.exe']:
            with self.assertRaisesRegex(ValueError,'DELIVERY_GOAL_PATHS'):
                self.app.assemblies.set_goal(self.owner,{'goal':{**goal,'required_paths':[path]}})
