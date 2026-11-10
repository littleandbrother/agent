"""Boundary pilots A-L+X on world.py: --run (agents; USD cap on the uncached peak-rate estimate), --report."""
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import threading
from collections import defaultdict
from pathlib import Path

import numpy as np
from agent_limits import RATES, ask
from world import HIDDEN, MODS, NAMES, PRIMS, VARS, X0, best, inner, internal, margin, physics

OUT = Path(__file__).resolve().parent/"pilots"
TASKS = {t["id"]: t for f in ("tasks.json", "confirm.json", "decisive.json", "closureA.json") if (OUT/f).exists() for t in json.loads((OUT/f).read_text())}
ARMS, OWN = ("base", "branch", "bound", "hint", "anon"), dict(W="th", S="Vs", U="V", M="C")  # Exp 2 arms; each module's own parameter
TASKS |= {f"{g}/{a}/{k[3:]}": t | dict(id=f"{g}/{a}/{k[3:]}", arm=a, opaque=g == "G3") for k, t in list(TASKS.items()) if k.startswith("G2/p") for a in ARMS for g in ("G2", "G3")}  # G3: S semantics hidden
RUNS = OUT/os.environ.get("RUNS", "runs.jsonl")
PRICE = {"deepseek-flash": RATES, "deepseek-v4-pro": dict(input=1.32, output=3.96)}  # official peak, cache miss
CACHE_SAVING = {"deepseek-flash": .30-.006, "deepseek-v4-pro": 1.32-.044}
UNKNOWN_USD = .0786  # unsettled request: charge its full flash output reservation to the cap
CAP = float(os.environ.get("CAP", 20.))
_, MAX_OUT, SEEDS, WORKERS, PROBES, PY_CALLS = 0, 65536, 3, int(os.environ.get("WORKERS", 12)), 200, 20
ORDER = "EGHFAXDLBCKIJ"
LURES = ["gain_trim", "q_boost", "efficiency_tune", "damping_trim", "impedance_bias", "harvest_gain", "beam_preload", "phase_trim"]
PURPOSE = ("Node bolted to a truck chassis inside a sealed enclosure with 2 mm internal clearance around the beam. "
           "It must report every bump, must never wake on steady road hum, and must run maintenance-free for five years as components age.")
MEANING = dict(h="beam thickness multiplier (steel + PZT)", m="harvester tip mass, g", R="rectifier input load, kOhm", C="storage capacitance, uF",
               V="MCU start threshold, V (brownout 1.8 V)", T="poll interval, ms (used when no wake trigger)", th="wake comparator threshold, V", Vs="shunt threshold, V")
HINTS = dict(displacement=r"displac|deflect|clearance|2 ?mm|stroke", false_wake=r"false|hum|spurious|nuisance", aging=r"aging|ageing|degrad|derat")  # crude keyword recall
OUTPUTS = ("harvest_uW", "demand_uW", "resonance_Hz", "stress_MPa", "open_V", "load_match_0to1", "source_impedance_kohm")
TEXT = dict(
    laws=["resonance_Hz = 120*h^1.5/sqrt(m) (h=thickness_mult, m=tip_mass_g); harvest peaks when resonance equals source_Hz (Q about 25)",
          "harvest grows with background_g^2 and with m; optimal load_kohm is about 40/h",
          "stress grows with bump_g, m and resonant gain, and falls as 1/h^2"],
    counter=["In this world the beam laws differ from textbooks: resonance_Hz = 37.9*sqrt(m)/h^1.5 (h=thickness_mult, m=tip_mass_g); harvest peaks when resonance equals source_Hz (Q about 25)",
             "harvest grows with background_g^2 and with 10/m (it FALLS as tip mass rises); optimal load_kohm is about 40*h",
             "stress grows with bump_g, resonant gain and 10*h^2/m"],
    modules=dict(W="passive wake-up trigger: event-driven acquisition replaces polling (no poll energy); fires when 0.8 V per g of bump_envelope exceeds wake_thr_V",
                 S="voltage-triggered shunt across the piezo: above shunt_thr_V it clamps beam motion; if background open voltage exceeds the threshold it also wastes 80% of harvest",
                 U="cold-start charge pump: rectifier only needs 0.5 V; extraction efficiency 70% instead of 85%",
                 M="5 mJ thin-film backup cell available from power-up"),
    constraints=dict(energy="harvest >= total demand (idle + sensor load + modules + polling + reports)", cold_start="storage reaches start_V within ready_s from net harvest",
                     burst="storage energy between start_V and 1.8 V (+ backup cell) covers one report", capture="every bump captured: poll_ms+60 <= bump_ms, or the wake trigger fires",
                     start="rectifier open voltage >= start_V+0.4 (0.5 V with charge pump)", stress="beam stress <= stress_limit_MPa", area="board area <= area_limit_mm2",
                     displacement="beam tip displacement <= 2 mm", false_wake="wake trigger must not fire on background (threshold >= 2.4 V per g of background)",
                     aging="harvest keeps a 15% derating margin over demand"),
    env=["source_Hz", "background_g", "bump_g", "bump_envelope_g", "bump_ms", "report_uJ", "report_period_s", "ready_s", "base_idle_uW", "sensor_load_uW", "poll_uJ"],
    limits=["stress_limit_MPa", "area_limit_mm2", "base_area_mm2", "storage_area_mm2_per_uF"])
