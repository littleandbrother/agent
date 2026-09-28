#!/usr/bin/env python3
"""Read-only research launch preflight. Does not call a model or unseal tasks."""
import json
from pathlib import Path
import yaml
REPO=Path(__file__).resolve().parents[1]

def readiness(protocol:dict)->dict:
    blockers=[];provider=protocol['provider'];budget=protocol['budget'];isolation=protocol['participant_isolation'];evaluation=protocol['history_and_evaluation']
    for key in ('implementation','version','model_identity'):
        if not provider.get(key):blockers.append('missing provider '+key)
    if not provider.get('usage_receipts_available'):blockers.append('provider usage receipts unavailable')
    for key in ('max_external_calls','max_tokens','max_paid_cost','max_wall_seconds'):
        value=budget.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or value<=0:blockers.append('no positive authorized budget: '+key)
    if not isolation.get('separate_filesystem') or not isolation.get('hidden_mount_test_passed'):blockers.append('participant isolation not verified')
    if isolation.get('reference_source_visible') or isolation.get('sealed_evaluator_visible'):blockers.append('reference or hidden evaluator exposed')
    for key in ('equal_history_manifest','public_development_manifest','sealed_final_confirmation_manifest'):
        if not evaluation.get(key):blockers.append('missing '+key)
    if evaluation.get('final_feedback_to_evolver'):blockers.append('sealed final feedback leak')
    return {'schema_version':'pilot-readiness-v1','launchable':not blockers,'blockers':blockers,'external_calls_made':0,
            'scope':'configuration preflight only; actual isolation and provider identities require independent verification'}

if __name__=='__main__':
    report=readiness(yaml.safe_load((REPO/'studies/protocols/fixed-model-pilot.yaml').read_text()))
    print(json.dumps(report,indent=2))
