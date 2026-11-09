"""Read-only M3 result, source, public boundary, cost and storage readback."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import sqlite3
import time
from run_m3 import (OUT, HERE, PKG, PROTOCOL, PACKAGE, ROOT, p, read, bind,
                    validate, identity, capacity, provider_snapshot, load_task)


def run():
    protocol = read(PROTOCOL)
    validate(protocol, participant=True)
    ledger, batch = read(HERE / "resource-ledger.json"), read(HERE / "batch-result.json")
    assert batch["error"] is None, batch["error"]
    assert len(batch["tracks"]) == 2
    assert ledger["full_dynamic_inputs"] <= 10 and ledger["full_dynamic_wall_s"] <= 1200
    assert ledger["cheap_scores"] <= 60
    a = read(OUT / "a/cheap-ledger.json")
    assert ledger["A_cheap_scores"] == a["total_calls"] <= 12
    assert ledger["cheap_scores"] == ledger["A_cheap_scores"] + sum(x.get("cheap_scores", 0) for x in batch["tracks"])
    assert all(x.get("evaluations_including_reuse", 0) <= 3 and x.get("cheap_scores", 0) <= 24 for x in batch["tracks"])
    assert ledger["full_dynamic_inputs"] == sum(x["full_dynamic_inputs"] for x in ledger["attempts"])
    assert ledger["cache_reuses"] == sum(bool(x["reused"]) for x in ledger["attempts"])
    assert ledger["evaluations_including_reuse"] == len(ledger["attempts"])
    assert ledger["post_participant_result_revisions"] == ledger["native_inputs"] == ledger["hardware_runs"] == 0
    consequences = []
    for item in ledger["attempts"]:
        for field in ["public_result", "raw", "assessment"]:
            ref = item[field]
            assert bind(ref["path"])["sha256"] == ref["sha256"], field
        public, raw, assessment = [read(item[x]["path"]) for x in ["public_result", "raw", "assessment"]]
        assert identity({k: v for k, v in raw.items() if k != "result_sha256"}) == raw["result_sha256"] == public["result_sha256"]
        assert raw["model_valid"] == public["model_valid"] == item["model_valid"]
        assert assessment["verdict"] == public["public_check"]["verdict"]
        assert len(assessment["matches"]) == item["timely_matches"]
        consequences.append({"category": item["category"], "task": item["task"],
            "design": public["design"], "public_check": public["public_check"],
            "model_valid": raw["model_valid"], "timely_matches": len(assessment["matches"]),
            "missed_event_ids": assessment.get("missed_event_ids"),
            "receiver_identity": assessment.get("receiver_identity"),
            "records": raw["records"], "receiver_records": assessment["receiver_records"],
            "activity_counts": dict(Counter(x["action"] for x in raw["activity"])),
            "program_state": public["facts"]["program_state"],
            "minimum_tx_terminal_v": raw["minimum_tx_terminal_v"],
            "raw": item["raw"], "assessment": item["assessment"], "reused": item["reused"]})

    with sqlite3.connect("file:" + str(p.DATABASE) + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        owners = [row[0] for row in db.execute("SELECT owner FROM research_model_owners WHERE protocol=?", (PACKAGE,))]
        assert len(owners) <= 1
        rows, authorities = [], []
        for owner in owners:
            rows += [dict(x) for x in db.execute("SELECT * FROM model_requests WHERE owner=?", (owner,))]
            authority = {"owner": owner,
                "principals": db.execute("SELECT count(*) FROM principals WHERE owner=?", (owner,)).fetchone()[0],
                "effective_grants": db.execute("SELECT count(*) FROM grants WHERE owner=? AND expires>?", (owner, time.time())).fetchone()[0]}
            assert authority["principals"] == authority["effective_grants"] == 0
            authorities.append(authority)
        study = db.execute("SELECT expires FROM research_model_studies WHERE protocol=?", (PACKAGE,)).fetchone()
        assert not study or study[0] < time.time()
        scope = db.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone()
        scope = scope[0] if scope else None
        assert scope == read(HERE / "runtime-registration.json")["scope_before"]
    assert len(rows) <= 12
    assert all(row["status"] == "SETTLED" and row["usage"] for row in rows), "New provider usage missing; retain and stop"
    input_tokens = sum(json.loads(x["usage"])["prompt_tokens"] for x in rows)
    output_tokens = sum(json.loads(x["usage"])["completion_tokens"] for x in rows)
    charge = sum(x["charged"] for x in rows)
    assert output_tokens <= 65536 and charge <= 5
    assert provider_snapshot()["historical_unknown_sha256"] == protocol["provider_before"]["historical_unknown_sha256"]
    dispatches = [read(path) for path in (HERE / "episodes/m3-g/callbacks").glob("*/dispatch-facts.json")]
    assert sum(x["forwarded"] for x in dispatches) == len(rows)
    assert all(x.get("actual_sdk_wire_bytes", 0) <= 400000 for x in dispatches if x.get("actual_sdk_wire_bytes") is not None)

    forbidden_keys = {"truth", "private_truth", "matches", "missed_event_ids", "receiver_identity"}
    forbidden_paths = [str(OUT / "a/engineering"), str(OUT / "a/prediction-joint"), str(HERE / "engineering")]
    public_truth_label = read(protocol["common_before"]["path"])["task"]["material_sources"]["truth"]
    allowed_provenance_labels = [0]
    def public_check(value, location=""):
        if isinstance(value, dict):
            for key, item in value.items():
                path = location + "/" + key
                if key == "truth" and path.endswith("/task/material_sources/truth") and item == public_truth_label:
                    # This is the frozen public source-description string, not
                    # the independent evaluator's event array called truth.
                    allowed_provenance_labels[0] += 1
                    continue
                assert key not in forbidden_keys, "PRIVATE_ASSESSMENT_KEY_IN_PUBLIC_OBJECT:" + path
                public_check(item, path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                public_check(item, location + "/" + str(index))
        elif isinstance(value, str):
            assert not any(path in value for path in forbidden_paths), "A_PRIVATE_REFERENCE_EXPOSED"
    public_objects = 0
    for index_file in (HERE / "public-objects").glob("*/index.json"):
        index = read(index_file)
        for ref in index["objects"].values():
            value = read(ref["path"])
            public_check(value)
            public_objects += 1
    callbacks = []
    for path in sorted((HERE / "episodes/m3-g/callbacks").glob("*/input-public.json")):
        payload = read(path)
        public_check(payload)
        assert len(p.encoded(payload)) <= 240000
        callbacks.append({"callback": path.parent.name, "payload_bytes": len(p.encoded(payload)), "input": bind(path)})
    save = __import__("run_m3").save
    save(HERE / "engineering-consequence-summary.json", {"package": PACKAGE, "consequences": consequences,
        "visibility": "INDEPENDENT_REVIEW_ONLY_NEVER_PARTICIPANT_INPUT"})
    result = {"package": PACKAGE, "status": "PASS_SCOPED_READBACK", "at": __import__("run_m3").now(),
        "protocol": bind(PROTOCOL), "participant_freeze": bind(HERE / "participant-freeze.json"),
        "source_bindings_unchanged": True, "common_start": protocol["common_start"],
        "raw_assessment_public_bindings": True, "tracks": batch["tracks"], "resources": ledger,
        "accounting": {"owners": owners, "requests": len(rows), "SETTLED": len(rows),
            "new_UNKNOWN": 0, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "rate_estimate_usd": charge, "invoice_claim": False, "rows": rows,
            "authorities": authorities, "study_expired": True, "scope_restored": scope,
            "R11_original_row_unchanged": True, "provider_snapshot": provider_snapshot()},
        "public_boundary": {"checked_objects": public_objects, "private_assessment_keys": 0,
            "frozen_public_source_description_labels": allowed_provenance_labels[0],
            "A_engineering_reference_paths": 0, "callbacks": callbacks, "dispatch_facts": dispatches,
            "broker_limit_unchanged": 400000}, "storage": capacity(),
        "no_full_init_or_repository_health_claim": True,
        "claim_boundary": protocol["claim_boundary"]}
    save(HERE / "verification.json", result)
    inventory = [{**bind(path), "relative": str(path.relative_to(OUT))} for path in OUT.rglob("*")
                 if path.is_file() and path.name != "generated-file-inventory.json"]
    save(HERE / "generated-file-inventory.json", {"package": PACKAGE, "files": inventory,
        "logical_bytes": sum(x["bytes"] for x in inventory), "generated_python_caches": [x["relative"] for x in inventory if "__pycache__" in x["relative"]]})
    print(json.dumps({"status": result["status"], "new_full": ledger["full_dynamic_inputs"],
        "cheap": ledger["cheap_scores"], "SETTLED": len(rows), "rate_estimate_usd": charge,
        "retained_bytes": capacity()["retained_logical_bytes"]}, ensure_ascii=False))


if __name__ == "__main__":
    run()
