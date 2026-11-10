"""Parametric harvester-node world for the boundary pilots: closed-form evaluator, skins, task cells, Layer-0 audit."""
import itertools
import json
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from scipy.optimize import differential_evolution

VARS = dict(h=(.5, 2, 1), m=(1, 10, 1), R=(1, 1000, 1), C=(10, 3000, 1), V=(2, 4, 0), T=(10, 5000, 1), th=(.05, 2, 1), Vs=(2, 40, 1))
MODS = dict(W=(1, 6), S=(.5, 4), U=(5, 6), M=(3, 8))  # idle uW, area mm2
NEED = dict(wake="W", stress="S", start="U", burst="M")
X0 = dict(h=1., m=3., R=40., C=200., V=3., T=500., th=.2, Vs=10.) | dict.fromkeys(MODS, False)
ENV = dict(f=60., a_bg=.1, a_ev=.5, a_wk=.8, E_ms=5000., E_pk=50., period=10., sigma=300., area=60., ready=60., load=0., couple=0., X_max=2., free=False)
HARD = dict(wake=dict(E_ms=150.), stress=dict(a_ev=3.), start=dict(a_bg=.05), burst=dict(E_pk=6000., period=1200.))
HIDDEN = ("displacement", "false_wake", "aging")
PRIMS = dict(aux_resonator=(.3, 3, "second small cantilever with its own piezo output, tuned near the bump frequency"),
             comparator=(.4, 1, "logic output high while its input voltage exceeds thr1 (aux path) or thr2 (piezo path)"),
             mcu_wake_pin=(.3, 2, "logic input that wakes the MCU from sleep"),
             switch=(.1, 1, "connects two nodes while its logic input is high"),
             bleed_resistor=(0, 2, "low-value resistor that can be placed across the harvester piezo terminals"),
             charge_pump=(5, 6, "cold-start converter that runs from 0.5 V input at 70% efficiency"),
             supercap=(3, 8, "5 mJ thin-film backup cell, available from power-up"),
             led=(2, 2, "status LED"), temp_sensor=(1, 2, "ambient temperature sensor"), watchdog=(.5, 1, "independent watchdog timer"))
RECIPE = dict(W={"aux_resonator", "comparator", "mcu_wake_pin"}, S={"comparator", "switch", "bleed_resistor"}, U={"charge_pump"}, M={"supercap"})
NAMES = dict(h="thickness_mult", m="tip_mass_g", R="load_kohm", C="storage_uF", V="start_V", T="poll_ms", th="wake_thr_V", Vs="shunt_thr_V")


def inner(x, skin):
    """Counterfactual skins are an exact log-reflection of h and m: identical volume and ridge, reversed laws."""
    return x | dict(h=1/x["h"], m=10/x["m"]) if skin.startswith("counter") else x


def physics(x, e, low=0.):
    g = lambda k: np.asarray(x[k], float)
    on = {k: np.asarray(x[k], bool) for k in MODS}
    idle_m, area_m = ({k: 0. for k in MODS},)*2 if e["free"] else ({k: v[0] for k, v in MODS.items()}, {k: v[1] for k, v in MODS.items()})
    if "prims" in x: idle_m, area_m = {k: 0. for k in MODS}, {k: 0. for k in MODS}
    h, m, R = g("h"), g("m"), g("R")
    r = R*h/40; lm = 2*r/(1+r*r)
    fn = 120*h**1.5/np.sqrt(m)*(1+e["couple"]*(lm-.5))
    H = 1/np.sqrt((1-(e["f"]/fn)**2)**2+(e["f"]/(25*fn))**2)
    P = 3*e["a_bg"]**2*m*H**2*lm
    Vb = np.sqrt(2e-3*P*R); Ve = Vb*e["a_ev"]/e["a_bg"]
    damp = np.where(on["S"] & (Ve > g("Vs")), g("Vs")/Ve, 1.)
    P = np.where(on["S"] & (Vb > g("Vs")), .2, 1.)*np.where(on["U"], .7, .85)*P*(1+low)
    stress = 1.5*e["a_ev"]*m*H*damp/h**2*(1-low)
    idle = 2+e["load"]+sum(on[k]*idle_m[k] for k in MODS)+x.get("prims_idle", 0)
    demand = idle+np.where(on["W"], 0, 18000/g("T"))+e["E_pk"]/e["period"]
    area = 10+.02*g("C")+sum(on[k]*area_m[k] for k in MODS)+x.get("prims_area", 0)
    s = dict(energy=(P-demand)/demand,
             cold_start=(P-idle)*e["ready"]/(.5*g("C")*g("V")**2)-1,
             burst=(.5*g("C")*(g("V")**2-3.24)+on["M"]*5000)/e["E_pk"]-1,
             capture=np.where(on["W"], .8*e["a_wk"]/g("th")-1, e["E_ms"]/(g("T")+60)-1),
             start=Vb/np.where(on["U"], .5, g("V")+.4)-1,
             stress=1-stress/e["sigma"], area=1-area/e["area"],
             displacement=1-.25*e["a_ev"]*H*damp*(60/fn)**2/e["X_max"],
             false_wake=np.where(on["W"], 1-2.4*e["a_bg"]/g("th"), 1.), aging=(.85*P-demand)/demand)
    return s, dict(harvest_uW=P, demand_uW=demand, resonance_Hz=fn, stress_MPa=stress, open_V=Vb, load_match_0to1=lm, source_impedance_kohm=40/h)


