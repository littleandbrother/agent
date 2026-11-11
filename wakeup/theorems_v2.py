"""Y1-Y3 remakes of the theorem checks. Old X1-X3 files are not touched.
Y1: area-constrained structure switch; Y2: tip-mass resonance pair; Y3: four-branch stop certificate.
--build [Y1 Y2 Y3] writes pilots/theorems_v2_Y*.json; --run / --report use those plus theorems_v2_Y*.jsonl."""
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
from theorems import BASE, VON, VOFF, ETA, CREF, F, TAU, energy, window

OUT = Path(__file__).resolve().parent/"pilots"
CACHE = Path(f"/tmp/theorems_v2_simcache_{'_'.join(sys.argv[2:])}.json")


def node(x, h):
    d = copy.deepcopy(BASE); n = int(x.get("harvester_beams") or 1)
    mt = (h["mass"] if x.get("tip_mass_g") is None else x["tip_mass_g"]) + h.get("dm", 0.)
    d["harvester"] |= dict(width_mm=10*n, length_mm=30., tip_mass_g=n*mt)
    d["circuit"] |= dict(storage_uF=x.get("storage_uF", h.get("C", 150)), bridge_series_ohm=5000/n)
    d["firmware"]["tx_mW"] = h["tx"]
    t1 = h.get("t1", 8.)
    return d, TASK | dict(background_peak_g=h.get("bg", .15), fault_starts_s=[t1+6*i for i in range(4)], nuisance_starts_s=[t1+3, t1+15])


def run(a):
    x, h, dur = a; d, task = node(x, h); r = simulate(d, task | ({"duration_s": dur} if dur else {})); m = r["metrics"]
    ev = [e["event"] for e in r["events"]]; bo = ev[ev.index("BROWNOUT")-1] if "BROWNOUT" in ev else None
    return dict(pass_=r["verdict"] == "PASS", delivered=m["delivered_on_time"], brownouts=m["brownouts"], ready=m["cold_charge_ready_s"], wake=m["first_wake_s"],
                minV=m["minimum_active_storage_V"], final=m["final_storage_V"], brownout_phase=bo, first=task["fault_starts_s"][0])


def osc(x, h):
    d, task = node(x, h); p = beam(d["harvester"]); w = 2*np.pi*task["background_Hz"]
    k = p["k"]+p["theta"]**2/p["cp"]; q = p["forcing_mass"]*task["background_peak_g"]*G/abs(k-p["m"]*w*w+1j*p["c"]*w)
    return float(p["theta"]*q/p["cp"]), float(np.degrees(np.arctan2(p["c"]*w, p["k"]+p["theta"]**2/(2*p["cp"])-p["m"]*w*w)))


def pc(rs):
    return [.5*CREF*VON**2/r["ready"] if r["ready"] else 0. for r in rs]


def shown(q, x, h):
    voc, _ = osc(x, h)
    return dict(passed=bool(q["pass_"]), delivered_on_time=f"{q['delivered']}/4", harvester_open_circuit_V=round(voc, 1),
                final_storage_V=None if q["final"] is None else round(q["final"], 1))


