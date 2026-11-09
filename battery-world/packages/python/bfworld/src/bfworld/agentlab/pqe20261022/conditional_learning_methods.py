"""Thin F1 wrappers: disclose the real contract and consume the initial FAIL.

The host owns current-role resolution, public paging, every paid request and
every scientific execution. No task registry, solver or provider is imported.
"""
from contextlib import contextmanager
from copy import deepcopy
import time

from . import episode_methods
from .episode_methods import EpisodeDriver, SUCCESS
from .f1first_methods import FormationDriver, formation_instructions
from .methods import ContractError, H_SITES, SAFE_ATTRIBUTES, SAFE_BUILTINS, digest

VERSION = "pqe-f1-conditional-learning-v1"


def runtime_contract():
    examples = {
        "H-GEN": 'def h_gen(ctx, ask):\n    return ask("H-GEN", ctx)\n',
        "H-RANK": 'def h_rank(ctx, ask):\n    return ask("H-RANK", ctx)\n',
        "H-EXP": 'def h_exp(ctx, ask):\n    return {"candidates": []}\n',
        "H-UPDATE": 'def h_update(ctx, ask):\n    return {"strategy": ctx["state"].get("strategy", {}), "next_evidence": {"verdict": ctx["result"].get("public_check", {}).get("verdict", "UNKNOWN")}}\n',
        "H-REFORM": 'def h_reform(ctx, ask):\n    return {"candidate_patches": {}}\n',
        "H-STOP": 'def h_stop(ctx, ask):\n    return {"stop": False, "reason": "continue within remaining quota", "scope": "current public state only"}\n',
    }
    return {"version": VERSION, "sites": list(H_SITES),
        "safe_builtins": sorted(SAFE_BUILTINS), "safe_attributes": sorted(SAFE_ATTRIBUTES),
        "type_is_available": False,
        "language": ["Only named h_gen/h_rank/h_exp/h_update/h_reform/h_stop(ctx, ask) and helper_ functions at top level.",
            "No imports, private names, arbitrary attributes, exceptions, while, classes, decorators, IO, network or subprocess.",
            "For/comprehension execution is bounded by 10000 traced hook line/call events; range length <=1000.",
            "Source <=65536 bytes; AST <=5000 nodes; no annotations/default arguments/return annotations.",
            "Use isinstance(value, dict/list/int/float/bool); type, print, open, getattr and hasattr are NOT builtins.",
            "ask may name only the currently executing site and receives a JSON object; it uses the common accounted callback.",
            "Capability AST checks and the separate fail-closed restricted worker are distinct boundaries."],
        "context": {"all": ["state", "quota", "site_config", "site_prompt"],
            "H-GEN": "state/task/design/problem/history/evidence/last_result/strategy and remaining quota",
            "H-RANK": "also candidates (already common-contract checked)",
            "H-EXP": "also generated", "H-REFORM": "also generated",
            "H-UPDATE": "also decision, executed public result and optional PUBLIC assessment; initial FAIL enters this before Generate",
            "H-STOP": "state/quota; local stop only"},
        "outputs": {"H-GEN": "{status:OK,candidates:[original complete candidate schema]} or {status:STOPPED,conclusion:{verdict,basis,scope}}",
            "H-RANK": "{selected_id:<supplied id>,selection_basis,expected_discrimination_or_gain}; cannot edit selected action",
            "H-EXP": "{candidates:[]}, same original candidate schema when nonempty",
            "H-UPDATE": "Only optional hypotheses/invalidated/next_evidence/strategy; no Design, Problem, action, adoption or history edits",
            "H-REFORM": "{candidate_patches:{candidate_id:legal Problem patch}}",
            "H-STOP": "{stop:boolean,reason:string,scope:string}; no unsupported domain verdict"},
        "examples": examples,
        "conditions": "applicability/non_trigger_conditions map site to dotted-context-path equality maps, not executable predicates.",
        "public_tools": "The host planner_callback resolves status PUBLIC_TOOLS/tool_calls before returning a final site payload. All groups have identical public tools; every provider request/page/cheap/full execution retains original accounting. Formation reads only frozen development materials, never new tasks or their predictions.",
        "rights": "H2/H4 same six sites and code/prompts/config/applicability/non_trigger_conditions rights via original materialize_patch; no semantic repair/reformation."}


def _contract_text():
    import json
    return "\nACTUAL COMMON EXECUTION CONTRACT (shared before formation): " + json.dumps(runtime_contract(), ensure_ascii=False)


