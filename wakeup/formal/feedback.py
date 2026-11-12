"""E1: hidden fabrication factors, one true transient, nested observed facts."""
import copy
import json
from pathlib import Path
from common import project
import numpy as np

HERE = Path(__file__).resolve().parent
DOMAIN = {"main_length_mm": [24., 42.], "aux_length_mm": [11., 24.],
          "storage_uF": [80., 1000.], "start_V": [1.9, 3.2], "wake_high_V": [.15, 2.]}


def build(seed=20261112, n=20):
    """Outcome-blind candidates; a rejected candidate stays visible in calibration."""
    rng = np.random.default_rng(seed)
    base = json.loads((HERE.parent / "design.json").read_text())
    import sys
    sys.path.insert(0, str(HERE.parent))
    from sim import TASK
    tasks = []
    for i in range(n):
        kind = ("main", "aux", "both", "threshold")[i % 4]
        fm = float(rng.uniform(.74, .80)) if kind in ("main", "both") else 1.
        fa = float(rng.uniform(1.27, 1.42)) if kind in ("aux", "both") else 1.
        nominal = copy.deepcopy(base)
        nominal["harvester"]["length_mm"] = 35.5 if fm != 1 else 30.
        nominal["trigger_beam"]["length_mm"] = 18.
        if kind == "threshold":
            nominal["circuit"]["wake_high_V"] = float(rng.uniform(1.1, 1.7))
        witness = copy.deepcopy(base)
        witness["harvester"]["length_mm"] /= fm
        witness["trigger_beam"]["length_mm"] /= fa
        env = copy.deepcopy(TASK)
        env["background_peak_g"] *= float(rng.uniform(.99, 1.01))
        env["fault_peak_g"] *= float(rng.uniform(.98, 1.02))
        tasks.append(dict(id=f"E1-{i+1:02}", case="wake", kind=kind, seed=seed,
                          domain=DOMAIN, initial=nominal, witness=witness, environment=env,
                          hidden_factors=dict(main_length=fm, aux_length=fa)))
    return tasks


def public(task):
    """Only this object may be shown to a future Agent; no witness or fault label."""
    return {k:copy.deepcopy(task[k]) for k in ("id", "case", "domain", "initial", "environment")}


def build_impact(seed=20261114, n=10):
    """Independent realization draws around the separately found Case-2 design."""
    source = json.loads((HERE/"case2.json").read_text())
    base, env = source["design"], source["task"]
    rng = np.random.default_rng(seed)
    tasks = []
    for i in range(n):
        fm = float(rng.uniform(.73,.79)) if i % 2 == 0 else 1.
        initial, witness = copy.deepcopy(base), copy.deepcopy(base)
        if i % 2:
            initial["circuit"]["wake_high_V"] = float(rng.uniform(2.4,3.1))
        witness["harvester"]["length_mm"] /= fm
        tasks.append(dict(id=f"E1-impact-{i+1:02}",case="impact",kind="main" if i%2==0 else "threshold",
            seed=seed, domain={**DOMAIN,"wake_high_V":[.6,3.2],"storage_uF":[80.,1000.]},
            initial=initial,witness=witness,environment=copy.deepcopy(env),
            hidden_factors=dict(main_length=fm,aux_length=1.),
            scientific_note="A disabled, harvester envelope detects 47Hz shock, D is a physical voltage-dependent resistive shunt. Not the 210Hz dual-beam service."))
    return tasks


def calibrate_impact(workers=2):
    from concurrent.futures import ProcessPoolExecutor
    tasks=build_impact()
    out=HERE/"outputs"
    save=lambda p,v:p.write_text(json.dumps(v,indent=2)+"\n")
    save(out/"e1_impact_tasks.json",tasks)
    save(out/"e1_impact_public_tasks.json",[public(t) for t in tasks])
    # All corrected designs realize exactly the prototype; verify it once, reference it openly.
    with ProcessPoolExecutor(workers) as pool:
        rows=list(pool.map(job,[(t,"initial") for t in tasks]+[(tasks[0],"witness")]))
    save(out/"e1_impact_calibration.json",rows)
    witness=rows[-1]
    summary=dict(status=[dict(id=r["id"], initial_zero=r["result"]["metrics"]["delivered_on_time"]==0,
        witness_pass=witness["result"]["verdict"]=="PASS", common_witness="E1-impact-01/witness",
        qualified=r["domain_ok"] and all(in_domain(t,t["witness"]) for t in tasks) and r["result"]["metrics"]["delivered_on_time"]==0 and witness["result"]["verdict"]=="PASS") for r in rows[:-1]],
        new_full_calls=len(rows),exact_common_realization="All witnesses undo their own length factor and realize the same passing Case-2 prototype.")
    save(out/"e1_impact_summary.json",summary)
    # Formal E1 uses ten independent wake draws and ten independent impact draws; twenty wake development draws remain intact.
    wake=json.loads((out/"e1_tasks.json").read_text())[:10]
    save(out/"e1_formal_tasks.json",wake+tasks)
    save(out/"e1_formal_public_tasks.json",[public(t) for t in wake+tasks])
    return summary


