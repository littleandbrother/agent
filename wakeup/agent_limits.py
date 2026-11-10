"""One-file boundary pilot: --calibrate, then --agents. No dependency on the old harness."""
import argparse
import concurrent.futures
import copy
import inspect
import json
import os
import time
import threading
import urllib.request
from pathlib import Path

import numpy as np
from scipy.stats import qmc
from sim import G, beam

HERE = Path(__file__).resolve().parent
OUT = HERE / "limits"
BASE = json.loads((HERE / "design.json").read_text())
# LHS is uniform in the coordinates explicitly listed here; rates depend on this measure.
DOMAIN = dict(C_uF=(50, 1500, "log"), R_kohm=(2, 300, "log"), h=(.85, 1.15, "linear"),
              mass_g=(3.5, 5.8, "linear"), L2_mm=(15, 22, "linear"), m2_g=(.08, .28, "linear"),
              gate_V=(1.9, 3.2, "linear"), poll_ms=(15, 400, "log"), shunt_kohm=(.5, 100, "log"),
              shield_V=(5, 50, "log"), trigger_V=(.2, 1.2, "linear"), sample_ms=(25, 80, "linear"))
DEFAULT = dict(C_uF=75., R_kohm=45., h=1., mass_g=4.65, L2_mm=18., m2_g=.14,
               gate_V=2.9, poll_ms=100., shunt_kohm=3., shield_V=15., trigger_V=.55, sample_ms=62.5,
               A=False, B=False, C=False, D=False)
MODULES = dict(A=dict(description="passive tuned trigger beam + comparator", idle_uW=.5, area_mm2=15),
               B=dict(description="active filter wake-up, gain 2 V/g", idle_uW=180., area_mm2=18),
               C=dict(description="additional off-chip FRAM, 5 uJ per write", idle_uW=2., area_mm2=40),
               D=dict(description="voltage-triggered parallel resistive shunt", idle_uW=.5, area_mm2=12))
N, SEED, STEPS, USD_CAP = 10000, 20261110, 6, 2.


def sample(n, seed):
    u = qmc.LatinHypercube(len(DOMAIN) + 4, seed=seed).random(n)
    x = {k: np.exp(np.log(a) + u[:, i] * np.log(b/a)) if scale == "log" else a + u[:, i]*(b-a)
         for i, (k, (a, b, scale)) in enumerate(DOMAIN.items())}
    return dict(x, **{k: u[:, len(DOMAIN)+i] >= .5 for i, k in enumerate(MODULES)})


def mechanics(x):
    d = dict(BASE["harvester"], substrate_mm=.15*x["h"], piezo_layer_mm=.12*x["h"], tip_mass_g=x["mass_g"])
    return beam(d)


def response(b, hz, amplitude_g, resistance):
    w = 2*np.pi*hz
    z = b["k"]-b["m"]*w*w + 1j*w*b["c"] + b["theta"]**2*1j*w/(1/resistance+1j*w*b["cp"])
    q = b["forcing_mass"]*amplitude_g*G/np.abs(z)
    v = b["theta"]*w*q/np.abs(1/resistance+1j*w*b["cp"])
    return q, v


