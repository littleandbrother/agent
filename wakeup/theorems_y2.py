"""Y2 (t36u tweak 1): resonance-side pair on tip mass, beam length fixed 30 mm. Hidden assembly error: heavy (actual = set + d1, drive above
resonance, fix = lighter) vs light (actual = set - d2, drive below resonance, fix = heavier); d2 tuned so the displayed base feedback is identical.
--build: sim-only gate -> pilots/theorems_Y2.json; --run: agents (X2-I loop) -> pilots/theorems_Y2.jsonl; --report."""
import concurrent.futures as cf
import json
import os
import sys
import threading
from pathlib import Path

import numpy as np
import theorems as T0
from sim import simulate

OUT, M0, CACHE = Path(__file__).resolve().parent/"pilots", 4.65, Path("/tmp/theorems_Y2_simcache.jsonl")  # M0: loaded-resonance set mass (measured phase -90 deg)
UNITS, DIAG, ARMS = 4, .2, ("blind", "tool", "given")
MEMO = {tuple(json.loads(s)[0]): json.loads(s)[1] for s in CACHE.read_text().splitlines()} if CACHE.exists() else {}


def sim(m, h):
    """Full transient run at ACTUAL tip mass m; lag = phase of tip deflection behind the inertial drive -m_f*a_base, fitted on [t1-2.5, t1-0.5] s."""
    k = (round(m, 4), h["tx"], h["bg"], h["C"], h["t1"])
    if k in MEMO: return MEMO[k]
    d, task = T0.node(dict(tip_mass_g=m, storage_uF=h["C"]), h | dict(mass=m)); r = simulate(d, task); M = r["metrics"]
    t, y = np.array(r["trace"]["t"]), r["trace"]["y"]; s = (t > h["t1"]-2.5) & (t < h["t1"]-.5); w = 2*np.pi*45
    a, b = np.linalg.lstsq(np.c_[np.sin(w*t[s]), np.cos(w*t[s])], y[s, 0], rcond=None)[0]
    q = dict(pass_=r["verdict"] == "PASS", delivered=M["delivered_on_time"], brownouts=M["brownouts"], ready=M["cold_charge_ready_s"], final=M["final_storage_V"], lag=float(-np.degrees(np.arctan2(-b, -a))))
    MEMO[k] = q; CACHE.open("a").write(json.dumps([k, q])+"\n"); return q


def feedback(q):
    return {"passed": q["pass_"], "delivered_on_time": f"{q['delivered']}/4", "brownouts": q["brownouts"], "cold_charge_ready_s": q["ready"] and round(q["ready"], 1), "final_storage_V": round(q["final"], 1)}


def diagnose(q):
    return dict(phase_lag_deg=round(q["lag"]), measured="phase lag of the harvester tip deflection behind the inertial base-drive force at 45 Hz, fitted on the simulated transient before the first fault")


def pair(a):
    i, bg, tx = a; C = round(1.15*2*T0.energy(tx)/(T0.VON**2-T0.VOFF**2), 1); h = dict(tx=tx, bg=bg, C=C, t1=11.5)
    h["t1"] = round(min(11.5, sim(M0, h)["ready"]+2.5), 2)
    d1 = next(d for d in (.6, .7, .85) if sim(M0+d, h)["ready"] is None); target = sim(M0+d1, h)["final"]; lo, hi = .02, .6
    for _ in range(10):
        mid = (lo+hi)/2; q = sim(M0-mid, h); lo, hi = (mid, hi) if q["ready"] or q["final"] > target else (lo, mid)
    return i, h, d1, round((lo+hi)/2, 4)


