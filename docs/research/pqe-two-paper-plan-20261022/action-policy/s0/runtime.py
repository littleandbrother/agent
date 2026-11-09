"""Bounded host increment; original science, transport and isolated worker reused."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import ast
import importlib.util
import inspect
import time

HERE = Path(__file__).resolve().parent
OUT, BASE = HERE.parent, HERE.parent.parent
spec = importlib.util.spec_from_file_location("sealed_training_host", BASE/"training-execution/s0/runtime.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
lc, p, host, legacy = prior.old, prior.p, prior.host, prior.legacy
ROOT, APP = prior.ROOT, prior.APP
PKG = APP/"packages/python/bfworld/src/bfworld/agentlab/pqe20261024policy"
PACKAGE = "BF-PQE-ACTION-POLICY-20261024-001"
PROTOCOL = OUT/"shared/protocol.json"
read, save, bind, checked, identity, now = prior.read, prior.save, prior.bind, prior.checked, prior.identity, prior.now
task, lc_context, sources, cache_key, adapter = prior.task, prior.lc_context, prior.sources, prior.cache_key, prior.adapter
SOLVE = dict(model_requests=12, tool_calls=24, numerical_inputs=3, candidates=3,
    wall_s=900, output_tokens=65536, generated_tokens=131072, usd=5, bytes=70000000)
FORMATION = dict(model_requests=30, tool_calls=60, numerical_inputs=8, candidates=8,
    wall_s=2400, output_tokens=65536, generated_tokens=393216, usd=15, bytes=120000000)
TOTAL = dict(requests=228, tool_calls=456, numerical_inputs=60, full_wall_s=7200, usd=100, retained_bytes=200000000)
PLAN = [("dev1", "development", "H1"), ("dev2", "development", "H1"),
        ("form-h2", "formation", "H2"), ("form-h4", "formation", "H4")]
PLAN += [(f"t{i}-{c.lower()}", f"t{i}", c) for i in range(1,5) for c in ("H1","H2","H4")]
_base_configure, _base_scope = prior._configure, lc.runtime_scope
validate, execute_child = lc.validate, lc.execute_child


def capacity():
    stat = lc.os.statvfs(ROOT)
    free = stat.f_bavail*stat.f_frsize
    files = [x.stat() for x in OUT.rglob("*") if x.is_file()]
    logical, allocated = sum(x.st_size for x in files), sum(max(4096,x.st_blocks*512) for x in files)
    if free < 11200000000 or allocated >= TOTAL["retained_bytes"]:
        raise ValueError("ACTION_POLICY_STORAGE_CAP")
    return dict(at=now(), available_bytes=free, retained_logical_bytes=logical,
        retained_allocated_upper_bound_bytes=allocated, retained_cap_metric="allocated_upper_bound",
        reclaimed_bytes=0, new_backups_environments_worktrees=0)


def configure(protocol, formation=False):
    return _base_configure(protocol, formation)


for module in (prior, lc):
    for name in ("HERE","OUT","BASE","PKG","PACKAGE","PROTOCOL","SOLVE","FORMATION","TOTAL","PLAN","capacity","configure"):
        setattr(module, name, globals()[name])


def _original_transport_with_package_caps():
    """Parameterize only the sealed host's two literal resource ceilings in memory.

    No consumer or cycle source is copied or changed. The two AST locations and
    expected old literals are checked exactly; all other original AST is reused.
    """
    source = inspect.getsource(prior._full)
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops)!=1 or not isinstance(node.ops[0], ast.GtE):
            continue
        left = node.left
        if not (isinstance(left, ast.Subscript) and isinstance(left.value,ast.Name) and left.value.id=="ledger"
                and isinstance(left.slice,ast.Constant) and isinstance(node.comparators[0],ast.Constant)):
            continue
        key, old_value = left.slice.value, node.comparators[0].value
        replacements = {"full_dynamic_inputs":(50,60), "full_dynamic_wall_s":(5880,7080)}
        if key in replacements:
            expected,new_value = replacements[key]
            if old_value!=expected:
                raise ValueError("SEALED_TRANSPORT_CAP_LOCATION_CHANGED")
            node.comparators[0].value=new_value
            found.append(dict(ledger_key=key, old=expected, new=new_value))
    if len(found)!=2:
        raise ValueError("SEALED_TRANSPORT_TWO_CAPS_REQUIRED")
    namespace = lc.__dict__.copy()
    namespace.update(HERE=HERE,OUT=OUT,PACKAGE=PACKAGE,capacity=capacity)
    def compact_if_idle(folder):
        try:
            lc.compact_completed(folder)
        except ValueError as exc:
            if str(exc)!="COMPLETED_OUTPUT_OPEN_OR_HANDLE_CHECK_FAILED":
                raise
            # An open-file check only prevents optional compression. Preserve
            # the already verified original output, with no retry or copy.
            path=HERE/"compaction-skipped.jsonl"
            with path.open("a") as stream:
                stream.write(lc.json.dumps(dict(at=now(),folder=str(folder),status="PRESERVED_UNCOMPRESSED",
                    reason=str(exc),scientific_rerun=False,backup_created=False))+"\n")
    namespace["compact_completed"]=compact_if_idle
    exec(compile(ast.fix_missing_locations(tree), str(Path(prior._full.__code__.co_filename))+":resource-caps-only", "exec"), namespace)
    return namespace["full_execute"], found


_transport, TRANSPORT_CAP_INCREMENT = _original_transport_with_package_caps()


def full_execute(entry,state,decision,folder,cache,category):
    return _transport(entry,state,decision,folder,cache,category)


lc.full_execute = prior.full_execute = full_execute
lc.capacity = prior.capacity = capacity


@contextmanager
def runtime_scope():
    with _base_scope():
        opened = read(HERE/"runtime-open.json")
        opened.update(study_usd=100,owners_max=16, package=PACKAGE)
        save(HERE/"runtime-open.json",opened)
        yield


class PolicyEpisode(prior.LCEpisode):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.training_slots_remaining=4
        self.revision_pending=True

    def ready(self,paid=False):
        if self.fatal:
            raise ValueError(self.fatal)
        budget=self.budget()
        capacity()
        allocated=sum(max(4096,x.stat().st_blocks*512) for x in self.root.rglob("*") if x.is_file())
        if budget["wall_s"]>=self.limits["wall_s"] or allocated>=self.limits["bytes"]:
            raise ValueError("POLICY_EPISODE_WALL_OR_STORAGE_CAP")
        with p.dbconnect() as db:
            if lc.new_batch_usage_blockers(db,self.owner):
                self.fatal="NEW_USAGE_UNKNOWN_STOP"
                raise ValueError(self.fatal)
            rows=db.execute("SELECT mr.charged FROM model_requests mr JOIN research_model_owners ro ON ro.owner=mr.owner WHERE ro.protocol=?",(PACKAGE,)).fetchall()
        if self.tools>self.limits["tool_calls"]:
            raise ValueError("POLICY_EPISODE_TOOL_CAP")
        if paid and (budget["model_requests"]>=self.limits["model_requests"] or budget["output_tokens"]>=self.limits["generated_tokens"]
                or budget["spent_usd"]+.19>self.limits["usd"] or len(rows)>=228 or sum(x[0] or 0 for x in rows)+.19>100):
            raise ValueError("POLICY_FINITE_MODEL_CAP")
        if self.subscope is not None:
            remaining=self._remaining(budget)
            if remaining["wall_s_remaining"]<=0:
                raise ValueError("NESTED_SOLVE_ABSOLUTE_DEADLINE")
            if paid and (remaining["provider_requests_remaining"]<=0 or remaining["output_tokens_remaining"]<=0
                    or remaining["reserve_usd_remaining"]<.19):
                raise ValueError("NESTED_SOLVE_FINITE_MODEL_CAP")
        return budget

    @contextmanager
    def nested_solve(self,task_id,actions_max):
        if self.subscope is not None:
            raise ValueError("NESTED_RECURSION_NOT_AUTHORIZED")
        before=self.snapshot()
        formation=self.role=="formation"
        reserve=dict(requests=1,tools=1,usd=.19,output=65536,wall=120) if formation and self.revision_pending else dict(requests=0,tools=0,usd=0,output=0,wall=0)
        slots=max(1,self.training_slots_remaining) if formation else 1
        limits=dict(provider_requests=int(min(12,(before["provider_requests_remaining"]-reserve["requests"])/slots)),
            tool_calls=int(min(24,(before["tool_calls_remaining"]-reserve["tools"])/slots)),
            new_numerical_inputs=int(min(actions_max,before["new_numerical_inputs_remaining"])),
            wall_s=min(900,(before["wall_s_remaining"]-reserve["wall"])/slots),
            output_tokens_per_request=65536,
            output_tokens_total=int(min(131072,(before["output_tokens_remaining"]-reserve["output"])/slots)),
            reserve_usd=min(5,(before["reserve_usd_remaining"]-reserve["usd"])/slots))
        if any(x<=0 for x in limits.values()) or limits["reserve_usd"]<.19:
            raise ValueError("NESTED_FAIR_ALLOCATION_UNAVAILABLE")
        limits["output_tokens_per_request"]=min(65536,limits["output_tokens_total"])
        self.subscope=dict(task_id=task_id,started=time.monotonic(),base=self.budget(),base_tools=self.tools,
            base_numerical=self.numerical,limits=limits)
        receipt=dict(task_id=task_id,owner=self.owner,parent_absolute_deadline=self.absolute_deadline,
            before=before,limits=deepcopy(limits),remaining_training_slots=slots,
            revision_opportunity_reserved=reserve,same_owner_and_ledger=True)
        try:
            yield limits
        finally:
            receipt["subsolve_remaining_after"]=self._remaining(self.budget())
            self.subscope=None
            if formation:
                self.training_slots_remaining=max(0,self.training_slots_remaining-1)
            receipt["parent_remaining_after"]=self.snapshot()
            self.nested_solves.append(receipt)
            self.audit(self.root/"nested-solve-budgets.json",self.nested_solves)

    def resolve_frozen_task(self,task_id):
        if task_id!=self.task["task_id"]:
            raise ValueError("CURRENT_ROLE_TASK_ONLY")
        return deepcopy(self.task)

    def planner(self,request):
        try:
            validate(self.protocol)
        except Exception as exc:
            self.fatal="FROZEN_VALIDATION_STOP:"+str(exc)
            raise
        context,usage,ids,calls=deepcopy(request),dict(cost=0,input_tokens=0,output_tokens=0),[],[]
        cap=request["max_output_tokens"]
        while True:
            remaining=min(cap-usage["output_tokens"],self.snapshot()["output_tokens_remaining"])
            if remaining<=0:
                response=dict(payload={"status":"OUTPUT_TOKEN_BUDGET_EXHAUSTED"},provider_status="COMPLETE")
                break
            fields=dict(shared_public_tools=deepcopy(legacy.SERVICE_TOOLS),shared_public_catalog=self.public_catalog)
            try:
                body=self.objects.project_final({**context,"max_output_tokens":min(remaining,65536)},fields)
                if len(p.encoded(p.callback_payload(body,body["max_output_tokens"])))>240000:
                    raise ValueError("LOCAL_PUBLIC_PAYLOAD_CAP_PRE_FORWARD")
            except Exception as exc:
                save(self.root/"local-planner-error.json",dict(error=str(exc),classification="LOCAL_TOOL_NOT_EXECUTED",
                    trusted_pre_forward=True,new_unsettled_provider_rows=0,known_prior_request_ids=ids))
                return dict(payload={"status":"TOOL_ERROR"},provider_status="LOCAL_TOOL_NOT_EXECUTED",error=str(exc),
                    usage=dict(status="KNOWN" if ids else "NOT_DISPATCHED",model_identity=p.MODEL_IDENTITY,**usage),request_ids=ids)
            if self.role=="formation" and ids:
                self.driver._consume_unit("PUBLIC_TOOL_CONTINUATION_CALLBACK")
            response=self.paid_callback(body)
            new_usage=response.get("usage",{})
            if new_usage.get("status")!="KNOWN":
                return response
            for key in usage:
                usage[key]+=new_usage[key]
            ids+=response.get("request_ids",[])
            payload=response.get("payload",{})
            if response.get("provider_status")!="COMPLETE" or payload.get("status")!="PUBLIC_TOOLS":
                break
            requests=payload.get("tool_calls")
            if not isinstance(requests,list) or not 1<=len(requests)<=self.snapshot()["tool_calls_remaining"]:
                response["payload"]={"status":"INVALID_PUBLIC_TOOL_REQUEST"}
                break
            results=[]
            for call in requests:
                if self.role=="formation":
                    self.driver._consume_unit("PUBLIC_TOOL_REQUEST",name=call.get("name"))
                if call.get("name")=="public_object":
                    try:
                        result=dict(id=call.get("id"),status="OK",result=self.public_read(call.get("arguments",{})))
                    except Exception as exc:
                        result=dict(id=call.get("id"),status="TOOL_ERROR",error=str(exc))
                elif self.current_solver is not None:
                    cheap=call.get("name") in {"predict_candidate","engineering_relations"}
                    resource=read(HERE/"resource-ledger.json")
                    if cheap:
                        if self.cheap_calls>=12 or resource["cheap_checks"]+resource["cheap_screen_reserved"]>=120:
                            raise ValueError("FINITE_CHEAP_CAP")
                        self.cheap_calls+=1
                        resource["cheap_checks"]+=1
                        save(HERE/"resource-ledger.json",resource)
                    self.public_tools._budget(dict(analytic_scores_left=12-self.cheap_calls+int(cheap),
                        public_tool_calls_left=self.snapshot()["tool_calls_remaining"]))
                    result=self.public_tools._tool(self.current_solver.state,call)
                else:
                    result=dict(id=call.get("id"),status="TOOL_ERROR",error="Formation public paging only; counted host callback performs complete science.")
                self.tools+=1
                results.append(result)
            calls.append(dict(requests=requests,results=results))
            save(self.root/"public-tool-log.json",calls)
            context={**request,"public_tool_results":calls}
        response["usage"]=dict(status="KNOWN",model_identity=p.MODEL_IDENTITY,**usage,request_ids=ids)
        response["request_ids"]=ids
        return response


LCEpisode=PolicyEpisode
