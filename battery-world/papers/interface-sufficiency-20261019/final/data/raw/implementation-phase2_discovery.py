"""Bounded observation proposals, not an E5 experiment or authority service.

Only JSON is interpreted. No eval, generated Python, filesystem reads, provider
calls, scientific solver or consumer execution occurs in the three public pure
APIs. S0 owns sources/acquisition, qualification, policy consumption and usage.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASELINE = "P2-f7ac8bfc4d5f262ff2736e25298d0c4bddd43b2f2064ae0c48b3bdb42b612977"
PROTOCOL = "configs/studies/phase2-20261020/interfaces/protocol.json"
OUTPUT = "docs/research/phase2-20261020/interfaces"
PROPOSAL_SCHEMA = "phase2-observation-proposal-v1"
MAX_SOURCE_BYTES = 8_000_000
MAX_ITEMS = 262144
MAX_VECTOR = 32768
MAX_NODES = 64
MAX_DEPTH = 8
_IDENT = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_ADMIN = {"expected", "expected_verdict", "reference_verdict", "ground_truth",
          "answer_key", "required_fields", "relevant_fields", "target_relation",
          "target_observation", "target_label"}
_ARITY = {**dict.fromkeys(["add", "sub", "mul", "div", "eq", "lt", "le", "gt", "ge", "and", "or"], 2),
          **dict.fromkeys(["min", "max", "mean", "sum", "abs", "neg", "sqrt", "not", "all", "any"], 1)}
_ZERO = (0, 0, 0, 0)  # kg, m, s, A


class ProposalError(ValueError):
    """A structural, resource, unit or source contract was rejected."""


class _Unavailable(Exception):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProposalError("FINITE_NUMBER_REQUIRED")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ProposalError("FINITE_NUMBER_REQUIRED") from exc
    if not math.isfinite(result):
        raise ProposalError("FINITE_NUMBER_REQUIRED")
    return result


def _text(value: Any, maximum: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ProposalError("BOUNDED_STRING_REQUIRED")
    return value


def _keys(value: Any, required: set, optional: set = frozenset()) -> None:
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        raise ProposalError("UNDECLARED_OR_MISSING_FIELDS")


def _bounded_json(value: Any, *, source: bool = False) -> None:
    pending = [(value, 0)]
    count = 0
    while pending:
        child, depth = pending.pop()
        count += 1
        if count > MAX_ITEMS or depth > 32:
            raise ProposalError("JSON_RESOURCE_LIMIT")
        if isinstance(child, dict):
            if len(child) > 1024 or any(not isinstance(k, str) or len(k) > 256 for k in child):
                raise ProposalError("JSON_OBJECT_LIMIT")
            if source and _ADMIN.intersection(child):
                raise ProposalError("EVALUATOR_METADATA_IN_SOURCE")
            pending.extend((x, depth + 1) for x in child.values())
        elif isinstance(child, list):
            if len(child) > MAX_VECTOR:
                raise ProposalError("VECTOR_RESOURCE_LIMIT")
            pending.extend((x, depth + 1) for x in child)
        elif isinstance(child, str):
            if len(child) > 16384:
                raise ProposalError("JSON_STRING_LIMIT")
        elif child is not None and not isinstance(child, bool):
            _number(child)
    if len(canonical(value)) > MAX_SOURCE_BYTES:
        raise ProposalError("JSON_BYTE_LIMIT")


def _pointer(value: Any) -> str:
    path = _text(value, 256, empty=True)
    if (path and not path.startswith("/")) or len(path.split("/")) > 17 or re.search(r"~(?![01])", path):
        raise ProposalError("JSON_POINTER_REQUIRED")
    return path


def _get(source: Any, path: str) -> Any:
    node = source
    for part in path.split("/")[1:] if path else []:
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and key in node:
            node = node[key]
        elif isinstance(node, list) and re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < len(node):
            node = node[int(key)]
        else:
            raise _Unavailable("MISSING_FIELD")
    if node is None:
        raise _Unavailable("UNAVAILABLE_VALUE")
    return node


@dataclass(frozen=True)
class _Unit:
    scale: float
    dimensions: tuple[int, int, int, int]


_UNITS = {
    "1": _Unit(1, _ZERO), "kg": _Unit(1, (1, 0, 0, 0)),
    "m": _Unit(1, (0, 1, 0, 0)), "s": _Unit(1, (0, 0, 1, 0)),
    "A": _Unit(1, (0, 0, 0, 1)), "J": _Unit(1, (1, 2, -2, 0)),
    "W": _Unit(1, (1, 2, -3, 0)), "V": _Unit(1, (1, 2, -3, -1)),
    "F": _Unit(1, (-1, -2, 4, 2)), "ohm": _Unit(1, (1, 2, -3, -2)),
    "C": _Unit(1, (0, 0, 1, 1)), "Hz": _Unit(1, (0, 0, -1, 0)),
}
for _base in ("J", "W", "V", "F", "A", "s"):
    for _prefix, _scale in [("m", 1e-3), ("u", 1e-6), ("n", 1e-9)]:
        _UNITS[_prefix + _base] = _Unit(_scale, _UNITS[_base].dimensions)


def _unit(value: Any) -> _Unit:
    unit = _text(value, 48).replace("µ", "u")
    pieces = re.split(r"([*/])", unit)
    result, sign = _Unit(1, _ZERO), 1
    for i, token in enumerate(pieces):
        if i % 2:
            sign = -1 if token == "/" else 1
            continue
        match = re.fullmatch(r"([A-Za-z]+|1)(?:\^(-?[0-9]{1,2}))?", token)
        if not match or match[1] not in _UNITS:
            raise ProposalError("UNSUPPORTED_UNIT")
        power = int(match[2] or 1) * sign
        if abs(power) > 8:
            raise ProposalError("UNIT_EXPONENT_LIMIT")
        atom = _UNITS[match[1]]
        dims = tuple(a + power * b for a, b in zip(result.dimensions, atom.dimensions))
        if any(abs(x) > 16 for x in dims):
            raise ProposalError("UNIT_DIMENSION_LIMIT")
        try:
            scale = result.scale * atom.scale ** power
        except OverflowError as exc:
            raise ProposalError("UNIT_SCALE_LIMIT") from exc
        if not math.isfinite(scale) or scale <= 0 or not math.isfinite(1 / scale):
            raise ProposalError("UNIT_SCALE_LIMIT")
        result = _Unit(scale, dims)
    return result


def _infer(op: str, dimensions: list[tuple]) -> tuple:
    left = dimensions[0]
    if op in {"add", "sub", "eq", "lt", "le", "gt", "ge"}:
        if left != dimensions[1]:
            raise ProposalError("INCOMPATIBLE_DIMENSIONS")
        return _ZERO if op in {"eq", "lt", "le", "gt", "ge"} else left
    if op in {"mul", "div"}:
        return tuple(a + (1 if op == "mul" else -1) * b for a, b in zip(left, dimensions[1]))
    if op == "sqrt":
        if any(x % 2 for x in left):
            raise ProposalError("FRACTIONAL_UNIT_DIMENSION_UNSUPPORTED")
        return tuple(x // 2 for x in left)
    if op in {"and", "or", "not", "all", "any"}:
        if any(x != _ZERO for x in dimensions):
            raise ProposalError("BOOLEAN_REQUIRES_DIMENSIONLESS")
        return _ZERO
    return left


def _validate_ast(node: Any, *, depth: int, counts: dict) -> tuple[dict, tuple]:
    counts["nodes"] += 1
    if counts["nodes"] > MAX_NODES or depth > MAX_DEPTH:
        raise ProposalError("AST_RESOURCE_LIMIT")
    if not isinstance(node, dict):
        raise ProposalError("JSON_AST_NODE_REQUIRED")
    if "field" in node:
        _keys(node, {"field", "units"})
        counts["fields"] += 1
        units = _text(node["units"], 48)
        return {"field": _pointer(node["field"]), "units": units}, _unit(units).dimensions
    if "constant" in node:
        _keys(node, {"constant", "units"})
        value, units = node["constant"], _text(node["units"], 48)
        parsed = _unit(units)
        if isinstance(value, (str, bool)):
            if isinstance(value, str):
                _text(value, 128, empty=True)
            if parsed != _Unit(1, _ZERO):
                raise ProposalError("CATEGORY_REQUIRES_UNIT_ONE")
        else:
            value = _number(value)
        return {"constant": value, "units": units}, parsed.dimensions
    _keys(node, {"op", "args"})
    op, args = node["op"], node["args"]
    if not isinstance(op, str) or op not in _ARITY or not isinstance(args, list) or len(args) != _ARITY[op]:
        raise ProposalError("UNSUPPORTED_OPERATOR_OR_ARITY")
    children = [_validate_ast(x, depth=depth + 1, counts=counts) for x in args]
    counts["operators"] += 1
    dims = _infer(op, [x[1] for x in children])
    if any(abs(x) > 16 for x in dims):
        raise ProposalError("UNIT_DIMENSION_LIMIT")
    return {"op": op, "args": [x[0] for x in children]}, dims


def validate_proposal(proposal: dict) -> dict:
    """Normalize only syntax/scope. Never label a proposal a real discovery."""
    _bounded_json(proposal)
    common = {"hypothesis", "mode", "source_id", "units", "domain"}
    _keys(proposal, common, {"schema_version", "field", "ast"})
    if proposal.get("schema_version", PROPOSAL_SCHEMA) != PROPOSAL_SCHEMA:
        raise ProposalError("UNKNOWN_PROPOSAL_SCHEMA")
    mode = proposal["mode"]
    if not isinstance(mode, str) or mode not in {"selection", "construction"}:
        raise ProposalError("UNKNOWN_PROPOSAL_MODE")
    source_id = _text(proposal["source_id"], 64)
    if not _IDENT.fullmatch(source_id):
        raise ProposalError("SOURCE_IDENTIFIER_REQUIRED")
    units = _text(proposal["units"], 48)
    output_unit = _unit(units)
    domain = proposal["domain"]
    _keys(domain, {"constraints"}, {"description"})
    if not isinstance(domain["constraints"], list) or len(domain["constraints"]) > 8:
        raise ProposalError("DOMAIN_CONSTRAINT_LIMIT")
    clean_domain = {"constraints": []}
    seen = set()
    for row in domain["constraints"]:
        _keys(row, {"field", "lower", "upper", "units"})
        path = _pointer(row["field"])
        low, high = _number(row["lower"]), _number(row["upper"])
        unit = _text(row["units"], 48)
        _unit(unit)
        if low > high or path in seen:
            raise ProposalError("INVALID_DOMAIN")
        seen.add(path)
        clean_domain["constraints"].append({"field": path, "lower": low, "upper": high, "units": unit})
    if "description" in domain:
        clean_domain["description"] = _text(domain["description"], 2000)
    clean = {"schema_version": PROPOSAL_SCHEMA, "hypothesis": _text(proposal["hypothesis"], 2000),
             "mode": mode, "source_id": source_id, "units": units, "domain": clean_domain}
    if mode == "selection":
        if "field" not in proposal or "ast" in proposal:
            raise ProposalError("SELECTION_REQUIRES_FIELD_ONLY")
        clean["field"] = _pointer(proposal["field"])
    else:
        if "ast" not in proposal or "field" in proposal:
            raise ProposalError("CONSTRUCTION_REQUIRES_AST_ONLY")
        counts = {"nodes": 0, "fields": 0, "operators": 0}
        tree, dimensions = _validate_ast(proposal["ast"], depth=1, counts=counts)
        if not counts["fields"] or not counts["operators"]:
            raise ProposalError("CONSTRUCTION_MUST_USE_SOURCE_AND_OPERATOR")
        if dimensions != output_unit.dimensions:
            raise ProposalError("OUTPUT_UNIT_MISMATCH")
        clean["ast"] = tree
    return clean


def _typed(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    raise _Unavailable("UNSUPPORTED_VALUE_TYPE")


def _numeric(value: Any) -> float:
    try:
        return _number(value)
    except ProposalError as exc:
        raise _Unavailable("NUMERIC_TYPE_REQUIRED") from exc


def _scale(value: Any, factor: float) -> Any:
    if isinstance(value, list):
        return [_scale(x, factor) for x in value]
    if isinstance(value, (bool, str)):
        if factor != 1:
            raise _Unavailable("CATEGORY_UNIT_MISMATCH")
        return value
    result = _numeric(value) * factor
    if not math.isfinite(result):
        raise _Unavailable("NONFINITE_RESULT")
    return result


def _leaf(source: Any, path: str, declared: str, field_units: dict | None, *, selection: bool = False) -> Any:
    unit = _unit(declared)
    if field_units is not None:
        if path not in field_units:
            raise _Unavailable("SOURCE_UNIT_UNAVAILABLE")
        actual = _unit(field_units[path])
        if actual.dimensions != unit.dimensions or (not selection and actual.scale != unit.scale):
            raise _Unavailable("SOURCE_UNIT_MISMATCH")
        unit = actual
    value = _get(source, path)
    if isinstance(value, (str, bool)) and unit != _Unit(1, _ZERO):
        raise _Unavailable("CATEGORY_UNIT_MISMATCH")
    return _scale(value, unit.scale)


def _binary(fn, left: Any, right: Any) -> Any:
    if isinstance(left, list) or isinstance(right, list):
        if isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                raise _Unavailable("VECTOR_LENGTH_MISMATCH")
            return [_binary(fn, a, b) for a, b in zip(left, right)]
        return [_binary(fn, x, right) for x in left] if isinstance(left, list) else [_binary(fn, left, x) for x in right]
    return fn(left, right)


def _eval(node: dict, source: Any, field_units: dict | None, count: list) -> Any:
    count[0] += 1
    if "field" in node:
        return _leaf(source, node["field"], node["units"], field_units)
    if "constant" in node:
        return _scale(node["constant"], _unit(node["units"]).scale)
    op = node["op"]
    args = [_eval(x, source, field_units, count) for x in node["args"]]
    if op in {"min", "max", "mean", "sum", "all", "any"}:
        values = args[0]
        if not isinstance(values, list) or not values:
            raise _Unavailable("NONEMPTY_VECTOR_REQUIRED")
        if op in {"all", "any"}:
            if any(not isinstance(x, bool) for x in values):
                raise _Unavailable("BOOLEAN_TYPE_REQUIRED")
            return all(values) if op == "all" else any(values)
        values = [_numeric(x) for x in values]
        if op == "min":
            return min(values)
        if op == "max":
            return max(values)
        return math.fsum(values) / (len(values) if op == "mean" else 1)
    if op in {"abs", "neg", "sqrt", "not"}:
        def unary(x):
            if op == "not":
                if not isinstance(x, bool):
                    raise _Unavailable("BOOLEAN_TYPE_REQUIRED")
                return not x
            value = _numeric(x)
            if op == "sqrt" and value < 0:
                raise _Unavailable("SQRT_DOMAIN")
            return abs(value) if op == "abs" else -value if op == "neg" else math.sqrt(value)
        return [unary(x) for x in args[0]] if isinstance(args[0], list) else unary(args[0])
    def binary(a, b):
        if op in {"and", "or"}:
            if not isinstance(a, bool) or not isinstance(b, bool):
                raise _Unavailable("BOOLEAN_TYPE_REQUIRED")
            return a and b if op == "and" else a or b
        if op == "eq":
            if _typed(a) != _typed(b):
                raise _Unavailable("STRICT_TYPE_MISMATCH")
            return a == b
        a, b = _numeric(a), _numeric(b)
        if op == "add": return a + b
        if op == "sub": return a - b
        if op == "mul": return a * b
        if op == "div":
            if b == 0: raise _Unavailable("DIVISION_BY_ZERO")
            return a / b
        if op == "lt": return a < b
        if op == "le": return a <= b
        if op == "gt": return a > b
        if op == "ge": return a >= b
        raise ProposalError("UNSUPPORTED_OPERATOR")
    return _binary(binary, args[0], args[1])


def evaluate_proposal(spec: dict, source_payload: Any, *, field_units: dict | None = None) -> dict:
    """Return one unqualified typed scalar from the corresponding raw JSON.

    field_units is an optional S0-supplied mapping, not participant metadata.
    Two-argument calls retain declared units only; this must not be promoted to
    independently verified physical units or source provenance.
    """
    start = time.perf_counter_ns()
    safe = validate_proposal(spec)
    _bounded_json(source_payload, source=True)
    if field_units is not None:
        if not isinstance(field_units, dict):
            raise ProposalError("FIELD_UNIT_MAPPING_REQUIRED")
        for path, unit in field_units.items():
            _pointer(path); _unit(unit)
    count = [0]
    status, reason, value, kind = "OBSERVED", None, None, None
    try:
        for row in safe["domain"]["constraints"]:
            measured = _leaf(source_payload, row["field"], row["units"], field_units)
            scale = _unit(row["units"]).scale
            if not row["lower"] * scale <= _numeric(measured) <= row["upper"] * scale:
                raise _Unavailable("OUT_OF_DOMAIN")
        value = (_leaf(source_payload, safe["field"], safe["units"], field_units, selection=True)
                 if safe["mode"] == "selection" else _eval(safe["ast"], source_payload, field_units, count))
        value = _scale(value, 1 / _unit(safe["units"]).scale)
        kind = _typed(value)
        if kind == "array":
            raise _Unavailable("SCALAR_CONSUMER_OUTPUT_REQUIRED")
        if isinstance(value, (bool, str)) and _unit(safe["units"]) != _Unit(1, _ZERO):
            raise _Unavailable("CATEGORY_UNIT_MISMATCH")
    except (_Unavailable, OverflowError, ValueError) as exc:
        status, reason, value, kind = "UNKNOWN", str(exc) if isinstance(exc, _Unavailable) else "ARITHMETIC_UNAVAILABLE", None, None
    return {"schema_version": "phase2-observation-result-v1", "status": status,
            "mode": safe["mode"], "source_id": safe["source_id"], "value": value,
            "type": kind, "units": safe["units"], "reason": reason,
            "proposal_sha256": digest(canonical(safe)), "payload_sha256": digest(canonical(source_payload)),
            "unit_status": "CHECKED_AGAINST_SUPPLIED_MAPPING" if field_units is not None else "DECLARED_ONLY",
            "domain_status": "CHECKED_ON_SOURCE" if safe["domain"]["constraints"] and status == "OBSERVED" else "NOT_ESTABLISHED",
            "evaluation": {"wall_ns": time.perf_counter_ns() - start, "ast_nodes_visited": count[0],
                           "scientific_executions": 0, "provider_requests": 0},
            "source_authenticity": "EXTERNAL_REQUIRED", "qualification": "EXTERNAL_REQUIRED",
            "real_consumer": "NOT_EXECUTED", "discovery_claim": "NOT_ESTABLISHED"}


def validate_policy(policy: Any, *, legal_domain: dict | None = None) -> list:
    """Structural table check only. S0 owns matching, legal D and real execution."""
    if not isinstance(policy, list) or not 1 <= len(policy) <= 3:
        raise ProposalError("POLICY_BRANCH_LIMIT")
    out, seen = [], set()
    for row in policy:
        _keys(row, {"equals", "design"})
        value = row["equals"]
        if isinstance(value, str):
            _text(value, 128, empty=True)
        elif not isinstance(value, bool):
            value = _number(value)
        marker = canonical([_typed(value), value])
        if marker in seen:
            raise ProposalError("DUPLICATE_POLICY_BRANCH")
        seen.add(marker)
        _keys(row["design"], {"capacitance_f", "tx_not_before_s"})
        design = {k: _number(v) for k, v in row["design"].items()}
        if design["capacitance_f"] <= 0 or design["tx_not_before_s"] < 0:
            raise ProposalError("INVALID_DEVICE_VALUE")
        if legal_domain is not None:
            for k, value_d in design.items():
                if k not in legal_domain or len(legal_domain[k]) != 2:
                    raise ProposalError("FROZEN_LEGAL_DOMAIN_REQUIRED")
                low, high = map(_number, legal_domain[k])
                if not low <= value_d <= high:
                    raise ProposalError("DESIGN_OUT_OF_DOMAIN")
        out.append({"equals": value, "design": design})
    return out


def tool_schema() -> dict:
    """Generic parameters only: no target fields, relation, expression or examples."""
    unit = {"type": "string", "minLength": 1, "maxLength": 48}
    pointer = {"type": "string", "maxLength": 256}
    scalar = {"type": ["number", "boolean", "string"]}
    domain = {"type": "object", "additionalProperties": False, "required": ["constraints"],
              "properties": {"description": {"type": "string", "maxLength": 2000},
                             "constraints": {"type": "array", "maxItems": 8, "items": {
                                 "type": "object", "additionalProperties": False,
                                 "required": ["field", "lower", "upper", "units"],
                                 "properties": {"field": pointer, "lower": {"type": "number"},
                                                "upper": {"type": "number"}, "units": unit}}}}}
    ast = {"oneOf": [
        {"type": "object", "additionalProperties": False, "required": ["field", "units"],
         "properties": {"field": pointer, "units": unit}},
        {"type": "object", "additionalProperties": False, "required": ["constant", "units"],
         "properties": {"constant": scalar, "units": unit}},
        {"type": "object", "additionalProperties": False, "required": ["op", "args"],
         "properties": {"op": {"type": "string", "enum": sorted(_ARITY)},
                        "args": {"type": "array", "minItems": 1, "maxItems": 2,
                                 "items": {"$ref": "#/$defs/ast"}}}}]}
    spec = {"type": "object", "additionalProperties": False,
            "required": ["hypothesis", "mode", "source_id", "units", "domain"],
            "properties": {"schema_version": {"const": PROPOSAL_SCHEMA},
                           "hypothesis": {"type": "string", "minLength": 1, "maxLength": 2000},
                           "mode": {"type": "string", "enum": ["selection", "construction"]},
                           "source_id": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{0,63}$"},
                           "field": pointer, "ast": {"$ref": "#/$defs/ast"},
                           "units": unit, "domain": domain},
            "oneOf": [{"properties": {"mode": {"const": "selection"}}, "required": ["field"], "not": {"required": ["ast"]}},
                      {"properties": {"mode": {"const": "construction"}}, "required": ["ast"], "not": {"required": ["field"]}}]}
    design = {"type": "object", "additionalProperties": False,
              "required": ["capacitance_f", "tx_not_before_s"],
              "properties": {"capacitance_f": {"type": "number", "exclusiveMinimum": 0},
                             "tx_not_before_s": {"type": "number", "minimum": 0}}}
    return {"type": "object", "additionalProperties": False, "required": ["action"],
            "$defs": {"ast": ast, "spec": spec},
            "properties": {"action": {"type": "string", "enum": ["sources", "acquire", "propose", "submit"]},
                           "source_id": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{0,63}$"},
                           "spec": {"$ref": "#/$defs/spec"},
                           "policy": {"type": "array", "minItems": 1, "maxItems": 3,
                                      "items": {"type": "object", "additionalProperties": False,
                                                "required": ["equals", "design"],
                                                "properties": {"equals": scalar, "design": design}}}},
            "oneOf": [{"properties": {"action": {"const": "sources"}}, "not": {"anyOf": [{"required": [k]} for k in ["source_id", "spec", "policy"]]}},
                      {"properties": {"action": {"const": "acquire"}}, "required": ["source_id"], "not": {"anyOf": [{"required": [k]} for k in ["spec", "policy"]]}},
                      {"properties": {"action": {"enum": ["propose", "submit"]}}, "required": ["spec", "policy"], "not": {"required": ["source_id"]}}]}


def validate_request(request: dict, *, legal_domain: dict | None = None) -> dict:
    _bounded_json(request)
    action = request.get("action") if isinstance(request, dict) else None
    if action == "sources":
        _keys(request, {"action"}); return {"action": action}
    if action == "acquire":
        _keys(request, {"action", "source_id"})
        source_id = _text(request["source_id"], 64)
        if not _IDENT.fullmatch(source_id): raise ProposalError("SOURCE_IDENTIFIER_REQUIRED")
        return {"action": action, "source_id": source_id}
    if isinstance(action, str) and action in {"propose", "submit"}:
        _keys(request, {"action", "spec", "policy"})
        return {"action": action, "spec": validate_proposal(request["spec"]),
                "policy": validate_policy(request["policy"], legal_domain=legal_domain)}
    raise ProposalError("UNSUPPORTED_HOST_ACTION")


def bind_acquisition(source_id: str, raw: bytes | None, expected_sha256: str,
                     costs: dict, *, status: str = "OBSERVED") -> dict:
    """Bind an attempt, retaining FAILED/UNKNOWN costs; never qualify its source.

    expected_sha256 and costs must be supplied by the trusted S0 broker/ledger.
    Hash consistency alone does not establish their authority.
    """
    if not isinstance(source_id, str) or not _IDENT.fullmatch(source_id):
        raise ProposalError("SOURCE_IDENTIFIER_REQUIRED")
    if not isinstance(expected_sha256, str) or not _HASH.fullmatch(expected_sha256):
        raise ProposalError("EXTERNAL_SOURCE_HASH_REQUIRED")
    _keys(costs, {"wall_s", "bytes_read", "model_requests", "scientific_executions", "billing_status", "cost_usd"})
    if costs["billing_status"] not in {"NOT_APPLICABLE", "SETTLED", "UNKNOWN"}:
        raise ProposalError("BILLING_STATUS_REQUIRED")
    for k in ["wall_s", "bytes_read", "model_requests", "scientific_executions", "cost_usd"]:
        if costs[k] is not None and _number(costs[k]) < 0:
            raise ProposalError("INVALID_COST")
    for k in ["bytes_read", "model_requests", "scientific_executions"]:
        if costs[k] is not None and (isinstance(costs[k], bool) or not isinstance(costs[k], int)):
            raise ProposalError("INTEGER_COST_REQUIRED")
    if costs["billing_status"] == "SETTLED" and costs["cost_usd"] is None:
        raise ProposalError("SETTLED_COST_REQUIRED")
    if status not in {"OBSERVED", "UNKNOWN", "FAILED"} or (raw is not None and not isinstance(raw, bytes)):
        raise ProposalError("ACQUISITION_STATUS_OR_BYTES_REQUIRED")
    actual = digest(raw) if raw is not None else None
    payload_hash, reason = None, None
    if status == "OBSERVED":
        if raw is None:
            status, reason = "UNKNOWN", "SOURCE_UNAVAILABLE"
        elif len(raw) > MAX_SOURCE_BYTES:
            status, reason = "REJECTED", "SOURCE_BYTE_LIMIT"
        elif actual != expected_sha256:
            status, reason = "REJECTED", "SOURCE_HASH_MISMATCH"
        else:
            try:
                value = json.loads(raw)
                _bounded_json(value, source=True)
                payload_hash = digest(canonical(value))
            except (ValueError, UnicodeError, RecursionError):
                status, reason = "REJECTED", "SOURCE_JSON_OR_SCOPE_INVALID"
    return {"schema_version": "phase2-acquisition-binding-v1", "source_id": source_id,
            "status": status, "reason": reason, "source_bytes_sha256": actual,
            "expected_source_bytes_sha256": expected_sha256, "payload_sha256": payload_hash,
            "costs": copy.deepcopy(costs), "cost_authority": "S0_EXTERNAL_LEDGER_REQUIRED",
            "qualification": "EXTERNAL_REQUIRED", "consumer": "NOT_EXECUTED"}


def load_protocol(root: Path) -> dict:
    protocol = json.loads((root / PROTOCOL).read_bytes())
    if protocol["source_baseline"] != BASELINE or protocol["feature"] != "BFA-056-phase2-information-discovery":
        raise ProposalError("UNKNOWN_PREPARATION_BASELINE")
    for name, b in protocol["source_pins"].items():
        raw = (root / name).read_bytes()
        if digest(raw) != b["sha256"] or len(raw) != b["bytes"]:
            raise ProposalError("FROZEN_SOURCE_DRIFT:" + name)
    if digest(Path(protocol["baseline_path"]).read_bytes()) != protocol["baseline_sha256"]:
        raise ProposalError("PHASE_TWO_BASELINE_DRIFT")
    return protocol


def preparation_gate(root: Path, profile_path: Path, *, free_bytes: int | None = None) -> dict:
    protocol = load_protocol(root)
    raw = profile_path.read_bytes(); profile = json.loads(raw)
    if digest(raw) != protocol["profile_sha256"] or Path(profile["source_root"]).resolve() != root.resolve().parent:
        raise ProposalError("REGISTERED_PROFILE_CHANGED")
    if profile["capabilities"] != {"model": False, "agent": False, "native": False}:
        raise ProposalError("WORKER_EXECUTION_CAPABILITY_DISABLED")
    free = shutil.disk_usage(root).free if free_bytes is None else free_bytes
    cap = protocol["cost_cap"]; required = cap["reserve_bytes"] + cap["phase_peak_additional_bytes"]
    if free < required:
        raise ProposalError("INSUFFICIENT_STORAGE_RESERVE")
    return {"status": "PASS", "free_bytes": free, "required_free_bytes": required,
            "capabilities": profile["capabilities"], "paid_requests": 0, "native_dispatches": 0,
            "scientific_executions": 0}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False).encode() + b"\n")


def prepare_mock(root: Path, profile_path: Path, output: Path) -> dict:
    gate = preparation_gate(root, profile_path)
    allowed = (root / OUTPUT).resolve()
    if output.is_symlink() or output.resolve() == allowed or not output.resolve().is_relative_to(allowed):
        raise ProposalError("OWNED_NEW_OUTPUT_REQUIRED")
    if any(x.is_symlink() for x in [output, *output.parents]):
        raise ProposalError("OUTPUT_SYMLINK_REJECTED")
    output.mkdir(parents=True, exist_ok=False)
    source = {"alpha": 2.0, "beta": 3.0, "flag": True, "series": [1, 2, 3]}
    selection = {"hypothesis": "MOCK field-selection fixture, not an Agent proposal", "mode": "selection",
                 "source_id": "mock-record", "field": "/flag", "units": "1", "domain": {"constraints": []}}
    construction = {"hypothesis": "MOCK researcher-authored arithmetic fixture, not discovery", "mode": "construction",
                    "source_id": "mock-record", "units": "J", "domain": {"constraints": []},
                    "ast": {"op": "add", "args": [{"field": "/alpha", "units": "J"}, {"field": "/beta", "units": "J"}]}}
    units = {"/alpha": "J", "/beta": "J", "/flag": "1", "/series": "J"}
    rows = [{"fixture": "MOCK", "proposal_origin": "researcher-defined unit fixture",
             "spec": validate_proposal(spec), "result": evaluate_proposal(spec, source, field_units=units)}
            for spec in [selection, construction]]
    costs = {"wall_s": 0.0, "bytes_read": len(canonical(source)), "model_requests": 0,
             "scientific_executions": 0, "billing_status": "NOT_APPLICABLE", "cost_usd": 0.0}
    acquired = bind_acquisition("mock-record", canonical(source), digest(canonical(source)), costs)
    bad = copy.deepcopy(construction); bad["ast"]["op"] = "python"
    try:
        validate_proposal(bad)
        raise AssertionError("Unsafe AST was accepted")
    except ProposalError:
        unsafe_rejected = True
    missing = copy.deepcopy(selection); missing["field"] = "/absent"
    unknown = evaluate_proposal(missing, source)
    tampered = bind_acquisition("mock-record", canonical(source) + b" ", digest(canonical(source)), costs)
    checks = {"unsupported_AST_rejected": unsafe_rejected, "uninformative_missing_field_UNKNOWN": unknown["status"] == "UNKNOWN",
              "tampered_source_rejected": tampered["status"] == "REJECTED",
              "construction_remains_MOCK_baseline": rows[1]["result"]["discovery_claim"] == "NOT_ESTABLISHED",
              "no_self_qualification_or_consumer": all(x["result"]["qualification"] == "EXTERNAL_REQUIRED" and x["result"]["real_consumer"] == "NOT_EXECUTED" for x in rows)}
    assert all(checks.values())
    write_json(output / "tool-schema.json", tool_schema())
    write_json(output / "mock-source.json", {"fixture": "MOCK", "data": source, "field_units": units})
    write_json(output / "mock-results.json", {"fixture": "MOCK", "rows": rows, "acquisition": acquired})
    write_json(output / "negative-controls.json", {"fixture": "MOCK", "checks": checks,
                                                 "unknown": unknown, "tampered_source": tampered})
    result = {"schema_version": "phase2-discovery-preparation-v1", "status": "PASS", "baseline": BASELINE,
              "scope": "MOCK preparation only; structural/value checks are not E5 evidence",
              "modes": ["selection", "construction"], "mock_examples": 2, "mock_negative_controls": checks,
              "gate": gate, "protocol_sha256": digest((root / PROTOCOL).read_bytes()),
              "implementation_sha256": digest(Path(__file__).read_bytes()), "live_agent_proposal": "NOT_RUN",
              "external_qualification": "NOT_RUN", "actual_policy_consumer": "NOT_RUN", "independent_service": "NOT_RUN",
              "paid_requests": 0, "native_dispatches": 0, "scientific_executions": 0}
    write_json(output / "result.json", result)
    files = {str(f.relative_to(output)): {"sha256": digest(f.read_bytes()), "bytes": f.stat().st_size}
             for f in sorted(output.rglob("*")) if f.is_file()}
    total = sum(x["bytes"] for x in files.values())
    if total > 20_000_000:
        raise ProposalError("WORKER_RETAINED_CAP")
    write_json(output / "seal.json", {"schema_version": "phase2-discovery-mock-seal-v1", "files": files,
                                       "payload_bytes": total, "fixture": "MOCK"})
    return result