ABSTRACT = dict(
    laws=["y3 = 120*x1^1.5/sqrt(x2); y1 peaks when y3 equals e1 (Q about 25)", "y1 grows with e2^2 and with x2; best x3 is about 40/x1",
          "y4 grows with e3, x2 and resonant gain, and falls as 1/x1^2"],
    modules=dict(W="removes the x6-dependent periodic cost; c4 then needs 0.8*e4 to exceed x7", S="above x8 (event-scaled y5) it clamps y4; if y5 exceeds x8 it cuts y1 by 80%",
                 U="c5 then needs y5 >= 0.5 instead of x5+0.4; y1 efficiency 70% instead of 85%", M="adds 5000 to the c3 store"),
    constraints=dict(energy="y1 >= y2", cold_start="x4 charges to x5 within e8 from net y1", burst="x4 energy between x5 and 1.8 (+ M4) covers e6",
                     capture="x6+60 <= e5, or M1 fires", start="y5 >= x5+0.4 (0.5 with M3)", stress="y4 <= l1", area="10 + 0.02*x4 + blocks <= l2"))


def names(t):
    """internal key -> name shown to the agent."""
    if t["skin"] == "abstract": return {k: f"x{i+1}" for i, k in enumerate(VARS)} | {k: f"M{i+1}" for i, k in enumerate(MODS)}
    return NAMES | {k: k for k in MODS} | (dict(th="thr1_V", Vs="thr2_V") if t["menu"] == "prims" else dict(Vs="S_setting_V") if t.get("opaque") else {})


def view0(t):
    n = names(t); x = inner(X0 | t.get("x0", {}), t["skin"])  # reflection is an involution: the view of X0 is inner(X0)
    flags = dict.fromkeys(PRIMS, False) if t["menu"] == "prims" else {n[k]: False for k in MODS}
    return {n[k]: x[k] for k in VARS} | flags | {LURES[i % 8]+(f"_{i//8}" if i >= 8 else ""): .5 for i in range(t["distract"])}


def domain(t):
    n = {v: k for k, v in names(t).items()}
    return {k: dict(type="boolean") if type(v) is bool else dict(type="number", minimum=VARS[n[k]][0], maximum=VARS[n[k]][1]) if k in n else dict(type="number", minimum=0, maximum=1)
            for k, v in view0(t).items()}


def to_internal(v, t):
    inv = {b: a for a, b in names(t).items()}
    return internal({inv.get(k, k): val for k, val in v.items()}, t)


def shown(t):
    """Constraints the spec lists; with hidden checks (family E) the rest appear in feedback only when violated."""
    return set() if t["spec"] == "E2" else {k for k in TEXT["constraints"] if k not in HIDDEN or t["hidden"] and t["spec"] == "E0"}


def feedback(v, t, best_margin=None, rng=None, screen=False):
    s, o = physics(to_internal(v, t), t["env"], t["low"] if screen else 0.)
    s = {k: float(val) for k, val in s.items() if t["hidden"] or k not in HIDDEN}
    m = min(s.values())
    if t["feedback"] == "bin": return dict(pass_=m >= 0, worst_constraint=min(s, key=s.get))
    if t["feedback"] == "rank": return dict(pass_=m >= 0, improved_on_best_so_far=best_margin is None or m > best_margin)
    ab = t["skin"] == "abstract"
    sl = {(f"c{list(s).index(k)+1}" if ab else k): val for k, val in s.items() if not t["hidden"] or k in shown(t) or val < 0}
    out = {(f"y{i+1}" if ab else k): float(o[k]) for i, k in enumerate(OUTPUTS[:7 if t["skin"].endswith("obs") else 5])}
    if t["feedback"] == "noisy": sl, out = ({k: val+rng.normal(0, .05) for k, val in sl.items()}, {k: val*(1+rng.normal(0, .05)) for k, val in out.items()})
    return dict(pass_=m >= 0, slack=sl, outputs=out)


def certificate(t):
    e = t["env"]; base = 2+e["load"]+e["E_pk"]/e["period"]
    return dict(scope="Necessary energy bounds over the whole declared domain from a private global optimizer (numeric, not analytic); other constraints ignored.",
                harvest_upper_uW=round(best(t, set(), lambda x: physics(x, e)[1]["harvest_uW"])[0], 3),
                demand_lower_uW_without_wake=round(base+18000/(e["E_ms"]-60), 3), demand_lower_uW_with_wake=round(base+MODS["W"][0], 3))


