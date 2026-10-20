"""Publish only the two previously human-authorized Overleaf manuscripts.

Credential helpers are reused without reading, printing or storing credentials.
The source/application repositories are never committed. Existing unrelated
Overleaf template/history files remain. No fresh clone/worktree is needed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
APP = ROOT / 'workbench/bf-campaign-s0-20261019/battery-world'
SPECS = {'rsi': ('method-reexecution-20261019', '6ad5fb6e87c3ac6782d05b2c'),
         'interface': ('interface-sufficiency-20261019', '6ad5fbda856b284d5d917ffd')}


def run(argv, cwd=None, timeout=60):
    result = subprocess.run(argv, cwd=cwd, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'},
                            capture_output=True, timeout=timeout)
    if result.returncode:
        # Git stderr can contain a configured sensitive URL; do not expose it.
        if argv[0] == 'pdflatex':
            raise RuntimeError(result.stdout.decode(errors='replace')[-2500:])
        raise RuntimeError(f'{argv[0]} {argv[1]} failed, exit {result.returncode}')
    return result.stdout


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pdf_words(p):
    extracted = run(['pdftotext', '-bbox-layout', str(p), '-']).decode()
    # Poppler can emit C0 character codes for valid mathematical glyphs.
    # Encode their identities reversibly instead of dropping words or positions.
    extracted = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',
        lambda match: f'__PDF_CONTROL_U{ord(match[0]):04X}__', extracted)
    root = ET.fromstring(extracted)
    return [{'dimensions': dict(page.attrib), 'words': [[dict(w.attrib), w.text]
        for w in page.iter() if w.tag.rsplit('}', 1)[-1] == 'word']}
        for page in root.iter() if page.tag.rsplit('}', 1)[-1] == 'page']


def write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def prepare(key, entry, reference):
    folder, project = SPECS[key]
    source = APP / 'papers' / folder / 'final'
    checkout = Path.home() / '.local/share/bf-agent-manuscripts/overleaf' / project
    receipt = HERE / 'publication' / key / 'prepared.json'
    assert not receipt.exists(), 'ALREADY_PREPARED'
    assert not run(['git', 'status', '--porcelain'], checkout).strip(), 'DIRTY_OVERLEAF_CHECKOUT'
    previous = run(['git', 'rev-parse', 'HEAD'], checkout).decode().strip()
    remote = run(['git', 'ls-remote', 'origin', 'HEAD'], checkout).decode().split()[0]
    assert previous == remote, 'OVERLEAF_HAS_NEW_REMOTE_CHANGES'
    assert (source / entry).is_file() and (source / reference).is_file()
    selected = []
    # TeX and actual figure assets only. Saved raw runs, billing and full datasets
    # are part of the local portable package, not pushed to Overleaf.
    for p in sorted(source.rglob('*')):
        rel = p.relative_to(source)
        if not p.is_file() or p.name == reference or any(v in rel.parts for v in ['data', 'qa', 'tmp', '__pycache__']):
            continue
        if p.suffix not in ['.tex', '.bib', '.sty', '.pdf', '.png', '.jpg', '.jpeg', '.svg', '.eps']:
            continue
        if p.suffix in ['.tex', '.bib', '.sty', '.svg']:
            assert not re.search(rb'(?:olp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{24,}|Bearer\s+[A-Za-z0-9._-]{12,})', p.read_bytes()), 'SECRET_LITERAL_IN_PUBLICATION'
        dest = checkout / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
        selected.append(str(rel))
    # Existing Overleaf entry is preserved as a tiny wrapper around the final
    # paper's real entry so its relative figure paths remain the same.
    (checkout / 'example_paper.tex').write_text('\\input{' + entry + '}\n')
    selected.append('example_paper.tex')
    with tempfile.TemporaryDirectory(prefix='bf-final-overleaf-') as tmp:
        scratch = Path(tmp)
        for iteration in [1, 2]:
            result = subprocess.run(['pdflatex', '-recorder', '-interaction=nonstopmode', '-halt-on-error',
                '-output-directory=' + str(scratch), 'example_paper.tex'], cwd=checkout,
                capture_output=True, timeout=60)
            (receipt.parent / f'build-{iteration}.log').parent.mkdir(parents=True, exist_ok=True)
            (receipt.parent / f'build-{iteration}.log').write_bytes(result.stdout)
            if result.returncode:
                raise RuntimeError('OVERLEAF_PORTABLE_ENTRY_BUILD_FAILED; exact log retained')
        log = (scratch / 'example_paper.log').read_text(errors='replace')
        material = [line for line in log.splitlines() if any(x in line for x in
            ['Overfull', 'Missing character', 'undefined references', 'undefined citations', 'multiply defined'])]
        assert not material, material
        built = scratch / 'example_paper.pdf'
        assert pdf_words(built) == pdf_words(source / reference), 'OVERLEAF_LAYOUT_DIFFERS_FROM_REVIEWED_FINAL_PDF'
        fonts = run(['pdffonts', str(built)]).decode().splitlines()[2:]
        assert fonts and all(len(v.split()) >= 8 and v.split()[-5] == 'yes' for v in fonts), 'UNEMBEDDED_FONT'
        shutil.copyfile(built, checkout / 'example_paper.pdf')
        selected.append('example_paper.pdf')
    info = {'schema_version': 'bf-final-overleaf-source-v1', 'project': project,
            'scope': 'Final manuscript source and figure assets only; no raw research logs, credentials or billing data.',
            'local_final_entry': entry, 'local_reference_pdf_sha256': sha(source / reference),
            'files': {name: sha(checkout / name) for name in selected},
            'cloud_compile_verified': False}
    (checkout / 'phase5-publication.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n')
    selected.append('phase5-publication.json')
    run(['git', 'diff', '--check'], checkout)
    write(receipt, {'status': 'PASS', 'at': datetime.now(timezone.utc).isoformat(), 'key': key,
        'project': project, 'checkout': str(checkout), 'previous_head': previous,
        'selected_files': selected, 'sha256': {name: sha(checkout / name) for name in selected},
        'actual_local_build_passes': 2, 'all_word_positions_and_page_dimensions_equal': True,
        'bbox_parser': 'XML-forbidden C0 glyph codes preserved as explicit code-point escape words',
        'all_fonts_embedded': True, 'pages': len(pdf_words(source / reference)),
        'source_reference_pdf': str(source / reference), 'cloud_compile_verified': False,
        'temporary_build_removed': True})
    print(json.dumps({'status': 'PREPARED', 'key': key, 'files': len(selected), 'project': project}))


def publish(key):
    receipt = HERE / 'publication' / key / 'prepared.json'
    data = json.loads(receipt.read_text())
    target = receipt.with_name('published.json')
    assert not target.exists(), 'ALREADY_PUBLISHED'
    checkout = Path(data['checkout'])
    assert run(['git', 'rev-parse', 'HEAD'], checkout).decode().strip() == data['previous_head']
    for name, digest in data['sha256'].items():
        assert sha(checkout / name) == digest, ('SOURCE_CHANGED_AFTER_REVIEW', name)
    branch = run(['git', 'symbolic-ref', '--short', 'HEAD'], checkout).decode().strip()
    run(['git', 'add', '--', *data['selected_files']], checkout)
    run(['git', 'diff', '--cached', '--check'], checkout)
    staged = run(['git', 'diff', '--cached', '--name-only'], checkout).decode().splitlines()
    assert staged and set(staged).issubset(set(data['selected_files'])), 'UNRELATED_STAGED_FILES'
    run(['git', 'commit', '-m', 'Finalize BF ' + key + ' manuscript, evidence tables and HKUST-GZ layout'], checkout)
    head = run(['git', 'rev-parse', 'HEAD'], checkout).decode().strip()
    run(['git', 'push', 'origin', 'HEAD:' + branch], checkout, timeout=90)
    remote = run(['git', 'ls-remote', 'origin', 'refs/heads/' + branch], checkout).decode().split()[0]
    assert head == remote, 'REMOTE_HEAD_MISMATCH'
    run(['git', 'fetch', '--no-tags', 'origin', branch], checkout, timeout=90)
    assert run(['git', 'rev-parse', 'FETCH_HEAD'], checkout).decode().strip() == head
    for name, digest in data['sha256'].items():
        assert hashlib.sha256(run(['git', 'show', 'FETCH_HEAD:' + name], checkout)).hexdigest() == digest, name
    assert not run(['git', 'status', '--porcelain'], checkout).strip(), 'UNRELATED_OR_DIRTY_FILES'
    write(target, {'status': 'PASS', 'project': data['project'], 'head': head, 'remote_head': remote,
        'branch': branch, 'readback_files': len(data['sha256']), 'remote_tree_readback': 'PASS',
        'local_compile': 'PASS_SAME_LAYOUT_AS_REVIEWED_PDF', 'cloud_compile_verified': False,
        'root_or_source_repositories_committed': False, 'at': datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'status': 'PUBLISHED_AND_READ_BACK', 'key': key, 'head': head}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'publish'])
    parser.add_argument('key', choices=list(SPECS))
    parser.add_argument('--entry', default='main.tex')
    parser.add_argument('--reference', default='main.pdf')
    args = parser.parse_args()
    prepare(args.key, args.entry, args.reference) if args.action == 'prepare' else publish(args.key)
