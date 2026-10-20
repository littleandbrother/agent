"""Additive A/R component-profile trials over the unchanged service apparatus.

Part selection and programs come from the BF participant. Source test points
are explicitly nominal projections, never whole-board measured guarantees.
There is no new switching, radio, PCB or hardware simulator here.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import time
import zlib

from . import ar_service as world
from .phase1 import digest, encoded, file_hash, seal

SCHEMA = "bf-abc-ar-component-design-v1"
PROFILE = "abc-ar-component-projection-v1"


def load(path):
    return json.loads(Path(path).read_text())


def checker(app):
    spec = importlib.util.spec_from_file_location("abc_ar_original_reference", Path(app)/"scripts/campaign_ar_service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def materialize(frozen, candidate, catalogue):
    """Only a closed source-derived profile; arbitrary power scalars forbidden."""
    keys = {"schema_version", "concept_id", "storage", "controller", "sensor", "power_management", "device", "program", "rationale"}
    if set(candidate) != keys or candidate["schema_version"] != SCHEMA:
        raise ValueError("PRODUCT_CANDIDATE_KEYS")
    if not isinstance(candidate["concept_id"], str) or not 1 <= len(candidate["concept_id"]) <= 64:
        raise ValueError("PRODUCT_CONCEPT_ID")
    s, m, p, d = (candidate[k] for k in ("storage", "controller", "power_management", "device"))
    if set(s) != {"part", "modules", "connection"} or s["part"] != "GA209F" or type(s["modules"]) is not int or s["modules"] not in (1, 2):
        raise ValueError("PRODUCT_STORAGE_SOURCE")
    if s["connection"] not in ("single", "series", "parallel") or (s["connection"] == "single") != (s["modules"] == 1):
        raise ValueError("PRODUCT_STORAGE_TOPOLOGY")
    if m != {"part": "MSP430FR2433", "mode": "LPM3_XT1", "rail_v": m.get("rail_v")} or type(m.get("rail_v")) not in (int, float) or m["rail_v"] not in (2, 3):
        raise ValueError("PRODUCT_RETAINED_RTC_SOURCE_MODE")
    if p != {"part": "BQ25570", "mode": "full_operating"}:
        raise ValueError("PRODUCT_PMIC_SOURCE_MODE")
    if candidate["sensor"] != {"part": "TMP117", "mode": "one_shot_shutdown", "averaging": 1}:
        raise ValueError("PRODUCT_SENSOR_SOURCE_MODE")
    if set(d) != {"off_v", "ready_v"}:
        raise ValueError("PRODUCT_DEVICE_FIELDS")
    part = catalogue["parts"]["GA209F"]
    n = s["modules"]
    factor = n if s["connection"] == "parallel" else 1/n
    capacitance = part["capacitance_typ_f"] * factor
    esr = part["esr_typ_ohm"] / factor
    base = {"schema_version": world.CANDIDATE_SCHEMA, "device": {"capacitance_f": capacitance, **d}, "program": candidate["program"]}
    world.validate_candidate(base)
    if d["off_v"] < m["rail_v"] + 0.3 or d["ready_v"] < d["off_v"] + 0.05:
        raise ValueError("PRODUCT_CONTROLLER_RAIL_OR_HYSTERESIS")
    if candidate["program"]["rank"] != {"field": "seq"}:
        raise ValueError("ORIGINAL_STRICT_FIFO_REQUIRED")
    if not isinstance(candidate["rationale"], str) or not 20 <= len(candidate["rationale"]) <= 10000:
        raise ValueError("PRODUCT_IMPLEMENTATION_RATIONALE")
    # Fixed, visible projection of manufacturer test points. The extrapolation
    # gaps below prevent any promotion to a calibrated implementation claim.
    mcu = catalogue["parts"]["MSP430FR2433"]["lpm3_xt1_typ_a_at_25c"][str(int(m["rail_v"]))]
    efficiency = frozen["device"]["harvest_efficiency"]
    mcu_storage_w = mcu * m["rail_v"] / efficiency
    pmic_w = catalogue["parts"]["BQ25570"]["full_operating_iq_typ_a"] * 2.1
    leakage_paths = n if s["connection"] == "parallel" else 1
    cap_w = part["leakage_typ_a_at_test_point"] * leakage_paths * frozen["device"]["cap_voltage_max_v"]
    sensor_w = catalogue["parts"]["TMP117"]["shutdown_typ_a_at_25c"] * m["rail_v"] / efficiency
    losses = {"mcu_rtc_and_svs_nominal_w": mcu_storage_w, "sensor_shutdown_nominal_w": sensor_w, "pmic_test_point_projection_w": pmic_w,
              "capacitor_test_point_projection_w": cap_w}
    task = world.apply_candidate(frozen, base)
    task["device"].update(sleep_power_w=sum(losses.values()), off_power_w=pmic_w+cap_w,
                           esr_ohm=esr, cold_start_voltage_v=0.7, cold_start_power_w=15e-6)
    task["implementation_profile"] = {"id": PROFILE, "candidate_sha256": digest(candidate), "catalogue_sha256": digest(catalogue),
        "losses": losses, "basis": "Uncalibrated nominal test-point projection; original storage-side activity charges retained.",
        "source_domain_gaps": ["BQ25570 IQ is specified at VSTOR=2.1 V; projected over the storage trajectory.",
            "GA209 leakage is specified at 2.3 V, 23 C after 120 hours; fresh cold-start and voltage/temperature dependence unmeasured.",
            "Constant nominal loss and 0.8 conversion are hypotheses, not guaranteed whole-board envelopes.",
            "Original 20 ppm clock, boot, sense, FRAM-write and TX charges are retained engineering assumptions; one-shot AVG=1 is specified, but no new binary, thermal path or RF link qualification.",
            "Series modules use ideal static equivalence; balancing and mismatch not qualified."]}
    world.validate(task)
    return task


def necessary_bounds(tasks, candidate, catalogue):
    rows = {}
    for name, frozen in tasks.items():
        task = materialize(frozen, candidate, catalogue)
        d = task["device"]
        # Perfect conversion and zero leakage/activities deliberately make this
        # cold-start impossibility test stronger than the nominal simulator.
        deadline = frozen["required_first_receive_s"]
        port_j = sum(max(0, min(deadline, x["end_s"]) - x["start_s"]) * x["power_w"]
                     for x in frozen["source_segments"] if x["start_s"] < deadline)
        cold_j = 0.5*d["capacitance_f"]*d["ready_v"]**2
        dark = [x["end_s"]-x["start_s"] for x in frozen["source_segments"] if x["power_w"] == 0]
        usable_j = 0.5*d["capacitance_f"]*(d["cap_voltage_max_v"]**2-d["off_v"]**2)
        rows[name] = {"source_port_energy_before_first_receive_j": port_j, "minimum_charge_to_ready_j": cold_j,
            "cold_excluded_even_with_perfect_conversion_and_no_load": cold_j > port_j,
            "fully_charged_usable_energy_j": usable_j, "longest_dark_s": max(dark, default=0),
            "nominal_background_dark_j": max(dark, default=0)*d["sleep_power_w"],
            "nominal_dark_excluded_before_activities": max(dark, default=0)*d["sleep_power_w"] > usable_j,
            "nominal_loss_decomposition": task["implementation_profile"]["losses"],
            "scope": "Cold energy exclusion uses conservation; dark exclusion is conditional on the explicit nominal projection, not a datasheet lower bound."}
    return rows


def tool_definition(spec):
    return {"name": "abc_product", "description": "Inspect sourced component modes and original A/R service; check a whole concept, run up to three revisions of one selected concept, submit. Facts only. No hardware or hidden final acceptance.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["action"], "properties": {
            "action": {"enum": ["inspect", "check", "simulate", "submit"]}, "candidate": {"type": "object"},
            "judgment": {"enum": ["PASS", "FAIL", "UNKNOWN"]}, "explanation": {"type": "string"}}}}


def prepare_episode(spec, root):
    app, root = Path(spec["source_root"]), Path(root)
    contract = load(app/"configs/studies/phase1-20261020/ar/service-contract.v1.json")
    catalogue = load(spec["catalogue"])
    for path, sha in catalogue["bound_files"].items():
        if file_hash(path) != sha: raise ValueError("PRODUCT_SOURCE_BINDING_DRIFT")
    root.joinpath("product").mkdir(parents=True, exist_ok=True)
    seal(root/"product/input-contract.json", {"contract_sha256": file_hash(app/"configs/studies/phase1-20261020/ar/service-contract.v1.json"), "tasks": contract["tasks"], "catalogue": catalogue})
    instruction = """Choose at most two whole sourced concepts, then one for original A/R service evaluation. You decide the design; no developer-supplied winner exists. Do not enlarge the 71.5 by 40 mm source-module footprint, improve the fixed 90/20 uW input, precharge, shorten dark periods, replace A/R by piezo, or replace strict FIFO. Permitted executable component projection is GA209F (one or two modules, single/series/parallel), BQ25570 full operating, MSP430FR2433 retained LPM3_XT1 at 2 V or 3 V. Its losses are computed from visible manufacturer test points; there are explicit unmeasured voltage/temperature/conditioning and activity gaps. A model PASS cannot establish hardware validity. Other architectures, such as timer-gating or split startup storage, may be discussed as gaps but cannot be claimed executed by this retained-RTC kernel. TPL5110 oscillator accuracy is not a retained accurate RTC; main power gating needs real repeated boot costs and timing.
