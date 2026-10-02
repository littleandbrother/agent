"""Pre-gate observations and organic-rule eligibility audits.

Static source guards are leads, never evidence of an observed blocked action.
An event must precede execution, bind an activated rule and explicit candidate,
and record the exposure probability. No model-private reasoning is collected.
"""
import json
from pathlib import Path
import re

from ..store import identity
from .core import sha


def observe(research, *, rule, candidate, decision, probability, trial, activation):
    research.check_trial(trial)
    if decision not in {'allow', 'block'} or type(probability) not in (float, int) or not 0 < probability <= 1:
        raise ValueError('GATE_OBSERVATION_INVALID')
    if not candidate or rule.get('identity') != identity(rule.get('source')):
        raise ValueError('GATE_RULE_IDENTITY')
    if activation.get('rule_identity') != rule['identity'] or activation.get('trial') != trial:
        raise ValueError('GATE_NOT_ACTIVATED')
    return research.event('gate_before', {'trial': trial, 'rule': rule, 'candidate': candidate,
        'candidate_hash': identity(candidate), 'decision': decision, 'exposure_probability': probability,
        'activation': activation, 'origin': rule.get('origin', 'unverified'),
        'origin_verified': False, 'eligibility': 'requires independent origin and activation review', 'outcome': None})


def audit_history(research):
    candidates = []
    for p in sorted((research.home/'studies/dev-v1/candidates').glob('*/candidate.json')):
        record = json.loads(p.read_text())
        if not record.get('changed_files'):
            continue
        harness = Path(record['harness_path']) if record.get('harness_path') else None
        sources = []
        if harness and harness.is_relative_to(research.home/'harnesses'):
            for name in record['changed_files']:
                if name not in {'solver.ts', 'improver.ts'}:
                    continue
                src = harness/'src'/name
                if src.is_file():
                    lines = src.read_text().splitlines()
                    guards = [{'line': i+1, 'text': line.strip()[:350]} for i, line in enumerate(lines)
                              if re.search(r'\b(if|filter|reject|skip|allow|deny)\b', line)]
                    sources.append({'path': str(src), 'sha256': sha(src.read_bytes()), 'guard_leads': guards})
        candidates.append({'record_path': str(p), 'record_sha256': sha(p.read_bytes()),
                           'label': record['label'], 'origin': record['origin'], 'status': record['status'],
                           'parent': record['parent'], 'identity': record.get('identity'), 'sources': sources})
    observed = []
    for p in sorted((research.home/'research').glob('*/events.jsonl')):
        for line in p.read_text().splitlines():
            row = json.loads(line)
            if row.get('kind') == 'gate_before' and row.get('data', {}).get('origin') == 'AUTONOMOUS_PI':
                observed.append({'journal': str(p), 'event_hash': row['hash']})
    report = dict(paper='C', kind='organic-rule-audit', candidates=candidates, gate_before_events=observed,
        status='REQUIRES_EVENT_REVIEW' if observed else 'NOT_IDENTIFIABLE_FROM_HISTORICAL_TRACE',
        eligible_pairs=0,
        finding='Existing autonomous program revisions are retained, but static guards do not reveal the outcomes of blocked candidates.',
        next='Collect explicit candidate and loaded rule identities before real rule execution; then use matched legal exposure branches.',
        limitations=['No claim of zero blind spots: historical trace lacks gate-before observations.',
                     'Injected gates validate instrumentation only; not organic C or RSI evidence.'])
    return research.put('reports', report)
