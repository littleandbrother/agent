"""Publish Lab in Studio's origin while the design runtime stays independent."""
import json
import mimetypes
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


ROUTES = {
    '/api/design-repository', '/api/design-repository/projects',
    '/api/design-repository/file', '/api/design-repository/archive',
    '/api/design-repository/trace',
}
QUERY_FIELDS = {
    'project', 'owner', 'system', 'path', 'domain_commit', 'job', 'preview',
    'release', 'session', 'after', 'limit',
}


def static_file(ui, path):
    """All Lab decoration is code; the only served assets are HTML/CSS/JS."""
    if path not in ('/lab', '/lab/', '/lab/v2', '/lab/v2/') and not path.startswith('/lab/v2/'):
        return None
    relative = path.removeprefix('/lab/v2/') if path.startswith('/lab/v2/') else 'index.html'
    if not relative: relative = 'index.html'
    if relative not in ('index.html', 'lab.js', 'lab.css'):
        raise FileNotFoundError('LAB_ASSET_NOT_FOUND')
    file = Path(ui)/'architecture-v2'/relative
    if not file.is_file(): raise FileNotFoundError('LAB_ASSET_NOT_FOUND')
    return file, mimetypes.guess_type(file)[0] or 'application/octet-stream'


class LabBridge:
    def __init__(self, configuration):
        self.config = json.loads(Path(configuration).read_text())
        c = self.config
        if c.get('schema_version') != 'bf-lab-read-bridge-v1':
            raise ValueError('LAB_BRIDGE_CONFIGURATION')
        parsed = urlparse(c['upstream'])
        if (parsed.scheme, parsed.hostname, parsed.port, parsed.path) != ('http', '127.0.0.1', 8870, ''):
            raise ValueError('LAB_BRIDGE_LOOPBACK_ONLY')
        token = Path(c['operator_token'])
        expected = Path('/Users/depengsu/.local/share/bf-agent-architecture-v2/workbench/state/operator.token')
        if token.resolve() != expected or not token.is_file():
            raise ValueError('LAB_BRIDGE_CREDENTIAL_SCOPE')
        self.token_path = token

    def get(self, url):
        parsed = urlparse(url)
        if parsed.path not in ROUTES:
            raise PermissionError('LAB_BRIDGE_READ_ROUTE_ONLY')
        query = parse_qs(parsed.query, keep_blank_values=True)
        if any(k not in QUERY_FIELDS or len(v) != 1 for k, v in query.items()):
            raise ValueError('LAB_BRIDGE_QUERY')
        if parsed.path != '/api/design-repository/projects':
            pair = {'project': query.get('project', [''])[0], 'owner': query.get('owner', [''])[0]}
            if pair not in self.config['projects']: raise PermissionError('LAB_BRIDGE_PROJECT_SCOPE')
        outgoing = self.config['upstream']+parsed.path
        if query: outgoing += '?'+urlencode({k:v[0] for k,v in query.items()})
        request = Request(outgoing, headers={
            'Authorization': 'Bearer '+self.token_path.read_text().strip(),
            'Accept': 'application/json, application/octet-stream',
        }, method='GET')
        try:
            with urlopen(request, timeout=25) as response:
                data = response.read()
                kind = response.headers.get('Content-Type', 'application/octet-stream')
                if parsed.path == '/api/design-repository/projects':
                    value = json.loads(data)
                    allowed = self.config['projects']
                    value['projects'] = [p for p in value['projects'] if {'project':p['id'],'owner':p['owner']} in allowed]
                    data = json.dumps(value, ensure_ascii=False).encode()
                elif parsed.path == '/api/design-repository':
                    value = json.loads(data)
                    if value['environment']['profile_sha256'] != self.config['profile_sha256']:
                        raise ValueError('LAB_BRIDGE_ENVIRONMENT_CHANGED')
                return response.status, data, kind
        except HTTPError as error:
            # Only public error content crosses the bridge; authorization stays server-side.
            return error.code, error.read(4096), 'application/json; charset=utf-8'
        except (URLError, TimeoutError):
            return 503, json.dumps({'error':'V2 Lab 服务暂时离线；Studio 仍可使用。'}, ensure_ascii=False).encode(), 'application/json; charset=utf-8'
