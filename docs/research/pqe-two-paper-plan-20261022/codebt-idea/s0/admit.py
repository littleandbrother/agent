"""Install the directly approved exact liability and reload the idle ledger service."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request

from run import APP, DB, HERE, PACKAGE, ROOT, digest, save
from bfworld.agentlab import historical_usage as h

RUNTIME = DB.parents[2]


def rows_hash(db):
    return digest([dict(r) for r in db.execute('SELECT * FROM model_requests ORDER BY id')])


def main():
    receipt_path = HERE / 'science-admission.json'
    if receipt_path.exists():
        raise RuntimeError('ADMISSION_ALREADY_ATTEMPTED_READ_EXISTING_RECEIPT')
    stamp = time.time()
    authority = dict(id=h.CODEBT_AMENDMENT_ID, package=PACKAGE,
        request_id='llm-16cd5bfe95e06e92fd6d',
        authority='Direct human message 01a16d83-ad43-7ac0-9dca-40b0db56fb76 in thread 01a11b01-a75e-75c2-81c3-7d152a24f15a, freshly read by S0; exact exception and immediate frozen USD10 science.',
        preserve_original_status='UNKNOWN', preserve_reserved_usd=0.1025205,
        preserve_original_usage=None, original_request_retry_allowed=False,
        source_ledger_rewrite_allowed=False, new_missing_usage_stops=True)
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        for table in ('jobs', 'engineering_jobs', 'eda_cli_jobs'):
            assert not db.execute('SELECT 1 FROM '+table+" WHERE status IN ('RUNNING','STARTING','QUEUED','DISPATCHED')").fetchone(), table
        assert not db.execute("SELECT 1 FROM model_requests WHERE status='DISPATCHED'").fetchone()
        assert not db.execute('SELECT 1 FROM grants WHERE expires>?', (stamp,)).fetchone()
        before = rows_hash(db)
        previous = dict(db.execute('SELECT * FROM historical_usage_exceptions WHERE id=?', (h.AMENDMENT_ID,)).fetchone())
        h.install(db, authority, stamp)
        assert rows_hash(db) == before
        assert dict(db.execute('SELECT * FROM historical_usage_exceptions WHERE id=?', (h.AMENDMENT_ID,)).fetchone()) == previous
        assert len(h.verified_exceptions(db, PACKAGE)) == 2
        assert len(h.verified_exceptions(db, 'ANOTHER_PACKAGE')) == 1
        assert h.new_batch_usage_blockers(db, 'pi-chat-cf40305e2149b2b9')
        db.commit()
    old = json.loads((DB.parent / 'active-runtime.json').read_text())
    listener = subprocess.run(['/usr/sbin/lsof','-nP','-t','-iTCP:8980','-sTCP:LISTEN'], capture_output=True,text=True,check=True)
    assert listener.stdout.strip() == str(old['pid'])
    receipt = dict(status='EXACT_POLICY_INSTALLED_RELOADING_IDLE_SERVICE', at=datetime.now(timezone.utc).isoformat(),
        authority=authority, authorized_at=stamp, original_request_rows_sha256=before,
        original_rows_unchanged=True, old_r11_policy_unchanged=True, package_scope_checked=True,
        old_owner_still_blocked=True, original_request_retry=False, old_pid=old['pid'],
        old_cleanup_resumed=False, deletion_bytes=0, new_backups_environments_worktrees=0)
    save(receipt_path, receipt)
    os.kill(old['pid'], signal.SIGTERM)
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        try:
            os.kill(old['pid'], 0)
        except ProcessLookupError:
            break
        time.sleep(.1)
    else:
        raise RuntimeError('IDLE_SERVICE_NOT_STOPPED')
    profile = json.loads((RUNTIME / 'profile.json').read_text())
    env = {k:v for k,v in os.environ.items() if not k.startswith('BF_')}
    env.update(BF_RUNTIME_ROOT=str(RUNTIME), BF_RUNTIME_CONFIG=str(RUNTIME/'runtime.json'),
        BF_HOME=profile['home'], BF_PI_ROOT=profile['pi_root'],
        BF_DEVELOPMENT_PROFILE=str(RUNTIME/'profile.json'),
        PI_CODING_AGENT_DIR=str(Path(profile['home'])/'pi-config'),
        PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(APP/'packages/python/bfworld/src'))
    with (RUNTIME/'server.log').open('ab') as log:
        process = subprocess.Popen([profile['paths']['CAD_PYTHON'],'-B','-m','bfworld.agentlab.server',
            '--root',str(DB.parent),'--port','8980'],cwd=APP,env=env,
            stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
    receipt['new_pid'] = process.pid
    save(receipt_path, receipt)
    deadline = time.monotonic()+55
    while time.monotonic()<deadline:
        assert process.poll() is None, 'ACCOUNTING_SERVICE_RELOAD_FAILED'
        loaded = json.loads((DB.parent/'active-runtime.json').read_text())
        if loaded['pid'] == process.pid:
            expected = hashlib.sha256(Path(h.__file__).read_bytes()).hexdigest()
            assert loaded['historical_usage_source_sha256'] == expected
            try:
                with urllib.request.urlopen('http://127.0.0.1:8980/',timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
        time.sleep(.2)
    else:
        raise RuntimeError('SAME_RELOAD_PROCESS_READINESS_TIMEOUT')
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        assert rows_hash(db) == before
    receipt.update(status='EXACT_POLICY_ACTIVE_SCIENCE_PROVIDER_BINDING_NEXT',
        loaded_runtime=loaded, provider_requests=0, full_inputs=0)
    save(receipt_path,receipt)
    save(RUNTIME/'service-start.json',dict(pid=process.pid,port=8980,log=str(RUNTIME/'server.log')))
    print(json.dumps(dict(status=receipt['status'], original_rows_unchanged=True,
        historical_unknowns_preserved=2, new_pid=process.pid)))


if __name__ == '__main__':
    main()
