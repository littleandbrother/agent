"""Prospective BF comparison: immutable initial knowledge, isolated job overlays.

Physical exact-input responses may be shared without exposing another arm's
decisions. Each arm still pays one logical evaluation for every new D it asks
about. Event provenance/order is evaluated separately from legacy labels.
"""
from __future__ import annotations

import copy
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import time
import zlib

from .common import digest, file_hash, seal
from .phase1 import encoded
from .phase2 import CaseStore, VARIABLES, consume, design, source_units
from . import phase2_discovery as discovery


def checked_design(value, limits):
    if not isinstance(value, dict) or set(value) != set(limits):
        raise ValueError('EXACT_LEGAL_D_FIELDS_REQUIRED')
    for key, (lo, hi) in limits.items():
        if type(value[key]) not in (int, float) or not math.isfinite(value[key]) or not lo <= value[key] <= hi:
            raise ValueError('DESIGN_OUT_OF_DOMAIN:' + key)
    return copy.deepcopy(value)


def ordered_state(task, run, reference):
    """Use the task event and receiver-checked packet, not success-and-any-reset."""
    deliveries = sorted(p['time_s'] for p in run['packets']
                        if p.get('event_id') == 1 and p.get('application_bytes') == 8)
    first = deliveries[0] if deliveries else None
    resets = [x for x in run['activity'] if x['action'] == 'brownout']
    captures = [x for x in run['activity'] if x['action'] == 'capture' and x.get('event_id') == 1]
    before = [x for x in resets if first is not None and task['event_s'] <= x['time_s'] < first]
    after = [x for x in resets if first is not None and first < x['time_s'] <= task['deadline_s']]
    valid = first is not None and reference['verdicts']['event_receive'] == 'PASS'
    retained = False
    if not valid:
        label = 'NO_VALID_EVENT_DELIVERY'
    elif not before:
        label = 'DELIVERED_BEFORE_ANY_RESET'
    else:
        last_reset = before[-1]['time_s']
        recaptured = any(last_reset < x['time_s'] <= first for x in captures)
        passive = task['device']['event_latch'] == 'passive-mechanical'
        # The frozen model captures the same task event passively even with no
        # powered capture action. This is explicitly an ideal memory assumption.
        retained = (passive and task['event_s'] < before[0]['time_s'] and not recaptured
                    and all(x.get('event_was_captured') is True for x in before))
        label = ('PENDING_EVENT_RETAINED_ACROSS_RESET' if retained else
                 'EVENT_RECAPTURED_AFTER_RESET' if recaptured else
                 'PENDING_EVENT_RETENTION_NOT_ESTABLISHED')
    return {'version': 'ordered-event-provenance-v1', 'classification': label,
            'pending_event_retained_across_reset': retained,
            'event_origin': {'task_event_id': 1, 'time_s': task['event_s'],
                             'receiver_event_id_matches': valid,
                             'mechanism': task['device']['event_latch']},
            'first_valid_receive_s': first if valid else None,
            'resets_before_first_delivery': before,
            'resets_after_delivery_before_deadline': after,
            'capture_actions': captures,
            'source_binding_sha256': digest({'task': task, 'activity': run['activity'], 'packets': run['packets']}),
            'lineage_scope': 'Single event_id=1 in frozen ideal digital state machine; no hardware memory witness',
            'legacy_label': reference['verdicts']['event_preserved_after_reset'],
            'physical_qualification': 'UNKNOWN'}


def pointer(payload, path):
    for token in path.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        payload = payload[int(token)] if isinstance(payload, list) else payload[token]
    return payload


def unit_scale(unit):
    atoms = {x: Decimal(1) for x in ('1','kg','m','s','A','J','W','V','F','ohm','C','Hz')}
    for base in ('J','W','V','F','A','s'):
        for prefix, exponent in [('m',-3),('u',-6),('n',-9)]:
            atoms[prefix+base] = Decimal(10)**exponent
    result, sign = Decimal(1), 1
    for part in re.split(r'([*/])', unit.replace('µ','u')):
        if part in ('*','/'):
            sign = -1 if part=='/' else 1
        else:
            match = re.fullmatch(r'([A-Za-z]+|1)(?:\^(-?[0-9]{1,2}))?', part)
            if not match or match[1] not in atoms:
                raise ValueError('INDEPENDENT_UNIT_UNAVAILABLE')
            result *= atoms[match[1]]**(int(match[2] or 1)*sign)
    return result


