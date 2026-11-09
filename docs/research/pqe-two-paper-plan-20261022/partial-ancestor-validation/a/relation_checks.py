import sys,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(R/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src'))
from bfworld.agentlab.pqe20261024debt.facts import public_record_relations
A=Path(__file__).parent

def make(actions,rx=()):
 return {"result_sha256":"synthetic-public-no-science","execution_status":"COMPLETE","facts":{"activity":actions,"receiver_records":list(rx)},"truth":["POISON_TRUTH"]}
def ev(action,time_s,**fields):return {"action":action,"time_s":time_s,"observer_epoch":"POISON_EPOCH",**fields}
def save(seq,di,t):return ev("save_commit",t,record={"seq":seq,"direction":di},durable=True)
# 1: rereads remain one holder record; receive does not require a later ACK.
actions=[ev("holding_capture_commit",1,record={"token":1,"direction":1}),ev("holding_read_commit",2,record={"token":1,"direction":1,"assigned_seq":1}),ev("holding_read_commit",2.1,record={"token":1,"direction":1,"assigned_seq":1}),ev("capture",2.1,direction=1,source="paid_holder_read"),save(1,1,2.2),ev("wire_complete",2.3,record={"seq":1,"direction":1}),ev("ack_commit",2.4,record={"seq":1,"direction":1}),ev("holding_clear_commit",2.5,record={"token":1,"assigned_seq":1,"direction":1})]
x=public_record_relations(make(actions,[{"seq":1,"direction":1,"time_s":2.3}]))
assert len(x["holder_records"])==len(x["records"])==1
assert len(x["holder_records"][0]["stages"]["read"])==2
assert all(k in x["records"][0]["stages"] for k in ["holder_capture","read","capture","save","tx","recv","ack","clear"])
assert "POISON" not in json.dumps(x) and "observer_epoch" not in json.dumps(x)
# 2: reset breaks token continuity; reused numeric identities remain two SAVE occurrences.
actions=[ev("holding_capture_commit",1,record={"token":1,"direction":1}),ev("holding_read_commit",1.1,record={"token":1,"direction":1,"assigned_seq":1}),ev("capture",1.1,direction=1,source="paid_holder_read"),save(1,1,1.2),ev("brownout",1.3,reason="UVLO"),ev("holding_reset",1.4),ev("holding_capture_commit",2,record={"token":1,"direction":1}),ev("holding_read_commit",2.1,record={"token":1,"direction":1,"assigned_seq":1}),ev("capture",2.1,direction=1,source="paid_holder_read"),save(1,1,2.2)]
x=public_record_relations(make(actions,[{"seq":1,"direction":1,"time_s":1.25}]))
assert len(x["holder_records"])==len(x["records"])==2
assert x["records"][0]["holder_capture_ref"]!=x["records"][1]["holder_capture_ref"]
assert "recv" in x["records"][0]["stages"] and "recv" not in x["records"][1]["stages"]
assert [r["observed_mcu_resets_at_save"] for r in x["records"]]==[0,1]
# 3: missing data/tool failure is UNKNOWN; no fabricated record losses.
x=public_record_relations({"execution_status":"TOOL_ERROR"})
assert not x["records"] and x["unknowns"] and all(u["status"]=="UNKNOWN" for u in x["unknowns"])
receipt={"software_cases":3,"cases":["reread/ACK-independent receive/paid clear/public whitelist","reset/token reuse/sequence reuse/source-limited join","missing-public-facts TOOL_ERROR stays UNKNOWN"],"status":"PASS","full_executions":0,"cheap_numeric":0,"source_sha256":hashlib.sha256((R/'workbench/bf-campaign-s0-20261019/battery-world/packages/python/bfworld/src/bfworld/agentlab/pqe20261024debt/facts.py').read_bytes()).hexdigest()}
(A/'relation-checks.json').write_text(json.dumps(receipt,indent=2)+'\n')
count=json.loads((A/'counter.json').read_text());count['software_cases']=3;(A/'counter.json').write_text(json.dumps(count,indent=2)+'\n')
print(json.dumps(receipt))
