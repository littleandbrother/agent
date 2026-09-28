#!/usr/bin/env python3
"""Preflight, explicit authorized provider trials, or read-only ledger recovery."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'packages/python/bfworld/src'))
from bfworld.campaign.budget import Ledger, BudgetStop
from bfworld.campaign.provider import Provider
from bfworld.campaign.repair import checked
from bfworld.campaign.live_trials import validate, run_matrix


def ledger_preflight(repo, *, dispatch):
    # Never create a replacement ledger in a launcher. Even the no-dispatch
    # preflight observes the exact existing account before loading credentials.
    path = repo/'.bfworld/paid-campaign/cost.sqlite'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
        calls, tokens, charged, unsettled = db.execute(
            'SELECT COUNT(*),COALESCE(SUM(COALESCE(tokens,token_bound)),0),'
            'COALESCE(SUM(COALESCE(charged,reserved)),0),SUM(state != ?) FROM calls', ('settled',)).fetchone()
    if dispatch and (unsettled or calls >= 120 or tokens >= 600000 or charged >= 19000000):
        raise BudgetStop('shared budget exhausted or uncertain; no new dispatch')
    return {'calls': calls, 'accounted_tokens': tokens, 'charged_or_reserved_micro_cny': charged,
            'unsettled': unsettled or 0, 'remaining_calls': 120-calls, 'remaining_tokens': 600000-tokens}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=REPO/'studies/b2-003/protocol-draft.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--key-file', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--reconcile-only', action='store_true')
    args = parser.parse_args()
    payload = json.loads(args.inputs.read_text()); protocol = json.loads(args.protocol.read_text())
    if 'content_hash' in payload:
        checked(payload); payload.pop('content_hash')
    if 'protocol' in payload:
        if payload.pop('protocol') != protocol:
            raise BudgetStop('input snapshot and supplied protocol differ')
    if set(payload) != {'plan', 'tasks', 'history', 'capsule', 'qualification'}:
        raise BudgetStop('exact bound trial input fields required')
    try:
        authority = validate(**payload, protocol=protocol, dispatch=not args.reconcile_only)
        if not args.reconcile_only and payload['plan']['purpose'] != 'formal-agent-trial':
            raise BudgetStop('CLI will not dispatch real calls for provider-control fixtures')
        current_budget = ledger_preflight(REPO, dispatch=not args.reconcile_only)
    except (BudgetStop, ValueError) as exc:
        print(json.dumps({'status': 'not-authorized', 'reason': str(exc), 'credentials_loaded': False, 'provider_calls': 0}))
        return 2
    if not args.execute and not args.reconcile_only:
        print(json.dumps({'status': 'preflight-ready-no-dispatch', 'authority': authority,
                          'current_shared_budget': current_budget, 'credentials_loaded': False, 'provider_calls': 0}))
        return 0
    if args.reconcile_only:
        db = sqlite3.connect((REPO/'.bfworld/paid-campaign/cost.sqlite').resolve().as_uri()+'?mode=ro', uri=True)
        ledger = SimpleNamespace(db=db, total=19_000_000, per_trial=2_000_000, max_calls=120, max_tokens=600_000)
        provider = SimpleNamespace(ledger=ledger)
    else:
        if args.key_file is None:
            raise BudgetStop('explicit key file required only after successful formal preflight')
        ledger = Ledger(REPO/'.bfworld/paid-campaign/cost.sqlite')
        try:
            provider = Provider(args.key_file, ledger)
        except BaseException:
            ledger.db.close(); raise
    try:
        result = run_matrix(**payload, protocol=protocol, repo=REPO, provider=provider,
                            root=args.output, reconcile_only=args.reconcile_only)
        print(json.dumps({'status': 'completed', 'report_hash': result['content_hash'],
                          'formal_agent_result': result['formal_agent_result'], 'cost': result['cost'],
                          'reconcile_only': args.reconcile_only, 'transfer_validated': False}))
        return 0
    finally:
        ledger.db.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (BudgetStop, ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({'status': 'stopped', 'reason': str(exc), 'no_automatic_retry': True})); sys.exit(2)