def build():
    from multiprocessing import Pool
    r = np.random.default_rng(20261122); spec = [(i, float(r.uniform(.12, .15)), float(r.uniform(10, 14))) for i in range(8)]; tasks = []
    log = lambda s: (print(s, flush=True), open("/workspace/theorems_Y2_build.log", "a").write(s+"\n"))
    with Pool(int(os.environ.get("PROCS", 6))) as p:
        pairs = p.map(pair, spec, chunksize=1)
        for i, h, d1, d2 in pairs: log(f"p{i} {h} d1={d1} d2={d2}")
        grid = sorted(set(np.round(np.r_[np.arange(3.6, 4.2, .2), np.arange(4.2, 5.21, .05), np.arange(5.4, 6.61, .2)], 2)))
        jobs = [(m, h) for _, h, d1, d2 in pairs for m in grid+[M0, M0+d1, M0-d2]]
        res = p.starmap(sim, jobs, chunksize=1)
    R = {(round(m, 4), h["t1"], h["bg"]): q for (m, h), q in zip(jobs, res)}
    for i, h, d1, d2 in pairs:
        q = lambda m: R[(round(m, 4), h["t1"], h["bg"])]; ok_ = [m for m in grid if q(m)["pass_"]]
        F = dict(heavy=[round(m-d1, 3) for m in ok_ if 3.8 <= m-d1 <= 5.8], light=[round(m+d2, 3) for m in ok_ if 3.8 <= m+d2 <= 5.8])
        base = dict(heavy=q(M0+d1), light=q(M0-d2))
        g = dict(identical_base=feedback(base["heavy"]) == feedback(base["light"]), disjoint=bool(F["heavy"]) and bool(F["light"]) and max(F["heavy"]) < min(F["light"]),
                 both_fail_base=not base["heavy"]["pass_"] and not base["light"]["pass_"], ideal_passes=q(M0)["pass_"],
                 phase_sides=base["heavy"]["lag"] > 90 > base["light"]["lag"], final_raw=[round(base[k]["final"], 4) for k in base], lag=[round(base[k]["lag"], 1) for k in base])
        g["ok"] = g["identical_base"] and g["disjoint"] and g["both_fail_base"] and g["ideal_passes"]
        for k, dm in (("heavy", d1), ("light", -d2)):
            tasks.append(dict(id=f"Y2/p{i}/{k}", theta=k, h=h | dict(dm=dm), d=dict(heavy=d1, light=d2), x0=dict(tip_mass_g=M0), truth=dict(passing=F[k], window=[min(F[k]), max(F[k])] if F[k] else None, actual_pass=ok_), base=feedback(base[k]), gate=g))
        log(f"p{i} F_heavy={tasks[-2]['truth']['window']} F_light={tasks[-1]['truth']['window']} base={feedback(base['heavy'])} {g}")
    (OUT/"theorems_Y2.json").write_text(json.dumps(dict(M0=M0, grid=grid, tasks=tasks), indent=1, default=float))


if __name__ == "__main__" and "--build" in sys.argv: build()


def prompt(t, arm):
    h, d = t["h"], t["d"]
    s = T0.describe(dict(h=h, exp="X1"))[0]+(f" One harvester beam, length 30 mm (fixed); storage capacitance fixed at {h['C']} uF. The set tip mass {M0} g would put the beam at its loaded resonance "
         f"with the 45 Hz background (power-optimal) if installed exactly, but the installed tip mass carries a hidden fixed assembly offset that applies to whatever value you set. Exactly one of two equally likely conditions holds: "
         f"theta_heavy: actual tip mass = set value + {d['heavy']} g; theta_light: actual tip mass = set value - {d['light']} g.")
    return (f"Find a passing design. evaluate(changes, reason) patches the CURRENT design and runs the official simulation (cost 1 unit). The run ends at the first passing evaluation. Budget {UNITS} units."
            + (f" diagnose() measures the CURRENT design (cost {DIAG} unit)." if arm == "tool" else "")+"\n"+s+"\nVariables: "+json.dumps(dict(tip_mass_g="set tip mass, g, 3.8-5.8")))


def agent(job, EX, emit, tally, lock, halt, key):
    from agent_limits import ask
    from pilots import PRICE, UNKNOWN_USD
    t, arm = job; jid = f"{t['id']}/{arm}"; rates = PRICE["deepseek-flash"]; h = t["h"]; x = dict(t["x0"])
    q0 = EX.submit(sim, x["tip_mass_g"]+h["dm"], h).result(); user = dict(design=x, feedback=feedback(q0)) | (dict(diagnosis=diagnose(q0)) if arm == "given" else {})
    fn = lambda name, desc, props: dict(type="function", function=dict(name=name, description=desc, parameters=dict(type="object", properties=props, required=list(props))))
    tl = [fn("evaluate", "Patch the CURRENT design and run the official full simulation.", dict(changes=dict(type="object", properties=dict(tip_mass_g=dict(type="number", description="set tip mass, g, 3.8-5.8")), additionalProperties=False), reason=dict(type="string")))]
    if arm == "tool": tl.append(fn("diagnose", f"Measure the CURRENT design (cost {DIAG} unit).", {}))
    msgs = [dict(role="system", content=prompt(t, arm)), dict(role="user", content=json.dumps(user))]
    used, evals, diags, first, error, usd, steps = 0., 0, [], None, None, 0., []
    for _ in range(16):
        raw = json.dumps(dict(model="deepseek-flash", messages=msgs, tools=tl, tool_choice="auto", max_tokens=65536, stream=True, stream_options=dict(include_usage=True), thinking=dict(type="enabled"), reasoning_effort="high")).encode()
        reserve = (len(raw)*rates["input"]+65536*rates["output"])/1e6
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
                if name == "diagnose" and arm == "tool" and used+DIAG <= UNITS+1e-9: used += DIAG; diags.append(evals); reply = diagnose(EX.submit(sim, x["tip_mass_g"]+h["dm"], h).result())
                elif name == "evaluate" and used+1 <= UNITS+1e-9 and first is None:
                    x = dict(tip_mass_g=float(min(max(a["changes"]["tip_mass_g"], 3.8), 5.8)))
                    q = EX.submit(sim, x["tip_mass_g"]+h["dm"], h).result(); used += 1; evals += 1; reply = feedback(q); first = evals if q["pass_"] else None
                    steps.append(dict(x=x, pass_=q["pass_"])); emit(dict(kind="evaluation", job=jid, step=evals, design=x, pass_=q["pass_"], reason=a.get("reason", "")[:300]))
                else: reply = dict(error="not available (budget used, run over, or tool not offered)")
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e: reply = dict(error=str(e)[:300])
            msgs.append(dict(role="tool", tool_call_id=c["id"], content=json.dumps(reply | dict(units_left=round(UNITS-used, 2)))))
        if first or used+(DIAG if arm == "tool" else 1) > UNITS+1e-9: break
    emit(dict(kind="terminal", job=jid, task=t["id"], arm=arm, pass_=bool(first), first_pass=first, evaluations=evals, units=round(used, 2), diag_at=diags, steps=steps, error=error, usd=usd))
    print(jid, "PASS@%d" % first if first else error or "FAIL", flush=True)


