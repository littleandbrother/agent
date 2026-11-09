"""Read-only post-run accounting, bindings and actual callback-wire audit."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

S0 = Path(__file__).resolve().parent
ROOT = S0.parents[4]
APP = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
sys.path.insert(0, str(APP / "packages/python/bfworld/src"))
from bfworld.agentlab.pqe20261022 import pilot
from bfworld.agentlab.pqe20261022.executor import identity


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit():
    pre = read(S0 / "preflight.json")
    before = read(S0 / "runtime-before.json")
    batch = read(S0 / "batch-result.json")
    protocol = read(APP / "studies/pqe20261022/shared/m3-protocol.json")
    db = sqlite3.connect(f"file:{pilot.DATABASE}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    old = dict(db.execute("SELECT * FROM model_requests WHERE id=?",
                          (before["original_r11_request"],)).fetchone())
    old_hash = hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    result = {
        "at": datetime.now(timezone.utc).isoformat(), "episodes": [], "wires": [],
        "original_r11_row_sha256": old_hash,
        "original_r11_row_unchanged": old_hash == before["original_r11_row_sha256"],
        "protected_nine_sources_unchanged": all(sha(p) == h for p, h in pre["protected_source_sha256"].items()),
        "new_bindings_unchanged": all(sha(p) == h for p, h in protocol["new_source_bindings"].items()),
        "old_task_identities_unchanged": True,
    }
    catalog = read(APP / "studies/pqe20261022/shared/door-tasks.json")
    result["old_task_identities_unchanged"] = all(identity(catalog[k]) == h for k, h in pre["old_task_identities"].items())
    for episode in batch["episodes"]:
        if "owner" not in episode:
            result["episodes"].append(episode)
            continue
        owner = episode["owner"]
        folder = S0 / "episodes" / episode["episode"]
        costs = read(folder / "provider-costs.json")
        rows = list(db.execute("SELECT * FROM model_requests WHERE owner=?", (owner,)))
        usage = [json.loads(row["usage"]) for row in rows if row["usage"]]
        result["episodes"].append({
            "episode": episode["episode"], "owner": owner,
            "status": episode["status"], "error": episode["error"], "fatal": episode["fatal"],
            "request_ids": [row["id"] for row in rows],
            "requests": len(rows), "all_settled": all(row["status"] == "SETTLED" and row["usage"] for row in rows),
            "input_tokens": sum(x["prompt_tokens"] for x in usage),
            "output_tokens": sum(x["completion_tokens"] for x in usage),
            "cache_aware_rate_estimate_usd": costs["cache_aware_rate_estimate_usd"],
            "unknown_or_missing_usage": costs["unknown_or_missing_usage"],
            "unsettled_reserved_usd": costs["unsettled_reserved_usd"],
            "principals_remaining": db.execute("SELECT count(*) FROM principals WHERE owner=?", (owner,)).fetchone()[0],
            "active_grants_remaining": db.execute("SELECT count(*) FROM grants WHERE owner=? AND expires>?", (owner, time.time())).fetchone()[0],
        })
        for callback in sorted((folder / "callbacks").glob("*")):
            if not (callback / "wire-public.json").exists():
                result["wires"].append({"episode": episode["episode"], "callback": callback.name, "status": "NO_WIRE_SAVED"})
                continue
            wire = read(callback / "wire-public.json")
            public = read(callback / "input-public.json")
            system = [m["content"] for m in wire["messages"] if m["role"] == "system"]
            users = [m["content"] for m in wire["messages"] if m["role"] == "user"]
            content = users[0] if len(users) == 1 else None
            text = content if isinstance(content, str) else "".join(x["text"] for x in content or [] if x["type"] == "text")
            expected_system = public["instruction"] + "\n\n<cwd>\n" + str(callback / "participant") + "\n</cwd>"
            result["wires"].append({
                "episode": episode["episode"], "callback": callback.name,
                "user_equals_saved_public_request": len(users) == 1 and json.loads(text) == public["request"],
                "system_only_instruction_and_participant_cwd": system == [expected_system],
                "actual_max_tokens": wire["max_tokens"], "granted_max_tokens": public["max_output_tokens"],
                "input_sha256": sha(callback / "input-public.json"), "wire_sha256": sha(callback / "wire-public.json"),
            })
    scope = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
    result["budget_scope_restored"] = (scope["value"] if scope else None) == before["model_budget_scope_before"]
    result["study_expired"] = not db.execute("SELECT 1 FROM research_model_studies WHERE protocol=? AND expires>?", (batch["package"], time.time())).fetchone()
    result["active_lock_removed"] = not (S0 / "active.lock").exists()
    result["actual_new_coupled_including_initial"] = batch["actual_new_numerical_inputs"] + batch["shared_initial_numerical_inputs"]
    return result


if __name__ == "__main__":
    out = S0 / "accounting-wire-review.json"
    if out.exists():
        raise SystemExit("Post-run audit already recorded; do not repeat without a new concern")
    value = audit()
    out.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(value, ensure_ascii=False))