@contextmanager
def _authorized_validation_ceilings():
    # S0 constructs serially; restore globals even if construction fails.
    previous = dict(episode_methods.MAX_LIMITS)
    try:
        episode_methods.MAX_LIMITS.update(output_tokens_per_request=65536, reserve_usd=5)
        yield
    finally:
        episode_methods.MAX_LIMITS.clear()
        episode_methods.MAX_LIMITS.update(previous)


class ConditionalFormationDriver(FormationDriver):
    def __init__(self, *args, **kwargs):
        with _authorized_validation_ceilings():
            super().__init__(*args, **kwargs)
        self.max_contract_corrections = 0

    def _instructions(self, request):
        return formation_instructions(request) + _contract_text()

    def _stage(self, fn):
        # One original formation path; malformed/illegal proposals are retained.
        reason = self._stop_reason(self._quota(), needs_action=False)
        if reason:
            return {"status": reason, "incidents": [], "programs": []}
        self.harness.quota = self._quota()
        return fn()


class ConditionalEpisodeDriver(EpisodeDriver):
    def __init__(self, *args, **kwargs):
        if kwargs.get("isolated_program", True) is not True:
            raise ContractError("CONDITIONAL_PROGRAM_REQUIRES_ISOLATED_WORKER")
        kwargs["isolated_program"] = True
        self.initial_update_receipt = None
        with _authorized_validation_ceilings():
            super().__init__(*args, **kwargs)

    def _instructions(self, request):
        return super()._instructions(request).replace("All four conditions", "All five conditions") + _contract_text()

    def apply_initial_update(self, budget_snapshot=None):
        """Consume the qualified public initial FAIL once, not a submitted action.

        Host must obtain a fresh owner snapshot before the subsequent next().
        Existing initial qualification cost remains in S0's global ledger.
        """
        if self.initial_update_receipt is not None or self.steps or self.pending is not None:
            raise ContractError("INITIAL_UPDATE_ALREADY_ATTEMPTED_OR_EPISODE_STARTED")
        result = deepcopy(self.state.get("last_result", {}))
        if (result.get("execution_status") not in SUCCESS or result.get("model_valid") is not True
                or result.get("public_check", {}).get("verdict") != "FAIL"
                or result.get("design") != self.state.get("design")
                or result.get("task_id") != self.state.get("task", {}).get("task_id")):
            raise ContractError("QUALIFIED_BOUND_INITIAL_FAIL_REQUIRED")
        if budget_snapshot is not None:
            self.owner_budget = deepcopy(budget_snapshot)
            self.owner_snapshot_base = {"provider_requests_remaining": len(self.harness.usage_ledger),
                "reserve_usd_remaining": sum(r.get("usage", {}).get("cost", 0) or 0 for r in self.harness.usage_ledger),
                "tool_calls_remaining": self.tool_calls, "new_numerical_inputs_remaining": self.numerical_inputs,
                "wall_s_remaining": time.monotonic() - self.started_at}
            self.output_snapshot_base_used = self._output_tokens_used()
        self.harness.quota = self._quota()
        reason = self._stop_reason(self._quota(), needs_model=self.harness.selection_uses_model, needs_action=False)
        if reason:
            self.finish(reason)
            return {"status": "STOPPED", "reason": reason}
        before, callback_start, design = len(self.harness.program.calls), len(self.callback_records), deepcopy(self.state["design"])
        self.state = self.harness.update(self.state, {"source": "EXTERNALLY_SUPPLIED_COMMON_INITIAL_FAIL",
            "autonomous_choice": False, "new_execution": False}, result)
        self.initial_update_receipt = {"status": self.state.get("update_status"),
            "result_sha256": result.get("result_sha256"), "public_result_digest": digest(result),
            "site_calls": deepcopy(self.harness.program.calls[before:]),
            "callback_start": callback_start, "callback_end": len(self.callback_records),
            "parent_design_preserved": self.state.get("design") == design,
            "submitted_candidate": False, "new_tool_or_numerical_execution": False}
        if self.state.get("update_status") != "UPDATED" or self.harness.blocked:
            self.finish("INITIAL_UPDATE_" + str(self.state.get("update_status", "UNKNOWN")))
        return deepcopy(self.initial_update_receipt)

    def next(self, budget_snapshot=None):
        if self.termination is None and not (self.initial_update_receipt or {}).get("status") == "UPDATED":
            raise ContractError("REAL_INITIAL_UPDATE_REQUIRED_BEFORE_GENERATE")
        return super().next(budget_snapshot)

    def transcript(self):
        return {**super().transcript(), "conditional_contract": VERSION,
                "initial_update": deepcopy(self.initial_update_receipt)}
