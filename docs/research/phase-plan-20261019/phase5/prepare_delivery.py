"""Assemble the explicitly scoped final delivery; originals stay read-only."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
OUT = ROOT / 'deliveries/BF_FINAL_20261020'
NODE = Path.home() / '.local/share/bf-agent-architecture-v2/workbench/design-lab/repository/node-realizations/NR-0c45b7c7be3cfbcf86bdb1b20e4702b657350ed0000feec09cc507948a3e6a78'


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def copy(p, destination):
    assert p.is_file() and not p.is_symlink(), p
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        assert sha(p) == sha(destination), destination
    else:
        shutil.copyfile(p, destination)
    return {'source': str(p), 'path': str(destination.relative_to(OUT)),
            'bytes': p.stat().st_size, 'sha256': sha(destination)}


def prepare():
    assert not OUT.exists(), 'DELIVERY_ALREADY_EXISTS'
    assert shutil.disk_usage(ROOT).free > 11_500_000_000
    OUT.mkdir(parents=True)
    bindings = []
    manifest = json.loads((NODE / 'manifest.json').read_text())
    assert sha(NODE / 'manifest.json') == '40e2b7535200c7db02ad92d07bfff5502f9e9b98515f78c809945909eee38e75'
    omitted = []
    for name, entry in manifest['outputs'].items():
        p = NODE / name
        assert sha(p) == entry['sha256'] and p.stat().st_size == entry['bytes'], name
        if name.startswith('target/objects/'):
            omitted.append({'path': name, **entry, 'reason': 'Rebuildable object file; fixed commands and ELF/HEX retained.'})
            continue
        bindings.append(copy(p, OUT / 'engineering/piezo-node' / name))
    bindings.append(copy(NODE / 'manifest.json', OUT / 'engineering/piezo-node/original-manifest.json'))
    save(OUT / 'engineering/piezo-node/omitted-rebuildable.json', omitted)
    # All source for the actual apparatus is small; caches, envs, secrets and SDKs are excluded.
    for folder in ['packages/python/bfworld/src', 'configs/studies', 'configs/reference_cases/node-engineering']:
        for p in sorted((APP / folder).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
                bindings.append(copy(p, OUT / 'source/battery-world' / p.relative_to(APP)))
    for name in ['pyproject.toml', 'requirements.lock']:
        bindings.append(copy(APP / name, OUT / 'source/battery-world' / name))
    for p in sorted((APP / 'scripts').glob('campaign*.py')):
        bindings.append(copy(p, OUT / 'source/battery-world/scripts' / p.name))
    for p in sorted((APP / 'papers/shared').rglob('*')):
        if p.is_file():
            bindings.append(copy(p, OUT / 'papers/shared' / p.relative_to(APP / 'papers/shared')))
    skill = APP.parent / 'pi-bf-aiot/packages/bf-harness/resources/skills/bf-engineering-report'
    if skill.is_dir():
        for p in sorted(skill.rglob('*')):
            if p.is_file():
                bindings.append(copy(p, OUT / 'source/bf-engineering-report' / p.relative_to(skill)))
    for name in ['node-engineering.html', 'node-engineering.css', 'node-engineering.js', 'model-viewer.js']:
        bindings.append(copy(APP / 'apps/agent-studio' / name, OUT / 'source/battery-world/apps/agent-studio' / name))
    for phase in range(1, 5):
        base = HERE.parent / f'phase{phase}'
        for name in ['result.json', 'RESULTS.md', 'source-manifest.json', 'preservation-final.json',
                     'actual-results.json', 'final-details.json', 'analysis-summary.json',
                     'final-integration.json', 'paper-readback.json', 'protocol-v1.1.json']:
            if (base / name).is_file():
                bindings.append(copy(base / name, OUT / f'evidence/phase{phase}' / name))
    engdoc = APP / 'docs/agentlab/architecture-v2/node-engineering-20261019'
    for name in ['RESULTS.json', 'REPORT.md', 'evidence/portable-rebuild.json', 'evidence/independent-check.json']:
        bindings.append(copy(engdoc / name, OUT / 'engineering/piezo-node/provenance' / name))
    ar = Path.home() / '.local/share/bf-phase1-20261020/a/ar-service/pi-episode-001'
    for p in sorted(ar.rglob('*')):
        rel = p.relative_to(ar)
        if p.is_file() and ('scientific' in rel.parts or 'external' in rel.parts or p.name in ['provider-costs.json', 'episode-result.json', 'protocol.json', 'closure.json']):
            bindings.append(copy(p, OUT / 'engineering/ar-failed-baseline' / rel))
    # Export billing facts only, never request payloads, keys, auth or provider config.
    dbpath = Path.home() / '.local/share/bf-campaign-20261019-s0/workbench/state/workbench.sqlite'
    with sqlite3.connect(dbpath.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        columns = {r[1] for r in db.execute('PRAGMA table_info(model_requests)')}
        selected = [n for n in ['id', 'owner', 'status', 'created', 'reserved', 'charged', 'usage', 'response_hash', 'error'] if n in columns]
        rows = [dict(row) for row in db.execute('SELECT ' + ','.join(selected) + ' FROM model_requests ORDER BY rowid')]
    save(OUT / 'billing/campaign-requests.json', {'scope': 'Original four-H campaign plus all phase1-4 requests; not all historical product or Codex billing.', 'rows': rows})
    save(HERE / 'source-bindings.json', bindings)
    save(HERE / 'initial-assembly.json', {'status': 'PREPARED', 'files': len(bindings), 'copied_bytes': sum(v['bytes'] for v in bindings), 'omitted_object_files': len(omitted), 'originals_unchanged': True, 'new_models_science_native': 0})
    print(json.dumps({'status': 'PREPARED', 'files': len(bindings), 'bytes': sum(v['bytes'] for v in bindings)}))


if __name__ == '__main__':
    prepare()
