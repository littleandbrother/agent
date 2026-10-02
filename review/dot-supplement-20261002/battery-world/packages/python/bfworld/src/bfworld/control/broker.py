"""Serial durable experiment broker; retry identity is distinct from replication.

The local development broker is not a security sandbox. A formal participant
must see only this API in a separate filesystem/container, never this database.
"""
from __future__ import annotations
import fcntl
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import asdict,replace
from pathlib import Path
from bfworld.coupled.engine import Design,Reference,execute
from bfworld.coupled.artifacts import seal_run,verify_bundle
from bfworld.kernel.canonical import canonical_hash,file_hash

RANGES={'capacitance_f':(.0001,.01),'esr_ohm':(0,100),'start_v':(1.81,5),'release_s':(0,1.2),
        'tx_power_w':(.001,.1),'model_threshold':(1,1000),'flash_bytes':(0,1000000),'sram_bytes':(0,1000000),'clamp_v':(1.81,8)}
PROFILES={'nominal':Reference(),'surge':replace(Reference(),surge_after_s=.9,surge_multiplier=7),
          'no-receiver':replace(Reference(),receiver_loss=True)}

def design_from_request(values:dict)->Design:
    if not isinstance(values,dict) or set(values)-set(RANGES):raise ValueError('unknown or unauthorized design field')
    for key,value in values.items():
        if key=='clamp_v' and value is None:continue
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):raise ValueError('finite numeric design required')
        lo,hi=RANGES[key]
        if not lo<=value<=hi:raise ValueError('design parameter outside declared domain: '+key)
        if key in ('model_threshold','flash_bytes','sram_bytes') and not isinstance(value,int):raise ValueError('integer design parameter required')
    return Design(**values)

class Broker:
    def __init__(self,root:Path,budget:int=100):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'control.sqlite';self.budget=budget
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS experiments (key TEXT PRIMARY KEY,request_hash TEXT NOT NULL,request TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,result_path TEXT,cpu_s REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS submissions (key TEXT PRIMARY KEY,content_hash TEXT NOT NULL,receipt TEXT NOT NULL);''')
            db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)',('budget',str(budget)))
            self.budget=int(db.execute('SELECT value FROM metadata WHERE name=?',('budget',)).fetchone()[0])
    def connection(self):
        db=sqlite3.connect(self.db,timeout=30);db.row_factory=sqlite3.Row
        db.execute('PRAGMA synchronous=FULL');return db
    def status(self)->dict:
        with self.connection() as db:
            entries=[dict(row) for row in db.execute('SELECT key,status,attempts,result_path,cpu_s FROM experiments ORDER BY rowid')]
        return {'schema_version':'control-status-v1','experiment_budget':self.budget,'reserved_experiments':len(entries),
                'remaining_experiments':self.budget-len(entries),'attempts':sum(e['attempts'] for e in entries),
                'recorded_cpu_s':sum(e['cpu_s'] for e in entries),'cpu_accounting':'completed executions only; interrupted CPU is unknown and not reported as zero',
                'external_model_calls':0,'experiments':entries,'formal_agent_study':False,'participant_sandbox':False}
    def request(self,request:dict,*,crash_at:str|None=None)->dict:
        if not isinstance(request,dict) or set(request)-{'idempotency_key','design','profile','prediction','replication_id','update_type'}:raise ValueError('unknown request field')
        key=request.get('idempotency_key','')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',key):raise ValueError('invalid idempotency key')
        design=design_from_request(request.get('design',{}));profile=request.get('profile','nominal')
        if profile not in PROFILES:raise ValueError('unknown public profile; reference mutation not permitted')
        update=request.get('update_type','design-revision')
        if update not in ('design-revision','world-model-revision','workflow-revision','replication'):raise ValueError('unknown update type')
        if update=='replication' and not request.get('replication_id'):raise ValueError('scientific replication requires explicit identity')
        normalized={**request,'design':asdict(design),'profile':profile,'update_type':update,
                    'engine_source_hash':file_hash(Path(__file__).resolve().parents[1]/'coupled/engine.py')}
        encoded=json.dumps(normalized,sort_keys=True,allow_nan=False)
        if len(encoded)>16384:raise ValueError('request exceeds size limit')
        identity=canonical_hash(normalized)
        # Process lock serializes reservation, execution, seal and commit; SQLite
        # transaction commits each recoverable boundary to disk.
        with (self.root/'broker.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with self.connection() as db:
                existing=db.execute('SELECT * FROM experiments WHERE key=?',(key,)).fetchone()
                if existing and existing['request_hash']!=identity:raise ValueError('idempotency conflict: new request needs new identity')
                if existing and existing['status']=='complete':return self._receipt(dict(existing),reused=True)
                if not existing:
                    if db.execute('SELECT COUNT(*) FROM experiments').fetchone()[0]>=self.budget:raise ValueError('experiment budget exhausted')
                    db.execute('INSERT INTO experiments(key,request_hash,request,status) VALUES (?,?,?,?)',(key,identity,encoded,'reserved'))
            if crash_at=='reservation':os._exit(91)
            with self.connection() as db:db.execute('UPDATE experiments SET attempts=attempts+1,status=? WHERE key=?',('running',key))
            started=time.process_time()
            run=execute(design,PROFILES[profile]);root=seal_run(self.root/'runs',run)
            cpu=time.process_time()-started
            if crash_at=='seal':os._exit(92)
            with self.connection() as db:
                db.execute('UPDATE experiments SET status=?,result_path=?,cpu_s=cpu_s+? WHERE key=?',('complete',str(root.relative_to(self.root)),cpu,key))
            return self.read(key)
    def _receipt(self,row:dict,*,reused:bool=False)->dict:
        root=self.root/row['result_path'];verify_bundle(root)
        run=json.loads((root/'run.json').read_text())
        return {'schema_version':'control-receipt-v1','experiment_id':row['key'],'request_hash':row['request_hash'],
          'request':json.loads(row['request']),'run':run,'attempts':row['attempts'],'reused_committed_result':reused,
          'cost':{'experiment_reservations':1,'execution_attempts':row['attempts'],'recorded_cpu_s':row['cpu_s'],
                  'interrupted_cpu_s':None if row['attempts']>1 else 0,'external_model_calls':0},
          'actor':'API client; agent identity not asserted by broker'}
    def read(self,key:str)->dict:
        with self.connection() as db:row=db.execute('SELECT * FROM experiments WHERE key=?',(key,)).fetchone()
        if row is None or row['status']!='complete':raise ValueError('experiment is missing or not committed')
        return self._receipt(dict(row))
    def recover(self)->list[dict]:
        with self.connection() as db:pending=[dict(r) for r in db.execute('SELECT * FROM experiments WHERE status!=?',('complete',))]
        receipts=[]
        for row in pending:
            request=json.loads(row['request']);request.pop('engine_source_hash')
            receipts.append(self.request(request))
        return receipts
    def submit(self,key:str,content_hash:str)->dict:
        receipt=self.read(key);run=receipt['run']
        if run['content_hash']!=content_hash:raise ValueError('submission identity mismatch')
        result={'experiment_id':key,'content_hash':content_hash,'physical_mission_pass':run['physical_mission_pass']['value'],
                'evidence_admissible':False,'verified_mission_success':False,'status':'recorded-unqualified',
                'reason':'No independent mission qualification receipt is present.'}
        with self.connection() as db:db.execute('INSERT OR IGNORE INTO submissions VALUES (?,?,?)',(key,content_hash,json.dumps(result,sort_keys=True)))
        return result
