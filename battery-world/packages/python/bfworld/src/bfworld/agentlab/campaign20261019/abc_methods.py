"""ABC-C: a bounded O time-semantics consumer and a generic H interpreter.

The developer defines task mechanisms and independent truth, never the learned
relation. Old O power/service contracts are unchanged. This additive component
task assumes continuous power and an available link; it cannot qualify an O or
A/R product. No SDK, subprocess, network, eval or native-solver entry exists.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import binascii

from . import ar

SCHEMA = "bf-abc-o-time-v1"
DESIGN = "bf-abc-o-time-design-v1"
METHOD = "bf-abc-o-time-method-v1"
ARMS = ("H0", "H0-history", "ordinary", "proposed")
VARIABLES = {"sample_period_s", "sample_phase_s", "confirmation_s", "quantum_s",
             "tolerance_s", "definition_delay_s", "stamp_offset_s", "link_delay_s",
             "delivery_deadline_s", "clock_error_bound_s", "timestamp_origin",
             "event_definition"}
OPS = {"add", "sub", "mul", "div", "ceil", "floor", "abs", "min", "max",
       "le", "lt", "ge", "gt", "eq", "and", "or", "not", "if"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(value) + b"\n"
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("IMMUTABLE_OUTPUT_EXISTS:" + path.name)
    else:
        with path.open("xb") as stream:
            stream.write(raw)
    return value


def load(path):
    return json.loads(Path(path).read_text())


def _int(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError("INTEGER_DOMAIN:" + name)
    return value


def make_task(task_id):
    """Host-only predeclared splits. Formation has no access to this registry."""
    settings = {
        "C-validation": (1350000, 4600000, 2200000, 3400000, 10000, 210000, "qualified", 180),
        "C-first": (2170000, 5870000, 1850000, 2650000, 100000, 190000, "qualified", -400),
        "C-phase": (2430000, 6970000, 3000000, 4000000, 20000, 130000, "qualified", 150),
        "C-confirm": (1870000, 6530000, 1370000, 2830000, 80000, 180000, "qualified", -250),
        "C-definition": (3210000, 8430000, 1900000, 3100000, 200000, 160000, "onset", 300),
    }
    if task_id not in settings:
        raise ValueError("UNREGISTERED_C_TASK")
    onset, low, on_confirm, off_confirm, quantum, tolerance, definition, ppm = settings[task_id]
    end = low + off_confirm + 4000000
    task = dict(schema_version=SCHEMA, task_id=task_id, split="validation" if task_id=="C-validation" else "first" if task_id=="C-first" else "formal",
        duration_us=end, waveform=[dict(start_us=0,end_us=onset,rms_g=.005),
          dict(start_us=onset,end_us=low,rms_g=.08),dict(start_us=low,end_us=end,rms_g=.005)],
        thresholds_g=dict(start=.05,stop=.01),confirmation_us=dict(start=on_confirm,stop=off_confirm),
        timestamp_quantum_us=quantum,timestamp_error_tolerance_us=tolerance,
        event_definition=definition,clock_ppm=ppm,link_delay_us=70000,
        receive_deadline_us=6500000,match_window_us=6500000,
        timestamp_rounding="nearest grid point, half upwards; then existing millisecond AR frame",
        clock_basis="Synchronized at t=0; signed constant ppm affects reported time only.",
        scope="Ideal continuously powered O time-semantics component; no energy, RF, keepalive or hardware acceptance.")
    validate_task(task)
    return task


def validate_task(task):
    if task.get("schema_version") != SCHEMA or task.get("event_definition") not in ("qualified","onset"):
        raise ValueError("TASK_SCHEMA_OR_EVENT_DEFINITION")
    horizon = _int(task["duration_us"],1,200000000,"duration_us")
    cursor = 0
    for row in task["waveform"]:
        if set(row)!={"start_us","end_us","rms_g"} or row["start_us"]!=cursor:
            raise ValueError("WAVEFORM_COVERAGE")
        cursor = _int(row["end_us"],cursor+1,horizon,"segment_end")
        if type(row["rms_g"]) not in (int,float) or not math.isfinite(row["rms_g"]) or row["rms_g"]<0:
            raise ValueError("WAVEFORM_RMS")
    if cursor!=horizon or task["thresholds_g"]!={"start":.05,"stop":.01}:
        raise ValueError("WAVEFORM_OR_THRESHOLD_DOMAIN")
    for kind in ("start","stop"):
        _int(task["confirmation_us"][kind],1000,60000000,"confirmation")
    for key in ("timestamp_quantum_us","timestamp_error_tolerance_us","receive_deadline_us","match_window_us"):
        _int(task[key],1000,60000000,key)
    if task["timestamp_quantum_us"]%1000:
        raise ValueError("QUANTUM_REQUIRES_WIRE_MILLISECONDS")
    _int(task["clock_ppm"],-10000,10000,"clock_ppm")
    _int(task["link_delay_us"],0,1000000,"link_delay_us")


def candidate_schema():
    properties = dict(schema_version={"const":DESIGN},sample_period_us={"type":"integer","minimum":20000,"maximum":2000000},
        sample_phase_us={"type":"integer","minimum":0,"maximum":1999999},
        timestamp_origin={"enum":["detected","first_sample","bracket_midpoint"]},
        timestamp_offset_us={"type":"integer","minimum":-60000000,"maximum":60000000})
    return dict(type="object",additionalProperties=False,required=list(properties),properties=properties)


def validate_candidate(candidate):
    if not isinstance(candidate,dict) or set(candidate)!=set(candidate_schema()["required"]) or candidate.get("schema_version")!=DESIGN:
        raise ValueError("DESIGN_KEYS_OR_SCHEMA")
    _int(candidate["sample_period_us"],20000,2000000,"sample_period_us")
    _int(candidate["sample_phase_us"],0,candidate["sample_period_us"]-1,"sample_phase_us")
    _int(candidate["timestamp_offset_us"],-60000000,60000000,"timestamp_offset_us")
    if candidate["timestamp_origin"] not in ("detected","first_sample","bracket_midpoint"):
        raise ValueError("TIMESTAMP_ORIGIN")
    return copy.deepcopy(candidate)


def execute(task, candidate):
    """Sample-and-hold poll program; never reads reference events/verdicts.

    At each poll, first confirm the previously held high/low observation if its
    elapsed duration reaches the task duration, then apply the new RMS sample.
    A generated record has detection time, observation-origin time, reported
    clock time and actual arrival time. The stamp origin/offset are design
    variables; quantization, clock law and true event definition are fixed.
    """
    validate_task(task)
    d = validate_candidate(candidate)
    period, phase = d["sample_period_us"],d["sample_phase_us"]
    active, since, prior = False,None,None
    records, runs = [],[]
    for t in range(phase,task["duration_us"],period):
        if since is not None:
            kind = "stop" if active else "start"
            if t-since>=task["confirmation_us"][kind]:
                origin = t if d["timestamp_origin"]=="detected" else since if d["timestamp_origin"]=="first_sample" else since-period/2
                unclocked = origin+d["timestamp_offset_us"]
                clocked = unclocked*(1000000+task["clock_ppm"])/1000000
                q = task["timestamp_quantum_us"]
                stamp = math.floor(clocked/q+.5)*q
                seq = len(records)+1
                raw = ar.frame(dict(seq=seq,kind=3 if kind=="start" else 4,temperature_c=int(not active),
                    time_interval_s=[stamp/1e6,stamp/1e6],time_known=True),1)
                records.append(dict(seq=seq,kind=kind,detected_us=t,first_sample_us=since,
                    last_opposite_sample_us=since-period if since>=phase+period else None,
                    chosen_origin_us=origin,unclocked_stamp_us=unclocked,stamp_us=stamp,
                    receive_us=t+task["link_delay_us"],hex=raw.hex()))
                active, since = not active,None
        measured = next(row["rms_g"] for row in task["waveform"] if row["start_us"]<=t<row["end_us"])
        condition = measured<task["thresholds_g"]["stop"] if active else measured>task["thresholds_g"]["start"]
        since = (t if since is None else since) if condition else None
        if runs and prior==measured:
            runs[-1].update(last_us=t,count=runs[-1]["count"]+1)
        else:
            runs.append(dict(first_us=t,last_us=t,count=1,period_us=period,rms_g=measured))
        prior=measured
    response = dict(schema_version="bf-abc-o-time-response-v1",task_sha256=digest(task),candidate=d,
        candidate_sha256=digest(d),engine_sha256=file_hash(__file__),wire_encoder_sha256=file_hash(ar.__file__),
        sample_runs=runs,sample_count=sum(r["count"] for r in runs),records=records,
        status="COMPLETE",physical_qualification="NOT_CALIBRATED")
    response["response_sha256"]=digest(response)
    return response


def reference_events(task):
    """Independent continuous-interval truth, without the producer poll loop."""
    validate_task(task)
    events=[]
    state=False
    onset=None
    for segment in task["waveform"]:
        kind="stop" if state else "start"
        satisfied=segment["rms_g"]<.01 if state else segment["rms_g"]>.05
        if not satisfied:
            onset=None
            continue
        onset=segment["start_us"] if onset is None else onset
        qualified=onset+task["confirmation_us"][kind]
        if qualified<=segment["end_us"]:
            events.append(dict(kind=kind,onset_us=onset,qualified_us=qualified,
                true_event_us=qualified if task["event_definition"]=="qualified" else onset))
            state, onset = not state,None
    return events


def assess(task, response):
    """Host-only evaluation. Event matching, arrival and stamp errors are separate."""
    errors=[]
    expected=reference_events(task)
    if (response.get("task_sha256")!=digest(task) or response.get("candidate_sha256")!=digest(response.get("candidate"))
            or response.get("engine_sha256")!=file_hash(__file__) or response.get("wire_encoder_sha256")!=file_hash(ar.__file__)
            or response.get("response_sha256")!=digest({k:v for k,v in response.items() if k!="response_sha256"})):
        return dict(status="FAIL",reasons=["RESPONSE_BINDING"],physical_qualification="NOT_CALIBRATED")
    validate_candidate(response["candidate"])
    actual=response["records"]
    if len(actual)!=len(expected):
        errors.append("EVENT_COUNT")
    per_event=[]
    for index,event in enumerate(expected):
        rec=actual[index] if index<len(actual) else None
        row={**event,"matched":False,"arrival_timely":False,"timestamp_accurate":False}
        if rec is not None:
            wire=bytes.fromhex(rec["hex"])
            valid=len(wire)==22 and binascii.crc_hqx(wire[:-2],65535)==int.from_bytes(wire[-2:],"big")
            decoded=struct.unpack(">IIiihBB",wire[:-2]) if valid else None
            valid=bool(decoded and decoded[0]==1 and decoded[1]==index+1 and decoded[4]==(100 if event["kind"]=="start" else 0)
                       and decoded[5]==(3 if event["kind"]=="start" else 4) and decoded[6]==1 and decoded[2]==decoded[3])
            stamp=decoded[2]*1000 if valid else None
            match=rec["kind"]==event["kind"] and abs(rec["detected_us"]-event["qualified_us"])<=task["match_window_us"]
            arrival=event["qualified_us"]<=rec["receive_us"]<=event["qualified_us"]+task["receive_deadline_us"]
            stamp_ok=valid and abs(stamp-event["true_event_us"])<=task["timestamp_error_tolerance_us"]
            row.update(matched=match,arrival_timely=arrival,timestamp_accurate=stamp_ok,
                detected_us=rec["detected_us"],receive_us=rec["receive_us"],decoded_stamp_us=stamp,
                signed_timestamp_error_us=None if stamp is None else stamp-event["true_event_us"])
        if not row["matched"]:errors.append("MISSING_OR_FALSE_EVENT")
        if not row["arrival_timely"]:errors.append("LATE_OR_NONCAUSAL_RECEIVE")
        if not row["timestamp_accurate"]:errors.append("WRONG_EVENT_TIME")
        per_event.append(row)
    return dict(schema_version="bf-abc-o-time-assessment-v1",status="FAIL" if errors else "PASS",
        event_matching="PASS" if all(r["matched"] for r in per_event) and len(actual)==len(expected) else "FAIL",
        timely_receive="PASS" if all(r["arrival_timely"] for r in per_event) else "FAIL",
        timestamp_accuracy="PASS" if all(r["timestamp_accurate"] for r in per_event) else "FAIL",
        reasons=sorted(set(errors)),per_event=per_event,task_sha256=digest(task),response_sha256=response["response_sha256"],
        physical_qualification="NOT_CALIBRATED",scope=task["scope"])


def expression(tree, values, *, depth=0, validate_only=False, seen=None):
    """Bounded arithmetic/Boolean AST, deliberately containing no time-error rule."""
    if depth>18:
        raise ValueError("EXPRESSION_DEPTH")
    if isinstance(tree,dict) and set(tree)=={"var"}:
        if tree["var"] not in VARIABLES:raise ValueError("EXPRESSION_VARIABLE")
        if seen is not None:seen.add(tree["var"])
        return 1 if validate_only else values[tree["var"]]
    if type(tree) in (int,float,bool,str):
        if isinstance(tree,(int,float)) and not math.isfinite(tree):raise ValueError("EXPRESSION_FINITE")
        if isinstance(tree,str) and tree not in ("qualified","onset","detected","first_sample","bracket_midpoint"):
            raise ValueError("EXPRESSION_STRING_LITERAL")
        return tree
    if not isinstance(tree,list) or not tree or tree[0] not in OPS:
        raise ValueError("EXPRESSION_OPERATOR")
    op=tree[0]
    arity=3 if op=="if" else 1 if op in ("ceil","floor","abs","not") else 2
    if len(tree)!=arity+1:raise ValueError("EXPRESSION_ARITY")
    args=[expression(t,values,depth=depth+1,validate_only=validate_only,seen=seen) for t in tree[1:]]
    if validate_only:return 1
    if op=="if":return args[1] if args[0] else args[2]
    if op=="and":return bool(args[0] and args[1])
    if op=="or":return bool(args[0] or args[1])
    if op=="not":return not args[0]
    if op=="eq":return args[0]==args[1]
    if op in ("le","lt","ge","gt"):
        return {"le":lambda a,b:a<=b,"lt":lambda a,b:a<b,"ge":lambda a,b:a>=b,"gt":lambda a,b:a>b}[op](*args)
    if any(type(a) not in (int,float) for a in args):raise ValueError("EXPRESSION_NUMBER_TYPE")
    return {"add":lambda a,b:a+b,"sub":lambda a,b:a-b,"mul":lambda a,b:a*b,"div":lambda a,b:a/b,
        "ceil":math.ceil,"floor":math.floor,"abs":abs,"min":min,"max":max}[op](*args)


def validate_method(proposal):
    required={"schema_version","hypothesis","falsifier","method_text","checks"}
    if not isinstance(proposal,dict) or set(proposal)!=required or proposal["schema_version"]!=METHOD:
        raise ValueError("METHOD_SCHEMA")
    for key in ("hypothesis","falsifier","method_text"):
        if not isinstance(proposal[key],str) or not 1<=len(proposal[key])<=12000:raise ValueError("METHOD_TEXT_DOMAIN")
    if not isinstance(proposal["checks"],list) or len(proposal["checks"])>8:raise ValueError("METHOD_CHECK_COUNT")
    if len(canonical(proposal))>32000:raise ValueError("METHOD_SIZE")
    seen=set()
    for check in proposal["checks"]:
        if set(check)!={"name","relation"} or not isinstance(check["name"],str) or not 1<=len(check["name"])<=120:
            raise ValueError("METHOD_CHECK_KEYS")
        expression(check["relation"],{},validate_only=True,seen=seen)
    coverage={name:name in seen for name in ("sample_period_s","confirmation_s","quantum_s","tolerance_s")}
    coverage["event_definition"]=bool(seen & {"definition_delay_s","event_definition"})
    return dict(proposal=copy.deepcopy(proposal),variables_used=sorted(seen),mechanism_coverage=coverage,
        executable_checks=len(proposal["checks"]),semantic_validity="NOT_ESTABLISHED",author_authentication="S0_PROVIDER_RECEIPT_REQUIRED")


def run_relations(task,candidate,proposal):
    validate_method(proposal)
    d=validate_candidate(candidate)
    rows=[]
    for kind,confirmation in task["confirmation_us"].items():
        values=dict(sample_period_s=d["sample_period_us"]/1e6,sample_phase_s=d["sample_phase_us"]/1e6,
            confirmation_s=confirmation/1e6,quantum_s=task["timestamp_quantum_us"]/1e6,
            tolerance_s=task["timestamp_error_tolerance_us"]/1e6,
            definition_delay_s=confirmation/1e6 if task["event_definition"]=="qualified" else 0,
            stamp_offset_s=d["timestamp_offset_us"]/1e6,link_delay_s=task["link_delay_us"]/1e6,
            delivery_deadline_s=task["receive_deadline_us"]/1e6,
            clock_error_bound_s=abs(task["clock_ppm"])*task["duration_us"]/1e12,
            timestamp_origin=d["timestamp_origin"],event_definition=task["event_definition"])
        for check in proposal["checks"]:
            try:
                result=expression(check["relation"],values)
                if type(result) is not bool:raise ValueError("RELATION_MUST_RETURN_BOOLEAN")
                rows.append(dict(kind=kind,name=check["name"],result=result,status="EXECUTED"))
            except (ValueError,TypeError,ZeroDivisionError,OverflowError) as error:
                rows.append(dict(kind=kind,name=check["name"],result=None,status="UNKNOWN",error=type(error).__name__))
    return dict(method_sha256=digest(proposal),rows=rows,qualification_authority="NONE")


def public_law():
    return dict(program=execute.__doc__,sample_order="At poll t: confirm held interval, then apply measured RMS.",
        timestamp_origins={"detected":"current confirmation poll", "first_sample":"first qualifying sample", "bracket_midpoint":"midpoint of that sample and its preceding scheduled sample"},
        emission="After confirmation, add candidate timestamp offset, apply t*(1+clock_ppm/1e6), round to task quantum, encode existing AR milliseconds; arrival is detection plus link delay.",
        truth="Continuous threshold excursion must last confirmation_us; event time is qualification time or onset according to task. Matching uses kind/order and detection window; timestamp accuracy is separately evaluated.",
        h_interpreter=dict(variables=sorted(VARIABLES),operators=sorted(OPS),syntax="Literal or {var: name}, or [operator, operands...]. No built-in learned rule.",schema_version=METHOD,
            submission_contract=dict(required=["schema_version","hypothesis","falsifier","method_text","checks"],
                schema_version=METHOD,checks="Up to eight {name: string, relation: expression} objects; relation returns a Boolean. Empty checks are permitted and reported.",
                constants="Finite numbers, Booleans or one of qualified/onset/detected/first_sample/bracket_midpoint; no executable source strings.",
                operators="Binary: add/sub/mul/div/min/max/le/lt/ge/gt/eq/and/or; unary: ceil/floor/abs/not; ternary: if. Arguments are evaluated eagerly. Variable units in seconds unless an enum.")))


def prepare_episode(spec,episode_root):
    stage=spec["stage"]
    arm=spec["arm"]
    if stage not in ("formation","validation","first","formal") or arm not in ARMS:
        raise ValueError("STAGE_OR_ARM")
    if stage=="formation" and arm not in ("ordinary","proposed"):raise ValueError("FORMATION_ARM")
    task=None if stage=="formation" else make_task(spec["task_id"])
    if task is not None and spec.get("task_sha256",digest(task))!=digest(task):raise ValueError("TASK_CONTENT_BINDING")
    if task is not None and task["split"]!={"validation":"validation","first":"first","formal":"formal"}[stage]:
        raise ValueError("TASK_SPLIT_LEAKAGE")
    history=None
    if arm!="H0":
        if file_hash(spec["history_path"])!=spec["history_sha256"]:raise ValueError("HISTORY_BINDING")
        history=load(spec["history_path"])
    method=None
    if spec.get("method_path"):
        if file_hash(spec["method_path"])!=spec["method_sha256"]:raise ValueError("METHOD_FILE_BINDING")
        method=load(spec["method_path"])
        validate_method(method)
    if stage!="formation" and arm in ("ordinary","proposed") and method is None and not spec.get("frozen_no_update_receipt"):
        raise ValueError("MODEL_AUTHORED_METHOD_OR_EXPLICIT_NO_UPDATE_REQUIRED")
    common="Use only the assigned BF tool. Tools return facts; independently infer and report PASS/FAIL/UNKNOWN. No shell/files/network or hidden evaluator access. No changing the task. Submit at most one assigned artifact."
    forming="" if stage!="formation" else ("Reflect on the same original O history and propose one reusable H, or an unchanged H with empty checks. Optional executable checks use the same AST available to both formation arms." if arm=="ordinary" else "From the original O failures, form one transferable H with executable relationship checks involving sampling interval, confirmation duration, quantization, event-time definition and tolerance. A remembered fixed sampling value is insufficient. Do not infer any validation/final task. The developer supplies only an interpreter, no target formula.")
    payload=dict(schema_version="bf-abc-C-participant-v1",stage=stage,arm=arm,task=task,
        base_H0=spec["h0_text"],history=history,learned_H=method,formation_instruction=forming,
        common_instruction=common,public_mechanism=public_law(),candidate_schema=candidate_schema(),
        limits=dict(requests=12,wall_s=900,tools=40,distinct_designs=2,max_output_tokens=65536,automatic_retry=False))
    root=Path(episode_root)/"methods"
    saved=dict(spec=copy.deepcopy(spec),task=task,history=history,method=method,participant_input=payload,
        engine_sha256=file_hash(__file__),wire_encoder_sha256=file_hash(ar.__file__))
    seal(root/"input.json",saved)
    return dict(participant_input=payload,participant_input_sha256=digest(payload),module_input=str(root/"input.json"),
        paid_dispatch_authority="S0_ONLY",task_sha256=None if task is None else digest(task))


def tool_definition(spec):
    return dict(name="bf_abc_methods",description="Inspect assigned O time-task/history, execute a legal design, interpret a model-authored relationship, and submit the assigned D or H. Public observations contain no independent verdict or next-step advice.",
        parameters=dict(type="object",additionalProperties=False,required=["action"],properties=dict(
            action={"enum":["inspect","history","check","submit","check_relations","submit_method"]},
            candidate=candidate_schema(),proposal={"type":"object"},service_judgment={"enum":["PASS","FAIL","UNKNOWN"]},reason={"type":"string","maxLength":12000})))


def create_handler(episode_root,spec):
    root=Path(episode_root)/"methods"
    saved=load(root/"input.json")
    if saved["spec"]!=spec or saved["engine_sha256"]!=file_hash(__file__):raise ValueError("EPISODE_SOURCE_BINDING")
    def handler(body):
        action=body["action"]
        if action=="inspect":return saved["participant_input"]
        if action=="history":return dict(history=saved["history"],history_sha256=spec.get("history_sha256") if saved["history"] else None)
        if action=="submit_method":
            if spec["stage"]!="formation":raise ValueError("ASSIGNED_ARTIFACT_IS_D")
            gate=validate_method(body["proposal"])
            seal(root/"method-submission.json",body["proposal"])
            return dict(recorded="H",method_sha256=digest(body["proposal"]),structural_gate=gate,scientific_validity="UNESTABLISHED")
        if spec["stage"]=="formation":raise ValueError("NO_UNSEEN_TASK_IN_FORMATION")
        candidate=validate_candidate(body["candidate"])
        if action=="check_relations":
            return run_relations(saved["task"],candidate,body["proposal"])
        if action not in ("check","submit"):raise ValueError("UNKNOWN_ACTION")
        key=digest(dict(task=saved["task"],candidate=candidate,engine=saved["engine_sha256"]))
        target=root/"executions"/key/"response.json"
        prior=list((root/"executions").glob("*/response.json"))
        if not target.exists() and len(prior)>=2:raise ValueError("DISTINCT_DESIGN_CAP")
        reused=target.exists()
        response=load(target) if reused else seal(target,execute(saved["task"],candidate))
        relations=None if saved["method"] is None else run_relations(saved["task"],candidate,saved["method"])
        if action=="submit":
            judgment=body.get("service_judgment")
            if judgment not in ("PASS","FAIL","UNKNOWN"):raise ValueError("SERVICE_JUDGMENT_REQUIRED")
            seal(root/"submission.json",dict(candidate=candidate,execution_key=key,response_sha256=response["response_sha256"],
                service_judgment=judgment,reason=body.get("reason",""),consumed_method_sha256=None if saved["method"] is None else digest(saved["method"])))
        return dict(recorded=action,execution_key=key,observed=response,relations=relations,
            acquisition=dict(new_scientific_executions=0 if reused else 1,native_calls=0,samples=response["sample_count"]))
    return handler


def independent_check(episode_root,spec):
    root=Path(episode_root)/"methods"
    saved=load(root/"input.json")
    if saved["spec"]!=spec or saved["engine_sha256"]!=file_hash(__file__):raise ValueError("INDEPENDENT_INPUT_BINDING")
    if spec["stage"]=="formation":
        path=root/"method-submission.json"
        result=dict(status="NO_SUBMISSION",qualification_authority="NONE") if not path.exists() else dict(status="STRUCTURALLY_ADMITTED",**validate_method(load(path)))
    elif not (root/"submission.json").exists():
        result=dict(status="NO_SUBMISSION",event_matching="UNKNOWN",timely_receive="UNKNOWN",timestamp_accuracy="UNKNOWN",physical_qualification="NOT_CALIBRATED")
    else:
        submission=load(root/"submission.json")
        response=load(root/"executions"/submission["execution_key"]/"response.json")
        if response["candidate"]!=submission["candidate"] or response["response_sha256"]!=submission["response_sha256"]:
            raise ValueError("SUBMISSION_RESPONSE_BINDING")
        result=assess(saved["task"],response)
        result.update(participant_judgment=submission["service_judgment"],wrong_service_judgment=submission["service_judgment"]!=result["status"],
            consumed_method_sha256=submission["consumed_method_sha256"],submitted_candidate=submission["candidate"])
    return seal(root/"independent-result.json",result)