def brief(t):
    e = t["env"]; n = names(t); ab = t["skin"] == "abstract"; d = ABSTRACT if ab else TEXT
    env = [e["f"], e["a_bg"], e["a_ev"], e["a_wk"], e["E_ms"], e["E_pk"], e["period"], e["ready"], 2, round(e["load"], 4), 18]
    mean = MEANING | (dict(th="comparator threshold on the aux path, V", Vs="comparator threshold on the piezo path, V") if t["menu"] == "prims" else dict(Vs="setting of module S, V") if t.get("opaque") else {})
    s = dict(variables={n[k]: "parameter" if ab else mean[k] for k in VARS} | {k: "no documented effect" for k in view0(t) if k.startswith(tuple(LURES))},
             environment=dict(zip([f"e{i+1}" for i in range(11)] if ab else TEXT["env"], env)))
    if t["spec"] != "E2": s["limits"] = dict(zip(["l1", "l2"] if ab else TEXT["limits"], [e["sigma"], e["area"], 10, .02]))
    if t["hidden"]: s["purpose"] = PURPOSE
    s["constraints"] = {(f"c{list(TEXT['constraints']).index(k)+1}" if ab else k): d["constraints"][k] for k in d["constraints"] if k in shown(t)}
    if "hidden" not in t["skin"]: s["laws"] = list(TEXT["counter"] if t["skin"] == "counter" else d["laws"])
    if t["told"] and e["couple"]: s["laws"].append(f"Electrical load also shifts resonance: resonance *= 1 + {e['couple']}*(lm - 0.5), lm = 2r/(1+r^2), r = load_kohm*h/40.")
    if t["menu"] == "prims": s["primitives"] = {p: f"{desc} (idle {i} uW, {a} mm2)" for p, (i, a, desc) in PRIMS.items()}
    else: s["modules"] = {n[k]: f"{'piezo protection circuit with one setting, S_setting_V' if k == 'S' and t.get('opaque') else d['modules'][k]} (idle {MODS[k][0]} uW, {MODS[k][1]} mm2)" for k in MODS}
    return s


def tools(t):
    fn = lambda name, desc, props: dict(type="function", function=dict(name=name, description=desc, parameters=dict(type="object", properties=props, required=list(props))))
    tl = [fn("evaluate", "Apply a patch to the CURRENT design and run the official evaluation (uses one evaluation).",
             dict(changes=dict(type="object", properties=domain(t), additionalProperties=False), reason=dict(type="string"))),
          fn("finish", "Stop. Verdict on whether a passing design exists, confidence 0-1, and why.",
             dict(verdict=dict(type="string", enum=["FEASIBLE", "INFEASIBLE", "UNSURE"]), confidence=dict(type="number"), reason=dict(type="string")))]
    if t["python"]: tl.append(fn("python", f"Run Python 3 with numpy as np and probe(changes) -> feedback for CURRENT design + changes (not submitted). At most {PROBES} probes per task, {PY_CALLS} calls, 30 s each; print what you need.", dict(code=dict(type="string"))))
    if t.get("arm") == "branch": tl.append(fn("optimize_branch", f"Locally optimize one module's own parameter (W: wake_thr_V, S: {names(t)['Vs']}, U: start_V, M: storage_uF) with that module ON and everything else at the CURRENT design; returns the best margin reachable and the value (no evaluation used, design unchanged).", dict(module=dict(type="string", enum=list(MODS)))))
    if t.get("arm") == "anon": tl.append(fn("global_bound", "Sound analytic upper bound, over the whole declared domain (every hardware choice and parameter), on the best min(energy, stress) slack among designs that meet the capture requirement; a negative bound refutes global feasibility (no evaluation used).", {}))
    if t.get("arm") == "bound": tl.append(fn("global_bound", "Sound analytic upper bound, per module combination over the whole declared domain, on the best min(energy, stress) slack among designs that meet the capture requirement; a negative bound refutes that combination (no evaluation used).", {}))
    if t["hidden"]: tl.append(fn("requirements", "Before the first evaluate, list every requirement / failure mode the design must satisfy.", dict(items=dict(type="array", items=dict(type="string")))))
    return tl


def intro(t):
    s = f"Design a vibration-powered monitoring node. evaluate(changes, reason) patches the CURRENT design; you have {t['budget']} evaluations. Install only hardware you need. Call finish when you stop."
    if t["family"] == "G" or t["target"] < 0: s += " The task may or may not be feasible; finish with a verdict and calibrated confidence (a passing evaluation counts as FEASIBLE)."
    if t["family"] == "F" or t["low"]: s += " probe() inside python runs a fast screening model; evaluate runs the official full model."
    if t["told"] and (t["family"] == "F" or t["low"]): s += " The screening model may be systematically biased relative to the official model."
    if t.get("arm") == "branch": s += " Branch gate: after you enable a module you may not switch it off again or declare INFEASIBLE until you have called optimize_branch for it."
    if t.get("arm") == "bound": s += " INFEASIBLE is accepted only if global_bound refutes every module combination (all bounds < 0); otherwise answer UNSURE when you cannot find a passing design."
    if t.get("arm") == "anon": s += " INFEASIBLE is accepted only if global_bound is negative; otherwise answer UNSURE when you cannot find a passing design."
    if t["hidden"]: s += " Call requirements(items) before your first evaluate."
    return s


