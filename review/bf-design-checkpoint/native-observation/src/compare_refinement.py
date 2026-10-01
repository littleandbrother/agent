"""Compare two retained metric reports under the prospectively frozen criteria."""
from pathlib import Path
import argparse,json,hashlib,math
from retained_raw import EvidenceError

ROOT=Path(__file__).resolve().parents[1]


LEDGER_KEYS={"drive_delivered_J","control_delivered_J","source_resistor_loss_J","switch_loss_J","load_loss_J","l_esr_loss_J","l_rpar_loss_J","cout_esr_loss_J","zero_sensor_absorption_J","macro_absorption_J","initial_external_stored_J","final_external_stored_J","max_abs_external_residual_J"}
def number(x):
    return type(x) in (int,float) and math.isfinite(x)
def finite_tree(x):
    if isinstance(x,float) and not math.isfinite(x): raise EvidenceError("NONFINITE_REPORT_QUANTITY")
    if isinstance(x,dict):
        for value in x.values(): finite_tree(value)
    elif isinstance(x,list):
        for value in x: finite_tree(value)
def validate_report(r,plan):
    if not isinstance(r,dict): raise EvidenceError("INVALID_METRIC_REPORT")
    required={"schema_version","case_id","energy_ledger","numerical_checks","all_numerical_checks_passed","initial_state","PGOOD","VIN_reference_crossings","switch_control_crossings","pre_uvlo_observation"}
    if not required<=set(r) or r["schema_version"]!="native-observation-retained-metrics-v1": raise EvidenceError("INCOMPLETE_METRIC_REPORT")
    finite_tree(r)
    if type(r["all_numerical_checks_passed"]) is not bool or type(r["initial_state"].get("zero_screen_passed")) is not bool: raise EvidenceError("NONBOOLEAN_PASS_FLAG")
    checks=r["numerical_checks"]
    if not isinstance(checks,list) or not checks: raise EvidenceError("MISSING_NUMERICAL_CHECKS")
    for c in checks:
        if not isinstance(c,dict) or type(c.get("passed")) is not bool: raise EvidenceError("NONBOOLEAN_PASS_FLAG")
        if not number(c.get("max_abs_residual")) or not number(c.get("tolerance")) or c["max_abs_residual"]<0 or c["tolerance"]<0: raise EvidenceError("INVALID_CHECK_QUANTITY")
        if c["passed"] != (c["max_abs_residual"]<=c["tolerance"]): raise EvidenceError("CHECK_FLAG_NUMERIC_MISMATCH")
    if r["all_numerical_checks_passed"] != all(c["passed"] for c in checks): raise EvidenceError("AGGREGATE_CHECK_FLAG_MISMATCH")
    if not isinstance(r["energy_ledger"],dict) or set(r["energy_ledger"])!=LEDGER_KEYS or not all(number(v) for v in r["energy_ledger"].values()): raise EvidenceError("LEDGER_FIELDS_OR_QUANTITIES_INVALID")
    expected={str(v) for v in plan["analysis"]["uvlo_reference_crossings_V"]}
    if not isinstance(r["VIN_reference_crossings"],dict) or set(r["VIN_reference_crossings"])!=expected: raise EvidenceError("VIN_REFERENCE_KEYS_MISMATCH")
    rails=r["pre_uvlo_observation"].get("rails")
    if not isinstance(rails,dict) or set(rails)!={"Ccap","Cvin2"}: raise EvidenceError("RAIL_METRICS_MISSING")
    for row in rails.values():
        if set(row)!={"voltage_start_V","voltage_end_V","delta_charge_C","delta_energy_J"} or not all(number(v) for v in row.values()): raise EvidenceError("RAIL_QUANTITIES_INVALID")
    if r["PGOOD"].get("events") is None:
        if not r["PGOOD"].get("status","").startswith("UNRESOLVED_"): raise EvidenceError("PGOOD_STATUS_INCONSISTENT")
    elif r["PGOOD"].get("status")!="OBSERVED_SIGNAL_BRACKETS": raise EvidenceError("PGOOD_STATUS_INCONSISTENT")
def event_fields(label):
    base={"direction","time_bracket_s","signal_bracket","analysis_level"}
    if label=="PGOOD": return base|{"vin_V_bracket","vout_V_bracket"}
    if label.startswith("VIN_reference_"): return base|{"pgood_V_bracket","vout_V_bracket"}
    if label=="switch_control": return base|{"source_current_A_bracket"}
    raise EvidenceError("UNKNOWN_EVENT_FAMILY")
def validate_events(events,label):
    if not isinstance(events,list): raise EvidenceError("INVALID_EVENTS")
    for e in events:
        if not isinstance(e,dict) or set(e)!=event_fields(label): raise EvidenceError("EVENT_FIELDS_MISMATCH:"+label)
        if e["direction"] not in ("rising","falling") or not number(e["analysis_level"]): raise EvidenceError("INVALID_EVENT_METADATA")
        for key,value in e.items():
            if key.endswith("bracket") or key=="time_bracket_s":
                if not isinstance(value,list) or len(value)!=2 or not all(number(v) for v in value): raise EvidenceError("INVALID_EVENT_BRACKET")
        if e["time_bracket_s"][0]<0 or e["time_bracket_s"][1]<=e["time_bracket_s"][0]: raise EvidenceError("INVALID_TIME_BRACKET")

