"""Pure phase-three information projection and lossless E4 serialization.

No filesystem, provider, solver, source acquisition or verdict computation.
S0 supplies public facts and binds/enforces the actual tool and budget contract.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re


BUDGET = {"provider_requests": 24, "wall_s": 1200, "distinct_designs": 2,
          "candidate_executions": 2, "native_dispatches": 0}
CONDITIONS = {
    "average-energy": ("average-energy-only", ("design",)),
    "rich-static": ("all-public-facts", ("design",)),
    "complete-raw": ("all-public-facts", ("design",)),
    "executable-response": ("all-public-facts", ("design", "model_response")),
    "live-e5": ("average-energy-only", ("design", "observation")),
}
_PRIVATE = {"expected", "expected_verdict", "reference_verdict", "ground_truth",
            "answer_key", "hidden_final", "required_fields", "relevant_fields",
            "target_relation", "target_observation", "target_expression"}
_MAX_BYTES, _MAX_NODES, _MAX_DEPTH = 2_000_000, 32768, 32
_HEADER = "| pointer_json | kind | value_json |\n| --- | --- | --- |"


def canonical(value) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("FINITE_JSON_REQUIRED") from exc


def _sha(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _public(value):
    if len(canonical(value)) > _MAX_BYTES:
        raise ValueError("PACKET_BYTE_LIMIT")
    stack, count = [(value, 0)], 0
    while stack:
        node, depth = stack.pop(); count += 1
        if depth > _MAX_DEPTH or count > _MAX_NODES:
            raise ValueError("PACKET_STRUCTURE_LIMIT")
        if isinstance(node, dict):
            if any(not isinstance(k, str) for k in node):
                raise ValueError("STRING_KEYS_REQUIRED")
            if _PRIVATE.intersection(node):
                raise ValueError("EVALUATOR_OR_ANSWER_METADATA")
            stack.extend((x, depth + 1) for x in node.values())
        elif isinstance(node, list):
            stack.extend((x, depth + 1) for x in node)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            try:
                finite = math.isfinite(float(node))
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("FINITE_NUMBER_REQUIRED")


def validate_conditions(config: dict) -> dict:
    """Check the fixed five-arm and separate E4 registration, without running it."""
    if config.get("schema_version") != "phase3-bf-interface-conditions-v1":
        raise ValueError("UNKNOWN_CONDITION_SCHEMA")
    rows = config.get("conditions", [])
    if len(rows) != 5 or {r["id"] for r in rows} != set(CONDITIONS):
        raise ValueError("FIVE_REGISTERED_CONDITIONS_REQUIRED")
    for row in rows:
        projection, roles = CONDITIONS[row["id"]]
        if (row["initial_projection"], tuple(row["tool_roles"])) != (projection, roles):
            raise ValueError("CONDITION_PROJECTION_OR_PERMISSIONS_CHANGED")
    if any(config["group_budget"].get(k) != v for k, v in BUDGET.items()):
        raise ValueError("MATCHED_TOTAL_BUDGET_REQUIRED")
    e4 = config["e4"]
    if e4["base_condition"] != "rich-static" or {a["representation"] for a in e4["arms"]} != {"json", "table"} or len(e4["arms"]) != 2:
        raise ValueError("E4_COMPLETE_STATIC_PAIR_REQUIRED")
    for flag in ["same_payload", "same_tool_permissions", "same_budget", "same_common_task_and_design_space", "no_added_summaries_or_answers", "independent_cells"]:
        if e4.get(flag) is not True:
            raise ValueError("E4_EQUAL_INFORMATION_REQUIRED")
    tasks = config["task_matrix"]["tasks"]
    if len(tasks) > 4 or len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("FOUR_DISTINCT_TASKS_MAXIMUM")
    return {"status": "PASS", "conditions": 5, "e4_arms": 2, "tasks": len(tasks),
            "budget": copy.deepcopy(BUDGET), "scientific_execution": "NOT_RUN"}


def project_condition(public_facts: dict, condition_id: str, *, common: dict,
                      average_energy: dict, tool_catalog: dict) -> dict:
    """Project host-owned public inputs, preserving every fact in strong arms.

    common contains at least task and legal_design_space (and any common units,
    assumptions, source identities or resource explanation). average_energy is
    an S0-declared coarse summary, never an inferred target relation. Tool keys
    are logical roles: design, model_response, observation; S0 maps each role to
    its actual frozen host tool definition. E4 serializes one rich-static packet
    twice, so arm labels never add facts or tool rights.
    """
    if not isinstance(condition_id, str) or condition_id not in CONDITIONS:
        raise ValueError("UNKNOWN_CONDITION")
    for value in [public_facts, common, average_energy, tool_catalog]:
        if not isinstance(value, dict):
            raise ValueError("PUBLIC_MAPPING_REQUIRED")
        _public(value)
    if not {"task", "legal_design_space"} <= common.keys():
        raise ValueError("COMMON_TASK_AND_LEGAL_SPACE_REQUIRED")
    projection, roles = CONDITIONS[condition_id]
    if not set(roles) <= tool_catalog.keys():
        raise ValueError("REGISTERED_TOOL_ROLE_MISSING")
    facts = public_facts if projection == "all-public-facts" else average_energy
    packet = {"schema_version": "phase3-interface-packet-v1", "condition": condition_id,
              "common": copy.deepcopy(common), "facts": copy.deepcopy(facts),
              "full_public_facts_sha256": _sha(public_facts),
              "tools": {role: copy.deepcopy(tool_catalog[role]) for role in roles},
              "budget": copy.deepcopy(BUDGET)}
    _public(packet)
    return packet


def _kind(value):
    if isinstance(value, dict): return "object"
    if isinstance(value, list): return "array"
    if isinstance(value, bool): return "boolean"
    if value is None: return "null"
    if isinstance(value, str): return "string"
    return "number"


def _rows(value, path=""):
    kind = _kind(value)
    yield path, kind, {} if kind == "object" else [] if kind == "array" else value
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _rows(value[key], path + "/" + key.replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _rows(child, path + "/" + str(index))


def _cell(value):
    # JSON escape the Markdown delimiters; decoding preserves the exact text.
    text = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    for character, escaped in [("|", r"\u007c"), ("`", r"\u0060"), ("<", r"\u003c"), (">", r"\u003e")]:
        text = text.replace(character, escaped)
    return "`" + text + "`"


def encode_packet(packet: dict, representation: str) -> str:
    _public(packet)
    if representation == "json":
        return canonical(packet).decode()
    if representation != "table":
        raise ValueError("JSON_OR_TABLE_REQUIRED")
    text = _HEADER + "\n" + "\n".join(
        f"| {_cell(path)} | {kind} | {_cell(value)} |" for path, kind, value in _rows(packet))
    if len(text.encode()) > _MAX_BYTES:
        raise ValueError("SERIALIZED_PACKET_BYTE_LIMIT")
    return text


def _unique_pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json(text):
    def reject(_): raise ValueError("NONFINITE_JSON")
    try:
        return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=reject)
    except (RecursionError, TypeError) as exc:
        raise ValueError("BOUNDED_JSON_REQUIRED") from exc


def decode_packet(text: str, representation: str) -> dict:
    if not isinstance(text, str) or len(text.encode()) > _MAX_BYTES:
        raise ValueError("SERIALIZED_PACKET_BYTE_LIMIT")
    if representation == "json":
        result = _json(text)
    elif representation == "table":
        lines = text.strip().splitlines()
        if lines[:2] != _HEADER.splitlines() or len(lines) > _MAX_NODES + 2:
            raise ValueError("CANONICAL_TABLE_HEADER_REQUIRED")
        nodes, rows = {}, []
        for line in lines[2:]:
            cells = line.split("|")
            if len(cells) != 5 or cells[0].strip() or cells[-1].strip():
                raise ValueError("TABLE_ROW_REQUIRED")
            path_cell, kind, value_cell = [c.strip() for c in cells[1:-1]]
            if any(not (c.startswith("`") and c.endswith("`")) for c in [path_cell, value_cell]):
                raise ValueError("JSON_TABLE_CELL_REQUIRED")
            path, value = _json(path_cell[1:-1]), _json(value_cell[1:-1])
            if not isinstance(path, str) or path in nodes or _kind(value) != kind:
                raise ValueError("DUPLICATE_PATH_OR_TYPE_MISMATCH")
            if kind in {"object", "array"} and value:
                raise ValueError("CONTAINER_STRUCTURE_ROW_REQUIRED")
            if path == "":
                if nodes: raise ValueError("ROOT_FIRST_REQUIRED")
            else:
                if not path.startswith("/") or re.search(r"~(?![01])", path):
                    raise ValueError("JSON_POINTER_REQUIRED")
                parent_path, segment = path.rsplit("/", 1)
                if parent_path not in nodes:
                    raise ValueError("PARENT_FIRST_REQUIRED")
                parent = nodes[parent_path]
                key = segment.replace("~1", "/").replace("~0", "~")
                if isinstance(parent, dict):
                    if key in parent: raise ValueError("DUPLICATE_OBJECT_FIELD")
                    parent[key] = value
                elif isinstance(parent, list) and segment == str(len(parent)):
                    parent.append(value)
                else:
                    raise ValueError("INVALID_CONTAINER_OR_ARRAY_INDEX")
            nodes[path] = value
            rows.append((path, kind, copy.deepcopy(value)))
        if "" not in nodes:
            raise ValueError("ROOT_REQUIRED")
        result = nodes[""]
        if list(_rows(result)) != rows:
            raise ValueError("CANONICAL_NODE_ORDER_REQUIRED")
    else:
        raise ValueError("JSON_OR_TABLE_REQUIRED")
    if not isinstance(result, dict):
        raise ValueError("PACKET_OBJECT_REQUIRED")
    _public(result)
    return result


def validate_equal_information(json_packet: str, table_packet: str) -> dict:
    left, right = decode_packet(json_packet, "json"), decode_packet(table_packet, "table")
    if canonical(left) != canonical(right):
        raise ValueError("E4_FACT_TOOL_OR_BUDGET_MISMATCH")
    if left.get("condition") != "rich-static":
        raise ValueError("E4_RICH_STATIC_REQUIRED")
    if left.get("budget") != BUDGET or set(left.get("tools", {})) != {"design"}:
        raise ValueError("E4_REGISTERED_PERMISSIONS_AND_BUDGET_REQUIRED")
    return {"status": "PASS", "decoded_packet_sha256": _sha(left),
            "facts_sha256": _sha(left["facts"]), "tools_sha256": _sha(left["tools"]),
            "common_sha256": _sha(left["common"]), "budget": copy.deepcopy(BUDGET),
            "model_format_benefit": "NOT_TESTED", "scientific_execution": "NOT_RUN"}
