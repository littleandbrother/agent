#!/usr/bin/env python3
"""Read-only HTTP acceptance/download check; no model or engineering dispatch."""
import hashlib
import http.cookiejar
import json
import re
from pathlib import Path
import time
import urllib.request
import zipfile
import io

APP = Path(__file__).resolve().parents[2]
OUT = APP / 'docs/agentlab/refactor-r0-r2-20261011'
owner = json.loads((OUT / 'trial/independent-review.json').read_text())['owner']
base = 'http://127.0.0.1:8768'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
with opener.open(base + '/', timeout=10) as response:
    main = response.read()
assert b'design-lab.css' not in main and b'design-lab.js' not in main
# The established server adds a content-build meta and cache-busting URLs.
# Compare the actual source after removing only those documented additions.
source = (APP / 'apps/agent-studio/index.html').read_bytes()
normalized = re.sub(rb'<meta name="bf-ui-build" content="[0-9a-f]{16}">', b'', main, count=1)
normalized = re.sub(rb'([.]css|[.]js)[?]v=[0-9a-f]{16}"', rb'\1"', normalized)
assert normalized == source
with opener.open(base + '/api/design-lab?session_id=' + owner, timeout=10) as response:
    view = json.load(response)
with opener.open(base + '/api/design-lab/package?session_id=' + owner, timeout=20) as response:
    package = response.read()
expected = json.loads((OUT / 'trial/independent-review.json').read_text())
assert view['owner'] == owner and view['current_design'] == expected['design_id']
assert view['submission']['submission_id'] == expected['submission']['submission_id']
assert view['submission']['acceptance']['scoped_passed'] is True
assert view['submission']['acceptance']['full_product_passed'] is False
assert hashlib.sha256(package).hexdigest() == expected['zip_sha256']
with zipfile.ZipFile(io.BytesIO(package)) as z:
    assert z.testzip() is None
receipt = {'schema_version': 'bf-live-restored-ui-and-delivery-v1', 'time': time.time(),
    'passed': True, 'main_ui_source_sha256': hashlib.sha256(source).hexdigest(),
    'main_ui_http_sha256': hashlib.sha256(main).hexdigest(),
    'source_equal_after_documented_cache_versioning': True,
    'main_ui_new_review_assets_absent': True,
    'owner': owner, 'design_id': expected['design_id'],
    'backend_view_keys': sorted(view), 'zip_sha256': expected['zip_sha256'],
    'zip_bytes': len(package), 'zip_crc_passed': True,
    'new_model_requests': 0, 'new_native_solver_calls': 0,
    'scope': 'Actual main HTTP bytes and same-version C delivery readback; no private cookie stored.'}
dest = OUT / ('live-readback-' + str(time.time_ns()) + '.json')
dest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
print(json.dumps({'passed': True, 'receipt': str(dest), 'zip_bytes': len(package)}))
