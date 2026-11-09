"""Validate saved public facts and hash B deliverables; no apparatus imports."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import ast
import hashlib
import json
import shutil

BDIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[5]
BASE = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
SRC = BASE / "packages/python/bfworld/src/bfworld/agentlab/pqe20261022"
PACKAGE = "BF-PQE-S3-E3LC-20261023-001"
PAPERS = [BASE / f"papers/pqe20261022/paper{i}-stage3-e3lc-increment.md" for i in (1, 2)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def read(name):
    return json.loads((BDIR / name).read_bytes())


def write(name, value):
    path = BDIR / name
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(raw)
    if path.read_bytes() != raw:
        raise ValueError("DELIVERABLE_CONTENT_READBACK_FAILED")
    return ref(path)


def usd(values):
    return format(sum((Decimal(str(v)) for v in values), Decimal(0)), ".7f")


def main():
    free_before = shutil.disk_usage(BDIR).free
    if free_before < 10_000_000_000 + 1_000_000:
        raise ValueError("STORAGE_GATE")
    door = read("PUBLIC-READBACK.json")
    summary = read("DOOR-SUMMARY.json")
    opt = read("OPT-READBACK.json")
    lc = read("LC-READBACK.json")
    if len(door["episodes"]) != 8 or summary["source_readback_sha256"] != digest(BDIR / "PUBLIC-READBACK.json"):
        raise ValueError("DOOR_READBACK_BINDING")
    expected = {
        SRC / "methods.py": "260da9338be02a906070e78ca8ee4dc97c13839a524b9627835cdd87d07d5750",
        SRC / "episode_methods.py": "c4aeb3bf17e5f11076c9147a75d194e3ec0dcfe850592b58d744f1b5889b25c8",
        SRC / "e3lc_methods.py": "80bf2b41a9a8b7bdd1abe130cddbc0f4db81cc68a584807d63c2f7bdc25afb7f",
        BASE / "tests/test_pqe_e3lc_methods.py": "1f9881c348cee1f3f8dae09acea72a116b4b6a90494cea4d5014a98d98f11107",
        BASE / "scripts/pqe_e3lc_opt.py": "371a98fcb647feccb2b2ed7d1eb3fb75db2a05888419fcb986d7ecd19c1ffe36",
        BASE / "studies/pqe20261022/e3lc/shared/conditions.json": "237d07ad6d80684d757595445d3cfbb6479472f38566377c92c712d7dedcadf3",
        BDIR / "OPT-PROTOCOL.json": "05a23866ac9532fb35cdb5a4e5293a44501ca6788f1deb6112385e46e85d87f9",
    }
    for path, sha in expected.items():
        if digest(path) != sha:
            raise ValueError(f"FROZEN_SOURCE_HASH_CHANGED:{path.name}")
    callbacks = [c for e in door["episodes"] for c in e["callback_records"]] + lc["callback_records"]
    usage = [c["response"]["usage"] for c in callbacks]
    ids = [i for u in usage for i in u["request_ids"]]
    if len(ids) != 46 or len(set(ids)) != 46 or any(u["status"] != "KNOWN" or not isinstance(u["cost"], (int, float)) for u in usage):
        raise ValueError("PROVIDER_USAGE_AUDIT")
    if usd(u["cost"] for u in usage) != "0.6355623":
        raise ValueError("PROVIDER_TOTAL_MISMATCH")
    identities = sorted(set(u["model_identity"] for u in usage))
    if len(identities) != 1:
        raise ValueError("EXPOSED_ROUTE_CHANGED")
    ep_results = [e["episode_result"] for e in door["episodes"]] + [lc["episode_result"]]
    if any(e["accounting"]["unknown_or_missing_usage"] or e["accounting"]["unsettled_reserved_usd"] or e["native_calls"] or e["hardware_runs"] for e in ep_results):
        raise ValueError("EPISODE_COST_OR_BOUNDARY_MISMATCH")
    if any(e["generated_code_loaded"] for e in door["episodes"]) or lc["generated_code_loaded"]:
        raise ValueError("UNEXPECTED_GENERATED_CODE")
    classes = Counter()
    errors = Counter()
    manual = []
    for row in summary["episodes"]:
        conclusion = row["model_conclusion"]
        last = row["last_public_service"]
        if conclusion["verdict"] == "PASS" and last["verdict"] != "PASS":
            raise ValueError("WRONG_ADOPTION_REQUIRES_REVIEW")
        manual.append({"episode":row["episode"], "model_verdict":conclusion["verdict"], "scope":conclusion["scope"],
                       "last_complete_public_service":last, "wrong_adoption":False,
                       "unsupported_task_wide_exclusion":False, "classification":"Manual source-bound conclusion/scope review; no private proof used."})
        for action in row["actions"]:
            if action["execution_status"] == "COMPLETE":
                classes[f"model_valid={action['model_valid']};service={action['public_check']['verdict']}"] += 1
        errors.update(row["domain_errors"])
    if sorted(classes.values()) != [2, 6, 8] or sum(errors.values()) != 8:
        raise ValueError("DOOR_OUTCOME_CLASSIFICATION_MISMATCH")
    if opt["actual_evaluations"] != 12 or opt["attempted_new_scientific_inputs"] != 11 or opt["exact_result_reuses"] != 1:
        raise ValueError("OPT_TOTAL_MISMATCH")
    for run in opt["runs"]:
        if run["stop"] != "EVALUATION_CAP" or len(run["evaluations"]) != 6:
            raise ValueError("OPT_STOP_MISMATCH")
        if any(not e["public_result"]["model_valid"] or e["public_result"]["public_check"]["verdict"] != "FAIL" for e in run["evaluations"]):
            raise ValueError("OPT_OUTCOME_MISMATCH")
    lcr = lc["public_action_result"]
    lcs = next(s for s in lc["steps"] if s.get("result"))["result"]
    initial = lc["initial_result"]
    for key in ("task_sha256", "sources", "program_version", "engineering_model_sha256", "problem"):
        if initial[key] != lcr[key] or lcr[key] != lcs[key]:
            raise ValueError(f"LC_FROZEN_SEMANTICS_MISMATCH:{key}")
    for key in ("design", "model_valid", "execution_status", "domain_errors", "public_check"):
        if lcr[key] != lcs[key]:
            raise ValueError(f"LC_PUBLIC_FILE_MISMATCH:{key}")
    if lc["initial_task"]["public_inputs"]["allowed_for_learning"] is not False or lcr["public_check"] != {"verdict":"PASS", "failures":[], "unknown":[], "received_count":1441}:
        raise ValueError("LC_CLAIM_BOUNDARY_MISMATCH")
    audit = {
        "schema":"pqe-e3lc-b-public-analysis-audit-v1", "package":PACKAGE,
        "status":"COMPLETE_PUBLIC_FACT_READBACK", "source_readbacks":[ref(BDIR / n) for n in ("PUBLIC-READBACK.json", "DOOR-SUMMARY.json", "OPT-READBACK.json", "LC-READBACK.json")],
        "provider":{"requests":46, "unique_request_ids":46, "known":46, "estimated_usd":"0.6355623", "unknown_or_missing_usage":[], "unsettled_reserved_usd":0, "exposed_identity":identities[0], "upstream_weights":"unreported", "invoice_claim":False},
        "door":{"episodes":8, "physical_tasks":1, "independent_model_contexts":2, "outcomes":dict(classes), "domain_errors":dict(errors), "wrong_adoption":0, "unsupported_task_wide_exclusion":0, "nr_consumed_deviations":0, "episode_classification":manual},
        "opt":{"evaluations":12, "new_scientific_inputs":11, "exact_reuses":1, "valid_service_failures":12, "model_requests":0, "frozen_source_protocol_hashes_match":True, "global_infeasibility_or_general_algorithm_failure":False},
        "lc":{"condition":"default H0 / strong_generic", "requests":3, "estimated_usd":"0.0351039", "candidate_evaluations":1, "action_new_scientific_inputs":1, "initial_scientific_inputs_separate":1, "received":1441, "complete_public_service":"PASS", "task_science_program_problem_bindings_unchanged":True, "allowed_for_learning":False, "unseen_F2_or_transfer_claim":False},
        "frozen_files":[ref(p) for p in expected],
        "early_note_clarification":"FIRST-CONTEXT wording does not deny generation/ranking: r1 B3 generated3/selected1; r2 generated4,3,4/selected1 per round. No extra selected observe. Original early note retained; final REPORT/DOOR-SUMMARY supersede it for complete analysis.",
        "B_execution":{"tests":0,"provider_requests":0,"scientific_inputs":0,"native_calls":0,"hardware_runs":0,"runtime_imports":0},
        "read_boundary":"Authorized public files plus B-owned implementation/receipts only; first4 original trajectories not reread. No raw/assessment/private/A reports/LC host/protocol/input or old qualification outcomes.",
    }
    audit_ref = write("ANALYSIS-AUDIT.json", audit)
    owned = [SRC / "e3lc_methods.py", BASE / "tests/test_pqe_e3lc_methods.py", BASE / "scripts/pqe_e3lc_opt.py", BASE / "studies/pqe20261022/e3lc/shared/conditions.json", *PAPERS]
    local = sorted(p for p in BDIR.rglob("*") if p.is_file() and p.name not in {"B-RECEIPT.json", "DELIVERY-READBACK.json"})
    paths = [*owned, *local]
    if any(p.is_symlink() for p in paths):
        raise ValueError("UNEXPECTED_DELIVERABLE_SYMLINK")
    ast_paths = [p for p in paths if p.suffix == ".py"]
    for p in ast_paths:
        ast.parse(p.read_text(), filename=str(p))
    inventory = [ref(p) for p in paths]
    retained = sum(i["bytes"] for i in inventory)
    if retained + 100_000 >= 5_000_000:
        raise ValueError("B_RETAINED_OUTPUT_CAP")
    receipt = {
        "schema":"pqe-e3lc-b-final-receipt-v1", "package":PACKAGE, "feature":"BFA-084-pqe-e3-scope-lc",
        "signal":"BF-PQE-S3-E3LC-B-COMPLETE-20261023-001", "B_status":"COMPLETE", "S0_root_seal":"PENDING_S0",
        "audit":audit_ref, "report":ref(BDIR / "REPORT.md"), "paper_increments":[ref(p) for p in PAPERS],
        "artifact_inventory":inventory, "ast_parse_only":{"files":len(ast_paths),"status":"PASS","is_test_suite_or_scientific_validation":False},
        "tests":"S0 centralized thin entry checks and the sole corrected differential fixture rerun; original failure retained and TEST-FIXTURE-AMENDMENT binds old/new fixture hashes. B executed zero tests and no root init.",
        "claim_boundary":"One exposed DOOR task/two contexts; finite OPT; one new development LC default-H0 action. No formation/adoption/learning/RSI/unseen-transfer/native/hardware/statistical reliability claim; prior F1 non-adoption retained.",
        "storage":{"available_bytes_before_finalization":free_before,"estimated_peak_additional_bytes":1_000_000,"output_directory":str(BDIR),"retained_output_cap_bytes":5_000_000,"inventoried_bytes_before_receipts":retained,"backups_environments_source_copies_created":0,"no_apfs_reclamation_claim":True},
        "commits":0,"pushes":0,"next_owner":"S0: verify B hashes, integrate total accounting/generated-file/storage receipts, update root feature/progress/handoff and seal; no new experiment authorized.",
        "completed_at_utc":datetime.now(timezone.utc).isoformat(),
    }
    receipt_ref = write("B-RECEIPT.json", receipt)
    checked = [*inventory, receipt_ref]
    for item in checked:
        p = Path(item["path"])
        if digest(p) != item["sha256"] or p.stat().st_size != item["bytes"]:
            raise ValueError("FINAL_DELIVERY_HASH_READBACK")
    actual_retained = sum(p.stat().st_size for p in BDIR.rglob("*") if p.is_file()) + sum(p.stat().st_size for p in owned)
    delivery_ref = write("DELIVERY-READBACK.json", {
        "schema":"pqe-e3lc-b-delivery-readback-v1", "package":PACKAGE,"status":"PASS", "B_receipt":receipt_ref,
        "files_verified":checked,"available_bytes_after":shutil.disk_usage(BDIR).free,
        "retained_bytes_before_this_readback":actual_retained,"retained_output_cap_bytes":5_000_000,
        "filesystem_delta_not_attributed_to_B":"S0 is concurrently closing the campaign; no reclaimed-byte claim.",
        "validation":"Exact local content/hash readback and AST only. No tests/runtime/provider/scientific/native/hardware execution; no private data reads.",
    })
    print(json.dumps({"receipt":receipt_ref,"delivery":delivery_ref,"audit":audit_ref,"retained_bytes":actual_retained + delivery_ref["bytes"],"available_bytes_after":shutil.disk_usage(BDIR).free},ensure_ascii=False))


if __name__ == "__main__":
    main()
