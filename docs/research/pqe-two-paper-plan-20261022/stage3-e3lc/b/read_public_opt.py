"""Read the frozen OPT public outputs only; never invoke the optimizer."""
from pathlib import Path
import hashlib
import json

BDIR = Path(__file__).resolve().parent
S0 = BDIR.parent / "s0"
OMIT = {"trace", "activity", "records", "packets", "receiver_records"}


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def compact(r):
    fields = ("execution_status", "task_id", "task_sha256", "input_sha256", "result_sha256", "design", "problem", "model_valid", "domain_errors", "public_check", "usage")
    return {**{k:r.get(k) for k in fields}, "facts":{k:v for k,v in r.get("facts", {}).items() if k not in OMIT}}


def main():
    source = S0 / "opt-result.json"
    data, digest = read(source)
    bindings = []
    documents = []
    for path in sorted((S0 / "opt").glob("*/*/public-compact.json")):
        doc, sha = read(path)
        bindings.append({"path": str(path), "sha256": sha})
        documents.append(compact(doc))
    runs = []
    evaluation_count = new_inputs = cache = 0
    for run in data["runs"]:
        evaluations = []
        for e in run["evaluations"]:
            r = compact(e["public_result"])
            matches = [d for d in documents if d["input_sha256"] == r["input_sha256"] and d["result_sha256"] == r["result_sha256"]]
            if not matches or any(any(d[k] != r[k] for k in ("design", "problem", "execution_status", "model_valid", "public_check")) for d in matches):
                raise ValueError("OPT_COMPACT_BINDING_MISMATCH")
            evaluation_count += 1
            new_inputs += r["usage"].get("numerical_inputs", 0)
            cache += bool(r["usage"].get("reused"))
            evaluations.append({**{k:v for k,v in e.items() if k != "public_result"}, "public_result": r})
        runs.append({**{k:v for k,v in run.items() if k != "evaluations"}, "evaluations": evaluations})
    if evaluation_count != data["actual_evaluations"] or new_inputs != data["attempted_new_scientific_inputs"] or cache != data["exact_result_reuses"]:
        raise ValueError("OPT_COST_ACCOUNTING_MISMATCH")
    for key in ("protocol", "optimizer"):
        ref = data[key]
        if hashlib.sha256(Path(ref["path"]).read_bytes()).hexdigest() != ref["sha256"]:
            raise ValueError("FROZEN_OPT_SOURCE_CHANGED")
    result = {**{k:v for k,v in data.items() if k != "runs"}, "runs": runs,
              "source_result": {"path": str(source), "sha256": digest}, "source_public_compacts": bindings,
              "read_boundary": "Authorized opt-result and opt/*/*/public-compact only. No raw/assessment/private sources, runtime imports or execution."}
    dest = BDIR / "OPT-READBACK.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"evaluations": evaluation_count, "new_scientific_inputs": new_inputs, "exact_reuses": cache,
                      "compact_files": len(bindings), "starts": [{k:r.get(k) for k in ("start_id", "stop", "best_public_score")} for r in runs],
                      "readback_sha256": hashlib.sha256(dest.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
