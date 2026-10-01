"""Apply review-only cache patch to a temporary tree, never production files."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / 'battery-world/packages/python/bfworld/src'))
from bfworld.agentlab.simulation_chain.contracts import ChainError


class CachePatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        manifest = json.loads((ROOT / 'contracts/CACHE-PATCH-CHECK.json').read_text())
        for name in manifest['paths']:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / name, target)
        subprocess.run(['git', 'apply', str(ROOT / 'patches/cache-v2-minimal-review.patch')], cwd=self.root, check=True, capture_output=True)
        spec = importlib.util.spec_from_file_location('bfworld.agentlab.simulation_chain.review_cache', self.root / manifest['paths'][0])
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.tmp.cleanup()

    def produce(self, directory):
        (directory / 'artifact').write_text('synthetic')
        return {'coordinate': (1., 2.)}

    def test_fresh_and_hit_keep_json_normalization(self):
        cache = self.module.Cache(self.root / 'cache')
        fresh = cache.stage('beam', {}, self.produce)
        hit = cache.stage('beam', {}, self.produce)
        self.assertEqual(fresh[1], hit[1]); self.assertIsInstance(fresh[1]['coordinate'], list)
        self.assertTrue(hit[3])

    def test_metadata_value_tamper_rejected(self):
        cache = self.module.Cache(self.root / 'cache')
        path = cache.stage('beam', {}, self.produce)[0]
        manifest = json.loads((path / 'checkpoint.json').read_text())
        manifest['value'] = {'coordinate': [9, 9]}
        (path / 'checkpoint.json').write_text(json.dumps(manifest))
        with self.assertRaises(ChainError): cache.stage('beam', {}, self.produce)

    def test_canonical_artifact_tamper_rejected(self):
        cache = self.module.Cache(self.root / 'cache')
        path = cache.stage('beam', {}, self.produce)[0]
        (path / self.module.VALUE_FILE).write_text('{}')
        with self.assertRaises(ChainError): cache.stage('beam', {}, self.produce)

    def test_owner_roots_are_not_replaced_or_shared(self):
        a = self.module.Cache(self.root / 'agent-cache/owner-a')
        b = self.module.Cache(self.root / 'agent-cache/owner-b')
        pa = a.stage('beam', {}, self.produce)[0]; pb = b.stage('beam', {}, self.produce)[0]
        self.assertNotEqual(pa, pb)
        self.assertEqual(a.root.parent.name, 'owner-a')
        (pa / 'artifact').write_text('tampered owner A')
        self.assertTrue(b.stage('beam', {}, self.produce)[3])
        with self.assertRaises(ChainError): a.stage('beam', {}, self.produce)

    def test_old_namespace_preserved_and_production_owner_selector_untouched(self):
        old = self.root / 'cache/beam/old'
        old.mkdir(parents=True); (old / 'retained').write_text('old failure')
        self.module.Cache(self.root / 'cache').stage('beam', {}, self.produce)
        self.assertEqual((old / 'retained').read_text(), 'old failure')
        patch = (ROOT / 'patches/cache-v2-minimal-review.patch').read_text()
        self.assertNotIn('__init__.py', patch)
        production = (REPO / 'battery-world/packages/python/bfworld/src/bfworld/agentlab/simulation_chain/__init__.py').read_text()
        self.assertIn("agent-cache'/job['owner']", production)


if __name__ == '__main__': unittest.main()
