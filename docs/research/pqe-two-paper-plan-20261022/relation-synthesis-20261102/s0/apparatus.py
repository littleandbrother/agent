"""Shared original DOOR/LC consumers; logical slots and new execution separate."""
import importlib.util
import signal
from common import *
from bfworld.agentlab.pqe20261024debt import adapter as door
from bfworld.agentlab.pqe20261024debt import task as door_task
from bfworld.agentlab.pqe20261023bold import lc_adapter

_spec = importlib.util.spec_from_file_location('relation_public_bridge',
    BASE / 'partial-ancestor-validation/s0/public_bridge.py')
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


def is_lc(task):
    return task.get('world_kind') == 'LC-PV' or 'area_cm2' in task['initial_design']


def condition_id(task):
    return task.get('condition_id', task['task_id'])


def action_for(task, design):
    actual = dict(operation='edit', design_patch={k: deepcopy(v) for k, v in design.items()
                  if task['initial_design'].get(k) != v},
                  problem_patch=dict(active_variables=list(task['design_domain'])))
    if not is_lc(task):
        actual['dt_s'] = task['integration']['dt_s']
    return dict(actual_input=actual)


def public_copy(value, task):
    return bridge.public_copy(value) if is_lc(task) else bridge.project(value)


class Apparatus:
    def __init__(self, *, resume=False):
        self.path = HERE / 'science-resource-ledger.json'
        if self.path.exists() and not resume:
            raise RuntimeError('EXISTING_LEDGER_NO_AUTOMATIC_RERUN')
        self.ledger = load(self.path) if self.path.exists() else dict(
            full_attempts=0, full_wall_s=0., cheap_numeric=0, static_hits=0,
            logical_inputs=0, cache_reuses=0, rows=[], prechecks=[], external_stage1=None)
        self.cache = {}
        self.original_static = door_task.static_geometry_facts
        door_task.static_geometry_facts = self.static_geometry
        for row in self.ledger['rows']:
            if row.get('status') == 'COMPLETE':
                self.cache[row['cache_key']] = dict(path=row['public_path'], origin='THIS_PACKAGE_EXACT')
        self.persist()

    def persist(self):
        save(self.path, self.ledger)

    def static_geometry(self, mechanism):
        from bfworld.agentlab.pqe20261022 import door_model
        f = door_model.source_step
        key = (f, getattr(f, '__code__', None), json.dumps(dict(mechanism=mechanism,
            defaults=door_model.DEFAULT_MECHANISM, domain=door_model.DOMAIN),
            sort_keys=True, separators=(',', ':'), allow_nan=False))
        if key in door_task._STATIC_GEOMETRY_CACHE:
            self.ledger['static_hits'] += 1
        else:
            if self.ledger['cheap_numeric'] >= 48:
                raise RuntimeError('S0_CHEAP_NUMERIC_CAP')
            self.ledger['cheap_numeric'] += 1
        try:
            return self.original_static(mechanism)
        finally:
            self.persist()

    def ready(self):
        ready()
        protocol = OUT / 'shared/protocol.json'
        if protocol.exists():
            frozen=load(protocol)
            require_sources(frozen)
            if 'consumer_sources' in frozen and (frozen['consumer_sources']['DOOR'] != door.source_identity()
                    or frozen['consumer_sources']['LC'] != lc_adapter.source_identity()):
                raise RuntimeError('FROZEN_SCIENTIFIC_CONSUMER_SOURCE_CHANGED')
        external = self.ledger['external_stage1'] or dict(full_attempts=6, full_wall_s=0.)
        if self.ledger['full_attempts'] + external['full_attempts'] >= 240:
            raise RuntimeError('GLOBAL_FULL_INPUT_CAP')
        if self.ledger['full_wall_s'] + external['full_wall_s'] >= 3600:
            raise RuntimeError('GLOBAL_FULL_WALL_CAP')

    @staticmethod
    def sources(task):
        return lc_adapter.source_identity() if is_lc(task) else door.source_identity()

    def key(self, task, design, context=None):
        return digest(dict(task=task, design=design, sources=self.sources(task),
                           lc_context=context if is_lc(task) else None))

    def admit(self, task, design, path, *, origin, context=None):
        value = load(path)
        if value['task_id'] != task['task_id'] or value['design'] != design:
            raise RuntimeError('EXACT_CACHE_INPUT_MISMATCH:' + str(path))
        decision_path = Path(path).parent / 'decision.json'
        receipt = load(decision_path)
        if receipt['task_sha256'] != digest(task) or receipt['sources'] != self.sources(task):
            raise RuntimeError('EXACT_CACHE_TASK_OR_SOURCE_MISMATCH:' + str(path))
        self.cache[self.key(task, design, context)] = dict(path=str(path), origin=origin)

    def validate(self, task, design):
        # One common validator for G/D/R and both relation ablation cells.
        if is_lc(task):
            lc_adapter.validate_design(task, design)
        else:
            door.prepare(task, task['initial_design'], task['initial_problem'],
                         action_for(task, design), task_resolver=lambda _: task)

    def member(self, task, design, *, group, slot, phase, context=None):
        self.ready()
        self.ledger['logical_inputs'] += 1
        key = self.key(task, design, context)
        if key in self.cache:
            saved = self.cache[key]
            value = load(saved['path'])
            self.ledger['cache_reuses'] += 1
            journal(HERE / 'logical-inputs.jsonl', dict(group=group, slot=slot, phase=phase,
                condition_id=condition_id(task), cache_key=key, reused=True,
                source=ref(saved['path']), new_full_wall_s=0.))
            self.persist()
            value.update(condition_id=condition_id(task), reused=True,
                         new_full_wall_s=0., canonical_public_path=saved['path'],
                         cache_origin=saved['origin'])
            return public_copy(value, task)
        phase_cap = dict(stage2=12, initial=6, comparison=216)[phase]
        if sum(r['phase'] == phase for r in self.ledger['rows']) >= phase_cap:
            raise RuntimeError('STAGE_ALLOCATION_CAP:' + phase)
        index = self.ledger['full_attempts'] + 1
        folder = HERE / 'science' / f'{index:03d}'
        folder.mkdir(parents=True, exist_ok=False)
        decision = action_for(task, design)
        save(folder / 'input.json', dict(task=task, design=design, decision=decision,
             group=group, slot=slot, phase=phase,
             lc_context_binding=digest(context) if context is not None else None))
        external = self.ledger['external_stage1'] or dict(full_attempts=6, full_wall_s=0.)
        timeout = min(120., 3600 - external['full_wall_s'] - self.ledger['full_wall_s'],
                      load(HERE / 'preflight.json')['absolute_deadline_epoch'] - time.time())
        row = dict(index=index, group=group, slot=slot, phase=phase, task_id=task['task_id'],
            condition_id=condition_id(task), design_sha256=digest(design), cache_key=key,
            path=str(folder), status='STARTED', reused=False)
        self.ledger['full_attempts'] += 1
        self.ledger['rows'].append(row)
        self.persist()
        started = time.monotonic()
        prior_signal = signal.getsignal(signal.SIGALRM)
        def expire(*_):
            raise TimeoutError('FULL_120S_OR_PACKAGE_REMAINING_WALL')
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, max(.001, timeout))
        try:
            kwargs = dict(task_resolver=lambda ident: task if ident == task['task_id'] else None)
            if is_lc(task):
                value = lc_adapter.execute(task, task['initial_design'], task['initial_problem'],
                    decision, folder / 'result', context=context, **kwargs)
            else:
                value = door.execute(task, task['initial_design'], task['initial_problem'],
                    decision, folder / 'result', **kwargs)
            value['condition_id'] = condition_id(task)
            path = folder / 'result/public-result.json.gz'
            door._write_gzip(path, value)
            (folder / 'result/public-result.json').unlink()
            # A single canonical gzip artifact, with exact full readback, for
            # freshly owned LC output. Never touch older source artifacts.
            if is_lc(task):
                for name in ('raw', 'assessment'):
                    source = folder / 'result' / (name + '.json')
                    raw = source.read_bytes()
                    target = source.with_suffix('.json.gz')
                    with gzip.open(target, 'wb') as stream:
                        stream.write(raw)
                    with gzip.open(target, 'rb') as stream:
                        if stream.read() != raw:
                            raise RuntimeError('LC_CANONICAL_GZIP_READBACK')
                    source.unlink()
            row.update(status='COMPLETE', model_valid=value['model_valid'],
                verdict=value['public_check']['verdict'], public_path=str(path))
            self.cache[key] = dict(path=str(path), origin='THIS_PACKAGE_NEW_FULL')
        except Exception as exc:
            row.update(status='TOOL_ERROR', error=type(exc).__name__ + ':' + str(exc))
            value = dict(task_id=task['task_id'], design=deepcopy(design),
                condition_id=condition_id(task), execution_status='TOOL_ERROR',
                model_valid=False, public_check=dict(verdict='UNKNOWN'), error=row['error'])
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prior_signal)
            elapsed = time.monotonic() - started
            row['full_wall_s'] = elapsed
            self.ledger['full_wall_s'] += elapsed
            save(folder / 'receipt.json', row)
            journal(HERE / 'logical-inputs.jsonl', row)
            self.persist()
        value.update(reused=False, new_full_wall_s=elapsed,
                     canonical_public_path=row.get('public_path'))
        print(json.dumps(dict(event='FULL', group=group, slot=slot,
            condition=condition_id(task), status=row['status'],
            verdict=value['public_check']['verdict'], wall_s=elapsed)), flush=True)
        return public_copy(value, task)

    def evaluate(self, family, design, *, group, slot, phase, contexts=None):
        self.ready()
        precheck = dict(group=group, slot=slot, design_sha256=digest(design), phase=phase)
        try:
            self.validate(family[0], design)
            precheck['status'] = 'PASS'
        except ValueError as exc:
            precheck.update(status='STATIC_REJECTED', reason=str(exc))
        self.ledger['prechecks'].append(precheck)
        self.persist()
        if precheck['status'] != 'PASS':
            return dict(design=deepcopy(design), results=[], model_valid=False,
                execution_status='STATIC_REJECTED', public_check=dict(verdict='UNKNOWN'),
                static_error=precheck['reason'], usage=dict(full_inputs=0, full_wall_s=0.,
                    logical_inputs=0, cache_reuses=0))
        rows = []
        for task in family:
            row = self.member(task, design, group=group, slot=slot, phase=phase,
                             context=(contexts or {}).get(task['task_id']))
            rows.append(row)
            if row.get('execution_status') == 'TOOL_ERROR':
                break
        valid = len(rows) == len(family) and all(r.get('model_valid') is True and
            r.get('execution_status') in {'OK', 'COMPLETE', 'COMPLETED', 'SUCCESS'} for r in rows)
        verdict = 'UNKNOWN' if not valid else 'PASS' if all(
            r['public_check']['verdict'] == 'PASS' for r in rows) else 'FAIL'
        return dict(design=deepcopy(design), results=rows, model_valid=valid,
            execution_status='COMPLETE' if len(rows) == len(family) else 'TOOL_ERROR',
            public_check=dict(verdict=verdict), usage=dict(
                full_inputs=sum(not r.get('reused', False) for r in rows),
                full_wall_s=sum(r['new_full_wall_s'] for r in rows),
                logical_inputs=len(rows), cache_reuses=sum(r.get('reused', False) for r in rows)))