def margin(x, t, low=0.):
    s = physics(x, t["env"], low)[0]
    return np.min([s[k] for k in s if t["hidden"] or k not in HIDDEN], axis=0)


def compile_prims(x, t):
    """Primitive arm: a module works only if its full recipe is present; every primitive pays its own cost."""
    if t["menu"] != "prims": return x
    have = {p for p in PRIMS if x.get(p)}
    return x | {k: RECIPE[k] <= have for k in MODS} | dict(prims=True, prims_idle=sum(PRIMS[p][0] for p in have), prims_area=sum(PRIMS[p][1] for p in have))


def internal(view, t):
    return compile_prims(inner(view, t["skin"]), t)


def best(t, mods, objective=None):
    """Private optimum over continuous variables with fixed modules (never shown to agents)."""
    keys = list(VARS)
    lo = [np.log(VARS[k][0]) if VARS[k][2] else VARS[k][0] for k in keys]; hi = [np.log(VARS[k][1]) if VARS[k][2] else VARS[k][1] for k in keys]
    def point(u): return {k: np.exp(u[i]) if VARS[k][2] else u[i] for i, k in enumerate(keys)} | {k: k in mods for k in MODS}
    f = objective or (lambda x: margin(x, t))
    rs = [differential_evolution(lambda u: -f(point(u)), list(zip(lo, hi)), popsize=25, maxiter=400, tol=1e-12, seed=s, polish=True, vectorized=True, updating="deferred") for s in (0, 1)]
    x = {k: float(v) if k in VARS else bool(v) for k, v in point(min(rs, key=lambda r: r.fun).x).items()}
    return float(f(x)), x


def make(cid, family, need=("wake",), w=.01, skin="text", feedback="cont", hidden=False, menu="menu", spec="E0",
         python=False, budget=6, distract=0, low=0., told=False, cert=False, model=("deepseek-flash", "high"), x0={}, **env):
    t = dict(id=cid, family=family, need=list(need), target=w, skin=skin, feedback=feedback, hidden=hidden, menu=menu, spec=spec,
             python=python, budget=budget, distract=distract, low=low, told=told, cert=cert, model=list(model), x0=x0,
             env=ENV | {k: v for n in need for k, v in HARD[n].items()} | env)
    mods = {NEED[n] for n in need}
    a, b = 0., 2000.
    for _ in range(30):  # bisection on a constant sensor load sets the optimum min-slack to the target
        t["env"]["load"] = (a+b)/2
        a, b = (t["env"]["load"], b) if best(t, mods)[0] > w else (a, t["env"]["load"])
    t["env"]["load"] = a
    t["optimum"], t["witness"] = best(t, mods)
    t["combos"] = {"".join(c) or "none": round(best(t, set(c))[0], 6) for n in range(5) for c in itertools.combinations(MODS, n)}
    return t


def spec(cid, family, **kw):
    return cid, family, kw


