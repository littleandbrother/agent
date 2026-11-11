"""Y3: non-saturating stop certificate. Branches harvester_beams in {1,2,3,4}; history = 4 failed one-beam points with only pass/delivered;
2 extra evaluations. S1 narrow 1-beam window; S2 only the 4-beam branch feasible; S3 all four infeasible. Levels L0 points / L1 U_m0 / L2 all U_m.
--build: simulation gate -> pilots/theorems_Y3.json; --run: agents -> pilots/theorems_Y3.jsonl; --report."""
import concurrent.futures as cf
import json
import os
import sys
import threading
from pathlib import Path

import numpy as np
import theorems as T
from theorems import TASK, TAU, VON, VOFF, energy, run, window

OUT, CACHE, B, N = T.OUT, Path("/tmp/theorems_simcache_Y3.json"), (1, 2, 3, 4), 6
log = lambda s: (print(s, flush=True), Path("/workspace/theorems_Y3_gate.log").open("a").write(s+"\n"))


def build(pool):
    memo = json.loads(CACHE.read_text())
    def sims(jobs):
        k = [json.dumps(j, default=float) for j in jobs]; new = [j for j, s in zip(jobs, k) if s not in memo]
        for j, q in zip(new, pool.map(run, new)): memo[json.dumps(j, default=float)] = q
        CACHE.write_text(json.dumps(memo)); return [memo[s] for s in k]
    ms = [m for m in sorted(set(np.round(np.r_[np.arange(3.8, 5.81, .05), np.arange(4.45, 4.8, .0125)], 4))) if 4.3 <= m <= 4.9]
    curve = {n: dict(zip(ms, T.pc(sims([(dict(harvester_beams=n, tip_mass_g=m, storage_uF=T.CREF), dict(tx=12.), 15.) for m in ms])))) for n in B}
    mo = max(curve[1], key=curve[1].get); P = {n: curve[n][mo] for n in B}; log(f"curve m*={mo} P={ {n: round(p, 1) for n, p in P.items()} }")
    grid = lambda lo, hi: list(np.round(np.geomspace(lo, hi, 18), 2))
    def truth(h, n, w):
        cs = grid(.7*w[1]["C_min_uF"], 1.5*max(w[n]["C_max_uF"], w[1]["C_min_uF"])); ok = [c for c, q in zip(cs, sims([(dict(harvester_beams=n, tip_mass_g=mo, storage_uF=c), h, None) for c in cs])) if q["pass_"]]
        return dict(passing=ok, window=[min(ok), max(ok)] if ok else None)
    def cert(h, n, cmin):
        xs = [dict(harvester_beams=n, tip_mass_g=mo, storage_uF=round(c, 2)) for c in [30, 600]+list(np.geomspace(.6*cmin, 1.6*cmin, 8))]
        return dict(points=len(xs), hits=sum(q["pass_"] for q in sims([(x, h, None) for x in xs])))
    tasks, r = [], np.random.default_rng(20261113)
    for i in range(N):
        for s, n, chi in (("S1", 1, .85), ("S2", 4, .85), ("S3", 4, 1.2)):
            tx = float(r.uniform(8, 20)); E = energy(tx); t1 = 2*E/(VON**2-VOFF**2)*VON**2/(2*P[n]*chi)-TASK["delivery_deadline_s"]+TAU
            h = dict(mass=mo, tx=tx, t1=float(t1)); w = {k: window(E, P[k], t1) for k in B}
            hist_x = [dict(harvester_beams=1, tip_mass_g=mo, storage_uF=round(f*w[1]["C_min_uF"])) for f in (.7, .85, 1.25, 1.6)]
            hist = [dict(design=x, feedback=fb(q)) for x, q in zip(hist_x, sims([(x, h, None) for x in hist_x]))]
            ratio = {k: round(max(curve[k].values())/P[k]/w[k]["chi"], 3) for k in B}
            feas = {"S1": {1}, "S2": {4}, "S3": set()}[s]
            tr = {k: truth(h, k, w) if k in feas else cert(h, k, w[k]["C_min_uF"]) for k in (B if s != "S1" else (1,))}
            ok = all(bool(tr[k]["passing"]) if k in feas else tr[k]["hits"] == 0 for k in tr) and not any(q["feedback"]["pass"] for q in hist) and all((ratio[k] >= 1) == (k in feas) for k in tr)
            tasks.append(dict(id=f"Y3/{s}/i{i}", exp="X3", state=s, h=h, x0=hist_x[-1], history=hist, window=w, ratio=ratio, truth=tr, feasible=s != "S3", gate=dict(ok=ok)))
            log(f"{tasks[-1]['id']} t1={t1:.2f} chi={ {k: w[k]['chi'] for k in B} } ratio={ratio} truth={ {k: v.get('window', v.get('hits')) for k, v in tr.items()} } ok={ok}")
        (OUT/"theorems_Y3.json").write_text(json.dumps(dict(m_opt=mo, P=P, tasks=tasks), indent=1, default=float))  # saved per instance: runs may start on gated instances


def fb(q):  # cold_charge_ready_s and all timing/voltage diagnostics hidden
    return {"pass": q["pass_"], "delivered_on_time": f"{q['delivered']}/4"}


if __name__ == "__main__" and "--build" in sys.argv:
    from multiprocessing import Pool
    with Pool(int(os.environ.get("POOL", 6))) as p: build(p)

