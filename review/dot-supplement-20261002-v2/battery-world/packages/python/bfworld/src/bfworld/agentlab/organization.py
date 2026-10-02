"""Operator-owned sidebar and shared folder context; scientific records stay untouched."""
import json
import secrets
import time
from .store import canonical

TOOLS = ["read", "edit", "write", "bash", "bf_experiment", "bf_job", "bf_inspect_run", "bf_submit", "bf_memory", "bf_engineering", "bf_reference"]
DEFAULT = {"memory": "", "prompt": "", "tools": TOOLS, "harness_revision": None}

class Organization:
    def __init__(self, app):
        self.app=app;self.store=app.store
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS chat_folders(id TEXT PRIMARY KEY,name TEXT,position INTEGER,config TEXT,revision INTEGER,deleted INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sidebar_entries(id TEXT PRIMARY KEY,title TEXT,folder_id TEXT,deleted INTEGER DEFAULT 0,updated REAL);
            CREATE TABLE IF NOT EXISTS folder_revisions(folder_id TEXT,revision INTEGER,config TEXT,created REAL,actor TEXT,PRIMARY KEY(folder_id,revision));
            CREATE TABLE IF NOT EXISTS chat_contexts(owner TEXT PRIMARY KEY,folder_id TEXT,config TEXT,revision INTEGER,created REAL);
            CREATE TABLE IF NOT EXISTS chat_context_history(id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT,folder_id TEXT,config TEXT,revision INTEGER,created REAL);
            """)

    def folder(self, fid, deleted=False):
        with self.store.connect() as db:r=db.execute('SELECT * FROM chat_folders WHERE id=?',(fid,)).fetchone()
        if not r or (r['deleted'] and not deleted):raise ValueError('FOLDER_NOT_FOUND')
        out=dict(r);out['config']=json.loads(out['config']);return out

    def folders(self, deleted=False):
        with self.store.connect() as db:return [self.folder(r['id'],True) for r in db.execute('SELECT id FROM chat_folders WHERE deleted=? ORDER BY position,name',(int(deleted),))]

    @staticmethod
    def name(value):
        if not isinstance(value,str) or not 1<=len(value.strip())<=80:raise ValueError('NAME_REQUIRED_MAX_80')
        return value.strip()

    def create_folder(self,name):
        name=self.name(name);fid='folder-'+secrets.token_hex(8)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            position=db.execute('SELECT COALESCE(MAX(position),0)+1 FROM chat_folders').fetchone()[0]
            db.execute('INSERT INTO chat_folders VALUES(?,?,?,?,0,0)',(fid,name,position,canonical(DEFAULT)))
            db.execute('INSERT INTO folder_revisions VALUES(?,0,?,?,?)',(fid,canonical(DEFAULT),time.time(),'operator'))
        return self.folder(fid)

    def configure(self,fid,config,expected,actor='operator'):
        if not isinstance(config,dict) or set(config)!=set(DEFAULT):raise ValueError('FOLDER_CONFIG_INVALID')
        if any(not isinstance(config[k],str) or len(config[k])>16000 for k in ('memory','prompt')):raise ValueError('FOLDER_TEXT_TOO_LONG')
        names=config['tools']
        if not isinstance(names,list) or not names or any(n not in TOOLS for n in names) or len(names)!=len(set(names)):raise ValueError('TOOL_SELECTION_INVALID')
        if config['harness_revision']:self.app.developer.resolve(config['harness_revision'])
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT * FROM chat_folders WHERE id=? AND deleted=0',(fid,)).fetchone()
            if not r:raise ValueError('FOLDER_NOT_FOUND')
            if type(expected) is not int or expected!=r['revision']:raise ValueError('FOLDER_CHANGED_REFRESH')
            revision=expected+1
            db.execute('UPDATE chat_folders SET config=?,revision=? WHERE id=?',(canonical(config),revision,fid))
            db.execute('INSERT INTO folder_revisions VALUES(?,?,?,?,?)',(fid,revision,canonical(config),time.time(),actor))
        return self.folder(fid)

    def busy(self,cid):return cid in self.app.conversations.starting or cid in self.app.conversations.processes

    def mutate_folder(self,fid,body):
        folder=self.folder(fid,True);action=body['action']
        if action=='configure':return self.configure(fid,body['config'],body['expected_revision'])
        with self.app.conversations.lock:
            with self.store.connect() as db:
                if action=='rename':db.execute('UPDATE chat_folders SET name=? WHERE id=?',(self.name(body['name']),fid))
                elif action=='reorder':
                    ordered=[x['id'] for x in self.folders()];i=ordered.index(fid);j=max(0,min(len(ordered)-1,i+(-1 if body.get('direction')=='up' else 1)))
                    ordered[i],ordered[j]=ordered[j],ordered[i]
                    for pos,key in enumerate(ordered):db.execute('UPDATE chat_folders SET position=? WHERE id=?',(pos,key))
                elif action=='delete':
                    members=list(db.execute('SELECT id FROM sidebar_entries WHERE folder_id=?',(fid,)))
                    if any(self.busy(r['id']) for r in members):raise ValueError('FOLDER_HAS_RUNNING_SESSION')
                    db.execute('UPDATE sidebar_entries SET folder_id=NULL WHERE folder_id=?',(fid,))
                    db.execute('UPDATE chat_folders SET deleted=1 WHERE id=?',(fid,))
                elif action=='restore':db.execute('UPDATE chat_folders SET deleted=0 WHERE id=?',(fid,))
                else:raise ValueError('FOLDER_ACTION_INVALID')
        return self.folder(fid,True)

    def metadata(self,cid):
        with self.store.connect() as db:r=db.execute('SELECT * FROM sidebar_entries WHERE id=?',(cid,)).fetchone()
        return dict(r) if r else {'id':cid,'title':None,'folder_id':None,'deleted':0}

    def decorate(self,items,deleted=False):
        out=[]
        for item in items:
            meta=self.metadata(item['id'])
            if bool(meta['deleted'])!=deleted:continue
            out.append({**item,'title':meta['title'] or item['title'],'folder_id':meta['folder_id'],'deleted':bool(meta['deleted'])})
        return out

    def change_entry(self,cid,body):
        # Verify against known conversations/receipts; never allow arbitrary filesystem paths.
        if not any(x['id']==cid for x in self.app.conversations.raw_list()):raise ValueError('CONVERSATION_NOT_FOUND')
        with self.app.conversations.lock:
            meta=self.metadata(cid);action=body['action']
            if action=='rename':meta['title']=self.name(body['name'])
            elif action=='move':
                if self.busy(cid):raise ValueError('CONVERSATION_BUSY_STOP_FIRST')
                fid=body.get('folder_id')
                if fid:self.folder(fid)
                meta['folder_id']=fid or None
            elif action=='delete':
                if cid.startswith('pi-chat-'):
                    with self.store.connect() as db:db.execute("UPDATE chat_messages SET status='CANCELLED' WHERE conversation=? AND status='QUEUED'",(cid,))
                    self.app.conversations.stop(cid)
                meta['deleted']=1
            elif action=='restore':meta['deleted']=0
            else:raise ValueError('SIDEBAR_ACTION_INVALID')
            with self.store.connect() as db:db.execute('INSERT OR REPLACE INTO sidebar_entries VALUES(?,?,?,?,?)',(cid,meta['title'],meta['folder_id'],meta['deleted'],time.time()))
        return meta

    def context(self,cid):
        fid=self.metadata(cid)['folder_id']
        if fid:
            f=self.folder(fid);return {'folder_id':fid,'folder_name':f['name'],'revision':f['revision'],**f['config']}
        return {'folder_id':None,'folder_name':None,'revision':0,**DEFAULT,'tools':[t for t in TOOLS if t!='bf_memory']}

    def bind(self,cid,context):
        with self.store.connect() as db:
            values=(cid,context['folder_id'],canonical(context),context['revision'],time.time())
            db.execute('INSERT OR REPLACE INTO chat_contexts VALUES(?,?,?,?,?)',values)
            db.execute('INSERT INTO chat_context_history(owner,folder_id,config,revision,created) VALUES(?,?,?,?,?)',values)

    def memory(self,owner,body=None):
        with self.store.connect() as db:r=db.execute('SELECT * FROM chat_contexts WHERE owner=?',(owner,)).fetchone()
        if not r or not r['folder_id'] or 'bf_memory' not in json.loads(r['config'])['tools']:raise PermissionError('FOLDER_MEMORY_DENIED')
        if self.metadata(owner)['folder_id']!=r['folder_id']:raise PermissionError('FOLDER_CONTEXT_CHANGED')
        f=self.folder(r['folder_id'])
        if body is not None:
            if set(body)!={'memory','expected_revision'}:raise ValueError('MEMORY_FIELDS_INVALID')
            f=self.configure(f['id'],{**f['config'],'memory':body['memory']},body['expected_revision'],owner)
        return {'folder_id':f['id'],'revision':f['revision'],'memory':f['config']['memory'],'status':'unverified_shared_notes'}
