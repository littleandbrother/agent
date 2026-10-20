#!/usr/bin/env python3
"""Explicit v1.1 recovery dispatcher; original attempts stay immutable."""
import importlib.util
import json
import os
from pathlib import Path
import sys

PLAN = Path(__file__).resolve().parent
ROOT = PLAN.parents[3]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
OUT = Path.home() / ".local/share/bf-phase4-20261020"
PROFILE = Path.home() / ".local/share/bf-campaign-20261019-s0/profile.json"
p = json.loads(PROFILE.read_text())
for k, v in p["paths"].items():
    os.environ["BF_" + k] = v
os.environ.update(BF_RUNTIME_ROOT=p["runtime_root"], BF_RUNTIME_CONFIG=p["configuration"],
                  BF_DEVELOPMENT_PROFILE=str(PROFILE), PYTHONDONTWRITEBYTECODE="1",
                  PI_CODING_AGENT_DIR=str(Path(p["home"]) / "pi-config"))
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.campaign20261019 import phase4_methods as m
from bfworld.agentlab.campaign20261019 import phase2_methods as hm
from bfworld.agentlab.campaign20261019 import phase4_interfaces as o
from bfworld.agentlab.campaign20261019.phase4 import DigitalBEngine, DigitalOEngine, load
from bfworld.agentlab.campaign20261019.phase1 import digest, file_hash, seal


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


r = module("phase4_dispatch_runner", APP / "scripts/campaign_phase4.py")
protocol = load(PLAN / "protocol-v1.1.json")
recoveries = protocol["recovery_attempts"]
parents = m.frozen_parent_methods()
H0 = parents["H0"]["method_text"]


def get(episode):
    path = OUT / "episodes" / recoveries.get(episode, episode) / "episode-result.json"
    return load(path) if path.exists() else None


def usage(result):
    account = result["accounting"]
    if account["unknown_or_missing_usage"]:
        raise ValueError("UNKNOWN_USAGE_STOP")
    return {"requests": account["requests"], "wall_s": result["wall_seconds_total"],
            "usd": account["settled_charge_upper_bound_usd"], "status": "SETTLED"}


def run(spec, payload, **kw):
    existing = get(spec["id"])
    if existing is not None:
        if existing["accounting"]["unknown_or_missing_usage"]:
            raise ValueError("UNKNOWN_USAGE_STOP")
        return existing
    if spec["id"] in recoveries:
        original_id = spec["id"]
        if payload != load(OUT / "episodes" / original_id / "participant-payload.json"):
            raise ValueError("RECOVERY_PARTICIPANT_PAYLOAD_CHANGED")
        spec = next(x for x in protocol["episodes"] if x["id"] == recoveries[original_id])
    result = r.run_episode(spec, payload, **kw)
    events = OUT / "episodes" / spec["id"] / "gateway/gateway-events.jsonl"
    host_errors = []
    for line in events.read_text().splitlines():
        event = json.loads(line)
        error = event.get("data", {}).get("error", "")
        if event["kind"] == "tool_failed" and (error.startswith("KeyError:") or
                any(x in error for x in ("HISTORICAL_", "CACHED_RESULT_TAMPERED", "FROZEN_SOURCE_CHANGED"))):
            host_errors.append(error)
    if host_errors:
        state_path = PLAN.parent / "phase-state.json"
        state = load(state_path)
        state.update(paid_dispatch_allowed=False, new_dispatch_allowed=False,
                     status="phase4_v11_held_on_new_host_error")
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        raise ValueError("AMENDED_HOST_ERROR_STOP:" + repr(host_errors))
    return result


def engine(spec):
    if spec["world"].startswith(("o0-", "p4-o-")):
        fixed = None
        case = load(protocol["O_tasks"][spec["world"]]["input_path"])
        if spec.get("condition") == "fixed-periodic":
            fixed = o.fixed_periodic(case)["candidate"]
        elif spec.get("condition") == "rich-state":
            fixed = o.rich_state(case)["candidate"]
        return DigitalOEngine(protocol["O_tasks"], o, fixed_candidate=fixed)
    checker = module("phase4_independent_B", APP / "scripts/campaign_reference.py")
    return DigitalBEngine(APP, r.HIST, protocol["B_tasks"], checker)


