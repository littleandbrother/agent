"""Three theorem checks on the full transient node (sim.py is ground truth).
X1 chi sweep, X2 same-symptom opposite-fix pairs, X3 certificate-coverage ladder.
--build [X2 X3 X1]: simulation-only construction gate -> pilots/theorems_<X>.json; --run: agents -> pilots/theorems.jsonl; --report."""
import concurrent.futures as cf
import copy
import json
import os
import re
import sys
import threading
from pathlib import Path

import numpy as np
from sim import G, TASK, beam, simulate

OUT = Path(__file__).resolve().parent/"pilots"; CACHE = Path(f"/tmp/theorems_simcache_{'_'.join(sys.argv[2:])}.json")
BASE = json.loads((OUT.parent/"design.json").read_text()); BASE["circuit"]["clamp_V"] = 2.95  # storage regulated just above start_V
VON, VOFF, ETA, CREF, F = 2.9, 1.8, .85, 100., BASE["firmware"]
TAU = 128/2048+sum(F[p+"_s"] for p in ("boot", "infer", "save", "tx", "ack"))  # one report task, s


def energy(tx):
    """uJ drawn from storage by one report task (harvest during the 72 ms task ignored)."""
    return 1e3*(128/2048*F["sample_mW"]+sum(F[p+"_s"]*F[p+"_mW"] for p in ("boot", "infer", "save", "ack"))+F["tx_s"]*tx)/ETA


def node(x, h):
    d = copy.deepcopy(BASE); n = x.get("harvester_beams", 1)  # n identical beams, each with its own bridge
    d["harvester"] |= dict(width_mm=10*n, length_mm=30., tip_mass_g=n*(x.get("tip_mass_g") or h["mass"]))
    d["circuit"] |= dict(storage_uF=x.get("storage_uF", h.get("C")), bridge_series_ohm=5000/n); d["firmware"]["tx_mW"] = h["tx"]
    t1 = h.get("t1", 8.)
    return d, TASK | dict(background_peak_g=h.get("bg", .15), fault_starts_s=[t1+6*i for i in range(4)], nuisance_starts_s=[t1+3, t1+15])


def run(a):
    x, h, dur = a; d, task = node(x, h); r = simulate(d, task | ({"duration_s": dur} if dur else {})); m = r["metrics"]
    ev = [e["event"] for e in r["events"]]; bo = ev[ev.index("BROWNOUT")-1] if "BROWNOUT" in ev else None
    return dict(pass_=r["verdict"] == "PASS", delivered=m["delivered_on_time"], brownouts=m["brownouts"], ready=m["cold_charge_ready_s"], wake=m["first_wake_s"],
                minV=m["minimum_active_storage_V"], final=m["final_storage_V"], brownout_phase=bo, first=task["fault_starts_s"][0])


def osc(x, h):
    """Analytic open-circuit voltage amplitude and phase lag (deg) of tip vs base displacement at the background frequency."""
    d, task = node(x, h); p = beam(d["harvester"]); w = 2*np.pi*task["background_Hz"]
    k = p["k"]+p["theta"]**2/p["cp"]; q = p["forcing_mass"]*task["background_peak_g"]*G/abs(k-p["m"]*w*w+1j*p["c"]*w)
    return float(p["theta"]*q/p["cp"]), float(np.degrees(np.arctan2(p["c"]*w, p["k"]+p["theta"]**2/(2*p["cp"])-p["m"]*w*w)))


def pc(rs):
    """Simplified net charging power (uW) from a cold-start test at C = 100 uF: 0.5 C Von^2 / t_ready."""
    return [.5*CREF*VON**2/r["ready"] if r["ready"] else 0. for r in rs]


def window(E, P, t1):
    cmin, cmax = 2*E/(VON**2-VOFF**2), 2*P*(t1+TASK["delivery_deadline_s"]-TAU)/VON**2
    return dict(E_need_uJ=round(E, 1), P_c_uW=round(P, 1), T_s=round(t1+TASK["delivery_deadline_s"]-TAU, 3), C_min_uF=round(cmin, 1), C_max_uF=round(cmax, 1), chi=round(cmin/cmax, 3))


