"""Contract tests; fixture numbers are rendering inputs, never physics evidence."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from types import SimpleNamespace

from bfworld.agentlab.scientific_figures import SCHEMA, validate_plan, request, public_response
from bfworld.agentlab.runtime_config import CAD
from tests.agentlab import test_product_results as fixtures


def plan(source):
    sources = [{'id': 'wave', 'path': 'wave.csv', 'sha256': hashlib.sha256(source).hexdigest(),
                'columns': {'time_s': 's', 'voltage_V': 'V'}, 'origin': 'fixture', 'scope': 'Rendering fixture, not physics.'}]
    panels = [{'id': '1a', 'label': 'a', 'title': 'Fixture voltage', 'question': 'Are declared units preserved?',
               'caption': 'Two fixture values; no device claim.', 'evidence_kind': 'fixture', 'dependencies': ['wave'],
               'status': 'available', 'type': 'line', 'series': [{'source': 'wave', 'x': 'time_s', 'y': 'voltage_V', 'x_unit': 'ms', 'y_unit': 'mV'}]},
              {'id': '1b', 'label': 'b', 'title': 'Missing measurement', 'question': 'Is missing evidence retained?',
               'caption': 'No hardware measured.', 'evidence_kind': 'gap', 'dependencies': ['wave'],
               'status': 'missing', 'reason': 'No measurement, do not invent error bars.'}]
    return {'schema_version': SCHEMA, 'title': 'Rendering contract fixture', 'version': 'F1',
            'conclusion': 'No physical qualification.', 'sources': sources,
            'groups': [{'order': 1, 'title': 'Input integrity', 'question': 'Do bytes and units match?',
                        'conclusion': 'Fixture only.', 'limitations': ['Not a physical model.'], 'panels': panels}]}


class FigureContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.source = b'time_s,voltage_V\n0,0\n0.001,0.5\n'
        self.p = plan(self.source)
        self.folder = self.root / 'participants' / 'owner' / 'figures'
        self.folder.mkdir(parents=True)
        self.app = SimpleNamespace(store=SimpleNamespace(root=self.root / 'state'))
        self.write()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        (self.folder / 'wave.csv').write_bytes(self.source)
        (self.folder / 'plan.json').write_text(json.dumps(self.p))

    def test_snapshot_preserves_bytes_and_does_not_expose_binary_in_tool_context(self):
        snapshot = request(self.app, 'owner', {'plan_path': 'figures/plan.json'})
        self.assertEqual(self.p, snapshot['figure_project']['plan'])
        public = public_response({'engine': 'scientific-figures', **snapshot})
        self.assertNotIn('figure_project', public)
        self.assertEqual(self.p, public['figure_plan'])
        self.assertEqual(snapshot['figure_project_sha256'], public['figure_project_sha256'])
        self.assertEqual(public, public_response({'jobs': [{'engine': 'scientific-figures', **snapshot}]})['jobs'][0])

    def test_modified_source_owner_and_path_escape_fail_closed(self):
        (self.folder / 'wave.csv').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            request(self.app, 'owner', {'plan_path': 'figures/plan.json'})
        with self.assertRaises((ValueError, PermissionError, FileNotFoundError)):
            request(self.app, 'other', {'plan_path': 'figures/plan.json'})
        self.p['sources'][0]['path'] = '../private.csv'; self.write()
        with self.assertRaises((PermissionError, ValueError)):
            request(self.app, 'owner', {'plan_path': 'figures/plan.json'})
        self.p['sources'][0]['path'] = 'link.csv'; self.write()
        (self.folder / 'link.csv').symlink_to(self.folder / 'wave.csv')
        with self.assertRaises((PermissionError, ValueError)):
            request(self.app, 'owner', {'plan_path': 'figures/plan.json'})

    def test_unbound_data_invented_error_bars_and_bad_gap_rejected(self):
        for field, value, message in [('dependencies', ['unknown'], 'DEPENDENCY'), ('error_bars', [1, 2], 'REPLICATE')]:
            p = copy.deepcopy(self.p); p['groups'][0]['panels'][0][field] = value
            with self.assertRaisesRegex(ValueError, message): validate_plan(p)
        p = copy.deepcopy(self.p); del p['groups'][0]['panels'][1]['reason']
        with self.assertRaisesRegex(ValueError, 'GAP_REASON'): validate_plan(p)
        p = copy.deepcopy(self.p); p['groups'][0]['panels'][0].update(type='diagram', evidence_kind='native-field')
        with self.assertRaisesRegex(ValueError, 'ILLUSTRATION'): validate_plan(p)
        p = copy.deepcopy(self.p); p['groups'][0]['panels'][0]['series'][0]['source'] = 'unbound'
        with self.assertRaisesRegex(ValueError, 'UNBOUND'): validate_plan(p)

    @unittest.skipUnless(CAD.is_file(), 'Scientific renderer runtime absent')
    def test_energy_units_and_named_font_weights_export_real_svg(self):
        # A full-cycle energy ledger is expressed in J at the source and mJ in
        # publication. Verify numerical conversion and actual SVG generation.
        self.source = b'time_s,energy_J\n0,0\n1,0.003\n'
        self.p['sources'][0].update(columns={'time_s': 's', 'energy_J': 'J'},
                                    sha256=hashlib.sha256(self.source).hexdigest())
        self.p['groups'][0]['panels'][0].update(title='Loading energy', series=[
            {'source': 'wave', 'x': 'time_s', 'y': 'energy_J', 'x_unit': 's', 'y_unit': 'mJ'}])
        self.write()
        renderer = Path(__file__).parents[2] / 'packages/python/bfworld/src/bfworld/agentlab/scientific_renderer.py'
        script = """import importlib.util,json,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('renderer',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
p=Path(sys.argv[2]);v=json.loads(p.read_text());a=m.Sources(v,p.parent).column('wave','energy_J','mJ');assert list(a)==[0.,3.]
m.render(p,Path(sys.argv[3]))
"""
        output = self.root / 'energy-render'
        subprocess.run([str(CAD), '-c', script, str(renderer), str(self.folder / 'plan.json'), str(output)],
                       check=True, capture_output=True, timeout=60)
        svg = (output / 'panel-1a.svg').read_text()
        self.assertIn('(mJ)', svg)
        self.assertIn('<text', svg)

    @unittest.skipUnless(CAD.is_file(), 'Scientific renderer runtime absent')
    def test_real_render_units_missing_vector_and_independent_reconstruction(self):
        renderer = Path(__file__).parents[2] / 'packages/python/bfworld/src/bfworld/agentlab/scientific_renderer.py'
        # Do not depend on Matplotlib being installed in the test interpreter.
        output = self.root / 'output'
        subprocess.run([str(CAD), str(renderer), str(self.folder / 'plan.json'), str(output)], check=True, capture_output=True, timeout=60)
        index = json.loads((output / 'figure-index.json').read_text())
        self.assertEqual({'available': 1, 'missing': 1, 'not_applicable': 0}, index['counts'])
        self.assertFalse(index['quality']['physical_qualification'])
        svg = (output / 'panel-1a.svg').read_text()
        self.assertIn('(ms)', svg); self.assertIn('(mV)', svg); self.assertIn('<text', svg)
        (output / 'scientific_renderer.py').write_bytes(renderer.read_bytes())
        subprocess.run([str(CAD), str(output / 'scientific_renderer.py'), str(output / 'reproduce-plan.json'), str(self.root / 'rebuild')], check=True, capture_output=True, timeout=60)
        self.assertEqual((output / 'panel-1a.png').read_bytes(), (self.root / 'rebuild/panel-1a.png').read_bytes())
        for bad_unit, data, error in [('A', self.source, 'UNIT_MISMATCH'), ('mV', b'time_s,voltage_V\n0,nan\n', 'NONFINITE')]:
            self.p['groups'][0]['panels'][0]['series'][0]['y_unit'] = bad_unit
            self.source = data; self.p['sources'][0]['sha256'] = hashlib.sha256(data).hexdigest(); self.write()
            proc = subprocess.run([str(CAD), str(renderer), str(self.folder / 'plan.json'), str(self.root / 'bad')], capture_output=True, timeout=60)
            self.assertNotEqual(0, proc.returncode); self.assertIn(error, proc.stderr.decode())


class FigureEngineeringTest(unittest.TestCase):
    setUp = fixtures.ProductResultsTest.setUp
    tearDown = fixtures.ProductResultsTest.tearDown
    write = fixtures.ProductResultsTest.write

    @unittest.skipUnless(CAD.is_file(), 'Scientific renderer runtime absent')
    def test_native_job_idempotence_trace_catalog_and_claim_boundary(self):
        folder = self.root / 'participants' / self.owner / 'figures'; folder.mkdir(parents=True)
        source = b'time_s,voltage_V\n0,0\n0.001,0.5\n'
        p = plan(source); (folder / 'wave.csv').write_bytes(source); (folder / 'plan.json').write_text(json.dumps(p))
        self.assertIn('scientific-figures', [e['id'] for e in self.app.engineering.catalog(self.owner)['engines']])
        skill = self.app.engineering.skill(self.owner, 'scientific-figures')
        self.assertIn('不等于复现成功率', skill['content'])
        body = {'engine': 'scientific-figures', 'operation_id': 'fixture-figures', 'parameters': {'plan_path': 'figures/plan.json'}}
        job = self.app.engineering.submit(self.owner, body)
        self.assertEqual(job['id'], self.app.engineering.submit(self.owner, body)['id'])
        deadline = time.monotonic() + 45
        while job['status'] in ('QUEUED', 'RUNNING') and time.monotonic() < deadline:
            time.sleep(.1); job = self.app.engineering.get(self.owner, job['id'])
        self.assertEqual('SUCCEEDED', job['status'], job.get('error'))
        self.assertFalse(job['result']['product_verified']); self.assertFalse(job['result']['hardware_verified'])
        events = {e['kind'] for e in self.app.engineering.events(self.owner)}
        self.assertTrue({'skill_read', 'process_start', 'job_completed'} <= events)
        queued = next(e['data'] for e in self.app.engineering.events(self.owner) if e['kind'] == 'job_queued')
        self.assertNotIn('figure_project', queued)
        self.assertEqual(job['figure_project_sha256'], queued['figure_project_sha256'])
        self.assertEqual(2, len(queued['figure_plan']['groups'][0]['panels']))
        catalog = self.app.results.inspect(self.owner)
        story = next(r['evidence_story'] for r in catalog['results'] if r.get('evidence_story'))
        self.assertEqual('missing', story['panels'][1]['status'])
        self.assertTrue(story['panels'][0]['source_files'])
        self.assertFalse(catalog['verdict']['passed'])
        source += b'0.002,0.7\n'; (folder / 'wave.csv').write_bytes(source)
        p['sources'][0]['sha256'] = hashlib.sha256(source).hexdigest(); (folder / 'plan.json').write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError, 'OPERATION_CONFLICT'): self.app.engineering.submit(self.owner, body)
        # Artifact source bytes are checked again when served.
        artifact = self.app.engineering.artifact(self.owner, job['id'], 'panel-1a.pdf')
        artifact.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): self.app.engineering.artifact(self.owner, job['id'], 'panel-1a.pdf')


if __name__ == '__main__':
    unittest.main()
