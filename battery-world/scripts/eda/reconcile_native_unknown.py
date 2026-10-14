#!/usr/bin/env python3
"""Operator reconciliation after a closed editing generation, never a retry.

Reads the campaign database in mode=ro. Original unknown state and native
receipts are archived; model usage rows and engineering sources are untouched.
This administrative action is not exposed through participant EDA tools.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_attribute_ids(path, document):
    ids = set()
    current = None
    found = False
    for line in path.read_text().splitlines():
        if '||' not in line:
            continue
        header, body = line.split('||', 1)
        header = json.loads(header)
        if header['type'] == 'DOCHEAD':
            value = json.loads(body.rstrip('|'))
            current = value.get('uuid') if value.get('docType') == 'SCH_PAGE' else None
            found |= current == document
        elif current == document and header['type'] == 'ATTR':
            ids.add(header['id'])
    if not found:
        raise ValueError('PERSISTED_NATIVE_DOCUMENT_REQUIRED')
    return ids


def canonical_scene(response, persisted_attribute_ids=None):
    body = response.get('result', {})
    if (response.get('ok') is not True or not body.get('components') or
            body.get('wiresAvailable') is not True or not body.get('pagePrimitives')):
        raise ValueError('COMPLETE_NATIVE_READBACK_REQUIRED')
    # Inventory enumeration changes on reload. Ordered geometric paths do not.
    inventories = {'components', 'pins', 'wires', 'buses', 'arcs', 'circles',
                   'rectangles', 'polygons', 'texts', 'attributes', 'objects'}
    def normalize(value, key=None):
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            items = [normalize(v) for v in value]
            return sorted(items, key=lambda v: json.dumps(v, sort_keys=True)) if key in inventories else items
        return value
    value = normalize({k: body[k] for k in ('components', 'wires', 'pagePrimitives', 'connectivitySummary')})
    if persisted_attribute_ids is not None:
        pins = {p.get('primitiveId') for c in body['components'] for p in c.get('pins', [])}
        components = {c.get('primitiveId') for c in body['components']}
        attrs = []
        for attr in value['pagePrimitives'].get('attributes', []):
            if attr['primitiveId'] not in persisted_attribute_ids:
                if (attr.get('ParentPrimitiveId') in pins and
                        attr.get('Key') in ('Pin Name', 'Pin Number', 'Pin Type')):
                    removed = ('primitiveId', 'X', 'Y', 'AlignMode')
                elif (attr.get('ParentPrimitiveId') in components and
                        attr.get('Key') in ('3D Model', '3D Model Title', '3D Model Transform', 'Description')):
                    removed = ('primitiveId',)
                else:
                    raise ValueError('UNCLASSIFIED_UNSTORED_NATIVE_ATTRIBUTE')
                # Native renderer creates these labels from unchanged symbol
                # pins. Their values and every other field remain exact.
                attr = {k: v for k, v in attr.items() if k not in removed}
            attrs.append(attr)
        value['pagePrimitives']['attributes'] = sorted(attrs, key=lambda v: json.dumps(v, sort_keys=True))
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate_campaign_binding(root, proof):
    """Require the canonical owner and the existing local-file alias."""
    paper = proof['paper']
    if paper not in ('P%02d' % i for i in range(1, 11)):
        raise ValueError('ORIGINAL_PAPER_REQUIRED')
    index = json.loads((root / 'campaign/parallel-20261009/pi-session-index.json').read_text())
    original = next((s for s in index['sessions'] if s['paper_id'] == paper), None)
    if not original or original['owner'] != proof['owner']:
        raise ValueError('ORIGINAL_CAMPAIGN_OWNER_REQUIRED')
    binding_path = root / 'campaign/eda' / paper / 'binding.json'
    if binding_path.is_symlink() or digest(binding_path) != proof['binding_sha256']:
        raise ValueError('ORIGINAL_BINDING_CHANGED')
    binding = json.loads(binding_path.read_text())
    if (binding['paper_id'] != paper or binding['owner'] != proof['owner'] or
            binding.get('local_project') != proof['local_project'] or binding.get('writable') is not True):
        raise ValueError('ORIGINAL_OWNER_LOCAL_BINDING_REQUIRED')
    alias_path = root / 'campaign/eda' / paper / proof['alias_name']
    if (alias_path.is_symlink() or alias_path.parent.resolve() != binding_path.parent.resolve() or
            digest(alias_path) != proof['alias_sha256']):
        raise ValueError('ORIGINAL_ALIAS_CHANGED')
    alias = json.loads(alias_path.read_text())
    expected = {'owner': proof['owner'], 'paper_id': paper, 'local_project': proof['local_project'],
                'binding_record_sha256': proof['binding_sha256'],
                'created_project_uuid': binding['project_uuid'], 'runtime_project_uuid': proof['project']}
    if any(alias.get(k) != v for k, v in expected.items()):
        raise ValueError('ORIGINAL_PROJECT_ALIAS_REQUIRED')
    return {'binding_sha256': digest(binding_path), 'alias_sha256': digest(alias_path)}


def validate_evidence(blocked, proof, folder):
    if proof.get('schema_version') != 'bf-native-unknown-generation-reconciliation-v1' or proof.get('actor') != 'Codex operator recovery':
        raise ValueError('OPERATOR_GENERATION_PROOF_REQUIRED')
    project = proof['project']
    prior = blocked.get(project)
    if not prior or prior['request_id'] != proof.get('request_id') or prior['action'] != proof.get('action'):
        raise ValueError('ORIGINAL_UNKNOWN_IDENTITY_CHANGED')
    if proof['old_session'] == proof['new_session']:
        raise ValueError('NEW_EDITING_GENERATION_REQUIRED')
    records = {}
    for name in ('old_sessions', 'close', 'new_sessions', 'project_read', 'before_read', 'after_read', 'after_read_again'):
        ref = proof['evidence'][name]
        path = folder / ref['path']
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()) or digest(path) != ref['sha256']:
            raise ValueError('RECOVERY_EVIDENCE_HASH_MISMATCH:' + name)
        record = json.loads(path.read_text())
        if record['exit_code'] != 0:
            raise ValueError('RECOVERY_COMMAND_FAILED:' + name)
        wire = json.loads(record['stdout'])
        if wire.get('ok') is not True:
            raise ValueError('RECOVERY_NATIVE_ACK_REQUIRED:' + name)
        records[name] = (record, wire['value'])
    old = records['old_sessions'][1]
    new = records['new_sessions'][1]
    source = next((s for s in old if s['sessionId'] == proof['old_session']), None)
    target = next((s for s in new if s['sessionId'] == proof['new_session']), None)
    closed_entry = next((s for s in new if s['sessionId'] == proof['old_session']), None)
    path = proof['local_project']
    if (not source or not target or source.get('status') != 'alive' or
            (closed_entry is not None and closed_entry.get('status') != 'closed') or
            source.get('headless') is not True or target.get('headless') is not True or
            source.get('origin') != 'cli' or target.get('origin') != 'cli' or
            source.get('path') != path or target.get('path') != path or target.get('status') != 'alive'):
        raise ValueError('SAME_LOCAL_CLI_GENERATION_REQUIRED')
    old_other = {s['sessionId']: s for s in old if s['sessionId'] != proof['old_session']}
    # Official session listing retains closed entries as history.
    new_other = {s['sessionId']: s for s in new if s['sessionId'] not in (proof['old_session'], proof['new_session'])}
    if old_other != new_other:
        raise ValueError('FOREIGN_NATIVE_SESSION_CHANGED')
    close_record, close = records['close']
    if (close.get('sessionId') != proof['old_session'] or close.get('status') != 'closed' or close.get('headless') is not True or
            close_record['created'] < datetime.fromisoformat(prior['at'].replace('Z', '+00:00')).timestamp()):
        raise ValueError('OLD_GENERATION_CLOSE_ACK_REQUIRED')
    read_record, current = records['project_read']
    context = current.get('context', {})
    if (current.get('ok') is not True or current.get('result', {}).get('uuid') != project or
            context.get('projectUuid') != project or context.get('environment', {}).get('host') != 'desktop' or
            read_record['created'] <= close_record['created']):
        raise ValueError('FRESH_EXACT_PROJECT_REQUIRED')
    directory = Path(path).parent.resolve()
    refs = proof.get('persisted_sources', [])
    if (not refs or not any(ref['path'].endswith('.esch2') for ref in refs) or
            not any(ref['path'].endswith('.epcb2') for ref in refs) or
            not any(ref['path'] == Path(path).name for ref in refs)):
        raise ValueError('PERSISTED_NATIVE_SOURCES_REQUIRED')
    stored_attributes = set()
    for ref in refs:
        source = directory / ref['path']
        if source.is_symlink() or not source.resolve().is_relative_to(directory) or digest(source) != ref['sha256']:
            raise ValueError('PERSISTED_NATIVE_SOURCE_CHANGED')
        if source.suffix == '.esch2':
            stored_attributes |= native_attribute_ids(source, proof['document'])
    scenes = []
    for name in ('before_read', 'after_read', 'after_read_again'):
        record, scene = records[name]
        ctx = scene.get('context', {})
        if ctx.get('projectUuid') != project or ctx.get('documentUuid') != proof['document']:
            raise ValueError('NATIVE_DOCUMENT_CHANGED')
        if name != 'before_read' and record['created'] <= close_record['created']:
            raise ValueError('POST_CLOSE_READ_REQUIRED')
        if name == 'before_read' and record['created'] >= close_record['created']:
            raise ValueError('PRE_CLOSE_READ_REQUIRED')
        scenes.append(canonical_scene(scene, stored_attributes))
    if len(set(scenes)) != 1:
        raise ValueError('PRESERVED_NATIVE_SCENE_MISMATCH')
    if records['after_read_again'][0]['created'] <= records['after_read'][0]['created']:
        raise ValueError('SECOND_FRESH_NATIVE_READ_REQUIRED')
    return {'project': project, 'request_id': prior['request_id'], 'action': prior['action'],
            'old_session': proof['old_session'], 'new_session': proof['new_session'],
            'native_scene_sha256': scenes[0], 'original_unknown': prior,
            'renderer_scope': 'Exact persisted SCH/PCB bytes, primitive and pin geometry, nets and stored attributes. Unstored pin-label ID/layout fields are renderer-derived; raw inventories retained.',
            'original_outcome_rewritten': False, 'unknown_action_replayed': False,
            'resolution': 'Old CLI editing generation closed; exact persisted design freshly read in new generation. Future repair requires a new plan from current state.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--singleton-port', type=int, default=60901)
    args = parser.parse_args()
    # Same kernel lease as the connector. No transport can be launched while
    # its unresolved state is being reconciled.
    with socket.socket() as lease:
        lease.bind(('127.0.0.1', args.singleton_port))
        lease.listen(1)
        with sqlite3.connect('file:' + str(args.root/'runtime/state/workbench.sqlite') + '?mode=ro', uri=True) as db:
            if db.execute("SELECT 1 FROM conversations WHERE status='RUNNING'").fetchone() or db.execute(
                    "SELECT 1 FROM eda_cli_jobs WHERE status='RUNNING'").fetchone():
                raise ValueError('RECOVERY_REQUIRES_IDLE_EXECUTION')
        raw = args.state.read_bytes()
        blocked = json.loads(raw)
        proof = json.loads(args.proof.read_text())
        binding = validate_campaign_binding(args.root, proof)
        record = validate_evidence(blocked, proof, args.proof.parent)
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out/'original-unknown-state.json').write_bytes(raw)
        (args.out/'proof.json').write_bytes(args.proof.read_bytes())
        next_state = {k: v for k, v in blocked.items() if k != proof['project']}
        payload = (json.dumps(next_state, indent=2) + '\n').encode()
        report = {'schema_version': 'bf-native-unknown-resolution-v1', 'created': time.time(),
                  'actor': proof['actor'], 'owner': proof['owner'], **binding, **record,
                  'proof_sha256': digest(args.proof), 'original_state_sha256': hashlib.sha256(raw).hexdigest(),
                  'new_state_sha256': hashlib.sha256(payload).hexdigest(), 'model_calls': 0,
                  'model_ledger_writes': 0, 'participant_design_edits': 0}
        (args.out/'resolution.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        if args.state.read_bytes() != raw:
            raise ValueError('NATIVE_UNKNOWN_STATE_CHANGED_DURING_RECONCILIATION')
        temp = args.state.with_suffix('.reconciled-next')
        temp.write_bytes(payload); temp.chmod(0o600); temp.replace(args.state)
        print(args.out/'resolution.json')


if __name__ == '__main__':
    main()