def build(pool):
    memo = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    def sims(jobs):  # disk memo: a crashed or interrupted gate resumes without re-simulating
        k = [json.dumps(j, default=float) for j in jobs]; new = [j for j, s in zip(jobs, k) if s not in memo]
        for j, q in zip(new, pool.map(run, new)): memo[json.dumps(j, default=float)] = q
        CACHE.write_text(json.dumps(memo)); return [memo[s] for s in k]
    log = lambda s: (print(s, flush=True), Path("/workspace/theorems_progress.log").open("a").write(s+"\n"))
    ms = sorted(set(np.round(np.r_[np.arange(3.8, 5.81, .05), np.arange(4.45, 4.8, .0125)], 4)))
    curve = {n: dict(zip(ms, pc(sims([(dict(harvester_beams=n, tip_mass_g=m, storage_uF=CREF), dict(tx=12.), 15.) for m in ms])))) for n in (1, 2)}
    mo = max(curve[1], key=curve[1].get); P = {n: curve[n][mo] for n in (1, 2)}
    log(f"curve: m*={mo} P1={P[1]:.1f} P2={P[2]:.1f} uW")
    t1_for = lambda E, Pn, chi: 2*E/(VON**2-VOFF**2)*VON**2/(2*Pn*chi)-TASK["delivery_deadline_s"]+TAU
    feas = lambda rs: [r["pass_"] for r in rs]
    grid = lambda lo, hi, k=18: list(np.round(np.geomspace(lo, hi, k), 2))
    def truth(h, n, lo, hi, k=18):
        cs = grid(lo, hi, k); rs = sims([(dict(harvester_beams=n, tip_mass_g=mo, storage_uF=c), h, None) for c in cs]); ok = [c for c, q in zip(cs, rs) if q["pass_"]]
        return dict(grid=cs, passing=ok, window=[min(ok), max(ok)] if ok else None)
    stages = sys.argv[2:] or ["X2", "X3", "X1"]
    save = lambda s, tasks, **kw: (OUT/f"theorems_{s}.json").write_text(json.dumps(dict(m_opt=mo, P=P, tasks=tasks, **kw), indent=1, default=float))
    if "X1" in stages:
        tasks, r = [], np.random.default_rng(20261111)
        # chi = 1 boundary vs transient truth (no LLM), tx = 12 mW, one beam at m*
        E12 = energy(12.); bnd = []
        for chi in (.7, .8, .9, 1., 1.1, 1.2, 1.4):
            h = dict(mass=mo, tx=12., t1=t1_for(E12, P[1], chi)); w = window(E12, P[1], h["t1"]); cs = grid(.6*w["C_min_uF"], 1.6*w["C_max_uF"])
            ok = [c for c, f in zip(cs, feas(sims([(dict(storage_uF=c), h, None) for c in cs]))) if f]
            bnd.append(dict(chi=chi, t1=h["t1"], window=w, true_window=[min(ok), max(ok)] if ok else None)); log(f"boundary chi={chi}: simplified [{w['C_min_uF']},{w['C_max_uF']}] true {bnd[-1]['true_window']}")
        # X1: chi sweep on one beam; two beams double P_c; surrogate pair = Voc-peak mass vs power-optimal mass
        vpk = max(np.arange(4.4, 5.2, .01), key=lambda m: osc(dict(tip_mass_g=m), dict(mass=mo, tx=12.))[0])
        for i in range(4):
            for chi in (.6, .95, 1.05, 1.8):
                tx = float(r.uniform(8, 20)); E = energy(tx); h = dict(mass=mo, tx=tx, t1=float(t1_for(E, P[1], chi))); w = {n: window(E, P[n], h["t1"]) for n in (1, 2)}
                tr = {n: truth(h, n, .7*w[1]["C_min_uF"], 1.5*max(w[n]["C_max_uF"], w[1]["C_min_uF"])) for n in ((1, 2) if chi > 1 else (1,))}
                t = dict(id=f"X1/chi{chi}/i{i}", exp="X1", level=chi, h=h, x0=dict(harvester_beams=1, tip_mass_g=mo, storage_uF=round(.75*w[1]["C_min_uF"])), window=w, truth=tr)
                if chi > 1 and tr[2]["window"]:
                    c = float(np.sqrt(np.prod(tr[2]["window"]))); a, b = sims([(dict(harvester_beams=2, tip_mass_g=m, storage_uF=c), h, None) for m in (vpk, mo)])
                    t["surrogate"] = dict(C=c, voc_peak=dict(mass=round(float(vpk), 2), Voc=osc(dict(tip_mass_g=vpk), h)[0], pass_=a["pass_"]), power_opt=dict(mass=mo, Voc=osc({}, h)[0], pass_=b["pass_"]))
                t["gate"] = dict(m0_feasible=bool(tr[1]["passing"]), feasible=bool(tr[1]["passing"] or tr.get(2, {}).get("passing")), x0_fails=not sims([(t["x0"], h, None)])[0]["pass_"])
                tasks.append(t); log(f"{t['id']} chi_s={w[1]['chi']} chi2={w[2]['chi']} true1={tr[1]['window']} true2={tr.get(2, {}).get('window')} surrogate={t.get('surrogate', {}).get('voc_peak', {}).get('pass_')}/{t.get('surrogate', {}).get('power_opt', {}).get('pass_')}")
        save("X1", tasks, boundary=bnd, curve={n: {str(m): v for m, v in c.items()} for n, c in curve.items()})
    if "X3" in stages:
        tasks, r = [], np.random.default_rng(20261112)
        # X3: certificate ladder. S1 narrow m0 window; S2 m0 infeasible, m1 feasible; S3 all infeasible (best branch ratio ~0.83)
        def cert(h, n, cmin):
            xs = [dict(harvester_beams=n, tip_mass_g=round(mo+dm, 4), storage_uF=round(c, 2)) for dm in (-.05, 0, .05) for c in [30, 600]+list(np.geomspace(.6*cmin, 1.6*cmin, 6))]
            return dict(points=len(xs), hits=sum(feas(sims([(x, h, None) for x in xs]))))
        for i in range(4):
            for s, n, chi in (("S1", 1, .85), ("S2", 2, .85), ("S3", 2, 1.2)):
                tx = float(r.uniform(8, 20)); E = energy(tx); h = dict(mass=mo, tx=tx, t1=float(t1_for(E, P[n], chi))); w = {k: window(E, P[k], h["t1"]) for k in (1, 2)}
                hist_x = [dict(harvester_beams=1, tip_mass_g=mo, storage_uF=round(f*w[1]["C_min_uF"])) for f in (.7, .85, 1.25, 1.6)]
                hist = [dict(design=x, feedback=fb(q, x, h)) for x, q in zip(hist_x, sims([(x, h, None) for x in hist_x]))]
                ratio = {k: round(max(curve[k][m] for m in ms)/P[k]/w[k]["chi"], 3) for k in (1, 2)}  # best over masses of C_max/C_min
                tr = {1: truth(h, 1, .7*w[1]["C_min_uF"], 1.5*max(w[1]["C_max_uF"], w[1]["C_min_uF"])) if s == "S1" else cert(h, 1, w[1]["C_min_uF"])}
                tr[2] = truth(h, 2, .7*w[2]["C_min_uF"], 1.5*max(w[2]["C_max_uF"], w[2]["C_min_uF"])) if s == "S2" else cert(h, 2, w[2]["C_min_uF"]) if s == "S3" else None
                feasible = s != "S3"
                ok = (bool(tr[1]["passing"]) if s == "S1" else tr[1]["hits"] == 0) and (s != "S2" or bool(tr[2]["passing"])) and (s != "S3" or tr[2]["hits"] == 0) and not any(q["feedback"]["pass"] for q in hist)
                tasks.append(dict(id=f"X3/{s}/i{i}", exp="X3", state=s, h=h, x0=hist_x[-1], history=hist, window=w, ratio=ratio, truth=tr, feasible=feasible, gate=dict(ok=ok)))
                log(f"X3/{s}/i{i} chi1={w[1]['chi']} chi2={w[2]['chi']} ratio={ratio} truth1={tr[1].get('window', tr[1].get('hits'))} truth2={tr[2] and tr[2].get('window', tr[2].get('hits'))} ok={ok}")
        save("X3", tasks)
    if "X2" in stages:
        tasks, r = [], np.random.default_rng(20261113)
        # X2-I: capacitor direction. theta_A brownout (needs larger C), theta_B late start (needs smaller C); same C0, pass/fail feedback identical
        def solve_bg(targets, h0):
            bg = [.15*np.sqrt(p/P[1]) for p in targets]
            for k in range(4):
                got = pc(sims([(dict(storage_uF=CREF), h0 | dict(bg=b), 15.) for b in bg]))
                if k < 3: bg = [b*np.sqrt(p/g) if g else b*1.3 for b, p, g in zip(bg, targets, got)]
            return [float(b) for b in bg], got
        T8 = 8+TASK["delivery_deadline_s"]-TAU; spec = []
        for i in range(8):
            C0 = float(r.uniform(160, 190)); txB = float(r.uniform(10, 14)); EA = 1.15*C0*(VON**2-VOFF**2)/2
            txA = (EA*ETA/1e3-(energy(0.)*ETA/1e3))/F["tx_s"]
            spec.append((C0, dict(tx=txB, P=C0/1.15*VON**2/(2*T8)), dict(tx=txA, P=1.5*C0*VON**2/(2*T8))))
        bgs, got = solve_bg([th["P"] for _, B, A in spec for th in (A, B)], dict(mass=mo, tx=12.))
        for i, (C0, B, A) in enumerate(spec):
            hs = {k: dict(mass=mo, tx=th["tx"], bg=bgs[2*i+j], C=C0) for j, (k, th) in enumerate((("A", A), ("B", B)))}
            P_ = {k: got[2*i+j] for j, k in enumerate("AB")}; w = {k: window(energy(hs[k]["tx"]), P_[k], 8.) for k in "AB"}
            cs = sorted(set(grid(20, 1000, 16)+grid(.6*C0, 1.8*C0, 24)+[round(C0, 2)]+[round((w[k]["C_min_uF"]+w[k]["C_max_uF"])/2, 2) for k in "AB"]))
            res = {k: dict(zip(cs, sims([(dict(storage_uF=c), hs[k], None) for c in cs]))) for k in "AB"}
            F_ = {k: [c for c in cs if res[k][c]["pass_"]] for k in "AB"}; ideal = {k: res[k][round((w[k]["C_min_uF"]+w[k]["C_max_uF"])/2, 2)]["pass_"] for k in "AB"}
            g = dict(disjoint=not set(F_["A"]) & set(F_["B"]), A_above=bool(F_["A"]) and min(F_["A"]) > C0, B_below=bool(F_["B"]) and max(F_["B"]) < C0,
                     C0_fails=not res["A"][round(C0, 2)]["pass_"] and not res["B"][round(C0, 2)]["pass_"], ideal_policy=ideal,
                     stages={k: res[k][round(C0, 2)]["brownout_phase"] or f"late:{res[k][round(C0, 2)]['ready']}" for k in "AB"})
            g["ok"] = g["disjoint"] and g["A_above"] and g["B_below"] and g["C0_fails"] and all(ideal.values())
            for k in "AB": tasks.append(dict(id=f"X2/I/p{i}/{k}", exp="X2", fam="I", theta=k, h=hs[k], x0=dict(storage_uF=round(C0, 1)), hyp=w, truth=dict(passing=F_[k], window=[min(F_[k]), max(F_[k])] if F_[k] else None), gate=g))
            log(f"X2/I/p{i} C0={C0:.1f} FA={[min(F_['A']), max(F_['A'])] if F_['A'] else None} FB={[min(F_['B']), max(F_['B'])] if F_['B'] else None} {g}")
        save("X2", tasks)


