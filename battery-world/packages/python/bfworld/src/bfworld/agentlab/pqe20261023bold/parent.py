"""Developer-authored executable G/S/U parent, before automatic formation.

Hook source obeys the existing restricted Python contract. Engineering cases
are optional compact PUBLIC development facts; binding them changes the program
digest, so the host must freeze one final parent after A's eight design results.
"""
from copy import deepcopy

from ..pqe20261022.methods import H_SITES, load_program, seed_program
from .contracts import VERSION, frozen_case_summaries


H_GEN = '''def helper_value(domain, design, name, fraction):
    spec = domain.get(name, {})
    kind = spec.get("kind")
    if kind == "number":
        low = spec.get("min")
        high = spec.get("max")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)) and high >= low:
            return low + fraction * (high - low)
    if kind == "integer":
        low = spec.get("min")
        high = spec.get("max")
        if isinstance(low, int) and isinstance(high, int) and high >= low:
            return int(low + fraction * (high - low))
    return design.get(name)

def helper_mechanism(domain, design, fraction):
    spec = domain.get("mechanism", {})
    allowed = spec.get("editable", {})
    old = design.get("mechanism", {})
    if not isinstance(allowed, dict) or not isinstance(old, dict):
        return None
    value = dict(old)
    stroke = allowed.get("stroke_m")
    radius = allowed.get("cam_base_radius_m")
    if isinstance(stroke, list) and len(stroke) == 2:
        value["stroke_m"] = stroke[0] + fraction * (stroke[1] - stroke[0])
    if isinstance(radius, list) and len(radius) == 2:
        value["cam_base_radius_m"] = radius[0] + (1.0 - fraction) * (radius[1] - radius[0])
    return value

def helper_patch(domain, design, active, mode):
    patch = {}
    fraction = 0.55
    if mode == "source":
        fraction = 0.8
    elif mode == "reserve":
        fraction = 0.7
    elif mode == "contrast":
        fraction = 0.3
    for name in ["area_cm2", "capacitance_f", "esr_ohm", "startup_v", "brownout_v", "tx_gate_v", "sample_period_s", "ack_spacing_s", "retry_s", "nvm_capacity_records", "backoff_max_s", "tx_reserve_v"]:
        if name not in domain or name not in active:
            continue
        chosen = None
        if name == "area_cm2":
            chosen = helper_value(domain, design, name, 0.9 if mode == "source" else fraction)
        elif name == "capacitance_f":
            chosen = helper_value(domain, design, name, fraction)
        elif name == "esr_ohm":
            chosen = helper_value(domain, design, name, 0.0)
        elif name == "startup_v" or name == "brownout_v":
            chosen = helper_value(domain, design, name, 0.0)
        elif name == "tx_gate_v":
            chosen = helper_value(domain, design, name, 0.25 if mode != "contrast" else 0.05)
        elif name == "sample_period_s" or name == "ack_spacing_s" or name == "retry_s":
            chosen = helper_value(domain, design, name, 0.0 if mode == "program" else 0.35)
        elif name == "nvm_capacity_records":
            chosen = helper_value(domain, design, name, 0.85)
        elif name == "backoff_max_s":
            chosen = helper_value(domain, design, name, 1.0 if mode == "program" else 0.85)
        elif name == "tx_reserve_v":
            chosen = helper_value(domain, design, name, 0.25 if mode == "program" else 0.0)
        if chosen is not None and chosen != design.get(name):
            patch[name] = chosen
    if "mechanism" in domain and "mechanism" in active:
        chosen = helper_mechanism(domain, design, 1.0 if mode == "source" else fraction)
        if chosen is not None and chosen != design.get("mechanism"):
            patch["mechanism"] = chosen
    for name in ["persistent_queue", "persistent_records"]:
        if name in domain and name in active and domain[name].get("kind") == "boolean" and design.get(name) is not True:
            if mode == "program" or mode == "reserve":
                patch[name] = True
    if "firmware_policy" in domain and "firmware_policy" in active:
        values = domain["firmware_policy"].get("values", [])
        if mode == "program" and "voltage_history_backoff_v1" in values and design.get("firmware_policy") != "voltage_history_backoff_v1":
            patch["firmware_policy"] = "voltage_history_backoff_v1"
        elif mode == "contrast" and "fixed_retry_v1" in values and design.get("firmware_policy") != "fixed_retry_v1":
            patch["firmware_policy"] = "fixed_retry_v1"
    return patch

def helper_case_patch(cases, task, domain, design, active):
    want_mechanism = "mechanism" in domain
    want_area = "area_cm2" in domain
    best = None
    best_count = -1
    for case in cases:
        old = case.get("design", {})
        if not isinstance(old, dict) or case.get("model_valid") is not True:
            continue
        if ("mechanism" in old) != want_mechanism or ("area_cm2" in old) != want_area:
            continue
        check = case.get("public_check", {})
        count = check.get("received_count", 0)
        if not isinstance(count, int):
            count = 0
        if check.get("verdict") == "PASS":
            count = count + 1000000
        if count > best_count:
            best = old
            best_count = count
    if best is None:
        return {}
    patch = {}
    for name in active:
        if name not in domain or name not in best or best[name] == design.get(name):
            continue
        spec = domain[name]
        value = best[name]
        if spec.get("kind") == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.get("min", value) <= value <= spec.get("max", value):
                patch[name] = value
        elif spec.get("kind") == "integer" and isinstance(value, int) and not isinstance(value, bool):
            if spec.get("min", value) <= value <= spec.get("max", value):
                patch[name] = value
        elif spec.get("kind") == "boolean" and isinstance(value, bool):
            patch[name] = value
        elif spec.get("kind") == "enum" and value in spec.get("values", []):
            patch[name] = value
        elif spec.get("kind") == "mechanism" and isinstance(value, dict):
            allowed = spec.get("editable", {})
            if all(key in allowed and isinstance(item, (int, float)) and allowed[key][0] <= item <= allowed[key][1] for key, item in value.items()):
                patch[name] = value
    return patch

def helper_candidate(label, patch, problem_patch, branch):
    return {"id": label, "target": "design", "operation": "edit",
        "actual_input": {"operation": "edit", "design_patch": patch, "problem_patch": problem_patch},
        "expected_state_change": "Run original complete consumer on a joint legal design; preserve executed scope",
        "prediction_or_unknown": "UNKNOWN",
        "observation_branches": ["model-valid complete PASS", "model-valid complete FAIL with changed service facts", "MODEL_DOMAIN or tool error"],
        "affected_constraints": ["complete service", "harvest and force", "storage and power", "record identity and deadline"],
        "cost_bound": 1,
        "validity_conditions": ["task design domain and unchanged original consumer", "actual full result required before service claim", "scope is this candidate only"],
        "source_branch": branch}

def h_gen(ctx, ask):
    state = ctx["state"]
    task = state.get("task", {})
    domain = task.get("design_domain", {})
    design = state.get("design", {})
    if not isinstance(domain, dict) or not isinstance(design, dict) or "edit" not in task.get("allowed_operations", ["edit"]):
        return {"status": "INSUFFICIENT_EVIDENCE", "candidates": []}
    active = list(domain.keys())
    problem = state.get("problem", {})
    problem_patch = {}
    if set(active) != set(problem.get("active_variables", [])) or problem.get("fixed_choices"):
        problem_patch = {"active_variables": active, "fixed_choices": {}, "groups": [active]}
    cases = ctx.get("site_config", {}).get("public_engineering_cases", [])
    branch = state.get("strategy", {}).get("bold_gsu", {}).get("failure_branch", "UNRESOLVED")
    options = []
    case_patch = helper_case_patch(cases, task, domain, design, active)
    if case_patch:
        options.append(["public-case-joint", case_patch])
    modes = ["source", "reserve", "program", "contrast"]
    if branch == "DELIVERY_ORDER_DEADLINE_OR_QUEUE":
        modes = ["program", "reserve", "source", "contrast"]
    elif branch == "TX_GATE_ENERGY_OR_RETRY":
        modes = ["reserve", "source", "program", "contrast"]
    elif branch == "MODEL_DOMAIN_OR_UNKNOWN":
        modes = ["contrast", "source", "program", "reserve"]
    for mode in modes:
        options.append(["joint-" + mode, helper_patch(domain, design, active, mode)])
    candidates = []
    patches = []
    ceiling = min(ctx["quota"].get("max_candidates", 4), 4)
    for option in options:
        patch = option[1]
        if patch and patch not in patches and len(candidates) < ceiling:
            candidates.append(helper_candidate(option[0], patch, problem_patch, branch))
            patches.append(patch)
    return {"status": "OK", "candidates": candidates}
'''


