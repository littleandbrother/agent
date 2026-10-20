"""Small evidence helpers for the frozen public development campaign."""
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(path, value):
    path = Path(path)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != raw:
        raise ValueError('IMMUTABLE_RECEIPT_EXISTS:' + str(path))
    if not path.exists():
        with path.open('x') as out:
            out.write(raw)
    return value


def require_matched(left, right):
    for key in ('task', 'checker', 'backend', 'information', 'cache_start', 'limits'):
        if left[key] != right[key]:
            raise ValueError('UNMATCHED_CONDITION:' + key)
    return True


def usage_summary(rows):
    missing = [r['id'] for r in rows if r['status'] == 'UNKNOWN'
               or (r['status'] == 'SETTLED' and not r.get('usage'))]
    return {'requests': len(rows), 'unknown_or_missing_usage': missing,
            'settled_cost_upper_bound_usd': sum(r.get('charged', 0) or 0 for r in rows
                                    if r['status'] == 'SETTLED'),
            'reserved_unsettled_usd': sum(r.get('reserved', 0) or 0 for r in rows
                                          if r['status'] != 'SETTLED')}