def d_payload(spec, method):
    return {"goal": "Design and judge the registered battery-free service using frozen facts and the assigned procedure.",
            "instruction": method + "\n\nUse bf_phase4 inspect and every source_id before design submission. "
                "Only the typed candidate fields may vary. Check at most two distinct candidates, then submit one with "
                "service_judgment PASS, FAIL or UNKNOWN and your source-bound reason. Reference truth and final service "
                "evaluation are host-side. A returned record is an observation, not a service acceptance label. "
                "Do not claim a complete unprojected trace when a response declares first-six-last-six projection.",
            "parent_files": []}


def proposal_payload(kind, procedure=None):
    facts = {"frozen_parents": parents, "public_experience": m.model_history_packet()}
    if kind == "H":
        facts["assigned_proposal_procedure"] = procedure
        instruction = parents["immutable_proposal_prefix"] + "\n\n" + procedure
    else:
        instruction = ("Inspect the same frozen H0, G0 and public phase2/3 experiences. Propose one prospective "
            "change to G0's natural-language H proposal procedure, or no-update. Change only G. Do not return an H "
            "or D submission, change budgets/selection/tools/model/physics, use O0 or final inputs, or declare acceptance. "
            "Your procedure will generate independent H descendants from the same H0/history. It is not a retained default.")
    return {"goal": "Form one model-authored G1 proposal procedure." if kind == "G" else "Propose one independent procedural H descendant.",
            "instruction": instruction + "\nUse bf_phase4 inspect, then submit the typed proposal or explicit no-update. No design checks are available.",
            "facts": facts, "parent_files": []}


def semantic(episode):
    path = OUT / "semantic-audit.json"
    audit = load(path) if path.exists() else {}
    if episode not in audit:
        raise ValueError("ACTUAL_PROPOSAL_REQUIRES_INDEPENDENT_SEMANTIC_REVIEW:" + episode)
    entry = audit[episode]
    submitted = OUT / "episodes" / episode / "scientific/submission.json"
    if entry["submission_sha256"] != file_hash(submitted):
        raise ValueError("REVIEWED_PROPOSAL_CHANGED")
    return entry


def g1():
    path = OUT / "G1-freeze.json"
    if not path.exists():
        raise ValueError("G1_FORMATION_NOT_REVIEWED_AND_FROZEN")
    return load(path)


def descendant(spec):
    return get(f"L{spec['lineage']}-{spec['arm']}-h{spec['child']}-proposal")


def selection_row(lineage, arm, child):
    proposal_id = f"L{lineage}-{arm}-h{child}-proposal"
    proposed = get(proposal_id)
    if proposed is None:
        notice = load(OUT / "not-dispatched" / (proposal_id + ".json"))
        return {"descendant_index": child, "proposal": {}, "proposal_status": notice["status"],
                "semantic_H_eligible": False, "proposal_usage": {"requests": 0, "wall_s": 0, "usd": 0, "status": "SETTLED"}, "selection": []}
    raw = proposed.get("external_result", {}).get("raw_proposal", {})
    accepted = proposed["status"] == "ACTUAL_PROSPECTIVE_SUBMITTED"
    eligible = semantic(proposal_id)["eligible"] if accepted else False
    records = []
    for task in ("b-pulse-fast", "b-volatile-reset"):
        result = get(f"L{lineage}-{arm}-h{child}-selection-{task}")
        if result:
            sub = result.get("external_result", {})
            records.append({"task_id": task, "service_status": sub.get("execution", {}).get("complete_service", "INCOMPLETE"),
                            "wrong_service_judgment": bool(sub.get("wrong_service_judgment", False)), "usage": usage(result)})
    return {"descendant_index": child, "proposal": raw,
            "proposal_status": "SUBMITTED" if accepted else proposed["status"],
            "semantic_H_eligible": eligible, "proposal_usage": usage(proposed), "selection": records}


