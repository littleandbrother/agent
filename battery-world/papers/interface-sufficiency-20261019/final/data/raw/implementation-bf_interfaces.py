"""BF interface protocol preparation. No provider, native dispatch or new solve.

The participant export is an allowlisted, label-separated *development* input,
not a security sandbox or an unseen evaluation. A future kernel must mount one
trial directory alone and own the cumulative budget/usage ledger.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import re
import shutil
import time
from pathlib import Path
from typing import Any

from . import interfaces as old


BASELINE = "CB2-61f3ff75e94647915c87b3746c3bc5e12a374409efe0642e6d3e3980fa2a672a"
PROTOCOL = "configs/studies/phase1-20261020/interfaces/protocol.json"
OUTPUT = "docs/research/phase1-20261020/interfaces"
LEGACY = "docs/research/parallel-20261019/interfaces/data/IF-7412532c4a6ab7a5879e"
MODULE = "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/bf_interfaces.py"
OLD_MODULE = "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/interfaces.py"
FORBIDDEN_KEYS = frozenset({
    "expected", "expected_verdict", "reference_verdict", "ground_truth", "label",
    "labels", "target_label", "correct", "required_fields", "target_observation",
    "relevant_fields", "answer", "answer_key", "proposed_verdict",
})
SUMMARY = ("Judge the announced legal design change using PASS, FAIL, or UNKNOWN. "
           "The models are ideal computational assumptions, not measured devices.")
UNITS = {"time": "s", "energy": "uJ", "capacitance": "uF", "voltage": "V",
         "power": "uW", "pending": "event identifier or null", "retention": "boolean"}
TOOLS = [
    {"operation": "read_current", "arguments": {},
     "returns": "saved current task, design and trajectory"},
    {"operation": "read_spec", "arguments": {},
     "returns": "complete declarative actual-world parameters, laws and assumptions"},
    {"operation": "read_raw", "arguments": {},
     "returns": "complete raw model definition and saved current output"},
    {"operation": "query_model", "arguments": {"patch": "public legal design patch"},
     "returns": "saved model response for the announced patch; cache miss abstains",
     "execution_mode": "saved-response-only; no new solve in this phase"},
]
RESOURCES = {"observation_calls_per_future_trial": 3,
             "observation_payload_bytes_per_future_trial": 262144,
             "wall_s_per_future_trial": 30, "output_tokens_per_future_trial": 4096,
             "paid_requests_admitted_now": 0, "native_dispatches_admitted_now": 0,
             "enforcement_now": "one offline replay request; cumulative ledger requires future kernel"}


class ProtocolError(ValueError):
    """Fail closed on scope, information, identity or evidence mismatch."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def binding(raw: bytes) -> dict:
    return {"sha256": sha(raw), "bytes": len(raw)}


def safe_path(root: Path, name: str) -> Path:
    """Reject traversal, absolute paths, and symlinks in every path component."""
    rel = Path(name)
    if rel.is_absolute() or not rel.parts or any(x in ("..", ".") for x in rel.parts):
        raise ProtocolError("Unsafe relative path")
    at = root
    for part in rel.parts:
        at = at / part
        if at.is_symlink():
            raise ProtocolError("Symlink is outside the artifact contract")
    if not at.resolve().is_relative_to(root.resolve()):
        raise ProtocolError("Path escapes artifact root")
    return at


