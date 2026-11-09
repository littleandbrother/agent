"""M3 developer service repair and equally shared generic service tools.

No solver, provider, file I/O, task-ID lookup or saved successful configuration.
The host supplies public state and owns the finite execution/accounting loop.
Only calls to the shared A predictor consume the monotone analytic allowance.
"""
from copy import deepcopy
import json
import math

from .methods import Harness, ContractError, digest, load_program, seed_program, public_state, common_contract_check
from .dynamic_methods import DynamicRepairHarness, SUCCESS, _actual, _number, _passed, _relations
from .decision_facts import candidate_facts
from .m2_methods import M2GenericHarness, TOOL_SCHEMA as M2_TOOLS

VERSION = "H-service-repair-m3-v1"


def extract_service_facts(task, design, result):
    from .service_relations import extract_service_facts as extract
    return extract(task, design, result)


def predict_candidate(task, design, service_facts=None):
    from .service_relations import predict_candidate as predict
    return predict(task, design, service_facts=service_facts)


def _program(generic=False):
    p = seed_program()
    p.update(program_id=VERSION + ("-generic" if generic else ""),
             origin="DEVELOPER_FIXED_SERVICE_METHOD" if not generic else "DEVELOPER_PUBLIC_TOOL_ADAPTER",
             adoption="M3_ENGINEERING_DEVELOPMENT")
    sites = {"H-STOP": ("h_stop", "SERVICE-STOP")}
    if not generic:
        sites.update({"H-GEN": ("h_gen", "SERVICE-GENERATE"),
                      "H-RANK": ("h_rank", "SERVICE-SELECT"),
                      "H-UPDATE": ("h_update", "SERVICE-UPDATE")})
    p["code"] = {site: f'def {name}(ctx, ask):\n    return ask("{target}", ctx)\n'
                 for site, (name, target) in sites.items()}
    p["config"] = {site: {"version": VERSION, "model_callbacks": 0} for site in sites}
    return load_program(p)


def _observations(task, result):
    """Public identity/age facts only; absence requires complete received rows.

    Age since SAVE exceeds the true age's lower bound; age<=deadline does not
    prove timely event delivery. A supplies the stronger contact-window test.
    """
    f = result.get("facts", {})
    saved, received = f.get("records", []), f.get("receiver_records", [])
    catalog = f.get("detail_catalog", {})
    complete = len(received) == catalog.get("receiver_records", {}).get("count", len(received))
    deadline = task.get("service", {}).get("receive_deadline_s")
    rows, late, missing = [], [], []
    for record in saved:
        identity = {k: record.get(k) for k in ("seq", "direction")}
        matches = [r for r in received if all(r.get(k) == v for k, v in identity.items())]
        ages = [r["time_s"] - record["committed_s"] for r in matches
                if _number(r.get("time_s")) and _number(record.get("committed_s"))]
        is_late = bool(ages and _number(deadline) and min(ages) > deadline)
        absent = not matches and complete
        rows.append({**identity, "committed_s": record.get("committed_s"),
                     "observed_receive_ages_since_SAVE_s": ages,
                     "definitely_late_since_SAVE": is_late,
                     "not_received_in_complete_public_list": absent})
        if is_late:
            late.append(identity)
        if absent:
            missing.append(identity)
    snap = f.get("program_state", {})
    image = snap.get("nvm") if snap.get("mode") == "OFF" and snap.get("persistent") else snap.get("ram")
    queue = deepcopy((image or {}).get("queue", []))
    return {"records": rows, "definitely_late_records": late, "unreceived_records": missing,
            "final_public_queue": queue, "receiver_list_complete": complete,
            "delivery_issue_observed": bool(late or missing or queue),
            "resets_with_pending_queue": [deepcopy(e) for e in f.get("activity", [])
                if e.get("action") == "brownout" and e.get("queue_length", 0) > 0],
            "conditions": ["Only public sequence/direction links; no hidden event truth.",
                           "An on-time SAVE-relative age does not certify the event deadline.",
                           "Pending queue and IDLE resets do not imply corrupt or reused IDs."]}