V = dict(storage_uF="storage capacitance, uF, 20-1000", harvester_beams="number of identical parallel harvester beams, 1, 2, 3 or 4", tip_mass_g="tip mass per beam, g, 3.8-5.8 (beam length 30 mm)")
T.DOM["harvester_beams"], T.UNITS["X3"], T.RUNS = (1, 4), 2, OUT/"theorems_Y3.jsonl"
T.describe, T.feedback = (lambda t, d=T.describe: (d(t)[0], V)), (lambda t, x, q: fb(q))
T.evidence = lambda t, arm: dict(history=t["history"]) | ({} if arm == "L0" else dict(analysis={f"harvester_beams={k}": dict(
    best_C_max_over_C_min=t["ratio"][str(k)], scope=f"exhaustive over all tip masses and capacitances with {k} beam(s); a passing design in this branch needs this ratio >= 1") for k in (B[:1] if arm == "L1" else B)}))


def launch():
    from pilots import UNKNOWN_USD, infra
    tasks = [t for t in json.loads((OUT/"theorems_Y3.json").read_text())["tasks"] if t["gate"]["ok"]]; prev = [json.loads(s) for s in T.RUNS.read_text().splitlines()] if T.RUNS.exists() else []
    done = {r["job"] for r in prev if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}
    jobs = sorted([(t, a) for t in tasks for a in ("L0", "L1", "L2") if f"{t['id']}/{a}" not in done], key=lambda j: (j[0]["id"][-1], j[1], j[0]["id"]))
    lock, halt, key = threading.Lock(), threading.Event(), os.environ["DEEPSEEK_API_KEY"]
    tally = dict(spent=sum(r["usd"] for r in prev if r["kind"] == "response")+UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in prev), reserved=0., cap=float(os.environ.get("CAP", 2.)))
    def emit(row):
        with lock, T.RUNS.open("a") as f: f.write(json.dumps(row, ensure_ascii=False, default=float)+"\n")
    print(len(jobs), "jobs; spent so far", round(tally["spent"], 3), flush=True)
    with cf.ProcessPoolExecutor(4) as EX, cf.ThreadPoolExecutor(int(os.environ.get("WORKERS", 8))) as pool:
        list(pool.map(lambda j: None if halt.is_set() else T.agent(j, EX, emit, tally, lock, halt, key), jobs))
    print(json.dumps(tally))


if __name__ == "__main__" and "--run" in sys.argv: launch()


def report():
    from scipy.stats import fisher_exact
    from pilots import UNKNOWN_USD, infra, wilson
    Tk = {t["id"]: t for t in json.loads((OUT/"theorems_Y3.json").read_text())["tasks"]}; rows = [json.loads(s) for s in T.RUNS.read_text().splitlines()]
    term = {r["job"]: r for r in rows if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}.values(); cells = {}
    for r in term: cells.setdefault(f"{Tk[r['task']]['state']}/{r['arm']}", []).append(r)
    rate = lambda rs, f: (sum(map(f, rs)), len(rs), wilson(sum(map(f, rs)), len(rs)))
    inf = lambda r: r["verdict"] == "INFEASIBLE"; out = {}
    for c, rs in sorted(cells.items()):
        out[c] = dict(n=len(rs), verdicts={str(v): sum(r["verdict"] == v for r in rs) for v in ("FEASIBLE", "INFEASIBLE", "UNSURE", None)}, infeasible=rate(rs, inf), found=rate(rs, lambda r: r["pass_"]),
                      tested_4=rate(rs, lambda r: any(s["x"].get("harvester_beams") == 4 for s in r["steps"])), evals_mean=round(float(np.mean([r["evaluations"] for r in rs])), 2), usd=round(sum(r["usd"] for r in rs), 3))
        print(c, out[c])
    for a in ("L0", "L1", "L2"):
        xs = [out[f"{s}/{a}"]["infeasible"] for s in ("S1", "S2") if f"{s}/{a}" in out]; k, n = sum(x[0] for x in xs), sum(x[1] for x in xs); out[f"S12/{a}"] = dict(infeasible=(k, n, wilson(k, n)))
    fisher = lambda a, b, key: (lambda x, y: [a, b, key, f"{x[0]}/{x[1]} vs {y[0]}/{y[1]}", round(float(fisher_exact([[x[0], x[1]-x[0]], [y[0], y[1]-y[0]]])[1]), 4)])(out[a][key], out[b][key])
    tests = [fisher(f"S12/{a}", "S12/L2", "infeasible") for a in ("L0", "L1")]+[fisher(f"S2/{a}", "S2/L2", "found") for a in ("L0", "L1")]+[fisher(f"S3/{a}", "S3/L2", "infeasible") for a in ("L0", "L1")]+[fisher("S3/L0", "S3/L1", "infeasible")]+[fisher("S1/L0", "S1/L2", "infeasible")]
    print(*tests, sep="\n"); resp = [r for r in rows if r["kind"] == "response"]
    usage = dict(requests=len(resp), usd=round(sum(r["usd"] for r in resp)+UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in rows), 3), infra_attempts=sum(r["kind"] == "terminal" and infra(r) for r in rows), terminals=len(term))
    print(usage); (OUT/"theorems_Y3_summary.json").write_text(json.dumps(dict(usage=usage, cells=out, tests=tests), indent=1, default=float))


if __name__ == "__main__" and "--report" in sys.argv: report()