def oracle(t, x):
    """Harmonic reduced-order screen, NOT sim.py's transient diode/program consumer.
    Resistive extraction efficiency=.65; shock is a settled high-amplitude sinusoid.
    D latches on an observed open-switch voltage crossing, with negligible switching delay.
    """
    b, r = mechanics(x), x["R_kohm"]*1000
    qb, vb = response(b, t["background_Hz"], t["background_g"], r)
    engaged = np.asarray(x["D"]) & (vb > x["shield_V"])
    rl = 1/(1/r + engaged/(x["shunt_kohm"]*1000))
    qb, vb = response(b, t["background_Hz"], t["background_g"], rl)
    power = .65*vb*vb/(2*r)  # current diverted through the shunt is not harvested
    qh, vh = response(b, t["event_Hz"], t["event_g"], r)
    rh = 1/(1/r + (np.asarray(x["D"]) & (vh > x["shield_V"]))/ (x["shunt_kohm"]*1000))
    qh, vh = response(b, t["event_Hz"], t["event_g"], rh)
    idle = (1.4 + sum(np.asarray(x[k])*v["idle_uW"] for k,v in MODULES.items()))*1e-6
    packet = (.003*x["sample_ms"]/1000 + 68e-6 + np.asarray(x["C"])*5e-6)/.85
    active = np.asarray(x["A"]) | np.asarray(x["B"])
    if t["case"] == "wake":
        w = beam(dict(BASE["trigger_beam"], length_mm=x["L2_mm"], tip_mass_g=x["m2_g"]))
        qt, vt = response(w, t["event_Hz"], t["event_g"], 1e8)
        envelope = np.maximum(vt*(1-np.exp(-.03*2*np.pi*t["event_Hz"]*t["event_ms"]/1000))-.2, 0)
        envelope = np.where(x["B"], np.maximum(envelope*np.asarray(x["A"]), 2*t["event_g"]), envelope)
        capture = np.where(active, envelope/x["trigger_V"]-1, t["event_ms"]/(x["poll_ms"]+x["sample_ms"])-1)
        demand = np.where(active, packet/t["event_period_s"], .003*np.minimum(1, x["sample_ms"]/x["poll_ms"]))
        stress = np.maximum((qb+qh)*b["stress_per_m"], np.asarray(x["A"])*qt*w["stress_per_m"])/1e6
    else:
        capture, demand = vh/(x["gate_V"]+.3)-1, packet/t["event_period_s"]
        stress = qh*b["stress_per_m"]/1e6
    net = power-idle
    slack = dict(energy=(net-demand)/max(t["power_scale_W"], 1e-9),
                 cold_charge=2*net*t["ready_s"]/(x["C_uF"]*1e-6*x["gate_V"]**2)-1,
                 burst_energy=(.5*x["C_uF"]*1e-6*(x["gate_V"]**2-1.8**2)+net*(x["sample_ms"]+9.5)/1000)/packet-1,
                 capture=capture, adc_window=x["sample_ms"]*t["event_Hz"]/4000-1 if t["case"]=="wake" else x["sample_ms"]/10-1,
                 stress=1-stress/t["stress_MPa"],
                 area=1-(20+.03*x["C_uF"]+sum(np.asarray(x[k])*v["area_mm2"] for k,v in MODULES.items()))/t["area_mm2"],
                 rectifier_voltage=vb/(x["gate_V"]+.3)-1)
    return slack


def passed(s):
    return np.logical_and.reduce([np.asarray(v) >= 0 for v in s.values()])


def local_keys(t):
    return ("C_uF", "poll_ms") if t["case"]=="wake" else ("C_uF", "R_kohm")


def intervals(polynomials, lo=2000., hi=300000.):
    cuts = [lo, hi]
    for p in polynomials:
        cuts += [float(z.real) for z in np.roots(p) if abs(z.imag)<1e-6 and lo<z.real<hi]
    cuts = sorted(cuts)
    good=[[a,b] for a,b in zip(cuts[:-1],cuts[1:]) if all(np.polyval(p,(a+b)/2)>=0 for p in polynomials)]
    for z in cuts:  # retain feasible singleton roots, too
        if all(np.polyval(p,z)>=-1e-10*sum(abs(p[j])*z**(len(p)-j-1) for j in range(len(p))) for p in polynomials):
            if not any(a<=z<=b for a,b in good): good.append([z,z])
    return good


def certificate(t):
    """Necessary constraints in fixed P0; quadratic root partition, not gradient signs."""
    b, x = mechanics(DEFAULT), DEFAULT
    def coefficients(hz):
        w=2*np.pi*hz; k=b["k"]-b["m"]*w*w; c=w*b["c"]; a=b["theta"]**2/b["cp"]; beta=w*b["cp"]
        return np.array([((k+a)**2+c*c)*beta*beta, 2*c*a*beta, k*k+c*c]), w, beta
    d,w,beta=coefficients(t["background_Hz"]); f=b["forcing_mass"]*t["background_g"]*G
    packet=(.003*x["sample_ms"]/1000+68e-6)/.85
    # Optimistically credit harvesting throughout the packet: still a necessary cold-start bound.
    need=packet/(t["ready_s"]*(1-1.8**2/x["gate_V"]**2)+(x["sample_ms"]+9.5)/1000)+1.4e-6
    if t["case"]=="wake":
        poll_max=t["event_ms"]-x["sample_ms"]
        need=max(need, .003*min(1,x["sample_ms"]/max(poll_max,1e-9))+1.4e-6)
    polys=[-need*d+np.array([0,.65*b["theta"]**2*w*w*f*f/2,0])]
    if t["case"]=="impact":
        ds,ws,bs=coefficients(t["event_Hz"]); fs=b["forcing_mass"]*t["event_g"]*G
        polys.append((t["stress_MPa"]*1e6)**2*ds-(fs*b["stress_per_m"])**2*np.array([bs*bs,0,1]))
    feasible=intervals(polys)
    if t["case"]=="wake":
        r=x["R_kohm"]*1000
        feasible=[[r,r]] if all(np.polyval(p,r)>=0 for p in polys) else []
    return dict(scope="P0: only "+", ".join(local_keys(t))+" vary; harmonic oracle only", proved_empty=not feasible,
                necessary_R_intervals_ohm=feasible, power_lower_bound_W=need,
                excluded_constraints=["energy/cold_start", "stress"] if t["case"]=="impact" else ["energy/capture"])