class M3ServiceHarness(DynamicRepairHarness):
    def __init__(self):
        super().__init__()
        self.program = _program()

    def _budget(self, quota):
        q = deepcopy(quota)
        if type(q.get("analytic_scores_left")) is int:
            q["analytic_scores_left"] = min(24, q["analytic_scores_left"])
        return super()._budget(q)

    def _service(self, state):
        m = state.get("strategy", {}).get("service_repair", {})
        if (m.get("task_sha256") == digest(state["task"])
                and m.get("design_sha256") == digest(state["design"])
                and m.get("execution_confirmed") is True):
            return deepcopy(m), True
        return {}, False

    def _predict(self, task, design, service):
        key = digest({"version": VERSION, "task": task, "design": design,
                      "service_facts": service.get("facts", service)})
        if key in self._predictions:
            return deepcopy(self._predictions[key])
        if not self._scores_left:
            return None
        self._scores_left -= 1
        self.analytic_score_count += 1
        row = {"index": self.analytic_score_count, "input_sha256": key,
               "task_sha256": digest(task), "design_sha256": digest(design),
               "service_facts_sha256": digest(service.get("facts", service))}
        self.analytic_score_log.append(row)
        try:
            value = predict_candidate(task, design, service_facts=service.get("facts", service) or None)
            if not isinstance(value, dict) or value.get("service_verdict", "UNKNOWN") != "UNKNOWN":
                raise ContractError("M3_SHARED_APPROXIMATION_MUST_KEEP_SERVICE_UNKNOWN")
            row.update(status="SCORED", prediction_sha256=digest(value))
        except Exception as exc:
            row.update(status="ERROR", error=type(exc).__name__)
            raise
        self._predictions[key] = deepcopy(value)
        return deepcopy(value)

    def _ask(self, site, ctx):
        if site == "SERVICE-STOP":
            return {"stop": _passed(ctx["state"]) or ctx["state"].get("applicability") == "OUT_OF_SCOPE"
                    or ctx["quota"].get("remaining_actions", 0) < 1,
                    "reason": "retain actual PASS, scope or quota", "scope": "current executed point only"}
        if site == "SERVICE-GENERATE":
            return self._generate(ctx)
        if site == "SERVICE-SELECT":
            return self._select(ctx)
        if site == "SERVICE-UPDATE":
            return self._update_service(ctx)
        raise ContractError("M3_UNEXPECTED_HOOK")

    def _proposals(self, state, memory, current_prediction):
        o = memory.get("observations", {})
        if not o.get("delivery_issue_observed"):
            return []
        t, d = state["task"], state["design"]
        domain, load = t.get("design_domain", {}), t.get("components", {})
        if not {"retry_s", "tx_gate_v", "capacitance_f"} <= set(domain):
            return []
        def clamp(value, key):
            return min(domain[key]["max"], max(domain[key]["min"], value))
        windows = sorted(t.get("gateway_windows", []))
        gaps = [b[0] - a[1] for a, b in zip(windows, windows[1:]) if b[0] > a[1]]
        outage = max(gaps, default=t.get("service", {}).get("receive_deadline_s", d["retry_s"]))
        short = domain["retry_s"]["min"]
        quiet = clamp(max(d["retry_s"], outage / 2), "retry_s")
        retry_rows = current_prediction.get("repair_intervals", {}).get("retry_s", {}).get("per_window", [])
        intervals = [(row.get("second_wire_after_recovery_retry_lower_s"),
                      row.get("second_wire_before_deadline_retry_upper_s")) for row in retry_rows]
        intervals = [(lo, hi) for lo, hi in intervals if _number(lo) and _number(hi) and lo <= hi]
        if intervals:
            lo, hi = max(v[0] for v in intervals), min(v[1] for v in intervals)
            if lo <= hi:
                quiet = clamp((lo + hi) / 2, "retry_s")
        qtx = load["tx_a"] * load["tx_s"]
        qack = load["write_a"] * load["write_s"]
        idle = load.get("idle_a", 0) + load.get("max_v", 0) / load.get("leakage_ohm", math.inf)
        headroom = load["max_v"] - d["brownout_v"] - load["tx_a"] * d["esr_ohm"]
        if headroom <= 0:
            return []
        bridge = clamp(d["capacitance_f"] + (qtx + idle * outage) / headroom, "capacitance_f")
        cold = clamp(d["capacitance_f"] / 2, "capacitance_f")
        def tail_gate(cap):
            # Conditional single TX+ACK reserve, not a service or reachability
            # bound; all candidate supply feedback is recomputed by A.
            return clamp(d["brownout_v"] + load["tx_a"] * d["esr_ohm"] + (qtx + qack) / cap,
                         "tx_gate_v")
        early = min(d["tx_gate_v"], tail_gate(d["capacitance_f"]))
        shared_gate = current_prediction.get("repair_intervals", {}).get("tx_gate_v", {}).get("conditional_no_source_tx_ack_lower_v")
        if _number(shared_gate):
            early = min(d["tx_gate_v"], clamp(shared_gate, "tx_gate_v"))
        descriptions = [
            ("retry-short", {"retry_s": short}, "Retry earlier while holding electrical conditions fixed; may waste scarce charge before gateway recovery."),
            ("retry-quiet", {"retry_s": quiet}, "Spend less TX charge during a public gateway outage; longer retry may miss the receive deadline."),
            ("early-gate-short-retry", {"tx_gate_v": early, "retry_s": short}, "Earlier conditional TX+ACK reserve with frequent retry; distinguish gate delay from retry-energy depletion."),
            ("early-gate-quiet-retry", {"tx_gate_v": early, "retry_s": quiet}, "Earlier TX eligibility with fewer outage retries; preserve startup and test timely gateway opportunity."),
            ("bridge-reserve", {"capacitance_f": bridge, "tx_gate_v": tail_gate(bridge), "retry_s": quiet}, "Add one outage-TX plus idle charge reserve; larger C may delay BOOT/capture and lower the reached source voltage."),
            ("cold-start-reserve", {"capacitance_f": cold, "tx_gate_v": tail_gate(cold), "retry_s": quiet}, "Reduce cold charging time while raising the isolated tail gate; may lose hold-up or never reach the new gate."),
        ]
        return [(label, {**deepcopy(d), **patch}, rationale) for label, patch, rationale in descriptions]

    def _generate(self, ctx):
        state, quota = ctx["state"], ctx["quota"]
        memory, consumed = self._service(state)
        if not consumed:
            return {"status": "INSUFFICIENT_EVIDENCE", "reason": "Executed public service Update required before this repair method."}
        current = self._predict(state["task"], state["design"], memory)
        if current is None:
            return {"status": "INSUFFICIENT_EVIDENCE", "reason": "Analytic allowance exhausted."}
        out, excluded, seen = [], [], set()
        for label, design, rationale in self._proposals(state, memory, current):
            if len(out) >= min(6, quota.get("max_candidates", 16)):
                break
            actual = _actual(state, design)
            if not actual["design_patch"] or digest(design) in seen:
                continue
            seen.add(digest(design))
            try:
                common_contract_check(state, actual, quota)
                bad = _relations(candidate_facts(state, actual))
                if bad or self._refuted(state, design):
                    excluded.append({"actual_input": actual, "necessary_failures": bad,
                                     "exact_executed_FAIL": self._refuted(state, design)})
                    continue
                pred = self._predict(state["task"], design, memory)
                if pred is None:
                    break
                if pred.get("necessary_failures") or pred.get("prediction_status") == "REJECT_NECESSARY":
                    excluded.append({"actual_input": actual, "necessary_failures": pred.get("necessary_failures", [])})
                    continue
                out.append({"id": label + "-" + digest(actual)[:12], "target": "timely record delivery",
                    "operation": actual["operation"], "actual_input": actual, "cost_bound": 1,
                    "repair_family": label, "expected_state_change": rationale,
                    "prediction_or_unknown": "UNKNOWN", "service_prediction": pred,
                    "observation_branches": ["Actual complete service PASS: retain the executed point.",
                        "Late/unreceived despite TX: compare record age, gateway opportunity, retry charge and final queue.",
                        "New BOOT/TX failure: retain the shifted electrical failure; do not rescue after budget."],
                    "affected_constraints": ["BOOT/capture", "TX/ACK energy", "retry/gateway timing", "queue order and receive deadline"],
                    "validity_conditions": ["Original Task, legal actions and device observations unchanged.",
                        "Conditional isolated-record approximation; reset/backlog effects remain UNKNOWN.",
                        "No added device clock or knowledge of future gateway state."],
                    "update_consumed": True, "update_service_facts_sha256": digest(memory["facts"])})
            except (ContractError, KeyError, TypeError) as exc:
                excluded.append({"actual_input": actual, "reason": str(exc)})
        self.decisions.append({"site": "Generate", "update_consumed": consumed,
            "service_memory_sha256": digest(memory), "observed_delivery_issue": memory["observations"],
            "current_service_prediction": current.get("service_prediction", {}),
            "consumed_repair_intervals": current.get("repair_intervals", {}),
            "excluded": excluded, "emitted_actual_inputs": [c["actual_input"] for c in out]})
        return {"status": "OK", "candidates": out}

    def _select(self, ctx):
        state, quota = ctx["state"], ctx["quota"]
        memory, consumed = self._service(state)
        choices, excluded = [], []
        for candidate in ctx["candidates"]:
            actual = candidate["actual_input"]
            design = {**state["design"], **actual.get("design_patch", {})}
            try:
                common_contract_check(state, actual, quota)
                if _relations(candidate_facts(state, actual)) or self._refuted(state, design):
                    raise ContractError("NECESSARY_OR_EXACT_FAILED_POINT")
                pred = self._predict(state["task"], design, memory)
                if pred is None or pred.get("necessary_failures"):
                    raise ContractError("NO_SCORED_LEGAL_CONDITIONAL_PREDICTION")
                assessment = _decision_assessment(pred, actual, memory)
                choices.append((assessment["priority"], candidate, assessment))
            except (ContractError, KeyError, TypeError) as exc:
                excluded.append({"id": candidate.get("id"), "reason": str(exc)})
        self.decisions.append({"site": "Select", "update_consumed": consumed, "excluded": excluded,
            "assessments": [{"id": c["id"], **a} for _, c, a in choices]})
        if not choices:
            return {"status": "INSUFFICIENT_EVIDENCE", "reason": "No scored legal service intervention remains."}
        priority, chosen, assessment = max(choices, key=lambda row: (row[0], row[1]["id"]))
        return {"selected_id": chosen["id"], "selection_basis": assessment["basis"],
                "expected_discrimination_or_gain": {**assessment, "service_verdict": "UNKNOWN",
                    "scope": "Conditional public model; original consumer must establish full service."}}

    def _update_service(self, ctx):
        state, result = ctx["state"], ctx["result"]
        facts = extract_service_facts(state["task"], state["design"], result)
        obs = _observations(state["task"], result)
        obs["delivery_issue_observed"] = bool(obs["delivery_issue_observed"]
            or facts.get("summary", {}).get("service_failure_observed") or facts.get("service_failures"))
        obs["shared_service_summary"] = deepcopy(facts.get("summary", {}))
        strategy = deepcopy(state.get("strategy", {}))
        failures = deepcopy(strategy.get("dynamic_repair", {}).get("executed_failures", []))
        confirmed = result.get("execution_status") in SUCCESS and result.get("model_valid") is True
        if confirmed and result.get("public_check", {}).get("verdict") == "FAIL":
            failures.append({"task_sha256": digest(state["task"]), "design_sha256": digest(state["design"]),
                             "result_sha256": result.get("result_sha256")})
        strategy["dynamic_repair"] = {"executed_failures": failures[-16:]}
        strategy["service_repair"] = {"version": VERSION, "task_sha256": digest(state["task"]),
            "design_sha256": digest(state["design"]), "source_result_sha256": result.get("result_sha256"),
            "execution_confirmed": confirmed, "facts": facts, "observations": obs,
            "unique_cause": False}
        self.decisions.append({"site": "Update", "execution_confirmed": confirmed,
                               "service_facts_sha256": digest(facts), "observations": obs})
        return {"strategy": strategy, "next_evidence": {"service_failures": deepcopy(facts.get("service_failures", [])),
            "delivery_issue_observed": obs["delivery_issue_observed"], "queue": obs["final_public_queue"],
            "competing_explanations": ["TX gate reached too late", "outage retry charge exhausted",
                "cold startup/capture delayed", "FIFO head blocks fresher saved record", "reset/queue dynamics unresolved"],
            "unique_cause": False}}

    def update(self, state, decision, result, independent_assessment=None):
        before = len(self.program.calls)
        updated = Harness.update(self, state, decision, result, independent_assessment)
        if not any(c["site"] == "H-UPDATE" for c in self.program.calls[before:]):
            patch = self._update_service({"state": updated, "result": updated["last_result"]})
            updated.update(patch)
        return updated

    def select(self, state, batch, quota):
        result = super().select(state, batch, quota)
        if result.get("status") == "READY":
            result["selection_control"]["policy"] = VERSION
        return result