def read_json(path: Path) -> Any:
    if path.stat().st_size > 2_000_000:
        raise ProtocolError("Unexpectedly large protocol artifact")
    return json.loads(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(json.dumps(value, indent=2, sort_keys=True,
                             ensure_ascii=False, allow_nan=False).encode() + b"\n")


def assert_public(value: Any) -> None:
    """Check structured keys and private paths, not legitimate physical inference.

    Current verdicts and model response verdicts are legal observations. Physical
    parameters may imply the target. This guard detects administrative leakage;
    it cannot detect arbitrary natural-language steganography.
    """
    if isinstance(value, dict):
        if FORBIDDEN_KEYS.intersection(value):
            raise ProtocolError("Evaluator or relevance metadata in participant input")
        for child in value.values():
            assert_public(child)
    elif isinstance(value, list):
        for child in value:
            assert_public(child)
    elif isinstance(value, str):
        if re.search(r"(^|[/\\])(?:evaluator|private|answer-key)(?:[/\\]|$)", value):
            raise ProtocolError("Private path in participant input")
        if any(x in value for x in ("low-clamp", "high-clamp", "IF-7412532c4a6ab7a5879e")):
            raise ProtocolError("Historical case identifier in participant input")
    canonical(value)  # reject NaN and non-JSON payloads


def load_protocol(root: Path) -> dict:
    value = read_json(safe_path(root, PROTOCOL))
    if value.get("schema_version") != "bf-interface-phase1-protocol-v1" or value.get("baseline") != BASELINE:
        raise ProtocolError("Unknown phase-one protocol/baseline")
    for name, expected in value["inputs"].items():
        if binding(safe_path(root, name).read_bytes()) != expected:
            raise ProtocolError("Frozen source changed: " + name)
    return value


def resource_gate(root: Path, profile_path: Path, action: str,
                  *, free_bytes: int | None = None) -> dict:
    protocol = load_protocol(root)
    raw = profile_path.read_bytes()
    profile = json.loads(raw)
    if sha(raw) != protocol["profile_sha256"]:
        raise ProtocolError("Registered development profile changed")
    if Path(profile["source_root"]).resolve() != root.resolve().parent:
        raise ProtocolError("Wrong workspace/profile owner")
    if (profile["baseline"]["manifest_sha256"] != protocol["baseline_manifest_sha256"]
            or profile["runtime_root"] != protocol["runtime_root"]):
        raise ProtocolError("Baseline/runtime identity mismatch")
    if profile["capabilities"] != {"model": False, "agent": False, "native": False}:
        raise ProtocolError("This protocol freezes all execution capabilities off")
    if action not in {"prepare", "verify", "replay"}:
        raise ProtocolError("Dispatch blocked: no model/native capability, provider usage or paid lease")
    # free_bytes is a deterministic test seam; CLI always reads the live filesystem.
    available = shutil.disk_usage(root).free if free_bytes is None else free_bytes
    cap = protocol["cost_cap"]
    required = cap["reserve_bytes"] + cap["whole_batch_peak_bytes"]
    if available < required:
        raise ProtocolError("Storage gate: less than reserve plus whole-batch peak")
    return {"schema_version": "bf-e4-resource-gate-v1", "status": "PASS",
            "action": action, "profile_sha256": sha(raw), "baseline": BASELINE,
            "free_bytes": available, "required_free_bytes": required,
            "paid_requests": 0, "native_dispatches": 0,
            "model_trial": "NOT_RUN", "capabilities": profile["capabilities"]}


def recheck_legacy(root: Path) -> dict:
    """Readback + parsing only. Do not call any numerical/event solver."""
    capsule = safe_path(root, LEGACY)
    audit = old.verify_run(capsule)
    result = read_json(capsule / "result.json")
    groups: dict[tuple, list] = {}
    for row in result["packets"]:
        facts, summary = old.parse_packet(safe_path(capsule, row["file"]).read_bytes(), row["format"])
        groups.setdefault((row["pair"], row["world"], row["information"]), []).append((facts, summary))
    if len(groups) != 8 or any(len(v) != 2 or canonical(v[0]) != canonical(v[1]) for v in groups.values()):
        raise ProtocolError("Historical 16-packet parity failed")
    if not all(x["prediction"] == x["reference_verdict"] for x in result["static_sufficient_rows"]):
        raise ProtocolError("Saved rich-static negative control changed")
    if not all(x["static"] == x["reference"] for x in result["additive_static_rows"]):
        raise ProtocolError("Saved additive negative control changed")
    return {"status": "PASS", "legacy_seal_audit": audit, "packet_files": 16,
            "format_parity_pairs": 8, "saved_reference_checks": len(result["reference_checks"]),
            "saved_max_reference_error_uj": result["reference_max_error_uj"],
            "static_sufficient_saved_checks": len(result["static_sufficient_rows"]),
            "additive_saved_checks": len(result["additive_static_rows"]),
            "solver_reexecutions": 0, "method": "hash/readback + parse/decision audit"}


def public_raw(raw: dict) -> tuple[dict, list[str]]:
    """Preserve every physical value, law, current sample and alternative world.

    Only historical case IDs/names are stripped. The list of alternative worlds
    and even the public development grids remain in the complete-raw baseline.
    """
    value = copy.deepcopy(raw)
    removed = ["pair.id", "world.name"]
    value["pair"].pop("id")
    value["world"].pop("name")
    for i, world in enumerate(value["pair"]["worlds"]):
        world.pop("name")
        removed.append(f"pair.worlds[{i}].name")
    assert_public(value)
    return value, removed


def rich_facts(raw: dict) -> dict:
    pair, world, current = raw["pair"], raw["world"], raw["current"]
    facts = old.sufficient_facts(pair, world, current)
    facts["bf_model"] = {
        "law": raw["law"], "actual_world": copy.deepcopy(world),
        "task": copy.deepcopy(pair["task"]), "design": copy.deepcopy(pair["design"]),
        "legal_domain": copy.deepcopy(pair["legal_domain"]), "units": UNITS,
        "assumptions": (["ideal capacitor and clamp", "all input precedes service",
                         "no leakage or intervening workload", "minimum rail is a service reserve"]
                        if world["kind"] == "clamp" else
                        ["forced on/off schedule", "ideal event capture when powered",
                         "reset retention is declared", "no physical NVM write or startup model"]),
        "evidence_type": raw["evidence_type"],
    }
    assert_public(facts)
    return facts


def model_source(root: Path) -> bytes:
    """Export the unchanged numerical model bodies, without invoking them."""
    source = safe_path(root, OLD_MODULE).read_text()
    names = {"DomainError", "number", "changed_design", "_rail", "numeric_clamp",
             "event_program", "numeric_memory"}
    chunks = [ast.get_source_segment(source, n) for n in ast.parse(source).body
              if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    if len(chunks) != len(names):
        raise ProtocolError("Incomplete executable baseline extraction")
    header = ('"""Ideal public model; computational prediction, not independent qualification."""\n'
              'from __future__ import annotations\nimport copy, json, math, re, sys\n'
              'from typing import Any\nTOL = 1e-7\n\n')
    entry = '''
def predict(raw, patch):
    pair, world = raw["pair"], raw["world"]
    design = changed_design(pair, patch)
    fn = numeric_clamp if world["kind"] == "clamp" else numeric_memory
    return fn(pair, world, design, 0.001)

if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as src:
        raw = json.load(src)
    patch = json.loads(sys.argv[2]) if len(sys.argv) > 2 else raw["pair"]["patch"]
    print(json.dumps(predict(raw, patch), sort_keys=True, allow_nan=False))
'''
    out = (header + "\n\n".join(chunks) + "\n" + entry).encode()
    compile(out, "bf_public_model.py", "exec")  # syntax only; no model execution
    return out


def mechanism_map(root: Path, result: dict) -> dict:
    reference = read_json(safe_path(root, "docs/research/parallel-20261019/reference/results.json"))
    conditions = read_json(safe_path(root, "configs/studies/parallel-20261019/reference/conditions.v1.json"))
    b_rows = [row for row in reference["cases"] if row["id"].startswith("b-")]
    if len(b_rows) != 7 or any(row["verdicts"]["physical_qualification"] != "UNKNOWN" for row in b_rows):
        raise ProtocolError("Historical BF evidence scope changed")
    return {
        "schema_version": "bf-mechanism-map-v1", "solver_reexecutions": 0,
        "structural_witnesses": [
            {"pair": result["pairs"][0]["pair"], "bf_mechanism": "storage saturation before a timed service",
             "causal_chain": "capacitance -> energy ceiling -> spill -> usable reserve -> service",
             "missing_current_information": "unexcited upper rail clamp",
             "observable_relation": "energy headroom over the legal capacitance domain",
             "consumer": "service-energy transaction with minimum-rail reserve",
             "saved_cases": result["pairs"][0]["cases"],
             "boundary": "ideal transaction; no MCU boot or calibrated PMIC"},
            {"pair": result["pairs"][1]["pair"], "bf_mechanism": "pending event through power loss",
             "causal_chain": "outage -> reset -> volatile/retained pending -> later TX",
             "missing_current_information": "reset retention when no reset has occurred",
             "observable_relation": "event continuity under a legal power schedule",
             "consumer": "event-program transmit condition",
             "saved_cases": result["pairs"][1]["cases"],
             "boundary": "forced gate and ideal retention; no free powered NVM write"}],
        "b_reference": {"base": conditions["b_base"],
                        "case_patches": conditions["b_cases"], "saved_outcomes": b_rows,
                        "consumer_source": "campaign20261019/b.py:simulate_b",
                        "mechanisms": [
                            {"cases": ["b-pulse-fast", "b-pulse-slow", "b-late-energy"],
                             "relation": "same 150 uJ, different source order and deadline access",
                             "boundary": "fast/slow both pass; late reception at 0.1058 s misses 0.1 s"},
                            {"cases": ["b-pulse-fast", "b-esr-fail", "b-no-energy"],
                             "relation": "ready/off energy thresholds, boot cost and ESR*TX-current droop",
                             "boundary": "no-energy voltage gate is vacuous; event service fails"},
                            {"cases": ["b-latched-reset", "b-volatile-reset"],
                             "relation": "same 210 uJ and shunt, different event retention through reset",
                             "boundary": "passive mechanical latch is an explicit ideal assumption"}],
                        "feedback_scope": "load -> stored energy/loaded rail -> reset -> program; prescribed source has no source-response feedback",
                        "control_scope": "predeclared_control PASS is expected-control agreement, not service PASS",
                        "physical_qualification": "UNKNOWN"},
        "claim_boundary": "BF-specific computational mechanisms; no extra physical solve, discovery or hardware result"}


def e5_contract() -> dict:
    return {
        "schema_version": "bf-e5-implementation-contract-v1", "status": "FROZEN_CONTRACT_ONLY",
        "e5_1": "Agent selects a legal observation from a general catalogue; no supplied relevant-field labels",
        "e5_2": "Agent proposes a missing BF relation, acquisition and executable observation; no supplied expression",
        "initial_visible": ["task", "current interface", "legal interventions", "general tools, schemas and costs"],
        "evaluator_only": ["target relation", "relevant fields", "expected service", "independent qualification controls"],
        "stages": [
            {"stage": "discover", "requires": ["Agent/provider/run identity", "usage receipt", "visible-input hash",
                                                  "proposed BF relation and applicability domain"],
             "falsifier": "researcher supplied target fields or expression"},
            {"stage": "propose_observation", "requires": ["legal experiment or data source", "units and schema",
                                                             "source/code hash", "wall/byte/solver/model budget"],
             "falsifier": "unsupported domain or observation that cannot distinguish the proposed relation"},
            {"stage": "acquire", "requires": ["immutable observation artifact", "input/source/code hashes",
                                                 "actual costs including failed/UNKNOWN attempts"],
             "falsifier": "advice or an unbound value presented as measurement"},
            {"stage": "qualify", "requires": ["separate reference implementation", "frozen public domain",
                                                 "uninformative, tampered, out-of-domain and static-rich controls"],
             "falsifier": "self-check only, evaluator leakage or post-outcome tuning"},
            {"stage": "consume", "requires": ["kernel-registered real consumer", "full consumer input hash",
                                                 "observation input edge and execution hash", "independent service result"],
             "falsifier": "echo, log-only use, scoring receipt or self-signed consumer receipt"},
            {"stage": "decide", "requires": ["outcome-blind next BF judgment or design decision", "scope/UNKNOWN retained"],
             "falsifier": "current-task repair relabeled transfer or recursion"}],
        "real_consumer_boundary": {
            "candidate": "campaign20261019/b.py:simulate_b (loaded rail/reset/event program)",
            "adapter_status": "NOT_REGISTERED; requires S0/kernel integration in a later feature",
            "dataflow": "qualified relation artifact -> typed parameter/constraint -> real BF consumer input -> execution -> independent service check",
            "trust": "external kernel registry; participant-supplied registry or self-declared actor is insufficient",
            "causal_benefit": "requires a separate frozen with/without-observation comparison; schema acceptance alone proves no gain"},
        "construction_baselines": ["human-required-field selector", "researcher-specified headroom AST/compiler"],
        "status_by_claim": {"genuine_agent_discovery": "NOT_RUN", "independent_new_qualification": "NOT_RUN",
                            "real_consumer_trial": "NOT_RUN", "transfer": "NOT_TESTED", "recursive_improvement": "NOT_RUN"},
        "negative_controls": ["static-rich already sufficient", "uninformative observation", "tampered hash",
                              "out-of-domain observation", "self-signed consumer", "researcher expression as discovery"],
        "validator_boundary": "structural admission against external authority, not execution or behavioral proof"}


def validate_discovery(submission: dict, authority: dict | None = None) -> dict:
    """Validate a future receipt against independently supplied kernel authority.

    This phase installs no authority/consumer adapter. Unit tests may supply
    synthetic registries; CONTRACT_VALID in such a fixture is not an experiment.
    """
    if authority is None:
        raise ProtocolError("CONSUMER_ADAPTER_NOT_REGISTERED; real E5 trial NOT_RUN")
    proposal = submission["proposal"]
    if proposal.get("actor") != "agent" or proposal.get("mode") not in {"selection", "construction"}:
        raise ProtocolError("Human construction is a baseline, not Agent discovery")
    assert_public(proposal)
    run = authority.get("agent_runs", {}).get(proposal.get("run_id"))
    if not run or not run.get("usage_available") or not run.get("provider") or not run.get("model"):
        raise ProtocolError("Missing trusted Agent/backend/usage identity")
    if run.get("proposal_sha256") != sha(canonical(proposal)) or run.get("visible_inputs_sha256") != proposal.get("visible_inputs_sha256"):
        raise ProtocolError("Proposal/visible-input provenance mismatch")
    required = {"bf_relation", "units", "domain", "acquisition", "budget", "code_sha256"}
    if not required.issubset(proposal) or not all(proposal[x] for x in required):
        raise ProtocolError("Incomplete BF observation proposal")
    observation = submission["observation"]
    if observation.get("sha256") != sha(canonical(observation.get("payload"))):
        raise ProtocolError("Observation digest mismatch")
    acquired = authority.get("observations", {}).get(observation["sha256"])
    if (not acquired or acquired.get("receipt_sha256") != sha(canonical(observation))
            or observation.get("code_sha256") != proposal["code_sha256"]
            or not observation.get("input_sha256") or not observation.get("source_sha256")):
        raise ProtocolError("Trusted acquisition/source/input/code/cost receipt missing")
    if observation.get("units") != proposal["units"] or observation.get("domain") != proposal["domain"]:
        raise ProtocolError("Observation units/domain mismatch")
    costs = observation.get("costs", {})
    for key in ("wall_s", "payload_bytes", "solver_runs", "model_requests"):
        actual, cap = costs.get(key), proposal["budget"].get(key)
        if (isinstance(actual, bool) or not isinstance(actual, (int, float))
                or not math.isfinite(actual) or actual < 0 or not isinstance(cap, (int, float))
                or isinstance(cap, bool) or not math.isfinite(cap) or actual > cap):
            raise ProtocolError("Missing or exceeded observation budget")
    if costs["payload_bytes"] != len(canonical(observation["payload"])):
        raise ProtocolError("Payload byte cost mismatch")
    q = authority.get("qualifications", {}).get(submission.get("qualification_id"))
    needed = {"uninformative", "tampered", "out_of_domain", "static_rich"}
    if (not q or q.get("observation_sha256") != observation["sha256"] or q.get("status") != "PASS"
            or q.get("domain") != proposal["domain"] or not q.get("reference_code_sha256")
            or q["reference_code_sha256"] == proposal["code_sha256"]
            or not needed.issubset(q.get("controls", {}))
            or any(q["controls"][k] != "PASS" for k in needed)):
        raise ProtocolError("Independent qualification/control evidence missing")
    receipt = submission["consumer"]
    consumer = authority.get("consumers", {}).get(receipt.get("consumer_id"))
    execution = authority.get("executions", {}).get(receipt.get("execution_id"))
    if (not consumer or consumer.get("purpose") != "bf-service" or not execution
            or proposal["bf_relation"] not in consumer.get("accepted_relations", [])
            or consumer.get("units") != proposal["units"]
            or consumer.get("code_sha256") != receipt.get("code_sha256")
            or execution.get("consumer_id") != receipt.get("consumer_id")
            or execution.get("code_sha256") != consumer["code_sha256"]
            or execution.get("input_sha256") != sha(canonical(receipt.get("full_input")))
            or receipt.get("input_sha256") != execution["input_sha256"]
            or execution.get("observation_sha256") != observation["sha256"]
            or receipt.get("full_input", {}).get("observation_sha256") != observation["sha256"]
            or execution.get("relation_input_edge") != proposal["bf_relation"]
            or not execution.get("independent_service_sha256")
            or execution.get("service_verdict") not in {"PASS", "FAIL", "UNKNOWN"}
            or not execution.get("decision_sha256")
            or execution.get("decision_mode") != "outcome-blind"):
        raise ProtocolError("Real consumer dataflow/execution/service binding missing")
    return {"status": "CONTRACT_VALID", "scope": "external-registry structural admission only",
            "service_verdict": execution["service_verdict"], "discovery_benefit": "NOT_ESTABLISHED"}


def _asset(trial: Path, name: str, raw: bytes) -> dict:
    path = safe_path(trial, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(raw)
    return {"path": name, **binding(raw)}


def verify_trial(trial: Path) -> dict:
    """Participant-only input gate: read one mounted trial, never evaluator data."""
    if trial.is_symlink() or any(p.is_symlink() for p in trial.rglob("*")):
        raise ProtocolError("Symlink in participant mount")
    manifest = read_json(safe_path(trial, "manifest.json"))
    assert_public(manifest)
    if manifest.get("schema_version") != "bf-e4-participant-v1":
        raise ProtocolError("Unknown participant schema")
    expected_files = {"manifest.json", manifest["packet"]["path"], *[a["path"] for a in manifest["assets"]]}
    actual_files = {str(p.relative_to(trial)) for p in trial.rglob("*") if p.is_file()}
    if expected_files != actual_files:
        raise ProtocolError("Unlisted or missing file in participant mount")
    raw = safe_path(trial, manifest["packet"]["path"]).read_bytes()
    facts, summary = old.parse_packet(raw, manifest["format"])
    assert_public(facts)
    if (binding(raw) != {k: manifest["packet"][k] for k in ("sha256", "bytes")}
            or sha(canonical(facts)) != manifest["facts_sha256"]
            or sha(canonical(summary)) != manifest["summary_sha256"]):
        raise ProtocolError("Participant packet/facts binding failed")
    for asset in manifest["assets"]:
        data = safe_path(trial, asset["path"]).read_bytes()
        if binding(data) != {k: asset[k] for k in ("sha256", "bytes")}:
            raise ProtocolError("Participant asset changed")
        if asset["path"].endswith(".json"):
            assert_public(json.loads(data))
    if manifest["tools"] != TOOLS or manifest["resources"] != RESOURCES:
        raise ProtocolError("Tool/schema/resource definitions differ from frozen contract")
    return {"status": "PASS", "trial_id": manifest["trial_id"],
            "manifest_sha256": sha(safe_path(trial, "manifest.json").read_bytes()),
            "facts_sha256": manifest["facts_sha256"], "files": len(expected_files),
            "scope": "participant-only mount audit; no evaluator read or model dispatch"}


def prepare(root: Path, profile: Path, output: Path) -> dict:
    started = time.monotonic()
    protocol = load_protocol(root)
    gate = resource_gate(root, profile, "prepare")
    allowed = safe_path(root, OUTPUT).resolve()
    if output.is_symlink() or not output.resolve().is_relative_to(allowed) or output.resolve() == allowed:
        raise ProtocolError("Output must be a new directory in the owner's output subtree")
    if any(p.is_symlink() for p in [output, *output.parents] if p != Path(p.anchor)):
        raise ProtocolError("Output path contains a symlink")
    output.mkdir(parents=True, exist_ok=False)
    # Write the started receipt first so an interrupted preparation is retained.
    write_json(output / "start.json", {"status": "STARTED", "baseline": BASELINE, "resource_gate": gate})
    capsule = safe_path(root, LEGACY)
    result = read_json(capsule / "result.json")
    audit = recheck_legacy(root)
    executable = model_source(root)
    private_rows, groups, raw_audits = [], {}, []
    unknown = correct = 0
    for pair in result["pairs"]:
        for case in pair["cases"]:
            raw = read_json(safe_path(capsule, f"observation-inputs/{pair['pair']}/{case['world']}/raw.json"))
            clean, removed = public_raw(raw)
            static = rich_facts(clean)
            current = copy.deepcopy(case["current_representation"])
            raw_audits.append({"pair": pair["pair"], "world": case["world"], "removed_metadata_only": removed,
                               "physical_raw_preserved": clean == public_raw(raw)[0]})
            # All responses here are saved outputs, never a new invocation.
            response = next(x["reference"] for x in result["reference_checks"]
                            if x["pair"] == pair["pair"] and x["world"] == case["world"]
                            and x["phase"] == "intervention" and x["reference"]["step_s"] == 0.001)
            for level in protocol["e4"]["information_levels"]:
                facts = current if level == "current" else static
                if level in {"complete-raw", "executable-response"}:
                    facts = {**current, "raw_model": clean, "units": UNITS}
                for regime in protocol["e4"]["observation_regimes"]:
                    for form in protocol["e4"]["formats"]:
                        key = [pair["pair"], case["world"], level, regime, form]
                        trial_id = "t-" + sha(canonical([BASELINE, key]))[:24]
                        trial = output / "participant" / trial_id
                        trial.mkdir(parents=True)
                        packet_name = "packet.json" if form == "structured" else "packet.txt"
                        packet = old.format_packet(facts, SUMMARY, form)
                        parsed, text = old.parse_packet(packet, form)
                        if canonical(parsed) != canonical(facts) or text != SUMMARY:
                            raise ProtocolError("New packet roundtrip failed")
                        assets = []
                        if level in {"complete-raw", "executable-response"}:
                            assets.append(_asset(trial, "raw.json", canonical(clean) + b"\n"))
                        if level == "executable-response":
                            assets.append(_asset(trial, "model.py", executable))
                        manifest = {"schema_version": "bf-e4-participant-v1", "trial_id": trial_id,
                                    "partition": "public-development", "information": level, "format": form,
                                    "observation_regime": regime, "packet": {"path": packet_name, **binding(packet)},
                                    "facts_sha256": sha(canonical(facts)), "summary_sha256": sha(canonical(SUMMARY)),
                                    "assets": assets, "tools": TOOLS, "resources": RESOURCES,
                                    "observation_access": "active" if regime == "active" else "disabled",
                                    "local_computation": "allowed on supplied facts/assets; future kernel accounts cost",
                                    "response_schema": {"judgment": ["PASS", "FAIL", "UNKNOWN"],
                                                        "reason": "participant explanation", "used_observations": "receipt hashes"}}
                        assert_public(manifest)
                        assert_public(facts)
                        _asset(trial, packet_name, packet)
                        write_json(trial / "manifest.json", manifest)
                        cache = output / "evaluator" / "cache" / trial_id
                        for name, value in {"current": current, "spec": static, "raw": clean,
                                            "response": response}.items():
                            write_json(cache / (name + ".json"), value)
                        row = {"trial_id": trial_id, "pair": pair["pair"], "world": case["world"],
                               "information": level, "regime": regime, "format": form,
                               "expected_verdict": case["intervention"]["verdict"],
                               "legal_patch": pair["shared_patch"], "cache": "cache/" + trial_id,
                               "participant_dir": "participant/" + trial_id}
                        private_rows.append(row)
                        groups.setdefault(tuple(key[:-1]), []).append(manifest)
                        if level in {"current", "bf-rich-static"}:
                            verdict = old.judge_facts(facts)
                            unknown += int(verdict == "UNKNOWN")
                            correct += int(verdict == row["expected_verdict"])
    parity = []
    fields = ("facts_sha256", "summary_sha256", "assets", "tools", "resources", "observation_access")
    for key, arms in groups.items():
        if len(arms) != 2 or any(arms[0][x] != arms[1][x] for x in fields):
            raise ProtocolError("Unequal information, assets, tools or resources across formats")
        parity.append({"trial_ids": [x["trial_id"] for x in arms], "status": "PASS",
                       "facts_sha256": arms[0]["facts_sha256"], "information": key[2], "regime": key[3]})
    if len(private_rows) != 64 or len(parity) != 32:
        raise ProtocolError("Unexpected E4 factorial size")
    write_json(output / "evaluator" / "index.json", {"schema_version": "bf-e4-evaluator-v1", "trials": private_rows})
    write_json(output / "legacy-audit.json", audit)
    write_json(output / "mechanisms.json", mechanism_map(root, result))
    write_json(output / "e4-parity.json", {"status": "PASS", "pairs": parity,
                                           "note": "facts equality, not equal token length or Agent performance"})
    write_json(output / "e5-contract.json", e5_contract())
    baselines = {"rich_static": {"unweakened": True, "scope": "all actual-world declarative parameters/laws/assumptions",
                                 "saved_sufficient_grid_checks": audit["static_sufficient_saved_checks"],
                                 "saved_additive_checks": audit["additive_saved_checks"],
                                 "boundary": "sufficiency on these ideal domains; no blanket static failure claim"},
                 "complete_raw": {"unweakened": True, "case_readbacks": raw_audits,
                                  "kept": "all physical fields, current outputs, alternative worlds and public grids",
                                  "removed": "historical case identifiers/names only; no target response added"},
                 "executable_response": {"model_source": binding(executable), "syntax_checked": True,
                                         "model_executions": 0, "entry": "python -B model.py raw.json '<legal patch JSON>'",
                                         "scope": "unchanged exported numerical function bodies; not independent truth"},
                 "e4_fixed_parser": {"current_unknown": unknown, "rich_static_correct": correct,
                                      "counting": "4 cases x 2 formats x 2 observation regimes per level; no Agent runs"}}
    write_json(output / "baselines.json", baselines)
    wall = time.monotonic() - started
    if wall > protocol["cost_cap"]["preparation_wall_s"]:
        raise ProtocolError("Preparation wall budget exhausted; retain started artifacts")
    report = {"schema_version": "bf-interface-phase1-result-v1", "status": "PASS",
              "baseline": BASELINE, "protocol_sha256": sha(safe_path(root, PROTOCOL).read_bytes()),
              "implementation_sha256": sha(safe_path(root, MODULE).read_bytes()),
              "legacy": audit, "bf_structural_pairs": 2, "b_saved_reference_cases": 7,
              "prepared_e4_inputs": len(private_rows), "equal_format_pairs": len(parity),
              "administrative_label_isolation": "PASS; standalone one-trial mount required for live study",
              "e5": "contract/validator only; Agent discovery, qualification and consumer experiment NOT_RUN",
              "new_solver_runs": 0, "paid_model_requests": 0, "native_dispatches": 0,
              "wall_s": wall, "claim_boundary": protocol["claim_boundary"]}
    write_json(output / "result.json", report)
    files = {str(p.relative_to(output)): binding(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}
    total = sum(v["bytes"] for v in files.values())
    if total > protocol["cost_cap"]["retained_output_cap_bytes"]:
        raise ProtocolError("Retained output budget exceeded")
    write_json(output / "seal.json", {"schema_version": "bf-interface-phase1-seal-v1", "files": files,
                                       "total_payload_bytes": total, "baseline": BASELINE})
    return report


def verify(output: Path) -> dict:
    if output.is_symlink():
        raise ProtocolError("Symlink bundle root")
    seal = read_json(output / "seal.json")
    if any(p.is_symlink() for p in output.rglob("*")):
        raise ProtocolError("Symlink in sealed bundle")
    actual = {str(p.relative_to(output)) for p in output.rglob("*") if p.is_file() and p != output / "seal.json"}
    if actual != set(seal["files"]):
        raise ProtocolError("Unlisted/missing artifact in sealed bundle")
    for name, expected in seal["files"].items():
        if binding(safe_path(output, name).read_bytes()) != expected:
            raise ProtocolError("Sealed artifact changed: " + name)
    if sum(v["bytes"] for v in seal["files"].values()) != seal["total_payload_bytes"]:
        raise ProtocolError("Payload accounting mismatch")
    index = read_json(safe_path(output, "evaluator/index.json"))
    groups: dict[tuple, list] = {}
    for row in index["trials"]:
        trial = safe_path(output, row["participant_dir"])
        verify_trial(trial)
        manifest = read_json(safe_path(trial, "manifest.json"))
        assert_public(manifest)
        packet = safe_path(trial, manifest["packet"]["path"]).read_bytes()
        facts, summary = old.parse_packet(packet, manifest["format"])
        assert_public(facts)
        if (binding(packet) != {k: manifest["packet"][k] for k in ("sha256", "bytes")}
                or sha(canonical(facts)) != manifest["facts_sha256"]
                or sha(canonical(summary)) != manifest["summary_sha256"]):
            raise ProtocolError("Participant packet/facts binding failed")
        for asset in manifest["assets"]:
            raw = safe_path(trial, asset["path"]).read_bytes()
            if binding(raw) != {k: asset[k] for k in ("sha256", "bytes")}:
                raise ProtocolError("Participant asset changed")
            if asset["path"].endswith(".json"):
                assert_public(json.loads(raw))
        key = (row["pair"], row["world"], row["information"], row["regime"])
        groups.setdefault(key, []).append(manifest)
    for arms in groups.values():
        if len(arms) != 2 or any(arms[0][k] != arms[1][k] for k in
                               ("facts_sha256", "summary_sha256", "assets", "tools", "resources", "observation_access")):
            raise ProtocolError("Format parity failed")
    report = read_json(output / "result.json")
    if len(index["trials"]) != 64 or len(groups) != 32 or report["baseline"] != BASELINE:
        raise ProtocolError("Factorial size/baseline mismatch")
    return {"status": "PASS", "sealed_files": len(seal["files"]),
            "payload_bytes": seal["total_payload_bytes"], "trials": 64, "format_pairs": 32,
            "new_solver_runs": 0, "paid_model_requests": 0, "native_dispatches": 0}


def replay_observation(output: Path, trial_id: str, operation: str,
                       patch: dict | None = None) -> dict:
    """Trusted-side replay of one observation. Never mount evaluator/ to an Agent.

    No live Agent study is admitted by this API. Future kernel integration must
    own cumulative budgets and mount restrictions before any model call.
    """
    started = time.perf_counter_ns()
    verify(output)
    rows = read_json(safe_path(output, "evaluator/index.json"))["trials"]
    row = next((r for r in rows if r["trial_id"] == trial_id), None)
    if row is None:
        raise ProtocolError("Unknown trial")
    if row["regime"] != "active":
        raise ProtocolError("Fixed-information regime prohibits external observation")
    names = {"read_current": "current", "read_spec": "spec", "read_raw": "raw", "query_model": "response"}
    if operation not in names:
        raise ProtocolError("Unsupported observation")
    if operation == "query_model":
        if patch != row["legal_patch"]:
            raise ProtocolError("No saved response for this patch; do not launch a new solve")
    elif patch is not None:
        raise ProtocolError("Unexpected observation arguments")
    source = safe_path(output / "evaluator", row["cache"] + "/" + names[operation] + ".json")
    raw = source.read_bytes()
    facts = json.loads(raw)
    assert_public(facts)
    if len(raw) > RESOURCES["observation_payload_bytes_per_future_trial"]:
        raise ProtocolError("Observation payload budget exceeded")
    wall = (time.perf_counter_ns() - started) / 1e9
    if wall > RESOURCES["wall_s_per_future_trial"]:
        raise ProtocolError("Observation wall budget exceeded")
    return {"schema_version": "bf-e4-observation-replay-v1", "trial_id": trial_id,
            "operation": operation, "patch": patch, "facts": facts,
            "facts_sha256": sha(canonical(facts)), "source_sha256": sha(raw),
            "units": UNITS, "source_kind": "saved ideal-model development output",
            "costs": {"payload_bytes": len(raw), "wall_s": wall, "new_solver_runs": 0,
                      "paid_model_requests": 0, "native_dispatches": 0},
            "cost_boundary": "one read request; audit reads and cumulative trial ledger not a performance claim"}
