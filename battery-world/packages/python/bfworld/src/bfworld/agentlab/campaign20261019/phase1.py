"""Finite BF/Pi bridge using the existing provider, ledger and scientific tools.

It owns dispatch bounds and records facts; the supplied BF tool owns device
execution. Independent final service evaluation is deliberately outside this
participant endpoint. No credentials or historical runtime are copied.
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import threading
import time
import urllib.request
import zlib

from jsonschema import Draft202012Validator

from .common import digest, file_hash, seal


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def tool_definition(name, description, parameters):
    Draft202012Validator.check_schema(parameters)
    value = {'name': name, 'description': description, 'parameters': parameters}
    raw = encoded(value)
    return {**value, 'canonical': raw.decode(), 'sha256': hashlib.sha256(raw).hexdigest()}


def ledger(database, owner):
    database = Path(database)
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        rows = [dict(r) for r in db.execute(
            'SELECT id,status,reserved,charged,usage,response_hash,error FROM model_requests '
            'WHERE owner=? ORDER BY created,rowid', (owner,))]
    unknown, estimates = [], []
    for row in rows:
        try:
            usage = json.loads(row['usage']) if row['usage'] else None
        except (ValueError, TypeError):
            usage = None
        valid_usage = isinstance(usage, dict) and all(
            type(usage.get(k)) is int and usage[k] >= 0
            for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
        if (row['status'] not in ('SETTLED', 'NOT_SENT') or
                row['status'] == 'SETTLED' and (not valid_usage or row['charged'] is None)):
            unknown.append(row['id'])
        if valid_usage and all(type(usage.get(k)) is int and usage[k] >= 0 for k in
                         ('prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'completion_tokens')):
            estimates.append((usage['prompt_cache_hit_tokens'] * .006 +
                              usage['prompt_cache_miss_tokens'] * .3 +
                              usage['completion_tokens'] * 1.2) / 1_000_000)
    return {'requests': len(rows), 'unknown_or_missing_usage': unknown,
            'settled_charge_upper_bound_usd': sum(r['charged'] or 0 for r in rows if r['status'] == 'SETTLED'),
            'unsettled_reserved_usd': sum(r['reserved'] or 0 for r in rows if r['status'] not in ('SETTLED', 'NOT_SENT')),
            'cache_aware_rate_estimate_usd': sum(estimates) if len(estimates) == len(rows) else None,
            'rate_scope': 'Existing pinned .006/.30/1.20 USD per million; estimates, not invoice amounts',
            'rows': rows}


def output_bytes(root):
    total = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
        total += sum((Path(directory) / n).lstat().st_size for n in names
                     if not (Path(directory) / n).is_symlink())
    return total


def require_lease(path, episode, now=None):
    value = json.loads(Path(path).read_text())
    holders = value.get('holders', [])
    if (value.get('status') != 'GRANTED' or value.get('episode') != episode or
            value.get('expires', 0) <= (time.time() if now is None else now) or
            not 1 <= len(holders) <= 3 or len(set(holders)) != len(holders) or
            'Pi' not in holders or value.get('other_executor_status') != 'idle'):
        raise ValueError('MODEL_SLOT_NOT_LEASED')
    return value


class BFPhaseGateway:
    """One participant tool and one guarded route to the existing paid proxy."""

    def __init__(self, protocol, root, handler, *, provider_token, lease_path):
        self.protocol = protocol
        self.root = Path(root)
        self.output_root = Path(protocol.get('output_root', self.root)).resolve()
        if not self.root.resolve().is_relative_to(self.output_root):
            raise ValueError('EPISODE_OUTPUT_ROOT_MUST_INCLUDE_GATEWAY')
        self.handler = handler
        self.provider_token = provider_token
        self.lease_path = Path(lease_path)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.started = time.time()
        self.tool_calls = 0
        self.model_dispatches = 0
        self.candidates = set()
        self.stopped = None
        self.last_event = '0' * 64
        self.models_seen = set()
        self.server = self.thread = None
        limits = protocol['limits']
        if (not 0 < limits['model_requests'] <= 60 or not 0 < limits['candidates'] <= 3 or
                not 0 < limits['wall_seconds'] <= 3600 or limits['peak_remaining_bytes'] < 0 or
                protocol.get('mode') != 'fixture' and limits['reserve_bytes'] < 10_000_000_000):
            raise ValueError('FINITE_EPISODE_LIMITS_REQUIRED')
        definition = protocol['tool']
        plain = {k: definition[k] for k in ('name', 'description', 'parameters')}
        if digest(plain) != definition['sha256']:
            raise ValueError('TOOL_CONTRACT_CHANGED')
        self.validator = Draft202012Validator(definition['parameters'])
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / 'gateway-events.jsonl').exists():
            raise ValueError('EPISODE_GATEWAY_ALREADY_STARTED')
        self.events = (self.root / 'gateway-events.jsonl').open('x')
        self.event('gateway_started', {'protocol': digest(protocol), 'owner': protocol['owner'],
                                       'new_models_started': 0})

    def event(self, kind, data):
        value = {'kind': kind, 'time': time.time(), 'previous': self.last_event, 'data': data}
        value['sha256'] = digest(value)
        self.events.write(encoded(value).decode() + '\n')
        self.events.flush()
        os.fsync(self.events.fileno())
        self.last_event = value['sha256']

    def stop(self, reason):
        if not self.stopped:
            self.stopped = reason
            self.event('episode_dispatch_stopped', {'reason': reason, 'automatic_resume': False})
        raise ValueError(reason)

    def ready(self, *, paid=False):
        p = self.protocol
        if self.stopped:
            raise ValueError('EPISODE_STOPPED:' + self.stopped)
        if time.time() - self.started >= p['limits']['wall_seconds']:
            self.stop('EPISODE_WALL_LIMIT')
        for name, expected in p['bound_files'].items():
            try:
                actual = file_hash(name)
            except OSError:
                actual = None
            if actual != expected:
                self.stop('BOUND_INPUT_CHANGED:' + name)
        if shutil.disk_usage(self.root).free < p['limits']['reserve_bytes'] + p['limits']['peak_remaining_bytes']:
            self.stop('EPISODE_STORAGE_RESERVE')
        if output_bytes(self.output_root) >= p['limits']['output_bytes']:
            self.stop('EPISODE_OUTPUT_CAP')
        if paid:
            try:
                require_lease(self.lease_path, p['id'])
            except (ValueError, OSError):
                self.stop('MODEL_SLOT_NOT_LEASED')
            account = ledger(p['provider_database'], p['owner'])
            if account['unknown_or_missing_usage']:
                self.stop('PROVIDER_USAGE_UNAVAILABLE')
            if account['requests'] >= p['limits']['model_requests'] or self.model_dispatches >= p['limits']['model_requests']:
                self.stop('EPISODE_REQUEST_LIMIT')
        return True

    def tool(self, body):
        with self.lock:
            self.ready()
            if self.tool_calls >= self.protocol['limits']['tool_calls']:
                raise ValueError('EPISODE_TOOL_LIMIT')
            action = body.get('action') if isinstance(body, dict) else None
            candidate = {k: body[k] for k in self.protocol['candidate_fields'] if isinstance(body, dict) and k in body}
            key = digest(candidate) if candidate else None
            if action in self.protocol['candidate_actions'] and key is not None:
                if key not in self.candidates and len(self.candidates) >= self.protocol['limits']['candidates']:
                    raise ValueError('EPISODE_CANDIDATE_LIMIT')
                self.candidates.add(key)
            # A rejected JSON candidate still consumes a revision. A no-go
            # submission has no candidate and remains legal at the budget cap.
            self.validator.validate(body)
            if action == 'check' and key is None:
                raise ValueError('CANDIDATE_REQUIRED')
            self.tool_calls += 1
            start = time.monotonic()
            self.event('tool_started', {'number': self.tool_calls, 'input': body, 'candidate_key': key})
            try:
                value = self.handler(body)
                raw = encoded(value)
                if len(raw) > self.protocol['limits']['tool_response_bytes']:
                    raise ValueError('TOOL_RESPONSE_BOUND')
                self.event('tool_completed', {'number': self.tool_calls, 'output': value,
                                              'wall_seconds': time.monotonic() - start})
                return value
            except Exception as error:
                self.event('tool_failed', {'number': self.tool_calls, 'error': type(error).__name__ + ': ' + str(error)[:1200],
                                           'wall_seconds': time.monotonic() - start})
                raise

    def model_payload(self, body):
        self.ready(paid=True)
        if body.get('model') != 'deepseek-flash' or body.get('stream') is not True:
            self.stop('PINNED_MODEL_STREAM_REQUIRED')
        tools = body.get('tools')
        if not isinstance(tools, list) or len(tools) != 1:
            self.stop('PINNED_TOOL_SET_REQUIRED')
        function = tools[0].get('function', {})
        actual = {k: function.get(k) for k in ('name', 'description', 'parameters')}
        expected = {k: self.protocol['tool'][k] for k in ('name', 'description', 'parameters')}
        if actual != expected:
            self.stop('ACTUAL_SDK_TOOL_SCHEMA_CHANGED')
        output = body.get('max_tokens', body.get('max_completion_tokens', 32768))
        if type(output) is not int or not 1 <= output <= self.protocol['limits']['max_output_tokens']:
            raise ValueError('MODEL_OUTPUT_LIMIT')
        return body

    def relay(self, request_handler, body):
        with self.lock:
            payload = self.model_payload(body)
            self.model_dispatches += 1
            request_path = self.root / 'requests' / ('model-%03d.json.zlib' % self.model_dispatches)
            request_path.parent.mkdir(exist_ok=True)
            with request_path.open('xb') as target:
                target.write(zlib.compress(encoded(payload)))
            self.ready()
            self.event('model_forward_started', {'number': self.model_dispatches, 'input_sha256': digest(payload),
                'input_artifact': str(request_path), 'input_encoding': 'zlib JSON',
                'model': payload['model'], 'max_tokens': payload.get('max_tokens')})
            req = urllib.request.Request(self.protocol['provider_service'] + '/v1/chat/completions',
                data=encoded(payload), headers={'Authorization': 'Bearer ' + self.provider_token,
                                                'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                remaining = self.protocol['limits']['wall_seconds'] - (time.time() - self.started)
                if remaining <= 0:
                    self.stop('EPISODE_WALL_LIMIT')
                with opener.open(req, timeout=min(310, remaining)) as response:
                    request_handler.send_response(200)
                    request_handler.send_header('Content-Type', 'text/event-stream')
                    request_handler.send_header('Cache-Control', 'no-cache')
                    request_handler.end_headers()
                    received = 0
                    for line in response:
                        if time.time() - self.started >= self.protocol['limits']['wall_seconds']:
                            self.stop('EPISODE_WALL_LIMIT')
                        received += len(line)
                        if received > self.protocol['limits']['model_response_bytes']:
                            raise ValueError('MODEL_RESPONSE_BYTE_LIMIT')
                        if line.startswith(b'data:') and line.strip() != b'data: [DONE]':
                            try:
                                value = json.loads(line[5:])
                                if isinstance(value.get('model'), str):
                                    self.models_seen.add(value['model'])
                                    if value['model'] not in self.protocol['allowed_reported_models']:
                                        raise RuntimeError('PROVIDER_REPORTED_MODEL_CHANGED')
                            except (ValueError, TypeError):
                                pass
                        request_handler.wfile.write(line)
                        request_handler.wfile.flush()
                account = ledger(self.protocol['provider_database'], self.protocol['owner'])
                self.event('model_forward_completed', {'number': self.model_dispatches, 'response_bytes': received,
                    'provider_requests': account['requests'], 'unresolved': account['unknown_or_missing_usage'],
                    'settled_charge_upper_bound_usd': account['settled_charge_upper_bound_usd'],
                    'reported_models': sorted(self.models_seen)})
                if account['unknown_or_missing_usage']:
                    self.stopped = 'PROVIDER_USAGE_UNAVAILABLE'
            except Exception as error:
                self.stopped = 'MODEL_TRANSPORT_OR_PROVIDER_FAILURE'
                self.event('model_forward_failed', {'number': self.model_dispatches,
                    'error': type(error).__name__ + ': ' + str(error)[:1200], 'no_automatic_retry': True})
                raise

    def start(self):
        bridge = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                relaying = False
                try:
                    if self.headers.get('Authorization') != 'Bearer ' + bridge.token:
                        raise PermissionError('EPISODE_TOKEN_REQUIRED')
                    if self.path not in ('/tool', '/v1/chat/completions'):
                        raise ValueError('EPISODE_ROUTE_DENIED')
                    size = int(self.headers.get('Content-Length', '0'))
                    bound = bridge.protocol['limits']['model_request_bytes'] if self.path.startswith('/v1/') else 96000
                    if not 0 < size <= bound:
                        raise ValueError('EPISODE_REQUEST_BYTES')
                    body = json.loads(self.rfile.read(size))
                    if self.path.startswith('/v1/'):
                        # Validate before headers; a later stream failure closes
                        # this exact attempt and preserves its provider liability.
                        bridge.model_payload(body)
                        relaying = True
                        bridge.relay(self, body)
                    else:
                        result = bridge.tool(body)
                        raw = encoded(result)
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(raw)))
                        self.end_headers()
                        self.wfile.write(raw)
                except Exception as error:
                    if relaying:
                        self.close_connection = True
                        return
                    raw = encoded({'error': type(error).__name__ + ': ' + str(error)[:1800]})
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return 'http://127.0.0.1:' + str(self.server.server_port)

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
        with self.lock:
            self.event('gateway_closed', {'tool_calls': self.tool_calls, 'model_dispatches': self.model_dispatches,
                'distinct_candidates': len(self.candidates), 'stopped': self.stopped,
                'reported_models': sorted(self.models_seen), 'output_bytes': output_bytes(self.output_root)})
            self.events.close()