def _decision_assessment(prediction, actual, memory):
    """Conditional service comparison; unknowns are experiments, never -1 utility.

    Shared model summary fields are normalized here, leaving the full model
    payload intact in each candidate. Stable ID breaks genuine remaining ties.
    """
    service = prediction.get("service_prediction", {})
    metrics = prediction.get("selection_metrics", {})
    timely = service.get("conditional_timely_windows") if isinstance(service, dict) else None
    unknown = service.get("unknown_windows") if isinstance(service, dict) else None
    ack = metrics.get("conditional_ack_completed_windows")
    energy = metrics.get("minimum_isolated_terminal_margin_v")
    energy = energy if _number(energy) else None
    startup = [p.get("startup_margin_v", p.get("terminal_margin_v"))
               for p in prediction.get("phase_predictions", []) if p.get("phase") == "BOOT"]
    startup = min([v for v in startup if _number(v)], default=None)
    electrical_negative = bool((energy is not None and energy < 0) or (startup is not None and startup < 0))
    model_comparable = (_number(timely) and _number(ack) and unknown == 0
                        and energy is not None and startup is not None and not electrical_negative)
    patch = actual.get("design_patch", {})
    evidence = memory.get("observations", {})
    # If delivery cannot be predicted, test the observed timing/charge rival
    # directly. This priority is a declared experiment policy, not efficacy.
    timing = int("tx_gate_v" in patch and evidence.get("delivery_issue_observed", False))
    retry = int("retry_s" in patch and bool(evidence.get("final_public_queue")))
    isolated = int(not ({"capacitance_f", "mechanism", "startup_v"} & patch.keys()))
    priority = ([2, timely, ack, energy, startup]
                if model_comparable else [0 if electrical_negative else 1, timing, retry, isolated])
    return {"priority": priority, "basis": "CONDITIONAL_SERVICE_MODEL" if model_comparable else "DISCRIMINATING_EXECUTION_OF_UNRESOLVED_SERVICE",
            "conditional_timely_records": timely if _number(timely) else None,
            "unknown_windows": unknown, "conditional_ack_completed_windows": ack,
            "minimum_conditional_terminal_margin_v": energy, "minimum_BOOT_margin_v": startup,
            "electrical_adverse_prediction": electrical_negative,
            "unknown_service_is_not_numeric_utility": True,
            "conditions": deepcopy(service.get("conditions", [])) if isinstance(service, dict) else [],
            "unknowns": deepcopy(prediction.get("unknowns", []))}


