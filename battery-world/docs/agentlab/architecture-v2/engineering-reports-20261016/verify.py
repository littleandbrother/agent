#!/usr/bin/env python3
"""Verify report identity, PDF structure, source integrity and state preservation."""
import hashlib
import json
from pathlib import Path
import tempfile

from pypdf import PdfReader
from PIL import Image, ImageDraw, ImageFont
import collect
import render

ROOT = Path(__file__).resolve().parent


def check(label, passed):
    if not passed:
        raise AssertionError(label)
    return {'check': label, 'status': 'PASS'}


def main():
    checks = []
    data = render.verified_input(ROOT/'input')
    checks.append(check('all 108 source asset hashes match the selected candidate', len(data['assets']) == 108))
    checks.append(check('report selects submitted revision and keeps adopted identity separate',
                        data['selection'] == 'submitted' and data['current_system'] == data['system']['id']
                        and data['system']['id'] != data['adopted_system']))
    facts = render.source_facts(data, ROOT/'input')
    power = facts['power']
    raw_job = next(j for j,v in data['system']['jobs'].items() if 'project-trace.raw' in v['artifacts'])
    raw = render.raw_channels(ROOT/'input/sources/jobs'/raw_job/'project-trace.raw')
    checks.append(check('RAW point count and storage endpoints match independent result',
        len(raw['time']) == power['points'] and
        all(abs(a-b) < 1e-8 for a,b in zip([raw['v(storage_rail)'][0], raw['v(storage_rail)'][-1]], power['storage_v']))))
    checks.append(check('RAW supply minimum matches independent result',
        abs(min(raw['v(supply_1v8)'])-power['minimum_supply_v']) < 1e-8))

    artifacts = []
    pdf_specs = [('P01_简版八页报告_模板样稿.pdf', 8), ('P01_详版技术报告_模板样稿.pdf', 12)]
    for name, pages in pdf_specs:
        pdf = ROOT/'output/pdf'/name
        reader = PdfReader(pdf)
        all_text = '\n'.join(page.extract_text() for page in reader.pages)
        checks.append(check(name+': correct page count and extractable Chinese text',
            len(reader.pages) == pages and '供能' in all_text and '待补' in all_text and '未进行' in all_text))
        checks.append(check(name+': selected version is printed on every page',
            all(data['system']['id'][:11] in page.extract_text() for page in reader.pages)))
        checks.append(check(name+': embedded fonts',
            all(any('/FontFile2' in font.get_object().get('/FontDescriptor', {})
                    for font in page['/Resources']['/Font'].get_object().values()) for page in reader.pages)))
        checks.append(check(name+': no replacement glyphs or fictional template values',
            all(token not in all_text for token in ('\ufffd', 'XXX', 'STM32L0', 'SX1262', '0.5 g'))))
        layout = json.loads(pdf.with_suffix('.layout.json').read_text())
        w,h = layout['size']
        outside = [b for b in layout['bounds'] if b['x'] < 0 or b['y'] < 0 or
                   b['x']+b['w'] > w+.2 or b['y']+b['h'] > h-12]
        checks.append(check(name+': text inside page boundaries', not outside))
        artifacts.append({'path':str(pdf.relative_to(ROOT)), 'pages':pages, 'bytes':pdf.stat().st_size,
                          'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()})

    inventory = json.loads((ROOT/'asset-inventory.json').read_text())
    checks.append(check('missing content remains assigned in the inventory',
        len(inventory['tasks']) == 11 and len(inventory['pages']) == 8))
    checks.append(check('old firmware event source mismatch is detected and assigned',
        len(inventory['historical_event_record_stale_inputs']) == 3 and
        any(t['id'] == 'R07' for t in inventory['tasks'])))

    for failure in ('ASSET_HASH_MISMATCH', 'ASSET_CANDIDATE_MISMATCH'):
        with tempfile.TemporaryDirectory(prefix='bf-report-negative-') as temp:
            folder = Path(temp)
            one = next(a for a in data['assets'] if a['bytes'] < 4096)
            target = folder/one['local_path']; target.parent.mkdir(parents=True)
            target.write_bytes((ROOT/'input'/one['local_path']).read_bytes())
            record = {**data, 'assets':[dict(one)]}
            if failure == 'ASSET_HASH_MISMATCH':
                target.write_bytes(b'tampered test input')
            else:
                record['assets'][0]['system_commit'] = 'SC-wrong-test-identity'
            (folder/'report-input.json').write_text(json.dumps(record))
            rejected = False
            try:
                render.verified_input(folder)
            except ValueError as error:
                rejected = str(error).startswith(failure)
            checks.append(check('negative control: '+failure+' rejected', rejected))

    preview_meta = json.loads((ROOT/'output/native-previews/native-previews.json').read_text())
    for item in preview_meta['items']:
        source = ROOT/'input/sources/previews'/item['source']
        derived = ROOT/'output/native-previews'/item['output']
        checks.append(check('native rendering source/output: '+item['source'],
            hashlib.sha256(source.read_bytes()).hexdigest() == item['source_sha256'] and
            hashlib.sha256(derived.read_bytes()).hexdigest() == item['output_sha256']))

    before = json.loads((ROOT/'input/protected-before.json').read_text())
    after = collect.protected_state()
    (ROOT/'verification').mkdir(exist_ok=True)
    (ROOT/'verification/protected-final.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n')
    checks.append(check('original sessions, billing fields, jobs, V2 design state and native project preserved', before == after))

    for kind, count, columns in [('simple',8,2), ('detail',12,3)]:
        images = sorted((ROOT/'tmp/pdfs'/kind).glob('final-*.png'))
        checks.append(check(kind+': every page rendered for visual review', len(images) == count))
        cell_w = 600 if kind == 'simple' else 360
        cell_h = 462 if kind == 'simple' else 557
        contact = Image.new('RGB',(columns*cell_w, ((count+columns-1)//columns)*cell_h),'#E5ECF3')
        painter = ImageDraw.Draw(contact)
        for i,source in enumerate(images):
            im = Image.open(source).convert('RGB')
            im.thumbnail((cell_w-16,cell_h-34))
            x=(i%columns)*cell_w+(cell_w-im.width)//2; y=(i//columns)*cell_h+22
            contact.paste(im,(x,y));painter.text(((i%columns)*cell_w+8,(i//columns)*cell_h+6),str(i+1),fill='#102C4B')
        contact.save(ROOT/'output'/f'{kind}-contact-sheet.jpg',quality=94)

    result = {'status':'PASS','scope':'P01 report template proof', 'system_commit':data['system']['id'],
              'checks':checks,'check_count':len(checks),'artifacts':artifacts,
              'assets_verified':len(data['assets']), 'new_model_requests':0, 'new_engineering_jobs':0,
              'native_project_changed':False, 'original_billing_changed':False,
              'skill_status':'draft for review; not installed',
              'visual_review_record':'verification/visual-review.json'}
    (ROOT/'verification/result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','check_count','assets_verified','system_commit')}))


if __name__ == '__main__':
    main()
