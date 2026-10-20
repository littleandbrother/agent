"""Finite BF transfer adapter; frozen earlier science is imported, never edited.

The actual episode runner owns identity, usage and executor admission. Engines
produce a complete digital response and a separately computed service decision.
The host exposes public facts, and keeps the final decision in sealed records.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import zlib

from .phase1 import digest, encoded, file_hash, seal


def load(path):
    return json.loads(Path(path).read_text())


def bindings_match(bindings):
    for path, expected in bindings.items():
        if file_hash(path) != expected:
            raise ValueError("FROZEN_SOURCE_CHANGED:" + str(path))


def require_final_freeze(spec, selection, selected_methods):
    if spec.get("stage") != "final":
        return
    if not selection or selection.get("status") != "ALL_SIX_ARMS_FROZEN":
        raise ValueError("FINAL_INPUT_NOT_ADMITTED_BEFORE_ALL_SELECTIONS")
    if selection.get("selected_methods_sha256") != digest(selected_methods):
        raise ValueError("FROZEN_SELECTION_CHANGED")
    if len(selected_methods) != 6:
        raise ValueError("SIX_COMPLETE_LINEAGE_ARM_SELECTIONS_REQUIRED")


def executor_admission(slots, now):
    if now - slots.get("observed_unix", 0) > 3600:
        raise ValueError("EXECUTOR_STATUS_STALE")
    if slots.get("status") != "OBSERVED":
        raise ValueError("EXECUTOR_LEASE_CLOSED")
    statuses = [slots.get(name) for name in ("A", "B")]
    if any(x not in ("idle", "running") for x in statuses):
        raise ValueError("EXECUTOR_STATUS_UNKNOWN")
    if statuses.count("running") > 1:
        raise ValueError("PI_WOULD_EXCEED_THREE_EXECUTORS")
    return ["S0", "Pi"] + [name for name in ("A", "B") if slots[name] == "running"]


def used_totals(records):
    rows = list(records)
    if any(row["accounting"]["unknown_or_missing_usage"] for row in rows):
        raise ValueError("UNRESOLVED_USAGE")
    return {
        "requests": sum(row["accounting"]["requests"] for row in rows),
        "wall_s": sum(row["wall_seconds_total"] for row in rows),
        "settled_upper_usd": sum(row["accounting"]["settled_charge_upper_bound_usd"] for row in rows),
    }


def bounded_allowance(spec, records, formation=None):
    """Parent and all descendant work share an arm budget; no free formation."""
    req = 8 if spec["kind"] in ("G", "H") else 24 if spec["stage"] == "O-transfer" else 12
    wall = 400 if spec["kind"] in ("G", "H") else 1200 if spec["stage"] == "O-transfer" else 800
    related = [x for x in records if spec.get("arm_id") and x["spec"].get("arm_id") == spec["arm_id"]]
    total = used_totals(related)
    allocated = formation or {"requests": 0, "wall_s": 0, "settled_upper_usd": 0}
    if spec.get("arm_id"):
        req = min(req, 120 - total["requests"] - allocated["requests"])
        wall = min(wall, 6600 - total["wall_s"] - allocated["wall_s"])
        if total["settled_upper_usd"] + allocated["settled_upper_usd"] >= 10:
            raise ValueError("LINEAGE_ARM_DOLLAR_CAP")
    if req < 1 or wall <= 0:
        raise ValueError("LINEAGE_ARM_BUDGET_EXHAUSTED")
    return req, wall


def public_projection(value):
    """Fixed mechanical response bound; full source-bound raw data stay sealed.

    Every long array has the same rule, independent of arm, outcome or task.
    The projection exposes no reference truth, service label or design advice.
    """
    if isinstance(value, dict):
        return {k: public_projection(v) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > 12:
            return {"projection": "first-six-last-six", "full_count": len(value),
                    "full_value_sha256": digest(value),
                    "first_six": [public_projection(v) for v in value[:6]],
                    "last_six": [public_projection(v) for v in value[-6:]]}
        return [public_projection(v) for v in value]
    return value


class ResponseStore:
    """Read-only starting cache, isolated logical D history, one physical writer."""

    def __init__(self, output, initial, group, engine, *, maximum=150):
        self.output, self.initial = Path(output), Path(initial)
        self.initial_sha = file_hash(self.initial)
        self.engine, self.maximum = engine, maximum
        self.root = self.output / "physical-cache"
        self.root.mkdir(parents=True, exist_ok=True)
        index = self.root / "index.json"
        if not index.exists():
            index.write_bytes(self.initial.read_bytes())
        self.index = load(index)
        self.initial_keys = set(load(self.initial))
        self.job = self.output / "groups" / group / "job-overlay.json"
        self.job.parent.mkdir(parents=True, exist_ok=True)
        if not self.job.exists():
            seal(self.job, {"initial_cache_sha256": self.initial_sha, "executed": {}})

    def task(self, world):
        return self.engine.task(world)

    def normalize(self, world, candidate):
        return self.engine.normalize(world, candidate)

    def sources(self, world):
        return self.engine.sources(world)

    def key(self, world, candidate):
        return self.engine.key(world, candidate)

    def execute(self, world, candidate):
        candidate = self.normalize(world, candidate)
        job = load(self.job)
        if job["initial_cache_sha256"] != self.initial_sha:
            raise ValueError("INITIAL_CACHE_CHANGED")
        marker = digest({"world": world, "candidate": candidate})
        if marker not in job["executed"] and len(job["executed"]) >= 2:
            raise ValueError("TWO_DISTINCT_DESIGNS_PER_EPISODE")
        self.engine.check_sources()
        key = self.key(world, candidate)
        if key in self.index:
            entry = self.index[key]
            if entry.get("status") == "STARTED":
                raise ValueError("INCOMPLETE_SCIENTIFIC_EXECUTION_NO_RETRY")
            bindings_match(entry["artifacts"])
            if file_hash(entry["result_path"]) != entry["result_sha256"]:
                raise ValueError("CACHED_RESULT_TAMPERED")
            original = load(entry["result_path"])
            raw = self.engine.raw(world, original)
            # Re-evaluation changes no original bytes and is not a new simulation.
            assessed = self.engine.assess(world, candidate, raw)
            result = {**original, **assessed, "world": world, "design": candidate, "reused": True}
        else:
            if sum(x["origin"] == "phase4-new-full-response" for x in self.index.values()) >= self.maximum:
                raise ValueError("PHASE4_SCIENTIFIC_EXECUTION_CAP")
            self.index[key] = {"origin": "phase4-new-full-response", "status": "STARTED"}
            (self.root / "index.json").write_bytes(encoded(self.index) + b"\n")
            raw = self.engine.simulate(world, candidate)
            assessed = self.engine.assess(world, candidate, raw)
            directory = self.root / key
            directory.mkdir()
            seal(directory / "input.json", self.engine.execution_input(world, candidate))
            (directory / "response.json.zlib").write_bytes(zlib.compress(encoded(raw)))
            result = {**assessed, "execution_key": key, "world": world, "design": candidate,
                      "input_sha256": digest(self.engine.execution_input(world, candidate)),
                      "origin": "phase4-new-full-response", "physical_qualification": "UNKNOWN",
                      "raw_path": str(directory / "response.json.zlib")}
            seal(directory / "result.json", result)
            self.index[key] = {"origin": result["origin"], "result_path": str(directory / "result.json"),
                               "result_sha256": file_hash(directory / "result.json"),
                               "input_sha256": result["input_sha256"],
                               "artifacts": {str(q): file_hash(q) for q in directory.iterdir() if q.is_file()}}
            (self.root / "index.json").write_bytes(encoded(self.index) + b"\n")
            result["reused"] = False
        result["job_accounting"] = {"initial_cache_sha256": self.initial_sha,
                                    "initial_cache_hit": key in self.initial_keys,
                                    "new_logical_D_exposure": marker not in job["executed"],
                                    "other_group_history_exposed": False}
        if marker not in job["executed"]:
            job["executed"][marker] = {"candidate": candidate, "execution_key": key,
                                      "result_sha256": digest(result)}
            self.job.write_bytes(encoded(job) + b"\n")
        return result, self.engine.public_response(world, candidate, raw, result)


class ProposalHost:
    """Only model-authored G/H proposals, with one valid distinct proposal."""

    def __init__(self, root, kind, packet, schema, normalize):
        self.root, self.kind = Path(root), kind
        self.root.mkdir(parents=True, exist_ok=True)
        self.packet, self.schema, self.normalize = packet, schema, normalize
        self.valid = set()
        self.syntax_rejections = 0

    def __call__(self, body):
        action = body["action"]
        if action == "inspect":
            seal_path = self.root / "information-packet.json"
            if not seal_path.exists():
                seal(seal_path, self.packet)
            return {"artifact": self.kind, "facts": self.packet, "proposal_schema": self.schema}
        if action == "acquire":
            source = body["source_id"]
            if source not in self.packet:
                raise ValueError("UNKNOWN_PUBLIC_SOURCE")
            value = {"source_id": source, "payload": self.packet[source],
                     "source_sha256": digest(self.packet[source])}
            target = self.root / "acquisitions" / (source + ".json")
            if not target.exists():
                seal(target, value)
            return value
        if action not in ("propose", "submit"):
            raise ValueError("NO_DESIGN_ACTION_IN_G_OR_H_EPISODE")
        proposed = self.normalize(body["proposal"])
        key = digest(proposed)
        if key not in self.valid and self.valid:
            raise ValueError("ONE_VALID_PROPOSAL_CAP")
        self.valid.add(key)
        if action == "submit":
            seal(self.root / "submission.json", {"proposal": proposed, "raw_proposal": body["proposal"]})
        return {"recorded": action, "proposal_sha256": key, "decision": proposed.get("decision", "propose")}


class DesignHost:
    def __init__(self, root, store, world):
        self.root, self.store, self.world = Path(root), store, world
        self.root.mkdir(parents=True, exist_ok=True)
        self.kind, self.candidates = "D", set()

    def __call__(self, body):
        action = body["action"]
        if action == "inspect":
            packet = self.store.engine.inspect(self.world)
            target = self.root / "information-packet.json"
            if not target.exists():
                seal(target, packet)
            return packet
        if action == "acquire":
            sources = self.store.sources(self.world)
            name = body["source_id"]
            if name not in sources:
                raise ValueError("SOURCE_NOT_REGISTERED")
            payload = sources[name]
            item = {"source_id": name, "payload": payload, "source_sha256": digest(payload)}
            target = self.root / "acquisitions" / (name + ".json")
            if not target.exists():
                seal(target, item)
            return item
        if action not in ("check", "submit"):
            raise ValueError("NO_G_OR_H_PROPOSAL_IN_DESIGN_EPISODE")
        candidate = self.store.normalize(self.world, body["candidate"])
        result, public = self.store.execute(self.world, candidate)
        self.candidates.add(digest(candidate))
        if action == "submit":
            judgment = body["service_judgment"]
            if judgment not in ("PASS", "FAIL", "UNKNOWN"):
                raise ValueError("SERVICE_JUDGMENT_REQUIRED")
            seal(self.root / "submission.json", {"candidate": candidate, "execution": result,
                 "service_judgment": judgment, "reason": body.get("reason", ""),
                 "wrong_service_judgment": judgment != result["complete_service"]})
        return {"recorded": action, "selected_design": candidate, "observed": public_projection(public),
                "physical_qualification": "UNKNOWN"}


class DigitalOEngine:
    """Original O event service on B's independently tested AR-based apparatus."""

    def __init__(self, tasks, interface, *, fixed_candidate=None):
        self.tasks, self.interface = tasks, interface
        self.fixed_candidate = copy.deepcopy(fixed_candidate)
        self.bound = {str(Path(interface.__file__)): file_hash(interface.__file__),
                      str(Path(interface.ar.__file__)): file_hash(interface.ar.__file__)}

    def check_sources(self):
        bindings_match(self.bound)
        bindings_match({s["input_path"]: s["input_sha256"] for s in self.tasks.values()})

    def task(self, world):
        spec = self.tasks[world]
        bindings_match({spec["input_path"]: spec["input_sha256"]})
        case = load(spec["input_path"])
        self.interface.validate_case(case)
        return case

    def normalize(self, world, candidate):
        self.interface.validate_candidate(self.task(world), candidate)
        if self.fixed_candidate is not None and candidate != self.fixed_candidate:
            raise ValueError("FROZEN_CONTROL_CANDIDATE_REQUIRED")
        return copy.deepcopy(candidate)

    def execution_input(self, world, candidate):
        return {"case": self.task(world), "candidate": self.normalize(world, candidate)}

    def key(self, world, candidate):
        return digest({"O_full_input": self.execution_input(world, candidate),
                       "producer_and_evaluator": self.bound,
                       "adapter_sha256": file_hash(Path(__file__))})

    def sources(self, world):
        case = self.task(world)
        view = self.interface.public_view(case)
        return {s["source_id"]: self.interface.public_view(case, source=s["source_id"])
                for s in view["sources"]}

    def inspect(self, world):
        view = self.interface.public_view(self.task(world))
        if self.fixed_candidate is not None:
            view["frozen_control_candidate"] = copy.deepcopy(self.fixed_candidate)
            view["candidate_schema"] = {"type": "object", "additionalProperties": False,
                "required": list(self.fixed_candidate), "properties": {
                    k: {"const": v} for k, v in self.fixed_candidate.items()}}
        view["source_ids"] = [x["source_id"] for x in view["sources"]]
        view["response_projection"] = "Arrays over 12 retain count, full canonical SHA, first six and last six. Complete raw response is host-sealed."
        return view

    def simulate(self, world, candidate):
        return self.interface.evaluate_candidate(self.task(world), self.normalize(world, candidate))

    def raw(self, world, original):
        return json.loads(zlib.decompress(Path(original["raw_path"]).read_bytes()))

    def assess(self, world, candidate, raw):
        if raw["candidate"] != self.normalize(world, candidate):
            raise ValueError("O_RESPONSE_CANDIDATE_CHANGED")
        result = self.interface.evaluate_service(self.task(world), raw)
        return {**result, "evaluator_version": "phase4-original-O-event-service-v1",
                "evaluator_sha256": file_hash(self.interface.__file__)}

    def public_response(self, world, candidate, raw, result):
        return self.interface.public_view(self.task(world), response=raw)["response"]