def scale_value(value, scale):
    if isinstance(value, list):
        return [scale_value(x, scale) for x in value]
    return Decimal(str(value))*scale if type(value) in (int,float,Decimal) else value


def independent_value(tree, payload):
    """Separate scalar Decimal implementation; unavailable operators fail closed."""
    if 'field' in tree or 'constant' in tree:
        value = pointer(payload, tree['field']) if 'field' in tree else tree['constant']
        return scale_value(value, unit_scale(tree['units']))
    values = [independent_value(node, payload) for node in tree['args']]
    op = tree['op']
    if op in ('neg','abs','sqrt','not'):
        fn = {'neg':lambda x:-x,'abs':abs,'sqrt':lambda x:x.sqrt(),'not':lambda x:not x}[op]
        return [fn(x) for x in values[0]] if isinstance(values[0],list) else fn(values[0])
    if op in ('sum','mean','min','max','all','any'):
        v=values[0]
        return {'sum':lambda:sum(v,Decimal(0)),'mean':lambda:sum(v,Decimal(0))/len(v),
                'min':lambda:min(v),'max':lambda:max(v),'all':lambda:all(v),'any':lambda:any(v)}[op]()
    functions = {'add': lambda a,b: a+b, 'sub': lambda a,b: a-b, 'mul': lambda a,b: a*b,
                 'div': lambda a,b: a/b, 'gt': lambda a,b: a>b, 'ge': lambda a,b: a>=b,
                 'lt': lambda a,b: a<b, 'le': lambda a,b: a<=b, 'eq': lambda a,b: a==b,
                 'and':lambda a,b:a and b,'or':lambda a,b:a or b}
    if op not in functions:
        raise ValueError('INDEPENDENT_OPERATOR_UNAVAILABLE:' + op)
    a, b = values
    if isinstance(a, list) or isinstance(b, list):
        n = len(a) if isinstance(a,list) else len(b)
        aa, bb = a if isinstance(a,list) else [a]*n, b if isinstance(b,list) else [b]*n
        if len(aa) != len(bb): raise ValueError('VECTOR_LENGTH_MISMATCH')
        return [functions[op](x,y) for x,y in zip(aa,bb)]
    return functions[op](a,b)


def qualify(spec, acquisition):
    start = time.monotonic()
    if digest(acquisition['payload']) != acquisition['source_sha256']:
        raise ValueError('SOURCE_PAYLOAD_BINDING_FAILED')
    if file_hash(acquisition['parent_path']) != acquisition['parent_sha256']:
        raise ValueError('SOURCE_PARENT_BINDING_FAILED')
    value = discovery.evaluate_proposal(spec, acquisition['payload'],
                                       field_units=acquisition['field_units'])
    if value['status'] != 'OBSERVED' or value['unit_status'] != 'CHECKED_AGAINST_SUPPLIED_MAPPING':
        raise ValueError('OBSERVATION_UNQUALIFIED:' + str(value.get('reason')))
    check = (scale_value(pointer(acquisition['payload'], spec['field']),
                         unit_scale(acquisition['field_units'][spec['field']]))
             if spec['mode'] == 'selection' else independent_value(spec['ast'], acquisition['payload']))
    check = scale_value(check, Decimal(1)/unit_scale(spec['units']))
    got = value['value']
    if type(got) in (int, float):
        if abs(Decimal(str(got)) - Decimal(str(check))) > max(Decimal('1e-18'), abs(Decimal(str(check)))*Decimal('1e-12')):
            raise ValueError('INDEPENDENT_VALUE_DISAGREED')
    elif type(got) is not type(check) or got != check:
        raise ValueError('INDEPENDENT_TYPED_VALUE_DISAGREED')
    obs = {'qualification': 'EXTERNAL_PASS', 'spec_sha256': digest(spec),
           'source_sha256': acquisition['source_sha256'],
           'parent_sha256': acquisition['parent_sha256'], 'value': got,
           'units': spec['units'], 'domain': spec['domain']}
    return obs, {'status': 'EXTERNAL_PASS', 'prospective': True,
                 'unit_status': value['unit_status'], 'domain_status': value['domain_status'],
                 'independent_scalar_value_agrees': True,
                 'wall_seconds': time.monotonic()-start,
                 'scope': 'Declared-source relation under fixed digital apparatus; not novelty, physical measurement or service proof'}