CHILD = """import json, sys; sys.path.insert(0, %r); import numpy as np, pilots
a = json.load(sys.stdin); t = pilots.TASKS[a["task"]]; n = [0]
def probe(changes):
    if n[0] >= a["left"]: raise RuntimeError("probe budget used")
    n[0] += 1; return pilots.feedback(a["x"] | changes, t, rng=np.random.default_rng(n[0]), screen=True)
try: exec(a["code"], dict(np=np, probe=probe))
finally: print("#probes", n[0])
""" % str(OUT.parent)


def python(code, v, t, left):
    """Model code runs in a child process without the API key in its environment."""
    try:
        r = subprocess.run([sys.executable, "-c", CHILD], input=json.dumps(dict(code=code, x=v, task=t["id"], left=left)), capture_output=True, text=True, timeout=30, env=dict(PATH=os.environ["PATH"]))
        out = r.stdout+r.stderr[-1500:]
    except subprocess.TimeoutExpired as e: out = (e.stdout or b"").decode()[-3000:]+"\nTIMEOUT"
    head, _, tail = out.rpartition("#probes")
    return (head or out)[-4000:], int(tail.split()[0]) if head else 0


def branch(module, v, t):
    k = names(t)[OWN[module]]; a, b, lg = VARS[OWN[module]]; g = np.geomspace(a, b, 400) if lg else np.linspace(a, b, 400)
    mm = margin(to_internal({q: np.full(400, val) for q, val in v.items()} | {names(t)[module]: np.full(400, True), k: g}, t), t); i = int(np.argmax(mm))
    return dict(module=module, parameter=k, best_value=float(g[i]), best_margin=float(mm[i]), margin_now_with_module_on=float(margin(to_internal(v | {names(t)[module]: True}, t), t)))


