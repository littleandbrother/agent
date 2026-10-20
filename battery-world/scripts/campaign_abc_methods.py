#!/usr/bin/env python3
"""Prepare the finite C packet or independently read one existing C episode.

This command cannot start SDK/Pi, install an environment or run a study.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import zlib

from bfworld.agentlab.campaign20261019 import abc_methods as c


def source(path, sources):
    path=Path(path)
    raw=path.read_bytes()
    sources[str(path.resolve())]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    return json.loads(raw)


def prepare(args):
    root=args.output.resolve()
    free=shutil.disk_usage(root.parent).free
    if free<11500000000:raise ValueError("10GB_PLUS_GLOBAL_PEAK_STORAGE_GATE")
    sources={}
    old=args.old_phase4.resolve()
    case=source(old/"host-only-inputs/p4-o-unexposed-waveform-v1.json",sources)
    episodes=[]
    for lineage in (1,2,3):
        for arm in ("H0","G0","G1"):
            eid=f"L{lineage}-{arm}-final-3"
            directory=old/"episodes"/eid
            result=source(directory/"episode-result.json",sources)
            usage=source(directory/"provider-costs.json",sources)
            submission=None
            observations=None
            path=directory/"scientific/submission.json"
            if path.exists():
                submission=source(path,sources)
                compressed=Path(submission["execution"]["raw_path"])
                raw=compressed.read_bytes()
                sources[str(compressed)]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
                decoded=json.loads(zlib.decompress(raw))
                if decoded["response_sha256"]!=submission["execution"]["response_sha256"]:
                    raise ValueError("OLD_RESPONSE_BINDING")
                observations={key:decoded[key] for key in ("candidate","sample_runs","records","packets","receiver","response_sha256")}
                observations["clock_and_reset_activity"]=[row for row in decoded["activity"] if row["action"] in ("boot","brownout","clock-sync")]
            episodes.append(dict(episode=eid,episode_result=result,provider_costs=usage,
                original_submission=submission,original_observations=observations,
                truncation_retained=result["status"]=="INCOMPLETE_OR_STOPPED"))
    history=dict(schema_version="bf-abc-C-original-history-v1",original_task=case,episodes=episodes,
        projection="Mechanical selection of all nine original O final cells; full original submissions, time-relevant raw response fields and unchanged cost/result records. No new task or authored time-error formula.",
        source_files=sources,old_censored_cells=4,old_submitted_wrong_event_time_cells=2,
        original_failures_rewritten=False)
    if sum(row["truncation_retained"] for row in episodes)!=4:raise ValueError("OLD_CENSOR_DENOMINATOR")
    failures=[row for row in episodes if row["original_submission"] and "WRONG_EVENT_TIME" in row["original_submission"]["execution"]["reasons"]]
    if len(failures)!=2:raise ValueError("OLD_FAILURE_DENOMINATOR")
    root.mkdir(parents=True,exist_ok=True)
    c.seal(root/"original-history.json",history)
    parents=source(args.s0_source/"configs/studies/phase4-20261020/methods/frozen-parents.json",sources)
    h0=parents["H0"]["method_text"]
    c.seal(root/"base-H0.json",parents["H0"])
    tasks={task_id:c.make_task(task_id) for task_id in ("C-validation","C-first","C-phase","C-confirm","C-definition")}
    for task_id,task in tasks.items():c.seal(root/"host-only-tasks"/(task_id+".json"),task)
    shared=dict(history_path=str(root/"original-history.json"),history_sha256=c.file_hash(root/"original-history.json"),h0_text=h0,
        package="methods",module="bfworld.agentlab.campaign20261019.abc_methods")
    formation=[]
    validation=[]
    for arm in ("ordinary","proposed"):
        spec={**shared,"episode_id":"C-formation-"+arm,"stage":"formation","arm":arm}
        c.seal(root/"specs"/(spec["episode_id"]+".json"),spec)
        formation.append(spec["episode_id"])
        spec={**shared,"episode_id":"C-validation-"+arm,"stage":"validation","arm":arm,"task_id":"C-validation",
              "task_sha256":c.digest(tasks["C-validation"]),"awaits_frozen_model_method":True}
        c.seal(root/"specs"/(spec["episode_id"]+".template.json"),spec)
        validation.append(spec["episode_id"])
    first={**shared,"episode_id":"C-first-proposed","stage":"first","arm":"proposed","task_id":"C-first","task_sha256":c.digest(tasks["C-first"]),"awaits_frozen_model_method":True}
    c.seal(root/"specs/C-first-proposed.template.json",first)
    formal=[]
    for repetition in (1,2):
        for task_id in ("C-phase","C-confirm","C-definition"):
            for arm in (c.ARMS if repetition==1 else tuple(reversed(c.ARMS))):
                eid=f"{task_id}-{arm}-r{repetition}"
                spec={**shared,"episode_id":eid,"stage":"formal","arm":arm,"task_id":task_id,"task_sha256":c.digest(tasks[task_id]),"repetition":repetition}
                if arm in ("ordinary","proposed"):spec["awaits_frozen_model_method"]=True
                c.seal(root/"specs"/(eid+".template.json"),spec)
                formal.append(dict(episode_id=eid,arm=arm,task_id=task_id,repetition=repetition,task_sha256=c.digest(tasks[task_id])))
    protocol=dict(schema_version="bf-abc-C-protocol-v1",dispatch_id="BF-ABC-20261020-001",feature="BFA-070-abc-method-transfer",
        status="PREPARED_NO_PAID_DISPATCH_AUTHORITY",source_baseline="b8498ee6c712dd52f060bc84abebebfd461c5fdc",
        hypothesis="A BF-authored general time-error H can change new O component-task decisions beyond equal-history controls.",
        falsifier="No gain against equal-history arms, fixed-value memory, leakage, unequal budgets, or post-result retries prevents a transfer claim.",
        formation=formation,validation=validation,first="C-first-proposed",formal=formal,formal_attempts=24,maximum_model_episodes=29,
        model_identity="S0_MUST_VERIFY_AND_FREEZE_BEFORE_PAID_ADMISSION",history_sha256=shared["history_sha256"],H0_sha256=parents["H0"]["method_sha256"],
        stage_separation="Formation sees only original history. Both validation episodes use C-validation. C-first is a distinct first-use task. The three formal task IDs are never shown during formation or validation.",
        common_episode_limits=dict(model_requests=12,wall_seconds=900,tool_calls=40,candidates=2,max_output_tokens=65536,automatic_retry=False),
        formation_limits="One H submission per arm, same tools/history/request/wall/output limits. Ordinary may use the same executable AST. No hand edit or second formation.",
        method_rule="Use each structurally valid original model H unchanged even if its independent validation fails; validity is reported, not selected by final success. Invalid/no-submission explicitly falls back to unchanged H0 and retains costs. S0 authenticates actual provider authorship and raw artifact hash before binding.",
        metrics=["event_matching","timely_receive","timestamp_accuracy","complete time-component service","wrong self-judgment","requests/tokens/cost","sample/execution acquisition","formation and validation cost","no submission/censoring"],
        denominator="All 24 named formal attempts, including failed, missing and truncated; no replacement. Formation/validation/first costs separately retained and included in total learning cost.",
        public_law=c.public_law(),learned_formula_supplied_by_developer=False,
        claim_boundary="New ideal digital timing component only, no full O energy/keepalive, A/R acceptance, hardware or stable RSI. Earlier methods yielded no extra success with more requests; all four old truncations remain.",
        storage=dict(reserve_bytes=10000000000,global_peak_bytes=1500000000,worker_cap_bytes=180000000,preparation_estimate_bytes=10000000,available_before_bytes=free),
        source_bindings={str(Path(c.__file__).resolve()):c.file_hash(c.__file__),str(Path(c.ar.__file__).resolve()):c.file_hash(c.ar.__file__)},
        task_hashes={key:c.digest(value) for key,value in tasks.items()},paid_dispatch_owner="S0",new_paid_requests_here=0)
    c.seal(root/"protocol.json",protocol)
    c.seal(root/"source-dependencies.json",sources)
    print(json.dumps(dict(status="PREPARED",history_bytes=(root/"original-history.json").stat().st_size,formal_attempts=24,
        first_task="C-first",learned_H="NOT_YET_FORMED",new_paid_requests=0,new_study_executions=0)))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest="action",required=True)
    p=sub.add_parser("prepare")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--old-phase4",type=Path,required=True)
    p.add_argument("--s0-source",type=Path,required=True)
    p=sub.add_parser("check-existing")
    p.add_argument("--spec",type=Path,required=True)
    p.add_argument("--episode-root",type=Path,required=True)
    args=ap.parse_args()
    if args.action=="prepare":prepare(args)
    else:print(json.dumps(c.independent_check(args.episode_root,c.load(args.spec))))


if __name__=="__main__":main()
