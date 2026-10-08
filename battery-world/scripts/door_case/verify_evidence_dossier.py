"""Offline verifier for the complete dossier, not a physical acceptance test."""
import hashlib
import json
import sys
from pathlib import Path

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify(root):
    seal=json.loads((root/'seal.json').read_text());b=json.loads((root/'report/baseline.json').read_text())
    for f in seal['files']:
        rel=Path(f['path']);p=root/rel
        if rel.is_absolute() or '..' in rel.parts or p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):raise ValueError('PATH_DENIED')
        if not p.is_file() or digest(p)!=f['sha256']:raise ValueError('FILE_CHANGED: '+f['path'])
    index=json.loads((root/'inputs/source-index.json').read_text())
    if json.loads((root/'report/source-index.json').read_text())!=index:raise ValueError('INDEX_MISMATCH')
    sources={f['path']:f for f in index['files']}
    all_hash=hashlib.sha256(json.dumps(sorted(index['files'],key=lambda x:x['path']),sort_keys=True).encode()).hexdigest()
    if all_hash!=b['source_identity'] or all_hash!=seal['source_identity']:raise ValueError('BASELINE_SOURCE_MISMATCH')
    for f in index['files']:
        if digest(root/'inputs'/f['path'])!=f['sha256']:raise ValueError('SOURCE_CHANGED')
    if [g['order'] for g in b['groups']]!=list(range(1,7)):raise ValueError('FIGURE_SEQUENCE')
    for g in b['groups']:
        if not g['question'] or not g['conclusion'] or not g['limitations']:raise ValueError('FIGURE_NARRATIVE_MISSING')
        deps=[sources[p] for p in g['dependencies']]
        h=hashlib.sha256(json.dumps(sorted(deps,key=lambda x:x['path']),sort_keys=True).encode()).hexdigest()
        if h!=g['source_identity']:raise ValueError('FIGURE_SOURCE_MISMATCH')
        if not (root/g['figure']).is_file() or not (root/g['vector']).is_file():raise ValueError('FIGURE_MISSING')
    if b['product_accepted'] or b['hardware_verified'] or b['autonomous_agent_verified']:raise ValueError('CLAIM_DRIFT')
    return dict(status='passed',figure_groups=6,files=len(seal['files']),source_identity=b['source_identity'],product_accepted=False,scope='Evidence archive integrity and narrative, not physical design acceptance')

if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1])),ensure_ascii=False))
