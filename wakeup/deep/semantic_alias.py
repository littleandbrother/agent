"""Axes 1/2: physical connection choices and indistinguishable end symptoms."""
import copy
import json
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sim import TASK, simulate

BASE = json.loads((Path(__file__).resolve().parents[1]/"design.json").read_text())
CACHE = {}
NUMERIC = dict(main_length_mm=[24., 42.], aux_length_mm=[11., 24.], C_uF=[80., 500.], gate_V=[2., 3.2], threshold_V=[.15, 1.])
INITIAL = dict(main_length_mm=30., aux_length_mm=18., C_uF=150., gate_V=2.9, threshold_V=.55)


def tasks():
    common = dict(axis=1, initial=INITIAL, domain=NUMERIC, fast_available=False,
                  description="Deliver all four 210-Hz abnormal events by 250 ms; reject 250-Hz interference; remain within 40 MPa and 1.5 mm.",
                  spec=dict(duration_s=30, input="45 Hz / .15g background, 210 Hz / .5g / 150ms target; 250Hz / .8g / 200ms nuisance",
                            acquisition="128 points at 2048Hz, actual ADC and spectral confirmation", supply="Initially empty storage, 1.8V brownout",
                            main_beam="10mm wide steel/PZT bimorph, .15mm substrate and .12mm layers,4.65g tip mass",
                            aux_beam="6mm wide, .10mm substrate/.08mm PZT layers,.14g tip mass",
                            circuit="Diode rectifier; auxiliary voltage can enter RC envelope detector; comparator can gate MCU; otherwise MCU polls at100ms. Installed auxiliary beam and RC loads participate in coupled ODE.",
                            primitive_cost="Additional beam has mechanical response and input loading; envelope has2nF capacitance,100kohm charge path,20Mohm bleed; no free constructed delivery bit."),
                  diagnostic="A failed design may originate at mechanical input, stored supply, analog observation or digital execution; terminal delivery alone does not identify the cause.")
    named = copy.deepcopy(common);named.update(id="P1_named", initial=INITIAL|dict(passive_wakeup=False), domain=NUMERIC|dict(passive_wakeup=[False,True]), _physical={})
    wired = copy.deepcopy(common);wired.update(id="P1_primitives", initial=INITIAL|dict(aux_resonator=False,detector_source="none",mcu_gate="poll"),
          domain=NUMERIC|dict(aux_resonator=[False,True],detector_source=["none","aux","harvester"],mcu_gate=["poll","envelope"]), _physical={})
    alias=[]
    for ident, variation in (("P2_unit_u",dict(main_factor=.75)),("P2_unit_v",dict(aux_factor=1.4))):
        t=copy.deepcopy(common);t.update(id=ident,axis=2,initial=INITIAL.copy(),domain=copy.deepcopy(NUMERIC),_physical=variation)
        t["description"]="The receiver observes0/4 delivered and0 false reports. Locate and repair the failure using design interventions or physical measurements. Same four-event service."
        t["spec"]["uncertainty"]="The device has an unmeasured effective-length variation in one beam due to fabrication or mounting. Knobs are nominal lengths; power/trigger/program measurements reveal realized behavior. Variation is unchanged during a trajectory."
        alias.append(t)
    return [named,wired]+alias


def _design(task,x):
    d=copy.deepcopy(BASE);v=task["_physical"]
    d["harvester"]["length_mm"]=x["main_length_mm"]*v.get("main_factor",1.)
    d["trigger_beam"]["length_mm"]=x["aux_length_mm"]*v.get("aux_factor",1.)
    d["circuit"].update(storage_uF=x["C_uF"],start_V=x["gate_V"],wake_high_V=x["threshold_V"],wake_low_V=x["threshold_V"]*.33)
    if task["axis"]==1:
        if "passive_wakeup" in x:
            on=x["passive_wakeup"];connection=dict(aux_resonator=on,detector_source="aux" if on else "none",mcu_gate="envelope" if on else "poll")
        else:connection={k:x[k] for k in ("aux_resonator","detector_source","mcu_gate")}
        d["connections"]=connection
        d["modules"]=dict(A=connection["aux_resonator"],B=False,C=False,D=False)
    d["firmware"]["poll_s"]=.1
    return d


