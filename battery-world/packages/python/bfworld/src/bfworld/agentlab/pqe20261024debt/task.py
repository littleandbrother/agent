"""One prospective family. Construction and validation do not run a solver."""
from copy import deepcopy
from collections import OrderedDict
import json
from ..pqe20261023bold.consumer import EXTRA_DOMAIN as BOLD_DOMAIN

VERSION = "codebt-door-task-v1"
FAMILY_ID = "CODEBT-DOOR-20261024-v1"
HOLDING_DOMAIN = {
    "holding_component": {"kind": "enum", "values": ["off", "lp_fifo"]},
    "holding_capacity": {"kind": "integer", "min": 1, "max": 4},
    "holding_overflow": {"kind": "enum", "values": ["drop_new", "overwrite_oldest"]},
    "read_source": {"kind": "enum", "values": ["contact_only", "holding_then_contact"]},
    "clear_after": {"kind": "enum", "values": ["early", "save", "ack", "never"]},
}
HOLDING_DEFAULTS = {"holding_component": "off", "holding_capacity": 2,
                    "holding_overflow": "drop_new", "read_source": "contact_only",
                    "clear_after": "never"}
BASE_DOMAIN = {
    "brownout_v": {"kind": "number", "min": 1.8, "max": 2.0},
    "capacitance_f": {"kind": "number", "min": 1e-5, "max": .001},
    "debounce_s": {"kind": "number", "min": 0., "max": .5},
    "esr_ohm": {"kind": "number", "min": .1, "max": 100.},
    "mechanism": {"kind": "mechanism", "editable": {
        "stroke_m": [.006, .0085], "cam_base_radius_m": [.006, .008]}},
    "persistent_queue": {"kind": "boolean"},
    "retry_s": {"kind": "number", "min": .01, "max": 1.},
    "startup_v": {"kind": "number", "min": 1.9, "max": 3.2},
    "tx_gate_v": {"kind": "number", "min": 1.8, "max": 3.3},
    **deepcopy(BOLD_DOMAIN),
}
DESIGN_DOMAIN = {**BASE_DOMAIN, **HOLDING_DOMAIN}
DEFAULT_DESIGN = {
    "brownout_v": 1.8, "capacitance_f": .0001, "debounce_s": .07,
    "esr_ohm": 5., "mechanism": {}, "persistent_queue": False,
    "retry_s": .1, "startup_v": 2.2, "tx_gate_v": 2.2,
    "firmware_policy": "fixed_retry_v1", "backoff_max_s": 1., "tx_reserve_v": .025,
    **HOLDING_DEFAULTS,
}
COMPONENTS = {"boot_a": .001, "boot_s": .002, "idle_a": 2e-6,
              "leakage_ohm": 1e8, "max_v": 3.3, "tx_a": .015,
              "tx_s": .006, "write_a": .003, "write_s": .002,
              "provenance": "Original constructed DOOR load assumptions; not calibrated hardware."}
SERVICE = {"closed_deg": 10., "open_deg": 80., "stable_s": .06,
           "receive_deadline_s": 2., "handle_force_max_n": .5,
           "require_event_order": True, "require_no_spurious_event_ids": True,
           "initial_state_event": False, "target_loss_rate": .01,
           "loss_rate_status": "Finite constructed task; no population-loss qualification.",
           "device_absolute_time": "Unavailable; sequence and direction frame only."}
SELECTION_RULES = (
    {"id": "short-cold", "starts_s": [73., 187., 51007.],
     "opening": [(0, 74, 1.1), (74, 90, .14)], "hold_s": .18,
     "closing": [(90, 16, .95), (16, 0, .14)], "link_gaps": False},
    {"id": "reset-link", "starts_s": [89., 95., 43009.],
     "opening": [(0, 79, .85), (79, 90, .55)], "hold_s": .35,
     "closing": [(90, 11, .85), (11, 0, .55)], "link_gaps": True},
    {"id": "simple-control", "starts_s": [61., 65., 69.],
     "opening": [(0, 90, 1.25)], "hold_s": .5,
     "closing": [(90, 0, 1.25)], "link_gaps": False},
)


def base_design(design):
    return {k: deepcopy(v) for k, v in design.items() if k not in HOLDING_DOMAIN}


STATIC_GEOMETRY_CACHE_VERSION = "codebt-static-geometry-memo-v1"
_STATIC_GEOMETRY_CACHE_LIMIT = 16
_STATIC_GEOMETRY_CACHE = OrderedDict()