def actual(task, design):
    d = copy.deepcopy(design)
    d["harvester"]["length_mm"] *= task["hidden_factors"]["main_length"]
    d["trigger_beam"]["length_mm"] *= task["hidden_factors"]["aux_length"]
    return d


def in_domain(task, design):
    pairs = [("main_length_mm", design["harvester"]["length_mm"]),
             ("aux_length_mm", design["trigger_beam"]["length_mm"]),
             ("storage_uF", design["circuit"]["storage_uF"]),
             ("start_V", design["circuit"]["start_V"]),
             ("wake_high_V", design["circuit"]["wake_high_V"])]
    return all(task["domain"][k][0] <= v <= task["domain"][k][1] for k, v in pairs) and design["circuit"]["wake_low_V"] < design["circuit"]["wake_high_V"]


def job(item):
    import sys
    sys.path.insert(0, str(HERE.parent))
    from sim import simulate
    task, which = item
    r = simulate(actual(task, task[which]), task["environment"])
    levels = [project(r, k) for k in range(4)]
    result = {k:r[k] for k in ("verdict", "checks", "metrics", "energy_J", "runtime_s")}
    return dict(id=task["id"], which=which, result=result, feedback=levels, domain_ok=in_domain(task,task[which]),
                nested=all(all(levels[k+1][name] == value for name,value in levels[k].items()) for k in range(3)))


def calibrate_wake(n=20, workers=4):
    from concurrent.futures import ProcessPoolExecutor
    tasks = build(n=n)
    out = HERE / "outputs"
    out.mkdir(exist_ok=True)
    (out/"e1_tasks.json").write_text(json.dumps(tasks, indent=2)+"\n")
    (out/"e1_public_tasks.json").write_text(json.dumps([public(t) for t in tasks], indent=2)+"\n")
    results = []
    with ProcessPoolExecutor(workers) as pool, (out/"e1_calibration.jsonl").open("w") as stream:
        for r in pool.map(job, [(t,w) for t in tasks for w in ("initial", "witness")]):
            results.append(r); stream.write(json.dumps(r)+"\n"); stream.flush()
            print(r["id"], r["which"], r["result"]["verdict"], r["result"]["metrics"]["delivered_on_time"], flush=True)
    status = []
    for t in tasks:
        a, b = [r for r in results if r["id"] == t["id"]]
        status.append(dict(id=t["id"], case=t["case"], initial_zero=a["result"]["metrics"]["delivered_on_time"] == 0,
            witness_pass=b["result"]["verdict"] == "PASS", nested=a["nested"] and b["nested"],
            qualified=a["domain_ok"] and b["domain_ok"] and a["result"]["metrics"]["delivered_on_time"] == 0 and b["result"]["verdict"] == "PASS"))
    (out/"e1_summary.json").write_text(json.dumps(dict(seed=20261112, status=status, count=sum(s["qualified"] for s in status),
        missing="Impact/shunt subset requires separately calibrated passing Case 2; these are wake-node tasks only.",
        independence="Independent fabrication draws; task-family generalization is not implied."), indent=2)+"\n")
    return results


def formal_summary():
    out=HERE/"outputs"
    wake=json.loads((out/"e1_summary.json").read_text())["status"][:10]
    impact=json.loads((out/"e1_impact_summary.json").read_text())["status"]
    rows=[dict(r,case="wake") for r in wake]+[dict(r,case="impact") for r in impact]
    summary=dict(experiment="E1",requested=20,count=sum(r["qualified"] for r in rows),status=rows,
        cases=dict(wake=10,impact=10),
        actual_measurement="Loaded voltage amplitude/phase fitted to the simulated trajectory, not a nominal analytical substitute.",
        deployment="Calibration witnesses are private. No model or Agent experiment has run.")
    (out/"e1_formal_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary


def calibrate(workers=4):
    """The formal twenty: ten wake tasks plus ten impact tasks."""
    calibrate_wake(n=10,workers=workers)
    calibrate_impact(workers=workers)
    return formal_summary()


if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--workers",type=int,default=4)
    a=p.parse_args();print(calibrate(a.workers))
