"""Durable operator conversations. Pi owns responses; the UI never fabricates them."""
import contextlib
import json
import re
import secrets
import threading
import time
from pathlib import Path
from .store import canonical
from . import experiments, launcher
from .concurrency import conversation_slot, MAX_CONVERSATIONS
from .recovery import INTERACTIVE_WALL_SECONDS
from . import budget_policy

class Conversations:
    def __init__(self, app):
        self.app=app;self.store=app.store;self.home=self.store.root.parent
        self.lock=threading.RLock();self.processes={};self.starting=set();self.port=8768
        self._trace_cursors={};self._trace_locks={}
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, operation TEXT UNIQUE, title TEXT, task_id TEXT, created REAL, updated REAL, status TEXT, harness TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS chat_messages(id TEXT PRIMARY KEY, conversation TEXT, operation TEXT, text TEXT, status TEXT, created REAL, UNIQUE(conversation,operation));
            CREATE TABLE IF NOT EXISTS chat_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, conversation TEXT, source TEXT, data TEXT, created REAL, UNIQUE(conversation,source));
            """)
            db.execute("UPDATE conversations SET status='INTERRUPTED',error='服务重启；已发送消息不会自动重发' WHERE status IN ('STARTING','RUNNING')")
            db.execute("UPDATE chat_messages SET status='UNKNOWN' WHERE status='SENT'")
        from .recall import Recall
        self.recalls=Recall(self)

    def get(self, cid):
        if not re.fullmatch(r'pi-chat-[a-f0-9]{16}',cid):raise ValueError('CONVERSATION_ID_INVALID')
        with self.store.connect() as db:row=db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone()
        if not row:raise ValueError('CONVERSATION_NOT_FOUND')
        return dict(row)

    def event(self,cid,source,data):
        with self.store.connect() as db:
            cursor=db.execute('INSERT OR IGNORE INTO chat_events(conversation,source,data,created) VALUES(?,?,?,?)',(cid,source,canonical(data),time.time()))
            return cursor.rowcount>0

    def events(self,cid,after=0):
        self.get(cid)
        with self.store.connect() as db:return [{'seq':r['seq'],'data':json.loads(r['data']),'time':r['created']} for r in db.execute('SELECT * FROM chat_events WHERE conversation=? AND seq>? ORDER BY seq LIMIT 2000',(cid,after))]

    def snapshot_events(self,cid):
        """Complete public history without replaying every historical token on reload.

        Raw events remain immutable and paginated through events()/developer Trace.
        The cursor is taken from the same read as the snapshot, so subsequent live
        events cannot fall into a gap between the history and the subscription.
        """
        self.get(cid)
        with self.store.connect() as db:
            rows=[{'seq':r['seq'],'data':json.loads(r['data']),'time':r['created']} for r in db.execute('SELECT seq,data,created FROM chat_events WHERE conversation=? ORDER BY seq',(cid,))]
        cursor=rows[-1]['seq'] if rows else 0
        if len(rows)<=2000:return rows,cursor
        complete={str(r['data'].get('id')) for r in rows if r['data']['type']=='message' and r['data'].get('message',{}).get('role')=='assistant'}
        projected=[];partials={}
        visible={'user_message','input_accepted','assistant_start','text_delta','tool_execution_start','tool_execution_end','message','turn_error','command_error','conversation_status','runtime_restored','product_record','message_withdrawn','turn_stopped','turn_complete','chat_idle','session_complete'}
        for row in rows:
            d=row['data'];kind=d['type'];key=str(d.get('id'))
            if kind not in visible:continue
            if kind in ('assistant_start','text_delta') and key in complete:continue
            if kind=='text_delta':
                if key in partials:partials[key]['data']['delta']+=d.get('delta','')
                else:
                    item={**row,'data':{**d,'projection':'combined_stream'}}
                    partials[key]=item;projected.append(item)
                continue
            if kind=='tool_execution_end':
                row={**row,'data':{k:v for k,v in d.items() if k in ('type','toolCallId','toolName','isError','time')}}
            elif kind=='message' and d.get('message',{}).get('role')=='toolResult':
                row={**row,'data':{**d,'message':{k:v for k,v in d['message'].items() if k in ('role','toolCallId','toolName','isError')}}}
            projected.append(row)
        return projected,cursor

    def state(self,cid,status,error=None):
        with self.store.connect() as db:db.execute('UPDATE conversations SET status=?,error=?,updated=? WHERE id=?',(status,error,time.time(),cid))
        self.event(cid,'status-'+secrets.token_hex(8),{'type':'conversation_status','status':status,'error':error})

    def create(self,text,task_id,operation,folder_id=None,attachments=None,model_cap_usd=None,preflight=None,defer_dispatch=False):
        self.validate_text(text,operation)
        self.app.products.validate_attachments(attachments or [])
        if model_cap_usd is not None and (type(model_cap_usd) not in (int,float) or not 0<model_cap_usd<=.05):raise ValueError('MODEL_CAP_INVALID')
        if attachments and task_id:raise ValueError('PRODUCT_ATTACHMENT_DISCOVERY_ONLY')
        if task_id:experiments.task(task_id)
        if task_id and not task_id.startswith('dev-'):raise PermissionError('TASK_DENIED')
        if folder_id:self.app.organization.folder(folder_id)
        with self.lock:
            with self.store.connect() as db:
                old=db.execute('SELECT * FROM conversations WHERE operation=?',(operation,)).fetchone()
                if old:
                    initial=db.execute('SELECT text FROM chat_messages WHERE conversation=? ORDER BY created LIMIT 1',(old['id'],)).fetchone()
                    if old['task_id']!=task_id or initial['text']!=text or self.app.organization.metadata(old['id'])['folder_id']!=folder_id:raise ValueError('OPERATION_CONFLICT')
                    cap=db.execute('SELECT max_usd FROM owner_model_caps WHERE owner=?',(old['id'],)).fetchone()
                    if (cap['max_usd'] if cap else None)!=model_cap_usd:raise ValueError('OPERATION_CONFLICT')
                    self.app.products.check_creation(old['id'],attachments)
                    return dict(old)
                cid='pi-chat-'+secrets.token_hex(8);now=time.time()
                db.execute('INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?)',(cid,operation,text.strip().splitlines()[0][:60],task_id,now,now,'IDLE',None,None))
                if model_cap_usd is not None:db.execute('INSERT INTO owner_model_caps VALUES(?,?)',(cid,model_cap_usd))
            if not task_id:self.app.products.create(cid,attachments)
            if folder_id:self.app.organization.change_entry(cid,{'action':'move','folder_id':folder_id})
            if preflight:preflight(cid)
            self.send(cid,text,operation,dispatch=not defer_dispatch)
            return self.get(cid)

    @staticmethod
    def validate_text(text,operation):
        if not isinstance(text,str) or not text.strip() or len(text)>12000:raise ValueError('MESSAGE_REQUIRED_MAX_12000')
        if not isinstance(operation,str) or not 1<=len(operation)<=100:raise ValueError('OPERATION_REQUIRED')

    def send(self,cid,text,operation,dispatch=True):
        self.get(cid);self.validate_text(text,operation)
        if self.app.organization.metadata(cid)['deleted']:raise ValueError('CONVERSATION_DELETED')
        if self.recalls.pending(cid):raise ValueError('RECALL_PENDING')
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM chat_messages WHERE conversation=? AND status='RECALLING'",(cid,)).fetchone():raise ValueError('RECALL_RETRY_REQUIRED')
        with self.lock:
            with self.store.connect() as db:
                old=db.execute('SELECT * FROM chat_messages WHERE conversation=? AND operation=?',(cid,operation)).fetchone()
                if old:
                    if old['text']!=text:raise ValueError('OPERATION_CONFLICT')
                    return dict(old)
                mid='msg-'+secrets.token_hex(8)
                db.execute('INSERT INTO chat_messages VALUES(?,?,?,?,?,?)',(mid,cid,operation,text,'QUEUED',time.time()))
            self.app.provider.recovery.issue(cid,mid)
            self.app.provider.recovery.refresh_grant(cid)
            self.event(cid,mid,{'type':'user_message','id':mid,'text':text})
            if not dispatch:
                self.event(cid,mid+'-staged',{'type':'conversation_staged','reason':'Operator prepares tool bindings and immutable inputs before dispatch.'})
                with self.store.connect() as db:return dict(db.execute('SELECT * FROM chat_messages WHERE id=?',(mid,)).fetchone())
            proc=self.processes.get(cid)
            if proc and proc.poll() is None:self.drain(cid,proc)
            elif cid not in self.starting:self.start(cid)
            with self.store.connect() as db:return dict(db.execute('SELECT * FROM chat_messages WHERE id=?',(mid,)).fetchone())

    def readiness(self,owner=None):
        model=self.app.provider.status(owner); reasons=[]
        from .runtime_config import DEVELOPMENT_PROFILE
        if DEVELOPMENT_PROFILE is not None and not all(DEVELOPMENT_PROFILE['capabilities'][k] for k in ['model','agent']):
            reasons.append('DEVELOPMENT_EXECUTION_NOT_ENABLED')
        with self.store.connect() as db:
            if (self.home/'paid-window-closed.json').exists() and not budget_policy.unbounded_time(db,owner):reasons.append('PAID_WINDOW_CLOSED')
            if self.app.provider.recovery.unknown_blockers(db,owner):reasons.append('PROVIDER_USAGE_UNKNOWN_STOP')
            unbounded=bool(budget_policy.for_owner(db,owner or 'pi-chat-new'))
        if any(r['error']=='PROVIDER_RESERVATION_EXCEEDED' for r in model['requests']):reasons.append('PROVIDER_RESERVATION_EXCEEDED')
        # Interactive wall time is granted only by a new explicit user message.
        # The original batch window remains unchanged for noninteractive owners.
        if not unbounded and model['upper_bound_usd']>=model['limits']['total_usd']-.005:reasons.append('MODEL_USD_BUDGET')
        used_tokens=sum(json.loads(r['usage'])['total_tokens'] for r in model['requests'] if r['usage'])
        if not unbounded and used_tokens>=model['limits']['max_tokens']:reasons.append('MODEL_TOKEN_BUDGET')
        return {'local':'connected','model':'blocked' if reasons else 'ready_for_dispatch','reasons':reasons,
                'upper_bound_usd':model['upper_bound_usd'],'limit_usd':None if unbounded else model['limits']['total_usd'],
                'token_limit':None if unbounded else model['limits']['max_tokens'],'unbounded':unbounded,'expires':model['limits']['expires'],
                'concurrency':{'limit':MAX_CONVERSATIONS,'active':sorted(self.starting)},
                'interactive_wall_seconds':INTERACTIVE_WALL_SECONDS,'network':'not_probed','note':'本地连接不代表模型响应；发送后以真实事件显示进展。'}

    def gate(self,owner=None):
        status=self.readiness(owner)
        if status['reasons']:raise ValueError(status['reasons'][0])

    def start(self,cid):
        from .runtime_config import require_capability
        require_capability('agent')
        if hasattr(self.app,'design_lab'):
            if self.app.design_lab.repository.bound(cid):
                from .design_lab.repository_controller import start
                start(self.app.design_lab.repository,cid)
                return
            with self.store.connect() as db:design_task=db.execute('SELECT 1 FROM design_tasks WHERE owner=?',(cid,)).fetchone()
            if design_task:
                from .design_lab.paper_candidate import bound
                if bound(self.app.design_lab,cid):
                    raise ValueError('PAPER_CANDIDATE_USE_ORIGINAL_QUEUE')
                from .design_lab.controller import start
                start(self.app.design_lab,cid)
                return
        try:
            self.gate(cid)
            with self.store.connect() as db:
                lease=self.app.provider.recovery.lease(db,cid)
                if not lease or lease['expires'] is not None and time.time()>lease['expires']:raise ValueError('CHAT_TURN_WALL_BUDGET')
        except ValueError as exc:self.state(cid,'BLOCKED',str(exc));return
        self.starting.add(cid);self.state(cid,'STARTING')
        threading.Thread(target=self.run,args=(cid,),daemon=True).start()

    def reconcile_blocks(self):
        if self.readiness()['reasons']:return
        with self.store.connect() as db:
            rows=list(db.execute("SELECT id FROM conversations WHERE status='BLOCKED' AND error IN ('PROVIDER_USAGE_UNKNOWN_STOP','MODEL_WALL_BUDGET')"))
        for row in rows:
            self.state(row['id'],'IDLE')
            self.event(row['id'],'runtime-restored-v1',{'type':'runtime_restored','text':'模型连接已恢复。已保存的任务仍保留；发送一条新消息即可继续。'})

    def retry(self,cid):
        self.get(cid)
        with self.lock:
            if cid in self.starting or cid in self.processes:return self.get(cid)
            with self.store.connect() as db:
                pending=db.execute("SELECT 1 FROM chat_messages WHERE conversation=? AND status='QUEUED'",(cid,)).fetchone()
            if not pending:raise ValueError('NO_QUEUED_MESSAGES')
            self.start(cid)
        return self.get(cid)

    def drain(self,cid,proc):
        if self.get(cid)['status'] not in ('RUNNING','STARTING'):return
        with self.store.connect() as db:
            rows=list(db.execute("SELECT * FROM chat_messages WHERE conversation=? AND status='QUEUED' ORDER BY created",(cid,)))
        for row in rows:
            # Persist dispatch before writing. Unacknowledged input is never auto-retried.
            with self.store.connect() as db:db.execute("UPDATE chat_messages SET status='SENT' WHERE id=?",(row['id'],))
            try:proc.stdin.write((canonical({'type':'message','id':row['id'],'text':row['text']})+'\n').encode());proc.stdin.flush()
            except (BrokenPipeError,ValueError):
                self.state(cid,'INTERRUPTED','消息发送中断，请检查对话后再补充消息');break

    def ingest(self,cid,execution_state=True):
        # A native watcher and a final drain may overlap. Serialize each owner,
        # without holding the shared conversation lock while reading its trace.
        with self.lock:guard=self._trace_locks.setdefault(cid,threading.RLock())
        with guard:self._ingest_append(cid,execution_state)

    def _ingest_append(self,cid,execution_state):
        path=self.home/'sessions'/cid/'trace.jsonl'
        if not path.exists():return
        signature,offset,index,witness=self._trace_cursors.get(cid,(None,0,0,b''))
        with path.open('rb') as stream:
            stat=path.stat();current=(stat.st_dev,stat.st_ino)
            if signature is not None and (signature!=current or stat.st_size<offset):
                raise ValueError('TRACE_HISTORY_CHANGED')
            stream.seek(max(0,offset-len(witness)))
            if stream.read(len(witness))!=witness:raise ValueError('TRACE_HISTORY_CHANGED')
            stream.seek(offset)
            suffix=stream.read()
        boundary=suffix.rfind(b'\n')+1
        if not boundary:return
        lines=suffix[:boundary].splitlines(keepends=True)
        for i,raw in enumerate(lines,index):
            line=raw.decode('utf-8')
            try:data=json.loads(line)
            except json.JSONDecodeError:data=None
            if data is not None:self._ingest_event(cid,i,data,execution_state)
            # Commit only after the event and its state effects complete. A
            # partial UTF8/JSON line stays unread until its terminating newline.
            offset+=len(raw)
            with path.open('rb') as stream:
                stream.seek(max(0,offset-64));witness=stream.read(min(offset,64))
            self._trace_cursors[cid]=(current,offset,i+1,witness)

    def _ingest_event(self,cid,i,data,execution_state):
            # Exact context is in developer mode, not the conversation feed.
            if not self.event(cid,'trace-'+str(i),data):return
            if data.get('type')=='input_accepted':
                with self.store.connect() as db:db.execute("UPDATE chat_messages SET status='ACCEPTED' WHERE id=? AND conversation=? AND status='SENT'",(data['message_id'],cid))
            # Recovery must first archive unseen historical events. A previous
            # process's error/idle must never terminate the newly launched one.
            if not execution_state:return
            # A queued follow-up can start inside the same Pi process after a
            # failed turn. The previous turn's error is historical, not the
            # state of this new response. Keep the error event in the trace.
            if data.get('type')=='assistant_start' and self.get(cid)['status']=='FAILED':
                self.state(cid,'RUNNING')
            if data.get('type')=='message' and data.get('message',{}).get('stopReason')=='error':
                self.state(cid,'FAILED',data['message'].get('errorMessage','MODEL_RESPONSE_ERROR'))
            # Pi can recover an intermediate truncated tool write in the same
            # turn. Only its terminal turn error marks that turn failed.
            if data.get('type')=='turn_error':
                self.state(cid,'FAILED',data.get('error','PI_TURN_ERROR'))
            if data.get('type')=='chat_idle':
                with self.lock:
                    if self.get(cid)['status'] not in ('FAILED','BLOCKED','PAUSED'):self.state(cid,'RECALLING' if self.recalls.pending(cid) else 'IDLE')
                    proc=self.processes.get(cid)
                    if proc and proc.poll() is None:
                        try:proc.stdin.write(b'{"type":"close"}\n');proc.stdin.flush()
                        except (BrokenPipeError,ValueError):pass

    def run(self,cid):
        finished=threading.Event();watcher=None;receipt=None;locks=contextlib.ExitStack()
        try:
            lock=locks.enter_context(conversation_slot(self.home,cid))
            self.app.provider.recovery.refresh_grant(cid)
            conv=self.get(cid);harness=conv['harness']
            resume=(self.home/'sessions'/cid/'receipt.json').exists()
            if self.app.organization.metadata(cid)['deleted']:return
            context=self.app.organization.context(cid)
            if context['folder_id']:
                active=context['harness_revision']
                source=self.app.developer.resolve(active) if active else launcher.PI/'packages/bf-harness'
            elif harness:source=Path(harness)
            else:
                active=self.app.developer.active()['revision']
                source=self.app.developer.resolve(active) if active else launcher.PI/'packages/bf-harness'
            product=self.app.products.exists(cid)
            harness=str(launcher.freeze(source,label='PRODUCT' if product else 'CHAT2',home_root=self.home,app_entry='chat-product.js' if product else 'chat-v2.js'))
            self.app.organization.bind(cid,context)
            with self.store.connect() as db:db.execute('UPDATE conversations SET harness=? WHERE id=?',(harness,cid))
            def ready(proc):
                with self.lock:
                    self.processes[cid]=proc
                    if self.recalls.pending(cid) or self.app.organization.metadata(cid)['deleted']:
                        proc.stdin.write(b'{"type":"close"}\n');proc.stdin.flush()
                    else:self.state(cid,'RUNNING');self.drain(cid,proc)
            def watch():
                while not finished.wait(.1):self.ingest(cid)
                self.ingest(cid)
            def expire(proc):
                with self.lock:
                    with self.store.connect() as db:lease=self.app.provider.recovery.lease(db,cid)
                    if lease and (lease['expires'] is None or time.time()<lease['expires']):return False
                    # New messages after this decision remain QUEUED and are
                    # started after the old process finishes saving its state.
                    self.state(cid,'STOPPING')
                    return True
            self.ingest(cid,execution_state=False)
            watcher=threading.Thread(target=watch,daemon=True);watcher.start()
            receipt=launcher.launch(Path(harness),conv['task_id'],label=cid,store_root=self.store.root,resume=resume,
                           service_port=self.port,on_process=ready,home_root=self.home,process_lock=lock,shared_context=context,chat_upgrade=True,product=self.app.products.exists(cid),on_expire=expire)
        except ValueError as exc:
            if str(exc) in ('PI_SESSION_ALREADY_RUNNING','PI_BATCH_ALREADY_RUNNING','PI_CONVERSATION_CAPACITY'):
                self.state(cid,'BLOCKED',str(exc))
            else:self.state(cid,'FAILED',str(exc)[:500])
        except Exception as exc:self.state(cid,'FAILED',str(exc)[:500])
        finally:
            finished.set()
            if watcher:watcher.join()
            locks.close()
            with self.lock:
                # Drain Pi's final abort/idle events before publishing the
                # launcher's terminal state. A delayed watcher must not turn
                # an intentional deadline pause back into a failed turn.
                if receipt:
                    if receipt.get('deadline_shutdown'):self.state(cid,'PAUSED',receipt['error'])
                    elif receipt['exit_code']:self.state(cid,'FAILED',receipt.get('error') or 'PI_PROCESS_FAILED')
                    elif self.get(cid)['status']=='RUNNING':self.state(cid,'IDLE')
                self.processes.pop(cid,None);self.starting.discard(cid)
                with self.store.connect() as db:
                    db.execute("UPDATE chat_messages SET status='UNKNOWN' WHERE conversation=? AND status='SENT'",(cid,))
                    pending=db.execute("SELECT 1 FROM chat_messages WHERE conversation=? AND status='QUEUED'",(cid,)).fetchone()
                if pending and not self.recalls.pending(cid) and not self.app.organization.metadata(cid)['deleted'] and self.get(cid)['status'] in ('IDLE','PAUSED'):self.start(cid)

    def stop(self,cid):
        self.get(cid)
        with self.lock:
            for job in self.store.jobs(cid):
                if job['status'] in ('QUEUED','RUNNING'):self.store.cancel(cid,job['id'])
            proc=self.processes.get(cid)
            if proc and proc.poll() is None:
                proc.stdin.write(b'{"type":"close"}\n');proc.stdin.flush()
                self.state(cid,'STOPPING')
            else:self.state(cid,'IDLE')
        return self.get(cid)

    def raw_list(self):
        with self.store.connect() as db:items=[dict(r) for r in db.execute('SELECT * FROM conversations ORDER BY updated DESC')]
        known={c['id'] for c in items}
        for path in (self.home/'sessions').glob('*/receipt.json'):
            r=json.loads(path.read_text())
            if r['owner'] in known or r.get('dry_run') or 'preflight' in r['owner']:continue
            items.append({'id':r['owner'],'title':r['task_id']+' · '+r['harness']['label']+(' · 改进' if r['mode']=='improve' else ''),
                          'task_id':r['task_id'],'created':r['started'],'updated':r.get('ended',r['started']),
                          'status':r['status'],'legacy':True})
        return sorted(items,key=lambda c:c['updated'],reverse=True)

    def list(self,deleted=False):return self.app.organization.decorate(self.raw_list(),deleted)

    def detail(self,cid):
        conv=self.get(cid)
        with self.store.connect() as db:
            messages=[dict(r) for r in db.execute('SELECT * FROM chat_messages WHERE conversation=? ORDER BY created',(cid,))]
        try:execution=self.app.session_detail(cid,include_events=False)
        except (FileNotFoundError,KeyError):execution=None
        meta=self.app.organization.metadata(cid)
        events,cursor=self.snapshot_events(cid)
        return {**conv,**meta,'title':meta['title'] or conv['title'],'recalls':self.recalls.list(cid),'shared_context':self.app.organization.context(cid),'messages':messages,'events':events,'event_cursor':cursor,'execution':execution,'jobs':self.store.jobs(cid),'product':self.app.products.projection(cid),'readiness':self.readiness(cid)}