H_RANK = '''def h_rank(ctx, ask):
    candidates = ctx.get("candidates", [])
    if not candidates:
        return {"status": "INSUFFICIENT_EVIDENCE"}
    rows = ctx.get("full_candidate_results")
    if not isinstance(rows, list) or len(rows) == 0:
        return {"selected_id": candidates[0]["id"],
            "selection_basis": "software screen only: full consumer results unavailable; service UNKNOWN",
            "expected_discrimination_or_gain": "UNKNOWN"}
    if len(rows) != len(candidates):
        return {"status": "MISSING_FULL_CANDIDATE_RESULT"}
    ids = [candidate["id"] for candidate in candidates]
    seen = []
    winning = None
    winning_basis = None
    best_fail = None
    best_count = -1
    signatures = []
    for row in rows:
        candidate_id = row.get("candidate_id")
        result = row.get("public_result", {})
        if candidate_id not in ids or candidate_id in seen or not isinstance(result, dict):
            return {"status": "INVALID_FULL_CANDIDATE_RESULT"}
        seen.append(candidate_id)
        if result.get("execution_status") not in ["OK", "COMPLETE", "COMPLETED", "SUCCESS"]:
            return {"status": "TOOL_OR_EXECUTION_ERROR"}
        check = result.get("public_check", {})
        if result.get("model_valid") is True and check.get("verdict") == "PASS" and winning is None:
            winning = candidate_id
            winning_basis = "original complete model-valid consumer PASS; choose executed candidate"
        if result.get("model_valid") is True and check.get("verdict") == "FAIL":
            count = check.get("received_count", -1)
            if isinstance(count, int) and count > best_count:
                best_count = count
                best_fail = candidate_id
            signatures.append([candidate_id, check.get("verdict"), check.get("failures", []), count])
    if len(seen) != len(ids):
        return {"status": "MISSING_FULL_CANDIDATE_RESULT"}
    if winning is not None:
        return {"selected_id": winning, "selection_basis": winning_basis,
            "expected_discrimination_or_gain": "actual complete service PASS for this executed input only"}
    baseline = ctx.get("state", {}).get("last_result", {}).get("public_check", {}).get("received_count", -1)
    if not isinstance(baseline, int):
        baseline = -1
    if best_fail is not None and best_count > baseline:
        return {"selected_id": best_fail,
            "selection_basis": "executed model-valid partial delivery improves received count; service remains FAIL and must be repaired",
            "expected_discrimination_or_gain": "partial observation only, no service PASS"}
    if len(signatures) >= 2:
        first = signatures[0]
        for signature in signatures[1:]:
            if signature[2] != first[2] or signature[3] != first[3]:
                return {"selected_id": signature[0],
                    "selection_basis": "executed full results discriminate failure modes; retain uncertainty and inspect original public facts",
                    "expected_discrimination_or_gain": "information about this candidate only, service not repaired"}
    return {"status": "NO_SUPPORTED_IMPROVEMENT"}
'''


