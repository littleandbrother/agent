"""Public prose-only projection for the current LC scenario.

Original frozen public/host inputs and raw bindings stay immutable. Numeric
service fields define this model; two inherited descriptive absolute anchors
are rendered from those current fields. No consumer/evaluator input changes.
"""
from copy import deepcopy
import lc_host


def participant_task(public=None):
    public=lc_host.load_public() if public is None else public
    task=deepcopy(public['Task'])
    service=task['service']
    service['new_sample_receive_scope']=(
        'Samples created while gateway is available, including those created at/after'
        +str(service['recovery_at_s'])+'; use acquisition time, not frame live/history label.')
    service['history']=(
        'Every committed record retained without corruption; receive all pre-recovery unacknowledged records by'
        +str(service['recovery_old_history_deadline_s'])+' in acquisition order with no duplicate logical samples.')
    return task
