"""Four physical probes: detuning, short precheck, rearm and rearm+burst.
No provider client or alternate state machine; complete results use sim.simulate.
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sim import TASK, simulate

HERE = Path(__file__).resolve().parent
BASE = json.loads((HERE.parent / "design.json").read_text())
CACHE = {}


def tasks():
    domain = dict(A=[False, True], mass_g=[2., 5.], h=[.9, 1.1], C_uF=[50., 400.],
                  gate_V=[1.9, 3.2], discharge_Mohm=[1., 20000.], wake_V=[.2, 1.2],
                  input_series_kohm=[.5, 20.], poll_ms=[15., 200.])
    initial = dict(A=True, mass_g=4.65, h=1., C_uF=150., gate_V=2.9,
                   discharge_Mohm=20., wake_V=.55, input_series_kohm=5., poll_ms=100.)
    spec = dict(parameters=dict(A="auxiliary resonator/envelope/comparator connected to MCU power",
                mass_g="main harvester end mass", h="multiplier of both main beam layer thicknesses",
                C_uF="storage capacitance", gate_V="MCU start voltage; brownout1.8V",
                discharge_Mohm="envelope discharge resistance", wake_V="comparator high voltage; low=.33high",
                input_series_kohm="diode bridge series resistance", poll_ms="poll interval without auxiliary front end"),
                acquisition="128 actual ADC samples at2048Hz; target195-225Hz; .25s delivery deadline",
                constraints="all targets on time, no false reports, no brownout, stress<=40MPa, travel<=1.5mm",
                observations=["power", "trigger", "program"], fast_evaluator=False)
    descriptions = [
        ("P3-detune",3,"Strong45Hz background and210Hz target; existing enclosure excludes added shunt hardware.",
         dict(background_peak_g=.8, fault_peak_g=2.), {}),
        ("P3-peek",3,"No auxiliary hardware fits; software may precheck before the unchanged128point frequency classifier.",
         dict(background_peak_g=.16),dict(A=False,peek_ms=0.,peek_threshold_g=.3)),
        ("P4-rearm",4,"Two target events require one coupled node to acquire, classify and deliver both.",
         {},dict(A=False,discharge_Mohm=20000.)),
        ("P4-rearm-burst",4,"Two target events with a small initial energy buffer; all delivery requirements remain.",
         {},dict(A=False,C_uF=50.,discharge_Mohm=20000.)),
    ]
    rows=[]
    for name,axis,description,changes,patch in descriptions:
        physical=dict(TASK,duration_s=11.,fault_starts_s=[8.,10.],nuisance_starts_s=[9.],**changes)
        d=domain.copy(); x=initial|patch
        if name=="P3-peek":
            d.pop("A");d|=dict(peek_ms=[0.,3.],peek_threshold_g=[.05,1.])
        rows.append(dict(id=name,axis=axis,description=description,initial=x,domain=d,
                         spec=spec|dict(environment={k:physical[k] for k in ("background_Hz","background_peak_g","fault_Hz","fault_peak_g","fault_duration_s","delivery_deadline_s")},event_gap_s=2.,cold_start_at_s=0.,first_event_not_before_s=8.,nuisance_Hz=250.,nuisance_peak_g=.8,
                                        implementation="same ODE, rectifier, sampled waveform classifier and actual program loads",
                                        precheck=dict(peek_ms="optional sensor RMS acquisition in milliseconds before unchanged FFT",peek_threshold_g="RMS below this skips full acquisition",peek_mW=3.,boot_energy_uJ=6.)),
                         diagnostic="Failure of one parameter vector cannot exclude a topology. Mechanical response, power storage and analog reset evolve together.",
                         _task=physical))
    return rows


def design(t, x):
    d=copy.deepcopy(BASE)
    d["modules"]=dict(A=x["A"],B=False,C=False,D=False)
    d["harvester"]|=dict(tip_mass_g=x["mass_g"],substrate_mm=.15*x["h"],piezo_layer_mm=.12*x["h"])
    d["circuit"]|=dict(storage_uF=x["C_uF"],start_V=x["gate_V"],
                          envelope_discharge_ohm=x["discharge_Mohm"]*1e6,
                          wake_high_V=x["wake_V"],wake_low_V=x["wake_V"]*.33,
                          bridge_series_ohm=x["input_series_kohm"]*1000)
    d["firmware"]|=dict(poll_s=x["poll_ms"]/1000)
    if t["id"]=="P3-peek":
        d["firmware"]|=dict(peek_window_s=x["peek_ms"]/1000,peek_threshold_g=x["peek_threshold_g"],peek_mW=3.)
    return d


def evaluate(t, x, fidelity="full", observation=None):
    if fidelity!="full":
        return dict(pass_=False,slack={},metrics=dict(not_executed="No qualified cheap classifier/rearm model for this probe"),
                    cost=dict(full=0,numeric=0),fidelity="unavailable")
    d = design(t,x); key = json.dumps([d,t["_task"]],sort_keys=True)
    cached = key in CACHE
    if not cached:
        CACHE[key] = simulate(d,t["_task"])
        CACHE[key].pop("trace")
    r=CACHE[key];m=r["metrics"]
    slack=dict(delivery=m["delivered_on_time"]/m["faults"]-1,
               stress=1-m["peak_stress_MPa"]/t["_task"]["stress_limit_MPa"],
               travel=1-m["peak_tip_mm"]/t["_task"]["tip_travel_limit_mm"],
               no_false_reports=-m["false_reports"],no_brownouts=-m["brownouts"])
    if observation=="power":
        visible={k:m[k] for k in ("cold_charge_ready_s","minimum_active_storage_V","final_storage_V","brownouts")}
    elif observation=="trigger":
        visible={k:m[k] for k in ("wakeups","first_wake_s","missed_fault_starts_s")}
    elif observation=="program":
        visible=dict(event_counts={k:sum(e["event"]==k for e in r["events"]) for k in ("WAKE","SAMPLE","CONFIRM","REJECT","TX","RECEIVED","BROWNOUT")})
    else:visible=m|dict(checks=r["checks"])
    return dict(pass_=r["verdict"]=="PASS",slack=slack,metrics=visible,
                cost=dict(full=0 if cached else 1,numeric=0,runtime_s=0. if cached else r["runtime_s"],cached=cached),fidelity="full-transient")
