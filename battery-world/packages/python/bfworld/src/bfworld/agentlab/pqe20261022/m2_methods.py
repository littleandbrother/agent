"""M2 thin, pre-result feedback ablation and generic public-tool adapter.

Frozen M1 algorithms/science are imported, never changed. Public tools expose
facts and conditional predictions, not a candidate shortlist or chosen answer.
The caller owns model/tool/dynamic/global ledgers and common re-GEN policy.
"""
from copy import deepcopy

from .methods import (Harness, ContractError, digest, public_state, seed_program,
                      load_program)
from .dynamic_methods import DynamicRepairHarness, _passed
from .dynamic_relations import extract_phase_facts
from .decision_facts import candidate_facts
from .door_model import DEFAULT_MECHANISM, DOMAIN

VERSION = "M2-thin-feedback-tools-v1"
PUBLIC_TOOL_INSTRUCTION = (
    "The same full public engineering calculators available to M1 are available to you. "
    "At H-GEN or H-RANK you may return {status:'PUBLIC_TOOLS',tool_calls:[{id,name,arguments}]} "
    "to request phase_facts, predict_candidate, engineering_relations or public_detail. "
    "Tool results will be returned at the same decision site; then request more tools or "
    "return the ordinary candidate/selection/STOPPED JSON. Predict requires a complete "
    "hypothetical design. public_detail takes list and offset, at most64 public rows. "
    "Tools provide no recommendation or independent service PASS. You choose every "
    "proposal and final supplied candidate yourself. A rejected candidate is not a "
    "whole-domain impossibility. Model/tool/score limits remain in force."
)
TOOL_SCHEMA = {
    "phase_facts": {"arguments": {"result_sha256": "optional exact known result; default last"},
                    "returns": "All public phase/service relations and competing explanations; no ranking."},
    "predict_candidate": {"arguments": {"design": "complete hypothetical Design", "result_sha256": "optional prior public phase evidence; default last"},
                          "returns": "Frozen M1 conditional predictor including every phase, repair interval and limitation; service UNKNOWN."},
    "engineering_relations": {"arguments": {"design": "optional hypothetical Design; default current"},
                              "returns": "Public static/necessary relations, frozen source coefficients/domain, load/energy equations; no candidate or choice."},
    "public_detail": {"arguments": {"result_sha256": "optional known result; default last", "list": "trace|activity|records|packets|receiver_records", "offset": "nonnegative integer"},
                      "returns": "Up to64 original public rows and total/next offset; no hidden assessment."},
}


class M2Harness(DynamicRepairHarness):
    """F and U differ only at the single inherited phase-memory read boundary."""
    def __init__(self, feedback_enabled=True):
        if type(feedback_enabled) is not bool:
            raise ContractError("M2_FEEDBACK_SWITCH_BOOLEAN_REQUIRED")
        super().__init__()
        self.feedback_enabled = feedback_enabled

    def _phase(self, state):
        if not self.feedback_enabled:
            return {}, False
        return super()._phase(state)


def _generic_program():
    program = seed_program()
    program.update(program_id=VERSION + "-generic-common-stop", origin="DEVELOPER_TOOL_ADAPTER",
                   adoption="FIXED_M2_COMPARISON")
    program["code"] = {"H-STOP": 'def h_stop(ctx, ask):\n    return ask("M2-COMMON-STOP", ctx)\n'}
    return load_program(program)