def build(pool):
    memo = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    def sims(jobs):
        k = [json.dumps(j, default=float) for j in jobs]; new = [j for j, s in zip(jobs, k) if s not in memo]
        for j, q in zip(new, pool.map(run, new)): memo[json.dumps(j, default=float)] = q
        CACHE.write_text(json.dumps(memo)); return [memo[s] for s in k]
    log = lambda s: (print(s, flush=True), Path("/workspace/theorems_v2_progress.log").open("a").write(s+"\n"))
    ms = sorted(set(np.round(np.r_[np.arange(3.8, 5.81, .05), np.arange(4.45, 4.8, .0125)], 4)))
    curve = {n: dict(zip(ms, pc(sims([(dict(harvester_beams=n, tip_mass_g=m, storage_uF=CREF), dict(mass=4.5875, tx=12.), 15.) for m in ms])))) for n in (1, 2, 3, 4)}
    mo = max(curve[1], key=curve[1].get); P = {n: curve[n][mo] for n in (1, 2, 3, 4)}
    log(f"curve: m*={mo} P="+", ".join(f"{n}:{P[n]:.1f}" for n in (1, 2, 3, 4)))
    t1_for = lambda E, Pn, chi: 2*E/(VON**2-VOFF**2)*VON**2/(2*Pn*chi)-TASK["delivery_deadline_s"]+TAU
    feas = lambda rs: [r["pass_"] for r in rs]
    grid = lambda lo, hi, k=18: list(np.round(np.geomspace(lo, hi, k), 2))
    def truth(h, n, lo, hi, k=18):
        cs = grid(lo, hi, k); rs = sims([(dict(harvester_beams=n, tip_mass_g=mo, storage_uF=c), h, None) for c in cs]); ok = [c for c, q in zip(cs, rs) if q["pass_"]]
        return dict(grid=cs, passing=ok, window=[min(ok), max(ok)] if ok else None)
    stages = sys.argv[2:] or ["Y1", "Y2", "Y3"]
    save = lambda s, tasks, **kw: (OUT/f"theorems_v2_{s}.json").write_text(json.dumps(dict(m_opt=mo, P=P, tasks=tasks, **kw), indent=1, default=float))

    if "Y1" in stages:
        tasks, r = [], np.random.default_rng(20261114)
        E12 = energy(12.); bnd = []
        for chi in (.6, .9, 1.0, 1.1, 1.8):
            h = dict(mass=mo, tx=12., t1=t1_for(E12, P[1], chi)); w = window(E12, P[1], h["t1"]); cs = grid(.6*w["C_min_uF"], 1.6*max(w["C_max_uF"], w["C_min_uF"]))
            ok = [c for c, f in zip(cs, feas(sims([(dict(storage_uF=c), h, None) for c in cs]))) if f]
            bnd.append(dict(chi=chi, t1=h["t1"], window=w, true_window=[min(ok), max(ok)] if ok else None)); log(f"Y1 boundary chi={chi}: simplified [{w['C_min_uF']},{w['C_max_uF']}] true {bnd[-1]['true_window']}")
        for i in range(4):
            for chi in (.6, .9, 1.1, 1.8):
                tx = float(r.uniform(8, 20)); E = energy(tx); h = dict(mass=mo, tx=tx, t1=float(t1_for(E, P[1], chi))); w = {n: window(E, P[n], h["t1"]) for n in (1, 2)}
                tr = {n: truth(h, n, .7*w[1]["C_min_uF"], 1.5*max(w[n]["C_max_uF"], w[1]["C_min_uF"])) for n in ((1, 2) if chi > 1 else (1,))}
                single = bool(tr[1]["passing"]); t = dict(id=f"Y1/chi{chi}/i{i}", exp="Y1", level=chi, h=h, x0=dict(harvester_beams=1, tip_mass_g=mo, storage_uF=round(.75*w[1]["C_min_uF"])), window=w, truth=tr, single_solvable=single)
                t["gate"] = dict(m0_feasible=single, feasible=single or bool(tr.get(2, {}).get("passing")), x0_fails=not sims([(t["x0"], h, None)])[0]["pass_"],
                                 margin_ok=(single and chi < 1) or ((not single) and chi > 1 and bool(tr.get(2, {}).get("passing"))))
                tasks.append(t); log(f"{t['id']} chi_s={w[1]['chi']} true1={tr[1]['window']} true2={tr.get(2, {}).get('window')} gate={t['gate']}")
        save("Y1", tasks, boundary=bnd, curve={n: {str(m): v for m, v in c.items()} for n, c in curve.items()})

    if "Y2" in stages:
        tasks, C0, tx0, t10, bg0 = [], 100., 8., 8., .15
        h0 = dict(mass=mo, tx=tx0, t1=t10, bg=bg0, C=C0)
        # passing window on true mass at the working (C, tx)
        mgrid = list(np.round(np.arange(4.4, 5.36, .02), 4))
        wr = dict(zip(mgrid, sims([(dict(tip_mass_g=float(m), storage_uF=C0, harvester_beams=1), h0, None) for m in mgrid])))
        W = [float(m) for m in mgrid if wr[m]["pass_"]]
        log(f"Y2 true-mass window at C={C0} tx={tx0}: { [min(W), max(W)] if W else None } n={len(W)}")
        # Voc-matched candidates across phi=90, both outside W
        rows = [(float(m),)+osc(dict(tip_mass_g=float(m)), h0) for m in np.round(np.arange(3.8, 5.801, .005), 4)]
        light, heavy = [r for r in rows if r[2] < 90], [r for r in rows if r[2] > 90]
        cands = []
        for m, v, p in light:
            mh, vh, ph = min(heavy, key=lambda r: abs(r[1]-v))
            if abs(v-vh) < .05 and (not W or (m < min(W)-.02 and mh > max(W)+.02)):
                cands.append((m, mh, v, vh, p, ph, abs(v-vh)))
        cands = sorted(cands, key=lambda r: r[6])
        # unique-ish pairs (keep m- at least 0.008 apart)
        picked, last = [], -99
        for c in cands:
            if c[0]-last >= .008: picked.append(c); last = c[0]
        picked = picked[:16]
        qs = sims([(dict(tip_mass_g=m, storage_uF=C0, harvester_beams=1), h0, None) for m, mh, *rest in picked] +
                  [(dict(tip_mass_g=mh, storage_uF=C0, harvester_beams=1), h0, None) for m, mh, *rest in picked])
        ok_pairs = []
        for i, (m, mh, v, vh, p, ph, dv) in enumerate(picked):
            qa, qb = qs[i], qs[i+len(picked)]
            fa, fb_ = shown(qa, dict(tip_mass_g=m), h0), shown(qb, dict(tip_mass_g=mh), h0)
            ident = fa == fb_ and fa["passed"] is False
            mid, dm = (m+mh)/2, (mh-m)/2
            wc = (min(W)+max(W))/2 if W else mo
            ideal = { "-": wc+dm, "+": wc-dm }
            iq = sims([(dict(tip_mass_g=ideal["-"], storage_uF=C0, harvester_beams=1), dict(h0, dm=-dm), None),
                       (dict(tip_mass_g=ideal["+"], storage_uF=C0, harvester_beams=1), dict(h0, dm=+dm), None)])
            # F on the commanded mass: true = cmd + dm, reuse the true-mass window
            Fm = [round(w-(-dm), 4) for w in W if 3.8 <= w-(-dm) <= 5.8]
            Fp = [round(w-(+dm), 4) for w in W if 3.8 <= w-(+dm) <= 5.8]
            g = dict(identical_base=ident, shown_minus=fa, shown_plus=fb_, ready=(qa["ready"], qb["ready"]),
                     minV=(qa["minV"], qb["minV"]), disjoint=not set(Fm) & set(Fp),
                     base_fails=(not qa["pass_"]) and (not qb["pass_"]),
                     ideal_policy={"-": iq[0]["pass_"], "+": iq[1]["pass_"]},
                     voc=(v, vh), phi=(p, ph), m_true=(m, mh), m0=mid, dm=dm, W=[min(W), max(W)] if W else None, F_minus=Fm, F_plus=Fp)
            g["ok"] = ident and g["disjoint"] and g["base_fails"] and all(g["ideal_policy"].values()) and bool(Fm) and bool(Fp)
            log(f"Y2 cand m-={m:.3f} m+={mh:.3f} dVoc={dv:.4f} ident={ident} ready={g['ready']} final={fa['final_storage_V']}/{fb_['final_storage_V']} Voc={fa['harvester_open_circuit_V']}/{fb_['harvester_open_circuit_V']} disjoint={g['disjoint']} ideal={g['ideal_policy']} ok={g['ok']}")
            if g["ok"]: ok_pairs.append(g)
        for i, g in enumerate(ok_pairs[:8]):
            for sign, key, dm in (("-", "-", -g["dm"]), ("+", "+", g["dm"])):
                h = dict(mass=mo, tx=tx0, t1=t10, bg=bg0, C=C0, dm=dm, m0=g["m0"])
                tasks.append(dict(id=f"Y2/II/p{i}/{key}", exp="Y2", fam="II", theta=key, h=h,
                                  x0=dict(tip_mass_g=round(g["m0"], 3), storage_uF=C0), truth=dict(passing=g["F_minus"] if key == "-" else g["F_plus"], W=g["W"]),
                                  gate=g, voc=g["voc"], phi=g["phi"]))
        log(f"Y2 ok pairs {len(ok_pairs)} kept {min(8, len(ok_pairs))}")
        save("Y2", tasks, window_true=([min(W), max(W)] if W else None), n_ok_pairs=len(ok_pairs))

    if "Y3" in stages:
        tasks, r = [], np.random.default_rng(20261116)
        def cert(h, n, cmin):
            xs = [dict(harvester_beams=n, tip_mass_g=round(mo+dm, 4), storage_uF=round(c, 2)) for dm in (-.05, 0, .05) for c in [30, 600]+list(np.geomspace(.6*cmin, 1.6*cmin, 6))]
            return dict(points=len(xs), hits=sum(feas(sims([(x, h, None) for x in xs]))))
        hist_fb = lambda q: dict(delivered_on_time=f"{q['delivered']}/4")
        for i in range(4):
            for s, n_chi, chi in (("S1", 1, .85), ("S2", 4, .85), ("S3", 4, 1.2)):
                tx = float(r.uniform(8, 20)); E = energy(tx); h = dict(mass=mo, tx=tx, t1=float(t1_for(E, P[n_chi], chi))); w = {k: window(E, P[k], h["t1"]) for k in (1, 2, 3, 4)}
                hist_x = [dict(harvester_beams=1, tip_mass_g=mo, storage_uF=round(f*w[1]["C_min_uF"])) for f in (.7, .85, 1.25, 1.6)]
                hist = [dict(design=x, feedback=hist_fb(q), _ready=q["ready"], _pass=q["pass_"]) for x, q in zip(hist_x, sims([(x, h, None) for x in hist_x]))]
                ratio = {k: round(max(curve[k][m] for m in ms)/P[k]/w[k]["chi"], 3) for k in (1, 2, 3, 4)}
                tr = {}
                for k in (1, 2, 3, 4):
                    if s == "S1" and k == 1 or s == "S2" and k == 4:
                        tr[k] = truth(h, k, .7*w[k]["C_min_uF"], 1.5*max(w[k]["C_max_uF"], w[k]["C_min_uF"]))
                    else:
                        tr[k] = cert(h, k, w[k]["C_min_uF"])
                if s == "S1": ok = bool(tr[1]["passing"]) and not any(q["_pass"] for q in hist)
                elif s == "S2": ok = (tr[4].get("passing") and tr[1]["hits"] == 0 and tr[2]["hits"] == 0 and tr[3]["hits"] == 0 and not any(q["_pass"] for q in hist)
                                       and w[4]["chi"] < 1 <= min(w[k]["chi"] for k in (1, 2, 3)))
                else: ok = all(tr[k]["hits"] == 0 for k in (1, 2, 3, 4)) and not any(q["_pass"] for q in hist) and min(w[k]["chi"] for k in (1, 2, 3, 4)) > 1
                for q in hist:
                    q.pop("_ready", None); q.pop("_pass", None)
                tasks.append(dict(id=f"Y3/{s}/i{i}", exp="Y3", state=s, h=h, x0=hist_x[-1], history=hist, window=w, ratio=ratio, truth=tr, feasible=s != "S3", gate=dict(ok=ok)))
                log(f"Y3/{s}/i{i} chi="+str({k: w[k]["chi"] for k in (1, 2, 3, 4)})+f" ratio={ratio} ok={ok} tr="+str({k: tr[k].get("window", tr[k].get("hits")) for k in (1, 2, 3, 4)}))
        save("Y3", tasks)