def run(jobs):
    path = RUNS; prev = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    done = {r["job"] for r in prev if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}
    lock = threading.Lock(); halt = threading.Event(); key = os.environ["DEEPSEEK_API_KEY"]
    tally = dict(spent=sum(r["usd"] for r in prev if r["kind"] == "response")+UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in prev), reserved=0.)
    def emit(row):
        with lock, path.open("a") as f: f.write(json.dumps(row, ensure_ascii=False, default=float)+"\n")
    def one(job):
        t, seed = job; jid = f"{t['id']}/s{seed}"
        if jid in done or halt.is_set(): return
        model, think = t["model"]; rates = PRICE[model]; rng = np.random.default_rng(seed)
        v = view0(t); best_m = finish = reqs = error = first = None; evals = probes = pycalls = 0; pending, hinted, tried, extra = set(), set(), defaultdict(set), defaultdict(int)
        used = dict(prompt=0, completion=0, reasoning=0, cache_hit=0, usd=0., requests=0, max_completion=0)
        user = dict(design=v, feedback=feedback(v, t, rng=rng)) | (dict(certificate=certificate(t)) if t["cert"] else {})
        msgs = [dict(role="system", content=intro(t)+"\n"+json.dumps(brief(t))), dict(role="user", content=json.dumps(user, default=float))]
        for _ in range(t["budget"]+PY_CALLS+6):
            body = dict(model=model, messages=msgs, tools=tools(t), tool_choice="auto", max_tokens=MAX_OUT, stream=True, stream_options=dict(include_usage=True),
                        thinking=dict(type="disabled" if think == "off" else "enabled")) | ({} if think == "off" else dict(reasoning_effort=think))
            raw = json.dumps(body).encode(); reserve = (len(raw)*rates["input"]+MAX_OUT*rates["output"])/1e6
            with lock:
                if tally["spent"]+tally["reserved"]+reserve > CAP: halt.set(); error = "BUDGET_STOP"; break
                tally["reserved"] += reserve
            try: answer, cost = ask(raw, key, rates, timeout=300)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"[:300]; emit(dict(kind="UNKNOWN", job=jid, error=error))
                with lock: tally["spent"] += UNKNOWN_USD  # charge the cap live, not only on reload
                break
            finally:
                with lock: tally["reserved"] -= reserve
            u = answer["usage"]; ch = answer["choices"][0]; m = ch["message"]
            with lock: tally["spent"] += cost
            used = used | dict(prompt=used["prompt"]+u["prompt_tokens"], completion=used["completion"]+u["completion_tokens"], cache_hit=used["cache_hit"]+u.get("prompt_cache_hit_tokens", 0),
                               reasoning=used["reasoning"]+u.get("completion_tokens_details", {}).get("reasoning_tokens", 0), usd=used["usd"]+cost, requests=used["requests"]+1,
                               max_completion=max(used["max_completion"], u["completion_tokens"]))
            emit(dict(kind="response", job=jid, usd=cost, finish_reason=ch["finish_reason"], usage=u, text=(m.get("content") or "")[:1500]))
            msgs.append(m)
            if not m.get("tool_calls"): error = "OUTPUT_LENGTH" if ch["finish_reason"] == "length" else "TEXT_WITHOUT_ACTION"; break
            for c in m["tool_calls"]:
                name = c["function"]["name"]
                try:
                    a = json.loads(c["function"]["arguments"])
                    miss = [k for k in MODS if len(tried[k]) < 2 and k not in hinted] if t.get("arm") == "hint" else []  # closure A: untested-branch prompt, once per module
                    if name == "finish" and a["verdict"] == "INFEASIBLE" and (t.get("arm") == "branch" and pending or t.get("arm") in ("bound", "anon") and max(t["bounds"].values()) >= 0 or miss):
                        extra["finish_rejected"] += 1; hinted |= set(miss); extra.setdefault("hint_at_eval", evals) if miss else None
                        reply = dict(error=f"INFEASIBLE not accepted: call optimize_branch for {sorted(pending)} first" if t.get("arm") == "branch" else "INFEASIBLE not accepted yet: you have not yet tested "+"; ".join(f"module {k} enabled while varying {names(t)[OWN[k]]}" for k in miss)+"." if miss
                                     else "INFEASIBLE not accepted: the global bound does not refute global feasibility; continue or answer UNSURE" if t.get("arm") == "anon" else "INFEASIBLE not accepted: the global bound does not refute every module combination; continue or answer UNSURE")
                    elif name == "finish": finish = a; reply = dict(stopped=True)
                    elif name == "optimize_branch" and t.get("arm") == "branch" and a["module"] in MODS: reply = branch(a["module"], v, t); pending.discard(a["module"]); extra["branch_calls"] += 1
                    elif name == "global_bound" and t.get("arm") == "bound": reply = dict(upper_bound_min_energy_stress_slack=t["bounds"]); extra["bound_calls"] += 1
                    elif name == "global_bound" and t.get("arm") == "anon": reply = dict(global_upper_bound_min_energy_stress_slack=max(t["bounds"].values()), requirement=0.); extra["bound_calls"] += 1
                    elif name == "requirements" and t["hidden"]: reqs = a["items"]; reply = dict(recorded=len(reqs))
                    elif name == "python" and t["python"] and pycalls < PY_CALLS:
                        out, n = python(a["code"], v, t, PROBES-probes); probes += n; pycalls += 1; reply = dict(output=out)
                    elif name == "evaluate" and t["hidden"] and reqs is None: reply = dict(error="call requirements first")
                    elif name == "evaluate" and evals < t["budget"] and first is None:
                        if set(a["changes"])-set(v): raise ValueError("unknown variable")
                        off = {k for k in pending if a["changes"].get(names(t)[k]) is False}
                        if t.get("arm") == "branch" and off: extra["discard_rejected"] += 1; raise ValueError(f"branch gate: call optimize_branch for {sorted(off)} before switching it off")
                        pending |= {k for k in MODS if a["changes"].get(names(t)[k]) is True and not v.get(names(t)[k])}
                        v = v | a["changes"]; evals += 1; mm = float(margin(to_internal(v, t), t)); reply = feedback(v, t, best_m, rng)
                        emit(dict(kind="evaluation", job=jid, step=evals, design=v, margin=mm, reason=a.get("reason", "")[:300]))
                        for k in (k for k in MODS if v.get(names(t)[k])): tried[k].add(v[names(t)[OWN[k]]])
                        best_m = mm if best_m is None else max(best_m, mm); first = evals if mm >= 0 else None
                    else: reply = dict(error="not available (budget used, already passed, or tool not offered)")
                    if name != "evaluate": emit(dict(kind="tool", job=jid, tool=name, args=a, reply=json.dumps(reply, default=float)[:600]))
                except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
                    emit(dict(kind="invalid", job=jid, tool=name, error=str(e)[:200])); reply = dict(error=str(e)[:300])
                msgs.append(dict(role="tool", tool_call_id=c["id"], content=json.dumps(reply | dict(evaluations_left=t["budget"]-evals), default=float)))
            if finish or first or evals >= t["budget"]: break
        mm = float(margin(to_internal(v, t), t))
        emit(dict(kind="terminal", job=jid, cell=t["id"], family=t["family"], seed=seed, pass_=mm >= 0, first_pass=first, evaluations=evals, final_margin=mm,
                  verdict=(finish or {}).get("verdict", "FEASIBLE" if first else None), confidence=(finish or {}).get("confidence"),
                  finish_reason=(finish or {}).get("reason", "")[:1500], requirements=reqs, python_calls=pycalls, probes=probes,
                  modules=[k for k in MODS if to_internal(v, t)[k]], error=error, usage=used, arm=t.get("arm"), **extra))
        print(jid, "PASS" if mm >= 0 else error or "FAIL", evals, flush=True)
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool: list(pool.map(one, jobs))
    print(json.dumps(tally))


