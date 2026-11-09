"""Read only the three explicitly handed-off new LC public files."""
from pathlib import Path
import hashlib
import json

BDIR = Path(__file__).resolve().parent
EPDIR = BDIR.parent / "s0/episodes/lcpv-h0"
OMIT = {"trace", "activity", "records", "packets", "receiver_records"}


def compact(r):
    return {**{k:v for k,v in r.items() if k != "facts"}, "facts":{k:v for k,v in r.get("facts", {}).items() if k not in OMIT}}


def main():
    docs = {}
    refs = []
    for name in ("episode-result.json", "method-transcript.json", "actions/01/public-compact.json"):
        path = EPDIR / name
        raw = path.read_bytes()
        docs[name] = json.loads(raw)
        refs.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
    t = docs["method-transcript.json"]
    ep = docs["episode-result.json"]
    initial = t["initial_state"]
    calls = [{"site":r["request"]["site"], "request_sha256":r["request_sha256"],
              "state_history_count":len(r["request"]["context"].get("state", {}).get("history", [])),
              "instruction":r["request"].get("instruction"), "response":r.get("response"),
              "consumed_payload":r.get("consumed_payload")} for r in t.get("callback_records", [])]
    steps = []
    first = None
    for s in t["steps"]:
        item = {k:v for k,v in s.items() if k not in {"state_before", "state_after", "result"}}
        item["state_before"] = {k:s["state_before"].get(k) for k in ("design", "problem", "hypotheses", "invalidated")}
        r = s.get("result")
        item["result"] = compact(r) if r else None
        if r and first is None and r.get("execution_status") in {"COMPLETE", "COMPLETED", "OK", "SUCCESS"} and r.get("model_valid") is True and r.get("public_check", {}).get("verdict") == "PASS":
            calls_before = [c for c in calls if c["state_history_count"] <= len(s["state_before"].get("history", []))]
            usage = [c.get("response", {}).get("usage", {}) for c in calls_before]
            first = {"step":s["step"], "model_requests":sum(len(u.get("request_ids", [])) for u in usage),
                     "estimated_usd":sum(u["cost"] for u in usage) if all(u.get("status") == "KNOWN" for u in usage) else None}
        steps.append(item)
    result = {
        "package":"BF-PQE-S3-E3LC-20261023-001", "source_files":refs,
        "episode_result":ep, "initial_task":initial["task"],
        "initial_design":initial["design"], "initial_problem":initial["problem"],
        "initial_result":compact(initial.get("last_result", {})),
        "public_action_result":compact(docs["actions/01/public-compact.json"]),
        "steps":steps, "callback_records":calls, "first_feasible":first,
        "termination":t.get("termination"), "model_conclusion":t.get("model_conclusion"),
        "contract_corrections":t.get("contract_corrections"), "model_identity":t.get("model_identity"),
        "generated_code_loaded":t.get("generated_code_loaded"),
        "read_boundary":"Only three S0-authorized lcpv-h0 public files. No LC host/protocol/input/raw/assessment/private/A report or earlier qualification trajectory read.",
    }
    dest = BDIR / "LC-READBACK.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"episode":ep["episode"],"accounting":ep["accounting"],"last_public_service":ep["last_public_service"],
                      "first_feasible":first,"sha256":hashlib.sha256(dest.read_bytes()).hexdigest()},ensure_ascii=False))


if __name__ == "__main__":
    main()
