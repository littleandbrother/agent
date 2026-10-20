"""Assemble independent readbacks and audit the frozen FIFO wording separately."""
from pathlib import Path
import csv
import gzip
import hashlib
import json

BASE = Path("/Users/depengsu/.local/share/bf-phase1-20261020/a/ar-service/pi-episode-001")
OUT = BASE / "continuation-001"
EXTERNAL = OUT / "external"


def main():
    submission = json.loads((OUT / "scientific/submission.json").read_text())
    results, ordering, matrix = {}, {}, []
    for receipt in sorted(EXTERNAL.glob("candidate-*.json")):
        data = json.loads(receipt.read_text())
        if data["execution_integrity"] != "PASS":
            raise ValueError("INDEPENDENT_INTEGRITY_FAILURE")
        name = receipt.stem
        results[name] = {"receipt": str(receipt), "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
            "candidate_sha256": data["candidate_sha256"], "execution_integrity": "PASS", "cases": {}}
        ordering[name] = {}
        for case, facts in data["cases"].items():
            statuses = {key: value["status"] for key, value in facts["gates"].items()}
            results[name]["cases"][case] = {"computational_services": facts["all_applicable_computational_services"],
                "gates": statuses, "sample_count": facts["sample_count"]}
            matrix.extend({"candidate": name, "case": case, "gate": gate, "status": status}
                for gate, status in statuses.items())
            folder = OUT / "scientific" / name / "cases" / case
            with gzip.open(folder / "observations.json.gz", "rt") as stream:
                raw = json.load(stream)
            task = json.loads((folder / "input.json").read_text())
            if raw["evictions"] or not task["device"]["nvm_persistent"]:
                raise ValueError("ORDER_AUDIT_NEEDS_RETENTION_EVICTION_EXTENSION")
            pending, violations = set(), []
            for action in raw["activity"]:
                if action["action"] == "commit":
                    pending.add(action["seq"])
                elif action["action"] == "program-dispatch":
                    if action["seq"] not in pending:
                        raise ValueError("INDEPENDENT_PENDING_REPLAY_FAILED")
                    if action["seq"] != min(pending):
                        violations.append({"time_s": action["time_s"], "selected_seq": action["seq"],
                            "oldest_pending_seq": min(pending), "pending_count": len(pending)})
                elif action["action"] == "tx" and action["ack"]:
                    pending.remove(action["seq"])
            ordering[name][case] = {"strict_fifo": "FAIL" if violations else "PASS",
                "violation_count": len(violations), "first_witness": violations[0] if violations else None,
                "scope": "Independent pending replay from commit/ACK actions; frozen persistent NVM and no evictions."}
    if len(results) != 3:
        raise ValueError("ALL_THREE_ATTEMPTS_MUST_BE_RETAINED")
    proof = json.loads((BASE / "external-fixed-space-bound.json").read_text())
    if proof["status"] != "FIXED_SPACE_NO_GO":
        raise ValueError("NO_FIXED_SPACE_PROOF")
    with (EXTERNAL / "service-matrix.csv").open("x", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["candidate", "case", "gate", "status"])
        writer.writeheader()
        writer.writerows(matrix)
    policy = {"schema_version": "bf-phase1-external-order-policy-audit-v1",
        "status": "CONTRACT_ORDER_AMBIGUITY_BLOCKS_UNQUALIFIED_REPAIR",
        "issue": "Frozen task text requires oldest unacknowledged first, while the v2 legal program grammar permits choosing rank. Newest-first is valid under that hook but violates strict FIFO. No frozen text is edited.",
        "cases": ordering, "new_simulations": 0, "paid_requests": 0, "native_dispatches": 0}
    result = {"schema_version": "bf-phase1-external-episode-readback-v1",
        "status": "FIXED_SPACE_NO_GO_WITH_CONDITIONAL_RANK_REPAIR",
        "owner": json.loads((OUT / "episode-result.json").read_text())["owner"],
        "episode": submission["host_lease"]["episode_id"], "submitted_candidate": Path(submission["candidate_artifact"]).name,
        "submission_conclusion": submission["conclusion"], "candidate_count": 3, "new_simulations": 12,
        "independent_new_simulations": 0, "candidates": results,
        "fixed_space_bound_receipt": str(BASE / "external-fixed-space-bound.json"),
        "ordering_policy_receipt": str(EXTERNAL / "ordering-policy-audit.json"), "matrix_rows": len(matrix),
        "product_acceptance": "NOT_ACCEPTED", "physical_qualification": "UNKNOWN",
        "method_benefit": "NOT_TESTED", "rsi": "NOT_TESTED", "paid_requests_in_readback": 0, "native_dispatches": 0}
    for name, data in [("ordering-policy-audit.json", policy), ("result.json", result)]:
        with (EXTERNAL / name).open("x") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write("\n")
    print(json.dumps({"status": result["status"], "candidate_count": 3, "matrix_rows": len(matrix),
        "selected": result["submitted_candidate"], "ordering_witnesses": {key: value["ar-upload-dedup"] for key, value in ordering.items()}}))


if __name__ == "__main__":
    main()
