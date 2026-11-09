"""Developer-fixed conditional G/S/U over the existing episode consumer.

No provider, joint solver, evaluator, task/candidate identity table or successful
design constants are defined here. Shared facts are available to all conditions.
"""
from copy import deepcopy
import math

from .methods import Harness, ContractError, digest, load_program, seed_program, _path
from .episode_methods import EpisodeDriver as OriginalEpisodeDriver, SUCCESS
from .decision_facts import candidate_facts

VERSION = "H-decision-conditional-v1"
CONDITIONS = {"strong_generic", "full_h", "improved_full_h"}
POLICY = (
    "Consume the shared necessary geometry and supply/storage facts before selecting. "
    "A failed necessary condition rules out that candidate, not its whole family. "
    "Generate conditional finite repairs or a discriminating information action when "
    "the unresolved explanation would change the design decision. Preserve a sufficient "
    "direct local repair; joint edits are legal and fewer edited parameters is not an "
    "absolute priority. Predict affected engineering relations with conditions and "
    "UNKNOWNs, rather than equating one packet or model validity with full service. "
    "Read strategy.decision_memory from prior executed results; do not repeat a scoped "
    "refuted input unchanged, infer unique cause from joint edits, or exclude a family "
    "from one failed point."
)


def fixed_program():
    p = seed_program()
    p.update(program_id=VERSION, artifact_version="1", origin="DEVELOPER_FIXED_H",
             adoption="FIXED_DEVELOPMENT_CONDITION")
    p["prompts"] = {"H-GEN": POLICY, "H-RANK": POLICY}
    p["code"] = {
        "H-GEN": 'def h_gen(ctx, ask):\n    early = ask("DECISION-STOP", ctx)\n    if early.get("status") == "STOPPED":\n        return early\n    generated = ask("H-GEN", ctx)\n    return ask("DECISION-GENERATE", {"state":ctx["state"], "quota":ctx["quota"], "generated":generated})\n',
        "H-RANK": 'def h_rank(ctx, ask):\n    chosen = ask("DECISION-SELECT", ctx)\n    if chosen.get("status") == "NEEDS_MODEL":\n        return ask("H-RANK", chosen["context"])\n    return chosen\n',
        "H-UPDATE": 'def h_update(ctx, ask):\n    return ask("DECISION-UPDATE", ctx)\n',
    }
    return p


def _design(state, actual):
    return {**state.get("design", {}), **actual.get("design_patch", {})}


def _scope(state, actual):
    return {"task_sha256":digest(state.get("task", {})), "design_sha256":digest(_design(state, actual))}


def _memory(state):
    return state.get("strategy", {}).get("decision_memory", [])


def _relations(facts):
    """Normalize A's public, necessary-condition relation records."""
    errors = {"cam_diameter_m":"assembly_envelope_exceeded", "maximum_pressure_angle_deg":"cam_pressure_angle_exceeded"}
    checks = facts.get("domain_checks", facts.get("checks", []))
    if isinstance(checks, dict):
        checks = [{"name":k, **v} for k,v in checks.items()]
    return [{**r, "relation_id":r.get("relation_id", r.get("name")),
             "domain_error":r.get("domain_error", errors.get(r.get("name")))}
            for r in checks + facts.get("relations", [])]


def _refuted_relations(facts):
    return [r for r in _relations(facts) if r.get("necessary") is True and r.get("status") == "FAIL"]


def _repeated_refutations(state, actual):
    scope = _scope(state, actual)
    return [m for m in _memory(state) if m.get("scope") == scope
            and m.get("classification") == "REFUTED"
            and m.get("relation_id") == "complete_service"]


def _annotate(state, candidate):
    c = deepcopy(candidate)
    f = candidate_facts(state, c["actual_input"])
    c["decision_relations"] = deepcopy(_relations(f))
    c["decision_scope"] = _scope(state, c["actual_input"])
    return c, f


def _screen(state, candidate, facts):
    if candidate["actual_input"].get("operation") in {"observe", "select", "report"}:
        return [], []
    return _refuted_relations(facts), _repeated_refutations(state, candidate["actual_input"])


def _stop(state):
    r = state.get("last_result", {})
    if r.get("execution_status") in SUCCESS and r.get("model_valid") is True and r.get("public_check", {}).get("verdict") == "PASS":
        return {"status":"STOPPED", "conclusion":{"verdict":"PASS", "basis":"Current completed model-valid public check passes every declared service.", "scope":"Current executed design and Task only; no family or statistical conclusion."}}
    return {"status":"CONTINUE"}


