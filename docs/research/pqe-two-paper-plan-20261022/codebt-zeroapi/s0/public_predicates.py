"""Condition-scoped observations from already public records; no evaluator I/O."""
from copy import deepcopy
import hashlib
import json

SCHEMA='codebt-public-observation-v1'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def observations(public_result, *, artifact_ref, expected_count=None, expected_ref=None):
    """Capture count support and distinct-capture sequence reuse, with UNKNOWN."""
    p=public_result
    facts=p.get('facts',{})
    facts=facts if isinstance(facts,dict) else {}
    activity=facts.get('activity')
    records=facts.get('records')
    base=dict(schema=SCHEMA,condition_id=p.get('condition_id'),
        design_sha256=digest(p['design']) if isinstance(p.get('design'),dict) else None,
        result_sha256=p.get('result_sha256'),scope='This condition and this complete public trace only; no hidden-event matching.')
    def ref(pointer):
        item=deepcopy(artifact_ref) if isinstance(artifact_ref,dict) else {'path':artifact_ref}
        item['pointer']=pointer
        return item
    valid=(p.get('model_valid') is True and p.get('execution_status') in {'COMPLETE','COMPLETED','SUCCESS','OK'}
           and isinstance(activity,list) and len(activity)<=100000 and isinstance(records,list) and len(records)<=100000
           and bool(artifact_ref) and bool(base['condition_id']) and bool(base['result_sha256']))
    captured=[];saves=[];resets=[];pairs=[];pending=None;ambiguous=False
    if valid:
        for i,event in enumerate(activity):
            if not isinstance(event,dict):ambiguous=True;continue
            action=event.get('action')
            if action in {'brownout','reset'}:resets.append(i)
            if action=='capture':
                if pending is not None:ambiguous=True
                pending=(i,event);captured.append(i)
            elif action=='save_commit':
                saves.append(i)
                if pending is not None:
                    record=event.get('record')
                    if (not isinstance(record,dict) or type(record.get('seq')) is not int
                            or record.get('direction')!=pending[1].get('direction')):
                        ambiguous=True
                    else:pairs.append((pending[0],i,record['seq']))
                    pending=None
        if pending is not None:ambiguous=True
    counts=dict(expected_capture_count=expected_count,capture_count=len(captured) if valid else None,
        save_commit_count=len(saves) if valid else None)
    known_target=type(expected_count) is int and expected_count>=0 and bool(expected_ref)
    capture_holds=None
    if valid and known_target:
        if len(captured)==expected_count:capture_holds=True
        elif len(captured)<expected_count:capture_holds=False
    capture_refs=[ref('/facts/activity'),ref('/facts/records')]
    if expected_ref:capture_refs.append(deepcopy(expected_ref))
    capture=dict(**base,predicate_id='capture_coverage',holds=capture_holds,measurements=counts,refs=capture_refs,
        reason='Observed capture count versus the common public count requirement; equality is count support, not hidden event correspondence.' if valid and known_target else 'UNKNOWN: complete valid public trace and explicit public count requirement are both required.')
    identities=[x[2] for x in pairs]
    reused=len(identities)-len(set(identities))
    paired=(valid and not ambiguous and bool(pairs) and len(pairs)==len(captured)==len(records))
    identity_holds=(reused==0) if paired else None
    refs=[]
    for capture_index,save_index,_ in pairs:
        refs.extend([ref('/facts/activity/'+str(capture_index)),ref('/facts/activity/'+str(save_index))])
    identity=dict(**base,predicate_id='sequence_identity',holds=identity_holds,
        measurements=dict(distinct_capture_save_pairs=len(pairs) if valid else None,
            distinct_saved_seq_count=len(set(identities)) if valid else None,
            reused_seq_count=reused if paired else None,reset_count=len(resets) if valid else None),
        refs=refs or [ref('/facts/activity'),ref('/facts/records')],
        reason='Different public capture-to-SAVE pairs reuse a saved sequence.' if identity_holds is False else
               'Distinct public capture-to-SAVE pairs have distinct saved sequences.' if identity_holds is True else
               'UNKNOWN: no complete unambiguous capture-to-SAVE pairing; packet retransmissions are not new captures.')
    return [capture,identity]


def attach_family_result(family_result, artifact_refs, expected_requirements):
    """Same derived facts for every controller; original artifacts remain intact."""
    derived=deepcopy(family_result)
    all_rows=[]
    for result in derived.get('results',[]):
        condition=result.get('condition_id')
        requirement=expected_requirements.get(condition,{})
        rows=observations(result,artifact_ref=artifact_refs.get(condition),
            expected_count=requirement.get('expected_capture_count'),expected_ref=requirement.get('ref'))
        result['predicate_observations']=rows
        all_rows.extend(rows)
    derived['predicate_observations']=all_rows
    derived['public_observation_bridge']=dict(schema=SCHEMA,original_family_sha256=digest(family_result),
        evidence_source='Only original public facts.activity/records and explicit shared count requirements; no evaluator truth or receiver_identity.')
    return derived