H_UPDATE = '''def h_update(ctx, ask):
    state = ctx["state"]
    result = ctx["result"]
    facts = result.get("facts", {})
    projection = facts.get("projection", {})
    counts = facts.get("activity_counts", {})
    exact_counts = isinstance(counts, dict) and bool(counts)
    if not exact_counts:
        counts = projection.get("observed_activity_row_counts", {})
    check = result.get("public_check", {})
    verdict = check.get("verdict", "UNKNOWN")
    failures = check.get("failures", [])
    branch = "UNRESOLVED"
    if result.get("model_valid") is not True:
        branch = "MODEL_DOMAIN_OR_UNKNOWN"
    elif verdict == "PASS":
        branch = "COMPLETE_SERVICE_PASS"
    elif verdict == "FAIL":
        if exact_counts and counts.get("boot", 0) == 0:
            branch = "STARTUP_OR_SOURCE"
        elif counts.get("save_commit", 0) > 0 and exact_counts and counts.get("tx_begin", 0) == 0:
            branch = "TX_GATE_ENERGY_OR_RETRY"
        elif counts.get("tx_begin", 0) > 0:
            branch = "DELIVERY_ORDER_DEADLINE_OR_QUEUE"
        elif counts.get("boot", 0) > 0:
            branch = "CAPTURE_SAVE_OR_PERSISTENCE"
        elif failures:
            branch = "FULL_SERVICE_CONSTRAINT_UNRESOLVED"
    strategy = dict(state.get("strategy", {}))
    old = strategy.get("bold_gsu", {})
    previous = old.get("recent_outcomes", [])
    if not isinstance(previous, list):
        previous = []
    ref = facts.get("detail_catalog", {}).get("full_public_object_ref")
    item = {"result_sha256": result.get("result_sha256"), "public_object_ref": ref,
        "verdict": verdict, "model_valid": result.get("model_valid"), "branch": branch,
        "received_count": check.get("received_count"), "failures": failures,
        "candidate_id": ctx.get("decision", {}).get("selected_id")}
    recent = previous[-5:] + [item]
    strategy["bold_gsu"] = {"failure_branch": branch, "recent_outcomes": recent,
        "last_public_object_ref": ref, "activity_counts_complete": exact_counts,
        "unique_cause": False, "scope": "this executed candidate and original complete public check"}
    invalidated = list(state.get("invalidated", []))
    if verdict == "FAIL" and item["candidate_id"] is not None:
        invalidated.append({"candidate_id": item["candidate_id"], "result_sha256": item["result_sha256"],
            "scope": "candidate-only observed complete-service FAIL; no whole-domain conclusion"})
    return {"strategy": strategy, "invalidated": invalidated[-8:],
        "hypotheses": state.get("hypotheses", []),
        "next_evidence": {"branch": branch, "public_object_ref": ref,
            "read_full_public_facts_if_needed": True, "no_global_infeasibility_claim": True}}
'''


