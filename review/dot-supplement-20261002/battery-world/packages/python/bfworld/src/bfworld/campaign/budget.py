import json
import sqlite3
import time
from pathlib import Path
from bfworld.kernel.canonical import canonical_hash

class BudgetStop(RuntimeError):pass

class Ledger:
    """Integer micro-CNY accounting; unknown calls retain their full reservation."""
    def __init__(self,path:Path,total=19_000_000,per_trial=2_000_000,max_calls=120,max_tokens=600_000):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=30,isolation_level=None)
        self.db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, trial TEXT, request_hash TEXT, state TEXT, reserved INTEGER, charged INTEGER, token_bound INTEGER, tokens INTEGER, receipt TEXT, created REAL)')
        self.total,self.per_trial,self.max_calls,self.max_tokens=total,per_trial,max_calls,max_tokens
    def reserve(self,key,trial,request):
        # UTF-8 bytes upper-bound text tokens; extra envelope margin is conservative.
        token_bound=len(json.dumps(request,ensure_ascii=False).encode())+2048+request['max_tokens']
        reserve=(token_bound-request['max_tokens'])*3+request['max_tokens']*9
        digest=canonical_hash(request)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old=self.db.execute('SELECT request_hash,state,receipt FROM calls WHERE id=?',(key,)).fetchone()
            if old:
                if old[0]!=digest:raise BudgetStop('idempotency conflict')
                if old[1]!='settled':raise BudgetStop('uncertain prior request; no automatic retry')
                self.db.execute('COMMIT');return json.loads(old[2])
            spent,count,tokens=self.db.execute('SELECT COALESCE(SUM(COALESCE(charged,reserved)),0),COUNT(*),COALESCE(SUM(COALESCE(tokens,token_bound)),0) FROM calls').fetchone()
            trial_spent=self.db.execute('SELECT COALESCE(SUM(COALESCE(charged,reserved)),0) FROM calls WHERE trial=?',(trial,)).fetchone()[0]
            if spent+reserve>self.total or trial_spent+reserve>self.per_trial or count>=self.max_calls or tokens+token_bound>self.max_tokens:raise BudgetStop('hard budget envelope reached before dispatch')
            self.db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?)',(key,trial,digest,'reserved',reserve,None,token_bound,None,None,time.time()))
            self.db.execute('COMMIT');return None
        except BaseException:self.db.execute('ROLLBACK');raise
    def settle(self,key,receipt):
        usage=receipt['usage'];prompt=usage.get('prompt_tokens');completion=usage.get('completion_tokens');total=usage.get('total_tokens')
        if any(type(v)is not int or v<0 for v in (prompt,completion,total)) or total!=prompt+completion:raise BudgetStop('missing or invalid usage receipt')
        # All input charged at cache-miss peak rate. This is an upper bound, not an invoice.
        charge=prompt*3+completion*9
        old=self.db.execute('SELECT state,reserved,token_bound,receipt FROM calls WHERE id=?',(key,)).fetchone()
        if old is None:raise BudgetStop('unreserved call')
        if old[0]=='settled':
            if json.loads(old[3])!=receipt:raise BudgetStop('settled receipt mutation')
            return
        if charge>old[1] or total>old[2]:raise BudgetStop('provider usage exceeded conservative reservation')
        self.db.execute('UPDATE calls SET state=?,charged=?,tokens=?,receipt=? WHERE id=?',('settled',charge,total,json.dumps(receipt),key))
    def summary(self):
        rows=self.db.execute('SELECT id,trial,state,reserved,charged,tokens FROM calls ORDER BY created').fetchall()
        return {'currency':'CNY','cap_cny':self.total/1e6,'per_trial_cap_cny':self.per_trial/1e6,
          'accounted_upper_bound_cny':sum(r[4] if r[4] is not None else r[3] for r in rows)/1e6,
          'usage_tokens':sum(r[5] or 0 for r in rows),'calls':len(rows),'unsettled':sum(r[2]!='settled' for r in rows),
          'pricing':'peak cache-miss 3 CNY/M input + 9 CNY/M output; conservative upper bound, not invoice',
          'receipts':[dict(zip(('id','trial','state','reserved_micro_cny','charged_upper_micro_cny','tokens'),r)) for r in rows]}