class DigitalBEngine:
    """Old transient model and receiver, with explicit new frozen task inputs."""

    def __init__(self, app, historical, tasks, checker):
        self.app, self.historical = Path(app), Path(historical)
        self.tasks, self.checker = tasks, checker
        old = load(self.app / "configs/studies/phase2-20261020/shared/case-registry.json")
        self.scientific_files = old["frozen_scientific_files"]
        self.bound = {str(self.app / q): sha for q, sha in self.scientific_files.items()}

    def check_sources(self):
        bindings_match(self.bound)
        for spec in self.tasks.values():
            if file_hash(spec["input_path"]) != spec["input_sha256"]:
                raise ValueError("FROZEN_TRANSFER_INPUT_CHANGED")

    def task(self, world):
        spec = self.tasks[world]
        if file_hash(spec["input_path"]) != spec["input_sha256"]:
            raise ValueError("FROZEN_TRANSFER_INPUT_CHANGED")
        return load(spec["input_path"])

    def normalize(self, world, candidate):
        from .phase3 import checked_design
        return checked_design(candidate, self.tasks[world]["legal_design_ranges"])

    def execution_input(self, world, candidate):
        task = self.task(world)
        task["device"].update(self.normalize(world, candidate))
        return task

    def key(self, world, candidate):
        return digest({"task": self.execution_input(world, candidate), "model": self.scientific_files,
                       "checker_sha256": file_hash(self.app / "scripts/campaign_reference.py")})

    def sources(self, world):
        task = self.task(world)
        model = self.app / "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/b.py"
        return {"component_record": task["device"],
                "excitation_record": {k: v for k, v in task.items() if k != "device"},
                "model_law": {"model_id": task["model_id"], "python_definition": model.read_text()}}

    def inspect(self, world):
        task = self.task(world)
        return {"world": world, "scope": "Frozen digital transient BF apparatus; physical qualification UNKNOWN",
                "task": task, "query_protocol": self.tasks[world].get("query_protocol"),
                "current_design": {k: task["device"][k] for k in self.tasks[world]["legal_design_ranges"]},
                "candidate_schema": self.tasks[world]["candidate_schema"],
                "sources": self.sources(world), "source_ids": list(self.sources(world)),
                "complete_service_requirements": ["independent energy", "one valid source event frame",
                    "causal event capture", "deadline", "deduplication", "voltage feasibility",
                    "registered single-query gates when present"]}

    def simulate(self, world, candidate):
        from .b import simulate_b
        return simulate_b(self.execution_input(world, candidate))

    def raw(self, world, original):
        if original.get("raw_path"):
            return json.loads(zlib.decompress(Path(original["raw_path"]).read_bytes()))
        return load(self.historical / "cases" / original["world"] / "observations.json")

    def assess(self, world, candidate, raw):
        from .phase3 import ordered_state
        task = self.execution_input(world, candidate)
        energy = self.checker.energy_reference(task, raw["trace"], "b")
        reference = self.checker.reference_b(task, raw, energy)
        passed = all(reference["verdicts"][k] == "PASS" for k in
                     ("independent_energy", "independent_receiver", "event_receive", "deduplication", "transient_voltage"))
        query = None
        rule = self.tasks[world].get("query_protocol")
        if rule:
            decoded = [(p, self.checker.decode(p["hex"], "b")) for p in raw["packets"]]
            matches = [p for p, d in decoded if d and d["seq"] == rule["nonce_sequence"]
                       and d["event"] == 1 and d["key"] == 1 and d["id"] == task["device"]["id"]]
            issued, deadline = rule["issued_s"], rule["deadline_s"]
            gates = {"single_query_token": len(matches) == 1,
                     "query_before_reply": bool(matches) and all(issued <= p["time_s"] <= deadline for p in matches),
                     "freshness": bool(matches) and all(0 <= p["time_s"] - issued <= rule["max_data_age_s"] for p in matches),
                     "query_state_capture": any(x["action"] == "capture" and issued <= x["time_s"] <= deadline for x in raw["activity"])}
            query = {"gates": gates, "protocol": rule, "status": "PASS" if all(gates.values()) else "FAIL"}
            passed = passed and all(gates.values())
        return {"complete_service": "PASS" if passed else "FAIL", "energy": energy, "reference": reference,
                "ordered_event_state": ordered_state(task, raw, reference), "query_service": query,
                "evaluator_version": "phase4-fixed-transient-and-single-query-v1",
                "evaluator_sha256": file_hash(Path(__file__))}

    def public_response(self, world, candidate, raw, result):
        return {"energy_ledger": result["energy"], "activity": raw["activity"], "packets": raw["packets"],
                "first_boot_s": result["reference"]["first_boot_s"],
                "first_receive_s": result["reference"]["first_receive_s"],
                "received_frames": result["reference"]["received_frames"]}