class ComparisonStore:
    def __init__(self, app, output, historical, initial, group, *, maximum=239):
        self.app, self.output, self.historical = map(Path, (app, output, historical))
        self.initial = Path(initial)
        self.initial_sha256 = file_hash(self.initial)
        self.group = group
        self.job = self.output / 'groups' / group / 'job-overlay.json'
        self.job.parent.mkdir(parents=True, exist_ok=True)
        if not self.job.exists():
            self.job.write_bytes(encoded({'initial_cache_sha256': self.initial_sha256, 'executed': {}})+b'\n')
        self.physical_root = self.output / 'physical-cache'
        self.physical_root.mkdir(parents=True, exist_ok=True)
        index = self.physical_root / 'index.json'
        if not index.exists():
            index.write_bytes(self.initial.read_bytes())
        self.base = PhysicalStore(app, self.physical_root, historical,
                              maximum=maximum+sum(e['origin']=='new-full-feedback-response'
                                                  for e in json.loads(self.initial.read_text()).values()))
        self.initial_keys = set(json.loads(self.initial.read_text()))

    def task(self, world):
        return self.base.task(world)

    def legal(self, world):
        return self.base.legal(world)

    def source(self, source, world):
        if source == 'model_law':
            path = self.app/'packages/python/bfworld/src/bfworld/agentlab/campaign20261019/b.py'
            payload = {'model_id': self.task(world)['model_id'], 'python_definition': path.read_text()}
            return {'source_id': source, 'payload': payload, 'source_sha256': digest(payload),
                    'field_units': source_units(payload), 'parent_path': str(path), 'parent_sha256': file_hash(path),
                    'acquisition': {'native_calls': 0, 'new_scientific_executions': 0, 'bytes': len(encoded(payload))}}
        return self.base.source(source, world)

    def execute(self, world, candidate):
        job = json.loads(self.job.read_text())
        if job['initial_cache_sha256'] != self.initial_sha256:
            raise ValueError('INITIAL_CACHE_SNAPSHOT_CHANGED')
        marker = digest({'world': world, 'D': checked_design(candidate, self.legal(world))})
        if marker not in job['executed'] and len(job['executed']) >= 2:
            raise ValueError('SHARED_GROUP_TWO_D_LIMIT')
        result = self.base.execute(world, candidate)
        raw = (json.loads(zlib.decompress(Path(result['raw_path']).read_bytes()))
               if result['raw_path'] else json.loads(self.base.original(world)['observations.json'].read_text()))
        result['ordered_event_state'] = ordered_state(self.task(world), raw, result['reference'])
        result['evaluator_version'] = 'phase3-independent-service-with-ordered-event-v1'
        rule = self.base.task_registry['tasks'][world].get('query_protocol')
        if rule:
            decoded = [self.base.checker.decode(p['hex'], 'b') for p in raw['packets']]
            matches = [p for p,d in zip(raw['packets'],decoded) if d and d['seq']==rule['nonce_sequence']
                       and d['event']==1 and d['key']==1 and d['id']==self.task(world)['device']['id']]
            issued, deadline = rule['issued_s'], rule['deadline_s']
            capture = any(x['action']=='capture' and issued<=x['time_s']<=deadline for x in raw['activity'])
            gates = {'single_query_token': len(matches)==1,
                     'query_before_reply': bool(matches) and all(issued<=p['time_s']<=deadline for p in matches),
                     'freshness': bool(matches) and all(0<=p['time_s']-issued<=rule['max_data_age_s'] for p in matches),
                     'query_state_capture': capture}
            result['query_service'] = {'gates': gates, 'status': 'PASS' if all(gates.values()) else 'FAIL',
                                       'protocol': rule, 'physical_or_multiquery_nonce_security': 'NOT_ESTABLISHED'}
            if not all(gates.values()): result['complete_service']='FAIL'
        result['job_accounting'] = {
            'initial_cache_sha256': self.initial_sha256,
            'initial_physical_cache_hit': result['execution_key'] in self.initial_keys,
            'another_group_output_not_exposed_before_query': True,
            'physical_exact_input_reused': result['reused'],
            'new_logical_D_evaluation': marker not in job['executed'],
            'scope': 'Physical deduplication does not enlarge the two-D arm budget; new group job histories remain isolated'}
        if marker not in job['executed']:
            job['executed'][marker] = {'world': world, 'candidate': candidate,
                                      'result_sha256': digest(result)}
            self.job.write_bytes(encoded(job)+b'\n')
        return result