if __name__ == "__main__" and "--build" in sys.argv:
    from multiprocessing import Pool
    with Pool(8) as p: build(p)


DOM = dict(storage_uF=(20, 1000), harvester_beams=(1, 4), tip_mass_g=(3.8, 5.8))
ARMS = dict(Y1=("base", "chi"), Y2=("blind", "tool", "given"), Y3=("L0", "L1", "L2"))
UNITS, DIAG = dict(Y1=6, Y2=4, Y3=2), .2
RUNS = OUT/os.environ.get("RUNS", "theorems_v2.jsonl")


def describe(t):
    h, fam = t["h"], t.get("fam"); f = [round(h.get("t1", 8.)+6*i, 3) for i in range(4)]
    s = (f"Battery-free vibration-powered fault reporter, judged by a full transient simulation. Storage starts empty at t=0; the MCU starts when storage reaches start_V 2.9 V, browns out at 1.8 V; "
         f"storage is regulated to <= 2.95 V. A tuned trigger beam wakes the MCU at each burst; each wake runs one report task: boot 3 mW 2 ms, sample 3 mW 62.5 ms, infer 5 mW 2 ms, save 2 mW 0.5 ms, "
         f"tx {round(h['tx'], 2)} mW 4 ms, ack 3 mW 1 ms (regulator efficiency 0.85). Faults (210 Hz, 0.5 g, 150 ms) start at {f} s and each must be reported "
         f"within 0.25 s; nuisance bursts at {[f[0]+3, f[0]+15]} s must not be reported. Background vibration {h.get('bg', .15)} g at 45 Hz drives the harvester: "
         f"piezo bimorph cantilever(s), width 10 mm per beam, length 30 mm, damping ratio 1.5%, each beam with its own bridge rectifier.")
    if t["exp"] == "Y1":
        s += " Area: one beam is 300 mm^2, two beams 600 mm^2. A second beam is allowed only when one beam cannot physically meet the service; submitting two beams on a one-beam-solvable task fails the area constraint (area_pass=False) and the evaluation is a failure."
        v = dict(storage_uF="storage capacitance, uF, 20-1000", harvester_beams="number of identical parallel harvester beams, 1 or 2 (install only what you need; two beams double the area)", tip_mass_g="tip mass per beam, g, 3.8-5.8")
    elif t["exp"] == "Y2":
        s += (f" Beam length is fixed at 30 mm. You may change the commanded tip mass (and storage is fixed at {h['C']} uF). "
              "Exactly one of two equally likely field conditions holds: a hidden tip-mass bias that places the true mass above or below resonance at 45 Hz. The sign of the bias is not in the base feedback.")
        v = dict(tip_mass_g="commanded tip mass, g, 3.8-5.8 (true mass equals the command plus a hidden bias)")
    else:
        s += " You may use 1 to 4 identical parallel harvester beams (width 10 mm each)."
        v = dict(storage_uF="storage capacitance, uF, 20-1000", harvester_beams="number of identical parallel harvester beams, 1, 2, 3 or 4", tip_mass_g="tip mass per beam, g, 3.8-5.8")
    return s, v


