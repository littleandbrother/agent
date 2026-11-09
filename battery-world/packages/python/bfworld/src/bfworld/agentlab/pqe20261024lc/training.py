"""Bounded model-authored H revision with real, S0-owned training feedback."""
from contextlib import contextmanager
from copy import deepcopy
import time

from ..pqe20261022 import episode_methods
from ..pqe20261022.f1first_methods import FormationDriver, formation_instructions, screen_program
from ..pqe20261022.conditional_learning_methods import runtime_contract
from ..pqe20261022.methods import ContractError, digest, materialize_patch
from .contracts import (VERSION, service_selection, validate_training_feedback,
                        version_binding)
from .projection import incident_source_map


@contextmanager
def _formation_ceilings():
    previous = dict(episode_methods.MAX_LIMITS)
    try:
        episode_methods.MAX_LIMITS.update(provider_requests=24, tool_calls=48,
            new_numerical_inputs=8, wall_s=1800, output_tokens_per_request=65536,
            output_tokens_total=262144, reserve_usd=10)
        yield
    finally:
        episode_methods.MAX_LIMITS.clear()
        episode_methods.MAX_LIMITS.update(previous)


class TrainingFormationDriver(FormationDriver):
    """One owner, one episode, at most two raw proposals and one revision each.

    The only scientific execution path is the injected S0 callback. Neither
    this class nor its behavior screen has a task registry or consumer.
    """
    def __init__(self, condition, planner_callback, *, parent, history,
                 source_catalog, training_tasks, training_execute=None,
                 run_training=None, episode_id, model_identity,
                 request_reserve_usd, limits=None, fixture_mode=False):
        execute = training_execute or run_training
        if not callable(execute):
            raise ContractError("S0_TRAINING_EXECUTE_CALLBACK_REQUIRED")
        if (not isinstance(training_tasks, list) or not training_tasks or
                len({t.get("task_id") for t in training_tasks if isinstance(t, dict)}) != len(training_tasks) or
                any(not isinstance(t, dict) or not isinstance(t.get("task_id"), str)
                    for t in training_tasks)):
            raise ContractError("FROZEN_TRAINING_TASK_IDS_REQUIRED")
        if not isinstance(source_catalog, (dict, list)):
            raise ContractError("PUBLIC_SOURCE_CATALOG_REQUIRED")
        self.source_catalog = deepcopy(source_catalog)
        self.training_tasks = deepcopy(training_tasks)
        self.training_execute = execute
        self.training_rows = []
        self.full_inputs_consumed = 0
        self.training_rounds = 0
        self.cheap_checks_consumed = 0
        self.raw_versions = []
        with _formation_ceilings():
            super().__init__(condition, planner_callback, parent=parent, history=history,
                episode_id=episode_id, model_identity=model_identity,
                request_reserve_usd=request_reserve_usd, limits=limits,
                fixture_mode=fixture_mode)
        self.max_contract_corrections = 0

    def _consume_unit(self, kind, **detail):
        if len(self.formation_units) >= 48:
            raise ContractError("FORMATION_TOOL_OR_CALLBACK_CAP")
        if time.monotonic() - self.started_at >= self.limits["wall_s"]:
            raise ContractError("FORMATION_WALL_CAP")
        self.formation_units.append({"index": len(self.formation_units),
                                     "kind": kind, **detail})
        self.tool_calls = len(self.formation_units)

    def _instructions(self, request):
        import json
        base = formation_instructions(request)
        if request.get("context", {}).get("revision_feedback") is not None:
            base += (" REVISION: Return exactly ONE raw patch, or patches:[] to stop. "
                     "Use only the reported public contract/behavior/full-training facts. "
                     "You must author every changed code byte and source_incidents ID; "
                     "the host performs no semantic repair. This is the one permitted "
                     "revision for this original proposal.")
        return (base + "\nACTUAL COMMON EXECUTION CONTRACT: " +
                json.dumps(runtime_contract(), ensure_ascii=False) +
                "\nLEGAL CITATION FIELD: source_incidents must use incident_id; "
                "source_id is a public catalog lookup identifier only. "
                "A complete original consumer run, not a software screen or "
                "received count, decides training service.")

    def _callback(self, request):
        request = deepcopy(request)
        request.setdefault("context", {})["public_source_catalog"] = deepcopy(self.source_catalog)
        request["context"]["incident_source_map"] = incident_source_map(self.history)
        request["context"]["source_incidents_legal_field"] = "incident_id"
        request["context"]["frozen_training_task_contract"] = deepcopy(self.training_tasks)
        return super()._callback(request)

    def _stage(self, fn):
        # Original transport-only JSON syntax retry preserves the model's raw
        # output and settled usage. It does not repair a semantic patch.
        return super()._stage(fn)

    @staticmethod
    def _raw_patches(payload):
        if not isinstance(payload, dict) or payload.get("status", "OK") not in {
                "OK", "READY", "NO_UPDATE", "RETAIN_PARENT", "INSUFFICIENT_EVIDENCE"}:
            return [], "PROPOSAL_RESPONSE_STATUS"
        patches = payload.get("patches")
        if not isinstance(patches, list):
            return [], "PATCHES_LIST_REQUIRED"
        if len(patches) > 2:
            return [], "TWO_RAW_PROPOSAL_CAP"
        if payload.get("status") in {"NO_UPDATE", "RETAIN_PARENT", "INSUFFICIENT_EVIDENCE"} and patches:
            return [], "NO_UPDATE_WITH_PATCHES"
        return patches, None

    def _attempt_version(self, patch, *, proposal_index, revision_index, incidents):
        row = {"proposal_index": proposal_index, "revision_index": revision_index,
               "raw_patch": deepcopy(patch), "raw_patch_sha256": digest(patch),
               "status": "RAW_RECEIVED", "contract_feedback": None,
               "screen": None, "training": None, "selection": None}
        self.raw_versions.append(row)
        try:
            program = materialize_patch(self.parent, patch, incidents,
                                        fixture_mode=self.fixture_mode)
        except (ValueError, TypeError, KeyError) as exc:
            row.update(status="CONTRACT_REJECTED", contract_feedback={
                "code": str(exc), "error_type": type(exc).__name__,
                "legal_source_incident_ids": [i["incident_id"] for i in incidents],
                "legal_source_field": "incident_id",
                "raw_patch_sha256": row["raw_patch_sha256"]})
            return row
        row["program"] = deepcopy(program)
        row["program_sha256"] = digest(program)
        row["version"] = version_binding(condition=self.condition,
            proposal_index=proposal_index, revision_index=revision_index,
            program=program, patch=patch, tasks=self.training_tasks)
        # Original isolated worker and four public behavior inputs; never science.
        try:
            screen = screen_program(program, consume=self._consume_unit)
        except Exception as exc:
            row.update(status="BEHAVIOR_SCREEN_UNRESOLVED", contract_feedback={
                "code": str(exc), "error_type": type(exc).__name__})
            self.harness.blocked = True
            return row
        self.cheap_checks_consumed += len(screen["fixtures"])
        row["screen"] = screen
        if screen["outcome"] != "PASS":
            row.update(status="BEHAVIOR_REJECTED", contract_feedback={
                "code": "ISOLATED_BEHAVIOR_SCREEN_ERROR",
                "errors": [{"kind": f["kind"], "error": f.get("error")}
                           for f in screen["fixtures"] if f["outcome"] != "PASS"]})
            return row
        row["status"] = "SCREEN_PASSED"
        if self.training_rounds >= 2 or self.full_inputs_consumed >= 8:
            row["status"] = "TRAINING_CAP_REACHED"
            return row
        reason = self._stop_reason(self._quota(), needs_action=False)
        if reason:
            row["status"] = reason
            return row
        self.training_rounds += 1
        remaining = 8 - self.full_inputs_consumed
        try:
            feedback = self.training_execute(deepcopy(program), deepcopy(row["version"]), remaining)
            feedback = validate_training_feedback(feedback, remaining_full=remaining,
                                                  frozen_tasks=self.training_tasks)
        except Exception as exc:
            row.update(status="TRAINING_EXECUTION_UNRESOLVED", contract_feedback={
                "code": str(exc), "error_type": type(exc).__name__})
            self.harness.blocked = True
            return row
        self.full_inputs_consumed += feedback["full_inputs"]
        self.numerical_inputs += feedback["full_inputs"]
        for _ in range(feedback["full_inputs"]):
            self._consume_unit("FULL_TRAINING_INPUT", program_id=program["program_id"])
        self.owner_budget = deepcopy(feedback["owner_budget_after"])
        self.owner_snapshot_base = {"provider_requests_remaining": len(self.harness.usage_ledger),
            "reserve_usd_remaining": sum(x.get("usage", {}).get("cost", 0) or 0
                                         for x in self.harness.usage_ledger),
            "tool_calls_remaining": self.tool_calls,
            "new_numerical_inputs_remaining": self.numerical_inputs,
            "wall_s_remaining": time.monotonic() - self.started_at}
        self.output_snapshot_base_used = self._output_tokens_used()
        row["training"] = feedback
        row["selection"] = (service_selection(feedback["task_results"], self.training_tasks)
                            if feedback["status"] == "COMPLETE" else
                            {"eligible": False, "reason": "TRAINING_PARTIAL_OR_STOPPED"})
        row["status"] = "TRAINED" if feedback["status"] == "COMPLETE" else "TRAINING_PARTIAL_STOP"
        self.training_rows.append({"version": deepcopy(row["version"]),
                                   "feedback": deepcopy(feedback),
                                   "selection": deepcopy(row["selection"])})
        return row

    def _revision(self, original, *, proposal_index, incidents, attribution):
        if self.harness.blocked or self._stop_reason(self._quota(), needs_action=False):
            return None
        self.harness.quota = self._quota()
        context = {"parent": self.parent, "parent_sha256": digest(self.parent),
                   "attribution": attribution, "incidents": incidents,
                   "original_raw_patch": original["raw_patch"],
                   "original_raw_patch_sha256": original["raw_patch_sha256"],
                   "revision_feedback": {"status": original["status"],
                       "contract_feedback": original["contract_feedback"],
                       "behavior_screen": original["screen"],
                       "actual_full_training": original["training"],
                       "selection": original["selection"]},
                   "instruction": "One model-authored revision or patches:[]; do not repair hidden data."}
        payload = self.harness._ask("G-PROPOSE", context)
        patches, error = self._raw_patches(payload)
        receipt = {"proposal_index": proposal_index, "payload": deepcopy(payload),
                   "raw_patch_count": len(patches), "error": error,
                   "version": None}
        if error or len(patches) != 1:
            receipt["error"] = error or ("MODEL_NO_REVISION" if not patches else
                                        "ONE_REVISION_PATCH_REQUIRED")
            return receipt
        receipt["version"] = self._attempt_version(patches[0], proposal_index=proposal_index,
                                                   revision_index=1, incidents=incidents)
        return receipt

    def run(self):
        if self.ran:
            raise ContractError("FORMATION_ALREADY_RUN")
        self.ran = True
        extracted = self.harness.extract(self.history)
        attribution = self._stage(lambda: self.harness.attribute(extracted, self.parent))
        proposals = self._stage(lambda: self.harness.propose(
            attribution, self.parent, {**self._quota(), "max_proposals": 2}))
        requests = [(index, record) for index, record in enumerate(self.callback_records)
                    if record.get("request", {}).get("site") == "G-PROPOSE"]
        initial_payload = requests[-1][1].get("consumed_payload") if requests else {}
        patches, payload_error = self._raw_patches(initial_payload)
        incidents = attribution.get("incidents", [])
        revisions = []
        if not payload_error and not self.harness.blocked and incidents:
            for proposal_index, patch in enumerate(patches):
                first = self._attempt_version(patch, proposal_index=proposal_index,
                                              revision_index=0, incidents=incidents)
                revision = self._revision(first, proposal_index=proposal_index,
                                          incidents=incidents, attribution=attribution)
                if revision is not None:
                    revisions.append(revision)
                if self.harness.blocked:
                    break
        eligible = [row for row in self.raw_versions
                    if (row.get("selection") or {}).get("eligible") is True]
        eligible.sort(key=lambda row: (-len(row["selection"].get("improved_task_ids", [])),
                                       row["proposal_index"], row["revision_index"]))
        selected = eligible[0] if eligible else None
        no_child_reason = None if selected else (
            "MISSING_USAGE_OR_TRAINING_UNRESOLVED" if self.harness.blocked else
            "NO_G_PROPOSAL_REQUEST" if not requests else
            payload_error or ("LEGAL_EMPTY_PROPOSAL" if not patches else
                              "NO_LAWFUL_FULL_SERVICE_GAIN"))
        return {"schema": VERSION, "condition": self.condition,
                "episode_id": self.episode_id,
                "parent_sha256": digest(self.parent),
                "common_history_sha256": digest(self.history),
                "source_catalog_sha256": digest(self.source_catalog),
                "training_tasks_sha256": digest(self.training_tasks),
                "extracted": extracted, "attribution": attribution,
                "initial_proposals": proposals,
                "initial_raw_response": deepcopy(initial_payload),
                "initial_raw_response_error": payload_error,
                "raw_proposal_count": len(patches), "raw_versions": deepcopy(self.raw_versions),
                "revisions": revisions, "training_rounds": self.training_rounds,
                "cheap_checks_consumed": self.cheap_checks_consumed,
                "full_inputs_consumed": self.full_inputs_consumed,
                "training_rows": deepcopy(self.training_rows),
                "selected_program": deepcopy(selected["program"] if selected else self.parent),
                "selected_candidate": selected is not None,
                "selected_version": deepcopy(selected["version"] if selected else None),
                "parent_retained": selected is None,
                "no_child_reason": no_child_reason,
                "adoption": "EXTERNAL_ISOLATED_TEST_NOT_YET_RUN",
                "callback_records": deepcopy(self.callback_records),
                "usage_ledger": deepcopy(self.harness.usage_ledger),
                "format_feedback": deepcopy(self.format_feedback),
                "tools_or_callbacks": {"limit": 48,
                    "consumed": len(self.formation_units),
                    "events": deepcopy(self.formation_units)},
                "wall_s": time.monotonic() - self.started_at,
                "claim_boundary": "Public development training only; held-out result and physical qualification absent."}