def static_geometry_facts(mechanism):
    """Same source algebra, with a bounded memo bound to exact inputs/source."""
    from ..pqe20261022 import door_model
    source_step = door_model.source_step
    try:
        # JSON preserves numeric representations (including int/float and -0),
        # and includes the full mapping rather than a rounded geometry subset.
        # Mutable model constants participate alongside the function/code identity.
        inputs_key = json.dumps({"mechanism": mechanism,
                                 "defaults": door_model.DEFAULT_MECHANISM,
                                 "domain": door_model.DOMAIN}, sort_keys=True,
                                separators=(",", ":"), allow_nan=False)
        cache_key = (source_step, getattr(source_step, "__code__", None), inputs_key)
        cached = _STATIC_GEOMETRY_CACHE.get(cache_key)
    except (TypeError, ValueError):
        # Uncacheable/invalid input still follows the original source function.
        cache_key, cached = None, None
    if cached is not None:
        _STATIC_GEOMETRY_CACHE.move_to_end(cache_key)
        return deepcopy(cached)
    result = source_step(0., 0., 0., mechanism)
    codes = {"assembly_envelope_exceeded", "cam_pressure_angle_exceeded"}
    facts = {"model_id": result["model_id"], "geometry": deepcopy(result.get("geometry")),
            "domain_errors": [e for e in result["domain_errors"] if e in codes],
            "depends_on": ["mechanism.stroke_m", "mechanism.cam_base_radius_m", "fixed model geometry/domain"],
            "source": "bfworld.agentlab.pqe20261022.door_model:source_step",
            "scope": "Static geometry only; dynamic source validity is checked independently by the consumer."}
    if cache_key is not None:
        _STATIC_GEOMETRY_CACHE[cache_key] = deepcopy(facts)
        _STATIC_GEOMETRY_CACHE.move_to_end(cache_key)
        if len(_STATIC_GEOMETRY_CACHE) > _STATIC_GEOMETRY_CACHE_LIMIT:
            _STATIC_GEOMETRY_CACHE.popitem(last=False)
    return deepcopy(facts)


def validate_design(task, design):
    """Task permission is authoritative; model fields alone confer no rights."""
    if set(design) != set(task["design_domain"]):
        raise ValueError("CODEBT_DESIGN_FIELDS_OUTSIDE_TASK")
    for k in HOLDING_DOMAIN:
        if task["design_domain"].get(k) != HOLDING_DOMAIN[k]:
            raise ValueError("CODEBT_HOLDING_CONTRACT:" + k)
    from ..pqe20261023bold.consumer import validate_design as validate_bold
    old_task = deepcopy(task)
    old_task["design_domain"] = {k: v for k, v in task["design_domain"].items() if k not in HOLDING_DOMAIN}
    validate_bold(old_task, base_design(design))
    for k, spec in HOLDING_DOMAIN.items():
        value = design[k]
        if spec["kind"] == "enum":
            if value not in spec["values"]:
                raise ValueError("CODEBT_ENUM:" + k)
        elif type(value) is not int or not spec["min"] <= value <= spec["max"]:
            raise ValueError("CODEBT_INTEGER:" + k)
    geometry_errors = static_geometry_facts(design["mechanism"])["domain_errors"]
    if geometry_errors:
        raise ValueError("CODEBT_STATIC_MODEL_DOMAIN:" + ",".join(geometry_errors))


def make_task_family():
    """Three immutable-by-content stimuli selected without executing any design."""
    tasks = []
    for rule in SELECTION_RULES:
        motion = []
        for start in rule["starts_s"]:
            t = start
            for a, b, duration in rule["opening"]:
                motion.append(dict(start_s=t, end_s=t+duration, start_deg=a, end_deg=b))
                t += duration
            t += rule["hold_s"]
            for a, b, duration in rule["closing"]:
                motion.append(dict(start_s=t, end_s=t+duration, start_deg=a, end_deg=b))
                t += duration
        gaps = [[s+1.1, s+2.1] for s in rule["starts_s"]] if rule["link_gaps"] else []
        windows, left = [], 0.
        for a, b in gaps:
            windows.append([left, a]); left = b
        windows.append([left, 86400.])
        task = {"schema_version": VERSION, "task_id": FAMILY_ID + ":" + rule["id"],
                "family_id": FAMILY_ID, "condition_id": rule["id"], "duration_s": 86400.,
                "description": "New prescribed event-recording family; necessity and service remain unknown.",
                "allowed_for_learning": False, "exposure": "Common prospective conditions, no outcome selection.",
                "initial": {"angle_deg": 0., "capacitor_v": 0., "event_counter": 0,
                            "logical_state": 0, "mechanical_stored_j": 0., "queue": []},
                "components": deepcopy(COMPONENTS), "sensor": {"open_deg": 80., "closed_deg": 10.,
                    "bounce_offsets_s": [0., .012, .024, .036, .048]},
                "service": deepcopy(SERVICE), "motion": motion, "gateway_windows": windows,
                "required_delivery_present": True,
                "geometry": {"door_height_m": .6, "door_width_m": .45, "handle_radius_m": .4,
                             "installation_envelope_mm": [60, 35, 20]},
                "design_domain": deepcopy(DESIGN_DOMAIN), "initial_design": deepcopy(DEFAULT_DESIGN),
                "integration": {"dt_s": .001, "allowed_dt_s": [.001, .0005],
                    "method": "Original midpoint loaded source; new paid holder and event-aware idle integration."},
                "selection_rule": deepcopy(rule),
                "qualification_claim": "Declared constructed model; physical qualification UNKNOWN."}
        fields = list(DESIGN_DOMAIN)
        task["initial_problem"] = {"active_variables": fields, "groups": [fields.copy()],
            "fixed_choices": {}, "assumptions": ["Task, service, source, holder coefficients and evaluator are fixed."],
            "local_objective": "Meet all original service requirements in the common new family."}
        validate_design(task, task["initial_design"])
        tasks.append(task)
    return tasks