def fb(q, x, h):
    """X1/X3 feedback: official transient metrics plus the analytic open-circuit voltage."""
    return {"pass": q["pass_"], "delivered_on_time": f"{q['delivered']}/4", "brownouts": q["brownouts"], "cold_charge_ready_s": q["ready"] and round(q["ready"], 3),
            "first_wake_s": q["wake"] and round(q["wake"], 3), "min_active_storage_V": q["minV"] and round(q["minV"], 3), "harvester_open_circuit_V": round(osc(x, h)[0], 2)}


if __name__ == "__main__" and "--build" in sys.argv:
    from multiprocessing import Pool
    with Pool(8) as p: build(p)


DOM = dict(storage_uF=(20, 1000), harvester_beams=(1, 2), tip_mass_g=(3.8, 5.8))
ARMS = dict(X1=("base", "chi"), X2=("blind", "tool", "given"), X3=("L0", "L1", "L2"))
UNITS, DIAG = dict(X1=6, X2=4, X3=4), .2
RUNS = OUT/os.environ.get("RUNS", "theorems.jsonl")


def describe(t):
    h, fam = t["h"], t.get("fam"); f = [round(h.get("t1", 8.)+6*i, 3) for i in range(4)]
    s = (f"Battery-free vibration-powered fault reporter, judged by a full transient simulation. Storage starts empty at t=0; the MCU starts when storage reaches start_V 2.9 V, browns out at 1.8 V; "
         f"storage is regulated to <= 2.95 V. A tuned trigger beam wakes the MCU at each burst; each wake runs one report task: boot 3 mW 2 ms, sample 3 mW 62.5 ms, infer 5 mW 2 ms, save 2 mW 0.5 ms, "
         f"tx {'(unknown, see conditions)' if fam == 'I' else round(h['tx'], 2)} mW 4 ms, ack 3 mW 1 ms (regulator efficiency 0.85). Faults (210 Hz, 0.5 g, 150 ms) start at {f} s and each must be reported "
         f"within 0.25 s; nuisance bursts at {[f[0]+3, f[0]+15]} s must not be reported. Background vibration {'(unknown, see conditions)' if fam == 'I' else h.get('bg', .15)} g at 45 Hz drives the harvester: "
         f"piezo bimorph cantilever(s), width 10 mm, damping ratio 1.5%, each beam with its own bridge rectifier.")
    if t["exp"] in ("X1", "X3"): v = dict(storage_uF="storage capacitance, uF, 20-1000", harvester_beams="number of identical parallel harvester beams, 1 or 2 (install only what you need)", tip_mass_g="tip mass per beam, g, 3.8-5.8 (beam length 30 mm)")
    else: v = dict(storage_uF="storage capacitance, uF, 20-1000"); s += f" Beam length 30 mm, tip mass {h['mass']} g. Exactly one of two equally likely field conditions holds: " + "; ".join(
        f"theta_{k}: net cold-start charging power about {w['P_c_uW']} uW and energy drawn from storage per report about {w['E_need_uJ']} uJ" for k, w in t["hyp"].items()) + "."
    return s, v


