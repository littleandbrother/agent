"""Generate only the five title words from pinned Inter 4.1 outlines.

Usage: python scripts/generate_runtime_title_font.py /path/to/Inter-Regular.woff2 /path/to/LICENSE.txt
Requires fontTools 4.61.1 and Node.js. No system font installation is performed.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace
from fontTools.ttLib import TTFont, woff2
from fontTools.pens.basePen import BasePen


class OutlinePen(BasePen):
    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.commands = []
        self.first = None

    def add(self, command, *points):
        self.commands.append(command)
        self.commands.extend(f'{v:.3f}'.rstrip('0').rstrip('.') for point in points for v in point)

    def _moveTo(self, point):
        self.first = point
        self.add('m', point)

    def _lineTo(self, point):
        self.add('l', point)

    def _curveToOne(self, c1, c2, point):
        self.add('b', point, c1, c2)

    def _qCurveToOne(self, control, point):
        self.add('q', point, control)

    def _closePath(self):
        if self.first is not None:
            self.add('l', self.first)

    def _endPath(self):
        pass


source, license_path = map(Path, sys.argv[1:3])
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
expected = 'e06f6b1bc553aaea4e4668023ed0ab0a147129c3107f511bc7d03d361b0ae085'
if source_hash != expected:
    raise SystemExit('Pinned Inter source hash differs')
# Decode the static, overlap-free upstream webfont. Node's built-in Brotli
# decoder avoids adding a Python native extension just for this build step.
if not woff2.haveBrotli:
    def decompress(payload):
        code = "const z=require('node:zlib'),f=require('node:fs');process.stdout.write(z.brotliDecompressSync(f.readFileSync(0)));"
        return subprocess.run(['node', '-e', code], input=payload, capture_output=True, check=True).stdout
    woff2.brotli = SimpleNamespace(decompress=decompress)
    woff2.haveBrotli = True
font = TTFont(source)
characters = sorted(set('MechanicalCircuitPCBPowerFirmware? '))
glyph_set, cmap = font.getGlyphSet(), font.getBestCmap()
glyphs = {}
for char in characters:
    name = cmap[ord(char)]
    pen = OutlinePen(glyph_set)
    glyph_set[name].draw(pen)
    glyphs[char] = {'ha': font['hmtx'][name][0], 'o': ' '.join(pen.commands)}
cap_height = font['OS/2'].sCapHeight
data = {
    'familyName': 'BF Studio Sans',
    'glyphs': glyphs,
    'resolution': cap_height,
    'boundingBox': {'yMin': font['head'].yMin, 'yMax': font['head'].yMax},
    'underlineThickness': font['post'].underlineThickness,
    'bf_source': {
        'font': 'Inter Regular', 'release': '4.1', 'weight': 400,
        'url': 'https://raw.githubusercontent.com/rsms/inter/v4.1/docs/font-files/Inter-Regular.woff2',
        'upstream_sha256': source_hash,
        'subset': 'Five workstation titles; renamed derivative under SIL OFL 1.1',
    },
    'license': license_path.read_text(),
}
target = Path(__file__).resolve().parents[1] / 'apps/agent-studio/runtime-scene/src/fonts/inter-titles.json'
target.write_text(json.dumps(data, separators=(',', ':')) + '\n')
print(f'Generated {len(glyphs)} glyphs from Inter 4.1')
