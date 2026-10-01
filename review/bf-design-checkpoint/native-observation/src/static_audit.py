"""Exact static deck audit and fail-closed runtime identity check; never launches."""
from pathlib import Path
import hashlib
import json
import re
import argparse
from build_decks import CASES, PORTS, SIGNALS, render
from retained_raw import EvidenceError

ROOT = Path(__file__).resolve().parents[1]
def sha(path):
    p=Path(path)
    if not p.is_file(): raise EvidenceError("REQUIRED_FILE_MISSING:" + str(p))
    return hashlib.sha256(p.read_bytes()).hexdigest()

def parse_deck(text):
    elements, directives = {}, []
    for number, line in enumerate(text.splitlines(), 1):
        line=line.strip()
        if not line or line.startswith("*"): continue
        if line.startswith("."):
            directives.append((number,line)); continue
        tokens=line.split(); key=tokens[0].lower()
        if key in elements: raise EvidenceError("DUPLICATE_ELEMENT:" + key)
        if len(tokens)<4: raise EvidenceError("SHORT_ELEMENT:" + key)
        elements[key]=tokens
    return elements, directives

def audit_deck(text, case):
    if text != render(case): raise EvidenceError("DECK_DIFFERS_FROM_FROZEN_GENERATOR:" + case)
    es, ds = parse_deck(text)
    if es["xu1"][1:-1] != [p[2] for p in PORTS]: raise EvidenceError("XU1_PORT_ORDER")
    if es["xu1"][-1] != "LTC3588-1": raise EvidenceError("MODEL_NAME")
    for _,external,internal,sensor in PORTS:
        if es[sensor.lower()][1:] != [external,internal,"0"]: raise EvidenceError("PORT_SENSOR_ORIENTATION")
    if es["vpm_pz1"][1] != "0" or es["vpm_pz2"][1] != "0": raise EvidenceError("PZ_NOT_CLAMPED")
    if es["cstorage"][1:3] != ["vin","0"] or es["ccap"][1:3] != ["vin","cap"] or es["cvin2"][1:3] != ["vin2","0"] or es["cout"][1:3] != ["cout_inner","0"]:
        raise EvidenceError("CAPACITOR_TOPOLOGY")
    for name in ("cstorage","ccap","cvin2","cout","l1"):
        if "ic=0" not in [t.lower() for t in es[name]]: raise EvidenceError("INITIAL_STATE_UNDECLARED")
    signals=[token.lower() for _,d in ds if d.lower().startswith(".save ") for token in d.split()[1:]]
    if len(signals)!=len(set(signals)) or set(signals)!={s.lower() for s in SIGNALS}: raise EvidenceError("SAVE_MISMATCH")
    if any("," in s for s in signals): raise EvidenceError("UNVERIFIED_DIFFERENTIAL_SAVE")
    return {"case":case,"elements":len(es),"saved_channels":len(signals),"exact_match":True}

def static_audit(root=ROOT):
    root=Path(root)
    results=[audit_deck((root/"decks"/(case+".cir")).read_text(),case) for case in CASES]
    iface=json.loads((root/"contracts/native-model-interface-v2.json").read_text())
    if iface["ordered_ports"] != [p[0] for p in PORTS] or iface["subckt_declaration"] is not None or iface["declaration_status"]!="unobserved-binary":
        raise EvidenceError("INVALID_SYMBOL_BACKED_V2")
    return {"status":"STATIC_ONLY_PASS","decks":results,"native_runs":0,"runtime_ready":False,"execution_authorized":False}

def runtime_identity(model, symbol, executable, root=ROOT):
    expected=json.loads((Path(root)/"contracts/native-model-interface-v2.json").read_text())
    verified={}
    for label,path in (("model",model),("symbol",symbol),("executable",executable)):
        if not path: raise EvidenceError("RUNTIME_" + label.upper() + "_NOT_SUPPLIED")
        actual=sha(path); item=expected["artifacts"][label]
        if actual != item["sha256"] or Path(path).stat().st_size != item["bytes"]:
            raise EvidenceError("RUNTIME_" + label.upper() + "_IDENTITY_MISMATCH")
        verified[label]={"path":str(Path(path).resolve()),"sha256":actual}
    # A matching opaque model hash is not a model run, RC smoke, or approval.
    return {"status":"STATIC_ARTIFACT_IDENTITIES_MATCH","artifacts":verified,
        "runtime_ready":False,"rc_smoke_verified":False,"execution_authorized":False}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--model");p.add_argument("--symbol");p.add_argument("--executable");p.add_argument("--static-only",action="store_true")
    a=p.parse_args()
    result=static_audit()
    if not a.static_only: result["runtime_identity"]=runtime_identity(a.model,a.symbol,a.executable)
    print(json.dumps(result,indent=2))

