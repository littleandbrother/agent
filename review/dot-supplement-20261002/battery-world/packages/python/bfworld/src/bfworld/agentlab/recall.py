"""Append-only message recall with actual Pi session branching and durable recovery."""
import json
import secrets
import subprocess
import threading
import time
from . import launcher
from .store import canonical

class Recall:
    def __init__(self,chat):
        self.chat=chat;self.store=chat.store;self.home=chat.home
        with self.store.connect() as db:
            db.executescript("CREATE TABLE IF NOT EXISTS chat_recalls(id TEXT PRIMARY KEY,conversation TEXT,message_id TEXT,from_seq INTEGER,to_seq INTEGER,messages TEXT,status TEXT,result TEXT,error TEXT);")
            db.execute("UPDATE chat_recalls SET status='FAILED',error='RECALL_INTERRUPTED_RETRY' WHERE status='PENDING'")

    def pending(self,cid):
        with self.store.connect() as db:return db.execute("SELECT 1 FROM chat_recalls WHERE conversation=? AND status='PENDING'",(cid,)).fetchone() is not None

    def request(self,cid,mid):
        self.chat.get(cid)
        with self.chat.lock:
            with self.store.connect() as db:
                old=db.execute('SELECT * FROM chat_recalls WHERE conversation=? AND message_id=? ORDER BY rowid DESC LIMIT 1',(cid,mid)).fetchone()
                if old and old['status']=='COMPLETE':return dict(old)
                if self.pending(cid):raise ValueError('RECALL_PENDING')
                messages=[dict(x) for x in db.execute("SELECT * FROM chat_messages WHERE conversation=? AND status NOT IN ('WITHDRAWN','CANCELLED') ORDER BY created",(cid,))]
                target=next((m for m in messages if m['id']==mid),None)
                if not target:raise ValueError('MESSAGE_NOT_FOUND')
                event=db.execute('SELECT seq FROM chat_events WHERE conversation=? AND source=?',(cid,mid)).fetchone()
                if not event:raise ValueError('MESSAGE_EVENT_MISSING')
                rid=old['id'] if old else 'recall-'+secrets.token_hex(8)
                db.execute('INSERT OR REPLACE INTO chat_recalls VALUES(?,?,?,?,?,?,?,NULL,NULL)',(rid,cid,mid,event['seq'],None,canonical(messages),'PENDING'))
                for m in messages[messages.index(target):]:db.execute("UPDATE chat_messages SET status='RECALLING' WHERE id=?",(m['id'],))
            self.chat.stop(cid);self.chat.state(cid,'RECALLING')
            threading.Thread(target=self.apply,args=(rid,),daemon=True).start()
        return {'id':rid,'status':'PENDING','text':target['text']}

    def apply(self,rid):
        with self.store.connect() as db:record=dict(db.execute('SELECT * FROM chat_recalls WHERE id=?',(rid,)).fetchone())
        cid=record['conversation']
        try:
            until=time.monotonic()+30
            while cid in self.chat.starting or cid in self.chat.processes:
                if time.monotonic()>until:raise ValueError('RECALL_STOP_TIMEOUT')
                time.sleep(.05)
            workspace=self.home/'participants'/cid
            result={'status':'not_delivered'}
            if workspace.exists():
                command=[launcher.NODE,str(launcher.PI/'packages/bf-agent/dist/chat-recall.js')]
                payload={'workspace':str(workspace),'message_id':record['message_id'],'operation':rid,'messages':json.loads(record['messages'])}
                proc=subprocess.run(command,input=canonical(payload),capture_output=True,text=True,timeout=15,env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin'})
                if proc.returncode:raise ValueError('RECALL_CONTEXT_MISMATCH: '+proc.stderr[-300:])
                result=json.loads(proc.stdout)
            with self.chat.lock:
                with self.store.connect() as db:
                    last=db.execute('SELECT MAX(seq) FROM chat_events WHERE conversation=?',(cid,)).fetchone()[0]
                    db.execute("UPDATE chat_messages SET status='WITHDRAWN' WHERE conversation=? AND status='RECALLING'",(cid,))
                    db.execute("UPDATE chat_recalls SET status='COMPLETE',to_seq=?,result=? WHERE id=?",(last,canonical(result),rid))
                self.chat.event(cid,rid,{'type':'message_withdrawn','message_id':record['message_id'],'from_seq':record['from_seq'],'to_seq':last,'completed_effects_retained':True})
                self.chat.state(cid,'IDLE')
        except Exception as exc:
            with self.store.connect() as db:db.execute("UPDATE chat_recalls SET status='FAILED',error=? WHERE id=?",(str(exc)[:600],rid))
            self.chat.state(cid,'INTERRUPTED',str(exc)[:600])

    def list(self,cid):
        with self.store.connect() as db:return [dict(r) for r in db.execute('SELECT id,message_id,status,error FROM chat_recalls WHERE conversation=?',(cid,))]