def evaluate(task,design,fidelity="full",observation=None):
    d=_design(task,design);key=json.dumps(d,sort_keys=True)
    cached=key in CACHE
    if not cached:CACHE[key]=simulate(d,TASK)
    r=CACHE[key];m=r["metrics"];tr=r["trace"];y=np.asarray(tr["y"]);times=np.asarray(tr["t"])
    metrics=dict(delivered=m["delivered_on_time"],expected=m["faults"],false_reports=m["false_reports"],brownouts=m["brownouts"])
    if observation=="power":
        metrics.update(max_storage_V=float(y[:,6].max()),storage_before_first_event_V=float(y[np.searchsorted(times,7.99),6]),
                       final_storage_V=m["final_storage_V"],main_peak_voltage_V=float(abs(y[:,2]).max()),cold_charge_ready_s=m["cold_charge_ready_s"],energy_J=r["energy_J"])
    elif observation=="trigger":
        metrics.update(aux_peak_voltage_V=float(abs(y[:,5]).max()),envelope_peak_V=float(y[:,7].max()),wakeups=m["wakeups"],first_wake_s=m["first_wake_s"])
    elif observation=="program":
        metrics.update(wakeups=m["wakeups"],stages={k:sum(e["event"]==k for e in r["events"]) for k in ("WAKE","SAMPLE","CONFIRM","REJECT","TX","RECEIVED","BROWNOUT")},peak_stress_MPa=m["peak_stress_MPa"],peak_tip_mm=m["peak_tip_mm"],minimum_active_storage_V=m["minimum_active_storage_V"])
    return dict(pass_=r["verdict"]=="PASS",metrics=metrics,slack=dict(delivery=m["delivered_on_time"]/m["faults"]-1,false_reports=-m["false_reports"]),
                cost=dict(full=0 if cached else 1,numeric=0),fidelity="full transient",cached=cached)


if __name__=="__main__":
    rows=[]
    for t in tasks():
        x=t["initial"].copy();initial=evaluate(t,x)
        if t["axis"]==1:
            fixed=x|({"passive_wakeup":True} if "passive_wakeup" in x else dict(aux_resonator=True,detector_source="aux",mcu_gate="envelope"))
        elif t["id"]=="P2_unit_u":fixed=x|dict(main_length_mm=40.)
        else:fixed=x|dict(aux_length_mm=18/1.4)
        final=evaluate(t,fixed);row=dict(id=t["id"],axis=t["axis"],physical_factors=t["_physical"],task=TASK,initial_input=x,initial=initial,
            power=evaluate(t,x,observation="power"),trigger=evaluate(t,x,observation="trigger"),program=evaluate(t,x,observation="program"),witness_input=fixed,witness=final,
            scope="Naming and action factorization jointly vary; not a label-only ablation" if t["axis"]==1 else "Two causes only, not four; stationary hidden fabrication/mounting factors.")
        if t["id"]=="P1_primitives":
            partials=[x|patch for patch in (dict(aux_resonator=True,detector_source="aux",mcu_gate="poll"),dict(aux_resonator=True,detector_source="none",mcu_gate="envelope"))]
            row["partial_wiring"]=[dict(design=z,result=evaluate(t,z)) for z in partials]
        elif t["axis"]==2:
            wrong=x|(dict(aux_length_mm=18/1.4) if t["id"]=="P2_unit_u" else dict(main_length_mm=40.))
            row.update(other_instance_repair_input=wrong,other_instance_repair_result=evaluate(t,wrong))
        rows.append(row);print(t["id"],initial["metrics"],"witness",final["pass_"],final["metrics"],flush=True)
    out=Path(__file__).with_name("semantic_alias_qualification.json");out.write_text(json.dumps(rows,indent=2));print(out)
