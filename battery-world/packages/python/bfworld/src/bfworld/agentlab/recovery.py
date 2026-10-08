"""Trusted transport facts and explicit user-turn leases; no budget resets."""
import hashlib
import http.client
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from .store import canonical, identity

INTERACTIVE_WALL_SECONDS = 1800

class RequestNotSent(OSError):
    """HTTPS connect failed before the completion request's headers/body."""


class ObservedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        try:
            super().connect()
        except OSError as exc:
            # HTTP proxy CONNECT may have been sent; it contains no model request.
            raise RequestNotSent(type(exc).__name__ + ': ' + str(exc)) from exc


class ObservedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(ObservedHTTPSConnection, req, context=self._context,
                            check_hostname=self._check_hostname)


def is_not_sent(exc):
    return isinstance(exc, RequestNotSent) or isinstance(getattr(exc, 'reason', None), RequestNotSent)


def open_before_send(opener, request, *, timeout, retry_record, before_retry, attempts=3):
    """Retry only verified connect failures; no model HTTP bytes were sent.

    The caller retains one reservation and the exact request identity. A timeout
    after connection, a response error, or unknown transmission is never replayed.
    """
    for attempt in range(1, attempts+1):
        try:
            return opener.open(request,timeout=timeout)
        except Exception as exc:
            if not is_not_sent(exc) or attempt == attempts: raise
            try:
                before_retry()
            except Exception as denied:
                raise RequestNotSent('Retry not permitted: '+str(denied)) from exc
            retry_record({'attempt':attempt,'next_attempt':attempt+1,'max_attempts':attempts,
                          'transmission':'not_sent','reason':type(exc).__name__+': '+str(exc)[:200]})


