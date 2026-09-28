"""Failure controls for real EDA transport; fixtures are never native-design evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from bfworld.agentlab.eda_mcp import MCPClient, MCPError
from bfworld.agentlab.jlceda import validate, guard, JLCEDA
from bfworld.agentlab.trace_analysis import analyze

BINDING={'project_uuid':'p','schematic_uuid':'s','pcb_uuid':'b','window_id':'w'}

class JLCEDATests(unittest.TestCase):
    def test_reject_ambiguous_or_nonfinite_routing(self):
        for p in ({'operation':'autoroute','nets':[]}, {'operation':'autoroute','nets':['GND'],'ignore_nets':['GND']},
                  {'operation':'tracks','tracks':[{'net':'a','layer':11,'x1_mm':0,'y1_mm':0,'x2_mm':1,'y2_mm':1,'width_mm':1}]},
                  {'operation':'components','components':[{'lcsc':'C25804','ref':'R1','x':float('nan'),'y':5}]},
                  {'operation':'inspect','code':'unsafe'}, {'operation':'components','document':'pcb'}, {'operation':'tracks','document':'schematic'}):
            with self.assertRaises(ValueError):validate(p)
        self.assertEqual('inspect',validate({'operation':'inspect'})['operation'])

    def test_guard_rejects_wrong_project_before_any_document_action(self):
        code=guard(BINDING,'pcb')+'return "mutated";'
        wrapper='''let opens=0;const eda={dmt_Project:{getCurrentProjectInfo:async()=>({uuid:'other'})},dmt_EditorControl:{openDocument:async()=>{opens++;return 'tab'}}};(async()=>{try{await (async()=>{CODE})();}catch(e){console.log(JSON.stringify({error:e.message,opens}))}})();'''.replace('CODE',code)
        r=subprocess.run(['node','-e',wrapper],capture_output=True,text=True,check=True)
        self.assertEqual({'error':'EDA_PROJECT_CHANGED','opens':0},json.loads(r.stdout))

    def test_guard_requires_active_document_identity(self):
        wrapper='''let mutated=false;const eda={dmt_Project:{getCurrentProjectInfo:async()=>({uuid:'p'})},dmt_EditorControl:{openDocument:async()=> 'tab',activateDocument:async()=>true},dmt_SelectControl:{getCurrentDocumentInfo:async()=>({uuid:'wrong',parentProjectUuid:'p'})}};(async()=>{try{await (async()=>{CODE mutated=true;})();}catch(e){console.log(JSON.stringify({error:e.message,mutated}))}})();'''.replace('CODE',guard(BINDING,'pcb'))
        r=subprocess.run(['node','-e',wrapper],capture_output=True,text=True,check=True)
        self.assertEqual({'error':'EDA_DOCUMENT_MISMATCH','mutated':False},json.loads(r.stdout))

    def test_stdio_transport_errors_preserved_and_audited(self):
        script="""import sys,json
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r:continue
 result={'protocolVersion':'2025-06-18'} if r['method']=='initialize' else {'isError':True,'content':[{'type':'text','text':'native DRC unavailable'}]}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
"""
        receipts=[]
        with MCPClient(receipts.append,command=[sys.executable,'-u','-c',script]) as c:
            with self.assertRaisesRegex(MCPError,'DRC unavailable'):c.call('eda_execute',{})
        self.assertEqual(['SUCCEEDED','FAILED'],[r['status'] for r in receipts])
        self.assertTrue(receipts[-1]['response']['result']['isError'])
        self.assertGreaterEqual(receipts[-1]['duration_ms'],0)

    def test_undefined_drc_does_not_become_pass(self):
        # Execute the actual adapter-emitted JS through a minimal API fixture.
        class Fake:
            def __init__(self,*args):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,code,window,timeout=30):
                pre="""const eda={dmt_Project:{getCurrentProjectInfo:async()=>({uuid:'p'})},dmt_EditorControl:{openDocument:async()=> 'tab',activateDocument:async()=>true},dmt_SelectControl:{getCurrentDocumentInfo:async()=>({uuid:'b',parentProjectUuid:'p'})},pcb_PrimitiveComponent:{getAll:async()=>[]},pcb_Drc:{check:async()=>undefined},pcb_ManufactureData:{getNetlistFile:async()=>undefined},sys_FileManager:{getDocumentSource:async()=> 'native-fixture'}};"""
                out=subprocess.run(['node','-e',pre+'(async()=>{console.log(JSON.stringify(await (async()=>{'+code+'})()))})()'],capture_output=True,text=True,check=True)
                return json.loads(out.stdout)
        adapter=object.__new__(JLCEDA)
        job={'owner':'fixture','id':'fixture-job','binding':BINDING,'parameters':{'operation':'check','document':'pcb'}}
        with tempfile.TemporaryDirectory() as d,patch('bfworld.agentlab.jlceda.MCPClient',Fake):
            r=adapter.run(job,Path(d))
            self.assertEqual('unavailable',r['drc']['status']);self.assertFalse(r['product_verified'])

    def test_import_acknowledgement_requires_native_confirmation(self):
        class Acknowledged:
            def __init__(self,*args):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,*args):return {'source':'native-fixture','saved':True,'components':[]}
        adapter=object.__new__(JLCEDA)
        job={'owner':'fixture','id':'fixture-job','binding':{**BINDING,'schematic_root_uuid':'root'},'parameters':{'operation':'import_pcb'}}
        with tempfile.TemporaryDirectory() as d,patch('bfworld.agentlab.jlceda.MCPClient',Acknowledged):
            r=adapter.run(job,Path(d))
            self.assertEqual('NEEDS_ACTION',r['_job_status'])
            self.assertFalse(r['import_verified']);self.assertTrue(r['requires_ui_action'])

if __name__=='__main__':unittest.main()
