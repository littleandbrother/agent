"""Bounded phase4 G -> H contracts; no provider, simulator or execution authority.

Only two pinned local config files are read. Public history is identical for
both arms. Host receipts and semantic audits must come from S0's independent
source-bound records; this module cannot authenticate a dictionary's author.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re

from .phase2_methods import D_FIELDS, digest, validate_method


SCHEMA = "bf-phase4-improver-proposal-v1"
HISTORY_SHA256 = "6732821ef52b8006eebd2d19a2c0b313dac822299f49c8747c9c3abfe59c33db"
MODEL_HISTORY_SHA256 = "7e7f379d80746d0572f6ef75214129a4c08292a4dfe8270b4d9f953308318cf9"
PARENTS_SHA256 = "d535ca972aef4cc061d3100b981d676cd502d0d843cf53d223f39c67c7e95386"
CONFIG = Path(__file__).resolve().parents[7] / "configs/studies/phase4-20261020/methods"
SELECTION_TASKS = ("b-pulse-fast", "b-volatile-reset")
ARM_SLOTS = ("h1-proposal", "h2-proposal",
             "h1-b-pulse-fast", "h1-b-volatile-reset",
             "h2-b-pulse-fast", "h2-b-volatile-reset",
             "final-1", "final-2", "final-3")


def _object(value, *, limit=65536):
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError("JSON_OBJECT_REQUIRED")
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError("FINITE_JSON_REQUIRED") from exc
    if len(raw) > limit:
        raise ValueError("JSON_BYTE_LIMIT")


def _text(value, name, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ValueError("INVALID_" + name.upper())
    return value.strip()


def _number(value, name):
    if type(value) not in (int, float, str):
        raise ValueError("INVALID_" + name.upper())
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("INVALID_" + name.upper()) from exc
    if not number.is_finite() or number < 0:
        raise ValueError("INVALID_" + name.upper())
    return number


def _requests(value):
    if type(value) is not int or value < 0:
        raise ValueError("INVALID_REQUESTS")
    return value


def _pinned_bytes(name, expected):
    raw = (CONFIG / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("FROZEN_CONFIG_HASH_MISMATCH_" + name)
    return raw


def frozen_parent_methods():
    """Return a new dict with unchanged phase3 H0, ordinary-reflection G0, prefix."""
    return json.loads(_pinned_bytes("frozen-parents.json", PARENTS_SHA256))


def history_packet_bytes():
    """Host-only complete audit bytes. G/H must use model_history_packet instead."""
    return _pinned_bytes("public-history.json", HISTORY_SHA256)


def public_history_packet():
    """Host-only entire public traces; no arbitrary paths or mutable lookups."""
    return json.loads(history_packet_bytes())


def _project_model_history(packet):
    """Mechanical projection only: retain every tool action, not chosen answers."""
    result_pool = {}

    def project(value, key=""):
        if key in ("python_definition", "proposal_schema", "proposal_tool_schema"):
            return {"host_only_omission": key, "original_value_sha256": digest(value),
                    "original_json_bytes": len(json.dumps(value, ensure_ascii=False,
                        sort_keys=True, separators=(",", ":")).encode())}
        if key == "serialized_information" and isinstance(value, str):
            return {"decoded_original_json": project(json.loads(value)),
                    "original_string_sha256": digest(value)}
        if isinstance(value, dict):
            return {k: project(v, k) for k, v in value.items()}
        if isinstance(value, list):
            if len(value) > 12:
                return {"host_only_long_array": True, "original_count": len(value),
                        "original_value_sha256": digest(value),
                        "first_six": [project(v) for v in value[:6]],
                        "last_six": [project(v) for v in value[-6:]]}
            return [project(v) for v in value]
        return value

    episodes = []
    for episode in packet["episodes"]:
        calls = []
        for index, row in enumerate(episode["public_trace"]):
            if row["type"] == "bf_tool_fact":
                result = project(row["result"])
                result_id = digest(result)
                result_pool[result_id] = result
                calls.append({"original_trace_index": index, "time": row["time"],
                              "input": deepcopy(row["input"]), "ok": row["ok"],
                              "original_result_sha256": digest(row["result"]),
                              "projected_result_ref": result_id})
        original_input = episode["participant_input"]
        episodes.append({"phase": episode["phase"], "episode_id": episode["episode_id"],
                         "source_files": deepcopy(episode["source_files"]),
                         "public_trace_canonical_sha256": episode["public_trace_canonical_sha256"],
                         "participant_input": {"goal": original_input["goal"],
                             "instruction": original_input["instruction"],
                             "tool_sha256": original_input["tool"]["sha256"],
                             "limits": deepcopy(original_input["limits"])},
                         "all_tool_calls": calls,
                         "original_public_trace_record_count": len(episode["public_trace"]),
                         "retained_episode_status": episode["retained_episode_status"],
                         "charged_usage": deepcopy(episode["charged_usage"])})
    return {"schema_version": "bf-phase4-model-history-projection-v1",
            "complete_host_packet_sha256": HISTORY_SHA256,
            "partition": packet["partition"], "sampling_rule": packet["sampling_rule"],
            "projection_rules": [
                "Keep original goal/instruction, tool hash and limits, all tool calls in trace order with full original inputs including every method proposal/error, original final status and complete recorded episode costs.",
                "Tool result values named python_definition/proposal_schema/proposal_tool_schema are replaced by original canonical value SHA and byte count. No source code or schema is summarized into a recommended procedure.",
                "Decode serialized_information JSON mechanically before the same field rules; retain its original string SHA. Arrays longer than 12 only in tool results become count/SHA/first6/last6. No task- or outcome-based array selection.",
                "Identical projected tool results share one SHA-addressed value in projected_tool_results; every call retains the original complete result SHA and original trace index.",
                "Omit startup/core bookkeeping, repeated tool definitions and all assistant prose duplicated around tool actions. Original final status, every tool action and full recorded costs remain. Entire original public traces/protocol/results stay unchanged on the host and are bound per episode. This projection does not contain every original fact and is the identical information condition for both G arms."],
            "episodes": episodes, "projected_tool_results": result_pool,
            "claim_boundary": packet["claim_boundary"]}


def model_history_packet_bytes():
    """Canonical UTF-8 model packet, <=80,000 bytes; never send the 257KB audit packet."""
    packet = _project_model_history(public_history_packet())
    raw = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode()
    if len(raw) > 80000:
        raise ValueError("MODEL_HISTORY_EXCEEDS_80000_BYTES")
    if hashlib.sha256(raw).hexdigest() != MODEL_HISTORY_SHA256:
        raise ValueError("FROZEN_MODEL_HISTORY_PROJECTION_HASH_MISMATCH")
    return raw


def model_history_packet():
    """Model-facing same-byte projection. Full original history remains host-only."""
    return json.loads(model_history_packet_bytes())


def g_proposal_schema():
    """JSON Schema parameters for a model-authored procedure-only G or abstention."""
    common = {"schema_version": {"const": SCHEMA}, "changed_artifact": {"const": "G"}}
    return {"type": "object", "oneOf": [
        {"type": "object", "additionalProperties": False,
         "required": ["changed_artifact", "hypothesis", "falsifier", "proposal_procedure"],
         "properties": {**common, "decision": {"const": "propose"},
                        "hypothesis": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "falsifier": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "proposal_procedure": {"type": "string", "minLength": 1, "maxLength": 16000,
                            "description": "Natural-language rules for generating H; cannot contain an H/D submission or change selection, base H0, tasks, budget, tools or model."}}},
        {"type": "object", "additionalProperties": False, "required": ["decision", "reason"],
         "properties": {**common, "decision": {"const": "no-update"},
                        "reason": {"type": "string", "minLength": 1, "maxLength": 4000}}},
        {"type": "object", "maxProperties": 0}]}


def validate_improver(value):
    """Normalize raw G input; legality of prose still requires external audit."""
    _object(value)
    if not value:
        value = {"decision": "no-update", "reason": "EMPTY_PROPOSAL"}
    if value.get("schema_version", SCHEMA) != SCHEMA:
        raise ValueError("UNSUPPORTED_G_SCHEMA")
    if value.get("changed_artifact", "G") != "G":
        raise ValueError("G_REQUIRES_PROCEDURE_NOT_H_OR_D")
    decision = value.get("decision", "propose")
    if decision == "no-update":
        if set(value) - {"schema_version", "changed_artifact", "decision", "reason"}:
            raise ValueError("NO_UPDATE_CANNOT_CARRY_CHANGE")
        return {"schema_version": SCHEMA, "changed_artifact": "G", "decision": decision,
                "reason": _text(value.get("reason"), "reason"), "status": "NO_UPDATE"}
    if decision != "propose":
        raise ValueError("UNKNOWN_G_DECISION")
    if set(value) - {"schema_version", "changed_artifact", "decision", "hypothesis",
                     "falsifier", "proposal_procedure"}:
        raise ValueError("G_CAN_ONLY_CHANGE_PROPOSAL_PROCEDURE")
    if value.get("changed_artifact") != "G":
        raise ValueError("CHANGED_ARTIFACT_G_REQUIRED")
    hypothesis = _text(value.get("hypothesis"), "hypothesis")
    falsifier = _text(value.get("falsifier"), "falsifier")
    text = _text(value.get("proposal_procedure"), "proposal_procedure", 16000)
    try:
        structured = json.loads(text)
    except ValueError:
        structured = None
    fields = "|".join(re.escape(x) for x in sorted(D_FIELDS))
    assignment = rf"(?:{fields})\s*[:=]\s*[-+0-9.eE]+"
    if isinstance(structured, (dict, list)) or re.fullmatch(
            rf"\s*{assignment}(?:\s*[,;\n]\s*{assignment})*\s*", text):
        raise ValueError("G_PROCEDURE_CANNOT_BE_STRUCTURED_H_OR_DEVICE_ASSIGNMENT")
    if text == frozen_parent_methods()["G0"]["proposal_procedure"]:
        return {"schema_version": SCHEMA, "changed_artifact": "G", "decision": "no-update",
                "reason": "UNCHANGED_G0_PROCEDURE", "status": "NO_UPDATE"}
    return {"schema_version": SCHEMA, "changed_artifact": "G", "decision": "propose",
            "hypothesis": hypothesis, "falsifier": falsifier,
            "proposal_procedure": text, "procedure_sha256": digest(text),
            "impact_scope": "method-lineage-root",
            "status": "PROPOSED_REQUIRES_MODEL_AUTHORSHIP_AND_EXTERNAL_SEMANTIC_AUDIT"}


def formation_allocation(actual_requests, wall_s, usd):
    """Three G1 shares, not three events. Decimal strings conserve wall/USD sums.

    Requests use floor(q/3) plus one in the first q%3 slots. The last decimal
    share retains the division residue; global actual usage is counted once.
    Zero is allowed for pre-dispatch arithmetic, not proof of a formed G1.
    """
    q = _requests(actual_requests)
    wall, money = _number(wall_s, "wall_s"), _number(usd, "usd")
    if q > 8 or wall > 400:
        raise ValueError("FORMATION_BUDGET_EXCEEDED")
    with localcontext() as ctx:
        ctx.prec = 40
        ws, ms = wall / 3, money / 3
        return [{"lineage": i + 1, "requests": q // 3 + int(i < q % 3),
                 "wall_s": str(ws if i < 2 else wall - ws - ws),
                 "usd": str(ms if i < 2 else money - ms - ms)} for i in range(3)]


def formation_gate(value, *, receipt):
    """Host-only structural eligibility. Never authenticates or self-promotes G.

    S0 must bind one actual SDK event, original raw proposal and settled ledger.
    Failure/invalid/no-update records and their actual costs stay in S0 storage.
    """
    normalized = validate_improver(value)
    _object(receipt)
    parents = frozen_parent_methods()
    required = {"evidence_kind": "ACTUAL_PROVIDER", "author": "participant-model",
                "semantic_component": "proposal_procedure_only", "usage_status": "SETTLED",
                "history_sha256": HISTORY_SHA256, "model_history_sha256": MODEL_HISTORY_SHA256,
                "H0_sha256": parents["H0"]["method_sha256"],
                "G0_sha256": parents["G0"]["procedure_sha256"],
                "proposal_sha256": digest(value), "automatic_retry": False,
                "reported_models": ["deepseek-flash"], "unknown_usage": []}
    if any(receipt.get(k) != v or type(receipt.get(k)) is not type(v) for k, v in required.items()):
        raise ValueError("FORMATION_AUTHORSHIP_SCOPE_IDENTITY_OR_USAGE_GATE")
    if type(receipt.get("formation_event_count")) is not int or receipt["formation_event_count"] != 1:
        raise ValueError("ONE_COMMON_G1_FORMATION_REQUIRED")
    event = _text(receipt.get("formation_event_id"), "formation_event_id", 128)
    if receipt.get("registered_formation_event_id") != event:
        raise ValueError("UNREGISTERED_G1_FORMATION")
    ids = receipt.get("provider_request_ids")
    q = _requests(receipt.get("requests"))
    if (not isinstance(ids, list) or not 1 <= q <= 8 or len(ids) != q
            or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != q):
        raise ValueError("ACTUAL_DISTINCT_PROVIDER_REQUESTS_REQUIRED")
    if not re.fullmatch(r"[a-f0-9]{64}", str(receipt.get("model_configuration_sha256", ""))):
        raise ValueError("MODEL_CONFIGURATION_BINDING_REQUIRED")
    shares = formation_allocation(q, receipt.get("wall_s"), receipt.get("usd"))
    return {"status": "NO_UPDATE" if normalized["decision"] == "no-update" else "ELIGIBLE_FOR_S0_FREEZE",
            "normalized": normalized, "formation_event_id": event, "allocation": shares,
            "independent_G1_formation_events": 1, "descendant_lineage_pairs": 3,
            "qualification_authority": "NONE", "retained": False}


def _usage(value, *, request_cap, wall_cap):
    _object(value)
    if set(value) != {"requests", "wall_s", "usd", "status"} or value["status"] != "SETTLED":
        raise ValueError("COMPLETE_SETTLED_USAGE_REQUIRED")
    q = _requests(value["requests"])
    wall, usd = _number(value["wall_s"], "wall_s"), _number(value["usd"], "usd")
    if q > request_cap or wall > wall_cap:
        raise ValueError("EPISODE_BUDGET_EXCEEDED")
    return q, wall, usd


def select_descendant(rows):
    """Host-only selection from exactly two predeclared H siblings.

    Each row: descendant_index (1/2), raw proposal, proposal_status (SUBMITTED
    for an admitted submission), semantic_H_eligible (trusted external bool),
    proposal_usage, selection. Each selection: task_id, service_status,
    wrong_service_judgment (trusted external bool), usage. Usage is a settled
    requests/wall_s/usd/status dict. A failed proposal may have an empty selection
    list. All failures and unselected sibling costs remain in returned raw rows.
    Unknown accounting stops; it is never silently made a zero-cost fallback.
    """
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("EXACTLY_TWO_REGISTERED_DESCENDANTS_REQUIRED")
    parents = frozen_parent_methods()
    metrics, eligible, indices = [], [], []
    for row in rows:
        _object(row)
        if set(row) != {"descendant_index", "proposal", "proposal_status", "semantic_H_eligible",
                        "proposal_usage", "selection"}:
            raise ValueError("SELECTION_ONLY_FIELDS_REQUIRED_NO_FINAL_FEEDBACK")
        index = row["descendant_index"]
        if type(index) is not int or index not in (1, 2) or index in indices:
            raise ValueError("DISTINCT_REGISTERED_DESCENDANT_INDICES_REQUIRED")
        indices.append(index)
        if type(row["semantic_H_eligible"]) is not bool:
            raise ValueError("EXTERNAL_H_SEMANTIC_AUDIT_REQUIRED")
        _text(row["proposal_status"], "proposal_status", 128)
        q, wall, usd = _usage(row["proposal_usage"], request_cap=8, wall_cap=400)
        selected = row["selection"]
        if not isinstance(selected, list) or len(selected) > 2:
            raise ValueError("FIXED_SELECTION_TASKS_REQUIRED")
        seen, passes, wrong = set(), 0, 0
        for run in selected:
            _object(run)
            if set(run) != {"task_id", "service_status", "wrong_service_judgment", "usage"}:
                raise ValueError("SELECTION_ONLY_FIELDS_REQUIRED_NO_FINAL_FEEDBACK")
            task = run["task_id"]
            if not isinstance(task, str) or task not in SELECTION_TASKS or task in seen:
                raise ValueError("FINAL_OR_DUPLICATE_TASK_FORBIDDEN_IN_SELECTION")
            seen.add(task)
            if run["service_status"] not in ("PASS", "FAIL", "UNKNOWN", "INCOMPLETE", "CENSORED"):
                raise ValueError("INDEPENDENT_SERVICE_STATUS_REQUIRED")
            if type(run["wrong_service_judgment"]) is not bool:
                raise ValueError("INDEPENDENT_WRONG_JUDGMENT_REQUIRED")
            rq, rw, ru = _usage(run["usage"], request_cap=12, wall_cap=800)
            q, wall, usd = q + rq, wall + rw, usd + ru
            passes += int(run["service_status"] == "PASS")
            wrong += int(run["wrong_service_judgment"])
        reasons, method = [], None
        try:
            method = validate_method(row["proposal"])
        except ValueError as exc:
            reasons.append("INVALID_H:" + str(exc))
        if method is not None and method["decision"] != "propose":
            reasons.append("NO_UPDATE")
        if row["proposal_status"] != "SUBMITTED" or not row["semantic_H_eligible"]:
            reasons.append("NOT_EXTERNALLY_ADMITTED_H")
        if seen != set(SELECTION_TASKS):
            reasons.append("INCOMPLETE_SELECTION")
        metric = {"descendant_index": index, "eligible": not reasons, "reasons": reasons,
                  "complete_service_passes": passes, "wrong_service_judgments": wrong,
                  "total_charged_requests": q, "total_wall_s": str(wall), "total_usd": str(usd)}
        metrics.append(metric)
        if not reasons:
            eligible.append(((-passes, wrong, q, index), index, method))
    chosen = min(eligible) if eligible else None
    h0 = parents["H0"]["method_text"]
    htext = h0 if chosen is None else h0 + "\n\n" + chosen[2]["method_text"]
    return {"status": "H0_FALLBACK_NO_ADMISSIBLE_DESCENDANT" if chosen is None else "SELECTED_DESCENDANT",
            "selected_descendant_index": None if chosen is None else chosen[1],
            "selected_method_text": None if chosen is None else chosen[2]["method_text"],
            "selected_H_text": htext, "selected_H_sha256": digest(htext),
            "H0_sha256": parents["H0"]["method_sha256"], "selection_tasks": list(SELECTION_TASKS),
            "candidate_metrics": sorted(metrics, key=lambda x: x["descendant_index"]),
            "total_selection_charged_requests": sum(x["total_charged_requests"] for x in metrics),
            "raw_rows": deepcopy(rows), "final_results_consulted": False,
            "default_H0_changed": False, "qualification_authority": "NONE"}


def arm_budget(arm, lineage, *, usage_rows, formation_actual=None):
    """Remaining all-stage arm budget, including unselected/failed siblings.

    usage_rows: [{slot: one ARM_SLOTS value, usage: settled usage}]. Include
    every actual episode once, even on failure. Anonymous final slots carry
    usage only. formation_actual is the same requests/wall_s/usd object for
    all three G1 arms (also if formation failed/no-update), None only for G0.
    """
    if arm not in ("G0", "G1") or type(lineage) is not int or lineage not in (1, 2, 3):
        raise ValueError("REGISTERED_ARM_AND_LINEAGE_REQUIRED")
    if not isinstance(usage_rows, list) or len(usage_rows) > len(ARM_SLOTS):
        raise ValueError("REGISTERED_EPISODE_SLOTS_REQUIRED")
    q, wall, usd, seen = 0, Decimal(0), Decimal(0), set()
    for row in usage_rows:
        _object(row)
        if set(row) != {"slot", "usage"} or row["slot"] not in ARM_SLOTS or row["slot"] in seen:
            raise ValueError("NO_EXTRA_OR_REPLACEMENT_EPISODE_SLOT")
        seen.add(row["slot"])
        proposal = row["slot"].endswith("-proposal")
        rq, rw, ru = _usage(row["usage"], request_cap=8 if proposal else 12,
                             wall_cap=400 if proposal else 800)
        q, wall, usd = q + rq, wall + rw, usd + ru
    own = {"requests": q, "wall_s": str(wall), "usd": str(usd)}
    share = {"lineage": lineage, "requests": 0, "wall_s": "0", "usd": "0"}
    if arm == "G1":
        _object(formation_actual)
        if set(formation_actual) != {"requests", "wall_s", "usd"}:
            raise ValueError("COMPLETE_COMMON_FORMATION_ACTUAL_REQUIRED")
        share = formation_allocation(formation_actual["requests"], formation_actual["wall_s"],
                                     formation_actual["usd"])[lineage - 1]
    elif formation_actual is not None:
        raise ValueError("G0_CANNOT_RECHARGE_G1_FORMATION")
    q += share["requests"]
    wall += Decimal(share["wall_s"])
    usd += Decimal(share["usd"])
    if q > 120 or wall > 6600 or usd > 10:
        raise ValueError("ALL_STAGE_ARM_BUDGET_EXCEEDED")
    return {"arm": arm, "lineage": lineage, "own_usage": own, "formation_share": share,
            "total_requests": q, "total_wall_s": str(wall), "total_usd": str(usd),
            "remaining_requests": 120 - q, "remaining_wall_s": str(Decimal(6600) - wall),
            "remaining_usd": str(Decimal(10) - usd), "dispatch_authority": "NONE"}
