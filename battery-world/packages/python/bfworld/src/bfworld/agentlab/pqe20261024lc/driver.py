"""Sequential H execution: one selected full result before the next decision."""
from copy import deepcopy
import time

from ..pqe20261022.conditional_learning_methods import ConditionalEpisodeDriver
from ..pqe20261022.episode_methods import SUCCESS
from ..pqe20261022.methods import ContractError, digest
from ..pqe20261023bold.contracts import compact_feedback
from .contracts import VERSION
from .projection import project_public_result


class SequentialEpisodeDriver(ConditionalEpisodeDriver):
    def __init__(self, *args, initial_public_object_ref, world_kind,
                 max_evaluated_candidates=4, **kwargs):
        if (world_kind not in {"DOOR", "LC_PV"} or
                type(max_evaluated_candidates) is not int or
                not 1 <= max_evaluated_candidates <= 4):
            raise ContractError("SEQUENTIAL_WORLD_OR_CANDIDATE_CAP")
        state = deepcopy(kwargs.get("initial_state"))
        if not isinstance(state, dict) or not isinstance(state.get("last_result"), dict):
            raise ContractError("INITIAL_PUBLIC_RESULT_REQUIRED")
        original = state["last_result"]
        state.setdefault("evidence", []).append(
            project_public_result(original, initial_public_object_ref, world_kind=world_kind))
        state["last_result"] = compact_feedback(original, initial_public_object_ref)
        kwargs["initial_state"] = state
        self.world_kind = world_kind
        self.max_evaluated_candidates = max_evaluated_candidates
        self.evaluated_candidates = []
        super().__init__(*args, **kwargs)

    def _instructions(self, request):
        return super()._instructions(request) + (
            "\nLC SEQUENTIAL PUBLIC FEEDBACK: H-GEN may emit a batch of legal candidates, "
            "but H-RANK chooses exactly one. Only the chosen input is sent to the "
            "original full consumer. Its complete PUBLIC result and reference enter "
            "H-UPDATE before the next H-STOP/H-GEN/H-RANK. The fact view states "
            "coverage and original event labels; absent DOOR boot is not LC failure. "
            "A model-valid public PASS or correct scoped stop is service evidence; "
            "received count alone is not service success."
        )

    def _quota(self):
        quota = super()._quota()
        quota["max_candidates"] = min(quota["max_candidates"],
                                      self.max_evaluated_candidates - len(self.evaluated_candidates))
        return quota

    def apply_initial_update(self, budget_snapshot=None):
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
                "wall_s_remaining": time.monotonic() - self.started_at}
            self.output_snapshot_base_used = self._output_tokens_used()
        self.harness.quota = self._quota()
        reason = self._stop_reason(self._quota(), needs_model=self.harness.selection_uses_model,
                                   needs_action=False)
        if reason:
            self.finish(reason)
            return {"status": "STOPPED", "reason": reason}
        before, callback_start, design = (len(self.harness.program.calls),
                                          len(self.callback_records), deepcopy(self.state["design"]))
        self.state = self.harness.update(self.state, {
            "source": "EXTERNALLY_SUPPLIED_COMMON_INITIAL_RESULT",
            "autonomous_choice": False, "new_execution": False}, result)
        self.initial_update_receipt = {
            "status": self.state.get("update_status"),
            "initial_verdict": result["public_check"]["verdict"],
            "result_sha256": result.get("result_sha256"),
            "public_result_digest": digest(result),
            "site_calls": deepcopy(self.harness.program.calls[before:]),
            "callback_start": callback_start, "callback_end": len(self.callback_records),
            "parent_design_preserved": self.state.get("design") == design,
            "submitted_candidate": False, "new_tool_or_numerical_execution": False}
        if self.state.get("update_status") != "UPDATED" or self.harness.blocked:
            self.finish("INITIAL_UPDATE_" + str(self.state.get("update_status", "UNKNOWN")))
        return deepcopy(self.initial_update_receipt)

    def next(self, budget_snapshot=None):
        if (self.termination is None and self.pending is None and
                len(self.evaluated_candidates) >= self.max_evaluated_candidates):
            self.finish("FULL_CANDIDATE_CAP_REACHED")
        return super().next(budget_snapshot)

    def update(self, public_result, public_object_ref=None):
        if self.pending is None or not public_object_ref:
            raise ContractError("PENDING_ACTION_AND_PUBLIC_REF_REQUIRED")
        if len(self.evaluated_candidates) >= self.max_evaluated_candidates:
            raise ContractError("FULL_CANDIDATES_PER_SOLVE_CAP")
        if not isinstance(public_result, dict) or not public_result.get("result_sha256"):
            raise ContractError("ORIGINAL_PUBLIC_RESULT_REQUIRED")
        selected = deepcopy(self.pending)
        compact = compact_feedback(public_result, public_object_ref)
        if compact.get("task_id") != self.state.get("task", {}).get("task_id"):
            raise ContractError("SELECTED_RESULT_TASK_BINDING")
        view = project_public_result(public_result, public_object_ref, world_kind=self.world_kind)
        self.state.setdefault("evidence", []).append(view)
        outcome = super().update(compact)
        self.evaluated_candidates.append({
            "selected_id": selected["selected_id"],
            "actual_input_digest": digest(selected["actual_input"]),
            "result_sha256": compact["result_sha256"],
            "public_object_ref": deepcopy(public_object_ref),
            "public_check": deepcopy(compact.get("public_check")),
            "model_valid": compact.get("model_valid"),
            "update_status": outcome.get("update_status"),
            "evidence_view_sha256": view["view_sha256"]})
        return outcome

    def transcript(self):
        return {**super().transcript(), "sequential_contract": VERSION,
                "world_kind": self.world_kind,
                "evaluated_candidates": deepcopy(self.evaluated_candidates),
                "selection_rule": "one selected full result, then H-UPDATE, then next decision"}