class DecisionHarness(Harness):
    def __init__(self, condition, planner=None, program=None, fixture_mode=False):
        self.declared_condition = condition
        if condition not in CONDITIONS:
            raise ContractError("DECISION_CONDITION")
        if condition == "improved_full_h" and program is not None:
            raise ContractError("FIXED_DECISION_PROGRAM_CANNOT_BE_REPLACED")
        super().__init__("full_h" if condition == "improved_full_h" else condition,
                         planner, load_program(fixed_program()) if condition == "improved_full_h" else program,
                         fixture_mode)
        self.decisions = []

    @property
    def selection_uses_model(self):
        # Improved hook may select deterministically; actual ask still checks
        # remaining request/token/cost quota if more than one candidate remains.
        return False if self.declared_condition == "improved_full_h" else super().selection_uses_model

    def _invoke(self, site, ctx, default):
        ctx = deepcopy(ctx)
        state = ctx.get("state", {})
        current = {"operation":"verify", "design_patch":{}, "problem_patch":{}}
        ctx["shared_decision_facts"] = {
            "current":candidate_facts(state, current),
            "candidates":[{"id":c["id"], "facts":candidate_facts(state, c["actual_input"])}
                          for c in ctx.get("candidates", [])],
        }
        return super()._invoke(site, ctx, default)

    def _ask(self, site, payload):
        if site == "DECISION-STOP":
            return _stop(payload["state"])
        if site == "DECISION-GENERATE":
            return self._generate(payload)
        if site == "DECISION-SELECT":
            return self._select(payload)
        if site == "DECISION-UPDATE":
            return self._typed_update(payload)
        if self.declared_condition == "improved_full_h" and self.quota.get("output_tokens_left", 1) <= 0:
            return {"status":"OUTPUT_TOKEN_BUDGET_EXHAUSTED"}
        return super()._ask(site, payload)

    def _generate(self, ctx):
        g = deepcopy(ctx["generated"])
        if g.get("status", "OK") != "OK":
            return g
        state = ctx["state"]
        raw = g.get("candidates", []) + g.get("experiment_candidates", [])
        candidates, excluded = [], []
        for candidate in raw:
            c = deepcopy(candidate)
            actual = c.get("actual_input", {})
            if not actual:
                candidates.append(c)  # Existing common contract diagnoses schema.
                continue
            reform = g.get("problem_reforms", {}).get(c.get("id"), {})
            actual["problem_patch"] = {**actual.get("problem_patch", {}), **reform}
            c["actual_input"] = actual
            c, facts = _annotate(state, c)
            violations, repeated = _screen(state, c, facts)
            if violations or repeated:
                excluded.append({"candidate":c, "relations":violations, "repeat_refutation":repeated})
            else:
                candidates.append(c)
        if not candidates and excluded:
            candidates = self._conditional_repairs(state, excluded, ctx["quota"])
        g.update(candidates=candidates, experiment_candidates=[], problem_reforms={})
        self.decisions.append({"site":"Generate", "excluded":[{"actual_input":e["candidate"]["actual_input"], "relations":e["relations"], "repeat_refutation":e["repeat_refutation"]} for e in excluded],
                               "emitted_actual_inputs":[c.get("actual_input") for c in candidates]})
        return g

    def _conditional_repairs(self, state, excluded, quota):
        # Implemented only from public relation coefficients, never reference
        # design values. Unknown relations cannot be used as numeric bounds.
        bounds = state.get("task", {}).get("design_domain", {}).get("mechanism", {}).get("editable", {})
        if not {"stroke_m", "cam_base_radius_m"} <= set(bounds):
            return []
        for entry in excluded:
            if not any(r.get("relation_id") in {"cam_diameter_m", "maximum_pressure_angle_deg"} for r in entry["relations"]):
                continue
            parent = deepcopy(entry["candidate"])
            actual = parent["actual_input"]
            relations = {r["relation_id"]:r for r in _relations(candidate_facts(state, actual))}
            diameter, angle = relations.get("cam_diameter_m", {}), relations.get("maximum_pressure_angle_deg", {})
            width, limit = diameter.get("bound", {}).get("maximum"), angle.get("bound", {}).get("maximum")
            # Clearance is a bound coefficient explicitly published with the
            # relation, not an optimized design parameter.
            clearance = diameter.get("clearance_m")
            if clearance is None:
                # Public frozen source_step: diameter=2*(base+stroke+0.002).
                # This is a model coefficient, never a successful design value.
                clearance = diameter.get("coefficients", {}).get("clearance_m", 0.002)
            if not all(isinstance(x, (int,float)) for x in (width, limit, clearance)):
                continue
            t = math.tan(math.radians(limit))
            if t <= 0:
                continue
            ratio = (math.sqrt(1 + 4 / (t*t)) - 1) / 2
            slo, shi = bounds["stroke_m"]
            rlo, rhi = bounds["cam_base_radius_m"]
            total = width / 2 - clearance
            maximum = min(shi, total-rlo, rhi/ratio, total/(1+ratio))
            if maximum < slo:
                continue
            proposed = _design(state, actual).get("mechanism", {})
            stroke = min(maximum, max(slo, proposed.get("stroke_m", slo)))
            low, high = max(rlo, ratio*stroke), min(rhi, total-stroke)
            if low > high:
                continue
            geometry = {**_design(state, actual).get("mechanism", {}),
                        "stroke_m":stroke, "cam_base_radius_m":(low+high)/2}
            actual.setdefault("design_patch", {})["mechanism"] = geometry
            parent.update(id="conditional-geometry-" + digest(actual)[:12],
                          expected_state_change="Retain proposed stroke if geometrically feasible; choose a base radius inside the simultaneous public envelope/pressure interval. Dynamic startup, TX and all service remain UNKNOWN.",
                          prediction_or_unknown="UNKNOWN")
            parent, facts = _annotate(state, parent)
            bad, repeated = _screen(state, parent, facts)
            if not bad and not repeated:
                parent["conditional_geometry_derivation"] = {"source_relations":[diameter, angle], "base_radius_feasible_interval_m":[low, high], "dynamic_service":"UNKNOWN"}
                return [parent]
        return []

    def _select(self, ctx):
        state, candidates = ctx["state"], ctx["candidates"]
        viable, excluded = [], []
        for candidate in candidates:
            facts = candidate_facts(state, candidate["actual_input"])
            violations, repeat = _screen(state, candidate, facts)
            if violations or repeat:
                excluded.append({"id":candidate["id"], "relations":violations, "repeat_refutation":repeat})
            else:
                viable.append(candidate)
        self.decisions.append({"site":"Select", "excluded":excluded, "remaining_actual_inputs":[c["actual_input"] for c in viable]})
        if not viable:
            return {"status":"INSUFFICIENT_EVIDENCE", "reason":"All submitted actions conflict with public necessary conditions or exact scoped refutations; no global exclusion."}
        if len(viable) == 1:
            return {"selected_id":viable[0]["id"], "selection_basis":"Only remaining candidate after public necessary-condition and scoped evidence checks.", "expected_discrimination_or_gain":"UNKNOWN; dynamic complete service still requires execution."}
        repairs = [c for c in viable if c["actual_input"].get("design_patch")]
        current_bad = _refuted_relations(candidate_facts(state, {"operation":"verify", "design_patch":{}, "problem_patch":{}}))
        if len(repairs) == 1 and current_bad:
            candidate = repairs[0]
            old_ids = {r["relation_id"] for r in current_bad}
            repaired = {r["relation_id"] for r in _relations(candidate_facts(state, candidate["actual_input"])) if r.get("status") == "PASS"}
            if old_ids & repaired:
                return {"selected_id":candidate["id"], "selection_basis":"One remaining design action removes a known necessary obstruction; supplied observation cannot add the already available bound. Execute its dynamic consequence without asserting full service.", "expected_discrimination_or_gain":"Conditional obstruction removed; full service UNKNOWN."}
        context = deepcopy(ctx)
        context["candidates"] = viable
        context["shared_decision_facts"]["candidates"] = [x for x in context["shared_decision_facts"]["candidates"] if any(c["id"] == x["id"] for c in viable)]
        return {"status":"NEEDS_MODEL", "context":context}

    def _typed_update(self, ctx):
        state, decision, result = ctx["state"], ctx["decision"], ctx["result"]
        candidate = decision.get("selected_candidate", {})
        scope = candidate.get("decision_scope") or _scope(state, {"design_patch":result.get("design", {}), "problem_patch":{}})
        complete = result.get("execution_status") in SUCCESS
        valid = result.get("model_valid") is True
        memory = deepcopy(_memory(state))
        relations = candidate.get("decision_relations")
        if relations is None:
            relations = _relations(candidate_facts(state, decision.get("actual_input", {})))
        claims = [{"relation_id":"complete_service", "kind":"service", "evidence_kind":"executed_point_feasibility_not_model_prediction"}, *relations]
        prediction = candidate.get("prediction_or_unknown")
        if isinstance(prediction, dict):
            claims.append({"relation_id":"selected_prediction", "kind":"prediction", "prediction":prediction})
        items = []
        for claim in claims:
            rid = claim.get("relation_id", "unidentified")
            if not complete:
                label = "NOT_EXECUTED"
            elif claim.get("kind") == "service":
                verdict = result.get("public_check", {}).get("verdict")
                label = "NOT_DISCRIMINATED" if not valid or verdict not in {"PASS", "FAIL"} else "SUPPORTED" if verdict == "PASS" else "REFUTED"
            elif claim.get("kind") == "prediction":
                p = claim["prediction"]
                observed = _path(result, p.get("metric", ""))
                expected, op = p.get("value"), p.get("operator")
                if not valid or observed is None:
                    label = "NOT_DISCRIMINATED"
                elif op == "eq":
                    label = "SUPPORTED" if observed == expected else "REFUTED"
                elif op in {"le", "ge"} and isinstance(observed, (int, float)) and isinstance(expected, (int, float)):
                    label = "SUPPORTED" if (observed <= expected if op == "le" else observed >= expected) else "REFUTED"
                else:
                    label = "NOT_DISCRIMINATED"
            else:
                code = claim.get("domain_error")
                label = ("REFUTED" if code in result.get("domain_errors", []) else "SUPPORTED") if code else "NOT_DISCRIMINATED"
            items.append({"relation_id":rid, "classification":label, "scope":scope,
                          "evidence_kind":claim.get("evidence_kind", claim.get("kind", "necessary_condition")),
                          "conditions":deepcopy(claim.get("conditions", [])),
                          "source":claim.get("source"),
                          "evidence_result":result.get("result_sha256"), "unique_cause":False})
        memory.extend(items)
        strategy = deepcopy(state.get("strategy", {}))
        strategy["decision_memory"] = memory[-64:]
        return {"strategy":strategy, "hypotheses":deepcopy(state.get("hypotheses", [])) + items,
                "invalidated":deepcopy(state.get("invalidated", [])),
                "next_evidence":{"scope":scope,"relations":items,"family_exclusion":False}}

    def update(self, state, decision, result, independent_assessment=None):
        updated = super().update(state, decision, result, independent_assessment)
        if self.declared_condition == "improved_full_h" and updated.get("update_status") in {"DOMAIN_UNKNOWN", "INCOMPLETE", "TOOL_ERROR"}:
            patch = self._invoke("H-UPDATE", {"state":updated,"decision":decision,"result":result}, lambda c:{})
            updated.update(patch)
        return updated


class DecisionEpisodeDriver(OriginalEpisodeDriver):
    def __init__(self, condition, planner_callback, **kwargs):
        if condition not in CONDITIONS:
            raise ContractError("DECISION_CONDITION")
        base = "full_h" if condition == "improved_full_h" else condition
        super().__init__(base, planner_callback, **kwargs)
        program = kwargs.get("program")
        self.condition = condition
        self.harness = DecisionHarness(condition, self._callback if planner_callback else None,
                                       program=program, fixture_mode=self.fixture_mode)

    def _instructions(self, request):
        text = super()._instructions(request)
        prompt = request.get("context", {}).get("site_prompt", "")
        return text + (" Developer-fixed decision policy: " + prompt if prompt else "")

    def transcript(self):
        t = super().transcript()
        improved = self.condition == "improved_full_h"
        t.update(decision_method_version=VERSION if improved else "original-" + self.condition,
                 developer_fixed_code_loaded=improved, model_generated_code_loaded=False,
                 generated_code_loaded=False, decision_consumption=deepcopy(self.harness.decisions))
        return t


EpisodeDriver = DecisionEpisodeDriver
