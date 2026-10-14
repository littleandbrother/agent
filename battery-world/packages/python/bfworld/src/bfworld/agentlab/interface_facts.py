"""Read current candidate interfaces in one bounded, source-bound operation."""
import hashlib
import ast
import json
import re


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def firmware_timing(text, path, source_hash):
    """Literal Nordic configuration only; never execute arbitrary C expressions."""
    facts = []
    patterns = {
        'ble.advertising_ms': (r'^\s*#define\s+APP_ADV_INTERVAL\s+(\d+)\b', 0.625),
        'ble.connection_min_ms': (r'^\s*#define\s+MIN_CONN_INTERVAL\s+MSEC_TO_UNITS\(\s*(\d+)\s*,\s*UNIT_1_25_MS\s*\)', 1),
        'ble.connection_max_ms': (r'^\s*#define\s+MAX_CONN_INTERVAL\s+MSEC_TO_UNITS\(\s*(\d+)\s*,\s*UNIT_1_25_MS\s*\)', 1),
        'policy.sample_ms': (r'^\s*\.sample_period_ms\s*=\s*(\d+)\b', 1),
        'policy.advertising_ms': (r'^\s*\.adv_period_ms\s*=\s*(\d+)\b', 1),
        'policy.connection_ms': (r'^\s*\.conn_param_period_ms\s*=\s*(\d+)\b', 1),
    }
    for number, line in enumerate(text.splitlines(), 1):
        for name, (pattern, factor) in patterns.items():
            match = re.match(pattern, line)
            if match:
                facts.append({'id': name, 'value': int(match[1])*factor, 'unit': 'ms',
                    'source': {'path': path, 'sha256': source_hash, 'line': number},
                    'definition': line.strip()})
    return facts


def compare_bindings(bindings, facts):
    """Pi declares correspondence; comparison returns facts and affected domains."""
    lookup = {f['id']: f for f in facts}
    result = []
    for link in bindings:
        left, right = lookup.get(link.get('left')), lookup.get(link.get('right'))
        status = 'NOT_CHECKED'
        if left and right:
            if left.get('unit') is not None and right.get('unit') is not None:
                status = 'PASS' if left['unit'] == right['unit'] and left['value'] == right['value'] else 'FAIL'
        result.append({'left': link.get('left'), 'right': link.get('right'), 'status': status,
            'values': [left, right], 'affected': link.get('affected', [])})
    return result


def referenced_value(raw, name, source):
    """Read a declared literal location; a source hash alone is not a value."""
    if 'json_pointer' in source and name.endswith('.json'):
        value=json.loads(raw)
        pointer=source['json_pointer']
        if not isinstance(pointer,str) or (pointer and not pointer.startswith('/')):
            raise ValueError('INTERFACE_JSON_POINTER_REQUIRED')
        for key in pointer.split('/')[1:] if pointer else []:
            key=key.replace('~1','/').replace('~0','~')
            value=value[int(key)] if isinstance(value,list) else value[key]
        return value,None
    if 'fact_id' in source and name.endswith('.c'):
        matches=[f for f in firmware_timing(raw.decode(),name,digest(raw)) if f['id']==source['fact_id']]
        if len(matches)!=1:raise ValueError('INTERFACE_FIRMWARE_FACT_NOT_FOUND')
        return matches[0]['value'],matches[0]['unit']
    if name.endswith('.py') and ('symbol' in source or 'fact_id' in source):
        symbol = source.get('symbol')
        fact_id = source.get('fact_id')
        if fact_id is not None:
            if not isinstance(fact_id, str) or not fact_id.startswith('cad.'):
                raise ValueError('INTERFACE_CAD_FACT_REQUIRED: '+name+'; use fact_id=cad.P.pcb_l or symbol=P.pcb_l')
            if symbol is not None and symbol != fact_id[4:]:
                raise ValueError('INTERFACE_CAD_SELECTOR_CONFLICT: '+name)
            symbol = fact_id[4:]
        if not isinstance(symbol, str) or not symbol:
            raise ValueError('INTERFACE_CAD_SYMBOL_REQUIRED: '+name+'; use symbol=P.pcb_l')
        names=symbol.split('.')
        for statement in ast.parse(raw.decode()).body:
            if isinstance(statement,ast.Assign) and len(statement.targets)==1 and isinstance(statement.targets[0],ast.Name) and statement.targets[0].id==names[0]:
                value=ast.literal_eval(statement.value)
                for key in names[1:]:value=value[key]
                return value,None
        raise ValueError('INTERFACE_CAD_SYMBOL_NOT_FOUND: '+name+'; symbol='+symbol)
    examples = {'.json': 'source.json_pointer=/path/to/value',
                '.py': 'source.symbol=P.pcb_l or source.fact_id=cad.P.pcb_l',
                '.c': 'source.fact_id=ble.advertising_ms'}
    suffix = next((ext for ext in examples if name.endswith(ext)), None)
    raise ValueError('INTERFACE_FACT_SELECTOR_REQUIRED: '+name+'; '+examples.get(suffix, 'supported sources: .json, .py, .c'))


