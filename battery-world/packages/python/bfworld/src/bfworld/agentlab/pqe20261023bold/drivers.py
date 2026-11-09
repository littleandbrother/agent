"""Thin original-driver adapters for a code parent and counted full evaluation.

S0 owns the actual consumer, cache, owner budgets, provider and PublicObjects.
This module only checks bindings, injects compact factual candidate results
into H-RANK and retains receipts. It does not execute science or bill a model.
"""
from copy import deepcopy

from ..pqe20261022.conditional_learning_methods import (
    ConditionalEpisodeDriver, ConditionalFormationDriver,
)
from ..pqe20261022.episode_methods import SUCCESS
from ..pqe20261022.methods import ContractError, digest, public_state
from .contracts import (
    FORMATION_GUIDANCE, VERSION, compact_feedback, validate_full_candidate_batch,
)


class BoldFormationDriver(ConditionalFormationDriver):
    """Original G path, same six H sites and budget for ordinary/attribution."""

    def _instructions(self, request):
        return super()._instructions(request) + "\nBOLD EXECUTABLE PARENT: " + FORMATION_GUIDANCE


class BoldEpisodeDriver(ConditionalEpisodeDriver):
    """Expose complete candidate facts to H-RANK before selecting one action.

    full_evaluator(request) is the S0-owned original consumer broker. It must
    return one fully accounted public result/ref per generated candidate plus
    a fresh owner_budget_after. The selected result is reused exactly by S0's
    ordinary update(result) call; no candidate is silently free or simulated.
    """

    def __init__(self, *args, full_evaluator, initial_public_object_ref, **kwargs):
        if not callable(full_evaluator):
            raise ContractError("FULL_EVALUATOR_CALLBACK_REQUIRED")
        state = deepcopy(kwargs.get("initial_state"))
        if not isinstance(state, dict) or not isinstance(state.get("last_result"), dict):
            raise ContractError("INITIAL_PUBLIC_FAIL_STATE_REQUIRED")
        state["last_result"] = compact_feedback(state["last_result"], initial_public_object_ref)
        kwargs["initial_state"] = state
        limits = kwargs.get("limits")
        if not isinstance(limits, dict) or limits.get("new_numerical_inputs") != 4:
            raise ContractError("BOLD_FOUR_CANDIDATE_LIMIT_REQUIRED")
        self.full_candidates_evaluated = 0
        super().__init__(*args, **kwargs)
        self.full_evaluator = full_evaluator
        self.full_candidate_evaluations = []
        self._current_rank_results = []
        original_invoke = self.harness._invoke
        original_select = self.harness.select

        def invoke_with_rank_facts(site, ctx, default):
            if site == "H-RANK":
                ctx = {**ctx, "full_candidate_results": deepcopy(self._current_rank_results)}
            return original_invoke(site, ctx, default)

        def evaluate_then_select(state, batch, quota):
            candidates = batch.get("candidates", [])
            if not candidates:
                return original_select(state, batch, quota)
            if self.full_candidates_evaluated + len(candidates) > 4:
                raise ContractError("FOUR_FULL_CANDIDATES_PER_SOLVE_CAP")
            request = {"episode_id": self.episode_id, "condition": self.condition,
                       "state": public_state(state), "candidates": deepcopy(candidates),
                       "quota": deepcopy(quota), "maximum_full_candidates": 4,
                       "original_consumer_required": True}
            envelope = self.full_evaluator(deepcopy(request))
            compact = validate_full_candidate_batch(candidates, envelope, state=state)
            self._current_rank_results = compact
            self.full_candidates_evaluated += len(compact)
            self.numerical_inputs += sum(x["accounting"]["numerical_inputs"] for x in compact)
            self.tool_calls += sum(x["accounting"]["tool_calls"] for x in compact)
            if (self.numerical_inputs > self.limits["new_numerical_inputs"] or
                    self.tool_calls > self.limits["tool_calls"]):
                raise ContractError("FULL_CANDIDATE_EPISODE_CAP_EXCEEDED")
            self.owner_budget = deepcopy(envelope["owner_budget_after"])
            self.owner_snapshot_base = {
                "provider_requests_remaining": len(self.harness.usage_ledger),
                "reserve_usd_remaining": sum(x.get("usage", {}).get("cost", 0) or 0
                                             for x in self.harness.usage_ledger),
                "tool_calls_remaining": self.tool_calls,
                "new_numerical_inputs_remaining": self.numerical_inputs,
                "wall_s_remaining": self._elapsed_s(),
            }
            self.output_snapshot_base_used = self._output_tokens_used()
            self.full_candidate_evaluations.append({
                "candidate_ids": [x["candidate_id"] for x in compact],
                "result_bindings": [{"candidate_id": x["candidate_id"],
                    "actual_input_digest": x["actual_input_digest"],
                    "result_sha256": x["public_result"]["result_sha256"],
                    "public_object_ref": x["public_object_ref"],
                    "execution_status": x["public_result"]["execution_status"],
                    "model_valid": x["public_result"].get("model_valid"),
                    "public_check": x["public_result"].get("public_check"),
                    "accounting": x["accounting"]} for x in compact],
                "owner_budget_after": deepcopy(self.owner_budget),
            })
            try:
                decision = original_select(state, batch, self._quota())
                if decision.get("status") == "READY":
                    selected = next(x for x in compact if x["candidate_id"] == decision["selected_id"])
                    decision["pre_evaluation"] = {
                        "candidate_id": selected["candidate_id"],
                        "actual_input_digest": selected["actual_input_digest"],
                        "result_sha256": selected["public_result"]["result_sha256"],
                        "public_object_ref": selected["public_object_ref"],
                        "exact_reuse_required": True,
                    }
                return decision
            finally:
                self._current_rank_results = []

        self.harness._invoke = invoke_with_rank_facts
        self.harness.select = evaluate_then_select

    def _quota(self):
        quota = super()._quota()
        quota["max_candidates"] = min(quota["max_candidates"],
                                      max(0, 4 - self.full_candidates_evaluated))
        return quota

    def _elapsed_s(self):
        import time
        return time.monotonic() - self.started_at

    def _instructions(self, request):
        return super()._instructions(request) + (
            "\nBOLD FULL-CANDIDATE CONTRACT: Up to four generated legal candidates "
            "are each evaluated by the original complete consumer before H-RANK. "
            "H-RANK receives only compact PUBLIC results and original PublicObject refs "
            "in full_candidate_results; every evaluation is charged by the S0 owner. "
            "Model-valid public PASS is the only complete service success. Software "
            "formation screens have no full results and must retain UNKNOWN."
        )

    def apply_initial_update(self, budget_snapshot=None):
        """Consume one bound, complete PUBLIC initial result, PASS or FAIL.

        The new tasks were fixed before execution. A legitimate initial PASS
        must enter the same real H-UPDATE and H-STOP path, rather than causing
        task replacement or being excluded from the comparison.
        """
        if self.initial_update_receipt is not None or self.steps or self.pending is not None:
            raise ContractError("INITIAL_UPDATE_ALREADY_ATTEMPTED_OR_EPISODE_STARTED")
        result = deepcopy(self.state.get("last_result", {}))
        if (result.get("execution_status") not in SUCCESS or result.get("model_valid") is not True
                or result.get("public_check", {}).get("verdict") not in {"PASS", "FAIL"}
                or result.get("design") != self.state.get("design")
                or result.get("task_id") != self.state.get("task", {}).get("task_id")):
            raise ContractError("QUALIFIED_BOUND_INITIAL_PUBLIC_RESULT_REQUIRED")
        if budget_snapshot is not None:
            if ("output_tokens_remaining" in budget_snapshot and
                    (type(budget_snapshot["output_tokens_remaining"]) is not int or
                     budget_snapshot["output_tokens_remaining"] < 0)):
                raise ContractError("OUTPUT_TOKEN_REMAINDER_MUST_BE_NONNEGATIVE_INT")
            self.owner_budget = deepcopy(budget_snapshot)
            self.owner_snapshot_base = {
                "provider_requests_remaining": len(self.harness.usage_ledger),
                "reserve_usd_remaining": sum(r.get("usage", {}).get("cost", 0) or 0
                                             for r in self.harness.usage_ledger),
                "tool_calls_remaining": self.tool_calls,
                "new_numerical_inputs_remaining": self.numerical_inputs,
                "wall_s_remaining": self._elapsed_s(),
            }
            self.output_snapshot_base_used = self._output_tokens_used()
        self.harness.quota = self._quota()
        reason = self._stop_reason(self._quota(), needs_model=self.harness.selection_uses_model,
                                   needs_action=False)
        if reason:
            self.finish(reason)
            return {"status": "STOPPED", "reason": reason}
        before = len(self.harness.program.calls)
        callback_start = len(self.callback_records)
        design = deepcopy(self.state["design"])
        self.state = self.harness.update(self.state, {
            "source": "EXTERNALLY_SUPPLIED_COMMON_INITIAL_RESULT",
            "autonomous_choice": False, "new_execution": False,
        }, result)
        self.initial_update_receipt = {
            "status": self.state.get("update_status"),
            "initial_verdict": result["public_check"]["verdict"],
            "result_sha256": result.get("result_sha256"),
            "public_result_digest": digest(result),
            "site_calls": deepcopy(self.harness.program.calls[before:]),
            "callback_start": callback_start, "callback_end": len(self.callback_records),
            "parent_design_preserved": self.state.get("design") == design,
            "submitted_candidate": False, "new_tool_or_numerical_execution": False,
        }
        if self.state.get("update_status") != "UPDATED" or self.harness.blocked:
            self.finish("INITIAL_UPDATE_" + str(self.state.get("update_status", "UNKNOWN")))
        return deepcopy(self.initial_update_receipt)

    def next(self, budget_snapshot=None):
        if (self.termination is None and self.pending is None and
                (self.initial_update_receipt or {}).get("status") == "UPDATED" and
                self.full_candidates_evaluated >= 4 and
                self.state.get("last_result", {}).get("public_check", {}).get("verdict") != "PASS"):
            self.finish("FULL_CANDIDATE_CAP_REACHED")
        return super().next(budget_snapshot)

    def update(self, public_result, public_object_ref=None):
        if not public_object_ref:
            raise ContractError("EXECUTED_PUBLIC_OBJECT_REF_REQUIRED")
        compact = compact_feedback(public_result, public_object_ref)
        pending = self.pending
        if pending is not None:
            pre = pending.get("pre_evaluation", {})
            if not pre or pre.get("result_sha256") != compact.get("result_sha256"):
                raise ContractError("SELECTED_EXACT_EVALUATION_REUSE_REQUIRED")
            if pre.get("public_object_ref") != public_object_ref:
                raise ContractError("SELECTED_PUBLIC_OBJECT_REF_CHANGED")
            if pre.get("actual_input_digest") != digest(pending["actual_input"]):
                raise ContractError("SELECTED_ACTUAL_INPUT_BINDING_CHANGED")
            if compact.get("usage", {}).get("numerical_inputs") != 0:
                raise ContractError("SELECTED_REUSE_MUST_COST_ZERO_NEW_NUMERICAL_INPUTS")
        return super().update(compact)

    def transcript(self):
        return {**super().transcript(), "bold_contract": VERSION,
                "full_candidates_evaluated": self.full_candidates_evaluated,
                "full_candidate_evaluations": deepcopy(self.full_candidate_evaluations),
                "compact_feedback_boundary": "original public Result/ref saved by S0; hooks see bounded summary"}
