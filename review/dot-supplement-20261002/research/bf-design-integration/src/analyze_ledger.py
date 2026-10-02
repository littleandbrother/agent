"""Read-only local method ledger summary, with no scientific verdict inference."""
import argparse
import json
from pathlib import Path
from method_adapter import digest, require


def analyze(path):
    text = Path(path).read_text()
    require(text.endswith('\n'), 'PARTIAL_LEDGER')
    events, intents, outcomes = [], {}, set()
    counts = {}
    reservations, activations, submissions = [], [], []
    for line in text.splitlines():
        event = json.loads(line)
        require(event.get('seq') == len(events) and event.get('previous') == (events[-1]['hash'] if events else None)
                and event.get('hash') == digest({k: v for k, v in event.items() if k != 'hash'}), 'LEDGER_HASH')
        events.append(event)
        kind, data = event['kind'], event['data']
        if kind == 'action_intent':
            require(data['tool'] == 'bf_engineering', 'ACTION_TOOL')
            intents[event['hash']] = data
            action = data['arguments']['action']
            counts[action] = counts.get(action, 0) + 1
        elif kind in {'action_result', 'action_error'}:
            require(data['intent_hash'] in intents and data['intent_hash'] not in outcomes, 'ACTION_OUTCOME_BINDING')
            if kind == 'action_result':
                require(data['response_hash'] == digest(data['response']), 'RESPONSE_HASH')
            outcomes.add(data['intent_hash'])
        elif kind == 'reserved':
            require(data['candidate_hash'] == digest(data['candidate']), 'CANDIDATE_HASH')
            reservations.append(data)
        elif kind == 'method_activation':
            activations.append(data)
        elif kind == 'submitted':
            require(data['receipt_hash'] == digest(data['receipt']), 'SUBMISSION_HASH')
            submissions.append(data)
    require(events and events[0]['kind'] == 'identity', 'LEDGER_IDENTITY')
    require(len(reservations) <= 3 and len({r['operation_id'] for r in reservations}) == len(reservations), 'CANDIDATE_QUOTA')
    require(len(submissions) <= 1, 'SUBMISSION_IMMUTABLE')
    return {'schema': 'bf-design-nominal-ledger-analysis-v1', 'identity': events[0]['data'],
            'head_hash': events[-1]['hash'], 'events': len(events), 'reserved_candidates': len(reservations),
            'action_intents': counts, 'unresolved_action_intents': sorted(set(intents) - outcomes),
            'method_function_invocations': len(activations), 'submission': submissions[0] if submissions else None,
            'scientific_success': False, 'costs': None,
            'limits': 'Local hash consistency and actual injected-tool calls only. Not authenticated authorship, SDK prompt delivery, native acceptance, paid-ledger accounting or method efficacy.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.ledger), ensure_ascii=False, indent=2))
