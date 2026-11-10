"""Boundary pilot: --calibrate, --agents, optional --followup, --transient, --report.
Earlier pilot retained in limits/ and Git commit 5f06f8a. No old harness dependency.
"""
import argparse
import concurrent.futures
import copy
import inspect
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
from scipy.stats import qmc
from sim import G, TASK, beam, simulate

HERE = Path(__file__).resolve().parent
OUT = HERE / "boundary"
BASE = json.loads((HERE / "design.json").read_text())
SAMPLE_MS = 62.5  # Fixed 128 samples / 2048 Hz, not a universal classification theorem.
DOMAIN = dict(C_uF=(50, 1500, "log"), R_kohm=(2, 300, "log"), h=(.85, 1.15, "linear"),
              mass_g=(3.5, 5.8, "linear"), L2_mm=(15, 22, "linear"), m2_g=(.08, .28, "linear"),
              gate_V=(1.9, 3.2, "linear"), poll_ms=(15, 4000, "log"), shunt_kohm=(.5, 100, "log"),
              shield_V=(5, 50, "log"), trigger_V=(.2, 1.2, "linear"))
DEFAULT = dict(C_uF=75., R_kohm=45., h=1., mass_g=4.65, L2_mm=18., m2_g=.14,
               gate_V=2.9, poll_ms=100., shunt_kohm=3., shield_V=15., trigger_V=.55,
               A=False, B=False, C=False, D=False)
MODULES = dict(A=dict(description="passive tuned trigger beam + comparator", idle_uW=.5, area_mm2=15),
               B=dict(description="active filter wake-up, gain 2 V/g", idle_uW=180., area_mm2=18),
               C=dict(description="additional FRAM; +5 uJ per write", idle_uW=2., area_mm2=40),
               D=dict(description="voltage-triggered parallel resistive shunt", idle_uW=.5, area_mm2=12))
ARMS = ("Fixed-P0", "All-Open", "Cert-Guided")
N, SEED, USD_CAP = 10000, 20261110, 2.
RATES = dict(input=.30, output=1.20, cache=.006)  # Official peak USD / million tokens.
HELPER_LIMIT, EXPLORE_POINTS, D3_MAX_OUTPUT = 20, 11, 65536
# 65536 is the official thinking-mode default (4x the 16384 ceiling that exhausted all 7 prior truncations).
# Official model maximum is 384K; that reservation would be ~USD 0.47/request and can trip the USD 2 cap with 3 workers.


def sample(n, seed):
    u = qmc.LatinHypercube(len(DOMAIN), seed=seed).random(n)
    return {k: np.exp(np.log(a)+u[:, i]*np.log(b/a)) if scale == "log" else a+u[:, i]*(b-a)
            for i, (k, (a, b, scale)) in enumerate(DOMAIN.items())} | {k: np.zeros(n, bool) for k in MODULES}


def mechanics(x):
    return beam(dict(BASE["harvester"], substrate_mm=.15*x["h"], piezo_layer_mm=.12*x["h"], tip_mass_g=x["mass_g"]))


def response(b, hz, amplitude_g, resistance):
    w = 2*np.pi*hz
    z = b["k"]-b["m"]*w*w+1j*w*b["c"]+b["theta"]**2*1j*w/(1/resistance+1j*w*b["cp"])
    q = b["forcing_mass"]*amplitude_g*G/np.abs(z)
    return q, b["theta"]*w*q/np.abs(1/resistance+1j*w*b["cp"])


def oracle(t, x):
    """Settled harmonic screen: D engages on open-switch peak voltage.
    Constant .65 extraction efficiency; no transient or waveform classification claim.
    """
    b, r = mechanics(x), x["R_kohm"]*1000
    def loaded(hz, amplitude):
        _, open_v = response(b, hz, amplitude, r)
        load = 1/(1/r+(np.asarray(x["D"]) & (open_v > x["shield_V"]))/ (x["shunt_kohm"]*1000))
        return response(b, hz, amplitude, load)
    qb, vb = loaded(t["background_Hz"], t["background_g"])
    qe, ve = loaded(t["event_Hz"], t["event_g"])
    power = .65*vb**2/(2*r)
    idle = (1.4+sum(np.asarray(x[k])*v["idle_uW"] for k, v in MODULES.items()))*1e-6
    packet = (.003*SAMPLE_MS/1000+68e-6+np.asarray(x["C"])*5e-6)/.85
    active = np.asarray(x["A"]) | np.asarray(x["B"])
    if t["case"] == "wake":
        w = beam(dict(BASE["trigger_beam"], length_mm=x["L2_mm"], tip_mass_g=x["m2_g"]))
        qt, vt = response(w, t["event_Hz"], t["event_g"], 1e8)
        env = np.maximum(vt*(1-np.exp(-.03*2*np.pi*t["event_Hz"]*t["event_ms"]/1000))-.2, 0)
        env = np.maximum(env*np.asarray(x["A"]), np.asarray(x["B"])*2*t["event_g"])
        capture = np.where(active, env/x["trigger_V"]-1, t["event_ms"]/(x["poll_ms"]+SAMPLE_MS)-1)
        demand = np.where(active, packet/t["event_period_s"], .003*np.minimum(1, SAMPLE_MS/x["poll_ms"]))
        stress = np.maximum((qb+qe)*b["stress_per_m"], np.asarray(x["A"])*qt*w["stress_per_m"])/1e6
    else:
        capture, demand = ve/(x["gate_V"]+.3)-1, packet/t["event_period_s"]
        stress = qe*b["stress_per_m"]/1e6
    net = power-idle
    slack = dict(energy=(net-demand)/1e-4,
                 cold_charge=2*net*t["ready_s"]/(x["C_uF"]*1e-6*x["gate_V"]**2)-1,
                 burst_energy=(.5*x["C_uF"]*1e-6*(x["gate_V"]**2-1.8**2)+net*(SAMPLE_MS+9.5)/1000)/packet-1,
                 capture=capture, stress=1-stress/t["stress_MPa"],
                 area=1-(20+.03*x["C_uF"]+sum(np.asarray(x[k])*v["area_mm2"] for k, v in MODULES.items()))/t["area_mm2"],
                 rectifier_voltage=vb/(x["gate_V"]+.3)-1,
                 acquisition_window=np.asarray(SAMPLE_MS*t["event_Hz"]/4000-1 if t["case"] == "wake" else 1.))
    return dict(slack=slack, harvested_uW=power*1e6, required_uW=(demand+idle)*1e6,
                background_voltage_V=vb, event_voltage_V=ve, stress_MPa=stress)


