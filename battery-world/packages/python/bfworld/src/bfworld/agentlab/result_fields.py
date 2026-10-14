"""Bounded JSON field queries. No eval, file reads or expression execution."""
import re


def select_fields(value, fields):
    if not isinstance(fields, list) or not 1 <= len(fields) <= 24:
        raise ValueError('RESPONSE_FIELDS_REQUIRED')
    result = {}
    for path in fields:
        if not isinstance(path, str) or len(path) > 256 or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', path):
            raise ValueError('RESPONSE_FIELD_PATH_INVALID')
        node = value
        for part in path.split('.'):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdecimal() and int(part) < len(node):
                node = node[int(part)]
            else:
                raise ValueError('RESPONSE_FIELD_NOT_FOUND:' + path)
        result[path] = node
    return result