def calibrate():
    started=time.perf_counter(); full=sample(N,SEED)
    rows=[]
    for i in range(15):
        kind="wake" if i<5 or i in (10,11) else "impact"
        t=dict(id=f"{kind}-{i+1:02}", case=kind, role="deadlock" if i<10 else "control",
               background_Hz=45., background_g=.13+.012*(i%5), event_Hz=(198+6*(i%5)) if kind=="wake" else 48+i%5,
               event_g=.5 if kind=="wake" else 3.+.4*(i%5), event_ms=150., event_period_s=60.,
               ready_s=12., stress_MPa=40., area_mm2=95., power_scale_W=100e-6)
        if i>=10:
            t.update(background_g=.35 if kind=="wake" else .16, event_g=.5 if kind=="wake" else .3+.02*(i%3),
                     event_ms=500., ready_s=60., stress_MPa=40.)
            if kind=="impact": t["event_Hz"]=44.8+.1*(i%3)
        local={k:full[k] if k in local_keys(t) else np.full(N,v) for k,v in DEFAULT.items()}
        candidates=[]
        for factor in ((1.,1.5,2.,2.5,3.) if i<5 else (1.,1.2,1.4) if i<10 else (1.,)):
            for ready in (8.,12.,20.,35.,60.,100.):
                stress_values=(40.,) if kind=="wake" or i>=10 else np.linspace(20,220,41)
                for stress in stress_values:
                    q=dict(t,background_g=t["background_g"]*factor,ready_s=ready,stress_MPa=float(stress)); cert=certificate(q)
                    if (i<10 and not cert["proved_empty"]) or (i>=10 and cert["proved_empty"]): continue
                    rho=float(passed(oracle(q,full)).mean()); r0=float(passed(oracle(q,local)).mean())
                    if i>=10 and r0==0: continue
                    candidates.append((abs(rho-.015),q,rho,r0,cert))
        if not candidates: rows.append(dict(task=t,status="NO_ADMISSIBLE_CALIBRATION")); continue
        _,t,rho,r0,cert=min(candidates,key=lambda z:z[0])
        fresh=sample(N,SEED+1); fresh_local={k:fresh[k] if k in local_keys(t) else np.full(N,v) for k,v in DEFAULT.items()}
        ok=passed(oracle(t,fresh)); j=np.flatnonzero(ok)
        witness={k:float(v[j[0]]) if k in DOMAIN else bool(v[j[0]]) for k,v in fresh.items()} if len(j) else None
        all_on=dict(fresh,**{k:np.ones(N,dtype=bool) for k in MODULES})
        measured=float(ok.mean()); r0=float(passed(oracle(t,fresh_local)).mean())
        rows.append(dict(task=t,status="IN_ZONE" if .005<=measured<=.03 else "OUTSIDE_TARGET_ZONE",rho_P0=r0,rho_full=measured,selection_rho=rho,
                         zero_hit_95_upper=1-.05**(1/N) if r0==0 else None,certificate=cert,
                         all_modules_enabled_rho=float(passed(oracle(t,all_on)).mean()),witness=witness))
    output=dict(seed=SEED,n=N,coordinates=DOMAIN,modules=MODULES,default=DEFAULT,tasks=rows,
                model="harmonic screen; representative .65 rectification efficiency, no impact transient qualification",
                calibration_policy="Choose closest 1.5% volume BEFORE model runs; do not select by model performance",
                runtime_s=time.perf_counter()-started)
    OUT.mkdir(exist_ok=True);(OUT/"calibration.json").write_text(json.dumps(output,indent=2))
    print(json.dumps({"runtime_s":output["runtime_s"],"tasks":[{k:r.get(k) for k in ["status","rho_P0","rho_full"]} for r in rows]},indent=2),flush=True)
    return output