def passed(result):
    return np.logical_and.reduce(np.broadcast_arrays(*[np.asarray(v) >= 0 for v in result["slack"].values()]))


def scalar(x):
    if isinstance(x, dict): return {k: scalar(v) for k, v in x.items()}
    return x.item() if isinstance(x, (np.ndarray, np.generic)) else x


def local_keys(t):
    return ("C_uF", "poll_ms") if t["case"] == "wake" else ("C_uF", "R_kohm")


def bounds(t):
    """Necessary bounds over ALL allowed geometry/load, not a zero-sample claim.
    F^2/c increases with tip mass and decreases with h on the declared rectangle.
    With equal forcing frequencies and no D, q_event/q_bg = a_event/a_bg.
    """
    b = mechanics(dict(DEFAULT, h=.85, mass_g=5.8))
    upper = .65*(b["forcing_mass"]*t["background_g"]*G)**2/(8*b["c"])
    packet = (.003*SAMPLE_MS/1000+68e-6)/.85
    if t["case"] == "wake":
        poll_limit = t["event_ms"]-SAMPLE_MS
        poll_need = .003*min(1, SAMPLE_MS/max(poll_limit, 1e-9))+1.4e-6
        active_need = packet/t["event_period_s"]+1.9e-6
        b_need = packet/t["event_period_s"]+181.4e-6
        return dict(scope="Declared harmonic geometry/load rectangle; fixed acquisition; no transient theorem",
                    power_upper_uW=upper*1e6, no_wake_power_lower_uW=poll_need*1e6,
                    active_B_power_lower_uW=b_need*1e6, active_A_power_lower_uW=active_need*1e6,
                    excluded_without_any_wake=upper < poll_need, excluded_without_A=upper < min(poll_need, b_need),
                    all_architectures_excluded_by_energy=upper < active_need,
                    derivation="P_useful <= .65 F^2/(8 c); capture needs poll+62.5 <= event_ms")
    b = mechanics(dict(DEFAULT, h=1.15))
    stress_upper = .65*b["theta"]**2*(2*np.pi*t["background_Hz"])/(4*b["cp"])*(t["stress_MPa"]*1e6/b["stress_per_m"]*t["background_g"]/t["event_g"])**2
    need = packet/t["event_period_s"]+1.4e-6
    return dict(scope="Harmonic geometry/load rectangle, equal forcing frequencies, D absent",
                no_D_stress_limited_power_upper_uW=stress_upper*1e6, service_power_lower_uW=need*1e6,
                excluded_without_D=t["event_Hz"] == t["background_Hz"] and stress_upper < need,
                derivation="q_event/q_bg=a_event/a_bg; max_R R/(1+(w Cp R)^2)=1/(2 w Cp)")