class M2GenericHarness(Harness):
    """Strong generic planner with the original callback {payload, usage} shape.

    tool_call_count covers explicit public calculator/detail calls only. S0 adds
    formal consumer calls to enforce the combined24 tools. Exact score cache
    hits still count a tool request, but consume zero new analytic scores.
    """
    def __init__(self, model_call, fixture_mode=False):
        if not callable(model_call):
            raise ContractError("M2_MODEL_CALLBACK_REQUIRED")
        super().__init__("strong_generic", model_call, _generic_program(), fixture_mode)
        self._calculator = DynamicRepairHarness()
        self.tool_call_count = 0
        self.tool_call_log = []
        self._tools_left = None
        self.decisions = []

    @property
    def analytic_score_count(self):
        return self._calculator.analytic_score_count

    @property
    def analytic_score_log(self):
        return self._calculator.analytic_score_log

    @property
    def public_tool_call_count(self):
        return self.tool_call_count

    @property
    def public_tool_call_log(self):
        return self.tool_call_log

    def _budget(self, quota):
        q = self._calculator._budget(quota)
        left = q.get("public_tool_calls_left", q.get("remaining_actions"))
        if type(left) is not int or left < 0:
            raise ContractError("M2_PUBLIC_TOOL_QUOTA_REQUIRED")
        self._tools_left = left if self._tools_left is None else min(self._tools_left, left)
        return q

    def _counts(self, output, before):
        output.update(analytic_scores_used=self.analytic_score_count-before[0],
                      analytic_score_count=self.analytic_score_count,
                      analytic_scores_left=self._calculator._scores_left,
                      public_tool_calls_used=self.tool_call_count-before[1],
                      public_tool_call_count=self.tool_call_count,
                      public_tool_calls_left=self._tools_left)
        return output

    def generate(self, state, quota):
        before = self.analytic_score_count, self.tool_call_count
        return self._counts(super().generate(state, self._budget(quota)), before)

    def select(self, state, batch, quota):
        before = self.analytic_score_count, self.tool_call_count
        result = super().select(state, batch, self._budget(quota))
        if result.get("status") == "READY":
            design = {**public_state(state)["design"], **result["actual_input"].get("design_patch", {})}
            if self._calculator._refuted(public_state(state), design):
                result.update(status="INSUFFICIENT_EVIDENCE", actual_input=None,
                              resource_reservation=0, reason="Selected point repeats an exact public valid FAIL.")
        if result.get("status") == "READY" and not self._tools_left:
            result.update(status="TOOL_BUDGET_EXHAUSTED", actual_input=None,
                          resource_reservation=0, reason="No combined tool slot remains for formal execution.")
        return self._counts(result, before)

    def _known_result(self, state, identifier=None):
        results = [state.get("last_result", {})]
        results += [h.get("result", {}) for h in reversed(state.get("history", [])) if isinstance(h, dict)]
        results += [e.get("result", {}) for e in state.get("evidence", []) if isinstance(e, dict)]
        for result in results:
            if isinstance(result, dict) and "design" in result and "facts" in result:
                if identifier in (None, "last") or identifier == result.get("result_sha256"):
                    return deepcopy(result)
        raise ContractError("KNOWN_PUBLIC_RESULT_REQUIRED")

    def _tool(self, state, call):
        if not self._tools_left:
            raise ContractError("PUBLIC_TOOL_BUDGET_EXHAUSTED")
        self._tools_left -= 1
        self.tool_call_count += 1
        record = {"index": self.tool_call_count, "request": deepcopy(call),
                  "task_sha256": digest(state["task"]), "analytic_before": self.analytic_score_count}
        self.tool_call_log.append(record)
        try:
            if not isinstance(call, dict):
                raise ContractError("PUBLIC_TOOL_OBJECT_REQUIRED")
            name = call.get("name")
            args = call.get("arguments", {k:v for k,v in call.items() if k not in {"id", "name"}})
            if not isinstance(args, dict):
                raise ContractError("PUBLIC_TOOL_ARGUMENTS_OBJECT_REQUIRED")
            if name in {"phase_facts", "extract_phase_facts"}:
                result = self._known_result(state, args.get("result_sha256"))
                output = extract_phase_facts(state["task"], result["design"], result)
            elif name == "predict_candidate":
                design = args.get("design")
                if not isinstance(design, dict):
                    raise ContractError("PREDICTION_COMPLETE_DESIGN_REQUIRED")
                result = self._known_result(state, args.get("result_sha256"))
                phase = extract_phase_facts(state["task"], result["design"], result)
                output = self._calculator._predict(state["task"], design, phase)
                if output is None:
                    raise ContractError("ANALYTIC_SCORE_QUOTA_EXHAUSTED")
            elif name == "engineering_relations":
                design = deepcopy(args.get("design", state["design"]))
                if not isinstance(design, dict):
                    raise ContractError("RELATIONS_DESIGN_REQUIRED")
                hypothetical = {**state, "design": design, "problem": {
                    "active_variables": list(state["task"].get("design_domain", {})),
                    "groups": [], "fixed_choices": {}}}
                output = {"task_sha256": digest(state["task"]), "design_sha256": digest(design),
                          "hypothetical_facts": candidate_facts(hypothetical, {"operation":"verify", "design_patch":{}, "problem_patch":{}}),
                          "source_coefficients": deepcopy(DEFAULT_MECHANISM), "frozen_source_domain": deepcopy(DOMAIN),
                          "source_law": "i=max((abs(K*L*sin(2theta)*omega)-Vbus-Vrect)/Rcoil,0)",
                          "geometry_laws": {"diameter":"2*(base+stroke+0.002)",
                                            "pressure_angle":"atan(stroke/sqrt(base*(base+stroke)))"},
                          "storage_laws": ["Q=C*V", "E=0.5*C*V^2", "phase_charge=I*duration", "load_terminal=Vbus-Iphase*Rbranch"],
                          "conditions": ["Current-design source feedback must be recomputed after C or mechanism changes.",
                                         "Necessary/conditional relations never certify complete dynamic service."],
                          "recommendation": None, "service_verdict":"UNKNOWN"}
            elif name in {"public_detail", "detail"}:
                result = self._known_result(state, args.get("result_sha256"))
                key, offset = args.get("list"), args.get("offset", 0)
                if key not in {"trace", "activity", "records", "packets", "receiver_records"} or type(offset) is not int or offset < 0:
                    raise ContractError("PUBLIC_DETAIL_LIST_AND_OFFSET_REQUIRED")
                rows = result.get("facts", {}).get(key)
                if not isinstance(rows, list):
                    raise ContractError("PUBLIC_DETAIL_LIST_UNAVAILABLE")
                page = deepcopy(rows[offset:offset+64])
                output = {"result_sha256":result.get("result_sha256"), "list":key, "offset":offset,
                          "total":len(rows), "rows":page, "next_offset":offset+64 if offset+64 < len(rows) else None,
                          "visibility":"PUBLIC_RESULT_ONLY"}
            else:
                raise ContractError("UNKNOWN_PUBLIC_TOOL")
            record.update(status="OK", result_sha256=digest(output))
            return {"id":call.get("id"), "name":name, "status":"OK", "result":output}
        except Exception as exc:
            record.update(status="ERROR", error=str(exc))
            return {"id":call.get("id") if isinstance(call, dict) else None,
                    "status":"TOOL_ERROR", "error":str(exc)}
        finally:
            record["analytic_scores_used"] = self.analytic_score_count-record["analytic_before"]

    def _ask(self, site, payload):
        if site == "M2-COMMON-STOP":
            state = payload["state"]
            return {"stop":_passed(state) or state.get("applicability")=="OUT_OF_SCOPE" or payload["quota"].get("remaining_actions",0)<1,
                    "reason":"current executed PASS, scope or quota", "scope":"current Task/Design only"}
        if site not in {"H-GEN", "H-RANK"}:
            return super()._ask(site, payload)
        context = deepcopy(payload)
        state = context["state"]
        context.update(public_tool_instruction=PUBLIC_TOOL_INSTRUCTION, public_tools=deepcopy(TOOL_SCHEMA))
        for _ in range(12):  # Original provider/usage gate remains authoritative.
            response = super()._ask(site, context)
            if response.get("status") != "PUBLIC_TOOLS":
                return response
            calls = response.get("tool_calls")
            if not isinstance(calls, list) or not calls:
                return {"status":"INVALID_PUBLIC_TOOL_REQUEST"}
            if len(calls) > self._tools_left:
                return {"status":"PUBLIC_TOOL_BUDGET_EXHAUSTED"}
            results = [self._tool(state, call) for call in calls]
            context.setdefault("public_tool_results", []).extend(results)
            if any(result.get("status") == "TOOL_ERROR" for result in results):
                return {"status":"TOOL_ERROR", "public_tool_results":results,
                        "reason":"Retain public-tool failure; no internal model rescue."}
            context["quota"] = {**context["quota"], "analytic_scores_left":self._calculator._scores_left,
                                "public_tool_calls_left":self._tools_left}
        return {"status":"MODEL_REQUEST_LIMIT"}

    def _invoke(self, site, ctx, default):
        ctx = deepcopy(ctx)
        if site == "H-RANK":
            kept, rejected = [], []
            for candidate in ctx.get("candidates", []):
                actual = candidate.get("actual_input", {})
                design = {**ctx["state"]["design"], **actual.get("design_patch", {})}
                if self._calculator._refuted(ctx["state"], design):
                    rejected.append(candidate.get("id"))
                else:
                    kept.append(candidate)
            self.decisions.append({"site":"CommonExactRefutation", "rejected":rejected})
            if not kept:
                return {"status":"INSUFFICIENT_EVIDENCE", "reason":"All candidates repeat exact public valid-FAIL points; no family exclusion."}
            ctx["candidates"] = kept
        return super()._invoke(site, ctx, default)

    def update(self, state, decision, result, independent_assessment=None):
        updated = super().update(state, decision, result, independent_assessment)
        public = updated["last_result"]
        strategy = deepcopy(updated.get("strategy", {}))
        memory = deepcopy(strategy.get("dynamic_repair", {}))
        failures = deepcopy(memory.get("executed_failures", []))
        if (public.get("execution_status") in {"OK","COMPLETE","COMPLETED","SUCCESS"}
                and public.get("model_valid") is True and public.get("public_check",{}).get("verdict")=="FAIL"):
            failures.append({"task_sha256":digest(updated["task"]), "design_sha256":digest(updated["design"]),
                             "result_sha256":public.get("result_sha256")})
        memory["executed_failures"] = failures[-16:]
        strategy["dynamic_repair"] = memory
        updated["strategy"] = strategy
        return updated