def intro(t, arm):
    if t["exp"] == "X1": return f"Design the node. evaluate(changes, reason) patches the CURRENT design and runs the official simulation; you have {UNITS['X1']} evaluations. The run ends at the first passing evaluation. If you conclude no design can pass, call finish."
    if t["exp"] == "X2": return f"Find a passing design. evaluate(changes, reason) patches the CURRENT design and runs the official simulation (cost 1 unit). The run ends at the first passing evaluation. Budget {UNITS['X2']} units." + (f" diagnose() measures the CURRENT design (cost {DIAG} unit)." if arm == "tool" else "")
    return (f"A previous engineer already evaluated the designs in `history` with the official simulation. You have {UNITS['X3']} more evaluations; a passing evaluation ends the run. The task may or may not be feasible: "
            "call finish with FEASIBLE / INFEASIBLE / UNSURE, a calibrated confidence and your reason. INFEASIBLE asserts that no design anywhere in the declared domain passes.")


def diagnose(t, x, q):
    late = not q["ready"] or q["ready"] > q["first"]
    return dict(first_fault=f"storage reached start_V only at t={q['ready'] and round(q['ready'], 2)} s; first fault at {q['first']} s" if late else f"brownout during {q['brownout_phase']}" if q["brownout_phase"] else "no failure at the first fault")


