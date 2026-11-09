"""Bind one prospectively sealed, storage-bounded action-policy package."""
from copy import deepcopy
import argparse
import ast
import json

import runtime as r


def build():
    from bfworld.agentlab.pqe20261024policy.parent import policy_parent_program,policy_runtime_contract
    original=r.read(r.BASE/"training-execution/shared/protocol.json")
    code=deepcopy(original["source_bindings"])
    for path,expected in code.items():
        if r.bind(path)["sha256"]!=expected:
            raise ValueError("SEALED_REQUIRED_SOURCE_CHANGED:"+path)
    ready=r.read(r.OUT/"b/SOURCE-READY.json")
    for name,expected in ready["source_sha256"].items():
        if r.bind(r.PKG/name)["sha256"]!=expected:
            raise ValueError("B_READY_SOURCE_CHANGED:"+name)
    for path in list(r.PKG.glob("*.py"))+list(r.HERE.glob("*.py")):
        ast.parse(path.read_text(),filename=str(path))
        code[str(path)]=r.bind(path)["sha256"]
    parent=policy_parent_program()
    r.save(r.OUT/"shared/common-parent.json",parent)
    model=deepcopy(original["model_contract"])
    model.update(package=r.PACKAGE,at=r.now(),total_usd=100,requests_total_max=228)
    descriptors=deepcopy(original["training_task_descriptors"])
    for item in descriptors:
        item.update(parent_final_verdict="UNKNOWN",parent_correct_stop=False,parent_model_valid=False,
            parent_basis="Pending actual common model-decision parent development in this package; old fixed-parent outcome is not this reference.")
    protocol=dict(package=r.PACKAGE,frozen_at=r.now(),model_contract=model,
        source_bindings=code,methods_sha256=original["methods_sha256"],apparatus_source=original["apparatus_source"],
        public_bindings=dict(parent=r.bind(r.OUT/"shared/common-parent.json"),
            history=original["public_bindings"]["history"],catalog=original["public_bindings"]["catalog"]),
        training_tasks=deepcopy(original["training_tasks"]),training_task_descriptors=descriptors,
        tasks=r.read(r.HERE/"host/test-bindings.json")["tasks"],
        sealed_host_manifest=r.bind(r.OUT/"a/host/MANIFEST.json"),
        public_allowlist=original["public_allowlist"],provider_before=r.host.provider_snapshot(),
        policy_runtime_contract=policy_runtime_contract(parent),storage=r.capacity(),
        formation_limits=r.FORMATION,solve_limits=r.SOLVE,total_caps=r.TOTAL,
        transport_resource_increment=r.TRANSPORT_CAP_INCREMENT,
        rules=dict(prospective_tasks_sealed_before_parent_implementation=True,
            public_parent_source_fully_inline=True,shared_developer_parent_change_not_learning_gain=True,
            same_parent_history_model_tools_rights_budgets=True,raw_proposals_each=1,revisions_each=1,
            one_round_each_original_and_revision=True,nested_same_owner_ledger_deadline=True,
            fair_remaining_training_slots_and_revision_reserve=True,
            diagnostic_admission_distinct_from_final_adoption=True,
            test_order=["t1","t2","t3","t4"],conditions=["H1","H2","H4"],
            parent_development_candidates_each=2,training_candidates_each_task=2,test_candidates_each=3,
            no_no_child_fallback=True,merge_training_before_all_tests=True,
            no_test_feedback_returned_to_formation_or_other_solve=True,
            final_all_four_full_service_and_no_parent_pass_regression=True,
            both_all_pass_requires_total_child_cost_including_learning_lower=True,
            public_request_bytes_cap=220000,low_cost_cap=120,
            original_r11_exception_only=True,no_old_quota_or_result_rescue=True,
            no_backup_environment_worktree=True))
    return protocol


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=["working","freeze"])
    args=parser.parse_args()
    if r.PROTOCOL.exists() or (r.HERE/"run-started.json").exists():
        raise ValueError("FROZEN_PACKAGE_NO_REPLACEMENT")
    protocol=build()
    r.configure(protocol)
    if args.phase=="working":
        r.save(r.OUT/"shared/working-protocol.json",protocol)
        print("working host configuration bound; zero provider dispatch")
        return
    direct=r.read(r.HERE/"direct-path-check.json")
    if direct["status"]!="PASS_SOFTWARE_HOST_THROUGH_CHAIN":
        raise ValueError("ONE_REAL_ASK_HOST_SOFTWARE_PATH_REQUIRED")
    revision=r.read(r.HERE/"common-revisions.json")
    if revision["count"]>2:
        raise ValueError("PRE_FORMATION_COMMON_REVISION_CAP")
    protocol.update(direct_path_check=r.bind(r.HERE/"direct-path-check.json"),pre_formation_common_revisions=revision["count"])
    resource=r.read(r.HERE/"resource-ledger.json")
    if resource.get("software_checks_seeded"):
        raise ValueError("SOFTWARE_CHECKS_ALREADY_SEEDED")
    bchecks=r.read(r.OUT/"b/SOURCE-READY.json")["software_check_ledger"]["counted_total"]
    resource["cheap_checks"]+=bchecks+direct["budgeted_software_operations"]
    resource["software_checks_seeded"]=True
    if resource["cheap_checks"]+resource["cheap_screen_reserved"]>120:
        raise ValueError("FINITE_CHEAP_RESERVATION_CAP")
    r.save(r.HERE/"resource-ledger.json",resource)
    r.save(r.PROTOCOL,protocol)
    r.validate(protocol)
    state=r.read(r.BASE/"execution-state.json")
    state.update(status="RUNNING_FROZEN_FINITE_PACKAGE",protocol=str(r.PROTOCOL),
        direct_path_check=str(r.HERE/"direct-path-check.json"),next_action="Actual common-parent two public development solves, milestone once, then both automatic edits/training and four prospective cases; no approval wait.")
    r.save(r.BASE/"execution-state.json",state)
    print(json.dumps(dict(status="FROZEN",source_bindings=len(protocol["source_bindings"]),
        full_inputs_already_used=resource["full_dynamic_inputs"],cheap_seed=resource["cheap_checks"],
        reserved_screen_checks=resource["cheap_screen_reserved"],provider=protocol["provider_before"],storage=r.capacity())))


if __name__=="__main__":
    main()
