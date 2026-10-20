#!/usr/bin/env python3
"""Editorial collection only. Reads closed files; never imports the apparatus.

This staging utility is intentionally separate from the portable reproducer.
Its source map is the exact collection receipt used by the coordinator.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coordinator-root", required=True, type=Path)
    ap.add_argument("--a-root", required=True, type=Path)
    ap.add_argument("--private-root", required=True, type=Path)
    args = ap.parse_args()
    root, a, private = args.coordinator_root, args.a_root, args.private_root
    final = a / "papers/method-reexecution-20261019/final"
    receipts = a / "docs/research/phase5-20261020/methods"
    data = final / "data"
    assert shutil.disk_usage(a).free > 10_000_000_000
    assert not (data / "manifest.json").exists(), "Never replace a collection silently"
    entries, source_map = [], []

    def add(source, destination, expected=None, purpose="saved observation"):
        source = Path(source)
        body = source.read_bytes()
        digest = sha(body)
        patterns = (rb"olp_[A-Za-z0-9_-]{20,}", rb"sk-[A-Za-z0-9_-]{20,}",
                    rb"(?i)Bearer\s+[A-Za-z0-9._~+/-]{16,}",
                    rb"https?://[^\s/:]+:[^\s/@]+@")
        assert not any(re.search(p, body) for p in patterns), "Credential-like literal; stop collection: " + str(source)
        if expected is not None:
            assert digest == expected, (str(source), digest, expected)
        target = data / destination
        assert not target.exists(), str(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        entry = dict(path=destination, sha256=digest, bytes=len(body), purpose=purpose)
        entries.append(entry)
        source_map.append(dict(source=str(source.resolve()), **entry))

    def read(p):
        return json.loads(Path(p).read_text())

    plan = root / "docs/research/phase-plan-20261019"
    add(plan / "phase4/result.json", "closed/phase4-result.json",
        "1a8a79356441ee0be3ad4a1625f9134b38481d13db3405c7f5176892cd5805db",
        "phase5 admission's closed phase4 result")
    for phase in (1, 2, 3):
        add(plan / f"phase{phase}/result.json", f"closed/phase{phase}-result.json")
    add(root / "deliveries/BF_FINAL_20261020/billing/campaign-requests.json",
        "billing/campaign-requests.json", purpose="all 1238 unique finite-campaign requests")
    add(root / "deliveries/BF_FINAL_20261020/billing/historical-UNKNOWN.json",
        "billing/historical-UNKNOWN.json", purpose="24 historical UNKNOWN; outside finite denominator")

    old = a / "papers/method-reexecution-20261019"
    for n in ("phase1-pi-evidence.json", "phase1-ar-evidence.json"):
        add(old / n, "ar/" + n)
    methods = a / "docs/research/parallel-20261019/methods"
    for n in ("f1a-controls.json", "paid-audit.json", "paid-results.csv"):
        add(methods / n, "early/" + n)
    for n in ("H0-r1", "H1-r1", "H1-r2", "H0-r2"):
        add(methods / "paid" / n / "result.json", f"early/{n}-result.json")

    p2 = private / "bf-phase2-20261020"
    binding = read(old / "phase2-binding.json")
    # All files used by the earlier audit, including original unsuccessful calls.
    for rel, rec in binding["evidence_files"].items():
        add(p2 / rel, "p2/" + rel, rec["sha256"])
    add(a / "docs/research/phase2-20261020/methods/actual-interpretation.json",
        "p2/actual-interpretation.json")

    p3 = private / "bf-phase3-20261020"
    binding = read(old / "phase3-binding.json")
    for rel, rec in binding["primary_inputs"].items():
        add(plan / "phase3" / rel, "p3/" + rel, rec["sha256"])
    actual = read(plan / "phase3/actual-comparison.json")
    episode_ids = sorted({e["id"] for g in actual["groups"].values() for e in g["episodes"]})
    assert len(episode_ids) == 140
    for eid in episode_ids:
        for leaf in ("episode-result.json", "provider-costs.json"):
            add(p3 / "episodes" / eid / leaf, f"p3/episodes/{eid}/{leaf}")

    p4 = private / "bf-phase4-20261020"
    ph = read(plan / "phase4/paper-handoff.json")
    # Primary sources are finite and selected explicitly, not a full-tree backup.
    for rel in ("actual-results.json", "final-details.json", "analysis-summary.json",
                "selection-complete.json", "preservation-final.json", "protocol-v1.1.json",
                "amendment-registration.json", "host-error-hold.json",
                "cache-repair-qualification.json", "recovery-results.json",
                "O0-transfer-results.json", "parent-freeze.json", "paper-handoff.json"):
        add(plan / "phase4" / rel, "p4/" + rel)
    for rel in ("G1-freeze.json", "G1-formation-accounting.json",
                "G1-actual-formation-receipt.json", "G1-structural-gate.json",
                "semantic-audit.json", "selected-methods.json", "final-selection-freeze.json"):
        add(p4 / rel, "p4/" + rel)
    bound = read(plan / "phase4/protocol-v1.1.json")["bound_files"]
    for rel, dest in [(f"configs/studies/phase4-20261020/methods/{n}.json", f"p4/config/{n}.json")
                      for n in ("frozen-parents", "history-sources", "model-history", "public-history")] + [
                          ("configs/studies/phase3-20261020/shared/instructions.json", "p4/config/phase3-instructions.json")]:
        expected = [v for k,v in bound.items() if k.endswith("/" + rel)]
        assert len(expected) == 1
        source = a / rel
        if not source.exists():
            source = root / "workbench/bf-campaign-s0-20261019/battery-world" / rel
        add(source, dest, expected[0], "frozen method parent and exact exposure packet")
    for lineage in (1, 2, 3):
        for arm in ("G0", "G1"):
            add(p4 / f"selections/L{lineage}-{arm}.json",
                f"p4/selections/L{lineage}-{arm}.json")
    actual = read(plan / "phase4/actual-results.json")
    assert len(actual["rows"]) == 77
    for row in actual["rows"]:
        eid = row["episode"]
        add(p4 / "episodes" / eid / "episode-result.json",
            f"p4/episodes/{eid}/episode-result.json", row["result_sha256"])
        add(p4 / "episodes" / eid / "provider-costs.json",
            f"p4/episodes/{eid}/provider-costs.json")
        add(p4 / "episodes" / eid / "participant-payload.json",
            f"p4/episodes/{eid}/participant-payload.json")
        if row["kind"] in ("H", "G"):
            for leaf in ("scientific/submission.json", "gateway/gateway-events.jsonl"):
                add(p4 / "episodes" / eid / leaf, f"p4/episodes/{eid}/{leaf}")

    ar = private / "bf-phase1-20261020/a/ar-service/pi-episode-001"
    for rel in ("episode-result.json", "protocol.json", "settlement-readback.json",
                "external-fixed-space-bound.json", "continuation-001/protocol.json",
                "continuation-001/episode-result.json", "continuation-001/provider-costs.json",
                "continuation-001/scientific/submission.json", "continuation-001/external/result.json",
                "continuation-001/external/ordering-policy-audit.json",
                "continuation-001/external/service-matrix.csv"):
        add(ar / rel, "ar/" + rel)
    p1bindings = read(old / "phase1-pi-evidence.json")["source_bindings"]
    for cid in ("candidate-001", "candidate-002", "candidate-003"):
        for leaf in ("candidate.json", "seal.json", "source-manifest.json"):
            source = ar / f"continuation-001/scientific/{cid}/{leaf}"
            add(source, f"ar/continuation-001/scientific/{cid}/{leaf}",
                p1bindings[str(source)]["sha256"], "candidate-bound failed A/R handoff")
        source = ar / f"continuation-001/external/{cid}.json"
        add(source, f"ar/continuation-001/external/{cid}.json", p1bindings[str(source)]["sha256"])
    for rel in ("configs/studies/phase1-20261020/ar/service-contract.v1.json",
                "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/ar_service.py",
                "scripts/campaign_ar_service.py"):
        expected = read(old / "phase1-pi-evidence.json")["frozen_sources"][rel]["sha256"]
        add(a / rel, "ar/apparatus/" + rel, expected, "frozen source for engineering inspection; never executed")

    # Byte-identical copies of the established shared style and official mark.
    for src, dst in ((a / "papers/shared/hkustgz-paper.sty", final / "hkustgz-paper.sty"),
                     (a / "papers/shared/assets/hkustgz-english.pdf", final / "assets/hkustgz-english.pdf")):
        dst.parent.mkdir(parents=True, exist_ok=True)
        b = src.read_bytes()
        dst.write_bytes(b)
        source_map.append(dict(source=str(src), path="../" + str(dst.relative_to(final)),
                               sha256=sha(b), bytes=len(b), purpose="unchanged shared style asset"))

    entries.sort(key=lambda x: x["path"])
    total = sum(x["bytes"] for x in entries)
    assert total < 50_000_000
    manifest = dict(schema_version="bf-f-saved-data-v1", entries=entries,
                    source_policy="Original bytes retained. Embedded historical host paths are inert provenance; the reproducer opens only manifest-relative paths.",
                    scientific_executions=0, provider_requests=0)
    (data / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    source_receipt = dict(schema_version="bf-phase5-a-exact-source-dependencies-v1",
                         created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         entries=source_map, data_files=len(entries), data_bytes=total,
                         data_manifest_sha256=sha((data / "manifest.json").read_bytes()),
                         no_science_or_model=True)
    (receipts / "source-dependencies.json").write_text(json.dumps(source_receipt, indent=2) + "\n")
    print(json.dumps(dict(data_files=len(entries), bytes=total, free_bytes=shutil.disk_usage(a).free)))


if __name__ == "__main__":
    main()
