"""Eight preregistered new-path cases, append-only receipt, no consumers."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import gzip
import importlib.util
import json
import os
import time

from joint_strategy import Strategy, digest

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT.parent
OLD = ROOT.parents[1] / "relation-synthesis-20261102"


def public(design, verdict="FAIL", received=0):
    return {"design": deepcopy(design), "results": [{"condition_id": "fixture", "design": deepcopy(design),
        "execution_status": "COMPLETE", "model_valid": True, "facts": {},
        "public_check": {"verdict": verdict, "received_count": received}}]}


def fixture_contract():
    return {"design_domain": {"capacity": {"kind": "number", "min": 1., "max": 20.},
        "rate": {"kind": "number", "min": 1., "max": 10.},
        "durable": {"kind": "boolean"}, "producer": {"kind": "boolean"},
        "reader": {"kind": "boolean"}, "clear": {"kind": "enum", "values": ["never", "early", "save", "ack"]}}}


INITIAL = {"capacity": 2., "rate": 5., "durable": False, "producer": False, "reader": False, "clear": "never"}


def fixture_facts(contract, design, public_result=None, *, meter=None):
    # Source-fact fixture: these are explicit program contracts, not science.
    checks = [{"kind": "CONSUMPTION", "subject": "record", "holds": design["reader"],
               "applicable": design["producer"], "dependencies": ["reader"],
               "predicate": {"fixture": "producer must have reader"}, "refs": ["SOFTWARE_FIXTURE:consumer"]},
              {"kind": "RELIABLE_HANDOFF", "subject": "record", "holds":
                   design["clear"] == "ack" or (design["clear"] == "save" and design["durable"]),
               "applicable": design["producer"] and design["reader"] and design["clear"] != "never",
               "dependencies": ["durable", "clear"], "predicate": {"fixture": "actual configured destination"},
               "refs": ["SOFTWARE_FIXTURE:handoff"]},
              {"kind": "DYNAMIC_ENERGY", "subject": "load", "holds": None,
               "applicable": True, "dependencies": ["capacity", "rate", "producer", "reader"],
               "predicate": {"fixture": "requires full observation"}, "refs": ["SOFTWARE_FIXTURE:energy"]}]
    return {"design_sha256": digest(design), "checks": checks, "source": "SOFTWARE_FIXTURE",
            "observed_current_design": public_result is not None}


def fixture_calc(contract, design, operation="all", *, public_result=None, meter=None):
    return {"design_sha256": digest(design), "constraints": [
        {"field": "capacity", "relation": ">=", "value": 8., "source_refs": ["SOFTWARE_FIXTURE:charge bound"]},
        {"field": "rate", "relation": "<=", "value": 3., "source_refs": ["SOFTWARE_FIXTURE:service load bound"]}],
        "numeric_facts": {"capacity_rate_product": design["capacity"] * design["rate"]},
        "source": "SOFTWARE_FIXTURE", "scientific_inputs": 0}


def make(*, recursive=False, calc=fixture_calc, facts=fixture_facts, design=INITIAL, seed=1):
    return Strategy(fixture_contract(), deepcopy(design), public(design), fact_fn=facts,
                    calc_fn=calc, recursive=recursive, seed=seed)


def run():
    output = ROOT / "direct-checks.json"
    if output.exists():
        raise RuntimeError("APPEND_ONLY_DIRECT_RECEIPT_EXISTS")
    started = time.monotonic()
    cases, actual_artifacts, actual_events, forbidden_full_attempts = [], {}, [], []

    def meter(kind, key, details=None):
        charged = sum(e['kind'] in {'cheap_numeric', 'geometry_miss'} for e in actual_events)
        if kind in {'cheap_numeric', 'geometry_miss'} and charged >= 24:
            actual_events.append({'kind':'BUDGET_REJECTED','requested_kind':kind,'key':key,'details':details})
            raise RuntimeError('B_CHEAP_INPUT_CAP_24')
        actual_events.append({'kind':kind,'key':key,'details':details})

    def case(name, fn):
        at = time.monotonic()
        try:
            details = fn()
            cases.append({"name": name, "status": "PASS", "details": details, "wall_s": time.monotonic() - at})
        except Exception as exc:
            cases.append({"name": name, "status": "FAIL", "error": type(exc).__name__ + ": " + str(exc),
                          "wall_s": time.monotonic() - at})

    def joint_recalculation():
        s = make()
        p = s.propose()
        c = next(c for c in p["common_candidates"] if c["origin"] == "SAME_PARENT_JOINT_RECALCULATED")
        assert c["design"]["capacity"] == 8. and c["design"]["rate"] == 3.
        assert c["predicted_facts"]["calculations"]["numeric_facts"]["capacity_rate_product"] == 24.
        assert c["side_effects_recomputed"] and c["parent_id"] == s.current_parent_id
        return {"fixture_only": True, "joint_patch": c["design_patch"], "actual_candidate_numeric_product": 24.}

    def preserve_current_parent():
        s = make()
        first = s.propose()["common_candidates"][0]
        accepted = s.update(public(first["design"], received=1))
        assert accepted["generated_candidate_adopted_exact"] == first["id"]
        edited = {**first["design"], "capacity": 10., "durable": True}
        receipt = s.update(public(edited, received=2))
        assert receipt["free_or_modified_model_proposal"] and receipt["previous_parent_retained"]
        next_pool = s.propose()
        assert next_pool["parent_design"]["capacity"] == 10.
        assert all(c["design"]["capacity"] >= 8. for c in next_pool["candidates"] if c["origin"] == "SAME_PARENT_JOINT_RECALCULATED")
        assert s.archive[s.current_parent_id]["design"]["durable"] is True
        return {"fixture_only": True, "current_parent": next_pool["parent_id"], "archive_size": len(s.archive), "automatic_restart": False}

    def conflict_and_invalidation():
        def calc(contract, design, operation="all", *, public_result=None, meter=None):
            return {"design_sha256": digest(design), "constraints": [
                {"field": "capacity", "relation": ">=", "value": 12.},
                {"field": "capacity", "relation": "<=", "value": 4.},
                {"field": "rate", "relation": "<=", "value": 3.}], "observations_bound": public_result is not None}
        s = make(calc=calc)
        p = s.propose()
        assert p["joint_conflicts"] and p["joint_conflicts"][0]["field"] == "capacity"
        c = p["common_candidates"][0]
        assert not c["predicted_facts"]["prior_observation_applies_to_candidate"]
        assert c["predicted_facts"]["calculations"]["observations_bound"] is False
        assert any(o["status"] == "UNKNOWN" for o in c["changed_obligations"])
        return {"fixture_only": True, "conflicts": p["joint_conflicts"], "candidate_old_evidence_invalidated": True}

    def inactive_and_authority():
        d = {"holding_component": "off", "holding_capacity": 2, "holding_overflow": "drop_new", "read_source": "contact_only", "clear_after": "never"}
        c = {"design_domain": {"holding_component": {"kind": "enum", "values": ["off", "lp_fifo"]},
             "holding_capacity": {"kind": "integer", "min": 1, "max": 4},
             "holding_overflow": {"kind": "enum", "values": ["drop_new", "overwrite_oldest"]},
             "read_source": {"kind": "enum", "values": ["contact_only", "holding_then_contact"]},
             "clear_after": {"kind": "enum", "values": ["never", "early", "save", "ack"]}}}
        s = Strategy(c, d, public(d), fact_fn=fixture_facts, calc_fn=fixture_calc)
        norm = s._normalize({**d, "holding_capacity": 4}, d)
        assert norm["design"] == d and norm["normalized_inactive_fields"]
        try:
            s._normalize({**d, "new_rtc": True}, d)
        except ValueError:
            rejected = True
        else:
            rejected = False
        assert rejected
        assert s.archive[s.current_parent_id]["design"]["holding_component"] == "off"
        return {"fixture_only": True, "inactive_normalization": norm["normalized_inactive_fields"], "unauthorized_RTC_rejected": rejected}

    def recursive_factual_chain():
        s = make(recursive=True)
        parent = s.archive[s.current_parent_id]
        base = s._inspect(parent["design"], parent)
        seed = s._candidate({**parent["design"], "producer": True}, parent, base, "SOURCE_FACT_FIXTURE_SEED", [])
        child, attempts = s._recursive(seed, parent, base)
        assert child is not None and child["design"]["reader"] is True
        assert len(child["closure_chain"]) >= 2
        assert child["closure_chain"][1]["transition"]["consumed_actual_obligation"]["kind"] == "CONSUMPTION"
        checks_by_clear = {}
        for clear in ["early", "save", "ack"]:
            result = fixture_facts(s.contract, {**child["design"], "durable": True, "clear": clear})
            checks_by_clear[clear] = next(c['holds'] for c in result['checks'] if c['kind']=='RELIABLE_HANDOFF')
        assert checks_by_clear == {"early": False, "save": True, "ack": True}
        return {"fixture_only": True, "actual_chain": child["closure_chain"], "clear_guarantee_fixture": checks_by_clear, "attempts": attempts}

    def unknown_probe():
        p = make().propose()
        c = p["common_candidates"][0]
        unknown = [x for x in c["predicted_facts"]["checks"] if x["holds"] is None]
        assert unknown and c["full_service"] == "UNKNOWN" and c["requires_model_choice"]
        assert p["automatic_candidate_selected"] is None and p["free_joint_edit_rights"]
        return {"fixture_only": True, "unknowns": len(unknown), "conditional_candidate_returned": True, "no_dispatch": True}

    def common_cut_and_meter():
        off, on = make(), make(recursive=True)
        a, b = off.propose(), on.propose()
        assert a["common_candidates_sha256"] == b["common_candidates_sha256"]
        assert a["common_candidates"] == b["common_candidates"]
        assert len(a["candidates"]) <= 3 and len(b["candidates"]) <= 3
        assert off.snapshot()["archive"] == on.snapshot()["archive"]
        assert off.cost["full_dispatches"] == on.cost["model_dispatches"] == 0
        return {"fixture_only": True, "common_pool_sha256": a["common_candidates_sha256"], "identical_archive": True}

    def actual_interfaces():
        path = PACKAGE / "a/shared_facts.py"
        spec = importlib.util.spec_from_file_location("bfa101_shared_facts", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from bfworld.agentlab.pqe20261024debt import adapter, consumer
        from bfworld.agentlab.pqe20261023bold import lc_adapter
        def forbidden(*args, **kwargs):
            forbidden_full_attempts.append('FORBIDDEN_FULL_ENTRY')
            raise AssertionError('B_FULL_EXECUTION_FORBIDDEN')
        module.lc.simulate = forbidden
        adapter.execute = consumer.execute_design = lc_adapter.execute = forbidden
        details = []
        for name, seed in [("identity-progress", 314159), ("saved-undelivered", 271828)]:
            source = OLD / "shared/prefixes" / (name + ".json.gz")
            with gzip.open(source, "rt") as stream:
                v = json.load(stream)
            contract, result = v["public_contract"], v["family_result"]
            contract = {**contract, "initial_design": result["design"]}
            strategies = [Strategy(contract, result["design"], result,
                          fact_fn=module.candidate_facts, calc_fn=module.calculate,
                          recursive=rec, seed=seed, meter=meter) for rec in [False,True]]
            outputs = [s.propose() for s in strategies]
            actual_artifacts[name] = {"source": str(source), "outputs": outputs,
                                      "strategies": [s.snapshot() for s in strategies]}
            assert outputs[0]["common_candidates_sha256"] == outputs[1]["common_candidates_sha256"]
            assert all(len(x["candidates"]) <= 3 for x in outputs)
            details.append({"prefix":name,"common_pool_equal":True,"candidate_counts":[len(x["candidates"]) for x in outputs],
                            "joint_patches":[c["design_patch"] for c in outputs[0]["common_candidates"] if c["origin"]=='SAME_PARENT_JOINT_RECALCULATED']})
        lcroot = OLD / 'a/stage3-host/LC'
        names = ['local-repair-control','light-before-link-challenge','link-before-light-challenge']
        tasks = [json.loads((lcroot/name/'task.json').read_text()) for name in names]
        design = json.loads((lcroot/names[0]/'initial-design.json').read_text())
        contract = {'family_id':'REL-SYNTH-LC-20261102','world_kind':'LC','tasks':tasks,
                    'design_domain':tasks[0]['design_domain'],'initial_design':design,
                    'initial_problem':tasks[0]['initial_problem']}
        observed = {'design':design,'results':[{'condition_id':t['task_id'],'design':design,
                    'execution_status':'NOT_EXECUTED','model_valid':True,'public_check':{'verdict':'UNKNOWN'}} for t in tasks]}
        s = Strategy(contract,design,observed,fact_fn=module.candidate_facts,calc_fn=module.calculate,meter=meter)
        before = s._inspect(design,s.archive[s.current_parent_id])
        changed_design = {**design,'area_cm2':tasks[0]['design_domain']['area_cm2']['max'],
                          'capacitance_f':tasks[0]['design_domain']['capacitance_f']['max']}
        after = s._candidate(changed_design,s.archive[s.current_parent_id],before,'LC_HARDWARE_DIRECT_CHECK',[])
        pool = s.propose()
        actual_artifacts['LC-hardware'] = {'source_public_tasks':[str(lcroot/name/'task.json') for name in names],
            'before':before,'changed_candidate':after,'proposal':pool,'strategy':s.snapshot()}
        assert {'area_cm2','capacitance_f'} <= set(after['design_patch'])
        assert before['actual_facts']['design_sha256'] != after['predicted_facts']['actual_facts']['design_sha256']
        assert before['calculations']['tasks'][0]['storage']['maximum_energy_j'] != after['predicted_facts']['calculations']['tasks'][0]['storage']['maximum_energy_j']
        assert before['calculations']['tasks'][0]['source']['declared_scenario_points'] != after['predicted_facts']['calculations']['tasks'][0]['source']['declared_scenario_points']
        assert after['full_service']=='UNKNOWN' and pool['free_joint_edit_rights']
        assert not forbidden_full_attempts
        return {"actual_A_source": str(path), "prefixes": details, "LC_hardware_variables_active":True,
                "LC_joint_patches":[c['design_patch'] for c in pool['common_candidates'] if c['origin']=='SAME_PARENT_JOINT_RECALCULATED'],
                "full_consumers": 0}

    for name, fn in [("same_parent_joint_recalculation",joint_recalculation),
        ("update_preserves_actual_parent_and_model_freedom",preserve_current_parent),
        ("conflict_and_candidate_evidence_invalidation",conflict_and_invalidation),
        ("inactive_fields_and_authority",inactive_and_authority),
        ("candidate_fact_companion_recheck",recursive_factual_chain),
        ("unknown_permitted_probe_not_static_PASS",unknown_probe),
        ("common_joint_layer_only_recursion_cut",common_cut_and_meter),
        ("actual_A_interfaces_two_public_prefixes",actual_interfaces)]:
        case(name,fn)
    receipt = {"schema":"BFA101-B-direct-checks-v1","at":datetime.now(timezone.utc).isoformat(),
               "software_cases":len(cases),"PASS":sum(c['status']=='PASS' for c in cases),
               "FAIL":sum(c['status']=='FAIL' for c in cases),"cases":cases,
               "actual_resource_events":actual_events,"full_consumers":0,"provider_calls":0,
               "forbidden_full_attempts":forbidden_full_attempts,
               "cheap_numeric_inputs":sum(e['kind']=='cheap_numeric' for e in actual_events),
               "actual_geometry_misses":sum(e['kind']=='geometry_miss' for e in actual_events),
               "cheap_total_cap":24,"cheap_total_charged":sum(e['kind'] in {'cheap_numeric','geometry_miss'} for e in actual_events),
               "software_fixture_cases_are_not_science":True,"wall_s":time.monotonic()-started,
               "PYTHONDONTWRITEBYTECODE":os.environ.get('PYTHONDONTWRITEBYTECODE')}
    with output.open('x') as stream:json.dump(receipt,stream,ensure_ascii=False,indent=2);stream.write('\n')
    with (ROOT/'direct-prefix-generations.json.gz').open('xb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as stream:
            stream.write(json.dumps(actual_artifacts,ensure_ascii=False,separators=(',',':')).encode())
    print(json.dumps({"software_cases":len(cases),"PASS":receipt['PASS'],"FAIL":receipt['FAIL'],
                      "cases":[{k:x[k] for k in ['name','status','error'] if k in x} for x in cases],
                      "actual_meter_event_count":len(actual_events)},ensure_ascii=False))
    if receipt['FAIL']:raise SystemExit(1)


if __name__=='__main__':run()
