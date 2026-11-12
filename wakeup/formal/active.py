"""E2: identical terminal observations, opposite physical repair directions.

These are controlled one-axis slices, calibrated with complete transient runs.
The declared precision and physical tail bounds are recorded with each pair.
"""
import copy
import json
from pathlib import Path
import numpy as np
from common import baseline, TASK, full, compact, save
from feedback import project

HERE = Path(__file__).resolve().parent


def build(seed=20261113, pairs=16):
    rng = np.random.default_rng(seed)
    result = []
    for axis in ("capacitance", "mass"):
        for i in range(pairs):
            env = copy.deepcopy(TASK)
            env["background_peak_g"] *= float(rng.uniform(.995, 1.005))
            env["fault_peak_g"] *= float(rng.uniform(.99, 1.01))
            base = baseline()
            if axis == "capacitance":
                base["circuit"]["storage_uF"] = 400.
                latent = (float(rng.uniform(.13, .15)), float(rng.uniform(1.5, 1.65)))
                field, domain = "storage_uF", [80., 1200.]
                target = 150.
            else:
                latent = (-float(rng.uniform(.75, 1.05)), float(rng.uniform(.75, 1.05)))
                field, domain = "tip_mass_g", [2., 7.]
                target = 4.65
            halves = []
            for direction, factor in zip(("increase", "decrease"), latent):
                witness = copy.deepcopy(base)
                part = "circuit" if axis == "capacitance" else "harvester"
                witness[part][field] = target / factor if axis == "capacitance" else target - factor
                halves.append(dict(direction=direction, latent=factor, witness=witness))
            result.append(dict(id=f"E2-{axis}-{i+1:02}", axis=axis, seed=seed,
                public=dict(initial=base, environment=env, axis=axis, domain={field:domain},
                    fixed_other_variables=True, diagnostic_cost=.2,
                    unknown_realization="effective storage-bank factor" if axis == "capacitance" else "tip-mass attachment offset",
                    diagnose_returns="actual storage capacitance / stage trace" if axis == "capacitance" else "actual loaded mechanical amplitude and phase"),
                private=dict(halves=halves),
                scope_note="Large storage factors are bank realization faults, NOT ordinary capacitor manufacturing tolerance." if axis == "capacitance" else "Independent signed attachment mass offsets, not different nominal equations."))
    return result


def realize(pair, half, design):
    d = copy.deepcopy(design)
    if pair["axis"] == "capacitance":
        d["circuit"]["storage_uF"] *= half["latent"]
    else:
        d["harvester"]["tip_mass_g"] += half["latent"]
    return d


def diagnose(pair, half_index, result):
    """Facts from a capacitance measurement or the recorded loaded voltage; no action advice."""
    half = pair["private"]["halves"][half_index]
    if pair["axis"] == "capacitance":
        value = pair["public"]["initial"]["circuit"]["storage_uF"] * half["latent"]
        return dict(effective_storage_uF=value, stage_counts=result["measurements"]["stages"], cost=.2)
    return dict(loaded_phase=result["measurements"]["phase"]["main"],cost=.2)


def job(item):
    pair, index, which = item
    halves = pair["private"]["halves"]
    half = halves[index]
    design = pair["public"]["initial"] if which == "initial" else halves[index if which == "witness" else 1-index]["witness"]
    actual = realize(pair, half, design)
    if which == "witness":
        known=json.loads((HERE/"outputs/e2_common_witness.json").read_text())
        return dict(id=pair["id"],half=index,direction=half["direction"],which=which,
            design=design,realized_design=baseline(),result=known["result"],gateway=known["gateway"],
            reused=True,source=known["source"],identity=known["identity"])
    r = full(actual, pair["public"]["environment"])
    return dict(id=pair["id"], half=index, direction=half["direction"], which=which,
                design=design, realized_design=actual, result=compact(r), gateway=project(r,0),reused=False)


def energy_upper(design, horizon):
    """Passive total energy bound, independent of capacitor or rectifier trajectory."""
    from sim import beam, G
    coefficient=sum(beam(design[k])["forcing_mass"]**2/(4*beam(design[k])["c"]) for k in ("harvester","trigger_beam"))
    norms=[TASK["background_peak_g"]*G*np.sqrt(horizon/2+1/(8*np.pi*TASK["background_Hz"]))]
    for kind in ("fault","nuisance"):
        for start in TASK[kind+"_starts_s"]:
            dt=max(0.,min(TASK[kind+"_duration_s"],horizon-start))
            if dt:
                norms.append(TASK[kind+"_peak_g"]*G*np.sqrt(dt/2+1/(8*np.pi*TASK[kind+"_Hz"])))
    return float(coefficient*sum(norms)**2)


def numeric_job(item):
    axis,value,round_,resolution=item
    d=baseline()
    d["circuit" if axis=="capacitance" else "harvester"]["storage_uF" if axis=="capacitance" else "tip_mass_g"]=value
    r=full(d,TASK,**resolution)
    return dict(axis=axis,value=value,round=round_,resolution=resolution,result=compact(r))