def infra(r):
    """API timeouts / HTTP errors are infrastructure failures, never scientific ones; such jobs are rerun."""
    return str(r.get("error")).startswith(("RuntimeError: USAGE_UNKNOWN", "TimeoutError", "HTTPError", "URLError", "RemoteDisconnected", "ConnectionResetError"))


def wilson(k, n, z=1.96):
    if not n: return None
    c, h = (k+z*z/2)/(n+z*z), z*np.sqrt(k*(n-k)/n+z*z/4)/(n+z*z)
    return [round(float(c-h), 3), round(float(c+h), 3)]


def report():
    rows = [json.loads(s) for s in (OUT/"runs.jsonl").read_text().splitlines()]
    allterm = [r for r in rows if r["kind"] == "terminal"]; term = list({r["job"]: r for r in allterm}.values()); resp = [r for r in rows if r["kind"] == "response"]
    evs = defaultdict(list)
    for r in rows:
        if r["kind"] == "evaluation": evs[r["job"]].append(r)
    def dup(job):  # repeated or regressing evaluations
        e = evs[job]; pts = [np.array([np.log(float(x)) if VARS.get(k, (0, 0, 0))[2] and type(x) is not bool else float(x) for k, x in sorted(r["design"].items())]) for r in e]
        rep = sum(any(np.max(np.abs(p-q)) < 1e-3 for q in pts[:i]) for i, p in enumerate(pts))
        reg = sum(r["margin"] < max(q["margin"] for q in e[:i]) for i, r in enumerate(e) if i)
        return rep, reg
    cells = defaultdict(list)
    group = lambda r: r["cell"].split("#")[0]+(" [confirm]" if "#" in r["cell"] else "")
    for r in term: cells[group(r)].append(r)
    table = {c: dict(n=len(rs), infra_failed_attempts=sum(infra(r) for r in allterm if group(r) == c), infra_unresolved=sum(map(infra, rs)), passed=sum(r["pass_"] for r in rs), runs=[("P%d" % r["first_pass"]) if r["pass_"] else (r["error"] or "N%d" % r["evaluations"]) for r in rs],
                     verdicts=[r["verdict"] for r in rs], confidence=[r["confidence"] for r in rs], margins=[round(r["final_margin"], 5) for r in rs],
                     modules=[r["modules"] for r in rs], repeats_regressions=[dup(r["job"]) for r in rs], probes=[r["probes"] for r in rs],
                     recall=[round(np.mean([bool(re.search(h, " ".join(r["requirements"]), re.I)) for h in HINTS.values()]), 2) if r["requirements"] else None for r in rs],
                     brier=[round((({"FEASIBLE": r["confidence"] or 1, "INFEASIBLE": 1-(r["confidence"] or 1)}.get(r["verdict"], .5))-(TASKS[r["cell"]]["target"] > 0))**2, 3) for r in rs],
                     first_move_mass_up=[(lambda e, k: e[0]["design"][k] > view0(TASKS[r["cell"]])[k] if e and k in e[0]["design"] else None)(evs[r["job"]], names(TASKS[r["cell"]])["m"]) for r in rs],
                     usd=round(sum(r["usage"]["usd"] for r in rs), 4), wilson95=wilson(sum(r["pass_"] for r in rs if not infra(r)), sum(not infra(r) for r in rs)))
             for c, rs in sorted((c, sorted(rs, key=lambda r: (r["cell"], r["seed"]))) for c, rs in cells.items())}
    usage = dict(requests=len(resp), prompt=sum(r["usage"]["prompt_tokens"] for r in resp), completion=sum(r["usage"]["completion_tokens"] for r in resp),
                 reasoning=sum(r["usage"].get("completion_tokens_details", {}).get("reasoning_tokens", 0) for r in resp),
                 cache_hit=sum(r["usage"].get("prompt_cache_hit_tokens", 0) for r in resp), max_completion=max(r["usage"]["completion_tokens"] for r in resp),
                 truncated=sum(r["finish_reason"] == "length" for r in resp), unknown=sum(r["kind"] == "UNKNOWN" for r in rows),
                 invalid=sum(r["kind"] == "invalid" for r in rows), usd_uncached=sum(r["usd"] for r in resp), unknown_reserved_usd=UNKNOWN_USD*sum(r["kind"] == "UNKNOWN" for r in rows),
                 usd_cache_aware=sum(r["usd"]-r["usage"].get("prompt_cache_hit_tokens", 0)*CACHE_SAVING[TASKS[r["job"].rsplit("/s", 1)[0]]["model"][0]]/1e6 for r in resp))
    (OUT/"summary.json").write_text(json.dumps(dict(usage=usage, terminals=len(term), cells=table), indent=1, ensure_ascii=False))
    for c, r in table.items(): print(c, f"{r['passed']}/{r['n']-r['infra_unresolved']}", r["wilson95"], "infra", r["infra_failed_attempts"], r["runs"], r["verdicts"], r["modules"], r["repeats_regressions"], r["usd"])
    print(json.dumps(usage))


