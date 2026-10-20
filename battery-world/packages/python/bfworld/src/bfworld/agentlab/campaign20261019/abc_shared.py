"""Finite ABC dispatch guards; reuse the existing provider and SDK gateway."""
import json
from pathlib import Path
import shutil
import time

from .phase1 import BFPhaseGateway, encoded, file_hash, ledger


def check_bindings(bindings):
    for name, expected in bindings.items():
        if file_hash(name) != expected:
            raise ValueError('ABC_BOUND_SOURCE_CHANGED:' + name)


def totals(output, database):
    result = dict(attempts=0, requests=0, charge_upper_usd=0.0, wall_s=0.0,
                  unresolved=[], scientific_executions=0)
    for path in sorted((Path(output) / 'episodes').glob('*/attempt.json')):
        result['attempts'] += 1
        root = path.parent
        owner_file = root / 'owner.json'
        if owner_file.exists():
            account = ledger(database, json.loads(owner_file.read_text())['owner'])
            result['requests'] += account['requests']
            result['charge_upper_usd'] += account['settled_charge_upper_bound_usd']
            result['unresolved'].extend(account['unknown_or_missing_usage'])
        final = root / 'episode-result.json'
        result['wall_s'] += (json.loads(final.read_text())['wall_seconds_total'] if final.exists()
                            else time.time() - json.loads(path.read_text())['started_unix'])
        result['scientific_executions'] += len(list(root.glob('*/executions/*/response.json')))
    result['scientific_executions'] += len(list((Path(output)/'exact-inputs/B').glob('*/feedback.json')))
    return result


def require_capacity(plan, output, database, *, entering=False):
    limits = plan['batch_limits']
    value = totals(output, database)
    if value['unresolved']:
        raise ValueError('ABC_PROVIDER_USAGE_UNRESOLVED')
    if value['attempts'] > limits['episodes'] or entering and value['attempts'] >= limits['episodes']:
        raise ValueError('ABC_FINITE_EPISODE_CAP')
    if value['requests'] >= limits['requests'] or value['charge_upper_usd'] >= limits['charge_upper_usd']:
        raise ValueError('ABC_FINITE_PROVIDER_CAP')
    if value['wall_s'] >= limits['summed_wall_s'] or value['scientific_executions'] >= limits['scientific_executions']:
        raise ValueError('ABC_FINITE_EXECUTION_CAP')
    if shutil.disk_usage(output).free < limits['reserve_bytes'] + limits['estimated_peak_bytes']:
        raise ValueError('ABC_STORAGE_RESERVE')
    from .phase1 import output_bytes
    if output_bytes(output) >= limits['retained_output_bytes']:
        raise ValueError('ABC_RETAINED_OUTPUT_CAP')
    db = Path(database)
    provider_bytes = sum(p.stat().st_size for p in db.parent.glob(db.name + '*') if p.is_file())
    if provider_bytes - plan['provider_bytes_before'] >= limits['provider_growth_bytes']:
        raise ValueError('ABC_PROVIDER_STORAGE_CAP')
    return value


def slot_holders(receipt, now=None):
    now = time.time() if now is None else now
    holders = receipt['holders']
    if (not 0 <= now - receipt['observed_unix'] < 120 or
            not receipt.get('idle_execution_thread') or receipt.get('other_executor_status') != 'idle' or
            'S0' not in holders or 'Pi' not in holders or len(set(holders)) != len(holders) or
            not 2 <= len(holders) <= 3):
        raise ValueError('ABC_FRESH_IDLE_SLOT_REQUIRED')
    return holders


class ABCGateway(BFPhaseGateway):
    def __init__(self, *args, batch, **kwargs):
        self.batch = batch
        super().__init__(*args, **kwargs)

    def ready(self, *, paid=False):
        super().ready(paid=paid)
        if paid:
            require_capacity(self.batch, self.batch['output'], self.protocol['provider_database'])
        return True

    def model_payload(self, body):
        result = super().model_payload(body)
        if body.get('max_tokens') != self.protocol['limits']['max_output_tokens']:
            raise ValueError('ABC_COMMON_OUTPUT_BUDGET_REQUIRED')
        return result

    def tool(self, body):
        with self.lock:
            self.ready()
            if self.tool_calls >= self.protocol['limits']['tool_calls']:
                raise ValueError('EPISODE_TOOL_LIMIT')
            self.tool_calls += 1
            self.event('tool_started', {'number': self.tool_calls, 'input': body})
            start = time.monotonic()
            try:
                self.validator.validate(body)
                result = self.handler(body)
                if len(encoded(result)) > self.protocol['limits']['tool_response_bytes']:
                    raise ValueError('TOOL_RESPONSE_BOUND')
                self.event('tool_completed', {'number': self.tool_calls, 'output': result,
                                               'wall_seconds': time.monotonic() - start})
                return result
            except Exception as error:
                self.event('tool_failed', {'number': self.tool_calls, 'error': type(error).__name__ + ': ' + str(error)[:1200],
                                           'wall_seconds': time.monotonic() - start})
                raise
