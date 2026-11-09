"""Common public graph -> controller facts; no hidden truth or repair values."""
from copy import deepcopy
from common import digest
from bfworld.agentlab.pqe20261024debt import facts

VERSION = 'partial-ancestor-observed-relations-v2'
STAGES = {'capture':'produced', 'holder_capture':'produced', 'read':'read',
          'save':'saved', 'tx':'wire', 'recv':'received', 'ack':'ack', 'clear':'clear'}


PRIVATE_FIELDS = frozenset(('observer_epoch', 'observer_event_id', 'hidden_truth',
                            'event_truth', 'truth_event_id'))


def public_copy(value):
    if isinstance(value, dict):
        return {k: public_copy(v) for k, v in value.items() if k not in PRIVATE_FIELDS}
    if isinstance(value, list):
        return [public_copy(v) for v in value]
    return deepcopy(value)


def project(public):
    # Original artifacts stay immutable; the entire shared runtime copy is
    # sanitized, including nested activity, not only the derived graph.
    value = public_copy(public)
    graph = facts.public_record_relations(value)
    rows = []
    cid = value.get('condition_id', value.get('task_id'))
    design_sha = digest(value.get('design'))

    def add(stage, holds, key, refs, kind, depends=()):
        row = dict(condition_id=cid, design_sha256=design_sha,
                   result_sha256=value.get('result_sha256'),
                   stage=stage, holds=holds, record_key=deepcopy(key),
                   refs=list(refs), evidence_kind='runtime', relation_kind=kind,
                   depends_on=list(depends),
                   source='original public activity/receiver_records; explicit source pointers',
                   scope='Observed operation/identity fact; absence never establishes lost service.')
        row['relation_id'] = 'rel-' + digest(row)[:24]
        rows.append(row)

    # A sequence is an observed field, never a globally unique device identity.
    # Unknown holder identity stays null; its real capture fact remains visible
    # but cannot be counted as a known-identity capability by the controller.
    for record in graph['records'] + graph['holder_records']:
        key = record.get('record_key')
        if not isinstance(key, dict) or key.get('status') != 'OBSERVED':
            key = None
        for stage, refs in record.get('stages', {}).items():
            if stage in STAGES:
                add(STAGES[stage], True, key, refs, 'observed_'+stage)

    prior = {}
    for record in graph['records']:
        key = (record.get('seq'), record.get('direction'))
        old = prior.get(key)
        if (old and key[0] is not None and old.get('observed_mcu_resets_at_save')
                != record.get('observed_mcu_resets_at_save')):
            old_holder, new_holder = old.get('holder_capture_ref'), record.get('holder_capture_ref')
            def origin(row):
                if row.get('holder_capture_ref'):
                    return row['holder_capture_ref']
                captures = row.get('stages', {}).get('capture', [])
                if len(captures) != 1:
                    return None
                event = next((e for e in graph['events'] if e['id'] == captures[0]), {})
                return captures[0] if event.get('source') != 'paid_holder_read' else None
            first, second = origin(old), origin(record)
            if first and second and first != second:
                add('identity', False, record.get('record_key'),
                    [old['id'], record['id'], first, second],
                    'distinct_public_capture_origins_share_numeric_identity_across_reset',
                    ('persistent_queue',))
            elif old_holder and old_holder == new_holder:
                pass  # Idempotent re-read of the same live holder record.
            else:
                graph['unknowns'].append(dict(relation='cross_reset_numeric_identity',
                    source_refs=[old['id'], record['id']], status='UNKNOWN',
                    reason='Distinct public capture origins are not established.'))
        prior[key] = record
    # Only explicit unsuccessful operations become negative facts. An expiry,
    # reset, absent stage, repeated read or ACK timing is not inferred loss.
    for event in graph['events']:
        if event['stage'] in {'overflow_drop', 'overflow_overwrite'}:
            add('produced', False, None, [event['source_ref']],
                'observed_holder_overflow_operation',
                ('holding_capacity','holding_overflow','read_source','clear_after'))
        elif event['stage']=='read_invalidated':
            add('read', False, None, [event['source_ref']], 'observed_read_invalidated',
                ('read_source','holding_component','startup_v','capacitance_f'))
    value['relationship_graph'] = graph
    value['relationship_view'] = dict(schema=VERSION, relations=rows,
        unknowns=deepcopy(graph['unknowns']), source_graph_schema=graph['schema'],
        source_types=dict(component_domain='component_contract; static source facts',
                          runtime='relations with source pointers',
                          manual_contract='depends_on lists declare field scope, never correct values'),
        absence_is_not_loss=True, observer_identity_exposed=False)
    return value
