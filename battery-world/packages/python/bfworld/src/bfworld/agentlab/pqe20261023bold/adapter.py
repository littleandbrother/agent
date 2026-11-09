"""Explicit common dispatcher; it gives neither task-specific choices nor advice."""
from . import lc_adapter


def is_lc(task):
    return task.get("public_inputs", {}).get("consumer_contract_task_id") == "LC-PV-STRICT-24H-v1"


def source_identity():
    from . import consumer
    return {"door": consumer.source_identity(), "lc": lc_adapter.source_identity()}


def validate_design(task, design):
    if is_lc(task):
        return lc_adapter.validate_design(task, design)
    from . import consumer
    return consumer.validate_design(task, design)


def execute(task, design, problem, decision, output_dir=None, *, task_resolver=None, lc_context=None):
    if is_lc(task):
        return lc_adapter.execute(task, design, problem, decision, output_dir,
                                  task_resolver=task_resolver, context=lc_context)
    from . import consumer
    return consumer.execute(task, design, problem, decision, output_dir, task_resolver=task_resolver)
