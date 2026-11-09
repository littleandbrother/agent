"""Execute the already frozen public comparator once with the existing consumer."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import e3lc as m, pilot as p, adapter
from bfworld.agentlab.pqe20261022.executor import identity
from bfworld.agentlab.pqe20261022.methods import common_contract_check
from bfworld.agentlab.pqe20261022.public_projection import project_result, scientific_source_identity

protocol_path = m.OUT / "b/OPT-PROTOCOL.json"
source_path = APP / "scripts/pqe_e3lc_opt.py"
assert m.sha(protocol_path) == "05a23866ac9532fb35cdb5a4e5293a44501ca6788f1deb6112385e46e85d87f9"
assert m.sha(source_path) == "371a98fcb647feccb2b2ed7d1eb3fb75db2a05888419fcb986d7ecd19c1ffe36"
assert not (m.OUT / "s0/active.lock").exists(), "WAIT_FOR_SERIAL_EPISODE_EXECUTOR"
protocol, original = m.read(protocol_path), m.read(m.PROTOCOL)
m.configure(original)
task, initial, registry = m.door_inputs(original)
assert task is not None, "NO_QUALIFIED_COMPARABLE_TASK"
public_path = ROOT / protocol["task_public"]["path"]
assert m.sha(public_path) == protocol["task_public"]["sha256"]
public = m.read(public_path)
assert identity(public["Task"]) == identity(task)
assert public["Design"] == task["initial_design"]
with (m.OUT / "s0/opt-run-claim.json").open("x") as stream:
    json.dump({"at": m.now(), "protocol": m.binding(protocol_path), "optimizer": m.binding(source_path),
               "runner": m.binding(__file__), "same_scientific_source": original["scientific_source"]}, stream)
spec = importlib.util.spec_from_file_location("pqe_frozen_opt", source_path)
optimizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(optimizer)
row = registry["roles"]["scope"]
cache = {p.execution_cache_key(task, initial["design"], task["integration"]["dt_s"], initial["sources"]):
         Path(row["initial_public_result_path"]).parent}
for path in sorted((m.OUT / "s0/episodes").glob("scope-*/actions/*/public-result.json")):
    result = m.read(path)
    if (result.get("execution_status") == "COMPLETE" and result.get("task_sha256") == identity(task)
            and scientific_source_identity(result["sources"]) == original["scientific_source"]):
        key = p.execution_cache_key(task, result["design"], task["integration"]["dt_s"], result["sources"])
        decision_path = path.parent / "decision.json"
        if decision_path.exists():
            actual_dt = m.read(decision_path)["decision"]["actual_input"].get("dt_s", task["integration"]["dt_s"])
            if actual_dt != task["integration"]["dt_s"]:
                continue
        elif (path.parent / "reused.json").exists():
            if m.read(path.parent / "reused.json")["exact_key"] != key:
                continue
        else:
            continue
        cache.setdefault(key, path.parent)
calls, new, reused = [], 0, 0


def consume(design, problem, *, start_id, evaluation_index):
    global new, reused
    if len(calls) >= 12 or p.output_bytes(m.OUT) >= 250000000:
        raise ValueError("OPT_SHARED_RESOURCE_CAP")
    output = m.OUT / "s0/opt" / start_id / f"{evaluation_index:02d}"
    actual = common_contract_check({"task": task, "design": task["initial_design"],
        "problem": task["initial_problem"]}, {"operation": "edit", "design_patch": design,
        "problem_patch": problem}, {"remaining_actions": 12-len(calls)})
    adapter.validate_design(task, design)
    key = p.execution_cache_key(task, design, task["integration"]["dt_s"], initial["sources"])
    if key in cache:
        result = project_result(m.read(cache[key] / "public-result.json"))
        assert result["design"] == design and result["task_sha256"] == identity(task)
        result["problem"] = deepcopy(problem)
        result["usage"] = {"numerical_inputs": 0, "paid_model_requests": 0, "reused": True, "wall_s": 0}
        p.save(output / "reused.json", {"source": str(cache[key]), "exact_key": key, "actual_input": actual})
        p.save(output / "public-result.json", result)
        reused += 1
    else:
        new += 1
        result = adapter.execute(task, task["initial_design"], task["initial_problem"],
            {"actual_input": actual}, output, task_resolver=m.resolve(original))
        cache[key] = output
    compact = p.compact_result(result)
    p.save(output / "public-compact.json", compact)
    calls.append({"start_id": start_id, "evaluation_index": evaluation_index, "output": str(output),
        "design": design, "public_check": result["public_check"], "usage": result["usage"]})
    return compact


started = time.monotonic()
try:
    result = optimizer.run_opt(protocol, consume)
except BaseException as exc:
    p.save(m.OUT / "s0/opt-result.json", {"status": "FINITE_OPT_STOPPED", "error": type(exc).__name__+":"+str(exc),
        "calls": calls, "attempted_new_scientific_inputs": new, "exact_result_reuses": reused})
    raise
result.update(status="FINITE_OPT_COMPLETE", protocol=m.binding(protocol_path), optimizer=m.binding(source_path),
    actual_evaluations=len(calls), attempted_new_scientific_inputs=new, exact_result_reuses=reused,
    wall_s=time.monotonic()-started, actual_provider_requests=0, completed_at=m.now())
p.save(m.OUT / "s0/opt-result.json", result)
print(json.dumps({"status": result["status"], "evaluations": len(calls), "new_scientific_inputs": new,
    "exact_reuses": reused, "runs": [(r["start_id"],r["stop"],r["best_public_score"]) for r in result["runs"]]}))
