import json
import urllib.request
from pathlib import Path
from .budget import Ledger,BudgetStop
MODEL='deepseek-v4-flash'
BASE='https://api.deepseek.com'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise BudgetStop('provider redirect refused')
class Provider:
    def __init__(self,key_file:Path,ledger:Ledger):
        if key_file.stat().st_mode&0o077:raise BudgetStop('credential permissions must be 0600')
        self._key=key_file.read_text().strip();self.ledger=ledger;self.opener=urllib.request.build_opener(NoRedirect)
    def request(self,path,body=None):
        if path not in ('/models','/chat/completions'):raise BudgetStop('unapproved provider endpoint')
        req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body else None,headers={'Authorization':'Bearer '+self._key,'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=120) as response:return json.load(response)
        except Exception as e:
            # Never serialize provider exception bodies, request headers or credentials.
            raise BudgetStop('provider transport failed: '+type(e).__name__+'; reservation retained') from None
    def models(self):
        result=self.request('/models');ids=[m['id'] for m in result.get('data',[])]
        if MODEL not in ids:raise BudgetStop('requested exact model absent from provider catalogue')
        return {'model_identity':MODEL,'available_model_ids':ids,'documented_version':'DeepSeek-V4-Flash-0731','identity_limit':'service alias and response fingerprint, not an immutable weight hash'}
    def complete(self,key,trial,messages):
        body={'model':MODEL,'messages':messages,'thinking':{'type':'disabled'},'temperature':.2,'max_tokens':4096,'response_format':{'type':'json_object'}}
        cached=self.ledger.reserve(key,trial,body)
        if cached is not None:return cached
        raw=self.request('/chat/completions',body)
        if raw.get('model')!=MODEL:raise BudgetStop('provider returned unexpected model identity')
        choice=raw['choices'][0]
        # Explicit decision summary only. Provider private reasoning is not copied.
        receipt={'id':raw['id'],'model':raw['model'],'system_fingerprint':raw.get('system_fingerprint'),
          'usage':raw.get('usage',{}),'finish_reason':choice['finish_reason'],'content':choice['message'].get('content','')}
        self.ledger.settle(key,receipt)
        return receipt
