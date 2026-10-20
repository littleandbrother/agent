#!/usr/bin/env python3
"""Register distinct task contracts before either executor starts."""
from pathlib import Path
import datetime
import json
import shutil

ROOT = Path(__file__).resolve().parents[3]
DOCS = Path(__file__).resolve().parent
BASE = json.loads((DOCS / "baseline-v1/manifest.json").read_text())
PREFIX = "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/"
RUNTIME = str(Path.home() / ".local/share/bf-agent-architecture-v2/parallel-campaign-20261019")


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def contract(feature_id, owner, hypothesis, claim, falsifier, paths, tests, negatives, command, artifacts):
    return {"schema_version": "battery-world-feature-v1", "id": feature_id, "owner": owner,
        "status": "in-progress", "source_baseline": BASE["id"],
        "authority": "Direct user authorization in 01a11b01-a75e-75c2-81c3-7d152a24f15a verified by S0; finite first batch only; no commit/push.",
        "hypothesis": hypothesis, "paper_claim": claim, "falsifier": falsifier,
        "owned_paths": paths, "schema_changes": ["campaign-task-v1", "campaign-result-v1"],
        "targeted_tests": tests, "negative_controls": negatives,
        "reproducible_command": command, "output_artifact": artifacts,
        "cost_cap": "Existing unlimited cumulative money/time authorization retained. This executor performs a finite deterministic development list, zero paid model requests, zero native EDA/hardware writes, <= 500 MB outputs. Paid work is dispatched by S0 after a model-session slot is free.",
        "claim_boundary": "Public development computational evidence; datasheet bounds are not calibrated device models. No hardware, unseen-mechanism generalization or Agent benefit claim.",
        "stop_condition": "Stop on baseline/content drift, reference disagreement, unavailable model domain, hidden evaluator exposure, < 5 GB free, unknown native state or need for an out-of-scope source edit. Return the exact blocker; retain failures."}


A = contract("BFA-045-ar-b-reference", "campaign-a",
    "An explicit single-light-source A/R service chain and a separate transient B model can be qualified with independent energy, event and receiver checks before an Agent is attached.",
    "One source-bound A/R computational candidate; B public positive/negative qualification and declared physical-anchor limits.",
    "Independent integration or receiver disagrees; darkness is relabeled N/A; retention is counted as continued sensing; lux is converted to watts without an IV assumption; a nominal device is presented as measured.",
    [PREFIX + "ar.py", PREFIX + "b.py", "scripts/campaign_reference.py", "tests/agentlab/test_campaign_reference.py",
     "configs/studies/parallel-20261019/reference/", "docs/research/parallel-20261019/reference/"],
    ["zero-storage startup and valid digital temperature reception", "darkness and finite storage", "history retention vs continued sensing", "recovery upload and deduplication", "B cold pulse and volatile event-loss controls", "independent energy/event readback"],
    ["no source energy", "startup too late", "stale sample", "volatile event lost on reset", "duplicate upload", "unavailable calibration -> UNKNOWN"],
    "PYTHONPATH=packages/python/bfworld/src python3 scripts/campaign_reference.py --output <new-absolute-directory>",
    "docs/research/parallel-20261019/reference/")

B = contract("BFA-046-interface-interventions", "campaign-b",
    "Two currently successful systems may share a verdict-level representation yet respond differently to the same legal design intervention; an executable observation may separate the pair at measured acquisition cost.",
    "A new structural development counterexample with independent reference, intervention outcomes, equal-information representation control and real observation costs; null format gain is allowed.",
    "Pair only rescales an existing template, current success differs, the intervention is not jointly legal, reference implementations disagree, or information/format controls see different facts.",
    [PREFIX + "interfaces.py", "scripts/campaign_interfaces.py", "tests/agentlab/test_campaign_interfaces.py",
     "configs/studies/parallel-20261019/interfaces/", "docs/research/parallel-20261019/interfaces/", "papers/interface-sufficiency-20261019/"],
    ["both systems pass before intervention", "same legal change yields different outcomes", "at least one static-sufficient negative control", "independent parser/integrator", "identical facts in text and structured views", "measured observation wall time/bytes and discovery-vs-selection labels"],
    ["pure additive static-sufficient task", "uninformative observation", "illegal patch", "same data different formatting", "tampered observation hash"],
    "PYTHONPATH=packages/python/bfworld/src python3 scripts/campaign_interfaces.py --output <new-absolute-directory>",
    "docs/research/parallel-20261019/interfaces/")

S0 = contract("BFA-047-method-reexecution", "campaign-s0",
    "A real global H prompt change can be evaluated only by replaying design decisions from task entry; exact-input physics cache reuse is compatible with fresh decisions and must be compared to conservative dependency invalidation and full response.",
    "Finite F1a/F1b/F4 development comparison; report actual H changes, fresh decisions, all costs, failures, and no-update outcomes without claiming RSI.",
    "H1 only rescored an old D; conditions use different task/evaluator/backend/cache starts; costs omit failures or UNKNOWN; stale trajectory determines the new design; method selection consumes final-test feedback.",
    [PREFIX + "__init__.py", PREFIX + "common.py", PREFIX + "reexecution.py", "scripts/campaign_methods.py", "tests/agentlab/test_campaign_methods.py",
     "configs/studies/parallel-20261019/shared/", "configs/studies/parallel-20261019/methods/", "docs/research/parallel-20261019/shared/",
     "docs/research/parallel-20261019/methods/", "papers/method-reexecution-20261019/", "PROJECT.yaml", "project/features/",
     "docs/PROGRESS.md", "docs/SESSION-HANDOFF.md"],
    ["D vs H vs G typed interventions", "fixed-trajectory vs dependency vs boundary vs full vs exact response cache", "global H restart from entry", "same method task/backend/info/resources across arms", "all parent/child usage and UNKNOWN accounting", "protected-state preservation"],
    ["unchanged exact-input cache hit", "feedback dependency expands to full", "changed prompt with no changed decisions", "infeasible task", "missing provider usage", "cache warm-start mismatch"],
    "PYTHONPATH=packages/python/bfworld/src python3 scripts/campaign_methods.py <mode>",
    "docs/research/parallel-20261019/methods/")