Candidate exact keys: schema_version='bf-abc-ar-component-design-v1', concept_id, storage={part:'GA209F',modules:1 or 2,connection:'single'/'series'/'parallel'}, controller={part:'MSP430FR2433',mode:'LPM3_XT1',rail_v:2 or 3}, sensor={part:'TMP117',mode:'one_shot_shutdown',averaging:1}, power_management={part:'BQ25570',mode:'full_operating'}, device={off_v,ready_v}, program={schema_version:'bf-ar-rank-program-v1',sample_period_s:integer1..60,ack_spacing_s:integer1..10,retry_s:integer1..3600,rank:{field:'seq'}}, rationale:string. off_v>=rail_v+0.3 and >=2.2, ready_v>=off_v+0.05 and <3.3. Capacitance/ESR/losses derive from parts; arbitrary power scalars are illegal. Retain original activity energies, uncertain time after brownout, persistence, receiver and services. Up to three immutable candidate inputs for one concept (initial plus two revisions), no hidden-result resampling. check reports necessary bounds only. simulate returns actual physical-model observations, never final independent verdict. Submit your selected candidate and PASS/FAIL/UNKNOWN with the original requirements and source gaps. It is valid to finish with a failure and next concrete missing relation. Do not choose or rewrite evaluation semantics."""
    return {"participant_input": {"common_instruction": instruction, "catalogue": catalogue, "original_tasks": contract["tasks"],
        "caps": {"concepts": 2, "selected_concept_initial_plus_revisions": 3, "native_jobs": 0}}}


class Handler:
    def __init__(self, root, spec):
        self.root, self.spec = Path(root), spec
        self.app = Path(spec["source_root"])
        self.data = load(self.root/"product/input-contract.json")
        self.selected = None
        self.concepts, self.designs = set(), set()

    def __call__(self, body):
        action = body["action"]
        if action == "inspect": return {"schema": SCHEMA, "scope": PROFILE, "data": self.data}
        candidate = body.get("candidate")
        if not isinstance(candidate, dict): raise ValueError("PRODUCT_CANDIDATE_REQUIRED")
        bounds = necessary_bounds(self.data["tasks"], candidate, self.data["catalogue"])
        concept = candidate["concept_id"]
        if concept not in self.concepts and len(self.concepts) >= 2: raise ValueError("PRODUCT_TWO_CONCEPT_CAP")
        self.concepts.add(concept)
        seal(self.root/"product/concepts"/(digest(candidate)+".json"), {"candidate": candidate, "bounds": bounds})
        if action == "check": return {"bounds": bounds, "hardware": "NOT_CALIBRATED"}
        if action == "simulate":
            if self.selected is not None and self.selected != concept: raise ValueError("ONE_SELECTED_PRODUCT_CONCEPT")
            ident = digest(candidate)
            if ident not in self.designs and len(self.designs) >= 3: raise ValueError("INITIAL_PLUS_TWO_REVISIONS_CAP")
            self.selected = concept
            self.designs.add(ident)
            result = execute(self.root, self.spec, candidate, self.data)
            return {"candidate_sha256": ident, "actual_observations": {k: v["observations"] for k, v in result.items()},
                    "new_simulations": sum(not v["reused"] for v in result.values()), "physical_qualification": "NOT_CALIBRATED"}
        if action == "submit":
            if body.get("judgment") not in ("PASS", "FAIL", "UNKNOWN"): raise ValueError("PRODUCT_JUDGMENT_REQUIRED")
            if not (self.root/"product/candidates"/(digest(candidate)+".json")).exists(): raise ValueError("PRODUCT_ACTUAL_EVALUATION_REQUIRED_BEFORE_SUBMISSION")
            seal(self.root/"product/submission.json", {"candidate": candidate, "judgment": body["judgment"], "explanation": body.get("explanation", "")})
            return {"recorded": "submit", "candidate_sha256": digest(candidate), "physical_qualification": "NOT_CALIBRATED"}
        raise ValueError("PRODUCT_ACTION")


def execute(root, spec, candidate, data):
    app = Path(spec["source_root"])
    reference = checker(app)
    rows = {}
    for name, frozen in data["tasks"].items():
        task = materialize(frozen, candidate, data["catalogue"])
        key = digest({"task": task, "producer": file_hash(world.__file__), "reference": file_hash(reference.__file__)})
        path = root/"product/executions"/key
        response = path/"response.json"
        reused = response.exists()
        if reused:
            row = load(response)
            if row["input_sha256"] != digest(task) or file_hash(path/"raw.json.zlib") != row["raw_sha256"]: raise ValueError("PRODUCT_EXACT_CACHE_DRIFT")
        else:
            if len(list((root/"product/executions").glob("*/response.json"))) >= 12: raise ValueError("PRODUCT_TWELVE_TASK_EXECUTIONS_CAP")
            path.mkdir(parents=True)
            started = time.monotonic()
            raw = world.simulate_ar(task)
            compressed = zlib.compress(encoded({"task": task, "run": raw}), 9)
            if len(compressed) > 10_000_000: raise ValueError("PRODUCT_RAW_CASE_CAP")
            (path/"raw.json.zlib").write_bytes(compressed)
            readback = json.loads(zlib.decompress((path/"raw.json.zlib").read_bytes()))
            if readback["task"] != task or digest(readback["run"]) != digest(raw): raise ValueError("PRODUCT_FULL_CONTENT_READBACK")
            raw = readback["run"]
            obs = {"first_boot_s": raw["first_boot_s"], "new_samples": sum(r["kind"] == 0 for r in raw["records"]),
                "brownouts": [a["time_s"] for a in raw["activity"] if a["action"] == "brownout"],
                "received_unique_frames": sum(r["accepted"] for r in raw["receiver"]),
                "stored_records": len(raw["final_history"])}
            row = {"case": name, "input_sha256": digest(task), "raw_sha256": file_hash(path/"raw.json.zlib"),
                   "raw_path": str(path/"raw.json.zlib"), "observations": obs, "wall_s": time.monotonic()-started,
                   "producer_model_id": world.MODEL_ID, "implementation_profile": PROFILE, "native_jobs": 0}
            seal(response, row)
        rows[name] = {**row, "reused": reused}
    seal(root/"product/candidates"/(digest(candidate)+".json"), {"candidate": candidate, "cases": {k: {a:b for a,b in v.items() if a != "reused"} for k,v in rows.items()}})
    return rows


def create_handler(root, spec):
    return Handler(root, spec)


def independent_check(root, spec):
    root = Path(root)
    subpath = root/"product/submission.json"
    if not subpath.exists(): return {"status": "NO_SUBMISSION", "physical_qualification": "NOT_CALIBRATED"}
    sub = load(subpath)
    data = load(root/"product/input-contract.json")
    frozen = load(Path(spec["source_root"])/"configs/studies/phase1-20261020/ar/service-contract.v1.json")
    if data["tasks"] != frozen["tasks"]: raise ValueError("PRODUCT_FIXED_REQUIREMENTS_DRIFT")
    reference = checker(spec["source_root"])
    manifest = load(root/"product/candidates"/(digest(sub["candidate"])+".json"))
    results = {}
    for name, base in frozen["tasks"].items():
        row = manifest["cases"][name]
        rawpath = Path(row["raw_path"])
        if file_hash(rawpath) != row["raw_sha256"]: raise ValueError("PRODUCT_RAW_DRIFT")
        raw = json.loads(zlib.decompress(rawpath.read_bytes()))
        expected = materialize(base, sub["candidate"], data["catalogue"])
        if raw["task"] != expected or digest(expected) != row["input_sha256"]: raise ValueError("PRODUCT_TASK_PROFILE_DRIFT")
        judged = reference.service_reference(expected, raw["run"])
        results[name] = reference.compact(judged)
        seal(root/"product/independent-cases"/(name+".json"), judged)
    integrity = all(r["execution_integrity"] == "PASS" for r in results.values())
    passed = integrity and all(r["all_applicable_computational_services"] == "PASS" for r in results.values())
    result = {"status": "PASS" if passed else "FAIL", "execution_integrity": "PASS" if integrity else "FAIL", "cases": results,
        "candidate_sha256": digest(sub["candidate"]), "participant_judgment": sub["judgment"],
        "wrong_service_judgment": sub["judgment"] != "UNKNOWN" and (sub["judgment"] == "PASS") != passed,
        "original_service_contract_sha256": data["contract_sha256"], "physical_qualification": "NOT_CALIBRATED",
        "engineering_acceptance": "NOT_ACCEPTED", "profile": PROFILE,
        "claim_boundary": "Full original A/R digital services evaluated on an explicit uncalibrated nominal component projection; no guaranteed current envelope, switching/RF model, PCB or hardware acceptance."}
    seal(root/"product/independent-result.json", result)
    return result
