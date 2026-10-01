"""Controlled trusted entrypoint failure; no participant code."""
def plan(context):
    raise RuntimeError('CONTROLLED_CALL_FAILURE')
