"""Scope experiment: existing harmonic oracle, witnessed feasibility, analytic energy bounds."""
import copy
import json
from pathlib import Path

from agent_limits import DEFAULT, DOMAIN, MODULES, bounds, oracle, passed, public_spec, scalar

OUT = Path(__file__).with_name("phase2") / "scope.json"
FIDELITY = "settled harmonic screen; fixed 62.5 ms acquisition; not transient/classification"


def evaluate(t, x):
    r = scalar(oracle(t["_physical"], dict(t["initial"], **x)))
    base = {k: v for k, v in r.items() if k != "slack"}
    ok = bool(passed(r))
    return dict(pass_=ok, slack=r["slack"], terminal=dict(feasible=ok), base=base,
                diagnostic=base, cost=dict(full=0, numeric=1), fidelity=FIDELITY)


def tasks(stage="G"):
    return copy.deepcopy(json.loads(OUT.read_text())["tasks"][stage])


def view(t, arm="P"):
    prefix = t["prefix"]
    if arm == "H":
        return dict(prefix=prefix, analytic_bound=t["public_bound"])
    best = max(prefix, key=lambda r: min(r["result"]["slack"].values()))
    summary = dict(evaluations=len(prefix), passes=sum(r["result"]["pass_"] for r in prefix),
                   best_observed_design=best["design"], best_observed_result=best["result"],
                   analytic_bound=t["public_bound"])
    if arm == "P":
        return dict(prefix=prefix, progress_summary=summary)
    varied = [k for k in t["initial"] if len({json.dumps(r["design"][k]) for r in prefix}) > 1]
    active = [k for k in MODULES if t["initial"][k]]
    scope = dict(active_modules=active,
                fixed_variables={k: v for k, v in t["initial"].items() if k not in varied},
                tried_variables=varied, untried_variables=[k for k in t["initial"] if k not in varied],
                evaluated_points=[r["design"] for r in prefix], legal_domain=t["domain"],
                result_kind="finite observed points, not a global extremum or an infeasibility proof",
                bound_scope=t["public_bound"]["scope"] if t["public_bound"] else None)
    return dict(prefix=prefix, scope_summary=dict(summary=summary, search_scope=scope))


def _public_bound(b, state):
    if state == "S2":
        return dict(scope="All declared geometry/load values with A absent; B/C/D allowed",
                    power_upper_uW=b["power_upper_uW"],
                    no_wake_power_lower_uW=b["no_wake_power_lower_uW"],
                    active_B_power_lower_uW=b["active_B_power_lower_uW"],
                    excluded_without_A=b["excluded_without_A"], derivation=b["derivation"])
    if state == "S4":
        return dict(scope=b["scope"] + "; ALL legal A/B/C/D combinations",
                    power_upper_uW=b["power_upper_uW"],
                    minimum_service_power_lower_uW=min(b["no_wake_power_lower_uW"],
                         b["active_A_power_lower_uW"], b["active_B_power_lower_uW"]),
                    all_architectures_excluded_by_energy=b["all_architectures_excluded_by_energy"],
                    derivation=b["derivation"])
    return None


def qualify():
    calibration = json.loads(Path(__file__).with_name("boundary").joinpath("calibration.json").read_text())
    rows = {r["task"]["id"]: r for r in calibration["workpoints"]}
    witnesses = dict(S1=rows["wake-D1"]["witnesses"]["none"], S2=rows["wake-D2"]["witnesses"]["A"])
    result = dict(tasks=dict(G=[], CG=[]), qualification=[], new_math=0, fidelity=FIDELITY,
                  truth_policy="PASS witness or existing analytic necessary energy bound; no random-zero proof",
                  selection="Parameter templates fixed before Agent results; G S3/S4 share physics; CG uses twelve independent parameter instances")
    settings = [("G", i, s) for i in range(4) for s in ("S1", "S2", "S3", "S4")]
    settings += [("CG", 6+3*j+i, s) for j, s in enumerate(("S1", "S2", "S3", "S4")) for i in range(3)]
    for stage, i, state in settings:
        physical = dict(case="wake", background_Hz=45., background_g=.30 if state == "S1" else .16 if state == "S2" else .052+.001*i,
                        event_Hz=210., event_g=.50+.01*i, event_ms=3000.+100*i if state == "S1" else 150.+4*i,
                        event_period_s=6., ready_s=90.+5*i, stress_MPa=40.+i, area_mm2=85.+3*i)
        ident = f"{stage}-{i+1}-{state}"
        b = scalar(bounds(physical))
        t = dict(id=ident, initial=DEFAULT.copy(), domain=scalar(DOMAIN) | {k: [False, True] for k in MODULES},
                 spec=dict(public_spec(), task=physical, goal="Satisfy every harmonic constraint; all legal joint edits are allowed"),
                 _physical=physical, public_bound=_public_bound(b, state), prefix=[])
        for x in ((DEFAULT.copy(), dict(DEFAULT, C_uF=150.)) if stage == "G" else (DEFAULT.copy(),)):
            y = evaluate(t, x); result["new_math"] += 1
            t["prefix"].append(dict(design=x, result=y))
        if any(r["result"]["pass_"] for r in t["prefix"]):
            raise ValueError((ident, "prefix must be failed"))
        witness = witnesses.get(state)
        witness_result = evaluate(t, witness) if witness else None
        result["new_math"] += int(witness is not None)
        if witness is not None and not witness_result["pass_"]:
            raise ValueError((ident, "saved witness did not pass", witness_result))
        if state == "S2" and not b["excluded_without_A"]:
            raise ValueError((ident, "branch bound unavailable"))
        energy_impossible = b["power_upper_uW"] < min(b["no_wake_power_lower_uW"], b["active_A_power_lower_uW"], b["active_B_power_lower_uW"])
        if state in ("S3", "S4") and not energy_impossible:
            raise ValueError((ident, "global energy bound unavailable"))
        t["private"] = dict(state=state, truth=state in ("S1", "S2"), witness=witness,
                            witness_result=witness_result, bound=b, original_branch=dict(A=False, B=False, C=False, D=False),
                            branch_truth=state == "S1", global_proof=energy_impossible, prefix=t["prefix"])
        result["tasks"][stage].append(t)
        result["qualification"].append(dict(id=ident, state=state, truth=t["private"]["truth"],
                    witness_pass=witness_result["pass_"] if witness_result else None,
                    energy_impossible=energy_impossible, public_bound=t["public_bound"]))
    OUT.parent.mkdir(exist_ok=True)
    result["development_math"] = 6
    result["development_incident"] = dict(task="G-1-S2", previous_event_g=.45, reused_witness_capture_slack=-.08099795234082208, result="FAIL; old witness not qualified at reduced amplitude; pre-Agent template starts at original qualified .50g")
    OUT.write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    r = qualify()
    print(json.dumps(dict(new_math=r["new_math"], tasks={k: len(v) for k, v in r["tasks"].items()},
                         qualification=r["qualification"]), indent=2))
