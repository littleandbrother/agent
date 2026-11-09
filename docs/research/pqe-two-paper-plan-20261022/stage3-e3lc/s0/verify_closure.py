"""Read-only binding/accounting check. Does not import or execute research code."""
from pathlib import Path
from decimal import Decimal
import hashlib
import json
import sqlite3
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    manifest = load(HERE / "verification.json")
    for item in manifest["bindings"]:
        path = Path(item["path"])
        assert path.stat().st_size == item["bytes"], str(path)
        assert sha(path) == item["sha256"], str(path)
    batch = load(HERE / "batch-result.json")
    episodes = load(HERE / "door-batch-result.json")["episodes"]
    episodes += load(HERE / "lc-batch-result.json")["episodes"]
    assert len(episodes) == 9
    assert all(e["status"] == "COMPLETED_FINITE_ATTEMPT" for e in episodes)
    assert all(not e["error"] and not e["fatal"] for e in episodes)
    assert batch["counts"]["new_scientific_inputs"] == 30
    assert batch["counts"]["exact_result_reuses"] == 2
    owners = [e["owner"] for e in episodes]
    assert len(set(owners)) == 9
    db = Path(manifest["accounting_database"])
    con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        marks = ",".join("?" for _ in owners)
        rows = [dict(r) for r in con.execute(
            f"SELECT * FROM model_requests WHERE owner IN ({marks})", owners)]
        assert len(rows) == 46
        assert all(r["status"] == "SETTLED" and r["usage"] for r in rows)
        assert abs(sum(Decimal(str(r["charged"])) for r in rows)
                   - Decimal("0.6355623")) < Decimal("0.000000001")
        usage = [json.loads(r["usage"]) for r in rows]
        for key, total in batch["accounting"]["usage"].items():
            assert sum(u.get(key, 0) or 0 for u in usage) == total
        for table in ("principals", "grants"):
            extra = " AND expires>?" if table == "grants" else ""
            params = owners + ([time.time()] if extra else [])
            assert con.execute(f"SELECT count(*) FROM {table} WHERE owner IN ({marks})"
                               + extra, params).fetchone()[0] == 0
        study = dict(con.execute("SELECT * FROM research_model_studies WHERE protocol=?",
                                 (batch["package"],)).fetchone())
        assert study["expires"] < time.time()
        assert con.execute("SELECT value FROM settings WHERE key='model_budget_scope'").fetchone() is None
        r11 = dict(con.execute("SELECT * FROM model_requests WHERE id=?",
                               ("llm-1de4d60d9bc93d257392",)).fetchone())
        assert hashlib.sha256(json.dumps(r11, sort_keys=True).encode()).hexdigest() == manifest["r11_full_row_sha256"]
        assert r11["status"] == "UNKNOWN" and r11["usage"] is None
    finally:
        con.close()
    assert not (HERE / "active.lock").exists()
    state = load(HERE.parents[1] / "execution-state.json")
    assert state["package"] == batch["package"]
    assert state["status"] == batch["status"]
    assert state["full_project_complete"] is False
    assert state["automation_status"] == "PAUSED unchanged"
    root_feature = load(ROOT / "feature_list.json")["bf_pqe_stage3_e3lc_20261023"]
    assert root_feature["status"] == "complete"
    feature = load(root_feature["feature"])
    assert feature["status"] == "complete"
    assert feature["root_init_run"] is False
    postflight = load(HERE / "postflight.json")
    assert postflight["retained_output_bytes"] < postflight["retained_output_cap_bytes"]
    assert postflight["research_active_reclaimed_bytes"] == 0
    print(json.dumps({"status": "PASS_SAVED_BINDINGS_AND_ACCOUNTING_ONLY",
                      "bindings": len(manifest["bindings"]), "episodes": len(episodes),
                      "settled_requests": len(rows), "new_model_or_science_calls": 0,
                      "full_init": False}, sort_keys=True))


if __name__ == "__main__":
    main()
