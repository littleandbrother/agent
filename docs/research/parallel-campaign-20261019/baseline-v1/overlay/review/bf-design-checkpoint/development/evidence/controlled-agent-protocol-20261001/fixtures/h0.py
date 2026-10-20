"""Trusted synthetic fixture; not participant-authored Harness or Agent."""
def plan(context):
    return {'value': context['value'] + 1, 'fixture': 'H0'}