def compare_events(a,b,p,label):
    if a is None or b is None:
        return {"name":label,"passed":False,"status":"UNRESOLVED_MISSING_EVENT_REFERENCE"}
    validate_events(a,label);validate_events(b,label)
    if len(a)!=len(b) or [x["direction"] for x in a]!=[x["direction"] for x in b]:
        return {"name":label,"passed":False,"status":"EVENT_COUNT_OR_ORDER_DIFFERS","counts":[len(a),len(b)]}
    rows=[]
    for x,y in zip(a,b):
        dt=max(abs(x["time_bracket_s"][i]-y["time_bracket_s"][i]) for i in (0,1))
        fields=set(x)
        if fields!=set(y): raise EvidenceError("EVENT_FIELDS_MISMATCH")
        dvs={f:max(abs(x[f][i]-y[f][i]) for i in (0,1)) for f in fields if f.endswith("_V_bracket")}
        ok=dt<=p["coarse_fine_event_time_s"] and all(d<=p["coarse_fine_event_voltage_V"] for d in dvs.values())
        rows.append({"time_bracket_endpoint_delta_s":dt,"voltage_bracket_endpoint_deltas_V":dvs,"passed":ok})
    return {"name":label,"status":"BRACKETS_COMPARED","passed":all(x["passed"] for x in rows),"events":rows}

def compare(a,b,plan):
    validate_report(a,plan);validate_report(b,plan)
    ca,cb=plan["cases"].get(a.get("case_id")),plan["cases"].get(b.get("case_id"))
    if not ca or not cb or ca["mode"]!=cb["mode"] or ca["resolution"]!="coarse" or cb["resolution"]!="fine":
        raise EvidenceError("REQUIRE_MATCHED_COARSE_AND_FINE_CASES")
    p=plan["analysis"];rows=[]
    if set(a["energy_ledger"])!=set(b["energy_ledger"]): raise EvidenceError("LEDGER_FIELDS_DIFFER")
    for key in a["energy_ledger"]:
        av,bv=a["energy_ledger"][key],b["energy_ledger"][key]
        tolerance=max(p["coarse_fine_energy_abs_J"],p["coarse_fine_energy_relative"]*max(abs(av),abs(bv)))
        rows.append({"quantity":key,"coarse":av,"fine":bv,"difference":abs(av-bv),"tolerance":tolerance,"passed":abs(av-bv)<=tolerance})
    events=[compare_events(a["PGOOD"]["events"],b["PGOOD"]["events"],p,"PGOOD")]
    for key in a["VIN_reference_crossings"]:
        events.append(compare_events(a["VIN_reference_crossings"][key],b["VIN_reference_crossings"][key],p,"VIN_reference_"+key))
    events.append(compare_events(a["switch_control_crossings"],b["switch_control_crossings"],p,"switch_control"))
    inputs_pass=bool(a["all_numerical_checks_passed"] and b["all_numerical_checks_passed"] and a["initial_state"]["zero_screen_passed"] and b["initial_state"]["zero_screen_passed"])
    numeric_pass=inputs_pass and all(r["passed"] for r in rows) and all(r["passed"] for r in events)
    rails={}
    for rail in ("Ccap","Cvin2"):
        aa=a["pre_uvlo_observation"]["rails"][rail];bb=b["pre_uvlo_observation"]["rails"][rail];detections={}
        for quantity in ("delta_charge_C","delta_energy_J"):
            diff=abs(aa[quantity]-bb[quantity]);small=min(aa[quantity],bb[quantity])
            detections[quantity]={"coarse":aa[quantity],"fine":bb[quantity],"observed_refinement_difference":diff,
                "positive_and_exceeds_5x_difference":small>0 and small>p["charge_detectability_factor"]*diff}
        rails[rail]={"numerically_detectable_charging":numeric_pass and all(x["positive_and_exceeds_5x_difference"] for x in detections.values()),"quantities":detections,
                     "claim":"External capacitor charging over the declared source interval only; not hidden UVLO state or physical qualification"}
    return {"schema_version":"native-observation-refinement-v1","mode":ca["mode"],"all_resolved_numerical_gates_passed":numeric_pass,
        "input_numerical_and_external_zero_screens_passed":inputs_pass,"energy_checks":rows,"event_checks":events,"pre_uvlo_rail_charge_detectability":rails,
        "scope":"Numerical fixture observations only, not statistical confidence, internal-state causality or device/mission validation"}

if __name__=="__main__":
    pa=argparse.ArgumentParser();pa.add_argument("--coarse",type=Path,required=True);pa.add_argument("--fine",type=Path,required=True);pa.add_argument("--output",type=Path,required=True);args=pa.parse_args()
    if args.output.exists(): raise EvidenceError("OUTPUT_EXISTS_PRESERVE_PRIOR_RESULT")
    a=json.loads(args.coarse.read_text());b=json.loads(args.fine.read_text());plan=json.loads((ROOT/"EXACT-PLAN.json").read_text())
    result=compare(a,b,plan);result["source_metric_sha256"]={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.coarse,args.fine]}
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")

