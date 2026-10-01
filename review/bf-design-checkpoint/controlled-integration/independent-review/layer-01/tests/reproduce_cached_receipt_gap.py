"""Reviewer-owned, no-process integrity negative control on trusted AttemptBook."""
import hashlib,importlib,sys,json
from pathlib import Path
source=Path('/workspace/shared/controlled-launcher-integration-20261001/src')
review=Path('/workspace/shared/next-stage-integration-review-20261001')
sys.dont_write_bytecode=True
sys.path.insert(0,str(source))
m=importlib.import_module('integration')
code_hash=hashlib.sha256((source/'integration.py').read_bytes()).hexdigest()
m.ROOT=review
book=m.AttemptBook(review/'outputs/cache-gap-fixture',['episode1'],{'kind':'reviewer-synthetic-no-process'},max_attempts=2)
request={'fixture':'no-process'}
assert book.begin('episode1','attempt1',request) is None
book.finish('attempt1','blocked',{'process_started':False,'reason':'reviewer control'})
f=book.root/book.receipt_file('attempt1')
r=json.loads(f.read_text());r['status']='activation_pass';r['scientific_success']=True
f.write_text(json.dumps(r))
try:
 got=book.begin('episode1','attempt1',request)
 cached_rejected=False;cached_status=got['status'];cached_science=got['scientific_success']
except Exception as e:
 cached_rejected=True;cached_status=str(e);cached_science=None
try:
 book.recover('attempt1');recover_rejected=False
except Exception as e:
 recover_rejected=True;recover_error=str(e)
out={'reviewed_source_sha256':code_hash,'cached_path_rejected_tamper':cached_rejected,'cached_status':cached_status,'cached_scientific_success':cached_science,'recover_path_rejected_tamper':recover_rejected,'recover_error':recover_error if recover_rejected else None,'processes_started':0,'provider_calls':0,'scientific_runs':0,'fixture_location':str(book.root)}
(review/'outputs/CACHE-INTEGRITY-REPAIR-READBACK.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