H_STOP = '''def h_stop(ctx, ask):
    state = ctx["state"]
    result = state.get("last_result", {})
    passed = result.get("execution_status") in ["OK", "COMPLETE", "COMPLETED", "SUCCESS"] and result.get("model_valid") is True and result.get("public_check", {}).get("verdict") == "PASS"
    exhausted = ctx["quota"].get("remaining_actions", 0) < 1
    return {"stop": passed or exhausted,
        "reason": "actual complete public service PASS" if passed else "action quota exhausted" if exhausted else "continue",
        "scope": "current executed Task and Design only"}
'''


def parent_program(public_engineering_cases=None):
    """Produce one loadable actual-method artifact; freeze its digest before G."""
    cases = frozen_case_summaries(public_engineering_cases or [])
    program = seed_program("H", "H0")
    program.update(program_id="H-bold-gsu-parent-v1", artifact_version=VERSION,
                   origin="DEVELOPER_AUTHORED_EXECUTABLE_GSU", adoption="NOT_EVALUATED",
                   editable_sites=list(H_SITES),
                   code={"H-GEN": H_GEN, "H-RANK": H_RANK, "H-UPDATE": H_UPDATE, "H-STOP": H_STOP},
                   prompts={"H-GEN": "Generate up to four legal joint design interventions from public Task/domain and full-execution facts; complete service is UNKNOWN until original consumer runs.",
                            "H-RANK": "Rank only bound, accounted original full candidate results. PASS requires model-valid original public PASS; a partial or diagnostic result is not service success.",
                            "H-UPDATE": "Maintain scoped actual failures, excluded candidate predictions and next evidence with full public object references."},
                   config={"H-GEN": {"public_engineering_cases": deepcopy(cases),
                                      "public_case_count": len(cases), "max_candidates": 4},
                           "H-RANK": {"requires_full_candidate_results_in_real_solve": True},
                           "H-UPDATE": {"max_recent_outcomes": 6}},
                   applicability={}, non_trigger_conditions={})
    load_program(program)  # Static schema/capability validation, never a science run.
    return program
