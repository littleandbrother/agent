"""ABC B: source-bound legal-input preflight and a thin real-consumer adapter.

No provider, native job, or scientific model is started here. S0 supplies the
existing exact-input B executor. Host final judgments are outside the endpoint.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from decimal import Decimal
from pathlib import Path

from . import phase2_discovery as old
from .phase3 import independent_value, scale_value, unit_scale

SCHEMA = "abc-e5-input-v1"
DECISIONS = ("retain", "adopt")
SERVICE_KEYS = ("independent_energy", "independent_receiver", "event_receive",
                "deduplication", "transient_voltage")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def write_once(path, value):
    path = Path(path)
    raw = canonical(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("IMMUTABLE_ARTIFACT_CONFLICT:" + str(path))
        return
    with path.open("xb") as handle:
        handle.write(raw)


class InputError(ValueError):
    def __init__(self, code, field, **details):
        self.record = {"code": code, "field": field, **details}
        super().__init__(code + ":" + field)


def need(ok, code, field, **details):
    if not ok:
        raise InputError(code, field, **details)


def kind(value):
    if type(value) is bool:
        return "boolean"
    if type(value) in (int, float, Decimal):
        need(math.isfinite(float(value)), "FINITE_NUMBER_REQUIRED", "value")
        return "number"
    if type(value) is str:
        return "string"
    raise InputError("SCALAR_REQUIRED", "value", allowed=["boolean", "number", "string"])


def unit_for_dimensions(dims):
    for unit in ("1", "J", "W", "V", "F", "s", "A", "ohm", "C", "Hz", "kg", "m"):
        if old._unit(unit).dimensions == dims:
            return unit
    return "*".join(f"{base}^{power}" for base, power in zip(("kg", "m", "s", "A"), dims)
                    if power) or "1"


def parsed_unit(value, location):
    try:
        return old._unit(value)
    except (ValueError, TypeError):
        raise InputError("VALID_UNIT_REQUIRED", location, allowed_examples=["1", "s", "ms", "J", "uJ", "V", "F", "uF", "A", "ohm"])


def unit_map(payload):
    """Registry from frozen B field definitions; never participant-supplied units."""
    units = {}
    suffixes = {"_s": "s", "_ms": "ms", "_j": "J", "_uj": "uJ", "_w": "W",
                "_v": "V", "_a": "A", "_f": "F", "_uf": "uF", "_ohm": "ohm"}
    def walk(value, path="", name=""):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, path+"/"+key.replace("~", "~0").replace("/", "~1"), key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path+"/"+str(index), name)
        elif value is not None:
            units[path] = next((u for ending, u in suffixes.items() if name.endswith(ending)), "1")
    walk(payload)
    return units


def _compile(request, sources, context_id):
    need(isinstance(request, dict), "OBJECT_REQUIRED", "request")
    old._bounded_json(request)
    need(request.get("schema_version") == SCHEMA, "SCHEMA_REQUIRED", "schema_version", allowed=[SCHEMA])
    need(set(request) <= {"schema_version", "hypothesis", "expression", "domain", "output_units", "consumer"},
         "UNKNOWN_FIELDS", "request")
    need(isinstance(request.get("hypothesis"), str) and 0 < len(request["hypothesis"]) <= 2000,
         "HYPOTHESIS_REQUIRED", "hypothesis")
    bundle, units, bindings, used = {}, {}, {}, set()
    for sid, source in sources.items():
        need(source.get("context_id") == context_id, "SOURCE_CONTEXT_MISMATCH", "sources."+sid,
             expected_context=context_id, actual_context=source.get("context_id"))
        need(digest(source["payload"]) == source["source_sha256"], "SOURCE_HASH_MISMATCH", "sources."+sid)
        need(source["field_units"] == unit_map(source["payload"]), "SOURCE_UNIT_REGISTRY_CHANGED", "sources."+sid)
        bundle[sid] = source["payload"]
        bindings[sid] = source["source_sha256"]
        units.update({"/"+sid+path: unit for path, unit in source["field_units"].items()})

    def field(node, location):
        need(set(node) <= {"source_id", "field", "units"} and {"source_id", "field"} <= set(node),
             "SOURCE_FIELD_STRUCTURE", location,
             allowed={"source_id": "catalogue identity", "field": "/JSON/Pointer", "units": "optional compatible target"})
        sid, pointer = node["source_id"], node["field"]
        need(isinstance(sid, str) and sid in sources, "SOURCE_NOT_ACQUIRED", location+".source_id", allowed=sorted(sources))
        try:
            old._pointer(pointer)
            value = old._get(bundle[sid], pointer)
        except (ValueError, TypeError):
            raise InputError("FIELD_NOT_AVAILABLE", location+".field", source_id=sid,
                             allowed_fields=list(sources[sid]["field_units"])[:40])
        registry = sources[sid]["field_units"]
        need(pointer in registry, "SOURCE_UNIT_UNAVAILABLE", location+".field", source_id=sid,
             allowed_fields=list(registry)[:40])
        declared = node.get("units", registry[pointer])
        need(parsed_unit(declared, location+".units").dimensions == old._unit(registry[pointer]).dimensions,
             "INCOMPATIBLE_SOURCE_UNIT", location+".units", source_id=sid, source_field=pointer,
             actual_source_unit=registry[pointer], requested_unit=declared)
        used.add(sid)
        # The stored numeric value is always expressed in its registry unit.
        # Prefix requests are checked here; output/domain conversions are explicit.
        return {"field": "/"+sid+pointer, "units": registry[pointer]}, kind(value), old._unit(registry[pointer]).dimensions

    count = [0]
    def expression(node, depth=1, location="expression"):
        count[0] += 1
        need(count[0] <= 64 and depth <= 8, "AST_RESOURCE_LIMIT", location)
        need(isinstance(node, dict), "AST_OBJECT_REQUIRED", location)
        if "field" in node:
            return field(node, location)
        if "constant" in node:
            need(set(node) <= {"constant", "units"}, "CONSTANT_STRUCTURE", location)
            value, unit = node["constant"], node.get("units", "1")
            tag, parsed = kind(value), parsed_unit(unit, location+".units")
            need(tag == "number" or parsed == old._unit("1"), "CATEGORY_UNIT_ONE_REQUIRED", location)
            return {"constant": value, "units": unit}, tag, parsed.dimensions
        need(set(node) == {"op", "args"} and isinstance(node["args"], list), "OPERATOR_STRUCTURE", location)
        op, args = node["op"], node["args"]
        arities = {"add": 2, "sub": 2, "mul": 2, "div": 2, "eq": 2, "lt": 2, "le": 2,
                   "gt": 2, "ge": 2, "and": 2, "or": 2, "not": 1, "neg": 1, "abs": 1, "sqrt": 1}
        need(op in arities and len(args) == arities[op], "OPERATOR_OR_ARITY", location, allowed=arities)
        children = [expression(a, depth+1, location+".args."+str(i)) for i, a in enumerate(args)]
        tags = [x[1] for x in children]
        if op in ("and", "or", "not"):
            need(all(t == "boolean" for t in tags), "BOOLEAN_OPERANDS_REQUIRED", location, actual=tags)
            tag = "boolean"
        elif op == "eq":
            need(len(set(tags)) == 1, "STRICT_TYPE_MISMATCH", location, actual=tags)
            tag = "boolean"
        else:
            need(all(t == "number" for t in tags), "NUMERIC_OPERANDS_REQUIRED", location, actual=tags)
            tag = "boolean" if op in ("lt", "le", "gt", "ge") else "number"
        try:
            dims = old._infer(op, [x[2] for x in children])
        except ValueError as error:
            raise InputError(str(error), location+".args", operand_dimensions=[list(x[2]) for x in children])
        return {"op": op, "args": [x[0] for x in children]}, tag, dims

    tree, output_type, dims = expression(request.get("expression"))
    output_units = request.get("output_units", unit_for_dimensions(dims))
    need(parsed_unit(output_units, "output_units").dimensions == dims, "OUTPUT_UNIT_MISMATCH", "output_units",
         inferred_unit=unit_for_dimensions(dims))
    constraints = []
    domain = request.get("domain", [])
    need(isinstance(domain, list) and len(domain) <= 8, "DOMAIN_LIMIT", "domain")
    for i, row in enumerate(domain):
        location = "domain."+str(i)
        need(isinstance(row, dict), "DOMAIN_OBJECT_REQUIRED", location)
        leaf, tag, _ = field({k: row[k] for k in ("source_id", "field", "units") if k in row}, location)
        need(set(row) <= {"source_id", "field", "units", "lower", "upper", "equals"}, "DOMAIN_STRUCTURE", location)
        if "equals" in row:
            need("lower" not in row and "upper" not in row, "DOMAIN_STRUCTURE", location)
            value = old._get(bundle, leaf["field"])
            same = kind(value) == kind(row["equals"])
            if same and tag == "number":
                actual_si = Decimal(str(value))*unit_scale(sources[row["source_id"]]["field_units"][row["field"]])
                required_si = Decimal(str(row["equals"]))*unit_scale(row.get("units", leaf["units"]))
                same = actual_si == required_si
            elif same:
                same = value == row["equals"]
            need(same, "SOURCE_CONDITION_NOT_APPLICABLE", location+".equals", actual=value, required=row["equals"])
        else:
            need(tag == "number" and {"lower", "upper"} <= set(row), "NUMERIC_DOMAIN_REQUIRED", location)
            need(kind(row["lower"]) == kind(row["upper"]) == "number", "NUMERIC_DOMAIN_REQUIRED", location)
            scale = unit_scale(row.get("units", leaf["units"]))/unit_scale(leaf["units"])
            constraints.append({"field": leaf["field"], "lower": float(Decimal(str(row["lower"]))*scale), "upper": float(Decimal(str(row["upper"]))*scale), "units": leaf["units"]})
    spec = {"hypothesis": request["hypothesis"], "source_id": "bundle", "units": output_units,
            "domain": {"constraints": constraints}}
    if "field" in tree:
        spec.update(mode="selection", field=tree["field"])
    else:
        spec.update(mode="construction", ast=tree)
    spec = old.validate_proposal(spec)
    result = old.evaluate_proposal(spec, bundle, field_units=units)
    need(result["status"] == "OBSERVED", "SOURCE_RELATION_UNAVAILABLE", "expression", reason=result["reason"])
    # Reuse the existing separate Decimal source-algebra checker, not simulator truth.
    check = (scale_value(old._get(bundle, tree["field"]), unit_scale(units[tree["field"]]))
             if "field" in tree else independent_value(tree, bundle))
    check = scale_value(check, Decimal(1)/unit_scale(output_units))
    got = result["value"]
    if output_type == "number":
        need(abs(Decimal(str(got))-Decimal(str(check))) <= max(Decimal("1e-18"), abs(Decimal(str(check)))*Decimal("1e-12")),
             "INDEPENDENT_VALUE_DISAGREED", "expression")
        got = float(check)
    else:
        need(type(got) is type(check) and got == check, "INDEPENDENT_TYPE_DISAGREED", "expression")
    consumer = request.get("consumer")
    need(isinstance(consumer, dict) and set(consumer) <= {"input_type", "units", "branches", "conversion"},
         "CONSUMER_STRUCTURE", "consumer")
    tag, target_units = consumer.get("input_type"), consumer.get("units", "1")
    need(tag in ("boolean", "number", "string"), "CONSUMER_TYPE_REQUIRED", "consumer.input_type")
    value = got
    conversion = consumer.get("conversion")
    if conversion:
        need(isinstance(conversion, dict) and set(conversion) == {"kind", "true", "false", "units"}
             and conversion["kind"] == "boolean_map" and output_type == "boolean" and tag == "number",
             "EXPLICIT_CONVERSION_STRUCTURE", "consumer.conversion",
             allowed={"kind": "boolean_map", "true": 2, "false": 1, "units": "ms"})
        need(kind(conversion["true"]) == kind(conversion["false"]) == "number",
             "CONVERSION_NUMERIC_VALUES_REQUIRED", "consumer.conversion")
        need(parsed_unit(conversion["units"], "consumer.conversion.units").dimensions == parsed_unit(target_units, "consumer.units").dimensions,
             "CONVERSION_UNIT_MISMATCH", "consumer.conversion.units")
        value = float(Decimal(str(conversion["true"] if got else conversion["false"]))*unit_scale(conversion["units"])/unit_scale(target_units))
    else:
        need(tag == output_type, "CONSUMER_TYPE_MISMATCH", "consumer.input_type", observation_type=output_type,
             allowed_input_type=output_type, explicit_conversion={"kind": "boolean_map", "true": 2, "false": 1, "units": "ms"} if output_type == "boolean" else None)
        need(old._unit(output_units).dimensions == parsed_unit(target_units, "consumer.units").dimensions,
             "CONSUMER_UNIT_MISMATCH", "consumer.units", observation_units=output_units)
        if tag == "number":
            value = float(Decimal(str(value))*unit_scale(output_units)/unit_scale(target_units))
    need(tag == "number" or target_units == "1", "CATEGORY_UNIT_ONE_REQUIRED", "consumer.units")
    branches = consumer.get("branches")
    need(isinstance(branches, list) and 1 <= len(branches) <= 3, "CONSUMER_BRANCH_LIMIT", "consumer.branches")
    selected, seen = None, set()
    for i, row in enumerate(branches):
        need(isinstance(row, dict) and set(row) == {"equals", "decision"}, "BRANCH_STRUCTURE", "consumer.branches."+str(i))
        need(kind(row["equals"]) == tag, "BRANCH_TYPE_MISMATCH", "consumer.branches."+str(i)+".equals", expected_type=tag)
        need(row["decision"] in DECISIONS, "DECISION_REQUIRED", "consumer.branches."+str(i)+".decision", allowed=DECISIONS)
        marker = (tag, row["equals"])
        need(marker not in seen, "DUPLICATE_BRANCH", "consumer.branches."+str(i));seen.add(marker)
        if row["equals"] == value:
            selected = row["decision"]
    need(selected is not None, "NO_TYPED_CONSUMER_MATCH", "consumer.branches", actual_type=tag, actual_value=value, actual_units=target_units)
    return {"schema_version": SCHEMA, "status": "LEGAL", "normalized_source_spec": spec,
            "source_bindings": {sid: bindings[sid] for sid in sorted(used)}, "context_id": context_id,
            "observation": {"value": got, "type": output_type, "units": output_units},
            "consumer_input": {"value": value, "type": tag, "units": target_units},
            "decision": selected, "request_sha256": digest(request), "independent_source_algebra_agrees": True,
            "scope": "Deterministic source/unit/domain/type consistency, not service or physical qualification"}


def preflight(request, sources, context_id):
    start = time.monotonic()
    try:
        value = _compile(request, sources, context_id)
    except InputError as error:
        value = {"schema_version": SCHEMA, "status": "REJECTED", "errors": [error.record]}
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        value = {"schema_version": SCHEMA, "status": "REJECTED", "errors": [{"code": str(error)[:160], "field": "request"}]}
    value["preflight_wall_s"] = time.monotonic()-start
    value["scientific_executions"] = 0
    return value


def _frozen(spec):
    path = Path(spec["frozen_families"])
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == spec["frozen_families_sha256"], "FAMILY_FREEZE_CHANGED", "frozen_families")
    bank = json.loads(raw)
    return bank, bank["cases"][spec["case"]]


def tool_definition(spec):
    return {"name": "abc_interface", "description": "Read equal-access B sources; deterministic cross-source unit/domain/type preflight; execute an immutable retain/adopt input and submit a prediction. Final independent judgment is host-only.",
            "parameters": {"type": "object", "properties": {
                "action": {"enum": ["inspect", "acquire", "preflight", "check", "submit"]},
                "source_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                "request": {"type": "object"}, "decision": {"enum": list(DECISIONS)},
                "prediction": {"enum": ["PASS", "FAIL", "UNKNOWN"]}}, "required": ["action"], "additionalProperties": False}}


def prepare_episode(spec, episode_root):
    bank, case = _frozen(spec)
    condition = spec.get("condition", "observation_refinement")
    need(condition in bank["conditions"], "CONDITION_REQUIRED", "condition")
    root = Path(episode_root)
    context_id = digest({"task_id": case["task_id"], "current": case["current"], "intervention": case["intervention"]})
    root.mkdir(parents=True, exist_ok=True)
    numerical_source = Path(spec["source_root"])/"packages/python/bfworld/src/bfworld/agentlab/campaign20261019/b.py"
    engine_bytes = numerical_source.read_bytes()
    need(hashlib.sha256(engine_bytes).hexdigest() == "86bdf88573956518ed09783f4f83e161b55b2e37e661e74218842542bb7e986b", "FROZEN_B_ENGINE_CHANGED", "source_root")
    sources = {
        "component_record": {"current": case["current"]["device"], "intervention": case["intervention"]["device"], "assembly": case["mechanism_record"]},
        "excitation_record": {role: {k: task[k] for k in ("duration_s", "dt_s", "event_s", "contact_duration_s", "deadline_s", "source_segments", "shunts")} for role, task in [("current", case["current"]), ("intervention", case["intervention"])]},
        "complete_inputs": {"current": case["current"], "intervention": case["intervention"]},
        "model_law": {"model_id": "b-transient-behavior-v1", "python_source": engine_bytes.decode(), "physical_calibration": "UNKNOWN"}}
    catalogue, source_registry = {}, {}
    for sid, payload in sources.items():
        record = {"source_id": sid, "context_id": context_id, "payload": payload,
                  "source_sha256": digest(payload), "field_units": unit_map(payload),
                  "applicability": {"task_id": case["task_id"], "model_id": "b-transient-behavior-v1", "physical_calibration": "UNKNOWN"}}
        write_once(root/"public"/"sources"/(sid+".json"), record)
        source_registry[sid] = digest(record)
        catalogue[sid] = {"source_sha256": record["source_sha256"], "bytes": len(canonical(record)), "field_units": record["field_units"]}
    task = {"task_id": case["task_id"], "family": case["family"], "context_id": context_id,
            "question": "Predict whether the stated intervention preserves complete service; adopt if it does, otherwise retain. Submit PASS/FAIL/UNKNOWN for the intervention separately from your decision.",
             "input_interpretation": "The executable device.event_latch selector controls event retention. The inherited event_latch_scope string describes general apparatus provenance and does not override that selector; inspect both frozen inputs and the model law.",
            "service": {"event_s": case["current"]["event_s"], "deadline_s": case["current"]["deadline_s"], "application_bytes": 8, "unique_frames": 1},
            "legal_decisions": list(DECISIONS), "source_catalogue": catalogue,
            "scope": "Frozen prescribed-source digital B apparatus. No physical calibration. No source, model, evaluator, service or input edit is allowed."}
    prompt = ("All arms have exactly the same complete source files and tool permissions. Source catalogue, units and full executable model are available; no truth labels are provided. "
              "Acquisition, format rejects, preflight, execution and rework are recorded. No automatic retry.\nMETHOD: "+bank["conditions"][condition]+"\n"+REQUEST_HELP)
    write_once(root/"public"/"task.json", task)
    write_once(root/"host"/"case.json", case)
    write_once(root/"host"/"source-registry.json", source_registry)
    write_once(root/"host"/"spec.json", {k: v for k, v in spec.items() if not k.startswith("_")})
    prompt_path = root/"public"/"prompt.txt"
    if prompt_path.exists():
        need(prompt_path.read_text() == prompt, "PREPARED_PROMPT_CHANGED", "condition")
    else:
        prompt_path.write_text(prompt)
    return {"participant_task": str(root/"public"/"task.json"), "prompt": prompt,
            "participant_input": {"task": task, "common_instruction": prompt},
            "public_root": str(root/"public"), "public_files": [str(q) for q in sorted((root/"public").rglob("*")) if q.is_file()],
            "tool": tool_definition(spec), "host_case": str(root/"host"/"case.json"),
            "context_id": context_id, "no_scientific_execution": True}


REQUEST_HELP = """REQUEST abc-e5-input-v1: hypothesis, expression, domain[], consumer.
A source leaf is {\"source_id\":\"catalogue id\",\"field\":\"/JSON/Pointer\"}; its unit is inferred from the host registry. Optional units must be dimension-compatible. Constants are {\"constant\":2,\"units\":\"ms\"}; operators are {\"op\":\"gt\",\"args\":[left,right]} (add/sub/mul/div/eq/lt/le/gt/ge/and/or/not/abs/neg/sqrt). Max 64 nodes/depth8, scalar output.
Each domain row explicitly names its own source_id and field, with lower/upper/optional units OR equals for a source condition. Cross-source references require the same frozen task context. A source field from another task or inapplicable condition is rejected.
consumer={\"input_type\":\"boolean\",\"units\":\"1\",\"branches\":[{\"equals\":true,\"decision\":\"adopt\"},{\"equals\":false,\"decision\":\"retain\"}]}. This is a syntax illustration, not a recommended engineering relation or decision polarity. Number prefixes convert automatically. Boolean is never a number. An intentional Boolean-to-number mapping must explicitly declare conversion={\"kind\":\"boolean_map\",\"true\":2,\"false\":1,\"units\":\"ms\"}, with input_type=number and compatible consumer units; branches use converted values. No implicit Boolean cast.
Use preflight with request to get an exact failing field, allowed structure/type/unit, or a legal normalized input. Preflight never executes science. check/submit accepts either request (real typed observation consumption) OR decision, never both. submit also requires prediction=PASS/FAIL/UNKNOWN for the intervention. Only the S0 real executor runs a selected immutable input. Both possible inputs count toward the same two-design limit. Final independent verdicts are outside this endpoint."""


class EpisodeHandler:
    def __init__(self, episode_root, spec, executor=None):
        self.root, self.spec, self.executor = Path(episode_root), spec, executor
        self.bank, self.case = _frozen(spec)
        task = json.loads((self.root/"public"/"task.json").read_text())
        self.context_id = digest({"task_id": self.case["task_id"], "current": self.case["current"], "intervention": self.case["intervention"]})
        need(task["context_id"] == self.context_id, "PREPARED_TASK_CONTEXT_CHANGED", "task")
        self.source_registry = json.loads((self.root/"host"/"source-registry.json").read_text())
        self.acquired = {}
        self.calls = 0

    def _source(self, sid):
        path = self.root/"public"/"sources"/(sid+".json")
        need(sid in ("component_record", "excitation_record", "complete_inputs", "model_law"), "SOURCE_ID_REQUIRED", "source_ids")
        value = json.loads(path.read_text())
        need(digest(value) == self.source_registry[sid], "SOURCE_RECORD_BINDING_CHANGED", "source_ids."+sid)
        task = json.loads((self.root/"public"/"task.json").read_text())
        need(value["source_sha256"] == task["source_catalogue"][sid]["source_sha256"], "SOURCE_BINDING_CHANGED", "source_ids."+sid)
        need(digest(value["payload"]) == value["source_sha256"], "SOURCE_HASH_MISMATCH", "source_ids."+sid)
        return value

    def execute(self, decision):
        need(decision in DECISIONS, "DECISION_REQUIRED", "decision", allowed=DECISIONS)
        role = "current" if decision == "retain" else "intervention"
        task = self.case[role]
        path = self.root/"host"/"executions"/(digest(task)+".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            need(self.executor is not None, "S0_REAL_EXECUTOR_REQUIRED", "executor")
            result = self.executor(copy.deepcopy(task))
            need(result.get("input_sha256") == digest(task), "EXECUTOR_INPUT_BINDING_FAILED", "execution")
            need("execution_key" in result and "reference" in result and "energy" in result,
                 "EXECUTOR_RESULT_REQUIRED", "execution")
            write_once(path, result)
        need(result.get("input_sha256") == digest(task), "CACHED_INPUT_BINDING_FAILED", "execution")
        return result

    def __call__(self, body):
        self.calls += 1
        need(self.calls <= 40, "TOOL_CAP", "action")
        start = time.monotonic()
        try:
            action = body.get("action")
            if action == "inspect":
                value = {"task": json.loads((self.root/"public"/"task.json").read_text()), "request_help": REQUEST_HELP}
            elif action == "acquire":
                ids = body.get("source_ids", ["component_record", "excitation_record", "complete_inputs", "model_law"])
                need(isinstance(ids, list) and 1 <= len(ids) <= 4, "SOURCE_IDS_REQUIRED", "source_ids")
                records = {sid: self._source(sid) for sid in ids}
                self.acquired.update(records)
                value = {"sources": records, "read_bytes": sum(len(canonical(r)) for r in records.values())}
            elif action in ("preflight", "check", "submit"):
                has_request = "request" in body
                need(has_request and "decision" not in body if action == "preflight" else has_request != ("decision" in body), "EXACTLY_ONE_INPUT_REQUIRED", "request/decision")
                if has_request:
                    value = preflight(body["request"], self.acquired, self.context_id)
                    if value["status"] != "LEGAL" or action == "preflight":
                        return self._record(body, value, start)
                    decision = value["decision"]
                else:
                    need(action != "preflight", "REQUEST_REQUIRED", "request")
                    decision, value = body["decision"], {"decision": body["decision"]}
                if action == "submit":
                    need(body.get("prediction") in ("PASS", "FAIL", "UNKNOWN"), "PREDICTION_REQUIRED", "prediction")
                execution = self.execute(decision)
                consumer = {"used_observation": has_request, "selected_decision": decision,
                            "observation": value.get("observation"), "consumer_input": value.get("consumer_input"),
                            "source_bindings": value.get("source_bindings"), "context_id": value.get("context_id"),
                            "normalized_source_spec": value.get("normalized_source_spec"),
                            "input_edge_sha256": digest({k: v for k, v in value.items() if k != "preflight_wall_s"}), "executed_input_sha256": execution["input_sha256"],
                            "execution_key": execution["execution_key"], "request_sha256": value.get("request_sha256")}
                write_once(self.root/"host"/"consumers"/(digest(consumer)+".json"), consumer)
                if action == "submit":
                    write_once(self.root/"host"/"submission.json", {"decision": decision, "prediction": body["prediction"], "consumer": consumer})
                ref = execution["reference"]
                value = {"recorded": action, "decision": decision, "used_observation": has_request,
                         "executed_input_sha256": execution["input_sha256"], "execution_key": execution["execution_key"],
                         "first_receive_s": ref.get("first_receive_s"), "received_frames": ref.get("received_frames"),
                         "brownouts_before_deadline": ref.get("brownouts_before_deadline"), "exact_input_reused": execution.get("reused"), "physical_qualification": "UNKNOWN"}
            else:
                raise InputError("ACTION_REQUIRED", "action")
        except InputError as error:
            value = {"status": "REJECTED", "errors": [error.record]}
        return self._record(body, value, start)

    def _record(self, body, value, start):
        event = {"number": self.calls, "input": body, "output": value, "wall_s": time.monotonic()-start}
        path = self.root/"host"/"tool-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(canonical(event)+b"\n")
        return value


def create_handler(episode_root, spec, *, executor=None):
    return EpisodeHandler(episode_root, spec, executor=executor)


def independent_check(episode_root, spec, *, executor=None):
    """Read actual independent B verdicts, optionally asking S0 to fill two inputs.

    This function is never installed as a participant action. Fixture executors
    cannot produce a scientific result. Missing execution stays NOT_EVALUATED.
    """
    root = Path(episode_root)
    handler = EpisodeHandler(root, spec, executor=executor)
    executions, missing = {}, []
    for decision in DECISIONS:
        role = "current" if decision == "retain" else "intervention"
        path = root/"host"/"executions"/(digest(handler.case[role])+".json")
        if not path.exists() and executor is None:
            missing.append(decision)
            continue
        executions[decision] = handler.execute(decision)
    if missing:
        return {"status": "NOT_EVALUATED", "missing_inputs": missing, "physical_qualification": "UNKNOWN"}
    need(all(v.get("origin") in ("new-full-feedback-response", "sealed-historical-exact-input") and v.get("execution_fidelity") != "fixture" for v in executions.values()),
         "FIXTURE_NOT_SCIENTIFIC_EVIDENCE", "execution")
    truth = {}
    for decision, value in executions.items():
        verdicts = value["reference"]["verdicts"]
        need(all(verdicts.get(k) in ("PASS", "FAIL", "UNKNOWN") for k in SERVICE_KEYS), "INDEPENDENT_VERDICTS_REQUIRED", "execution.reference.verdicts")
        values = [verdicts[k] for k in SERVICE_KEYS]
        truth[decision] = "FAIL" if "FAIL" in values else "PASS" if all(v == "PASS" for v in values) else "UNKNOWN"
    submission_path = root/"host"/"submission.json"
    sub = json.loads(submission_path.read_text()) if submission_path.exists() else None
    result = {"schema_version": "abc-B-independent-result-v1", "status": "EVALUATED",
              "task_id": handler.case["task_id"], "truth": truth, "submission": sub,
              "coverage": sub is not None and sub["prediction"] != "UNKNOWN",
              "prediction_correct": None if sub is None or sub["prediction"] == "UNKNOWN" or truth["adopt"] == "UNKNOWN" else sub["prediction"] == truth["adopt"],
              "decision_correct": None if sub is None or truth["adopt"] == "UNKNOWN" else sub["decision"] == ("adopt" if truth["adopt"] == "PASS" else "retain"),
              "selected_service": "INCOMPLETE" if sub is None else truth[sub["decision"]],
              "wrong_adoption": bool(sub and sub["decision"] == "adopt" and truth["adopt"] == "FAIL"),
              "wrong_rejection": bool(sub and sub["decision"] == "retain" and truth["adopt"] == "PASS"),
              "execution_keys": {k: v["execution_key"] for k, v in executions.items()},
              "physical_qualification": "UNKNOWN", "new_physical_measurement": False,
              "boundary": "Digital fixed B executor and independent receiver/energy checks; no fixture or hardware promotion"}
    events_path = root/"host"/"tool-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    result["costs"] = {"tool_calls": len(events), "acquisition_read_bytes": sum(e["output"].get("read_bytes", 0) for e in events), "rejected_actions": sum(e["output"].get("status") == "REJECTED" for e in events), "preflight_calls": sum(e["input"].get("action") == "preflight" for e in events), "tool_wall_s": sum(e["wall_s"] for e in events), "provider_usage": "S0_SHARED_LEDGER_REQUIRED", "independent_final_evaluation_cost": "S0_EXACT_INPUT_EXECUTOR_LEDGER_REQUIRED"}
    result["real_typed_consumer"] = bool(sub and sub["consumer"]["used_observation"])
    result["interface_decision_success"] = bool(result["real_typed_consumer"] and result["prediction_correct"] and result["decision_correct"] and result["selected_service"] == "PASS")
    write_once(root/"host"/"independent-result.json", result)
    return result