def agents(feedback="slack"):
    calibration=json.loads((OUT/"calibration.json").read_text())
    log=OUT/"agents.jsonl"
    previous=[json.loads(s) for s in log.read_text().splitlines()] if log.exists() else []
    terminals={(r["task"],r["arm"]):r for r in previous if r["kind"]=="terminal"}
    sent={r["id"] for r in previous if r["kind"]=="request"}; received={r["id"] for r in previous if r["kind"]=="response"}
    if sent-received: raise SystemExit("An existing request has no settled usage; do not retry it.")
    prior_summary=json.loads((OUT/"summary.json").read_text()) if (OUT/"summary.json").exists() else {}
    prior_runtime=prior_summary.get("runtime_s",0.)
    max_output=16384
    key=os.environ.get("DEEPSEEK_API_KEY") or (Path.home()/".local/share/bf-campaign-20261019-s0/workbench/secrets/deepseek.key").read_text().strip()
    source="\n".join(inspect.getsource(f) for f in (beam,mechanics,response,oracle))
    rules={"Fixed-P0":"Only the two declared P0 variables can change.",
           "All-Open":"All variables are available immediately. This does NOT enable/install all modules. Choose freely.",
           "Free-Expand":"Start in P0, but you may immediately change any variable or module in the same call. No unlock overhead.",
           "Cert-Guided":"Expand beyond P0 only if the supplied necessary-bound certificate proves P0 empty; otherwise stay local."}
    common=dict(model="deepseek-flash",thinking="enabled",reasoning_effort="high",max_tokens=max_output,
                feedback=feedback,max_evaluations=STEPS,max_requests=360,usd_cap=USD_CAP,
                source=source,base_beams={k:BASE[k] for k in ["harvester","trigger_beam"]},
                G=G,domain=DOMAIN,modules=MODULES,rules=rules,initial=DEFAULT,
                rate_usd_per_million=dict(input=.30,output=1.20,cache=.006))
    common["output_limit_policy"]=("Initial 4096-token pilot retained. Only length-truncated episodes continue, with 16384 tokens and unchanged six-evaluation budget; complete episodes are not rerun." if previous else "16384-token ceiling, six design evaluations per trajectory.")
    (OUT/"agent_input.json").write_text(json.dumps(common,indent=2))
    lock,halt=threading.Lock(),threading.Event()
    answers=[r for r in previous if r["kind"]=="response"]
    tally=dict(spent=sum(r["estimated_usd"] for r in answers),reserved=0.,requests=len(sent),
               prompt_tokens=sum(r["response"]["usage"]["prompt_tokens"] for r in answers),
               completion_tokens=sum(r["response"]["usage"]["completion_tokens"] for r in answers),
               reasoning_tokens=sum(r["response"]["usage"].get("completion_tokens_details",{}).get("reasoning_tokens",0) for r in answers),
               cache_hit_tokens=sum(r["response"]["usage"].get("prompt_cache_hit_tokens",0) for r in answers))
    started=time.perf_counter()
    def emit(row):
        with lock:
            with log.open("a") as f: f.write(json.dumps(row,ensure_ascii=False)+"\n")
    def view(s):
        out={k:float(v) for k,v in s.items()}
        return dict(pass_=bool(passed(s)),**({"slack":out} if feedback=="slack" else {}))
    def run(row,arm):
        t=row["task"]; x=copy.deepcopy(DEFAULT); initial=view(oracle(t,x)); evaluated=0; error=None
        old=terminals.get((t["id"],arm))
        if old and (old.get("error")!="MODEL_OUTPUT_LENGTH" or old.get("output_limit",4096)>=max_output):return old
        messages=[dict(role="system",content="Design this physical node. You have six design evaluations. Use evaluate with a patch; no prose-only answer. Minimize unnecessary hardware while satisfying every constraint. All public equations and component facts follow.\n"+json.dumps({k:common[k] for k in ["source","base_beams","G","domain","modules"]})),
                  dict(role="user",content=json.dumps(dict(task=t,initial=x,initial_feedback=initial,P0=local_keys(t),condition=rules[arm],certificate=row["certificate"] if arm=="Cert-Guided" else None)))]
        if initial["pass_"]:
            emit(dict(kind="initial_pass",task=t["id"],arm=arm,design=x));return dict(task=t["id"],arm=arm,pass_=True,first_pass=0,evaluations=0)
        if old:
            x=old["final_design"].copy();evaluated=old["evaluations"]
            for r in previous:
                if r["kind"]!="response" or (r["task"],r["arm"])!=(t["id"],arm):continue
                m=r["response"]["choices"][0]["message"];calls=m.get("tool_calls",[])
                if not calls:continue
                messages.append(m)
                evaluations=[v for v in previous if v["kind"]=="evaluation" and (v["task"],v["arm"],v["step"])==(t["id"],arm,r["step"])]
                for j,c in enumerate(calls):
                    reply=evaluations[j]["feedback"] if j<len(evaluations) else {"not_executed":True}
                    messages.append(dict(role="tool",tool_call_id=c["id"],content=json.dumps(reply)))
            messages.append(dict(role="user",content=f"The previous generation hit its output limit before submitting a tool call. That usage remains counted. Continue from the unchanged current design {json.dumps(x)}; {STEPS-evaluated} design evaluations remain. The generation ceiling is now 16384 tokens. Do not repeat evaluated designs."))
        allowed=local_keys(t) if arm=="Fixed-P0" or (arm=="Cert-Guided" and not row["certificate"]["proved_empty"]) else tuple(DEFAULT)
        properties={k:dict(type="boolean") if k in MODULES else dict(type="number",minimum=DOMAIN[k][0],maximum=DOMAIN[k][1]) for k in allowed}
        tools=[dict(type="function",function=dict(name="evaluate",description="Apply changes to current design and evaluate all service slacks.",parameters=dict(type="object",properties=dict(changes=dict(type="object",properties=properties,additionalProperties=False),reason=dict(type="string")),required=["changes","reason"])))]
        for step in range(evaluated+1,STEPS+1):
            if time.perf_counter()-started+prior_runtime>=7200: halt.set();error="WALL_TIME_STOP";break
            if halt.is_set(): error="STOPPED_AFTER_OPERATIONAL_ERROR";break
            body=dict(model=common["model"],messages=messages,tools=tools,tool_choice="auto",thinking=dict(type="enabled"),reasoning_effort="high",max_tokens=max_output,stream=False)
            raw=json.dumps(body).encode(); reserve=(len(raw)*.30+max_output*1.20)/1e6
            with lock:
                if tally["spent"]+tally["reserved"]+reserve>USD_CAP or tally["requests"]>=360:
                    halt.set();error="BUDGET_STOP";break
                tally["reserved"]+=reserve;tally["requests"]+=1;rid=tally["requests"]
            emit(dict(kind="request",id=rid,task=t["id"],arm=arm,step=step,reserved_usd=reserve,max_tokens=max_output))
            try:
                req=urllib.request.Request("https://api.deepseek.com/chat/completions",data=raw,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
                with urllib.request.urlopen(req,timeout=240) as response: answer=json.load(response)
                usage=answer.get("usage",{})
                if not all(type(usage.get(k)) is int for k in ["prompt_tokens","completion_tokens","total_tokens"]): raise RuntimeError("USAGE_UNKNOWN")
                charge=(usage["prompt_tokens"]*.30+usage["completion_tokens"]*1.20)/1e6
                with lock:
                    tally["reserved"]-=reserve;tally["spent"]+=charge
                    for k in ["prompt_tokens","completion_tokens"]:tally[k]+=usage[k]
                    tally["reasoning_tokens"]+=usage.get("completion_tokens_details",{}).get("reasoning_tokens",0)
                    tally["cache_hit_tokens"]+=usage.get("prompt_cache_hit_tokens",0)
                emit(dict(kind="response",id=rid,task=t["id"],arm=arm,step=step,response=answer,estimated_usd=charge))
            except Exception as e:
                error=type(e).__name__+": "+str(e);halt.set()
                emit(dict(kind="UNKNOWN",id=rid,task=t["id"],arm=arm,error=error,reserved_usd=reserve));break
            message=answer["choices"][0]["message"]; messages.append(message)
            calls=message.get("tool_calls",[])
            if not calls:
                error="MODEL_OUTPUT_LENGTH" if answer["choices"][0]["finish_reason"]=="length" else "NO_TOOL_SUBMISSION";break
            result={}
            for call in calls:
                if evaluated>=STEPS or result.get("pass_"):
                    messages.append(dict(role="tool",tool_call_id=call["id"],content="No execution: evaluation budget exhausted or service already passed."));continue
                try:
                    patch=json.loads(call["function"]["arguments"])["changes"]
                    if any(k not in allowed or (k in DOMAIN and not DOMAIN[k][0]<=v<=DOMAIN[k][1]) or (k in MODULES and type(v) is not bool) for k,v in patch.items()):raise ValueError("OUTSIDE_DECLARED_DOMAIN")
                    candidate=dict(x,**patch);s=oracle(t,candidate);x=candidate;result=view(s);evaluated+=1
                except Exception as e:
                    result=dict(error=str(e));emit(dict(kind="invalid_action",task=t["id"],arm=arm,step=step,error=str(e)))
                messages.append(dict(role="tool",tool_call_id=call["id"],content=json.dumps(dict(result,remaining_evaluations=STEPS-evaluated))))
                emit(dict(kind="evaluation",id=rid,task=t["id"],arm=arm,step=step,design=x.copy(),feedback=result))
            if result.get("pass_"):break
            if evaluated>=STEPS:break
        good=bool(passed(oracle(t,x)))
        expanded=any(x[k]!=DEFAULT[k] for k in DEFAULT if k not in local_keys(t))
        conditional=sample(N,SEED+2)
        conditional.update({k:np.full(N,x[k]) for k in MODULES})
        diagnostic=int(passed(oracle(t,conditional)).sum()) if not good else None
        result=dict(task=t["id"],arm=arm,role=t["role"],pass_=good,first_pass=evaluated if good else None,evaluations=evaluated,
                    expanded=expanded,unneeded_expansion_control=expanded and t["role"]=="control",enabled_modules=[k for k in MODULES if x[k]],
                    final_design=x,final_slack={k:float(v) for k,v in oracle(t,x).items()},error=error,output_limit=max_output,
                    same_architecture_feasible_samples=diagnostic,diagnostic_samples=N)
        emit(dict(kind="terminal",**result));print(t["id"],arm,"PASS" if good else error or "FAIL",evaluated,flush=True)
        return result
    jobs=[(r,a) for r in calibration["tasks"] if r.get("witness") for a in rules]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(run,r,a) for r,a in jobs]
        results=[f.result() for f in futures]
    if abs(tally["reserved"])<1e-10:tally["reserved"]=0.
    tally["total_tokens"]=tally["prompt_tokens"]+tally["completion_tokens"]
    summary=dict(model=common["model"],feedback=feedback,completed_trajectories=len(results),results=results,accounting=tally,
                 cache_aware_peak_estimate_usd=tally["spent"]-tally["cache_hit_tokens"]*(.30-.006)/1e6,
                 runtime_s=prior_runtime+time.perf_counter()-started,operational_stop=halt.is_set(),
                 initial_pilot=prior_summary.get("initial_pilot",{k:prior_summary[k] for k in ["runtime_s","accounting"] if k in prior_summary}),
                 scientific_evaluations=sum(r["evaluations"] for r in results),
                 same_architecture_sampling_scope="All continuous coordinates sampled with final modules fixed; not a P0 feasibility test or an impossibility proof.",
                 interpretation="Same continuous feedback in all four arms by default. A separate binary run is needed to isolate feedback value. Zero conditional samples is not an impossibility proof.")
    summary["by_arm"]={a:dict(
        passes=sum(r["pass_"] for r in results if r["arm"]==a),
        deadlock_passes=sum(r["pass_"] for r in results if r["arm"]==a and r["role"]=="deadlock"),
        control_passes=sum(r["pass_"] for r in results if r["arm"]==a and r["role"]=="control"),
        success_by_evaluation=[sum(r["pass_"] and r["first_pass"]<=n for r in results if r["arm"]==a) for n in range(1,STEPS+1)],
        control_expansions=sum(r["unneeded_expansion_control"] for r in results if r["arm"]==a),
        length_incomplete=sum(r.get("error")=="MODEL_OUTPUT_LENGTH" for r in results if r["arm"]==a),
        text_stops=sum(r.get("error")=="NO_TOOL_SUBMISSION" for r in results if r["arm"]==a)) for a in rules}
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2));print(json.dumps({k:summary[k] for k in ["accounting","runtime_s","operational_stop"]}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--calibrate",action="store_true");p.add_argument("--agents",action="store_true")
    p.add_argument("--feedback",choices=["slack","binary"],default="slack")
    args=p.parse_args()
    if args.feedback=="binary": OUT=HERE/"limits-binary"
    if args.calibrate or not args.agents: calibrate()
    if args.agents: agents(args.feedback)