SERVICE_TOOLS = {**deepcopy(M2_TOOLS),
    "service_facts": {"arguments": {"result_sha256": "optional known public result; default last"},
        "returns": "All public record/SAVE/receive/ACK/queue evidence, competing explanations and coverage."},
    "public_object": {"arguments": {"object_id": "stable public object identity", "section": "public section path", "offset": "nonnegative integer"},
        "returns": "Host bounded public page, <=24 rows and14KB with next_offset; all tools count against24."}}
SERVICE_TOOLS["predict_candidate"]["returns"] = "Shared A service prediction: necessary electrical checks, per-record timing/energy/conditions/unknowns; full service UNKNOWN."
SERVICE_TOOLS["phase_facts"]["returns"] = "Compatibility alias for the shared service_facts tool, including electrical and delivery evidence."
SERVICE_INSTRUCTION = (
    "At H-GEN/H-RANK return status PUBLIC_TOOLS with tool_calls[{id,name,arguments}] to use shared service_facts, "
    "predict_candidate, engineering_relations, public_detail or public_object. You choose all designs and final actions. "
    "A prediction is conditional and cannot certify complete service; reset/backlog uncertainty stays UNKNOWN. "
    "Use public_object object_id/section/offset to read full public data behind bounded references. "
    "The host projects repeated state/materials/predictions into bounded summaries; full public objects remain readable."
)


