#!/usr/bin/env python3
"""Package explicit public R0-R2 evidence and code, not private runtime state."""
import hashlib
import json
from pathlib import Path
import re
import time
import zipfile

APP = Path(__file__).resolve().parents[2]
STAGE = APP.parent
ROOT = STAGE.parents[1]
OUT = APP / 'docs/agentlab/refactor-r0-r2-20261011'
DEST = ROOT / 'workbench/review-packages/BF_Agent_R0-R2_C_Acceptance_20261012.zip'
if DEST.exists():
    raise RuntimeError('REVIEW_PACKAGE_ALREADY_EXISTS; preserve the existing package and choose a new release name')
selected = {}
def add(path, name):
    assert path.is_file(), str(path)
    assert name not in selected, name
    selected[name] = path

add(APP / 'docs/agentlab/DESIGN-LAB-R0-R2-20261011.md', '01_IMPLEMENTATION_AND_ACCEPTANCE.md')
add(ROOT / 'workbench/review-packages/BF_Agent_Refactor_Implementation_Plan_20261011.md', '02_APPROVED_PLAN.md')
base = APP / 'packages/python/bfworld/src/bfworld/agentlab'
for p in sorted((base / 'design_lab').glob('*.py')):
    add(p, 'current-code/battery-world/' + str(p.relative_to(APP)))
for name in ('server.py', 'chat.py', 'launcher.py', 'budget_policy.py', 'recovery.py', 'provider.py',
             'model_profile.py', 'context.py', 'skill_resources.py', 'engineering_projects.py'):
    add(base / name, 'current-code/battery-world/' + str((base / name).relative_to(APP)))
for directory, pattern in [('scripts/design_lab', '*.py'), ('configs/reference_cases/design-lab', '*')]:
    for p in sorted((APP / directory).rglob(pattern)):
        if p.is_file():
            add(p, 'current-code/battery-world/' + str(p.relative_to(APP)))
for name in ('test_design_lab.py', 'test_design_execution.py', 'test_design_resources.py',
             'test_unbounded_budget.py', 'test_context_recovery.py', 'test_product.py', 'test_product_authority.py'):
    add(APP / 'tests/agentlab' / name, 'current-code/battery-world/tests/agentlab/' + name)
add(APP / 'project/features/BFA-035-dot-integration-pilot/design-lab-r0-r2.json', 'current-code/feature.json')
for name in ('design-lab.html', 'design-lab.js', 'design-lab.css', 'index.html'):
    add(APP / 'apps/agent-studio' / name, 'current-code/battery-world/apps/agent-studio/' + name)
for name in ('src/design-task.ts', 'src/extensions/bf-design.ts', 'src/chat-product.ts'):
    add(STAGE / 'pi-bf-aiot/packages/bf-agent' / name, 'current-code/pi-bf-aiot/packages/bf-agent/' + name)
for p in sorted(OUT.rglob('*')):
    if not p.is_file() or p.suffix not in ('.json', '.jsonl', '.log', '.py', '.ts', '.js', '.md', '.zip', '.jpg', '.html'):
        continue
    rel = p.relative_to(OUT)
    # Exact provider wire dumps are bulky; private original SDK traces are
    # outside OUT and never selected. Keep filtered public trace and identities.
    if p.name == 'model-wire-evidence.json' or p.name.startswith('package-'):
        continue
    add(p, 'evidence/' + str(rel))

def audit(value, path):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('apiKey', 'api_key', 'access_token', 'reasoning_content', 'thinkingSignature') and item:
                raise RuntimeError('PRIVATE_FIELD_DENIED:' + path + ':' + key)
            if key in ('token', 'authorization', 'Authorization') and isinstance(item, str) and item:
                raise RuntimeError('CREDENTIAL_FIELD_DENIED:' + path + ':' + key)
            audit(item, path)
    elif isinstance(value, list):
        for item in value:
            audit(item, path)

records = []
for name, path in selected.items():
    data = path.read_bytes()
    if path.suffix == '.json':
        audit(json.loads(data), name)
    elif path.suffix == '.jsonl':
        for line in data.decode().splitlines():
            audit(json.loads(line), name)
    if path.suffix in ('.log', '.md') and re.search(rb'(?:sk-[A-Za-z0-9]{24,}|Bearer [A-Za-z0-9._-]{24,})', data):
        raise RuntimeError('POSSIBLE_CREDENTIAL_DENIED:' + name)
    records.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
manifest = {'schema_version': 'bf-public-refactor-review-package-v1', 'time': time.time(),
    'files': records, 'private_runtime_and_reasoning_included': False,
    'claim': 'Finite C acceptance and implementation evidence; complete hardware, full root health and RSI not granted.'}
DEST.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(DEST, 'x', compression=zipfile.ZIP_DEFLATED) as z:
    for name, path in selected.items():
        z.write(path, name)
    z.writestr('MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
with zipfile.ZipFile(DEST) as z:
    assert z.testzip() is None
    frozen = json.loads(z.read('MANIFEST.json'))
    for entry in frozen['files']:
        data = z.read(entry['path'])
        assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256']
receipt = {'schema_version': 'bf-public-review-package-receipt-v1', 'time': time.time(),
    'path': str(DEST), 'bytes': DEST.stat().st_size,
    'sha256': hashlib.sha256(DEST.read_bytes()).hexdigest(), 'files_verified': len(records),
    'crc_verified': True, 'all_member_sha256_verified': True,
    'private_runtime_included': False, 'model_calls': 0, 'native_solver_calls': 0}
dest = OUT / ('package-' + str(time.time_ns()) + '.json')
dest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
print(json.dumps(receipt, ensure_ascii=False))