S0["cost_cap"] = "Deterministic qualification first; then two fixed H conditions x two full attempts = four paid development trials, each <= 80 parent+child requests, <= 4 distinct physical execution inputs, <= 1200 s decision wall time. No automatic resampling. Native jobs serial and globally locked. At most three active model sessions including S0 and executors. Provider identity/usage prerequisite. Existing cumulative unlimited authorization retained."

def main():
    material = json.loads((DOCS / "baseline-v1/materialization.json").read_text())
    assert all(w["status"] == "PASS" for w in material["workspaces"])
    # Assert lexical ownership separation before registration. Shared paths are S0-owned.
    for left, right in [(A, B), (A, S0), (B, S0)]:
        for x in left["owned_paths"]:
            for y in right["owned_paths"]:
                assert not (x == y or x.startswith(y.rstrip("/") + "/") or y.startswith(x.rstrip("/") + "/")), (x, y)
    plans = {"a": A, "b": B, "s0": S0}
    tasks = [
        {"id": "AR-cold", "mechanism": "zero-storage startup and digital temperature reception", "partition": "public-development", "role": "A/R-1 reference and F1a input"},
        {"id": "AR-light-dark", "mechanism": "energy arrival order, storage and loss of power", "partition": "public-development", "role": "A/R-2 service failure and E2"},
        {"id": "AR-history", "mechanism": "NVM retention distinct from continued sampling and time knowledge", "partition": "public-development", "role": "A/R-2/3 independent requirements"},
        {"id": "AR-upload", "mechanism": "gateway recovery, acknowledgment and deduplication", "partition": "public-development", "role": "A/R-2/3 service completion"},
        {"id": "B-pulse", "mechanism": "single actuation cold start and transient load", "partition": "public-development", "role": "B positive/negative qualification"},
        {"id": "B-event-memory", "mechanism": "event lost across reset or delayed energy", "partition": "public-development", "role": "B structural event/state control"}]
    protocol = {"schema_version": "bf-research-campaign-contract-v1", "baseline": BASE["id"], "tasks": tasks,
        "formal_test_status": "NOT_CREATED; no public development task may later be relabeled unseen",
        "selection_status": "Protocol prepared only; fresh selection and final tasks must be independently frozen before a transfer claim",
        "development_exposure": "S0 and both research executors see the public development mechanisms; shared across both papers",
        "cache_rule": "Same initial immutable input cache for paired methods; construction and warm-up charged explicitly; unchanged valid successful solves reused",
        "resource_protocol": S0["cost_cap"], "native_lock": RUNTIME + "/locks/native-resource.lock",
        "protected": ["Baseline", "current Demo", "ten original Pi sessions/projects", "all historical billing and UNKNOWN", "BFA-043 native project"],
        "no_original_owner_resume": True, "require_reference_before_agent": True,
        "papers": {"P1": "interface adequacy under legal intervention; observation choice/construction", "P2": "D/H/G separation, F1a/F1b/F4 and later F5"}}
    save(DOCS / "campaign-contract.json", protocol)
    save(DOCS / "ownership.json", {"baseline": BASE["id"], "shared_state_writer": "campaign-s0", "owners": list(plans.values())})
    for role, feature in plans.items():
        work = ROOT / f"workbench/bf-campaign-{role}-20261019/battery-world"
        save(work / f"project/features/{feature['id']}/feature.yaml", feature)
        save(work / "configs/studies/parallel-20261019/shared/campaign-contract.json", protocol)
        save(work / "configs/studies/parallel-20261019/shared/source-baseline.json", {k: BASE[k] for k in ["id", "head", "head_tree", "manifest_sha256"]})
        package = work / PREFIX
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text('"""Finite public development campaign; no hardware claims."""\n')
        # One active feature per physical workspace, with shared global ownership
        # declared separately in the root authority.
        p = work / "PROJECT.yaml"
        text = p.read_text().replace("active_feature: null", "active_feature: " + feature["id"])
        p.write_text(text)
        save(DOCS / f"{feature['id']}.json", feature)
    p = ROOT / "feature_list.json"
    state = json.loads(p.read_text()); c = state["bf_parallel_campaign_20261019"]
    c["features"][0]["status"] = "complete"
    c["features"][0]["evidence"] = [str(DOCS / "baseline-v1/manifest.json"), str(DOCS / "baseline-v1/materialization.json")]
    c["features"].extend([A, B, S0]); c["status"] = "first-batch-in-progress"; c["baseline"] = BASE["id"]
    c["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save(p, state)
    for role in plans:
        (Path(RUNTIME) / role).mkdir(parents=True, exist_ok=True)
    print(json.dumps({"baseline": BASE["id"], "registered": [f["id"] for f in plans.values()], "tasks": len(tasks)}, indent=2))


if __name__ == "__main__":
    main()
