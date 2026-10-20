"""Generate a source-bound target control-flow supplement, without execution."""
from pathlib import Path
import hashlib
import html
import json
import re


def generate(node):
    source = node / 'target-source/main.c'
    raw = source.read_bytes()
    lines = raw.decode().splitlines()
    constants = {}
    for name in ['T_ARM_MS', 'T_PERIOD_MS', 'T_SAMPLE_MS', 'T_TX_MAX_MS',
                 'T_PROBE_MS', 'VDD_ADMIT_MIN_MV', 'VDD_SERVICE_MIN_MV']:
        match = re.search(r'^#define\s+' + name + r'\s+(\d+)u', raw.decode(), re.M)
        assert match, name
        constants[name] = int(match[1])
    spans = {'constants': [93, 100], 'frame_finish': [392, 401],
             'frame_step': [403, 449], 'supply_abort': [451, 474],
             'admission': [513, 529], 'main': [532, 569]}
    evidence = {'schema_version': 'bf-target-source-control-flow-v1',
                'system_id': json.loads((node / 'input.json').read_text())['system_id'],
                'source': 'target-source/main.c', 'source_sha256': hashlib.sha256(raw).hexdigest(),
                'constants': constants, 'source_spans': {},
                'boundary': 'Control flow and configured bounds from saved target source; no target execution, RF receipt or measured hardware timing.'}
    for key, (start, end) in spans.items():
        evidence['source_spans'][key] = {'first_line': start, 'last_line': end,
            'sha256': hashlib.sha256(('\n'.join(lines[start-1:end]) + '\n').encode()).hexdigest()}
    c = constants
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="650" viewBox="0 0 1300 650">',
           '<rect width="1300" height="650" fill="white"/>',
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#264b70"/></marker></defs>',
           '<g font-family="Arial, sans-serif" fill="#18354f">']
    def text(x, y, value, size=19, weight='normal'):
        svg.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}">{html.escape(str(value))}</text>')
    def box(x, y, w, h, title, body, color='#edf4f9'):
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{color}" stroke="#7995aa"/>')
        text(x+16, y+31, title, 18, 'bold')
        for i, line in enumerate(body): text(x+16, y+61+25*i, line, 15)
    def arrow(path): svg.append(f'<path d="{path}" fill="none" stroke="#264b70" stroke-width="2.4" marker-end="url(#arrow)"/>')
    text(35, 37, 'nRF52832 target control flow', 28, 'bold')
    text(35, 68, 'Saved source; configured bounds only. Hardware and RF timing remain unmeasured.', 19)
    box(35, 102, 285, 135, 'Initialize / re-admit', ['Stack, timer, SAADC, advertising', 'On reset: no NVM state', f'PGOOD and VDD >= {c["VDD_ADMIT_MIN_MV"]} mV'])
    box(365, 102, 275, 135, 'PH_IDLE: scheduled slot', [f'First slot: +{c["T_ARM_MS"]} ms', 'seq++; sample temperature', 'Read VDD; set status flags'])
    box(685, 102, 245, 135, 'PH_SAMPLE', [f'Window: {c["T_SAMPLE_MS"]} ms from slot', 'Build payload: seq, value, CRC', f'Service threshold: {c["VDD_SERVICE_MIN_MV"]} mV'])
    box(975, 102, 290, 135, 'PH_TX', ['Start only with supply flags clear', 'One advertising event', f'Completion event or {c["T_TX_MAX_MS"]} ms bound'])
    arrow('M 320 169 L 365 169'); arrow('M 640 169 L 685 169'); arrow('M 930 169 L 975 169')
    text(325, 145, 'admit', 15)
    arrow('M 1120 237 L 1120 282 L 502 282 L 502 237')
    text(630, 273, f'Stop TX; PH_IDLE; advance scheduled slot by {c["T_PERIOD_MS"]} ms', 18)
    box(365, 335, 565, 130, 'PGOOD lost during SAMPLE or TX', ['On the next wake: cancel window and stop active advertising', 'Mark skipped / aborted; PH_IDLE; advance exactly one period', 'Detection depends on wake-up; hardware latency unmeasured'], '#fff4e3')
    arrow('M 808 237 L 808 248 M 808 290 L 808 335'); arrow('M 1120 237 L 1120 400 L 930 400')
    arrow('M 365 400 L 340 400 L 340 260 L 502 260')
    text(35, 515, f'Admission wait: PGOOD GPIO sense and {c["T_PROBE_MS"]} ms probe; sleep with sd_app_evt_wait().', 19)
    text(35, 548, 'Actual BLE event duration differs from the host reference TX window; advertising start is not receiver delivery.', 19)
    text(35, 581, 'Source: target-source/main.c, lines 93-100, 392-474, 513-569. SHA-256 bound in target-control-flow.json.', 18)
    text(35, 617, 'No new build, simulation, native design revision or hardware execution was performed for this diagram.', 18)
    svg.append('</g></svg>\n')
    return '\n'.join(svg), evidence


if __name__ == '__main__':
    node = Path(__file__).resolve().parent
    svg, evidence = generate(node)
    (node / 'target-control-flow.svg').write_text(svg)
    (node / 'target-control-flow.json').write_text(json.dumps(evidence, indent=2) + '\n')