def evidence(t, arm):
    out = dict(history=t["history"])
    for k in (1, 2)[:{"L0": 0, "L1": 1, "L2": 2}[arm]]:
        out.setdefault("analysis", {})[f"harvester_beams={k}"] = dict(best_C_max_over_C_min=t["ratio"][str(k)], scope=f"exhaustive over all tip masses and capacitances with {k} beam(s); a passing design in this branch needs this ratio >= 1")
    return out


def feedback(t, x, q):
    return dict(passed=q["pass_"]) if t.get("fam") == "I" else fb(q, x, t["h"])


def agent(job, EX, emit, tally, lock, halt, key):
    from agent_limits import ask
    from pilots import PRICE, UNKNOWN_USD
    t, arm = job; jid = f"{t['id']}/{arm}"; rates = PRICE["deepseek-flash"]
    s, v = describe(t); x = dict(t["x0"]); q0 = EX.submit(run, (x, t["h"], None)).result() if t["exp"] != "X3" else None
    user = dict(design=x) | (evidence(t, arm) if t["exp"] == "X3" else dict(feedback=feedback(t, x, q0)))
    if arm == "chi": user["analysis"] = dict(simplified_window={f"{k} beam(s)": w for k, w in t["window"].items()}, rule="chi = C_min/C_max: chi<1 means a capacitor window exists for that structure; chi>1 means no capacitance works for it")
    if arm == "given": user["diagnosis"] = diagnose(t, x, q0)
    fn = lambda name, desc, props: dict(type="function", function=dict(name=name, description=desc, parameters=dict(type="object", properties=props, required=list(props))))
    tl = [fn("evaluate", "Patch the CURRENT design and run the official full simulation.", dict(changes=dict(type="object", properties={k: dict(type="number", description=d) for k, d in v.items()}, additionalProperties=False), reason=dict(type="string")))]
    if t["exp"] != "X2": tl.append(fn("finish", "Stop with a verdict on whether any passing design exists.", dict(verdict=dict(type="string", enum=["FEASIBLE", "INFEASIBLE", "UNSURE"]), confidence=dict(type="number"), reason=dict(type="string"))))
    if arm == "tool": tl.append(fn("diagnose", f"Measure the CURRENT design (cost {DIAG} unit).", {}))
    msgs = [dict(role="system", content=intro(t, arm)+"\n"+s+"\nVariables: "+json.dumps(v)), dict(role="user", content=json.dumps(user, default=float))]
    units = UNITS[t["exp"]]; used, evals, diags, first, fin, error, usd, steps = 0., 0, [], None, None, None, 0., []
    for _ in range(16):
        body = dict(model="deepseek-flash", messages=msgs, tools=tl, tool_choice="auto", max_tokens=65536, stream=True, stream_options=dict(include_usage=True), thinking=dict(type="enabled"), reasoning_effort="high")
        raw = json.dumps(body).encode(); reserve = (len(raw)*rates["input"]+65536*rates["output"])/1e6
        with lock:
            if tally["spent"]+tally["reserved"]+reserve > tally["cap"]: halt.set(); error = "BUDGET_STOP"; break
            tally["reserved"] += reserve
        try: answer, cost = ask(raw, key, rates, timeout=300)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"[:300]; emit(dict(kind="UNKNOWN", job=jid, error=error))
            with lock: tally["spent"] += UNKNOWN_USD
            break
        finally:
            with lock: tally["reserved"] -= reserve
        with lock: tally["spent"] += cost
        usd += cost; ch = answer["choices"][0]; m = ch["message"]; emit(dict(kind="response", job=jid, usd=cost, usage=answer["usage"], finish_reason=ch["finish_reason"], text=(m.get("content") or "")[:800]))
        msgs.append(m)
        if not m.get("tool_calls"): error = "OUTPUT_LENGTH" if ch["finish_reason"] == "length" else "TEXT_WITHOUT_ACTION"; break
        for c in m["tool_calls"]:
            name = c["function"]["name"]
            try:
                a = json.loads(c["function"]["arguments"] or "{}")
                if name == "finish" and t["exp"] != "X2": fin = a; reply = dict(stopped=True)
                elif name == "diagnose" and arm == "tool" and used+DIAG <= units+1e-9: used += DIAG; diags.append(evals); reply = diagnose(t, x, EX.submit(run, (x, t["h"], None)).result())
                elif name == "evaluate" and used+1 <= units+1e-9 and first is None:
                    ch_ = a["changes"]
                    if set(ch_)-set(v): raise ValueError(f"unknown variable; allowed {list(v)}")
                    x = x | {k: int(round(min(max(val, DOM[k][0]), DOM[k][1]))) if k == "harvester_beams" else float(min(max(val, DOM[k][0]), DOM[k][1])) for k, val in ch_.items()}
                    q = EX.submit(run, (x, t["h"], None)).result(); used += 1; evals += 1; reply = feedback(t, x, q); first = evals if q["pass_"] else None
                    steps.append(dict(x=x, pass_=q["pass_"])); emit(dict(kind="evaluation", job=jid, step=evals, design=x, pass_=q["pass_"], reason=a.get("reason", "")[:300]))
                else: reply = dict(error="not available (budget used, run over, or tool not offered)")
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e: reply = dict(error=str(e)[:300])
            msgs.append(dict(role="tool", tool_call_id=c["id"], content=json.dumps(reply | dict(units_left=round(units-used, 2)), default=float)))
        if fin or first or t["exp"] != "X3" and used+(DIAG if arm == "tool" else 1) > units+1e-9: break
    emit(dict(kind="terminal", job=jid, task=t["id"], exp=t["exp"], arm=arm, pass_=bool(first), first_pass=first, evaluations=evals, units=round(used, 2), diag_at=diags, steps=steps,
              verdict=(fin or {}).get("verdict", "FEASIBLE" if first else None), confidence=(fin or {}).get("confidence"), reason=(fin or {}).get("reason", "")[:1500], error=error, usd=usd))
    print(jid, "PASS@%d" % first if first else error or (fin or {}).get("verdict") or "FAIL", flush=True)