def cells():
    c = []
    for skin, w in itertools.product(("text", "abstract", "counter", "counter_hidden", "text_hidden", "counter_hidden_obs"), (.1, 1e-3)): c.append(spec(f"A/{skin}/{w:g}", "A", w=w, skin=skin))
    for w, py in itertools.product((.1, 1e-2, 1e-3, 1e-4, 1e-5), (False, True)): c.append(spec(f"B/{w:g}/{'py' if py else 'nopy'}", "B", w=w, python=py))
    needs = list(NEED)
    for k in range(1, 5): c.append(spec(f"C/k{k}", "C", need=needs[:k]))
    c.append(spec("C/k4-free", "C", need=needs, free=True))
    for name, cpl, told in (("D0", 0., False), ("D1", .1, True), ("D2", .1, False), ("D1", .3, True), ("D2", .3, False)):
        c.append(spec(f"D/{name}/{cpl:g}", "D", couple=cpl, told=told, python=True))
    for level, need in itertools.product(("E0", "E1", "E2"), ("wake", "stress")): c.append(spec(f"E/{level}/{need}", "E", need=(need,), hidden=True, spec=level))
    for b, told in itertools.product((0., .1, .3), (False, True)): c.append(spec(f"F/{b:g}/{'told' if told else 'untold'}", "F", w=.02, low=b, told=told, python=True, budget=3))
    for need, w in itertools.product((("wake",), ("stress",), ("wake", "stress")), (3e-3, -.05)): c.append(spec(f"G/{'+'.join(need)}/{'feasible' if w > 0 else 'infeasible'}", "G", need=need, w=w))
    for menu, need in itertools.product(("menu", "prims"), ("wake", "stress")): c.append(spec(f"H/{menu}/{need}", "H", need=(need,), w=.02, menu=menu))
    for d in (0, 8, 16, 24): c.append(spec(f"I/{8+d}", "I", distract=d))
    for b in (6, 20, 50): c.append(spec(f"J/{b}", "J", w=1e-3, budget=b))
    for f in ("cont", "rank", "bin", "noisy"): c.append(spec(f"K/{f}", "K", feedback=f))
    mids = dict(A=dict(w=1e-3, skin="counter"), E=dict(hidden=True, spec="E2"), F=dict(w=.02, low=.3, python=True, budget=3),
                G=dict(w=-.05), H=dict(w=.02, menu="prims"))
    for (fam, kw), model in itertools.product(mids.items(), (("deepseek-flash", "off"), ("deepseek-v4-pro", "high"))):
        c.append(spec(f"L/{fam}/{model[0]}-{model[1]}", "L", model=model, **kw))
    for fam, kw in dict(D=dict(couple=.3, python=True), E=mids["E"], F=mids["F"], G=mids["G"]).items(): c.append(spec(f"X/{fam}/cert", "X", cert=True, **kw))
    return c


def fresh(cid, n=8):
    """Confirmation: n fresh instances of a cell (new source frequency and wake envelope per instance)."""
    _, family, kw = {c[0]: c for c in cells()}[cid]; rng = np.random.default_rng(zlib.crc32(cid.encode()))
    return [(f"{cid}#{i}", family, kw | dict(f=float(rng.uniform(50, 70)), a_wk=float(rng.uniform(.7, .9)))) for i in range(n)]