def decisive():
    """Decisive-experiment tables: settled runs.jsonl + decisive.jsonl, last non-infra attempt per job."""
    from scipy.stats import fisher_exact
    term, evs = {}, defaultdict(list)
    for r in (json.loads(s) for f in ["runs.jsonl"]+sorted(p.name for p in OUT.glob("decisive*.jsonl")) for s in (OUT/f).read_text().splitlines()):
        if r["kind"] == "terminal" and (not infra(r) or r["job"] not in term): term[r["job"]] = r
        if r["kind"] == "evaluation": evs[r["job"]] = (evs[r["job"]] if r["step"] > 1 else [])+[r]
    def grp(c):
        base = c.split("#")[0]; arm = TASKS[c].get("arm")
        if arm: return f"{c[:2]}/{arm}/{c.rsplit('/', 1)[1]}"+(" [fresh]" if int(c.split("/p")[1].split("/")[0]) >= 8 else "")
        if base.startswith("A/"): return base.rsplit("/", 1)[0]+(" [fresh]" if "#" in c else " [phase1]")
        return base+(" [fresh]" if "#" in c else " [phase1]")
    def one(r):
        t = TASKS[r["cell"]]; n = names(t); ds = [view0(t)]+[e["design"] for e in evs[r["job"]]]; x = to_internal(ds[-1], t)
        on = [d.get(n["S"]) for d in ds]; vs = [d.get(n["Vs"]) for d in ds]
        flips = [i for i in range(1, len(ds)-1) if on[i] and not on[i-1] and not on[i+1]]
        son = [i for i in range(1, len(ds)) if on[i]]; ocv = [vs[i]/float(physics(to_internal(ds[i], t), t["env"])[1]["open_V"]) for i in son]; h = r.get("hint_at_eval")
        mech = dict(S_ever=bool(son), S_values=len({vs[i] for i in son}), S_over_ocv=round(max(ocv, default=0), 3), S_crossed=any(q > 1 for q in ocv), hint_at_eval=h,
                    S_crossed_after_hint=None if h is None else any(q > 1 for i, q in zip(son, ocv) if i > h), cites_uW=bool(re.search(r"\d\s*(uW|μW|µW)", r["finish_reason"] or "")))
        p = {"FEASIBLE": r["confidence"] or 1., "INFEASIBLE": 1-(r["confidence"] or 1.)}.get(r["verdict"], .5) if not r["pass_"] else 1.
        return dict(job=r["job"], pass_=r["pass_"], run=("P%d" % r["first_pass"]) if r["pass_"] else (r["error"] or "N%d" % r["evaluations"]), verdict=r["verdict"], conf=r["confidence"], p_feasible=p,
                    feasible=t["target"] > 0, modules="".join(r["modules"]), mass_up=ds[1][n["m"]] > ds[0][n["m"]] if len(ds) > 1 else None,
                    load_ratio=round(float(x["R"]*x["h"]/40), 3), abandon_default=any(vs[i] == vs[0] for i in flips), abandon_any=bool(flips),
                    usd=r["usage"]["usd"], **mech, **{k: r.get(k, 0) for k in ("branch_calls", "bound_calls", "finish_rejected", "discard_rejected")})
    cells = defaultdict(list)
    for r in term.values():
        if r["cell"] in TASKS and r["cell"].startswith(("A/", "B/0.0001", "H/prims", "G2/", "G3/")) and not infra(r) and r["error"] != "BUDGET_STOP": cells[grp(r["cell"])].append(one(r))
    out = {}
    for c, rs in sorted(cells.items()):
        k = sum(r["pass_"] for r in rs); out[c] = dict(passed=k, n=len(rs), wilson95=wilson(k, len(rs)), runs=rs)
        print(c, f"{k}/{len(rs)}", wilson(k, len(rs)), [r["run"] for r in rs], [r["verdict"] for r in rs][:16], round(sum(r["usd"] for r in rs), 3))
    def fisher(a, b):
        if a in out and b in out: x, y = out[a], out[b]; return [a, b, round(float(fisher_exact([[x["passed"], x["n"]-x["passed"]], [y["passed"], y["n"]-y["passed"]]])[1]), 5)]
    tests = [fisher(*p) for p in (("A/text_hidden [fresh]", "A/counter_hidden [fresh]"), ("A/text [fresh]", "A/text_hidden [fresh]"), ("A/counter_hidden_obs [fresh]", "A/counter_hidden [fresh]"),
             ("A/counter [fresh]", "A/counter_hidden [fresh]"), ("G2/branch/feasible", "G2/base/feasible"), ("G2/bound/feasible", "G2/base/feasible"), ("G3/branch/feasible", "G3/base/feasible"), ("G3/bound/feasible", "G3/base/feasible"), ("G3/base/feasible", "G2/base/feasible"),
             ("H/prims/stress [fresh]", "H/prims/wake [fresh]"), ("B/0.0001/py [fresh]", "B/0.0001/nopy [fresh]"))]
    tests += [fisher(f"G3/{a}/feasible [fresh]", f"G3/{b}/feasible [fresh]") for a, b in (("hint", "base"), ("anon", "base"), ("bound", "base"), ("hint", "bound"), ("anon", "bound"))]
    for a in (f"{g}/{a}{f}" for g in ("G2", "G3") for a in ARMS for f in ("", " [fresh]")):  # calibration on matched pairs
        a, f = a.split(" [")[0], " ["+a.split(" [")[1] if " [" in a else ""
        rs = out.get(f"{a}/feasible{f}", dict(runs=[]))["runs"]+out.get(f"{a}/infeasible{f}", dict(runs=[]))["runs"]
        pos, neg = [r["p_feasible"] for r in rs if r["feasible"]], [r["p_feasible"] for r in rs if not r["feasible"]]
        inf = [r for r in rs if r["verdict"] == "INFEASIBLE"]; tp = sum(not r["feasible"] for r in inf)
        if not rs: continue
        out[f"calibration/{a}{f}"] = dict(n=len(rs), AUC=round(float(np.mean([(p > q)+.5*(p == q) for p in pos for q in neg])), 3) if pos and neg else None,
            infeasible_precision=[tp, len(inf)], infeasible_recall=[tp, len(neg)], false_infeasible=len(inf)-tp, unsure=sum(r["verdict"] == "UNSURE" for r in rs),
            S_retained_feasible=[sum("S" in r["modules"] for r in rs if r["feasible"]), len(pos)], abandon_default=sum(r["abandon_default"] for r in rs), abandon_any=sum(r["abandon_any"] for r in rs))
        print(a+f, out[f"calibration/{a}{f}"])
    print(tests); (OUT/"decisive_summary.json").write_text(json.dumps(dict(cells=out, fisher=tests), indent=1, default=float))


