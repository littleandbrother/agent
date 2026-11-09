"""Read saved BOLD closure evidence only; never dispatch or rerun consumers."""
from pathlib import Path
import hashlib
import json


HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = Path(__file__).resolve().parents[5]
cache = {}
checked = set()


def load(path):
    return json.loads(Path(path).read_text())


def binding(ref):
    path = Path(ref["path"])
    if path not in cache:
        data = path.read_bytes()
        cache[path] = (hashlib.sha256(data).hexdigest(), len(data))
    digest, size = cache[path]
    assert digest == ref["sha256"], (str(path), "hash changed")
    if "bytes" in ref:
        assert size == ref["bytes"], (str(path), "size changed")
    checked.add(str(path))


def walk(value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            binding(value)
        for child in value.values():
            walk(child)
    elif isinstance(value, list):
        for child in value:
            walk(child)


result = load(HERE / "RESULTS.json")
verification = load(HERE / "verification.json")
ledger = load(HERE / "resource-ledger.json")
batch = load(HERE / "batch-result.json")
assert result["finite_execution_complete"] and batch["complete"]
assert result["independent_reviews"]["status"] == "COMPLETE"
walk(result["independent_reviews"])

a = load(OUT / "a/FINAL-RECEIPT.json")
b = load(OUT / "b/FINAL-RECEIPT.json")
walk(a)
walk(b)
assert a["independent_saved_trace_reviews_passed"] == 5
assert a["resources"]["audit_new_science_model_cheap"] == 0
assert b["status"] == "INDEPENDENT_PUBLIC_READBACK_PASS"
assert b["outcome"]["qualified_descendants"] == 0
for ref in b["papers"].values():
    data = Path(ref["path"]).read_bytes()
    assert hashlib.sha256(data[:ref["preserved_prefix_bytes"]]).hexdigest() == ref["preserved_prefix_sha256"]

accounting = result["accounting"]
assert ledger["full_dynamic_inputs"] == accounting["full_dynamic_inputs"] == 14
assert abs(ledger["full_dynamic_wall_s"] - 57.12461650004843) < 1e-8
assert accounting["provider_requests"] == 3
assert accounting["all_settled_complete_usage"]
assert accounting["new_billing_unknown"] == 0
assert accounting["original_r11_unchanged"]
assert abs(accounting["rate_estimate_usd"] - .0451242) < 1e-12
assert len(result["skipped_descendant_cells"]) == 4
assert verification["temporary_principals_active_grants"] == 0
assert verification["provider_after"]["inflight"] == 0
assert verification["new_execution_for_verification"] == 0
assert not verification["full_repository_health_claim"]
assert load(HERE / "adoption.json")["decision"] == "NO_AUTOMATIC_DESCENDANT_ADOPTION_RETAIN_PARENT_ARTIFACT"

feature = load(ROOT / "feature_list.json")["bf_pqe_bold_interventions_20261023"]
assert feature["status"] == "complete"
assert load(ROOT / "workbench/bf-campaign-s0-20261019/battery-world/project/features/BFA-093-pqe-bold-interventions/feature.yaml") == feature
state = load(OUT.parent / "execution-state.json")
assert state["status"] == "COMPLETE_FINITE_PACKAGE"
postflight = load(HERE / "postflight.json")
assert postflight["reclaimed_bytes"] == 0
assert postflight["new_backups_environments_worktrees"] == 0
assert postflight["retained_logical_bytes"] < 150000000
print(json.dumps({"status": "PASS_SAVED_FINAL_READBACK", "bound_files_checked": len(checked),
                  "original_manuscript_prefixes_preserved": 2,
                  "full_inputs": 14, "settled_provider_requests": 3,
                  "new_science_model_cheap_calls": 0,
                  "full_repository_health_claim": False}))
