"""Prospective retained-data metrics only; never calls a circuit solver.
Every integral uses original monotonic native samples. Event outputs are sample
brackets, not interpolated crossing claims. All reported gates are numerical,
fixture-specific, and cannot qualify physical hardware or hidden macro state.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from build_decks import PORTS, SIGNALS
from retained_raw import EvidenceError, read_raw, require_columns, require_finished_log

ROOT=Path(__file__).resolve().parents[1]

def cumtrap(t,y):
    return np.r_[0.,np.cumsum(np.diff(t)*(y[:-1]+y[1:])*.5)]

def integral(t,y):
    return float(np.sum(np.diff(t)*(y[:-1]+y[1:])*.5))

def selected(t,start,end,minimum=2,cover_start=False):
    left=int(np.searchsorted(t,start,side="left"))
    if left>=len(t): raise EvidenceError("WINDOW_START_AFTER_TRACE")
    if cover_start and left>0 and t[left]>start: left-=1
    right=int(np.searchsorted(t,end,side="right"))
    if right-left<minimum: raise EvidenceError("INSUFFICIENT_WINDOW_SAMPLES")
    return slice(left,right)

def event_brackets(t,x,level,extras=None):
    events=[]
    # Equality belongs to the high side for this analysis rule, not a hidden switch state.
    high=x>=level
    for j in np.flatnonzero(high[1:]!=high[:-1])+1:
        item={"direction":"rising" if high[j] else "falling",
            "time_bracket_s":[float(t[j-1]),float(t[j])],
            "signal_bracket":[float(x[j-1]),float(x[j])],"analysis_level":float(level)}
        if extras:
            for name,a in extras.items(): item[name+"_bracket"]=[float(a[j-1]),float(a[j])]
        events.append(item)
    return events

def pg_events(t,c,p):
    try:
        lo=selected(t,*p["pgood_low_reference_s"],minimum=p["pgood_min_reference_samples"])
        hi=selected(t,*p["pgood_high_reference_s"],minimum=p["pgood_min_reference_samples"])
    except EvidenceError as e:
        return {"status":"UNRESOLVED_REFERENCE_WINDOWS","reason":str(e),"events":None}
    x=c["v(pgood)"]; low=float(np.median(x[lo])); high=float(np.median(x[hi]))
    spans=[float(np.ptp(x[lo])),float(np.ptp(x[hi]))]
    if high-low<p["pgood_min_swing_V"] or max(spans)>p["pgood_stable_peak_to_peak_V"]:
        return {"status":"UNRESOLVED_NO_STABLE_LOW_AND_HIGH","low_median_V":low,
                "high_median_V":high,"reference_peak_to_peak_V":spans,"events":None}
    threshold=.5*(low+high)
    events=event_brackets(t,x,threshold,{"vin_V":c["v(vin)"],"vout_V":c["v(out)"]})
    return {"status":"OBSERVED_SIGNAL_BRACKETS","low_median_V":low,"high_median_V":high,
        "analysis_crossing_V":threshold,"reference_peak_to_peak_V":spans,
        "events":events,
        "rising_event_status":"observed" if any(e["direction"]=="rising" for e in events) else "right-censored at trace end",
        "falling_event_status":"observed" if any(e["direction"]=="falling" for e in events) else "right-censored at trace end",
        "hidden_sleep_event":"UNOBSERVED"}

def check_residual(name,residual,scale,absolute,relative):
    maximum=float(np.max(np.abs(residual))); tolerance=max(absolute,relative*float(scale))
    return {"name":name,"max_abs_residual":maximum,"tolerance":tolerance,"passed":maximum<=tolerance}

def analyze_trace(raw,case_id,plan):
    if case_id not in plan["cases"]: raise EvidenceError("UNKNOWN_CASE")
    require_columns(raw,SIGNALS)
    t,c=raw.time,raw.columns; case=plan["cases"][case_id]; p=plan["analysis"]; v=plan["physical_values"]
    if t[0]!=0 or abs(t[-1]-2.0)>1e-12: raise EvidenceError("INCOMPLETE_INITIAL_OR_FINAL_TIME")
    if float(np.max(np.diff(t)))>case["maxstep_s"]+1e-10: raise EvidenceError("SAMPLE_GAP_EXCEEDS_FROZEN_MAXSTEP")
    if any(not np.isfinite(a).all() for a in c.values()): raise EvidenceError("NONFINITE")
    zero=np.zeros_like(t)
    def V(n): return zero if n=="0" else c["v("+n.lower()+")"]
    def I(n): return c["i("+n.lower()+")"]
    checks=[]
    src_pwl=plan["source_prefix_pwl_s_V"]+plan["source_suffix"][case["mode"]]
    control=plan["switch"]["source_open_control_pwl_s_V"] if case["mode"]=="source-open" else plan["switch"]["driven_down_control_pwl_s_V"]
    for label,actual,points in (("source_command",V("drv"),src_pwl),("switch_control",V("sw_ctl"),control)):
        expected=np.interp(t,np.asarray(points)[:,0],np.asarray(points)[:,1])
        checks.append(check_residual(label,actual-expected,0,1e-8,0))
    caps=[("Cstorage",v["cin_F"],V("vin"),I("Cstorage")),
          ("Ccap",v["ccap_F"],V("vin")-V("cap"),I("Ccap")),
          ("Cvin2",v["cvin2_F"],V("vin2"),I("Cvin2")),
          ("Cout",v["cout_F"],V("cout_inner"),I("Cout"))]
    stores={}; cap_metrics={}
    with np.errstate(over="raise",invalid="raise"):
        for name,C,voltage,current in caps:
            energy=.5*C*voltage**2; stores[name]=energy
            charge=cumtrap(t,current); work=cumtrap(t,voltage*current)
            qr=check_residual(name+"_charge",charge-C*(voltage-voltage[0]),integral(t,np.abs(current)),p["charge_gate_abs_C"],p["charge_gate_relative_to_total_abs_charge"])
            er=check_residual(name+"_energy",work-(energy-energy[0]),integral(t,np.abs(voltage*current)),p["capacitor_energy_gate_abs_J"],p["capacitor_energy_gate_relative_to_total_abs_work"])
            checks += [qr,er]
            cap_metrics[name]={"initial_J":float(energy[0]),"final_J":float(energy[-1]),"max_J":float(np.max(energy)),"signed_terminal_work_J":float(work[-1]),"charge_check":qr,"energy_check":er}
        vL=V("l_inner")-V("out")
        iL=I("V_L_TERMINAL")-vL/v["l_rpar_ohm"]
        stores["L1"]=.5*v["l_H"]*iL**2
    flux=cumtrap(t,vL)
    checks.append(check_residual("ideal_L_flux",flux-v["l_H"]*(iL-iL[0]),integral(t,np.abs(vL)),p["inductor_flux_gate_abs_Wb"],p["inductor_flux_gate_relative_to_abs_volt_seconds"]))
    macro_power=zero.copy(); sensor_power=zero.copy()
    for _,external,internal,sensor in PORTS:
        drop=V(external)-V(internal); current=I(sensor)
        checks.append(check_residual(sensor+"_zero_drop",drop,0,p["zero_sensor_drop_gate_V"],0))
        sensor_power += drop*current
        macro_power += V(internal)*current
    for sensor,n1,n2 in [("Vsupply","src_after_r","pre_switch"),("V_L_TERMINAL","l_after_r","l_inner"),("V_COUT_BRANCH","cout_after_r","cout_inner")]:
        drop=V(n1)-V(n2); sensor_power += drop*I(sensor)
        checks.append(check_residual(sensor+"_zero_drop",drop,0,p["zero_sensor_drop_gate_V"],0))
    # Current consistency never infers the saved I(L1) convention.
    branches={
        "source":[I("Vdrive"),I("Vsupply")],
        "switch_control":[I("Vcontrol")],
        "vin":[I("Vsupply"),-I("Cstorage"),-I("Ccap"),-I("VPM_VIN")],
        "cap":[I("Ccap"),-I("VPM_CAP")],
        "vin2":[-I("Cvin2"),-I("VPM_VIN2"),-I("VPM_D1")],
        "sw":[-I("V_L_TERMINAL"),-I("VPM_SW")],
        "out":[I("V_L_TERMINAL"),-I("V_COUT_BRANCH"),-I("Rload"),-I("VPM_VOUT")],
        "cout":[I("V_COUT_BRANCH"),-I("Cout")],
        "pgood":[I("VPM_PGOOD")],
        "source_resistor":[I("Rsource"),-I("Vsupply")],
        "source_switch":[I("Sdrive"),-I("Vsupply")],
        "l_esr":[I("R_L_ESR"),-I("V_L_TERMINAL")],
        "cout_esr":[I("R_COUT_ESR"),-I("V_COUT_BRANCH")],
        "all_declared_macro_ports":[I(x[3]) for x in PORTS],
    }
    for name,values in branches.items():
        checks.append(check_residual("KCL_"+name,np.sum(values,axis=0),max(float(np.max(np.abs(a))) for a in values),p["kcl_gate_abs_A"],p["kcl_gate_relative_to_largest_branch"]))
    # Check resistance laws independently from node KCL.
    for name,actual,expected in [
        ("Rsource",I("Vsupply"),(V("drv")-V("src_after_r"))/v["source_R_ohm"]),
        ("R_L_ESR",I("V_L_TERMINAL"),(V("sw")-V("l_after_r"))/v["l_esr_ohm"]),
        ("R_COUT_ESR",I("V_COUT_BRANCH"),(V("out")-V("cout_after_r"))/v["cout_esr_ohm"]),
        ("Rload",I("Rload"),V("out")/v["load_R_ohm"]),
    ]:
        checks.append(check_residual("OHM_"+name,actual-expected,max(float(np.max(np.abs(actual))),float(np.max(np.abs(expected)))),p["kcl_gate_abs_A"],p["kcl_gate_relative_to_largest_branch"]))
    away=np.abs(V("sw_ctl")-.5)>1e-9
    expected_switch_current=(V("pre_switch")-V("vin"))/np.where(V("sw_ctl")>.5,.01,1e12)
    checks.append(check_residual("SWITCH_OHM_AWAY_FROM_THRESHOLD",(I("Vsupply")-expected_switch_current)[away],float(np.max(np.abs(expected_switch_current[away]))),p["kcl_gate_abs_A"],p["kcl_gate_relative_to_largest_branch"]))
    off=(V("sw_ctl")<.5-1e-9)
    off_observation=None
    if np.any(off):
        checks.append(check_residual("SWITCH_OFF_LEAKAGE_CURRENT",(I("Vsupply")-expected_switch_current)[off],0,p["switch_off_current_abs_A"],0))
        off_observation={"max_abs_source_branch_A":float(np.max(np.abs(I("Vsupply")[off]))),"max_abs_ideal_Roff_current_A":float(np.max(np.abs(expected_switch_current[off]))),"measurement_current_residual_tolerance_A":p["switch_off_current_abs_A"],"finite_Roff_ohm":1e12}
    powers={
        "drive_delivered":-V("drv")*I("Vdrive"),
        "control_delivered":-V("sw_ctl")*I("Vcontrol"),
        "source_resistor_loss":v["source_R_ohm"]*I("Vsupply")**2,
        "switch_loss":(V("pre_switch")-V("vin"))*I("Vsupply"),
        "load_loss":V("out")**2/v["load_R_ohm"],
        "l_esr_loss":v["l_esr_ohm"]*I("V_L_TERMINAL")**2,
        "l_rpar_loss":vL**2/v["l_rpar_ohm"],
        "cout_esr_loss":v["cout_esr_ohm"]*I("V_COUT_BRANCH")**2,
        "zero_sensor_absorption":sensor_power,
        "macro_absorption":macro_power,
    }
    total_source=powers["drive_delivered"]+powers["control_delivered"]
    external_loss=sum(powers[k] for k in ["source_resistor_loss","switch_loss","load_loss","l_esr_loss","l_rpar_loss","cout_esr_loss","zero_sensor_absorption"])
    stored_total=sum(stores.values())
    residual=cumtrap(t,total_source-external_loss-macro_power)-(stored_total-stored_total[0])
    checks.append(check_residual("EXTERNAL_LEDGER",residual,integral(t,np.abs(total_source)),p["external_ledger_gate_abs_J"],p["external_ledger_gate_relative_to_abs_source_work"]))
    screen=selected(t,np.nextafter(0.,1.),p["initial_zero_screen"]["window_end_s"])
    voltages={name:float(np.max(np.abs(voltage[screen]))) for name,C,voltage,current in caps}
    initial_pass=max(voltages.values())<=p["initial_zero_screen"]["max_abs_external_store_voltage_V"] and float(np.max(np.abs(iL[screen])))<=p["initial_zero_screen"]["max_abs_ideal_L_current_A"]
    first=1
    initial={"explicit_external_ICs":plan["initial_states"],"raw_t0_values":{name:float(voltage[0]) for name,C,voltage,current in caps},
        "first_postzero_time_s":float(t[first]),"first_postzero_store_voltages_V":{name:float(voltage[first]) for name,C,voltage,current in caps},
        "first_postzero_ideal_L_A":float(iL[first]),"zero_screen_max_voltages_V":voltages,
        "zero_screen_max_abs_ideal_L_A":float(np.max(np.abs(iL[screen]))),"zero_screen_passed":bool(initial_pass),"internal_macro_states":"UNKNOWN"}
    pre=selected(t,*p["pre_uvlo_charge_window_s"]); plateau=selected(t,*p["pre_uvlo_plateau_window_s"])
    pre_rails={}
    for name,C,voltage,current in caps[1:3]:
        vv=voltage[pre];pre_rails[name]={"voltage_start_V":float(vv[0]),"voltage_end_V":float(vv[-1]),"delta_charge_C":float(C*(vv[-1]-vv[0])),"delta_energy_J":float(.5*C*(vv[-1]**2-vv[0]**2))}
    pre_result={"actual_window_s":[float(t[pre][0]),float(t[pre][-1])],"rails":pre_rails,"max_actual_vin_V":float(np.max(V("vin")[pre])),
        "max_vout_V":float(np.max(V("out")[pre])),"max_abs_ideal_L_A":float(np.max(np.abs(iL[pre]))),"sw_minmax_V":[float(np.min(V("sw")[pre])),float(np.max(V("sw")[pre]))],
        "below_datasheet_min_UVLO_rise_reference":bool(np.max(V("vin")[pre])<4.73),
        "plateau_rail_end_V":{"vin":float(V("vin")[plateau][-1]),"cap_differential":float((V("vin")-V("cap"))[plateau][-1]),"vin2":float(V("vin2")[plateau][-1])},
        "interpretation":"Observed external rail states before the specified source-ramp transition; hidden UVLO/converter state not inferred"}
    settle=[]
    sp=p["settling"]
    for multiple in sp["window_multiples"]:
        sl=selected(t,2.0-multiple*sp["window_s"],2.,minimum=sp["minimum_samples"],cover_start=True)
        tt=t[sl]; elapsed=float(tt[-1]-tt[0]);spacing=float(np.max(np.diff(tt)))
        for name,C,voltage,current in caps[1:3]:
            vv=voltage[sl];ii=current[sl];dt=tt-tt[0];slope=float(np.polyfit(dt,vv,1)[0])
            metrics={"peak_to_peak_V":float(np.ptp(vv)),"slope_times_span_V":abs(slope)*elapsed,"energy_drift_J":float(abs(.5*C*(vv[-1]**2-vv[0]**2))),"charge_consistency_C":float(abs(integral(tt,ii)-C*(vv[-1]-vv[0])))}
            passed=all(metrics[k]<=sp[k] for k in metrics) and spacing<=case["maxstep_s"]+1e-10 and tt[0]>=sp["source_last_command_change_s"][case["mode"]]
            settle.append({"rail":name,"window_multiple":multiple,"observed_window_s":[float(tt[0]),float(tt[-1])],"max_sample_spacing_s":spacing,**metrics,"passed":bool(passed)})
    energy={name+"_J":integral(t,a) for name,a in powers.items()}
    energy.update({"initial_external_stored_J":float(stored_total[0]),"final_external_stored_J":float(stored_total[-1]),"max_abs_external_residual_J":float(np.max(np.abs(residual)))})
    pg=pg_events(t,c,p)
    refs={str(level):event_brackets(t,V("vin"),level,{"pgood_V":V("pgood"),"vout_V":V("out")}) for level in p["uvlo_reference_crossings_V"]}
    pg["high_through_nominal_3p67V_falling_reference"]=[e for e in refs["3.67"] if e["direction"]=="falling" and min(e["pgood_V_bracket"])>=pg["analysis_crossing_V"]] if pg["events"] is not None else None
    return {"schema_version":"native-observation-retained-metrics-v1","case_id":case_id,"trace_metadata":raw.metadata,
        "numerical_checks":checks,"all_numerical_checks_passed":all(x["passed"] for x in checks),
        "initial_state":initial,"pre_uvlo_observation":pre_result,"PGOOD":pg,
        "VIN_reference_crossings":refs,
        "source_off_observation":off_observation,
        "switch_control_crossings":event_brackets(t,V("sw_ctl"),.5,{"source_current_A":I("Vsupply")}),
        "capacitor_checks":cap_metrics,"energy_ledger":energy,"settling_windows":settle,"settled_over_declared_windows":all(x["passed"] for x in settle),
        "claim_limits":["No hidden UVLO/sleep state observation","No macro internal storage/loss split","No historical native-run authentication","No physical or mission qualification"],
        "analysis_is_execution_authorization":False}

def validate_receipt(receipt,case_id,plan,root=ROOT):
    required=set(plan["run_receipt_required"])
    missing=required-set(receipt)
    if missing: raise EvidenceError("INCOMPLETE_RUN_RECEIPT:"+",".join(sorted(missing)))
    if receipt["case_id"]!=case_id or type(receipt["process_returncode"]) is not int or receipt["process_returncode"]!=0: raise EvidenceError("RUN_NOT_SUCCESSFULLY_COMPLETED")
    elapsed=receipt["elapsed_s"]
    if type(elapsed) not in (int,float) or not np.isfinite(elapsed) or elapsed<=0 or elapsed>plan["budget"]["max_elapsed_s_per_attempt"]: raise EvidenceError("RUN_ELAPSED_BUDGET")
    if receipt["plan_sha256"]!=hashlib.sha256((Path(root)/"EXACT-PLAN.json").read_bytes()).hexdigest(): raise EvidenceError("PLAN_RECEIPT_MISMATCH")
    iface=json.loads((Path(root)/"contracts/native-model-interface-v2.json").read_text())
    if receipt["deck_sha256"]!=plan["cases"][case_id]["deck_sha256"]: raise EvidenceError("DECK_RECEIPT_MISMATCH")
    for key in ("model","symbol","executable"):
        if receipt[key+"_sha256"]!=iface["artifacts"][key]["sha256"]: raise EvidenceError("RUN_IDENTITY_MISMATCH:"+key)
    for key in ("raw","log"):
        path=Path(receipt[key+"_path"])
        if not path.is_file(): raise EvidenceError("RETAINED_FILE_MISSING:"+key)
        if key=="raw" and path.stat().st_size>plan["budget"]["max_raw_bytes_per_attempt"]: raise EvidenceError("RAW_BUDGET_EXCEEDED")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt[key+"_sha256"]: raise EvidenceError("RETAINED_HASH_MISMATCH:"+key)
    for key in ("rc_smoke_review_reference","exact_plan_authorization_reference"):
        if not isinstance(receipt[key],str) or not receipt[key].strip(): raise EvidenceError("MISSING_WORKFLOW_REFERENCE:"+key)
    # References bind evidence; this reader cannot grant or independently authenticate authorization.
    return True

if __name__=="__main__":
    pa=argparse.ArgumentParser();pa.add_argument("--case",required=True);pa.add_argument("--receipt",type=Path,required=True);pa.add_argument("--output",type=Path,required=True)
    args=pa.parse_args()
    if args.output.exists(): raise EvidenceError("OUTPUT_EXISTS_PRESERVE_PRIOR_RESULT")
    plan=json.loads((ROOT/"EXACT-PLAN.json").read_text());receipt=json.loads(args.receipt.read_text())
    validate_receipt(receipt,args.case,plan)
    log=require_finished_log(receipt["log_path"],["vin_peak","vout_peak","vin2_peak"])
    raw=read_raw(receipt["raw_path"]);result=analyze_trace(raw,args.case,plan)
    for name,channel in [("vin_peak","v(vin)"),("vout_peak","v(out)"),("vin2_peak","v(vin2)")]:
        measured=log["measures"][name];actual=float(np.max(raw.columns[channel]))
        if abs(measured-actual)>max(1e-6,5e-4*abs(actual)): raise EvidenceError("MEAS_RAW_MISMATCH:"+name)
    result["run_receipt"]=receipt;result["native_log"]=log
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")