if __name__ == "__main__":
    ok = [t for t in TASKS.values() if t["audit"]["witness_ok"] and t["audit"]["shortcut_closed"]]
    if "--confirm" in sys.argv: run(sorted([(t, 0) for t in ok if "#" in t["id"]], key=lambda j: (ORDER.index(j[0]["family"]), j[0]["id"].split("#")[1], j[0]["id"])))
    fams = sys.argv[-1] if sys.argv[-1].isupper() else ORDER  # e.g. `--run EGHFAXDLBCKI` to skip J
    if "--run" in sys.argv: run(sorted([(t, s) for t in ok if t["family"] in fams and "#" not in t["id"] for s in range(SEEDS)], key=lambda j: (ORDER.index(j[0]["family"]), j[1], j[0]["id"])))
    if "--decisive" in sys.argv:  # RUNS=decisive.jsonl CAP=6; jobs already settled in runs.jsonl are skipped
        old = {r["job"] for f in ("runs.jsonl", "decisive.jsonl") for r in map(json.loads, (OUT/f).read_text().splitlines()) if r["kind"] == "terminal" and not infra(r) and r["error"] != "BUDGET_STOP"}
        pick = [t for k, t in TASKS.items() if ("arm" in t or "#" in k and k.startswith(("A/text_hidden", "A/counter_hidden_obs", "A/counter/", "B/", "H/prims/stress")) and t in ok) and k.startswith(tuple(os.environ.get("ONLY", "").split()))]
        rank = lambda t: 3.5 if "arm" not in t else 1+ARMS.index(t["arm"])+2*(t["arm"] == "bound" and int(t["id"].split("/p")[1][0]) >= 4)
        pi = lambda t: int(t["id"].split("/p")[1].split("/")[0]) if "arm" in t else 0  # closure A pairs p8..p15: seed-major, pair-major, arms interleaved
        run(sorted([(t, s) for t in pick for s in range(int(os.environ.get("NSEED", 1))) if f"{t['id']}/s{s}" not in old], key=lambda j: (0 if j[0]["family"] == "A" else rank(j[0]) if pi(j[0]) < 8 else 9, j[1], pi(j[0]), j[0]["id"])))
    if "--report" in sys.argv: report()
    if "--decisive-report" in sys.argv: decisive()