def freeze_selection():
    expected = [s for s in protocol["episodes"] if s["stage"] == "selection" and not s.get("recovery_of")]
    if len(expected) != 30 or any(get(s["id"]) is None for s in expected):
        raise ValueError("ALL_THIRTY_CANONICAL_SELECTION_CELLS_REQUIRED")
    selected = {}
    for lineage in (1, 2, 3):
        for arm in ("G0", "G1"):
            value = m.select_descendant([selection_row(lineage, arm, child) for child in (1, 2)])
            seal(OUT / "selections" / f"L{lineage}-{arm}.json", value)
            selected[f"L{lineage}-{arm}"] = {k: value[k] for k in
                ("status", "selected_descendant_index", "selected_H_text", "selected_H_sha256")}
    seal(OUT / "selected-methods.json", selected)
    seal(OUT / "final-selection-freeze.json", {"status": "ALL_SIX_ARMS_FROZEN", "selected_methods_sha256": digest(selected),
          "adapter_revision": "1.1", "amendment_id": protocol["amendment_id"],
          "canonical_selection_attempts": {s["id"]: get(s["id"])["episode"] for s in expected},
          "final_results_consulted": False, "all_final_episodes_not_started": not any(
              (OUT / "episodes" / s["id"]).exists() for s in protocol["episodes"] if s["stage"] == "final")})
    print(json.dumps({k: {x: v[x] for x in ("status", "selected_descendant_index")} for k, v in selected.items()}), flush=True)


def skip(spec, reason):
    path = OUT / "not-dispatched" / (spec["id"] + ".json")
    if not path.exists():
        seal(path, {"spec": spec, "status": "NOT_DISPATCHED_PARENT_INELIGIBLE", "reason": reason,
                    "actual_provider_requests": 0, "cost_scope": "No participant allocated; parent costs retained separately"})
    print(json.dumps({"episode": spec["id"], "status": "NOT_DISPATCHED_PARENT_INELIGIBLE"}), flush=True)


def main(stage, only=None):
    if stage == "recovery":
        for original_id in recoveries:
            main("selection", original_id)
        return
    if stage not in ("selection", "final", "freeze-selection"):
        raise ValueError("NO_NEW_G_H_OR_O0_FORMATION_IN_CACHE_AMENDMENT")
    if stage == "freeze-selection":
        freeze_selection()
        return
    for spec in protocol["episodes"]:
        if spec.get("recovery_of"):
            continue
        if spec["stage"] != stage or (only and spec["id"] != only):
            continue
        if stage == "formation":
            schema = m.g_proposal_schema()
            schema["oneOf"][0]["properties"]["proposal_procedure"]["maxLength"] = 6000
            run(spec, proposal_payload("G"), proposal_schema=schema, normalize=m.validate_improver)
        elif stage == "proposal":
            G = parents["G0"]["proposal_procedure"]
            if spec["arm"] == "G1":
                formed = g1()
                if not formed["eligible"]:
                    skip(spec, "G1 formation was invalid/no-update/incomplete; no replacement formation")
                    continue
                G = formed["proposal_procedure"]
            run(spec, proposal_payload("H", G), proposal_schema=hm.tool_schema(), normalize=hm.validate_method)
        elif stage == "selection":
            method = H0
            if spec.get("arm"):
                proposed = descendant(spec)
                if proposed is None or proposed["status"] != "ACTUAL_PROSPECTIVE_SUBMITTED":
                    skip(spec, "H proposal unavailable or incomplete")
                    continue
                if not semantic(proposed["episode"])["eligible"]:
                    skip(spec, "H semantic/no-update rejection retained")
                    continue
                method += "\n\n" + proposed["external_result"]["proposal"]["method_text"]
            run(spec, d_payload(spec, method), engine=engine(spec))
        elif stage == "final":
            selected = load(OUT / "selected-methods.json")
            method = H0 if not spec.get("arm") else selected[spec["arm_id"]]["selected_H_text"]
            payload = d_payload(spec, method)
            payload["parent_files"] = [str(OUT / "selected-methods.json"), str(OUT / "final-selection-freeze.json")]
            run(spec, payload, engine=engine(spec))
        elif stage == "O-transfer":
            method = H0
            case = load(protocol["O_tasks"][spec["world"]]["input_path"])
            if spec["condition"] == "fixed-periodic":
                method += "\n\n" + o.fixed_periodic(case)["method_text"]
            elif spec["condition"] == "rich-state":
                method += "\n\n" + o.rich_state(case)["method_text"]
            run(spec, d_payload(spec, method), engine=engine(spec))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