def cad_parameters(text, path, source_hash, unit):
    facts = []
    for statement in ast.parse(text).body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
            continue
        try:
            value = ast.literal_eval(statement.value)
        except (ValueError, TypeError):
            continue
        name = statement.targets[0].id
        # P01 puts its dimensions in a literal parameter dictionary. Counts and
        # dimensions share this dictionary, so keep the project unit as context
        # until a declared interface binding assigns the quantity's own unit.
        values = value.items() if isinstance(value, dict) else [(None, value)]
        for key, number in values:
            if type(number) not in (int, float) or (key is not None and not isinstance(key, str)):
                continue
            suffix = name + ('.' + key if key is not None else '')
            facts.append({'id':'cad.'+suffix, 'value':number, 'unit':None, 'declared_project_units':unit,
                'source':{'path':path,'sha256':source_hash,'line':statement.lineno}})
    return facts


def candidate_facts(design, workspace, paths=()):
    from .design_lab.paper_candidate import safe_file
    chosen = list(paths) if paths else [n for n in design['files'] if
        n.endswith(('interfaces.json', 'firmware-events.json', 'interface-bindings.json')) or
        ('fw' in n and n.endswith('/main.c'))]
    if not paths:
        from pathlib import PurePosixPath
        for manifest_path, project in design['projects'].items():
            if project.get('kind') != 'cadquery':
                continue
            for name in project.get('source_files', []):
                entry = str(PurePosixPath(manifest_path).parent / name)
                if entry.endswith('.py') and entry in design['files'] and entry not in chosen:
                    chosen.append(entry)
    if len(chosen) > 12 or len(chosen) != len(set(chosen)):
        raise ValueError('INTERFACE_EXPLICIT_PATHS_REQUIRED_MAX_12')
    sources, facts, reviews, bindings = [], [], [], []
    for name in chosen:
        if name not in design['files']:
            raise ValueError('INTERFACE_FILE_NOT_IN_CANDIDATE:' + name)
        path = safe_file(workspace, name)
        raw = path.read_bytes(); source_hash = digest(raw)
        if source_hash != design['files'][name]['sha256']:
            raise ValueError('INTERFACE_INPUT_CHANGED_RECHECK_REQUIRED:' + name)
        if len(raw) > 2*1024*1024:
            raise ValueError('INTERFACE_INPUT_TOO_LARGE:' + name)
        reference = {'path': name, 'sha256': source_hash}
        sources.append(reference)
        if name.endswith('.c'):
            facts.extend(firmware_timing(raw.decode(), name, source_hash))
            continue
        if name.endswith('.py'):
            units = {p.get('interfaces', {}).get('units') for p in design['projects'].values()
                     if p.get('kind') == 'cadquery'}
            if len(units) != 1 or None in units: raise ValueError('CAD_DECLARED_UNITS_REQUIRED')
            facts.extend(cad_parameters(raw.decode(), name, source_hash, next(iter(units))))
            continue
        value = json.loads(raw)
        if name.endswith('interface-bindings.json'):
            if value.get('schema_version') != 'bf-interface-bindings-v1':
                raise ValueError('INTERFACE_BINDING_SCHEMA_REQUIRED')
            for fact in value.get('facts', []):
                ref = fact['source']; ref_name = ref['path']
                source_raw=safe_file(workspace,ref_name).read_bytes() if ref_name in design['files'] else None
                if source_raw is None or digest(source_raw) != ref['sha256']:
                    raise ValueError('INTERFACE_FACT_SOURCE_CHANGED:' + ref_name)
                observed,unit=referenced_value(source_raw,ref_name,ref)
                if type(observed)!=type(fact['value']) and not (type(observed) in (int,float) and type(fact['value']) in (int,float)):
                    raise ValueError('INTERFACE_FACT_VALUE_TYPE_MISMATCH:'+fact['id'])
                if observed!=fact['value'] or (unit is not None and unit!=fact['unit']):
                    raise ValueError('INTERFACE_FACT_VALUE_MISMATCH:'+fact['id'])
                facts.append({**fact,'value_verified':True})
            bindings.extend(value.get('bindings', []))
        else:
            # These are existing independent observations, with their own source hashes.
            stale = []
            for source_name, expected in value.get('source_sha256', {}).items():
                local = workspace / source_name
                if not local.resolve().is_relative_to(workspace.resolve()) or not local.is_file() or digest(local.read_bytes()) != expected:
                    stale.append(source_name)
            reviews.append({'source': reference, 'source_status': 'RECHECK_REQUIRED' if stale else 'CURRENT',
                'changed_sources': stale, 'checks': value.get('checks', []),
                'timeline': {k:value[k] for k in ('events', 'decoded', 'sample_period_ms') if k in value}})
    if len({f['id'] for f in facts}) != len(facts):
        raise ValueError('INTERFACE_FACT_ID_AMBIGUOUS')
    values = {f['id']: f for f in facts}
    contrasts = []
    for actual, model in [('ble.advertising_ms', 'policy.advertising_ms'),
                          ('ble.connection_min_ms', 'policy.connection_ms')]:
        if actual in values and model in values and values[actual]['value'] != values[model]['value']:
            contrasts.append({'actual': values[actual], 'policy': values[model],
                'difference_ms': values[model]['value']-values[actual]['value']})
    return {'schema_version': 'bf-candidate-interface-facts-v1', 'design_id': design['design_id'],
        'sources': sources, 'facts': facts, 'parameter_contrasts': contrasts,
        'bindings': compare_bindings(bindings, facts), 'reviews': reviews,
        'input_sha256': digest(json.dumps(sources, sort_keys=True).encode())}
