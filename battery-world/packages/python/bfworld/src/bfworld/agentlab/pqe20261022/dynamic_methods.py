"""Developer-fixed, finite dynamic repair over the original public consumer.

Approximate scores propose actions, never service PASS. No provider, complete
solver, evaluator, task-ID table, saved successful design or file I/O is used.
Every predict_candidate call, including rejection/error, consumes analytic quota.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .methods import (Harness, ContractError, digest, load_program, seed_program,
                      public_state, common_contract_check)
from .decision_facts import candidate_facts, _motion_bound
from .door_model import DEFAULT_MECHANISM, DOMAIN, source_step
from .dynamic_relations import extract_phase_facts, predict_candidate

VERSION = "H-dynamic-repair-m1-v1"
SUCCESS = {"OK", "COMPLETE", "COMPLETED", "SUCCESS"}


def fixed_program():
    program = seed_program()
    program.update(program_id=VERSION, artifact_version="1",
                   origin="DEVELOPER_FIXED_H", adoption="FIXED_ENGINEERING_METHOD")
    program["code"] = {
        "H-STOP": 'def h_stop(ctx, ask):\n    return ask("DYNAMIC-STOP", ctx)\n',
        "H-GEN": 'def h_gen(ctx, ask):\n    return ask("DYNAMIC-GENERATE", ctx)\n',
        "H-RANK": 'def h_rank(ctx, ask):\n    return ask("DYNAMIC-SELECT", ctx)\n',
        "H-UPDATE": 'def h_update(ctx, ask):\n    return ask("DYNAMIC-UPDATE", ctx)\n',
    }
    program["config"] = {site: {"version": VERSION, "model_callbacks": 0}
                         for site in program["code"]}
    return program


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _passed(state):
    result = state.get("last_result", {})
    return (result.get("execution_status") in SUCCESS and result.get("model_valid") is True
            and result.get("public_check", {}).get("verdict") == "PASS"
            and result.get("design", state.get("design")) == state.get("design"))


def _relations(facts):
    checks = facts.get("domain_checks", [])
    return [row for row in checks if row.get("necessary") is True and row.get("status") == "FAIL"]


def _clamp(value, domain):
    return min(domain["max"], max(domain["min"], value))


def _changed(current, proposed):
    return {key: deepcopy(value) for key, value in proposed.items() if current.get(key) != value}


def _actual(state, proposed):
    patch = _changed(state["design"], proposed)
    problem = state.get("problem", {})
    active = problem.get("active_variables", [])
    fixed = problem.get("fixed_choices", {})
    reform = bool(set(patch) - set(active) or set(patch) & set(fixed))
    ppatch = {}
    if reform:
        new_active = list(dict.fromkeys([*active, *patch]))
        groups = deepcopy(problem.get("groups", []))
        group = list(patch)
        if group and group not in groups:
            groups.append(group)
        ppatch = {"active_variables": new_active, "groups": groups,
                  "fixed_choices": {key: deepcopy(value) for key, value in fixed.items() if key not in patch}}
    return {"operation": "restructure" if reform else "edit",
            "design_patch": patch, "problem_patch": ppatch}


def _geometry(task, design):
    """Intersect the public cam envelope/pressure and editable intervals."""
    editable = task.get("design_domain", {}).get("mechanism", {}).get("editable", {})
    if not {"stroke_m", "cam_base_radius_m"} <= set(editable):
        return []
    static = source_step(0.0, 0.0, 0.0, design.get("mechanism"))
    geo = static.get("geometry")
    if not geo:
        return []
    current = {**DEFAULT_MECHANISM, **design.get("mechanism", {})}
    rim = geo["cam_diameter_m"] / 2 - current["cam_base_radius_m"] - current["stroke_m"]
    installation = task.get("geometry", {}).get("installation_envelope_mm", [])
    width = min(DOMAIN["envelope_width_m"], installation[1] / 1000) if len(installation) > 1 else DOMAIN["envelope_width_m"]
    total = width / 2 - rim
    tangent = math.tan(math.radians(DOMAIN["maximum_pressure_angle_deg"]))
    ratio = (math.sqrt(1 + 4 / tangent ** 2) - 1) / 2
    slo, shi = editable["stroke_m"]
    rlo, rhi = editable["cam_base_radius_m"]
    maximum = min(shi, total - rlo, rhi / ratio, total / (1 + ratio),
                  DOMAIN["envelope_length_m"] - (geo["generator_travel_envelope_m"][0] - current["stroke_m"]))
    # Strict interior rounding is solely to avoid trigonometric boundary noise.
    maximum = math.nextafter(maximum, -math.inf)
    if maximum < slo:
        return []
    base_stroke = min(maximum, max(slo, current["stroke_m"]))
    values = []
    for stroke in (maximum, (base_stroke + maximum) / 2, base_stroke):
        low, high = max(rlo, ratio * stroke), min(rhi, total - stroke)
        if low > high:
            continue
        radius = (low + high) / 2
        mechanism = deepcopy(design.get("mechanism", {}))
        mechanism.update(stroke_m=stroke, cam_base_radius_m=radius)
        if mechanism not in values:
            values.append(mechanism)
    return values


class DynamicRepairHarness(Harness):
    """Original G/S/U contract with deterministic loaded developer hooks.

    Caller owns the package-global 128-score ledger. analytic_scores_left is
    mandatory and only decreases on this instance; passing a stale quota never
    replenishes it. Cached identical Task/Design/phase-fact predictions cost zero.
    """
    def __init__(self, planner=None, program=None, fixture_mode=False):
        if planner is not None or program is not None:
            raise ContractError("DYNAMIC_FIXED_METHOD_NO_PROVIDER_OR_REPLACEMENT")
        super().__init__("full_h", None, load_program(fixed_program()), fixture_mode)
        self.analytic_score_count = 0
        self.analytic_score_log = []
        self.decisions = []
        self._scores_left = None
        self._predictions = {}

    @property
    def selection_uses_model(self):
        return False

    def _budget(self, quota):
        value = quota.get("analytic_scores_left")
        if type(value) is not int or value < 0:
            raise ContractError("ANALYTIC_SCORE_QUOTA_REQUIRED")
        self._scores_left = value if self._scores_left is None else min(self._scores_left, value)
        return {**deepcopy(quota), "analytic_scores_left": self._scores_left}

    def generate(self, state, quota):
        before = self.analytic_score_count
        batch = super().generate(state, self._budget(quota))
        batch.update(analytic_scores_used=self.analytic_score_count - before,
                     analytic_score_count=self.analytic_score_count,
                     analytic_scores_left=self._scores_left)
        return batch

    def select(self, state, batch, quota):
        before = self.analytic_score_count
        choice = super().select(state, batch, self._budget(quota))
        choice.update(analytic_scores_used=self.analytic_score_count - before,
                      analytic_score_count=self.analytic_score_count,
                      analytic_scores_left=self._scores_left)
        if choice.get("status") == "READY":
            choice["selection_control"]["policy"] = VERSION
        return choice

    def _ask(self, site, ctx):
        # These are internal developer-method dispatches, never planner callbacks.
        if site == "DYNAMIC-STOP":
            passed = _passed(ctx["state"])
            return {"stop": passed or ctx["quota"].get("remaining_actions", 0) < 1
                    or ctx["state"].get("applicability") == "OUT_OF_SCOPE",
                    "reason": "retain executed valid PASS" if passed else "scope or action budget",
                    "scope": "current executed Task/Design only"}
        if site == "DYNAMIC-GENERATE":
            return self._generate(ctx)
        if site == "DYNAMIC-SELECT":
            return self._select(ctx)
        if site == "DYNAMIC-UPDATE":
            return self._update_relations(ctx)
        raise ContractError("DYNAMIC_UNEXPECTED_CALLBACK:" + site)

    def _phase(self, state):
        memory = state.get("strategy", {}).get("dynamic_repair", {})
        if (memory.get("task_sha256") == digest(state["task"])
                and memory.get("design_sha256") == digest(state["design"])):
            return deepcopy(memory.get("phase_facts", {})), True
        return {}, False

    def _predict(self, task, design, phase):
        key = digest({"version": VERSION, "task": task, "design": design, "phase_facts": phase})
        if key in self._predictions:
            return deepcopy(self._predictions[key])
        if not self._scores_left:
            return None
        self._scores_left -= 1
        self.analytic_score_count += 1
        record = {"index": self.analytic_score_count, "input_sha256": key,
                  "task_sha256": digest(task), "design_sha256": digest(design),
                  "phase_facts_sha256": digest(phase)}
        self.analytic_score_log.append(record)
        try:
            prediction = predict_candidate(task, design, phase_facts=phase or None)
            if not isinstance(prediction, dict):
                raise ContractError("DYNAMIC_PREDICTION_OBJECT_REQUIRED")
            if prediction.get("service_verdict", "UNKNOWN") != "UNKNOWN":
                raise ContractError("APPROXIMATION_CANNOT_ASSERT_SERVICE_PASS")
            prediction = deepcopy(prediction)
            record.update(status="SCORED", prediction_sha256=digest(prediction))
        except Exception as exc:
            record.update(status="ERROR", error=type(exc).__name__)
            raise
        self._predictions[key] = prediction
        return deepcopy(prediction)

    def _simple_repairs(self, state, phase):
        task, design = state["task"], state["design"]
        domain = task.get("design_domain", {})
        sensor = task.get("sensor", {})
        offsets = sensor.get("bounce_offsets_s", [])
        service = phase.get("service", {})
        if service.get("public_check", {}).get("verdict") != "FAIL":
            return []
        out = []
        # A powered contact stable beyond the declared entire bounce burst is
        # a conditional direct information repair, not an energy/root-cause claim.
        if offsets and all(_number(t) for t in offsets) and "debounce_s" in domain:
            burst = max(offsets) - min(offsets)
            if design.get("debounce_s", math.inf) <= burst:
                quiet = max(burst, task.get("service", {}).get("stable_s", burst))
                debounce = math.nextafter(quiet, math.inf)
                if domain["debounce_s"]["min"] <= debounce <= domain["debounce_s"]["max"]:
                    out.append(("local-contact-window", {**design, "debounce_s": debounce}, "local-rule"))
        counts = service.get("activity_counts", {})
        if ("persistent_queue" in domain and design.get("persistent_queue") is False
                and counts.get("brownout", 0) > 0 and counts.get("save_commit", 0) > 0):
            out.append(("local-durable-state", {**design, "persistent_queue": True}, "local-rule"))
        return out

    def _proposals(self, state, phase, current_prediction):
        task, design = state["task"], state["design"]
        domain, load = task.get("design_domain", {}), task.get("components", {})
        required = {"capacitance_f", "esr_ohm", "startup_v", "brownout_v", "tx_gate_v"}
        if not required <= set(domain):
            return []
        qboot = load.get("boot_a", 0) * load.get("boot_s", 0)
        qservice = load.get("tx_a", 0) * load.get("tx_s", 0) + 2 * load.get("write_a", 0) * load.get("write_s", 0)
        esr = domain["esr_ohm"]["min"]
        brown = design["brownout_v"]
        peak_current = max(load.get("boot_a", 0), load.get("write_a", 0), load.get("tx_a", 0))
        peak_motion = _motion_bound(task)
        mechanisms = _geometry(task, design)
        intervals = current_prediction.get("repair_intervals", {})
        cap_interval = intervals.get("capacitance_f", {})
        failed = set(phase.get("failed_phases", []))
        candidates = self._simple_repairs(state, phase)
        if design["esr_ohm"] != esr:
            candidates.append(("local-load-drop", {**design, "esr_ohm": esr}, "local"))
        # Current geometry is always considered before source restructuring.
        source_options = [("local-power", design.get("mechanism", {}), "local")]
        source_options += [("joint-source-storage", m, "joint") for m in mechanisms[:2]]
        for label, mechanism, family in source_options:
            m = {**DEFAULT_MECHANISM, **mechanism}
            ceiling = min(load.get("max_v", math.inf), max(task.get("initial", {}).get("capacitor_v", 0),
                          m["generator_constant_vs_per_m"] * m["stroke_m"] * (peak_motion or 0) - m["rectifier_drop_v"]))
            headroom = ceiling - brown - peak_current * esr
            if headroom <= 0 or qservice <= 0:
                continue
            # Conditional no-source hold-up allocation; current-dependent source
            # feedback is recomputed by predict_candidate for each full design.
            cap_lower = _clamp((qservice + qboot) / (headroom / 2), domain["capacitance_f"])
            # Executed failed phases choose which computable interval to use.
            # The lower bound is conditional on old predicted entry voltage;
            # it proposes a new point which is always re-predicted below.
            if failed & {"TX", "SAVE", "ACK"}:
                observed_bound = cap_interval.get("conditional_no_source_lower_f")
                if _number(observed_bound):
                    cap_lower = _clamp(max(cap_lower, observed_bound), domain["capacitance_f"])
            cap_upper = domain["capacitance_f"]["max"]
            optimistic_upper = cap_interval.get("optimistic_cold_start_upper_f")
            if family == "local" and "BOOT" in failed and _number(optimistic_upper):
                cap_upper = min(cap_upper, max(domain["capacitance_f"]["min"], optimistic_upper))
            cap_balanced = math.sqrt(cap_lower * cap_upper)
            for cap, kind in ((cap_balanced, "balanced"), (cap_lower, "hold-up")):
                proposed = {**deepcopy(design), "esr_ohm": esr,
                            "capacitance_f": _clamp(cap, domain["capacitance_f"]),
                            "startup_v": _clamp(max(domain["startup_v"]["min"],
                                brown + load.get("boot_a", 0) * esr + qboot / cap
                                + load.get("max_v", 0) / load.get("leakage_ohm", math.inf) * load.get("boot_s", 0) / cap), domain["startup_v"]),
                            "tx_gate_v": _clamp(max(domain["tx_gate_v"]["min"],
                                brown + load.get("tx_a", 0) * esr + qservice / cap), domain["tx_gate_v"])}
                if family == "joint":
                    proposed["mechanism"] = deepcopy(mechanism)
                candidates.append((label + "-" + kind, proposed, family))
        # Interleave local and joint alternatives before scoring exhausts quota.
        candidates.sort(key=lambda item: (item[2] != "local-rule", "hold-up" in item[0], item[0] != "local-load-drop", item[0]))
        if ("BOOT" in failed or "TX" in failed) and "persistent_queue" in domain and not design.get("persistent_queue"):
            candidates.append(("local-state-retention", {**design, "persistent_queue": True}, "local"))
        return candidates

    def _refuted(self, state, design):
        memory = state.get("strategy", {}).get("dynamic_repair", {})
        point = {"task_sha256": digest(state["task"]), "design_sha256": digest(design)}
        return any(all(row.get(key) == value for key, value in point.items())
                   for row in memory.get("executed_failures", []))

    def _generate(self, ctx):
        state, quota = ctx["state"], ctx["quota"]
        phase, consumed = self._phase(state)
        current = self._predict(state["task"], state["design"], phase)
        if current is None:
            return {"status": "INSUFFICIENT_EVIDENCE", "reason": "Analytic score quota exhausted; no unscored candidate dispatch."}
        cap = min(64, max(0, int(quota.get("max_candidates", 16))))
        viable, excluded, seen = [], [], set()
        for label, proposed, family in self._proposals(state, phase, current):
            if len(viable) >= cap:
                break
            actual = _actual(state, proposed)
            if not actual["design_patch"] or digest(actual) in seen:
                continue
            seen.add(digest(actual))
            try:
                common_contract_check(state, actual, quota)
            except (ContractError, KeyError, TypeError) as exc:
                excluded.append({"actual_input": actual, "reason": str(exc)})
                continue
            facts = candidate_facts(state, actual)
            bad = _relations(facts)
            if bad:
                excluded.append({"actual_input": actual, "necessary_failures": bad})
                continue
            design = {**state["design"], **actual["design_patch"]}
            if self._refuted(state, design):
                excluded.append({"actual_input": actual, "reason": "Exact executed valid FAIL; no family exclusion"})
                continue
            prediction = self._predict(state["task"], design, phase)
            if prediction is None:
                break
            if prediction.get("necessary_failures") or prediction.get("prediction_status") == "REJECT_NECESSARY":
                excluded.append({"actual_input": actual, "necessary_failures": prediction.get("necessary_failures", []),
                                 "prediction_status": prediction.get("prediction_status")})
                continue
            gain = prediction.get("score", 0) - current.get("score", 0) if _number(prediction.get("score")) and _number(current.get("score")) else None
            candidate = {"id": label + "-" + digest(actual)[:12], "target": "current coupled service",
                         "operation": actual["operation"], "actual_input": actual,
                         "expected_state_change": ("Direct local contact/state repair from declared bounce/quiet window or saved-state/reset evidence; preserve power and source." if family == "local-rule" else "Conditional phase repair derived from Task load charge, source voltage, geometric intervals and current-design bus feedback; execute to distinguish it from the previous failure."),
                         "prediction_or_unknown": "UNKNOWN", "dynamic_prediction": prediction,
                         "observation_branches": ["If the public valid service passes, retain the executed design.",
                             "If BOOT/capture still fails, distinguish charging arrival time from hold-up capacity.",
                             "If TX/ACK fails, use the newly observed terminal margin and queue/phase trace; do not infer a unique cause."],
                         "affected_constraints": ["BOOT/capture timing", "TX/ACK continuity", "geometry/force", "full service"],
                         "validity_conditions": ["Same public Task and source model", "Approximate prediction is conditional, not formal PASS", "New source-bus feedback computed for this design"],
                         "cost_bound": 1, "repair_family": family,
                         "rank_components": {"approximate_score": prediction.get("score"), "expected_increment": gain,
                             "minimum_phase_margin_v": min((p["terminal_margin_v"] for p in prediction.get("phase_predictions", []) if _number(p.get("terminal_margin_v"))), default=None),
                             "minimum_deadline_slack_s": min((p["deadline_slack_s"] for p in prediction.get("phase_predictions", []) if _number(p.get("deadline_slack_s"))), default=None),
                             "discrimination_value": 1 / max(1, len(actual["design_patch"])),
                             "changed_fields": len(actual["design_patch"]), "action_cost": 1},
                         "update_phase_facts_sha256": digest(phase), "update_consumed": consumed}
            viable.append(candidate)
        self.decisions.append({"site": "Generate", "update_consumed": consumed,
                               "phase_facts_sha256": digest(phase), "failed_phases": phase.get("failed_phases", []),
                               "repair_intervals": current.get("repair_intervals", {}),
                               "current_prediction": current, "excluded": excluded,
                               "emitted_actual_inputs": [c["actual_input"] for c in viable]})
        return {"status": "OK", "candidates": viable}

    def _select(self, ctx):
        state, quota = ctx["state"], ctx["quota"]
        phase, consumed = self._phase(state)
        viable, excluded = [], []
        for candidate in ctx["candidates"]:
            actual = candidate.get("actual_input", {})
            try:
                common_contract_check(state, actual, quota)
                if candidate.get("cost_bound", math.inf) > quota.get("remaining_cost", 0):
                    raise ContractError("CANDIDATE_COST_BOUND")
                bad = _relations(candidate_facts(state, actual))
                if bad:
                    excluded.append({"id": candidate["id"], "necessary_failures": bad})
                    continue
                design = {**state["design"], **actual.get("design_patch", {})}
                if self._refuted(state, design):
                    excluded.append({"id": candidate["id"], "reason": "Exact executed valid FAIL"})
                    continue
                prediction = self._predict(state["task"], design, phase)
                if prediction is None or prediction.get("necessary_failures") or prediction.get("prediction_status") == "REJECT_NECESSARY":
                    excluded.append({"id": candidate["id"], "reason": "Unscored or necessary condition failed"})
                    continue
                score = prediction.get("score")
                if not _number(score):
                    score = -1e100
                # A sufficient local alternative may be selected without any
                # compulsory source restructure. Equal predicted scores favor it.
                change_count = len(actual.get("design_patch", {}))
                # Nonnegative approximate all-phase margins permit trying a
                # simpler repair first; they still cannot assert service PASS.
                local = "mechanism" not in actual.get("design_patch", {})
                margins = [p["terminal_margin_v"] for p in prediction.get("phase_predictions", [])
                           if p.get("phase") in set(phase.get("failed_phases", [])) and _number(p.get("terminal_margin_v"))]
                failed_margin = min(margins, default=0)
                counts = phase.get("service", {}).get("activity_counts", {})
                direct_rule = (candidate.get("repair_family") == "local-rule"
                               and not phase.get("failed_phases") and counts.get("wire_complete", 0) > 0)
                rank = (int(direct_rule), int(score >= 0), int(local) if score >= 0 else 0,
                        -change_count if score >= 0 else score,
                        score, failed_margin,
                        candidate.get("rank_components", {}).get("expected_increment") or 0,
                        candidate.get("rank_components", {}).get("discrimination_value", 0),
                        -candidate.get("cost_bound", 1), -change_count)
                viable.append((rank, candidate, prediction))
            except (ContractError, KeyError, TypeError) as exc:
                excluded.append({"id": candidate.get("id"), "reason": str(exc)})
        self.decisions.append({"site": "Select", "update_consumed": consumed, "excluded": excluded,
                               "ranking": [{"id": c["id"], "rank": list(rank), "prediction": pred} for rank, c, pred in viable]})
        if not viable:
            return {"status": "INSUFFICIENT_EVIDENCE", "reason": "No affordable scored candidate passes necessary checks; finite set only."}
        rank, chosen, prediction = max(viable, key=lambda row: row[0])
        return {"selected_id": chosen["id"],
                "selection_basis": "Necessary checks first, then conditional phase score/increment, discrimination, cost and edit count; no independent service PASS.",
                "expected_discrimination_or_gain": {"rank": list(rank), "prediction": prediction,
                                                    "scope": "current Task/Design; original consumer must execute"}}

    def _update_relations(self, ctx):
        state, result = ctx["state"], ctx["result"]
        phase = extract_phase_facts(state["task"], state["design"], result)
        memory = {"version": VERSION, "task_sha256": digest(state["task"]),
                  "design_sha256": digest(state["design"]), "phase_facts": phase,
                  "source_result_sha256": result.get("result_sha256"),
                  "unique_cause": False}
        previous = state.get("strategy", {}).get("dynamic_repair", {})
        failures = deepcopy(previous.get("executed_failures", []))
        if (result.get("execution_status") in SUCCESS and result.get("model_valid") is True
                and result.get("public_check", {}).get("verdict") == "FAIL"):
            failures.append({"task_sha256": memory["task_sha256"], "design_sha256": memory["design_sha256"],
                             "result_sha256": result.get("result_sha256")})
        memory["executed_failures"] = failures[-16:]
        strategy = deepcopy(state.get("strategy", {}))
        strategy["dynamic_repair"] = memory
        relations = deepcopy(phase.get("relations", []))
        return {"strategy": strategy,
                "hypotheses": (deepcopy(state.get("hypotheses", [])) + relations)[-64:],
                "invalidated": deepcopy(state.get("invalidated", [])),
                "next_evidence": {"failed_phases": phase.get("failed_phases", []),
                                  "competing_explanations": phase.get("competing_explanations", []),
                                  "scope": phase.get("scope"), "unique_cause": False}}

    def update(self, state, decision, result, independent_assessment=None):
        start = len(self.program.calls)
        updated = super().update(state, decision, result, independent_assessment)
        # The original wrapper bypasses H-UPDATE for invalid/incomplete results.
        # Preserve those statuses while recording public phase/domain uncertainty.
        if not any(c["site"] == "H-UPDATE" for c in self.program.calls[start:]):
            patch = self._invoke("H-UPDATE", {"state": public_state(updated), "decision": decision,
                                              "result": updated["last_result"]}, lambda c: {})
            if set(patch) <= {"strategy", "hypotheses", "invalidated", "next_evidence"}:
                updated.update(patch)
        self.decisions.append({"site": "Update", "update_status": updated.get("update_status"),
                               "memory": deepcopy(updated.get("strategy", {}).get("dynamic_repair"))})
        return updated