def intro(t, arm):
    if t["exp"] == "Y1":
        return f"Design the node. evaluate(changes, reason) patches the CURRENT design and runs the official simulation; you have {UNITS['Y1']} evaluations. The run ends at the first passing evaluation (simulation pass and area constraint). If you conclude no design can pass, call finish."
    if t["exp"] == "Y2":
        return f"Find a passing design. evaluate(changes, reason) patches the CURRENT design and runs the official simulation (cost 1 unit). The run ends at the first passing evaluation. Budget {UNITS['Y2']} units." + (f" diagnose() measures the CURRENT design's phase lag (cost {DIAG} unit)." if arm == "tool" else "")
    return (f"A previous engineer already evaluated the designs in `history` with the official simulation. You have {UNITS['Y3']} more evaluations; a passing evaluation ends the run. The task may or may not be feasible: "
            "call finish with FEASIBLE / INFEASIBLE / UNSURE, a calibrated confidence and your reason. INFEASIBLE asserts that no design anywhere in the declared domain passes.")


def diagnose(t, x, q):
    voc, phi = osc(x, t["h"])
    return dict(phase_lag_deg=round(phi, 1), open_circuit_V=round(voc, 2),
                note="phase lag of tip vs base displacement at 45 Hz; >90 deg means below resonance (true mass too high), <90 means above resonance (true mass too low)")