class M3GenericHarness(M2GenericHarness):
    def __init__(self, model_call, fixture_mode=False, public_reader=None):
        super().__init__(model_call, fixture_mode)
        if public_reader is not None and not callable(public_reader):
            raise ContractError("M3_PUBLIC_READER_MUST_BE_CALLABLE")
        self.program = _program(generic=True)
        self._calculator = M3ServiceHarness()
        self.public_reader = public_reader

    def _budget(self, quota):
        q = deepcopy(quota)
        if type(q.get("public_tool_calls_left")) is int:
            q["public_tool_calls_left"] = min(24, q["public_tool_calls_left"])
        return super()._budget(q)

    def _tool(self, state, call):
        name = call.get("name") if isinstance(call, dict) else None
        if name not in {"service_facts", "phase_facts", "extract_phase_facts", "extract_service_facts", "predict_candidate", "public_object"}:
            out = super()._tool(state, call)
            if name == "engineering_relations" and out.get("status") == "OK":
                out["result"]["public_service_program_laws"] = [
                    "retry_due=powered_uptime_after_wire+retry_s; reset clears powered clock",
                    "TX requires current voltage>=tx_gate; gateway observed only at completion",
                    "SAVE commits record; ACK atomically pops FIFO head and pays write charge",
                    "No absolute device clock, future gateway observation or new queue policy is added"]
                self.tool_call_log[-1]["result_sha256"] = digest(out["result"])
            return out
        if not self._tools_left:
            raise ContractError("PUBLIC_TOOL_BUDGET_EXHAUSTED")
        self._tools_left -= 1
        self.tool_call_count += 1
        record = {"index": self.tool_call_count, "request": deepcopy(call), "analytic_before": self.analytic_score_count}
        self.tool_call_log.append(record)
        try:
            args = call.get("arguments", {})
            if not isinstance(args, dict):
                raise ContractError("PUBLIC_TOOL_ARGUMENTS_OBJECT_REQUIRED")
            if name == "public_object":
                if self.public_reader is None:
                    raise ContractError("M3_PUBLIC_READER_NOT_CONNECTED")
                output = self.public_reader(deepcopy(args))
                if (not isinstance(output, dict) or output.get("visibility") != "PUBLIC_ONLY"
                        or len(json.dumps(output, ensure_ascii=False).encode()) > 16000):
                    raise ContractError("M3_PUBLIC_PAGE_BOUND_OR_VISIBILITY")
            else:
                result = self._known_result(state, args.get("result_sha256"))
                facts = extract_service_facts(state["task"], result["design"], result)
                if name == "predict_candidate":
                    design = args.get("design")
                    if not isinstance(design, dict):
                        raise ContractError("PREDICTION_COMPLETE_DESIGN_REQUIRED")
                    output = self._calculator._predict(state["task"], design, {"facts": facts})
                    if output is None:
                        raise ContractError("ANALYTIC_SCORE_QUOTA_EXHAUSTED")
                else:
                    output = facts
            record.update(status="OK", result_sha256=digest(output))
            return {"id": call.get("id"), "name": name, "status": "OK", "result": output}
        except Exception as exc:
            record.update(status="ERROR", error=str(exc))
            return {"id": call.get("id"), "name": name, "status": "TOOL_ERROR", "error": str(exc)}
        finally:
            record["analytic_scores_used"] = self.analytic_score_count - record["analytic_before"]

    def _ask(self, site, payload):
        if site == "SERVICE-STOP":
            return self._calculator._ask(site, payload)
        if site not in {"H-GEN", "H-RANK"}:
            return Harness._ask(self, site, payload)
        context = deepcopy(payload)
        state = context["state"]
        context.update(public_tool_instruction=SERVICE_INSTRUCTION, public_tools=deepcopy(SERVICE_TOOLS))
        for _ in range(12):
            response = Harness._ask(self, site, context)
            if response.get("status") != "PUBLIC_TOOLS":
                return response
            calls = response.get("tool_calls")
            if not isinstance(calls, list) or not calls:
                return {"status": "INVALID_PUBLIC_TOOL_REQUEST"}
            if len(calls) > self._tools_left:
                return {"status": "PUBLIC_TOOL_BUDGET_EXHAUSTED"}
            results = [self._tool(state, c) for c in calls]
            context.setdefault("public_tool_results", []).extend(results)
            if any(r.get("status") == "TOOL_ERROR" for r in results):
                return {"status": "TOOL_ERROR", "reason": "Retain public tool failure; no internal rescue.", "public_tool_results": results}
            context["quota"] = {**context["quota"], "analytic_scores_left": self._calculator._scores_left,
                                "public_tool_calls_left": self._tools_left}
        return {"status": "MODEL_REQUEST_LIMIT"}
