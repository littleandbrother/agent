"""Conformance with the actual Go daemon type, not a JSON-only mock."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from bfworld.agentlab import runtime_config


class ActualNativeProtocolCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        cls.root=Path(cls.folder.name)
        source=runtime_config.EDA_PROTOCOL_ROOT/'internal/protocol/envelope.go'
        cls.protocol_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        module='github.com/zhoushoujianwork/easyeda-agent'
        (cls.root/'go.mod').write_text('module '+module+'/conformance-probe\n\ngo 1.26.3\n\nrequire '+module+' v0.0.0\nreplace '+module+' => '+str(runtime_config.EDA_PROTOCOL_ROOT)+'\n')
        (cls.root/'main.go').write_text('''package main
import("encoding/json"; "os"; p "github.com/zhoushoujianwork/easyeda-agent/internal/protocol")
func main(){var raws []json.RawMessage; if err:=json.NewDecoder(os.Stdin).Decode(&raws);err!=nil{panic(err)}
 out:=[]map[string]any{};for _,raw:=range raws{var r p.Response;err:=json.Unmarshal(raw,&r)
 item:=map[string]any{"decoded":err==nil};if err==nil{item["id"]=r.ID;item["seq"]=r.Seq;item["ok"]=r.OK;if r.Error!=nil{item["code"]=r.Error.Code;item["detail"]=r.Error.Detail}};out=append(out,item)}
 if err:=json.NewEncoder(os.Stdout).Encode(out);err!=nil{panic(err)}}''')
        cls.env={**os.environ,'GOTOOLCHAIN':'local','GOWORK':'off','GOPROXY':'off'}
        cls.binary=cls.root/'decode'
        proc=subprocess.run([str(runtime_config.GO),'build','-mod=mod','-o',str(cls.binary),'.'],
            cwd=cls.root,env=cls.env,capture_output=True,text=True,timeout=60)
        if proc.returncode:raise RuntimeError('Actual Go protocol probe build failed: '+proc.stderr[-2000:])

    def decode(self, values):
        proc=subprocess.run([str(self.binary)],input=json.dumps(values),capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr)
        return json.loads(proc.stdout)

    def test_actual_go_type_rejects_historical_object_error_detail(self):
        old={'id':'failed-read','type':'response','version':'v1','ok':False,
             'error':{'code':'PRECONDITION_REFUSED','message':'not sent','detail':{'native_entered':False}}}
        self.assertFalse(self.decode([old])[0]['decoded'])

    def test_wire_normalization_retains_terminal_cause_and_dispatch_facts(self):
        adapter=runtime_config.REPO/'scripts/eda/native_connector.mjs'
        code='import {protocolResponse,nativeFailure} from '+json.dumps(adapter.as_uri())+''';
const error=new Error('readonly timeout');error.code='NATIVE_EXECUTION_UNKNOWN';
const errors=[nativeFailure(error,{action:'project.current'},{mutates:false}),
 {code:'PRECONDITION_REFUSED',message:'NATIVE_DIAGNOSTIC_BUSY_NOT_SENT',detail:{native_entered:false,native_write_dispatched:false}},
 {code:'NATIVE_EXECUTION_UNKNOWN',message:'entered write timeout',detail:'no replay'}];
console.log(JSON.stringify(errors.map((error,i)=>protocolResponse({id:'terminal-'+i,type:'response',version:'v1',ok:false,seq:i+1,seqAbandoned:0,error}))));'''
        proc=subprocess.run([str(runtime_config.NODE),'--input-type=module','-e',code],capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr);wire=json.loads(proc.stdout);decoded=self.decode(wire)
        self.assertTrue(all(x['decoded'] for x in decoded))
        self.assertEqual([x['id'] for x in decoded],['terminal-0','terminal-1','terminal-2'])
        self.assertEqual([x['seq'] for x in decoded],[1,2,3])
        self.assertEqual(decoded[0]['code'],'NATIVE_DIAGNOSTIC_TIMEOUT')
        self.assertFalse(json.loads(decoded[0]['detail'])['native_write_dispatched'])
        self.assertFalse(json.loads(decoded[1]['detail'])['native_entered'])
        self.assertEqual(decoded[2]['code'],'NATIVE_EXECUTION_UNKNOWN')
        source=runtime_config.EDA_PROTOCOL_ROOT/'internal/protocol/envelope.go'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),self.protocol_hash)