def bound(t, mods, rounds=24):
    """Sound upper bound on max min(energy, stress) slack for one module set: relax lm<=1, S at its best threshold (Vs=Vb, stress uses a_bg)
    or lossy (x0.2 harvest, stress>=0), then interval branch-and-bound over log(h), log(m) with the unimodal resonance gain."""
    e = t["env"]; Hf = lambda u: 1/np.sqrt((1-u*u)**2+(u/25)**2); us = np.sqrt(1-1/1250)
    D = 2+e["load"]+sum(0 if e["free"] else MODS[k][0] for k in mods)+(0 if "W" in mods else 18000/(e["E_ms"]-60))+e["E_pk"]/e["period"]
    eff = .7 if "U" in mods else .85; out = -np.inf
    for fac, a_s in ([(1, e["a_bg"]), (.2, 0)] if "S" in mods else [(1, e["a_ev"])]):
        def ub(h0, h1, m0, m1, point=False):
            ul, uh = e["f"]*np.sqrt(m0)/(120*h1**1.5), e["f"]*np.sqrt(m1)/(120*h0**1.5)
            Hu, Hl = (Hf(ul),)*2 if point else (Hf(np.clip(us, ul, uh)), np.minimum(Hf(ul), Hf(uh)))
            return np.minimum((fac*eff*3*e["a_bg"]**2*m1*Hu**2-D)/D, 1-1.5*a_s*m0*Hl/h1**2/e["sigma"])
        b = np.array([[np.log(.5), np.log(2), 0, np.log(10)]])
        for _ in range(rounds):
            if not len(b): break
            h0, h1, m0, m1 = np.exp(b.T); u = ub(h0, h1, m0, m1); c = np.exp((b[:, :2].mean(1), b[:, 2:].mean(1)))
            lb = ub(c[0], c[0], c[1], c[1], True).max(); out = max(out, u[u < max(lb, 0)].max(initial=-np.inf))
            b = b[u >= max(lb, 0)]; hm, mm = b[:, :2].mean(1), b[:, 2:].mean(1)
            b = np.concatenate([np.c_[b[:, 0], hm, b[:, 2], mm], np.c_[hm, b[:, 1], b[:, 2], mm], np.c_[b[:, 0], hm, mm, b[:, 3]], np.c_[hm, b[:, 1], mm, b[:, 3]]])
        if len(b): h0, h1, m0, m1 = np.exp(b.T); out = max(out, ub(h0, h1, m0, m1).max())
    return float(out)


def rho(t, n=2_000_000, mods=None):
    """Random feasible volume: log-uniform / uniform continuous variables, module bits uniform (or fixed to `mods`)."""
    r = np.random.default_rng(0); x = {k: np.exp(r.uniform(np.log(a), np.log(b), n)) if lg else r.uniform(a, b, n) for k, (a, b, lg) in VARS.items()}
    return float(np.mean(margin(x | {k: (r.random(n) < .5) if mods is None else np.full(n, k in mods) for k in MODS}, t) >= 0))


def pair(i):
    """Exp 2 matched pair i: identical env (fresh f, a_ev), T4b-like default shunt threshold below the background open voltage; only the load differs."""
    r = np.random.default_rng(1000+i); env = dict(f=float(r.uniform(50, 70)), a_ev=float(r.uniform(2.6, 3.4)))
    ts = [make(f"G2/p{i}/{k}", "G", need=("stress",), w=w, x0=dict(Vs=2.), **env) for k, w in (("feasible", .03), ("infeasible", -.03))]
    for t in ts: t |= dict(bounds={"".join(c) or "none": bound(t, set(c)) for n in range(5) for c in itertools.combinations(MODS, n)}, rho=rho(t), rho_S=rho(t, mods={"S"}), audit=audit(t))
    return ts


def build(cid, family, kw):
    t = make(cid, family, **kw)
    return t | dict(audit=audit(t))


def audit(t):
    """Layer-0: feasible cells need a stored witness; every module combo lacking a required module must stay below zero."""
    mods = {NEED[n] for n in t["need"]}
    feasible = t["target"] > 0
    shortcut = max(v for k, v in t["combos"].items() if not mods <= set(k.replace("none", "")))
    ok = (t["optimum"] >= 0 and margin(t["witness"], t) >= 0) if feasible else max(t["combos"].values()) < 0
    return dict(feasible=feasible, witness_ok=bool(ok), best_without_required=shortcut, shortcut_closed=shortcut < 0)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent/"pilots"; out.mkdir(exist_ok=True)
    confirm = sys.argv[1:2] == ["--confirm"]; decisive = sys.argv[1:2] == ["--decisive"]  # --decisive <cell>...: Exp 2 pairs + fresh instances
    closure = sys.argv[1:2] == ["--closureA"]  # closure A: 8 fresh matched pairs p8..p15
    path = out/("confirm.json" if confirm else "decisive.json" if decisive else "closureA.json" if closure else "tasks.json")
    old = json.loads(path.read_text()) if confirm and path.exists() else []
    with Pool() as pool:
        rows = [] if closure else pool.starmap(build, [c for cid in sys.argv[2:] for c in fresh(cid)] if confirm or decisive else cells())
        if decisive or closure: rows += [t for ts in pool.map(pair, range(8, 16) if closure else range(8)) for t in ts]
    path.write_text(json.dumps(old+rows, indent=1, default=float))
    for t in rows: print(t["id"], round(t["optimum"], 6), round(t["env"]["load"], 3), t["audit"])