def launch():
    from pilots import UNKNOWN_USD, infra
    T = [t for f in sorted(OUT.glob("theorems_X*.json")) for t in json.loads(f.read_text())["tasks"]]; prev = [json.loads(s) for s in RUNS.read_text().splitlines()] if RUNS.exists() else []
    done = {r["job"] for r in prev if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}
    ok = [t for t in T if t["exp"] in os.environ.get("ONLY", "X1 X2 X3").split() and (t["gate"].get("ok") if t["exp"] != "X1" else t["gate"]["x0_fails"] and t["gate"]["feasible"])]
    jobs = sorted([(t, a) for t in ok for a in ARMS[t["exp"]] if f"{t['id']}/{a}" not in done], key=lambda j: (re.search(r"/[ip](\d)", j[0]["id"])[1], j[0]["exp"], j[1], j[0]["id"]))
    lock, halt = threading.Lock(), threading.Event(); key = os.environ["DEEPSEEK_API_KEY"]
    tally = dict(spent=sum(r["usd"] for r in prev if r["kind"] == "response")+UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in prev), reserved=0., cap=float(os.environ.get("CAP", 6.)))
    def emit(row):
        with lock, RUNS.open("a") as f: f.write(json.dumps(row, ensure_ascii=False, default=float)+"\n")
    print(len(jobs), "jobs; spent so far", round(tally["spent"], 3), flush=True)
    with cf.ProcessPoolExecutor(8) as EX, cf.ThreadPoolExecutor(int(os.environ.get("WORKERS", 16))) as pool:
        list(pool.map(lambda j: None if halt.is_set() else agent(j, EX, emit, tally, lock, halt, key), jobs))
    print(json.dumps(tally))