RUNS = OUT/"theorems_Y2.jsonl"


def launch():
    from pilots import UNKNOWN_USD, infra
    prev = [json.loads(s) for s in RUNS.read_text().splitlines()] if RUNS.exists() else []
    done = {r["job"] for r in prev if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}
    T = [t for t in json.loads((OUT/"theorems_Y2.json").read_text())["tasks"] if t["gate"]["ok"]]
    jobs = sorted([(t, a) for t in T for a in ARMS if f"{t['id']}/{a}" not in done], key=lambda j: (j[0]["id"][:6], j[1], j[0]["id"]))
    lock, halt = threading.Lock(), threading.Event(); key = os.environ["DEEPSEEK_API_KEY"]
    tally = dict(spent=sum(r["usd"] for r in prev if r["kind"] == "response")+UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in prev), reserved=0., cap=float(os.environ.get("CAP", 1.5)))
    def emit(row):
        with lock, RUNS.open("a") as f: f.write(json.dumps(row, ensure_ascii=False, default=float)+"\n")
    print(len(jobs), "jobs; spent so far", round(tally["spent"], 3), flush=True)
    with cf.ProcessPoolExecutor(int(os.environ.get("PROCS", 6))) as EX, cf.ThreadPoolExecutor(int(os.environ.get("WORKERS", 8))) as pool:
        list(pool.map(lambda j: None if halt.is_set() else agent(j, EX, emit, tally, lock, halt, key), jobs))
    print(json.dumps(tally))


if __name__ == "__main__" and "--run" in sys.argv: launch()


def report():
    from scipy.stats import fisher_exact, mannwhitneyu
    from pilots import UNKNOWN_USD, infra, wilson
    T = {t["id"]: t for t in json.loads((OUT/"theorems_Y2.json").read_text())["tasks"]}; rows = [json.loads(s) for s in RUNS.read_text().splitlines()]
    term = list({r["job"]: r for r in rows if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}.values())
    rate = lambda rs, f: (sum(map(f, rs)), len(rs), wilson(sum(map(f, rs)), len(rs)))
    right = lambda r: bool(r["steps"]) and (r["steps"][0]["x"]["tip_mass_g"] < M0) == (T[r["task"]]["theta"] == "heavy")
    out = {}
    for a in ARMS:
        rs = [r for r in term if r["arm"] == a]; N = [r["first_pass"] or UNITS+1 for r in rs]
        out[a] = dict(n=len(rs), passed=rate(rs, lambda r: r["pass_"]), step1=rate(rs, lambda r: r["first_pass"] == 1), first_move_right=rate(rs, right), diag_first=rate(rs, lambda r: 0 in r["diag_at"]),
                      N_eval=N, N_eval_mean=round(float(np.mean(N)), 3), units_mean=round(float(np.mean([r["units"] for r in rs])), 3), usd=round(sum(r["usd"] for r in rs), 3))
        print(a, {k: v for k, v in out[a].items() if k != "N_eval"})
    tests = [[a, "blind", k, f"{out[a][k][0]}/{out[a][k][1]} vs {out['blind'][k][0]}/{out['blind'][k][1]}", round(float(fisher_exact([[out[a][k][0], out[a][k][1]-out[a][k][0]], [out["blind"][k][0], out["blind"][k][1]-out["blind"][k][0]]])[1]), 4)]
             for a in ("tool", "given") for k in ("step1", "passed", "first_move_right")]
    tests += [[a, "blind", "N_eval MWU", round(float(mannwhitneyu(out[a]["N_eval"], out["blind"]["N_eval"]).pvalue), 4)] for a in ("tool", "given")]
    print(*tests, sep="\n")
    usage = dict(requests=sum(r["kind"] == "response" for r in rows), usd=round(sum(r["usd"] for r in rows if r["kind"] == "response")+UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in rows), 3),
                 unknown=sum(r["kind"] == "UNKNOWN" for r in rows), infra_attempts=sum(r["kind"] == "terminal" and infra(r) for r in rows), terminals=len(term))
    print(usage); (OUT/"theorems_Y2_summary.json").write_text(json.dumps(dict(usage=usage, cells=out, tests=tests), indent=1, default=float))


if __name__ == "__main__" and "--report" in sys.argv: report()
