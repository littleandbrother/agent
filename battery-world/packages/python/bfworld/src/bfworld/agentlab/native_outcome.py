"""Small, complete facts from native output; process success never implies a check pass."""
import json


def documents(text):
    decoder = json.JSONDecoder()
    remaining = text.lstrip()
    while remaining:
        if remaining.startswith('{'):
            try:
                value, end = decoder.raw_decode(remaining)
                yield value
                remaining = remaining[end:].lstrip()
                continue
            except ValueError:
                pass
        remaining = remaining.partition('\n')[2].lstrip()


def summarize(receipt):
    argv = receipt.get('argv', [])
    values = [d.get('result', {}) for d in documents(receipt.get('stdout', ''))]
    checks = [v for v in values if isinstance(v, dict) and type(v.get('passed')) is bool]
    execution = receipt.get('status', 'UNKNOWN')
    status = ('failed' if any(not v['passed'] for v in checks) else 'passed') if checks else 'not_reported'
    if execution != 'SUCCEEDED':
        status = 'unavailable'
    elif not checks and any(x in argv[:2] for x in ('drc', 'check', 'bridge-check', 'module-check')):
        status = 'unavailable'
    counts = [{'name': str(x.get('name', 'unknown')), 'count': x['count']}
              for v in checks for x in v.get('violations', [])
              if isinstance(x, dict) and type(x.get('count')) is int]
    return {'schema_version': 'bf-native-outcome-v1', 'execution_status': execution,
            'check_status': status, 'check_scope': '.'.join(argv[:2]),
            'counts': counts, 'binding': next((v['binding'] for v in checks if 'binding' in v), None),
            'job_id': receipt.get('job_id'), 'project': receipt.get('project'),
            'engineering_passed': False, 'hardware_verified': False}