class PhysicalStore(CaseStore):
    """Add only preregistered derived digital cases, without editing old worlds."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_registry = json.loads((self.app/'configs/studies/phase3-20261020/shared/tasks.json').read_text())

    def legal(self, world):
        return {k:tuple(v) for k,v in self.task_registry['tasks'][world]['legal_design_ranges'].items()}

    def execute(self, world, patch):
        if 'derived_assets' not in self.task_registry['tasks'][world]:
            return super().execute(world, patch)
        from .b import simulate_b
        self.check_sources()
        patch=checked_design(patch,self.legal(world)); original=self.original(world)
        task=json.loads(original['input.json'].read_text()); task['device'].update(patch)
        key=digest({'task':task,'model':self.registry['frozen_scientific_files'],
                    'checker_sha256':file_hash(self.app/'scripts/campaign_reference.py')})
        if key in self.index:
            entry=self.index[key]
            if entry.get('status')=='STARTED':raise ValueError('INCOMPLETE_EXECUTION_NO_AUTOMATIC_RESAMPLING')
            for p,sha in entry['artifacts'].items():
                if file_hash(p)!=sha:raise ValueError('CACHED_RESPONSE_TAMPERED')
            return {**json.loads(Path(entry['result_path']).read_text()),'reused':True}
        if self.new_executions>=self.maximum:raise ValueError('GLOBAL_SCIENTIFIC_EXECUTION_CAP')
        self.index[key]={'origin':'new-full-feedback-response','status':'STARTED','input_sha256':digest(task)}
        (self.root/'index.json').write_bytes(encoded(self.index)+b'\n')
        run=simulate_b(task);energy=self.checker.energy_reference(task,run['trace'],'b')
        reference=self.checker.reference_b(task,run,energy)
        out=self.root/key;out.mkdir();seal(out/'input.json',task)
        (out/'response.json.zlib').write_bytes(zlib.compress(encoded(run)))
        value={'input_sha256':digest(task),'execution_key':key,'world':world,'design':patch,
               'origin':'new-full-feedback-response','energy':energy,'reference':reference,
               'complete_service':'PASS' if all(reference['verdicts'][k]=='PASS' for k in
                    ('independent_energy','independent_receiver','event_receive','deduplication','transient_voltage')) else 'FAIL',
               'physical_qualification':'UNKNOWN','raw_path':str(out/'response.json.zlib')}
        seal(out/'result.json',value)
        self.index[key]={'origin':value['origin'],'result_path':str(out/'result.json'),
                         'result_sha256':file_hash(out/'result.json'),'input_sha256':value['input_sha256'],
                         'artifacts':{str(p):file_hash(p) for p in out.iterdir() if p.is_file()}}
        (self.root/'index.json').write_bytes(encoded(self.index)+b'\n')
        return {**value,'reused':False}

    def original(self, world):
        registry_path = self.app / 'configs/studies/phase3-20261020/shared/tasks.json'
        registry = json.loads(registry_path.read_text())
        spec = registry['tasks'][world]
        if 'derived_assets' not in spec:
            return super().original(world)
        result = {}
        for name, item in spec['derived_assets'].items():
            path = Path(item['path'])
            if file_hash(path) != item['sha256']:
                raise ValueError('DERIVED_FIXED_CASE_CHANGED:' + name)
            result[name] = path
        return result


class ProspectiveHost:
    def __init__(self, root, store, world, kind, adapter, *, condition, tool):
        self.root, self.store, self.world = Path(root), store, world
        self.root.mkdir(parents=True, exist_ok=True)
        self.kind, self.adapter, self.condition, self.tool = kind, adapter, condition, tool
        self.counter = adapter.ProposalCounter(kind) if kind in ('E5', 'H') else None
        if self.counter and self.store.legal(world) != VARIABLES:
            self.counter = DomainProposalCounter(adapter,kind,self.store.legal(world))
        self.acquired, self.processed = {}, {}
        self.current = {k: self.store.task(world)['device'][k] for k in VARIABLES}
        self.source_ids = ['component_record', 'excitation_record', 'saved_activity', 'model_law']

    def information(self):
        from .phase3_interfaces import project_condition, encode_packet, validate_equal_information
        task=self.store.task(self.world)
        full={sid:self.store.source(sid,self.world)['payload'] for sid in self.source_ids}
        duration=task['duration_s']
        integral=sum(s['power_w']*max(0,min(duration,s['end_s'])-max(0,s['start_s'])) for s in task['source_segments'])
        coarse={'source_integral_j':integral,'duration_s':duration,'average_power_w':integral/duration,
                'physical_calibration':'UNKNOWN'}
        common={'task':{'event_s':task['event_s'],'contact_duration_s':task['contact_duration_s'],
                        'deadline_s':task['deadline_s'],'required_application_bytes':8,'unique_frames':1,
                        'query_protocol':self.store.base.task_registry['tasks'][self.world].get('query_protocol')},
                'legal_design_space':{k:list(v) for k,v in self.store.legal(self.world).items()},'current_design':self.current}
        c={'fixed_h':'complete-raw','ordinary_reflection':'complete-raw','proposed_method':'complete-raw',
           'e4-rich-static-table':'rich-static','e4-rich-static-json':'rich-static'}.get(self.condition,self.condition)
        roles={x:{'tool_definition_sha256':digest(self.tool),'permissions':self.tool['parameters']} for x in
               ('design','model_response','observation')}
        packet=project_condition(full,c,common=common,average_energy=coarse,tool_catalog=roles)
        rep='table' if self.condition=='e4-rich-static-table' else 'json'
        text=encode_packet(packet,rep)
        if c=='rich-static':
            seal(self.root/'equal-information-qualification.json',validate_equal_information(encode_packet(packet,'json'),encode_packet(packet,'table')))
        seal(self.root/'information-packet.json',{'representation':rep,'decoded_packet_sha256':digest(packet),'packet':packet})
        return {'representation':rep,'serialized_information':text}

    def inspect(self):
        t = self.store.task(self.world)
        value = {'partition': 'public-development', 'world': self.world,
                 'service': {'application_bytes': 8, 'unique_valid_frames': 1,
                             'event_s': t['event_s'], 'deadline_s': t['deadline_s']},
                 'current_design': self.current, 'legal_design_ranges': self.store.legal(self.world),
                 'source_ids': self.source_ids,
                 'scope': 'Frozen ideal digital BF apparatus; physical calibration UNKNOWN'}
        value.update(self.information())
        if self.kind in ('E5', 'H'):
            value['proposal_schema'] = self.adapter.schema(self.kind)
        return value

    def __call__(self, body):
        if self.counter:
            self.counter.prepare(body)
        action = body['action']
        if action in ('inspect', 'sources'):
            return self.inspect()
        if action == 'acquire':
            sid = body['source_id']
            if sid not in self.acquired:
                item = self.store.source(sid, self.world)
                if self.condition == 'average-energy':
                    packet=json.loads(self.information()['serialized_information'])
                    item=copy.deepcopy(item);item['payload']=packet['facts']
                    item['source_sha256']=digest(item['payload']);item['field_units']=source_units(item['payload'])
                self.acquired[sid] = item
                seal(self.root/'acquisitions'/(sid+'.json'), item)
            return {k:v for k,v in self.acquired[sid].items() if k!='parent_path'}
        if self.kind == 'H' and action in ('propose', 'submit'):
            from .phase2_methods import validate_method
            proposal = validate_method(body['proposal'])
            submission = {'proposal': proposal, 'raw_proposal': body['proposal']}
        elif self.kind == 'E5' and action in ('propose', 'submit'):
            req = discovery.validate_request(body, legal_domain=self.store.legal(self.world))
            spec, policy = req['spec'], req['policy']
            if spec['source_id'] not in self.acquired:
                raise ValueError('SOURCE_MUST_BE_ACTUALLY_ACQUIRED')
            key = digest({'spec': spec, 'policy': policy})
            if key not in self.processed:
                observation, qualification = qualify(spec, self.acquired[spec['source_id']])
                consumer = typed_consume(observation, policy, self.current, self.store.legal(self.world))
                if not consumer['used_observation']:
                    raise ValueError('NO_TYPED_CONSUMER_MATCH')
                execution = self.store.execute(self.world, consumer['design'])
                self.processed[key] = {'spec': spec, 'policy': policy, 'observation': observation,
                                       'qualification': qualification, 'consumer': consumer,
                                       'execution': execution}
                seal(self.root/'qualified-consumers'/(key+'.json'), self.processed[key])
            submission = self.processed[key]
        elif self.kind == 'D' and action in ('check', 'submit'):
            candidate = checked_design(body['candidate'],self.store.legal(self.world))
            execution = self.store.execute(self.world, candidate)
            submission = {'candidate': candidate, 'execution': execution}
        else:
            raise ValueError('ACTION_NOT_AVAILABLE_FOR_ARTIFACT_TYPE')
        if action == 'submit':
            seal(self.root/'submission.json', submission)
        if self.kind == 'H':
            return {'recorded': action, 'method_decision': submission['proposal']['decision'],
                    'method_sha256': digest(submission['proposal'])}
        execution = submission['execution']
        result = {'recorded': action, 'selected_design': execution['design'],
                'received_frames': execution['reference']['received_frames'],
                'first_receive_s': execution['reference']['first_receive_s'],
                'brownouts_before_deadline': execution['reference']['brownouts_before_deadline'],
                'first_boot_s': execution['reference']['first_boot_s'],
                'physical_qualification': 'UNKNOWN',
                **({'observation_value': submission['observation']['value'],
                    'qualification_status': submission['qualification']['status']}
                   if self.kind == 'E5' else {})}
        if self.condition == 'executable-response':
            raw=(json.loads(zlib.decompress(Path(execution['raw_path']).read_bytes())) if execution['raw_path'] else
                 json.loads(self.store.base.original(self.world)['observations.json'].read_text()))
            result['response']={'energy_ledger':execution['energy'],'activity':raw['activity'],'packets':raw['packets']}
        return result


def typed_consume(observation, policy, current, limits):
    checked_design(current,limits)
    for row in policy:
        checked_design(row['design'],limits)
        if type(row['equals']) is type(observation['value']) and row['equals']==observation['value']:
            return {'judgment':'SELECTED','design':copy.deepcopy(row['design']),'used_observation':True,
                    'observation_sha256':digest(observation),'policy_sha256':digest(policy)}
    return {'judgment':'UNKNOWN','design':copy.deepcopy(current),'used_observation':False}


class DomainProposalCounter:
    """Same repaired ordering, with the separately preregistered derived domain."""
    def __init__(self,adapter,kind,limits):
        from jsonschema import Draft202012Validator
        self.kind,self.limits=kind,limits;self.validator=Draft202012Validator(adapter.schema(kind))
        self.used=set();self.rejected_operations=0

    def prepare(self,body):
        from jsonschema import ValidationError
        from .phase2_methods import validate_method
        try:
            self.validator.validate(body)
            if body['action'] not in ('propose','submit'):return body
            value=(validate_method(body['proposal']) if self.kind=='H' else
                   discovery.validate_request(body,legal_domain=self.limits))
            if self.kind=='H' and value['decision']=='no-update':return body
            if self.kind=='E5':value={k:v for k,v in value.items() if k!='action'}
        except (ValueError,ValidationError) as error:
            self.rejected_operations+=1
            if self.rejected_operations>2:raise ValueError('V2_SYNTAX_REJECTION_CAP') from error
            raise ValueError('V2_ACTION_TYPE_OR_SYNTAX_REJECTED') from error
        key=digest(value)
        if key not in self.used and self.used:raise ValueError('V2_VALID_PROPOSAL_CAP')
        self.used.add(key);return body
