"""Reference isolation, evidence boundaries and real coupled solver controls."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from bfworld.agentlab.server import Workbench, handler
from bfworld.agentlab import references, event_design, event_measurement
from bfworld.agentlab.store import identity


def fixture(force=2):
    # Generic apparatus calibration. Never copied into the participant workspace.
    return {'schema_version':'bf-event-design-v1',
        'mechanics':{'mass_kg':.001,'stiffness_n_m':100,'damping_ns_m':.01,'coupling_n_v':.0005,'piezo_capacitance_f':1e-7},
        'drive':{'kind':'force-pwl','trajectory':[[0,0],[.01,force],[.011,0],[.25,0]]},
        'storage':{'capacitance_f':47e-6,'initial_v':0,'leakage_a':1e-7},
        'power':{'start_v':4,'stop_v':3.4,'output_v':3.3,'efficiency':.8,'quiescent_a':1e-7},
        'diode':{'saturation_a':1e-9,'emission_coefficient':1.5,'series_ohm':2,'junction_capacitance_f':1e-12,'transit_time_s':1e-9},
        'workload':{'origin':'estimate','firmware_sha256':None,'idle_current_a':1e-6,'tx_stage':'tx',
                    'stages':[{'name':'boot','duration_s':.002,'current_a':.003},{'name':'tx','duration_s':.002,'current_a':.008}]},
        'simulation':{'duration_s':.25,'step_s':1e-5},
        'requirements':{'action_time_s':0,'deadline_s':.2,'max_deflection_m':.03},
        'provenance':[{'parameter':k,'origin':'assumption','source':'generic numerical test fixture','locator':k,'conditions':'not a target product or measurement'} for k in ('mechanics','drive','storage','power','workload','diode','requirements')]}


class ReferenceEvent(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
        (self.home/'paid-window-closed.json').write_text('{}')
        self.app=Workbench(self.home/'state');self.owner='pi-ref-test'

    def tearDown(self):
        self.app.stop.set();self.app.thread.join(3);self.app.lock.close();self.tmp.cleanup()

    def test_public_fetch_denies_private_dns_and_credentials(self):
        for ip in ('127.0.0.1','10.0.0.1','169.254.169.254','::1'):
            with patch.object(socket,'getaddrinfo',return_value=[(None,None,None,None,(ip,443))]):
                with self.assertRaisesRegex(ValueError,'PRIVATE_NETWORK'):references.public_target('https://example.org/data')
        for url in ('file:///etc/passwd','https://user:secret@example.org','http://x.local','http://example.org:8768'):
            with self.assertRaises(ValueError):references.public_target(url)

    def test_http_measurement_operator_boundary_and_disabled_reference_tool(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        token=self.app.store.issue('unprivileged')
        try:
            for route,body in [('/api/measurements/import',{}),('/api/references',{'action':'fetch','url':'https://example.org'})]:
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+route,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
                self.assertEqual(403,err.exception.code)
            self.assertEqual([],self.app.references.projection('unprivileged')['records'])
        finally:server.shutdown();server.server_close()

    def test_redirect_rechecks_public_target(self):
        class Response:
            status=302
            def getheader(self,name,default=None):return 'http://127.0.0.1/private' if name=='Location' else default
        from unittest.mock import MagicMock
        connection=MagicMock();connection.getresponse.return_value=Response()
        public=references.urlsplit('http://example.org/source')
        with patch.object(references,'public_target',side_effect=[(public,80,['93.184.216.34']),ValueError('REFERENCE_PRIVATE_NETWORK_DENIED')]) as resolve,patch.object(references.socket,'create_connection'),patch.object(references.http.client,'HTTPConnection',return_value=connection):
            with self.assertRaisesRegex(ValueError,'PRIVATE_NETWORK'):references.fetch_public('http://example.org/source')
            self.assertEqual('http://127.0.0.1/private',resolve.call_args.args[0])

    def test_source_read_scoped_hashed_and_adoption_is_not_validation(self):
        with patch.object(references,'fetch_public',return_value=(b'<html><p>Reference board</p></html>',{'content_type':'text/html','final_url':'https://example.org/ref'})):
            src=self.app.references.action(self.owner,{'action':'fetch','url':'https://example.org/ref'})
        self.assertIn('Reference board',self.app.references.read(self.owner,src['id'])['text'])
        with self.assertRaises(PermissionError):self.app.references.read('foreign',src['id'])
        with patch.object(self.app.products,'context',return_value={'proposal':{'revision':2}}):
            body={'reference_id':src['id'],'proposal_revision':2,**{k:'explicit test interpretation' for k in ('application','locator','assumptions','differences','required_checks')}}
            adopted=self.app.references.adopt(self.owner,body)
            self.assertEqual('participant-interpretation-not-validation',adopted['evidence_level'])
            with self.assertRaisesRegex(ValueError,'STALE'):self.app.references.adopt(self.owner,{**body,'proposal_revision':1})
        self.app.references.blob(src['text_sha256']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'TAMPER'):self.app.references.read(self.owner,src['id'])

    def test_failure_retained_and_measured_label_cannot_self_certify(self):
        with patch.object(references,'fetch_public',side_effect=ValueError('HTTP_403')):
            with self.assertRaises(ValueError):self.app.references.action(self.owner,{'action':'fetch','url':'https://example.org'})
        self.assertEqual('failure',self.app.references.projection(self.owner)['records'][0]['kind'])
        root=self.home/'participants'/self.owner;root.mkdir(parents=True)
        spec=fixture();spec['workload'].update(origin='measured',measurement_sha256='0'*64)
        (root/'event.json').write_text(json.dumps(spec))
        with self.assertRaisesRegex(ValueError,'OPERATOR_IMPORT'):event_design.request(self.app,self.owner,{'spec_path':'event.json'})
        with self.assertRaisesRegex(ValueError,'PATH_DENIED'):event_design.request(self.app,self.owner,{'spec_path':'../outside.json'})

    def test_invalid_inputs_and_explicit_receiver_events(self):
        for change in ('provenance','trajectory','power'):
            s=fixture()
            if change=='provenance':s['provenance']=[]
            if change=='trajectory':s['drive']['trajectory']=[[],[1,2]]
            if change=='power':s['power']['stop_v']=2
            with self.assertRaises(ValueError):event_design.validate(s)
        a=[{'event_id':'a','time_s':1},{'event_id':'b','time_s':2}]
        r=[{'event_id':'a','time_s':1.1},{'event_id':'a','time_s':1.2},{'event_id':'unknown','time_s':3}]
        result=event_measurement.evaluate_receiver(a,r,.5)
        self.assertFalse(result['passed']);self.assertEqual(['b'],result['misses']);self.assertEqual(1,len(result['duplicates']))
        self.assertFalse(event_measurement.evaluate_receiver([],[],.5)['passed'])

    def test_measurement_requires_binary_binding_and_exact_profile(self):
        body={'instrument':'test fixture (not physical)','hardware_id':'fixture','captured_at':'2026-09-24',
              'firmware_sha256':'0'*64,'csv':'time_s,current_a,voltage_v,stage\n0,0.01,3.3,tx\n0.001,0.01,3.3,tx\n0.002,0.01,3.3,tx\n'}
        with self.assertRaisesRegex(ValueError,'COMPILED_BINARY'):event_measurement.import_capture(self.app,self.owner,body)
        binary=self.home/'fixture.bin';binary.write_bytes(b'fixture binary; not deployed')
        body['firmware_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
        job={'id':'fixture','status':'SUCCEEDED','engine':'mcu-firmware','result':{'artifacts':[{'name':'firmware.bin','sha256':body['firmware_sha256']}]}}
        with patch.object(self.app.engineering,'jobs',return_value=[job]),patch.object(self.app.engineering,'artifact',return_value=binary):
            capture=event_measurement.import_capture(self.app,self.owner,body)
        workload={'measurement_sha256':capture['measurement_sha256'],'firmware_sha256':body['firmware_sha256'],
                  'stages':[{k:s[k] for k in ('name','duration_s','current_a')} for s in capture['stages']]}
        event_measurement.verified_load(self.home,self.owner,workload)
        workload['stages'][0]['current_a']*=.5
        with self.assertRaisesRegex(ValueError,'PROFILE_MISMATCH'):event_measurement.verified_load(self.home,self.owner,workload)

    def test_event_operation_binds_snapshot_not_only_filename(self):
        root=self.home/'participants'/self.owner;root.mkdir(parents=True)
        s=fixture();path=root/'event.json';path.write_text(json.dumps(s))
        body={'engine':'event-transient','operation_id':'first','parameters':{'spec_path':'event.json'}}
        with patch.object(self.app.engineering,'run'):
            job=self.app.engineering.submit(self.owner,body)
            self.assertEqual(identity(s),job['event_spec_sha256'])
            self.assertEqual(job['id'],self.app.engineering.submit(self.owner,body)['id'])
            s['storage']['capacitance_f']*=2;path.write_text(json.dumps(s))
            with self.assertRaisesRegex(ValueError,'CONFLICT'):self.app.engineering.submit(self.owner,body)

    @unittest.skipUnless(event_design.SPICE.is_file(),'ngspice not installed')
    def test_actual_ngspice_positive_negative_controls_and_coupling(self):
        reports=[]
        for name,force in [('strong',2),('weak',.001)]:
            spec=fixture(force);directory=self.home/name;directory.mkdir()
            job={'event_spec':spec,'event_spec_sha256':identity(spec),'id':name,'owner':self.owner}
            result=event_design.run(self.app.engineering,job,directory,time.monotonic()+60)
            reports.append(result)
            self.assertFalse(result['hardware_verified']);self.assertTrue(result['checks']['coarse_fine_agreement'])
            self.assertTrue(result['checks']['transient_complete'])
        self.assertTrue(reports[0]['computational_checks_passed'],reports[0]['fine'])
        self.assertFalse(reports[1]['checks']['simulated_event_in_deadline'])
        # A high electrical load must change mechanical response through piezo reaction.
        s=fixture();s['power'].update(start_v=.8,stop_v=.5,output_v=.4)
        s['workload']['idle_current_a']=.01
        directory=self.home/'feedback';directory.mkdir()
        (directory/'test.cir').write_text(event_design.netlist(s,1e-5,'out.tsv'))
        subprocess.run([str(event_design.SPICE),'-n','-b','test.cir'],cwd=directory,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=40,check=True)
        rows=event_design.read_channels(directory/'out.tsv');summary=event_design.summarize(s,rows)
        self.assertTrue(summary['checks']['transient_complete'])
        self.assertGreater(abs(summary['peak_deflection_m']-reports[0]['fine']['peak_deflection_m']),1e-7)


if __name__=='__main__':unittest.main()
