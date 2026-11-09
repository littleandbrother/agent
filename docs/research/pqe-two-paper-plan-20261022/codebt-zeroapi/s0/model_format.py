"""Bounded JSON/observed DSML normalization. No tool execution or model I/O."""
import json
import re

MAX_BYTES = 65536
MAX_CALLS = 8
TOKEN = '｜｜DSML｜｜'
OPEN = f'<{TOKEN} calls>'
CLOSE = f'</{TOKEN} calls>'
INVOKE = re.compile(r'<'+TOKEN+r' invoke name="([a-z_]+)">(.*?)</'+TOKEN+r' invoke>',re.S)
PARAM = re.compile(r'<'+TOKEN+r' parameter name="([a-z_]+)" string="(true|false)">(.*?)</'+TOKEN+r' parameter>',re.S)


def _pairs(items):
    out = {}
    for key,value in items:
        if key in out:raise ValueError('DUPLICATE_JSON_FIELD')
        out[key] = value
    return out


def _load(text):
    def nonfinite(_):raise ValueError('NONFINITE_JSON')
    value=json.loads(text,object_pairs_hook=_pairs,parse_constant=nonfinite)
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1
        if depth>16 or count>4096:raise ValueError('JSON_STRUCTURE_CAP')
        if isinstance(item,dict):pending.extend((v,depth+1) for v in item.values())
        elif isinstance(item,list):pending.extend((v,depth+1) for v in item)
    return value


def _arguments(value):
    if not isinstance(value,dict) or set(value)!={'object_id','section','offset'}:
        raise ValueError('PUBLIC_OBJECT_ARGUMENT_FIELDS')
    if not isinstance(value['object_id'],str) or not re.fullmatch('pub-[0-9a-f]{64}',value['object_id']):
        raise ValueError('PUBLIC_OBJECT_ID')
    section=value['section']
    if not isinstance(section,str) or len(section)>512 or (section and not section.startswith('/')) or re.search(r'~(?![01])',section) or any(ord(c)<32 for c in section):
        raise ValueError('PUBLIC_JSON_POINTER')
    if type(value['offset']) is not int or not 0<=value['offset']<=1000000:
        raise ValueError('PUBLIC_OBJECT_OFFSET')
    return value


def _validate_tools(payload):
    if 'tool_calls' not in payload:return
    calls=payload['tool_calls']
    if set(payload)!={'tool_calls'} or not isinstance(calls,list) or not 1<=len(calls)<=MAX_CALLS:
        raise ValueError('TOOL_CALL_CAP_OR_ROOT_FIELDS')
    for call in calls:
        if not isinstance(call,dict) or set(call)!={'name','arguments'} or call['name']!='public_object':
            raise ValueError('TOOL_NOT_ALLOWED')
        _arguments(call['arguments'])


def parse_model_output(text):
    """Return a payload or a format error; never infer a design or invoke tools."""
    try:
        if not isinstance(text,str) or len(text.encode())>MAX_BYTES:raise ValueError('TEXT_BYTE_CAP')
        stripped=text.strip()
        try:
            value=_load(stripped)
        except json.JSONDecodeError:
            value=None
        if value is not None:
            if not isinstance(value,dict):raise ValueError('JSON_OBJECT_REQUIRED')
            _validate_tools(value)
            return {'status':'OK','format':'JSON','payload':value}
        if not stripped.startswith(OPEN) or not stripped.endswith(CLOSE):raise ValueError('COMPLETE_DSML_REQUIRED')
        body=stripped[len(OPEN):-len(CLOSE)]
        cursor=0;calls=[]
        for invoke in INVOKE.finditer(body):
            if body[cursor:invoke.start()].strip():raise ValueError('AMBIGUOUS_DSML')
            if invoke.group(1)!='public_object':raise ValueError('TOOL_NOT_ALLOWED')
            fields={};p_cursor=0;params=invoke.group(2)
            for param in PARAM.finditer(params):
                if params[p_cursor:param.start()].strip():raise ValueError('AMBIGUOUS_PARAMETER')
                name,is_string,raw=param.groups()
                if name in fields:raise ValueError('DUPLICATE_DSML_FIELD')
                if name not in {'arguments','name','object_id','section','offset'}:raise ValueError('DSML_FIELD_NOT_ALLOWED')
                if '<' in raw or '>' in raw:raise ValueError('NESTED_DSML')
                fields[name]=raw if is_string=='true' else _load(raw)
                p_cursor=param.end()
            if params[p_cursor:].strip():raise ValueError('INCOMPLETE_PARAMETER')
            if 'arguments' in fields:
                if set(fields) not in ({'arguments'},{'arguments','name'}) or fields.get('name','public_object')!='public_object':
                    raise ValueError('AMBIGUOUS_ARGUMENT_FORM')
                arguments=fields['arguments']
            else:
                if set(fields)!={'object_id','section','offset'}:raise ValueError('DIRECT_ARGUMENT_FIELDS')
                arguments=fields
            calls.append({'name':'public_object','arguments':_arguments(arguments)})
            if len(calls)>MAX_CALLS:raise ValueError('TOOL_CALL_CAP')
            cursor=invoke.end()
        if body[cursor:].strip() or not calls:raise ValueError('INCOMPLETE_CALLS')
        payload={'tool_calls':calls};_validate_tools(payload)
        return {'status':'OK','format':'DSML','payload':payload}
    except (ValueError,TypeError,RecursionError) as exc:
        return {'status':'FORMAT_ERROR','error':str(exc),'payload':None,'retry_scope':'Same future episode budget only; never a design or scientific failure.'}