if __name__ == "__main__" and "--run" in sys.argv: launch()


def report():
    from scipy.stats import fisher_exact, mannwhitneyu
    from pilots import infra, wilson
    T = {t["id"]: t for f in sorted(OUT.glob("theorems_X*.json")) for t in json.loads(f.read_text())["tasks"]}; rows = [json.loads(s) for f in sorted(OUT.glob("theorems_X?.jsonl")) for s in f.read_text().splitlines()]
    term = {r["job"]: r for r in rows if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}.values()
    G = lambda r: (lambda t: f"X1/chi{t['level']}" if t["exp"] == "X1" else f"X2/{t['fam']}" if t["exp"] == "X2" else f"X3/{t['state']}")(T[r["task"]])+"/"+r["arm"]
    cells = {}
    for r in term: cells.setdefault(G(r), []).append(r)
    def right(r):  # first evaluated move in the theta-correct direction (A: larger C)
        t = T[r["task"]]; k = list(t["x0"])[0]; up = bool(r["steps"]) and r["steps"][0]["x"][k] > t["x0"][k]
        return bool(r["steps"]) and up == (t["theta"] == "A")
    rate = lambda rs, f: (sum(map(f, rs)), len(rs), wilson(sum(map(f, rs)), len(rs)))
    out, two = {}, re.compile(r"2 beams|two beams|beams\s*=\s*2|harvester_beams\D{0,6}2|second beam|both (branches|structures)|dual", re.I)
    for c, rs in sorted(cells.items()):
        t0 = T[rs[0]["task"]]; d = dict(n=len(rs), passed=rate(rs, lambda r: r["pass_"]))
        if t0["exp"] == "X1":
            mo = t0["x0"]["tip_mass_g"]; d |= dict(two_beams=rate(rs, lambda r: any(s["x"]["harvester_beams"] == 2 for s in r["steps"])),
                       C_in_true_window_1beam=rate(rs, lambda r: any(s["x"]["harvester_beams"] == 1 and (lambda w: w and w[0] <= s["x"]["storage_uF"] <= w[1])(T[r["task"]]["truth"]["1"]["window"]) for s in r["steps"])),
                       mass_toward_voc_peak=rate(rs, lambda r: any(s["x"]["tip_mass_g"] > mo+.05 for s in r["steps"])), infeasible=rate(rs, lambda r: r["verdict"] == "INFEASIBLE"),
                       evals_mean=round(float(np.mean([r["evaluations"] for r in rs])), 2))
        if t0["exp"] == "X2":
            N = [r["first_pass"] or UNITS["X2"]+1 for r in rs]
            d |= dict(step1=rate(rs, lambda r: r["first_pass"] == 1), N_eval=N, N_eval_mean=round(float(np.mean(N)), 3), units_mean=round(float(np.mean([r["units"] for r in rs])), 3),
                      diag_first=rate(rs, lambda r: 0 in r["diag_at"]), first_move_right=rate(rs, right))
        if t0["exp"] == "X3":
            inf = lambda r: r["verdict"] == "INFEASIBLE"; m1 = lambda r: any(s["x"].get("harvester_beams") == 2 for s in r["steps"])
            d |= dict(verdicts={v: sum(r["verdict"] == v for r in rs) for v in ("FEASIBLE", "INFEASIBLE", "UNSURE", None)}, infeasible=rate(rs, inf),
                      tested_two_beams=rate(rs, m1), infeasible_without_testing_two_beams=rate(rs, lambda r: inf(r) and not m1(r)),
                      infeasible_global_justification=rate(rs, lambda r: inf(r) and (m1(r) or bool(two.search(r["reason"] or "")))))
        d["usd"] = round(sum(r["usd"] for r in rs), 3); out[c] = d; print(c, {k: v for k, v in d.items() if k not in ("N_eval",)})
    def fisher(a, b, key="passed"):
        if a in out and b in out: x, y = out[a][key], out[b][key]; return [a, b, key, f"{x[0]}/{x[1]} vs {y[0]}/{y[1]}", round(float(fisher_exact([[x[0], x[1]-x[0]], [y[0], y[1]-y[0]]])[1]), 4)]
    pool = lambda cs, key: (lambda xs: (sum(x[0] for x in xs), sum(x[1] for x in xs)))([out[c][key] for c in cs if c in out])
    for g, cs in dict(X1_hi_base=["X1/chi1.05/base", "X1/chi1.8/base"], X1_hi_chi=["X1/chi1.05/chi", "X1/chi1.8/chi"], X1_lo_base=["X1/chi0.6/base", "X1/chi0.95/base"], X1_lo_chi=["X1/chi0.6/chi", "X1/chi0.95/chi"],
                      X3_S12_L0=["X3/S1/L0", "X3/S2/L0"], X3_S12_L1=["X3/S1/L1", "X3/S2/L1"], X3_S12_L2=["X3/S1/L2", "X3/S2/L2"]).items():
        for key in ("passed", "two_beams", "infeasible"):
            if all(key in out.get(c, {}) for c in cs): k, n = pool(cs, key); out[f"pool/{g}"] = out.get(f"pool/{g}", {}) | {key: (k, n, wilson(k, n))}
    tests = [fisher(*a) for a in (("pool/X1_hi_chi", "pool/X1_hi_base"), ("pool/X1_hi_chi", "pool/X1_hi_base", "two_beams"), ("pool/X1_lo_base", "pool/X1_hi_base"), ("pool/X1_lo_chi", "pool/X1_lo_base"),
             ("X3/S3/L2", "X3/S3/L0", "infeasible"), ("X3/S3/L1", "X3/S3/L0", "infeasible"), ("pool/X3_S12_L0", "pool/X3_S12_L2", "infeasible"), ("pool/X3_S12_L0", "pool/X3_S12_L1", "infeasible"))]
    for f in ("I",):
        tests += [fisher(f"X2/{f}/{a}", f"X2/{f}/blind", "step1") for a in ("tool", "given")]
        for a in ("tool", "given"):
            if f"X2/{f}/{a}" in out and f"X2/{f}/blind" in out: tests.append([f"X2/{f}/{a}", f"X2/{f}/blind", "N_eval MWU", round(float(mannwhitneyu(out[f"X2/{f}/{a}"]["N_eval"], out[f"X2/{f}/blind"]["N_eval"]).pvalue), 4)])
    tests = [x for x in tests if x]; print(*tests, sep="\n")
    resp = [r for r in rows if r["kind"] == "response"]; from pilots import UNKNOWN_USD
    usage = dict(requests=len(resp), usd=round(sum(r["usd"] for r in resp)+UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in rows), 3), unknown=sum(r["kind"] == "UNKNOWN" for r in rows),
                 infra_attempts=sum(r["kind"] == "terminal" and infra(r) for r in rows), terminals=len(term))
    print(usage); (OUT/"theorems_summary.json").write_text(json.dumps(dict(usage=usage, cells=out, tests=tests), indent=1, default=float))


if __name__ == "__main__" and "--report" in sys.argv: report()
