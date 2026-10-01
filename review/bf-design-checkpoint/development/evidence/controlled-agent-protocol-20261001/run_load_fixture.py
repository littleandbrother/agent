#!/usr/bin/env python3
"""Emit evidence for bundled trusted fixtures, with supervisor-pinned identities."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from preflight import activation_errors, file_digest

ROOT=Path(__file__).resolve().parent
rows=[]
for name in ('h0','h1','h0'):
    nonce=secrets.token_hex(16)
    source_hash=file_digest(ROOT/'fixtures'/(name+'.py'))
    expected={'harness_source_hash':source_hash,'harness_build_hash':source_hash,
        'controller_hash':file_digest(ROOT/'fixture_load_probe.py'),'nonce':nonce,
        'entrypoint':'plan','loaded_modules':{'trusted_load_fixture':source_hash},'author_pid':os.getpid()}
    with tempfile.TemporaryDirectory() as temp:
        process=subprocess.run([sys.executable,'-I','-S',str(ROOT/'fixture_load_probe.py'),name,nonce],
            cwd=temp,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,timeout=5)
    if process.returncode: raise RuntimeError(process.stderr)
    observed=json.loads(process.stdout);observed['exit_code']=process.returncode
    errors=activation_errors(observed,expected)
    if errors: raise RuntimeError(errors)
    rows.append({'fixture':name,'expected_before_launch':expected,'observed':observed,'errors':errors})
print(json.dumps({'schema_version':'bf-trusted-load-fixture-v1','purpose':'offline-contract-tests',
    'participant_runtime_qualified':False,'participant_authorship_proven':False,'provider_calls':0,
    'rows':rows,'rollback_hash_and_behavior_restored':all(rows[0]['observed'][k]==rows[2]['observed'][k]
        for k in ('harness_source_hash','harness_build_hash','invocation_output_hash'))},indent=2))
