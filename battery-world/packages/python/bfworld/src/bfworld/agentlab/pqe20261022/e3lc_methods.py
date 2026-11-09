"""Finite E3 scope-policy wrapper; scientific permissions are never changed."""
from copy import deepcopy

from .episode_methods import EpisodeDriver as BaseEpisodeDriver, SUCCESS
from .methods import ContractError


CONDITIONS = {
    "strong_generic": "strong_generic",
    "full_h": "full_h",
    "full_h_no_active_reform": "full_h",
    "strong_generic_scope_matched": "strong_generic",
}
NO_ACTIVE_REFORM_POLICY = (
    " E3 declared method strategy: retain the initial Problem active-variable set "
    "and fixed choices. Do not proactively enlarge or shrink that set, release or "
    "change fixed choices, or propose an action/problem_reforms that does so. "
    "Use the initial active scope for legal design edits, observations, verification "
    "and local predictions. Group labels alone do not enlarge that scope. "
    "If evidence or budget does not support a solution there, stop with an explicitly "
    "local scope; failure in this initial scope is not global Task infeasibility. "
    "This is your method policy. The complete Task design domain and all broker "
    "permissions remain available and unchanged."
)


class E3LCEpisodeDriver(BaseEpisodeDriver):
    """Map four declared conditions onto the unchanged B0/B3 implementation.

    The owner supplies the matched-scope initial Problem. The no-reform condition
    changes only the method instruction, with any executed deviation recorded.
    """

    def __init__(self, condition, planner_callback, *, episode_id, initial_state,
                 model_identity, request_reserve_usd, limits=None, fixture_mode=False,
                 max_contract_corrections=0, program=None, common_history=None,
                 expected_methods_sha256=None, isolated_program=False):
        if condition not in CONDITIONS:
            raise ContractError("E3LC_UNKNOWN_CONDITION")
        self.declared_condition = condition
        self.initial_scope = deepcopy(initial_state.get("problem", {}))
        super().__init__(CONDITIONS[condition], planner_callback,
            episode_id=episode_id, initial_state=initial_state,
            model_identity=model_identity, request_reserve_usd=request_reserve_usd,
            limits=limits, fixture_mode=fixture_mode,
            max_contract_corrections=max_contract_corrections, program=program,
            common_history=common_history, expected_methods_sha256=expected_methods_sha256,
            isolated_program=isolated_program)

    def _instructions(self, request):
        common = super()._instructions(request)
        if (self.declared_condition == "full_h_no_active_reform"
                and request.get("site") in {"H-GEN", "H-RANK"}):
            return common + NO_ACTIVE_REFORM_POLICY
        return common

    def transcript(self):
        out = super().transcript()
        initial_active = set(self.initial_scope.get("active_variables", []))
        initial_fixed = self.initial_scope.get("fixed_choices", {})
        consumed, deviations = [], []
        for step in out["steps"]:
            result = step.get("result") or {}
            selected = step.get("select") or {}
            actual = selected.get("actual_input") or {}
            expected_problem = {**step["state_before"].get("problem", {}),
                                **actual.get("problem_patch", {})}
            if (result.get("execution_status") not in SUCCESS
                    or result.get("problem") != expected_problem):
                continue
            current_active = set(expected_problem.get("active_variables", []))
            current_fixed = expected_problem.get("fixed_choices", {})
            relaxed = {k for k in initial_fixed
                       if k not in current_fixed or current_fixed[k] != initial_fixed[k]}
            edit_keys = set(actual.get("design_patch", {}))
            item = {
                "step": step["step"], "operation": actual.get("operation"),
                "model_valid": result.get("model_valid"),
                "public_service": result.get("public_check"),
                "scope_effect": step.get("scope_effect"),
                "active_variables_added_from_initial": sorted(current_active - initial_active),
                "active_variables_removed_from_initial": sorted(initial_active - current_active),
                "initial_fixed_choices_relaxed_or_changed": sorted(relaxed),
                "actual_edit_outside_initial_active": sorted(edit_keys - initial_active),
                "actual_edit_using_relaxed_initial_fixed_choices": sorted(edit_keys & relaxed),
            }
            consumed.append(item)
            if (self.declared_condition == "full_h_no_active_reform"
                    and (current_active != initial_active or current_fixed != initial_fixed)):
                deviations.append(item)
        out["base_condition"] = out["condition"]
        out["condition"] = self.declared_condition
        out["e3lc_policy"] = {
            "declared_condition": self.declared_condition,
            "base_condition": CONDITIONS[self.declared_condition],
            "instruction_only_scope_policy": self.declared_condition == "full_h_no_active_reform",
            "matched_scope_prepared_by_owner": self.declared_condition == "strong_generic_scope_matched",
            "initial_problem": deepcopy(self.initial_scope),
            "task_permissions_changed_by_wrapper": False,
            "consumed_actions": consumed,
            "no_active_reform_consumed_deviations": deviations,
            "scope_metadata_is_not_service_or_causal_verdict": True,
        }
        return out


# Optional drop-in name for the owner's injected-driver entry point.
EpisodeDriver = E3LCEpisodeDriver