def evidence(t, arm):
    out = dict(history=t["history"]); nmax = {"L0": 0, "L1": 1, "L2": 4}[arm]
    for k in range(1, nmax+1):
        out.setdefault("analysis", {})[f"harvester_beams={k}"] = dict(best_C_max_over_C_min=t["ratio"][str(k)], scope=f"exhaustive over all tip masses and capacitances with {k} beam(s); a passing design in this branch needs this ratio >= 1")
    return out


def feedback(t, x, q):
    if t["exp"] == "Y2": return shown(q, x, t["h"])
    if t["exp"] == "Y3": return dict(delivered_on_time=f"{q['delivered']}/4", passed=q["pass_"])
    area_ok = not (x.get("harvester_beams", 1) == 2 and t.get("single_solvable"))
    return dict(passed=bool(q["pass_"] and area_ok), area_pass=area_ok, delivered_on_time=f"{q['delivered']}/4", brownouts=q["brownouts"],
                cold_charge_ready_s=q["ready"] and round(q["ready"], 3), first_wake_s=q["wake"] and round(q["wake"], 3),
                min_active_storage_V=q["minV"] and round(q["minV"], 3), harvester_open_circuit_V=round(osc(x, t["h"])[0], 2))


def agent(job, EX, emit, tally, lock, halt, key):
    from agent_limits import ask
    from pilots import PRICE, UNKNOWN_USD
    t, arm = job; jid = f"{t['id']}/{arm}"; rates = PRICE["deepseek-flash"]
    s, v = describe(t); x = dict(t["x0"]); q0 = EX.submit(run, (x, t["h"], None)).result() if t["exp"] != "Y3" else None
    user = dict(design=x) | (evidence(t, arm) if t["exp"] == "Y3" else dict(feedback=feedback(t, x, q0)))
    if arm == "chi": user["analysis"] = dict(simplified_window={f"{k} beam(s)": w for k, w in t["window"].items()}, rule="chi = C_min/C_max: chi<1 means a capacitor window exists for that structure; chi>1 means no capacitance works for it. A second beam is allowed only when the one-beam window is empty.")
    if arm == "given": user["diagnosis"] = diagnose(t, x, q0)
    fn = lambda name, desc, props: dict(type="function", function=dict(name=name, description=desc, parameters=dict(type="object", properties=props, required=list(props))))
    tl = [fn("evaluate", "Patch the CURRENT design and run the official full simulation.", dict(changes=dict(type="object", properties={k: dict(type="number", description=d) for k, d in v.items()}, additionalProperties=False), reason=dict(type="string")))]
    if t["exp"] != "Y2": tl.append(fn("finish", "Stop with a verdict on whether any passing design exists.", dict(verdict=dict(type="string", enum=["FEASIBLE", "INFEASIBLE", "UNSURE"]), confidence=dict(type="number"), reason=dict(type="string"))))
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
                if name == "finish" and t["exp"] != "Y2": fin = a; reply = dict(stopped=True)
                elif name == "diagnose" and arm == "tool" and used+DIAG <= units+1e-9: used += DIAG; diags.append(evals); reply = diagnose(t, x, EX.submit(run, (x, t["h"], None)).result())
                elif name == "evaluate" and used+1 <= units+1e-9 and first is None:
                    ch_ = a["changes"]
                    if set(ch_)-set(v): raise ValueError(f"unknown variable; allowed {list(v)}")
                    lohi = {k: DOM[k] if k != "harvester_beams" else ((1, 2) if t["exp"] == "Y1" else DOM[k]) for k in v}
                    x = x | {k: int(round(min(max(val, lohi[k][0]), lohi[k][1]))) if k == "harvester_beams" else float(min(max(val, lohi[k][0]), lohi[k][1])) for k, val in ch_.items()}
                    q = EX.submit(run, (x, t["h"], None)).result(); used += 1; evals += 1
                    area_ok = True if t["exp"] != "Y1" else not (x.get("harvester_beams", 1) >= 2 and t.get("single_solvable"))
                    ok = bool(q["pass_"] and area_ok); reply = feedback(t, x, q); first = evals if ok else None
                    steps.append(dict(x=x, pass_=ok, sim_pass=q["pass_"], area_pass=area_ok)); emit(dict(kind="evaluation", job=jid, step=evals, design=x, pass_=ok, area_pass=area_ok, reason=a.get("reason", "")[:300]))
                else: reply = dict(error="not available (budget used, run over, or tool not offered)")
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e: reply = dict(error=str(e)[:300])
            msgs.append(dict(role="tool", tool_call_id=c["id"], content=json.dumps(reply | dict(units_left=round(units-used, 2)), default=float)))
        if fin or first or t["exp"] != "Y3" and used+(DIAG if arm == "tool" else 1) > units+1e-9: break
    emit(dict(kind="terminal", job=jid, task=t["id"], exp=t["exp"], arm=arm, pass_=bool(first), first_pass=first, evaluations=evals, units=round(used, 2), diag_at=diags, steps=steps,
              verdict=(fin or {}).get("verdict", "FEASIBLE" if first else None), confidence=(fin or {}).get("confidence"), reason=(fin or {}).get("reason", "")[:1500], error=error, usd=usd))
    print(jid, "PASS@%d" % first if first else error or (fin or {}).get("verdict") or "FAIL", flush=True)