def bands(rows, axis):
    xs=sorted((r for r in rows if r.get("axis")==axis and r.get("round") in ("coarse","offset","boundary")),key=lambda r:r["value"])
    result=[]; i=0
    while i<len(xs):
        if xs[i]["result"]["verdict"]!="PASS":
            i+=1;continue
        first=i
        while i+1<len(xs) and xs[i+1]["result"]["verdict"]=="PASS":i+=1
        result.append(dict(inner=[xs[first]["value"],xs[i]["value"]],
            outer=[xs[first-1]["value"] if first else xs[first]["value"],xs[i+1]["value"] if i+1<len(xs) else xs[i]["value"]]))
        i+=1
    return result


def calibrate(workers=4,pairs=16):
    """One shared physical axis scan, then exact reparameterization of all pairs."""
    import time
    from concurrent.futures import ProcessPoolExecutor
    from scipy.optimize import brentq
    out=HERE/"outputs"; started=time.perf_counter()
    # Preserve prior counterfactual-only evidence; final artifacts get the canonical names.
    for name in ("tasks.json","public_tasks.json","calibration.jsonl","summary.json"):
        p=out/("e2_"+name)
        if p.exists() and not (out/("e2_development_"+name)).exists():p.rename(out/("e2_development_"+name))
    tasks=build(pairs=pairs)
    for p in tasks:p["public"]["environment"]=copy.deepcopy(TASK)
    order=np.random.default_rng(20261115).random(len(tasks))<.5
    for p,swap in zip(tasks,order):
        if swap:p["private"]["halves"].reverse()
    save(out/"e2_tasks.json",tasks);save(out/"e2_public_tasks.json",[{"id":p["id"],**p["public"]} for p in tasks])
    horizon=TASK["fault_starts_s"][0]+TASK["delivery_deadline_s"]
    d=baseline(); startup=.5*(d["circuit"]["start_V"]**2)
    capmax=energy_upper(d,horizon)/startup*1e6
    def mass_gap(m):
        dd=baseline();dd["harvester"]["tip_mass_g"]=m
        return energy_upper(dd,horizon)-.5*150e-6*d["circuit"]["start_V"]**2
    massmin=float(brentq(mass_gap,.05,4.65))
    cf=[h["latent"] for p in tasks if p["axis"]=="capacitance" for h in p["private"]["halves"]]
    mf=[h["latent"] for p in tasks if p["axis"]=="mass" for h in p["private"]["halves"]]
    ranges={"capacitance":[80*min(cf),capmax],"mass":[max(2+min(mf),massmin),7+max(mf)]}
    steps={"capacitance":10.,"mass":.1}
    rows=[]; counter=0
    with ProcessPoolExecutor(workers) as pool,(out/"e2_axis_validation.jsonl").open("w") as stream:
        def collect(jobs):
            nonlocal counter
            for r in pool.map(numeric_job,jobs):
                rows.append(r);counter+=1;stream.write(json.dumps(r)+"\n");stream.flush()
                if counter%20==0:print("E2 axis",counter,r["axis"],r["value"],r["result"]["verdict"],flush=True)
        jobs=[]
        for axis,(lo,hi) in ranges.items():
            grid=np.arange(lo,hi,steps[axis]); grid=np.unique(np.r_[grid,hi])
            jobs += [(axis,float(v),"coarse",{}) for v in grid]
            jobs += [(axis,float((a+b)/2),"offset",dict(rtol=1e-6,max_step=.000125)) for a,b in zip(grid[:-1],grid[1:])]
        collect(jobs)
        # Every observed transition is bisected; newly found islands remain separate bands.
        brackets=[]
        for axis in ranges:
            xx=sorted([r for r in rows if r["axis"]==axis],key=lambda r:r["value"])
            brackets += [(axis,a["value"],b["value"],a["result"]["verdict"]=="PASS")
                         for a,b in zip(xx[:-1],xx[1:]) if a["result"]["verdict"]!=b["result"]["verdict"]]
        for iteration in range(7):
            mids=[(axis,(lo+hi)/2,"boundary",dict(rtol=1e-6,max_step=.000125)) for axis,lo,hi,leftpass in brackets]
            before=len(rows);collect(mids)
            updated=[]
            for (axis,lo,hi,leftpass),r in zip(brackets,rows[before:]):
                mid=(lo+hi)/2
                updated.append((axis,mid,hi,leftpass) if (r["result"]["verdict"]=="PASS")==leftpass else (axis,lo,mid,leftpass))
            brackets=updated
        physical={axis:bands(rows,axis) for axis in ranges}
        repeat_jobs=[]
        for axis,bs in physical.items():
            for b in bs:
                repeat_jobs += [(axis,float(v),"independent_resolution",dict(rtol=5e-7,max_step=.0000625))
                                for v in (b["outer"][0],b["inner"][0],sum(b["inner"])/2,b["inner"][1],b["outer"][1])]
        collect(repeat_jobs)
        save(out/"e2_axis_bands.json",dict(ranges=ranges,grid_max_gap={k:v/2 for k,v in steps.items()},
            bands=physical,brackets=brackets,physical_exclusion=dict(capacitor_above_uF=capmax,mass_below_g=massmin,
            horizon_s=horizon,energy_upper_J=energy_upper(d,horizon),
            proof="dE/dt=-a*mf*v-c*v^2-loss <= a^2*mf^2/(4c); integrate both modes with triangle L2 bound; zero initial energy and nonnegative loads."),
            interpretation="Numerical interval calibration at stated resolution with an offset grid, transition bisection, and tighter independent reruns. Not a validated-interval-ODE mathematical proof."))
    # One common actual witness, not 64 identical numerical reruns.
    reference=full(baseline(),TASK);counter+=1
    save(out/"e2_common_witness.json",dict(result=compact(reference),gateway=project(reference,0),
        source="one shared full baseline execution in this calibration",
        identity="All direction-specific witnesses algebraically realize baseline(); same TASK and physical consumer."))
    # Initial observations and crossed witnesses remain distinct real executions.
    jobs=[(p,i,w) for p in tasks for i in (0,1) for w in ("initial","witness","opposite_witness")]
    points=[]
    with ProcessPoolExecutor(workers) as pool,(out/"e2_calibration.jsonl").open("w") as stream:
        for r in pool.map(job,jobs):
            counter+=not r.get("reused",False);points.append(r);stream.write(json.dumps(r)+"\n");stream.flush()
            if len(points)%20==0:print("E2 pairs",len(points),r["id"],flush=True)
    repeat_checks=[dict(axis=r["axis"],value=r["value"],pass_=r["result"]["verdict"]=="PASS",
        expected=any(b["inner"][0]<=r["value"]<=b["inner"][1] for b in physical[r["axis"]]))
        for r in rows if r.get("round")=="independent_resolution"]
    resolution_stable=all(r["pass_"]==r["expected"] for r in repeat_checks)
    status=[]
    for p in tasks:
        rr=[r for r in points if r["id"]==p["id"]]
        init=[r for r in rr if r["which"]=="initial"]
        good=[r for r in rr if r["which"]=="witness"]
        wrong=[r for r in rr if r["which"]=="opposite_witness"]
        transformed=[]
        for h in p["private"]["halves"]:
            transform=lambda x:x/h["latent"] if p["axis"]=="capacitance" else x-h["latent"]
            domain=next(iter(p["public"]["domain"].values()))
            mapped=[]
            for b in physical[p["axis"]]:
                inner=[max(domain[0],transform(b["inner"][0])),min(domain[1],transform(b["inner"][1]))]
                outer=[max(domain[0],transform(b["outer"][0])),min(domain[1],transform(b["outer"][1]))]
                if outer[0]<=outer[1]:mapped.append(dict(inner=inner,outer=outer,
                    direction=h["direction"],realization_factor=h["latent"]))
            transformed.append(mapped)
        separated=all(a["outer"][1]<b["outer"][0] or b["outer"][1]<a["outer"][0] for a in transformed[0] for b in transformed[1])
        gaps=[max(a["outer"][0]-b["outer"][1],b["outer"][0]-a["outer"][1]) for a in transformed[0] for b in transformed[1]]
        matched=init[0]["gateway"]==init[1]["gateway"] and all(r["result"]["metrics"]["delivered_on_time"]==0 for r in init)
        passes=all(r["result"]["verdict"]=="PASS" for r in good)
        rejects=all(r["result"]["verdict"]=="FAIL" for r in wrong)
        status.append(dict(id=p["id"],axis=p["axis"],matched_F0=matched,both_witnesses_pass=passes,
            opposite_witnesses_fail=rejects, feasible_intervals=transformed,minimum_outer_gap=min(gaps),
            numerically_disjoint=separated,qualified=matched and passes and rejects and separated and resolution_stable))
    summary=dict(pairs=len(tasks),halves=2*len(tasks),full_calls=counter,wall_s=time.perf_counter()-started,
        new_full_calls=counter,exact_input_reuses=sum(r.get("reused",False) for r in points),
        total_evaluations=len(rows)+len(points)+1,
        half_order_seed=20261115,
        status=status,qualified=sum(s["qualified"] for s in status),physical_intervals=physical,
        grid_max_gap={k:v/2 for k,v in steps.items()},repeat_checks=repeat_checks,resolution_stable=resolution_stable,
        tight_repeat_source=dict(path="outputs/e2_axis_validation.jsonl",round="independent_resolution",count=len(repeat_checks)),
        claim="Engineering numerical qualification of the declared fixed single-axis domains; not a theorem over freely editable full designs.",
        independence="32 independently drawn realization-factor pairs, one common physical environment. Halves are paired, not independent samples.")
    save(out/"e2_summary.json",summary)
    return summary


if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--pairs",type=int,default=16);p.add_argument("--workers",type=int,default=4)
    a=p.parse_args();print(calibrate(a.workers,a.pairs))
