#!/usr/bin/env python3
"""Build the independent paper twice. Asset rendering is a separate saved-data command."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def main():
    scratch = HERE / '.build'
    scratch.mkdir(exist_ok=True)
    tex = shutil.which('pdflatex') or '/Library/TeX/texbin/pdflatex'
    commands = []
    for i in range(1, 3):
        cmd = [tex, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', '-output-directory=.build', 'main.tex']
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '1792454400', 'FORCE_SOURCE_DATE': '1'})
        commands.append({'pass': i, 'argv': cmd, 'exit_code': p.returncode})
        if p.returncode:
            print(p.stdout[-8000:]); raise SystemExit(p.returncode)
    log = (scratch / 'main.log').read_text(errors='replace')
    warnings = re.findall(r'^(?:.*Warning.*|Overfull.*|Underfull.*|Missing character.*)$', log, re.M)
    assert not any('Overfull' in x or 'undefined' in x.lower() or 'Missing character' in x for x in warnings), warnings
    shutil.copyfile(scratch / 'main.pdf', HERE / 'main.pdf')
    info = subprocess.check_output(['/opt/homebrew/bin/pdfinfo', str(HERE / 'main.pdf')], text=True)
    fonts = subprocess.check_output(['/opt/homebrew/bin/pdffonts', str(HERE / 'main.pdf')], text=True)
    assert 'Type 3' not in fonts, fonts
    receipt = {'schema': 'bf-abc-C-paper-build-v1', 'commands': commands, 'passes': 2,
               'warnings_final_pass': warnings, 'pdfinfo': info, 'pdffonts': fonts,
               'scope': 'LaTeX/PDF compilation only; visual and scientific review recorded separately.'}
    (HERE / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'passes': 2, 'warnings': warnings, 'pdf_bytes': (HERE/'main.pdf').stat().st_size}))


if __name__ == '__main__':
    main()