def calibrate():
    started = time.perf_counter(); x = sample(N, SEED+301)
    settings = [("wake", "D1", .30, .5, 3000., 40.), ("wake", "D2", .16, .5, 150., 40.),
                ("wake", "D3", .095, .5, 150., 40.), ("impact", "D1", .20, 1.5, 500., 150.),
                ("impact", "D2", .12, 5., 500., 285.), ("impact", "D3", .12, 5., 500., 225.)]
    rows = []
    for kind, level, bg, event_g, event_ms, stress in settings:
        t = dict(id=kind+"-"+level, case=kind, difficulty=level, background_Hz=45., background_g=bg,
                 event_Hz=210. if kind == "wake" else 45., event_g=event_g, event_ms=event_ms,
                 event_period_s=6., ready_s=100., stress_MPa=stress, area_mm2=95.)
        rates, witnesses = {}, {}
        for label, mods in [("none", ()), ("A", ("A",)), ("B", ("B",)), ("D", ("D",)), ("all", tuple(MODULES))]:
            z = x | {k: np.full(N, k in mods) for k in MODULES}; ok = passed(oracle(t, z)); hits = np.flatnonzero(ok)
            rates[label] = dict(hits=len(hits), n=N, fraction=float(ok.mean()))
            if len(hits): witnesses[label] = {k: scalar(v[hits[0]]) for k, v in z.items()}
        local = {k: x[k] if k in local_keys(t) else np.full(N, v) for k, v in DEFAULT.items()}
        rates["P0"] = dict(hits=int(passed(oracle(t, local)).sum()), n=N)
        rows.append(dict(task=t, rates=rates, witnesses=witnesses, bounds=scalar(bounds(t)), initial=scalar(oracle(t, DEFAULT))))
    OUT.mkdir(exist_ok=True)
    result = dict(seed=SEED+301, coordinates=DOMAIN, fixed_acquisition_ms=SAMPLE_MS, default=DEFAULT,
                  modules=MODULES, workpoints=rows, runtime_s=time.perf_counter()-started,
                  policy="Mechanism-conditioned points; witnesses/labels/rates NEVER sent to learners. Zero hits is not proof. D3 is rare under this measure, not globally impossible.")
    (OUT/"calibration.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({r["task"]["id"]: dict(rates=r["rates"], bounds=r["bounds"]) for r in rows}, indent=2))


def public_spec():
    return dict(domain=DOMAIN, modules=MODULES, acquisition="Fixed 128 samples at 2048 Hz (62.5 ms); sample_ms is not an action.",
                classifier="Harmonic capture/window screen only; waveform classification checked separately.",
                parameters=dict(C_uF="storage capacitance", R_kohm="regulated rectifier equivalent input load",
                                h="multiplier of BOTH .15-mm steel and .12-mm PZT thickness of 30x10-mm beam",
                                mass_g="harvester tip mass", L2_mm="trigger beam length", m2_g="trigger beam mass",
                                gate_V="MCU start threshold; brownout=1.8 V", poll_ms="sampling interval if A and B off",
                                shunt_kohm="D parallel load above shield_V", shield_V="D voltage threshold", trigger_V="wake envelope threshold"),
                physics=["Beam resonance increases with thickness and decreases with mass/length; electrical load changes damping and stiffness.",
                         "Harvest depends on resonance, acceleration squared and load. Useful power cannot exceed mechanical input.",
                         "Larger storage helps bursts but slows charging and costs board area.",
                         "Without A/B, complete capture needs poll_ms+62.5 <= event_ms; polling consumes energy every interval.",
                         "A/B replace polling with triggered acquisition. All installed modules pay their stated costs.",
                         "D changes damping at high observed voltage, potentially sacrificing harvested power; no prescribed stress-reduction percentage.",
                         "PASS requires all energy, charging, burst, capture, acquisition, stress, area and rectifier constraints together."],
                base_beams={k: BASE[k] for k in ("harvester", "trigger_beam")},
                circuit_specs=dict(extraction_efficiency=.65, regulator_efficiency=.85, idle_uW=1.4,
                                   base_area_mm2=20., storage_area_mm2_per_uF=.03, digital_energy_uJ=255.5,
                                   brownout_V=1.8, bridge_pair_drop_V=.3),
                feedback_units="Slack >=0 satisfies a condition; energy scaled by 100 uW. I0/I1 include physical units.")


def feedback(result, visibility):
    s = result["slack"]; worst = min(s, key=lambda k: float(s[k]))
    return dict(pass_=bool(passed(result)), worst_constraint=worst) | (scalar(result) if visibility != "I2" else {})


def explore_sweep(t, base, allowed, vis, vary, low, high, n=None):
    """Local 1-2 variable sweep. Does not mutate the official design. Feedback matches the information tier."""
    if not isinstance(vary, list) or not 1 <= len(vary) <= 2: raise ValueError("vary must be 1 or 2 allowed names")
    if any(k not in allowed for k in vary): raise ValueError("explore variable outside allowed set")
    if not (isinstance(low, list) and isinstance(high, list) and len(low) == len(high) == len(vary)):
        raise ValueError("low and high must match vary")
    axes = []
    for i, k in enumerate(vary):
        if k in MODULES:
            lo, hi = bool(low[i]), bool(high[i])
            axes.append([(k, lo)] if lo == hi else [(k, False), (k, True)])
        else:
            lo, hi = float(low[i]), float(high[i])
            a, b, scale = DOMAIN[k]
            lo, hi = max(a, min(lo, hi)), min(b, max(lo, hi))
            if lo > hi: raise ValueError("empty explore interval")
            count = int(n or EXPLORE_POINTS) if len(vary) == 1 else min(int(n or 3), 3)
            count = max(2, min(count, EXPLORE_POINTS))
            vals = np.geomspace(lo, hi, count) if scale == "log" and lo > 0 else np.linspace(lo, hi, count)
            axes.append([(k, float(v)) for v in vals])
    combos = list(__import__("itertools").product(*axes))[:EXPLORE_POINTS]
    points = []
    for combo in combos:
        y = dict(base)
        for k, v in combo: y[k] = v
        points.append(dict(settings={k: v for k, v in combo}, public=feedback(oracle(t, y), vis)))
    return dict(n=len(points), official_design_unchanged=True, points=points)


def collect(stream):
    """Rebuild a non-stream answer from SSE chunks; the read timeout then bounds silence, not total generation time."""
    m, calls, fin, u = dict(role="assistant", content="", reasoning_content=""), {}, None, {}
    for line in stream:
        if not line.startswith(b"data: {"): continue
        d = json.loads(line[6:]); u = d.get("usage") or u
        for ch in d.get("choices", []):
            dl = ch["delta"]; fin = ch.get("finish_reason") or fin; m["content"] += dl.get("content") or ""; m["reasoning_content"] += dl.get("reasoning_content") or ""
            for tc in dl.get("tool_calls") or []:
                c = calls.setdefault(tc["index"], dict(id="", type="function", function=dict(name="", arguments="")))
                c["id"] += tc.get("id") or ""; c["function"]["name"] += tc["function"].get("name") or ""; c["function"]["arguments"] += tc["function"].get("arguments") or ""
    return dict(choices=[dict(finish_reason=fin, message=m | (dict(tool_calls=[calls[i] for i in sorted(calls)]) if calls else {}))], usage=u)


def ask(raw, key, rates=RATES, timeout=600):
    """One DeepSeek chat call; returns the answer and its uncached peak-rate USD estimate."""
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=raw, headers={"Authorization": "Bearer "+key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as stream: answer = collect(stream) if b'"stream": true' in raw else json.load(stream)
    u = answer.get("usage", {})
    if not all(type(u.get(k)) is int for k in ("prompt_tokens", "completion_tokens", "total_tokens")): raise RuntimeError("USAGE_UNKNOWN")
    return answer, (u["prompt_tokens"]*rates["input"]+u["completion_tokens"]*rates["output"])/1e6


def run_agents(jobs, *, out=None, calibration=None, max_output=16384):
    out = Path(out) if out else OUT
    out.mkdir(exist_ok=True)
    cal = Path(calibration) if calibration else out/"calibration.json"
    rows = {r["task"]["id"]: r for r in json.loads(cal.read_text())["workpoints"]}
    path = out/"agents.jsonl"; previous = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    requests = {r["id"] for r in previous if r["kind"] == "request"}; settled = {r["id"] for r in previous if r["kind"] == "response"}
    if requests-settled: raise SystemExit("Unsettled request: preserve UNKNOWN; no automatic retry.")
    terminals = {r["job"] for r in previous if r["kind"] == "terminal"}
    started = time.perf_counter(); lock = threading.Lock(); halt = threading.Event()
    tally = dict(spent=sum(r["estimated_usd"] for r in previous if r["kind"] == "response"), reserved=0., requests=len(requests))
    key = os.environ.get("DEEPSEEK_API_KEY") or (Path.home()/".local/share/bf-campaign-20261019-s0/workbench/secrets/deepseek.key").read_text().strip()
    source = "\n".join(inspect.getsource(f) for f in (beam, mechanics, response, oracle))
    inputs = dict(model="deepseek-flash", thinking="high", max_output=max_output, usd_cap=USD_CAP, max_requests=600,
                  wall_s=7200, simultaneous_requests=3, spec=public_spec(), source=source, rates=RATES,
                  visibility=dict(I0="source + specs + continuous feedback", I1="specs + continuous feedback", I2="specs + pass/fail/worst name"),
                  certificate_policy="All-Open and Cert-Guided have identical actions. Cert gets an additional analytic necessary bound: tests diagnostic information, not a pure strategy ablation.",
                  repeat_policy="54 first-replicate cells. At most two D2 case/visibility blocks with pass mismatch or >=2-step gap get two paired repeats; I1 then I2 then I0/case order, regardless of winner. If both fail I1/D2 with completed evaluations, at most one paired 12-evaluation block.",
                  replicate_note="Independent API conversations; no deterministic provider seed claim.")
    protocol = {k: v for k, v in inputs.items() if k != "source"}
    protocol["helper"] = dict(name="explore", limit=HELPER_LIMIT, points=EXPLORE_POINTS,
                              rule="Same information tier as evaluate; does not commit the design or consume the 6 evaluations.")
    protocol["calibration"] = str(cal)
    (out/"protocol.json").write_text(json.dumps(protocol, indent=2))
    def emit(row):
        with lock:
            with path.open("a") as f: f.write(json.dumps(row, ensure_ascii=False)+"\n")
    def run(job):
        tid, vis, arm, rep, budget, *rest = job
        helper = bool(rest[0]) if rest else False
        jid = f"{tid}/{vis}/{arm}/r{rep}/b{budget}" + (f"/{'tool' if helper else 'notool'}" if rest else "")
        if jid in terminals: return
        t = {k: v for k, v in rows[tid]["task"].items() if k != "difficulty"}
        x = DEFAULT.copy(); evaluations = 0; helpers = 0; error = None; finish = None
        used = dict(prompt_tokens=0, completion_tokens=0, reasoning_tokens=0, estimated_usd=0., requests=0)
        allowed = local_keys(t) if arm == "Fixed-P0" else tuple(DEFAULT)
        spec = dict(inputs["spec"])
        if vis == "I0": spec |= dict(source=source, G=G, BASE=BASE, SAMPLE_MS=SAMPLE_MS)
        intro = "Design a vibration-powered monitoring node. Use evaluate(changes,reason), relative to the CURRENT design. All-Open/Cert may freely install or remove modules; availability does not install them. Satisfy every constraint, avoid unnecessary hardware. You may finish with a scoped diagnosis."
        if helper:
            intro += " You may also call explore to sweep one or two allowed variables without changing the official design or consuming a design evaluation. explore returns the same information tier as evaluate, at most 20 calls and 11 points each."
        messages = [dict(role="system", content=intro+"\n"+json.dumps(spec)),
                    dict(role="user", content=json.dumps(dict(task=t, initial=x, initial_feedback=feedback(oracle(t, x), vis),
                         allowed_variables=allowed, evaluations=budget, analytic_bound=rows[tid]["bounds"] if arm == "Cert-Guided" else None)))]
        props = {k: dict(type="boolean") if k in MODULES else dict(type="number", minimum=DOMAIN[k][0], maximum=DOMAIN[k][1]) for k in allowed}
        tools = [dict(type="function", function=dict(name="evaluate", description="Apply patch to current design and evaluate.", parameters=dict(type="object", properties=dict(changes=dict(type="object", properties=props, additionalProperties=False), reason=dict(type="string")), required=["changes", "reason"]))),
                 dict(type="function", function=dict(name="finish", description="Stop with scoped diagnosis; no evaluation.", parameters=dict(type="object", properties=dict(missing_function=dict(type="string"), reason=dict(type="string")), required=["missing_function", "reason"])))]
        if helper:
            tools.append(dict(type="function", function=dict(name="explore",
                description="Sweep 1-2 allowed variables around an optional hold patch. Does not commit the official design or use a design evaluation. Returns the same information as evaluate at this visibility tier.",
                parameters=dict(type="object", properties=dict(
                    vary=dict(type="array", items=dict(type="string"), minItems=1, maxItems=2),
                    low=dict(type="array", items={"type": ["number", "boolean"]}, minItems=1, maxItems=2),
                    high=dict(type="array", items={"type": ["number", "boolean"]}, minItems=1, maxItems=2),
                    n=dict(type="integer", minimum=2, maximum=11),
                    hold=dict(type="object", description="Temporary patch, not committed."),
                    reason=dict(type="string")), required=["vary", "low", "high", "reason"]))))
        emit(dict(kind="start", job=jid, task=tid, visibility=vis, arm=arm, replicate=rep, budget=budget, helper=helper, max_output=max_output))
        for _ in range(budget + (HELPER_LIMIT if helper else 0) + 3):
            if halt.is_set(): error = "DEPENDENCY_STOP"; break
            if time.perf_counter()-started > 7200: halt.set(); error = "WALL_STOP"; break
            body = dict(model=inputs["model"], messages=messages, tools=tools, tool_choice="auto", thinking=dict(type="enabled"), reasoning_effort="high", max_tokens=max_output, stream=False)
            raw = json.dumps(body).encode(); reserve = (len(raw)*RATES["input"]+max_output*RATES["output"])/1e6
            with lock:
                if tally["spent"]+tally["reserved"]+reserve > USD_CAP or tally["requests"] >= 600:
                    halt.set(); error = "BUDGET_STOP"; break
                tally["requests"] += 1; rid = tally["requests"]; tally["reserved"] += reserve
            emit(dict(kind="request", job=jid, id=rid, reserved_usd=reserve, max_tokens=max_output))
            try:
                answer, cost = ask(raw, key); u = answer["usage"]
                with lock:
                    tally["reserved"] -= reserve; tally["spent"] += cost
                used["prompt_tokens"] += u["prompt_tokens"]; used["completion_tokens"] += u["completion_tokens"]
                used["reasoning_tokens"] += u.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
                used["estimated_usd"] += cost; used["requests"] += 1
                ch = answer["choices"][0]; m = ch["message"]
                emit(dict(kind="response", job=jid, id=rid, estimated_usd=cost, finish_reason=ch.get("finish_reason"),
                          usage=u, tool_names=[c.get("function", {}).get("name") for c in m.get("tool_calls") or []]))
            except Exception as e:
                halt.set(); error = type(e).__name__+": "+str(e)
                emit(dict(kind="UNKNOWN", job=jid, id=rid, error=error, reservation_usd=reserve)); break
            messages.append(m); calls = m.get("tool_calls", [])
            if not calls:
                error = "OUTPUT_LENGTH" if ch.get("finish_reason") == "length" else "TEXT_WITHOUT_ACTION"; break
            for call in calls:
                try:
                    a = json.loads(call["function"]["arguments"]); name = call["function"]["name"]
                    if name == "finish":
                        finish = a; reply = dict(stopped=True)
                    elif name == "explore":
                        if not helper: raise ValueError("explore is not available in this condition")
                        if helpers >= HELPER_LIMIT: reply = dict(not_executed="explore budget used")
                        else:
                            y = dict(x)
                            if a.get("hold"):
                                patch = a["hold"]
                                if any(k not in allowed or (k in DOMAIN and (type(v) not in (int, float) or not DOMAIN[k][0] <= v <= DOMAIN[k][1])) or (k in MODULES and type(v) is not bool) for k, v in patch.items()):
                                    raise ValueError("Outside declared domain")
                                y |= patch
                            reply = explore_sweep(t, y, allowed, vis, a["vary"], a["low"], a["high"], a.get("n"))
                            helpers += 1
                            emit(dict(kind="explore", job=jid, step=helpers, hold=a.get("hold"), vary=a["vary"], public=reply, reason=a.get("reason")))
                    elif evaluations >= budget or bool(passed(oracle(t, x))):
                        reply = dict(not_executed="Already passed or evaluation budget used")
                    else:
                        patch = a["changes"]
                        if any(k not in allowed or (k in DOMAIN and (type(v) not in (int, float) or not DOMAIN[k][0] <= v <= DOMAIN[k][1])) or (k in MODULES and type(v) is not bool) for k, v in patch.items()): raise ValueError("Outside declared domain")
                        x |= patch; actual = oracle(t, x); evaluations += 1; reply = feedback(actual, vis)
                        emit(dict(kind="evaluation", job=jid, step=evaluations, design=x.copy(), actual=scalar(actual), public=reply, reason=a.get("reason")))
                    messages.append(dict(role="tool", tool_call_id=call["id"], content=json.dumps(reply | dict(remaining_evaluations=budget-evaluations, remaining_explores=HELPER_LIMIT-helpers if helper else 0))))
                except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
                    emit(dict(kind="invalid_action", job=jid, error=str(e)))
                    messages.append(dict(role="tool", tool_call_id=call["id"], content=json.dumps(dict(error=str(e), remaining_evaluations=budget-evaluations, remaining_explores=HELPER_LIMIT-helpers if helper else 0))))
            if finish is not None or bool(passed(oracle(t, x))) or evaluations >= budget: break
        actual = scalar(oracle(t, x)); ok = bool(passed(actual)); tight = min(actual["slack"], key=actual["slack"].get)
        result = dict(kind="terminal", job=jid, task=tid, visibility=vis, arm=arm, replicate=rep, budget=budget, helper=helper,
                      pass_=ok, evaluations=evaluations, helper_calls=helpers, first_pass=evaluations if ok else None, final_design=x,
                      tightest=tight, minimum_slack=actual["slack"][tight], final_actual=actual,
                      enabled_modules=[k for k in MODULES if x[k]], diagnosis=finish, error=error, usage=used)
        emit(result); print(jid, "PASS" if ok else error or "FAIL", evaluations, "explore", helpers, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: list(pool.map(run, jobs))
    print(json.dumps(dict(accounting=tally, runtime_s=time.perf_counter()-started, operational_stop=halt.is_set())), flush=True)
    report(out)


def followup_jobs():
    rows = [json.loads(s) for s in (OUT/"agents.jsonl").read_text().splitlines()]
    transfer = json.loads((OUT/"transient.json").read_text())
    qualified = {a["source_job"].removeprefix("calibration/").split("-")[0] for a in transfer if not a["removed_module"]
                 and a["transient"]["verdict"] == "PASS" and any(b["source_job"] == a["source_job"]
                 and b["removed_module"] and b["transient"]["verdict"] == "FAIL" for b in transfer)}
    first = {(r["task"], r["visibility"], r["arm"]): r for r in rows if r["kind"] == "terminal" and r["replicate"] == 0 and r["budget"] == 6}
    jobs = []; selected = []
    for vis in ("I1", "I2", "I0"):
        for case in ("wake", "impact"):
            if case not in qualified: continue
            a = first.get((case+"-D2", vis, "All-Open")); b = first.get((case+"-D2", vis, "Cert-Guided"))
            if not a or not b or a["error"] or b["error"]: continue
            if a["pass_"] != b["pass_"] or (a["pass_"] and abs(a["first_pass"]-b["first_pass"]) >= 2): selected.append((case+"-D2", vis))
    for tid, vis in selected[:2]: jobs += [(tid, vis, arm, rep, 6) for rep in (1, 2) for arm in ARMS]
    for case in ("wake", "impact"):
        if case not in qualified: continue
        a = first.get((case+"-D2", "I1", "All-Open")); b = first.get((case+"-D2", "I1", "Cert-Guided"))
        if a and b and not a["error"] and not b["error"] and not a["pass_"] and not b["pass_"]:
            jobs += [(case+"-D2", "I1", arm, 3, 12) for arm in ("All-Open", "Cert-Guided")]; break
    (OUT/"followup-selection.json").write_text(json.dumps(dict(selected_blocks=selected[:2], qualified_cases=sorted(qualified), jobs=jobs,
        policy="Original sign-blind gap rule, plus physical-transfer requirement after observed impact model mismatch; no repetitions for an unqualified engineering premise"), indent=2))
    return jobs


def _usage_of(r):
    return r.get("usage") or r.get("response", {}).get("usage") or {}


def report(out=None):
    out = Path(out) if out else OUT
    records = [json.loads(s) for s in (out/"agents.jsonl").read_text().splitlines()]
    terminal = [r for r in records if r["kind"] == "terminal"]; responses = [r for r in records if r["kind"] == "response"]
    usage = {k: sum(_usage_of(r).get(k, 0) for r in responses) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens")}
    usage["reasoning_tokens"] = sum(_usage_of(r).get("completion_tokens_details", {}).get("reasoning_tokens", 0) for r in responses)
    costs = sum(r["estimated_usd"] for r in responses)
    cells = {}
    for r in terminal:
        key = (r.get("visibility"), r.get("arm"), bool(r.get("helper")))
        cells.setdefault(str(key), []).append(dict(job=r["job"], pass_=r["pass_"], first_pass=r.get("first_pass"),
            evaluations=r["evaluations"], helper_calls=r.get("helper_calls", 0), minimum_slack=r.get("minimum_slack"),
            tightest=r.get("tightest"), error=r.get("error"), modules=r.get("enabled_modules"), usage=r.get("usage")))
    summary = dict(results=terminal, requests=len([r for r in records if r["kind"] == "request"]), settled=len(responses),
                   unknown=[r for r in records if r["kind"] == "UNKNOWN"], usage=usage, conservative_estimated_usd=costs,
                   cache_aware_peak_estimated_usd=costs-usage["prompt_cache_hit_tokens"]*(.30-.006)/1e6,
                   evaluations=len([r for r in records if r["kind"] == "evaluation"]),
                   explores=len([r for r in records if r["kind"] == "explore"]),
                   invalid_actions=len([r for r in records if r["kind"] == "invalid_action"]),
                   length_truncated=sum(r.get("error")=="OUTPUT_LENGTH" for r in terminal),
                   cells=cells)
    (out/"summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def compact_transient(a):
    return dict(verdict=a["verdict"], checks=a["checks"], metrics=a["metrics"], energy_J=a.get("energy_J"), runtime_s=a.get("runtime_s"))


def run_one_transient(t, x):
    d = copy.deepcopy(BASE)
    d["harvester"] |= dict(substrate_mm=.15*x["h"], piezo_layer_mm=.12*x["h"], tip_mass_g=x["mass_g"])
    d["trigger_beam"] |= dict(length_mm=x["L2_mm"], tip_mass_g=x["m2_g"])
    d["modules"] = {k: x[k] for k in MODULES}
    d["circuit"] |= dict(storage_uF=x["C_uF"], start_V=x["gate_V"], wake_high_V=x["trigger_V"],
                          wake_low_V=x["trigger_V"]*.33, converter_input_R_ohm=x["R_kohm"]*1000,
                          shunt_ohm=x["shunt_kohm"]*1000, shunt_threshold_V=x["shield_V"])
    d["firmware"]["poll_s"] = x["poll_ms"]/1000
    task = dict(TASK, background_peak_g=t["background_g"], fault_Hz=t["event_Hz"], fault_peak_g=t["event_g"],
                fault_duration_s=t["event_ms"]/1000, stress_limit_MPa=t["stress_MPa"],
                fault_starts_s=[t["ready_s"], t["ready_s"]+6], duration_s=t["ready_s"]+7.5,
                nuisance_starts_s=[t["ready_s"]+3])
    a = simulate(d, task); a.pop("trace", None)
    return compact_transient(a)


def d3_transient(out, calibration):
    """Replay a few passing wake-D3 designs, plus one remove-A counterfactual. Stop under 5 minutes."""
    summary = json.loads((out/"summary.json").read_text())
    t = next(r["task"] for r in json.loads(Path(calibration).read_text())["workpoints"] if r["task"]["id"] == "wake-D3")
    passed = [r for r in summary["results"] if r["pass_"]]
    chosen, seen = [], set()
    for r in sorted(passed, key=lambda r: (r.get("first_pass") or 9, r["job"])):
        key = tuple(sorted((k, r["final_design"][k]) for k in list(DOMAIN)+list(MODULES)))
        if key in seen: continue
        seen.add(key); chosen.append(r)
        if len(chosen) >= 3: break
    output, started = [], time.perf_counter()
    for i, r in enumerate(chosen):
        if time.perf_counter()-started > 280: break
        a = run_one_transient(t, r["final_design"])
        output.append(dict(source_job=r["job"], removed_module=False, harmonic=r.get("final_actual"), transient=a))
        print(r["job"], "selected", a["verdict"], a["metrics"].get("delivered_on_time"), flush=True)
        if i == 0:
            x = dict(r["final_design"], A=False)
            b = run_one_transient(t, x)
            output.append(dict(source_job=r["job"], removed_module=True, harmonic=scalar(oracle(t, x)), transient=b))
            print(r["job"], "removed-A", b["verdict"], b["metrics"].get("delivered_on_time"), flush=True)
        (out/"transient.json").write_text(json.dumps(output, indent=2))
    return output


def d3_plot(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = [json.loads(s) for s in (out/"agents.jsonl").read_text().splitlines() if s]
    terms = [r for r in rows if r["kind"]=="terminal"]
    vis_arm = [("I1","All-Open"),("I1","Cert-Guided"),("I2","All-Open"),("I2","Cert-Guided")]
    fig, axes = plt.subplots(2, 4, figsize=(11, 5.2), sharey=True, layout="constrained")
    for col, (vis, arm) in enumerate(vis_arm):
        for row, helper in enumerate((False, True)):
            ax = axes[row][col]
            cell = [r for r in terms if r.get("visibility")==vis and r.get("arm")==arm and bool(r.get("helper"))==helper]
            cell = sorted(cell, key=lambda r: r.get("replicate", 0))
            colors, labels = [], []
            for r in cell:
                if r["pass_"]: colors.append("#16a34a"); labels.append(f"P{r['first_pass']}")
                elif r.get("error")=="OUTPUT_LENGTH": colors.append("#f59e0b"); labels.append(f"L{r['evaluations']}")
                elif r.get("error"): colors.append("#a8a29e"); labels.append(r["error"][:6])
                else: colors.append("#dc2626"); labels.append(f"N{r['evaluations']}")
            ax.bar(range(len(cell)), [1]*len(cell), color=colors)
            for i, (r, lab) in enumerate(zip(cell, labels)):
                ax.text(i, 0.5, lab, ha="center", va="center", color="white", fontsize=8)
                ax.text(i, 0.15, f"e{r.get('helper_calls',0)}", ha="center", va="center", color="white", fontsize=6)
            ax.set_xticks(range(3), ["s0","s1","s2"]); ax.set_yticks([])
            ax.set_title(f"{vis} {arm}\n{'explore' if helper else 'no tool'}", fontsize=8)
    fig.suptitle("wake-D3 2x2x2x3  |  P=first pass  N=finished fail  L=truncated  e=explore calls")
    fig.savefig(out/"overview.png", dpi=120); plt.close(fig)


def d3_jobs():
    return [("wake-D3", vis, arm, rep, 6, helper)
            for vis in ("I1", "I2") for helper in (False, True)
            for arm in ("All-Open", "Cert-Guided") for rep in (0, 1, 2)]


def transient():
    """D2 I0 successes plus module removal; a calibration witness if All-Open submitted none."""
    calibration = json.loads((OUT/"calibration.json").read_text()); summary = json.loads((OUT/"summary.json").read_text())
    output = json.loads((OUT/"transient.json").read_text()) if (OUT/"transient.json").exists() else []
    for case in ("wake", "impact"):
        t = next(r["task"] for r in calibration["workpoints"] if r["task"]["id"] == case+"-D2")
        candidates = [r for r in summary["results"] if r["task"] == case+"-D2" and r["pass_"]]
        for arm in ("All-Open", "Cert-Guided"):
            choices = [r for r in candidates if r["arm"] == arm and r["visibility"] == "I0" and r["replicate"] == 0]
            if not choices:
                if arm != "All-Open": continue
                row = next(a for a in calibration["workpoints"] if a["task"]["id"] == case+"-D2")
                witness = row["witnesses"].get("A" if case == "wake" else "D")
                if witness is None: continue
                choices = [dict(job="calibration/"+case+"-D2", final_design=witness,
                                enabled_modules=[k for k in MODULES if witness[k]], first_pass=0)]
            r = min(choices, key=lambda r: (len(r["enabled_modules"]), r["first_pass"], r["job"]))
            for remove in (False, True):
                if any(a["source_job"] == r["job"] and a["removed_module"] == remove for a in output): continue
                x = dict(r["final_design"])
                if remove: x["A" if case == "wake" else "D"] = False
                d = copy.deepcopy(BASE)
                d["harvester"] |= dict(substrate_mm=.15*x["h"], piezo_layer_mm=.12*x["h"], tip_mass_g=x["mass_g"])
                d["trigger_beam"] |= dict(length_mm=x["L2_mm"], tip_mass_g=x["m2_g"])
                d["modules"] = {k: x[k] for k in MODULES}
                d["circuit"] |= dict(storage_uF=x["C_uF"], start_V=x["gate_V"], wake_high_V=x["trigger_V"],
                                      wake_low_V=x["trigger_V"]*.33, converter_input_R_ohm=x["R_kohm"]*1000,
                                      shunt_ohm=x["shunt_kohm"]*1000, shunt_threshold_V=x["shield_V"])
                d["firmware"]["poll_s"] = x["poll_ms"]/1000
                task = dict(TASK, background_peak_g=t["background_g"], fault_Hz=t["event_Hz"], fault_peak_g=t["event_g"],
                            fault_duration_s=t["event_ms"]/1000, stress_limit_MPa=t["stress_MPa"],
                            fault_starts_s=[t["ready_s"], t["ready_s"]+6], duration_s=t["ready_s"]+7.5,
                            nuisance_starts_s=[t["ready_s"]+3])
                if case == "impact":
                    d["firmware"] |= dict(target_band_Hz=[35, 55], minimum_target_rms_g=1., wake_from_harvester=True)
                    d["circuit"] |= dict(wake_high_V=x["gate_V"]+.3, wake_low_V=(x["gate_V"]+.3)*.33)
                    task |= dict(nuisance_Hz=75., nuisance_peak_g=2.)
                a = simulate(d, task); a.pop("trace")
                output.append(dict(source_job=r["job"], removed_module=remove, harmonic=scalar(oracle(t, x)), transient=a))
                print(r["job"], "removed" if remove else "selected", a["verdict"], a["metrics"], flush=True)
                (OUT/"transient.json").write_text(json.dumps(output, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for flag in ("calibrate", "agents", "followup", "transient", "report", "d3", "tool"): p.add_argument("--"+flag, action="store_true")
    args = p.parse_args()
    if args.calibrate: calibrate()
    if args.agents:
        rows = json.loads((OUT/"calibration.json").read_text())["workpoints"]
        run_agents([(r["task"]["id"], vis, arm, 0, 6) for r in rows for vis in ("I0", "I1", "I2") for arm in ARMS])
    if args.followup:
        jobs = followup_jobs()
        if jobs: run_agents(jobs)
    if args.d3:
        dest = HERE/"boundary_d3"
        jobs = d3_jobs()
        if args.tool: jobs = [j for j in jobs if j[5]]
        run_agents(jobs, out=dest, calibration=HERE/"boundary"/"calibration.json", max_output=D3_MAX_OUTPUT)
        try: d3_plot(dest)
        except Exception as e: print("plot skipped:", type(e).__name__, e, flush=True)
        try: d3_transient(dest, HERE/"boundary"/"calibration.json")
        except Exception as e: print("transient skipped:", type(e).__name__, e, flush=True)
    if args.report: report(HERE/"boundary_d3" if args.d3 else OUT)
    if args.transient and not args.d3: transient()
