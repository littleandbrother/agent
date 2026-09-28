import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab import server


class ConversationProjection(unittest.TestCase):
    def test_streaming_and_historical_projection(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for the browser projection test')
        result = subprocess.run([node, str(Path(__file__).with_name('conversation_projection.cjs'))], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_build_identity_and_versioned_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'index.html').write_text('<html><head></head><script src="/app.js"></script><link href="/chat.css"></html>')
            (root/'app.js').write_text('first')
            with patch.object(server, 'UI', root):
                first = server.ui_build()
                self.assertEqual(first, server.ui_build())
                page = server.ui_index().decode()
                self.assertIn(f'name="bf-ui-build" content="{first}"', page)
                self.assertIn(f'/app.js?v={first}', page)
                self.assertIn(f'/chat.css?v={first}', page)
                (root/'app.js').write_text('second')
                self.assertNotEqual(first, server.ui_build())

    def test_version_endpoint_and_current_assets_without_model_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            app = server.Workbench(Path(temp)/'state')
            http = ThreadingHTTPServer(('127.0.0.1', 0), server.handler(app))
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                base = f'http://127.0.0.1:{http.server_port}'
                token = (app.store.root/'operator.token').read_text().strip()
                req = urllib.request.Request(base+'/api/ui-version', headers={'Authorization':'Bearer '+token})
                with urllib.request.urlopen(req) as response:
                    version = json.load(response)
                    self.assertEqual('no-store', response.headers['Cache-Control'])
                self.assertEqual(server.ui_build(), version['build'])
                with urllib.request.urlopen(base+'/') as response:
                    page = response.read().decode()
                assets = re.findall(r'(?:src|href)="(/[^"?]+\.(?:js|css)\?v=[^"]+)"', page)
                self.assertGreater(len(assets), 10)
                for asset in assets:
                    with urllib.request.urlopen(base+asset) as response:
                        self.assertEqual(200, response.status)
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(base+'/api/ui-version')
                self.assertEqual(403, caught.exception.code)
                self.assertEqual(0, app.provider.status()['calls'])
            finally:
                http.shutdown();http.server_close();app.stop.set();app.thread.join(3);app.lock.close()