def launch():
    from pilots import UNKNOWN_USD, infra
    T = [t for f in sorted(OUT.glob("theorems_v2_Y*.json")) for t in json.loads(f.read_text())["tasks"]]; prev = [json.loads(s) for s in RUNS.read_text().splitlines()] if RUNS.exists() else []
    done = {r["job"] for r in prev if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}
    def allowed(t):
        g = t["gate"]
        if t["exp"] == "Y1": return g["x0_fails"] and g["feasible"] and g["margin_ok"]
        return bool(g.get("ok"))
    ok = [t for t in T if t["exp"] in os.environ.get("ONLY", "Y1 Y2 Y3").split() and allowed(t)]
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
    T = {t["id"]: t for f in sorted(OUT.glob("theorems_v2_Y*.json")) for t in json.loads(f.read_text())["tasks"]}
    rows = [json.loads(s) for f in sorted(OUT.glob("theorems_v2_Y?.jsonl")) for s in f.read_text().splitlines()]
    term = {r["job"]: r for r in rows if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}.values()
    G = lambda r: (lambda t: f"Y1/chi{t['level']}" if t["exp"] == "Y1" else f"Y2/{t['fam']}" if t["exp"] == "Y2" else f"Y3/{t['state']}")(T[r["task"]])+"/"+r["arm"]
    cells = {}
    for r in term: cells.setdefault(G(r), []).append(r)
    def right(r):
        t = T[r["task"]]; k = list(t["x0"])[0]; up = bool(r["steps"]) and r["steps"][0]["x"][k] > t["x0"][k]
        return bool(r["steps"]) and up == (t["theta"] == "-")  # light side needs higher command
    rate = lambda rs, f: (sum(map(f, rs)), len(rs), wilson(sum(map(f, rs)), len(rs)))
    out = {}
    for c, rs in sorted(cells.items()):
        t0 = T[rs[0]["task"]]; d = dict(n=len(rs), passed=rate(rs, lambda r: r["pass_"]))
        if t0["exp"] == "Y1":
            def struct(r):
                want = 1 if T[r["task"]]["single_solvable"] else 2
                return any(s["x"].get("harvester_beams", 1) == want and s.get("pass_") for s in r["steps"]) or (bool(r["steps"]) and r["steps"][-1]["x"].get("harvester_beams", 1) == want and r["pass_"])
            d |= dict(two_beams=rate(rs, lambda r: any(s["x"].get("harvester_beams", 1) >= 2 for s in r["steps"])),
                      structure_ok=rate(rs, struct), area_fail=rate(rs, lambda r: any(s.get("area_pass") is False for s in r["steps"])),
                      evals_mean=round(float(np.mean([r["evaluations"] for r in rs]) if rs else 0), 2))
        if t0["exp"] == "Y2":
            N = [r["first_pass"] or UNITS["Y2"]+1 for r in rs]
            d |= dict(step1=rate(rs, lambda r: r["first_pass"] == 1), N_eval=N, N_eval_mean=round(float(np.mean(N)), 3), units_mean=round(float(np.mean([r["units"] for r in rs])), 3),
                      diag_first=rate(rs, lambda r: 0 in r["diag_at"]), first_move_right=rate(rs, right))
        if t0["exp"] == "Y3":
            inf = lambda r: r["verdict"] == "INFEASIBLE"
            d |= dict(verdicts={v: sum(r["verdict"] == v for r in rs) for v in ("FEASIBLE", "INFEASIBLE", "UNSURE", None)}, infeasible=rate(rs, inf),
                      unsure=rate(rs, lambda r: r["verdict"] == "UNSURE"), tested_other=rate(rs, lambda r: any(s["x"].get("harvester_beams", 1) != 1 for s in r["steps"])),
                      infeasible_without_testing_other=rate(rs, lambda r: inf(r) and not any(s["x"].get("harvester_beams", 1) != 1 for s in r["steps"])))
        d["usd"] = round(sum(r["usd"] for r in rs), 3); out[c] = d; print(c, {k: v for k, v in d.items() if k not in ("N_eval",)})
    def fisher(a, b, key="passed"):
        if a in out and b in out:
            x, y = out[a][key], out[b][key]; return [a, b, key, f"{x[0]}/{x[1]} vs {y[0]}/{y[1]}", round(float(fisher_exact([[x[0], x[1]-x[0]], [y[0], y[1]-y[0]]])[1]), 4)]
    pool = lambda cs, key: (lambda xs: (sum(x[0] for x in xs), sum(x[1] for x in xs)))([out[c][key] for c in cs if c in out])
    for g, cs in dict(Y1_hi_base=["Y1/chi1.1/base", "Y1/chi1.8/base"], Y1_hi_chi=["Y1/chi1.1/chi", "Y1/chi1.8/chi"],
                      Y1_lo_base=["Y1/chi0.6/base", "Y1/chi0.9/base"], Y1_lo_chi=["Y1/chi0.6/chi", "Y1/chi0.9/chi"],
                      Y3_S12_L0=["Y3/S1/L0", "Y3/S2/L0"], Y3_S12_L1=["Y3/S1/L1", "Y3/S2/L1"], Y3_S12_L2=["Y3/S1/L2", "Y3/S2/L2"]).items():
        for key in ("passed", "two_beams", "structure_ok", "infeasible"):
            if all(key in out.get(c, {}) for c in cs): k, n = pool(cs, key); out[f"pool/{g}"] = out.get(f"pool/{g}", {}) | {key: (k, n, wilson(k, n))}
    tests = [fisher(*a) for a in (("pool/Y1_hi_chi", "pool/Y1_hi_base"), ("pool/Y1_lo_chi", "pool/Y1_lo_base", "structure_ok"),
             ("pool/Y1_hi_chi", "pool/Y1_hi_base", "structure_ok"), ("pool/Y1_lo_base", "pool/Y1_hi_base", "structure_ok"),
             ("Y3/S3/L2", "Y3/S3/L0", "infeasible"), ("Y3/S3/L1", "Y3/S3/L0", "infeasible"),
             ("pool/Y3_S12_L0", "pool/Y3_S12_L2", "infeasible"), ("pool/Y3_S12_L0", "pool/Y3_S12_L1", "infeasible"))]
    if "Y2/II/tool" in out and "Y2/II/blind" in out:
        tests += [fisher("Y2/II/tool", "Y2/II/blind", "step1"), fisher("Y2/II/given", "Y2/II/blind", "step1")]
        for a in ("tool", "given"):
            tests.append(["Y2/II/"+a, "Y2/II/blind", "N_eval MWU", round(float(mannwhitneyu(out["Y2/II/"+a]["N_eval"], out["Y2/II/blind"]["N_eval"]).pvalue), 4)])
    tests = [x for x in tests if x]; print(*tests, sep="\n")
    resp = [r for r in rows if r["kind"] == "response"]; from pilots import UNKNOWN_USD
    usage = dict(requests=len(resp), usd=round(sum(r["usd"] for r in resp)+UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in rows), 3), unknown=sum(r["kind"] == "UNKNOWN" for r in rows),
                 infra_attempts=sum(r["kind"] == "terminal" and infra(r) for r in rows), terminals=len(term))
    print(usage); (OUT/"theorems_v2_summary.json").write_text(json.dumps(dict(usage=usage, cells=out, tests=tests), indent=1, default=float))


if __name__ == "__main__" and "--report" in sys.argv: report()