class Recovery:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS model_resolutions(request_id TEXT PRIMARY KEY,kind TEXT,evidence TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS interactive_leases(owner TEXT,message_id TEXT PRIMARY KEY,created REAL,expires REAL);
            CREATE TABLE IF NOT EXISTS owner_model_caps(owner TEXT PRIMARY KEY,max_usd REAL);
            CREATE TABLE IF NOT EXISTS research_model_studies(protocol TEXT PRIMARY KEY,created REAL NOT NULL,
              expires REAL NOT NULL,max_usd REAL NOT NULL,model TEXT NOT NULL,authorization TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS research_model_owners(owner TEXT PRIMARY KEY,protocol TEXT NOT NULL,trial TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS research_usage_continuations(protocol TEXT PRIMARY KEY,
              created REAL NOT NULL,expires REAL NOT NULL,authorization TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS research_usage_carryforwards(protocol TEXT NOT NULL,
              request_id TEXT NOT NULL,original_row_hash TEXT NOT NULL,authorization TEXT NOT NULL,
              created REAL NOT NULL,PRIMARY KEY(protocol,request_id));
            ''')

    def usage_continuation(self, db, owner=None, protocol=None):
        if protocol is None:
            row = db.execute('SELECT protocol FROM research_model_owners WHERE owner=?', (owner,)).fetchone()
            if not row: return None
            protocol = row['protocol']
        row = db.execute('''SELECT c.* FROM research_usage_continuations c
            JOIN research_model_studies s ON s.protocol=c.protocol
            WHERE c.protocol=? AND c.expires>? AND s.expires>?''', (protocol,time.time(),time.time())).fetchone()
        return dict(row) if row else None

    def unknown_blockers(self, db, owner=None):
        policy = self.usage_continuation(db, owner=owner)
        allowed = {r['owner'] for r in db.execute('SELECT owner FROM research_model_owners WHERE protocol=?',
                   (policy['protocol'],))} if policy else set()
        # A new exploratory study may explicitly carry a known historical liability.
        # This is not a usage resolution: the original row and reservation stay intact,
        # and Provider still counts them against the global monetary ceiling.
        carried = {r['request_id']:r['original_row_hash'] for r in db.execute(
            'SELECT * FROM research_usage_carryforwards WHERE protocol=? AND authorization<>?',
            (policy['protocol'],''))} if policy else {}
        resolved = self.resolved(db)
        return [dict(r) for r in db.execute("SELECT * FROM model_requests WHERE status='UNKNOWN'")
                if r['id'] not in resolved and r['owner'] not in allowed
                and carried.get(r['id']) != identity(dict(r))]

    def resolved(self, db):
        return {r['request_id'] for r in db.execute("SELECT request_id FROM model_resolutions WHERE kind='NOT_SENT'")}

    def issue(self, owner, message_id):
        """Called only after a new operator message is committed, never by a worker."""
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            message = db.execute("SELECT * FROM chat_messages WHERE id=? AND conversation=? AND status='QUEUED'", (message_id, owner)).fetchone()
            if not message:
                raise ValueError('LEASE_REQUIRES_NEW_USER_MESSAGE')
            now = time.time()
            db.execute('INSERT OR IGNORE INTO interactive_leases VALUES(?,?,?,?)', (owner, message_id, now, now + INTERACTIVE_WALL_SECONDS))

    def lease(self, db, owner):
        # Every lease refers to an operator-created message, never a model turn.
        row = db.execute('SELECT 1 FROM interactive_leases WHERE owner=?', (owner,)).fetchone()
        if not row:
            return None
        row = db.execute("""SELECT l.* FROM interactive_leases l JOIN chat_messages m ON m.id=l.message_id
            WHERE l.owner=? AND m.conversation=? AND m.status NOT IN ('WITHDRAWN','RECALLING','CANCELLED')
            ORDER BY l.created DESC, l.message_id DESC LIMIT 1""", (owner, owner)).fetchone()
        return dict(row) if row else None

    def refresh_grant(self, owner):
        with self.store.connect() as db:
            lease = self.lease(db, owner)
            if lease and time.time() < lease['expires']:
                db.execute('UPDATE grants SET expires=? WHERE owner=?', (lease['expires'], owner))

    def check_window(self, db, owner, grant, limits):
        if not grant:
            raise PermissionError('MODEL_OWNER_GRANT_EXPIRED')
        lease = self.lease(db, owner)
        interactive = db.execute('SELECT 1 FROM interactive_leases WHERE owner=?', (owner,)).fetchone()
        if interactive and not lease:
            raise ValueError('CHAT_TURN_AUTH_REQUIRED')
        if lease:
            if time.time() > lease['expires']:
                raise ValueError('CHAT_TURN_WALL_BUDGET')
            if time.time() > grant['expires']:
                raise PermissionError('MODEL_OWNER_GRANT_EXPIRED')
            return
        if time.time() > grant['expires']:
            raise PermissionError('MODEL_OWNER_GRANT_EXPIRED')
        study = db.execute('SELECT s.* FROM research_model_studies s JOIN research_model_owners o ON o.protocol=s.protocol WHERE o.owner=?', (owner,)).fetchone()
        if study:
            if time.time() > study['expires']:
                raise ValueError('RESEARCH_MODEL_WINDOW_EXPIRED')
            return
        if time.time() > limits['expires']:
            raise ValueError('MODEL_WALL_BUDGET')

    def resolve_historical_handshake(self, request_id, evidence):
        """Local operator reconciliation, narrowly pinned to this CPython call site.

        Original UNKNOWN rows, NULL usage and the full reservation stay intact.
        No provider charge is inferred from a balance query or an SDK's zero usage.
        """
        from pathlib import Path
        if sys.version_info[:3] != (3, 11, 9):
            raise ValueError('RECOVERY_RUNTIME_UNVERIFIED')
        source = Path(evidence['ssl_source']).read_bytes()
        if hashlib.sha256(source).hexdigest() != '90250b0ef726b80fe7f8f1d360c91d5a0ddde08fd968034a214906849ec0fb1b':
            raise ValueError('RECOVERY_SOURCE_MISMATCH')
        lines = source.decode().splitlines()
        if 'return PySSL_SetError' not in lines[1005] or '_ssl__SSLSocket_do_handshake_impl' not in '\n'.join(lines[910:955]):
            raise ValueError('RECOVERY_CALLSITE_MISMATCH')
        probe = json.loads(Path(evidence['probe_file']).read_text())
        if not probe.get('only_tls_handshake') or '_ssl.c:1006' not in probe.get('error', ''):
            raise ValueError('RECOVERY_PROBE_MISMATCH')
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM model_requests WHERE id=?', (request_id,)).fetchone()
            if not row or row['status'] != 'UNKNOWN' or row['usage'] is not None or 'UNEXPECTED_EOF_WHILE_READING' not in (row['error'] or '') or '_ssl.c:1006' not in row['error']:
                raise ValueError('RECOVERY_NOT_HANDSHAKE_UNKNOWN')
            if identity(dict(row)) != evidence['original_row_hash']:
                raise ValueError('RECOVERY_ROW_CHANGED')
            record = {**evidence, 'original_row': dict(row), 'python': sys.version, 'openssl': ssl.OPENSSL_VERSION,
                      'kind': 'pre-completion-request TLS handshake failure', 'usage_observed': False,
                      'reservation_retained_usd': row['reserved'], 'probe': probe}
            db.execute('INSERT OR IGNORE INTO model_resolutions VALUES(?,?,?,?)', (request_id, 'NOT_SENT', canonical(record), time.time()))
        return record
