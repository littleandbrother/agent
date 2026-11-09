"""Public component/operation facts. No repairs, obligations or service labels."""
from copy import deepcopy

from ..pqe20261022.executor import identity
from .holding import PROFILE, VERSION as HOLDER_VERSION
from .task import DESIGN_DOMAIN, DEFAULT_DESIGN, COMPONENTS, validate_design

VERSION = "codebt-component-facts-v1"
SOURCE = "bfworld.agentlab.pqe20261024debt"
KINDS = ["production", "consumption", "handoff", "reset", "capacity", "timing", "load", "dynamic"]
RELATIONS = ["produces", "reads", "available_after", "clear_trigger", "survives_reset",
             "identity_storage", "bounded_by", "expires_after", "connected_to", "observed"]


def describe_contract():
    """Shared, outcome-independent vocabulary for all search conditions."""
    return {"schema": "codebt-fact-contract-v1", "version": VERSION,
        "design_domain": deepcopy(DESIGN_DOMAIN), "defaults": deepcopy(DEFAULT_DESIGN),
        "components": {"holder": {"version": HOLDER_VERSION, **deepcopy(PROFILE)},
                       "mcu": deepcopy(COMPONENTS)},
        "fact_kinds": list(KINDS), "relations": list(RELATIONS),
        "operations": {
            "capture": {"inputs": ["current_contact"], "outputs": ["holding_record"],
                "domain": "holder voltage domain, stable powered contact; no MCU required",
                "commit": "after paid capture_s", "interruption": "uncommitted capture discarded"},
            "read": {"inputs": ["holding_record"], "outputs": ["mcu_pending", "holding_seq_claim"],
                "commit": "after paid read_s; holder claim is assigned MCU seq, retained only in holder domain",
                "interruption": "no claim or pending import before completion"},
            "save": {"inputs": ["mcu_pending"], "outputs": ["ram_queue", "nvm_queue_if_enabled"],
                "commit": "original paid atomic SAVE", "interruption": "old NVM image retained; volatile pending discarded"},
            "tx": {"inputs": ["ram_queue_head"], "outputs": ["wire_frame"],
                "commit": "original completed CRC frame", "interruption": "partial frame not delivered"},
            "ack": {"inputs": ["wire_frame", "actual_gateway_confirmation"], "outputs": ["queue_head_removed"],
                "commit": "original paid atomic ACK; receiver sequence dedup remains independent"},
            "clear": {"inputs": ["holding_seq_claim"], "outputs": ["holding_slot_released"],
                "commit": "paid clear_s; only matching claimed FIFO head removed",
                "interruption": "holder record unchanged"}},
        "semantics": {
            "clear_after": {"early": "read_commit -> clear_commit -> SAVE",
                            "save": "SAVE_commit -> clear; queue retention depends on persistent_queue",
                            "ack": "ACK_commit -> clear; ACK follows actual gateway confirmation",
                            "never": "no clear operation; expiry/overflow/domain loss still apply"},
            "reentry": "Paid reread returns existing assigned_seq. Durable seq/queue distinguishes already committed or ACKed records; holder loss clears its claims. Host audit epoch is never a device input.",
            "reliability_scope": "NVM after SAVE and independently accepted receiver after ACK are different handoff destinations. No chosen placement is declared globally correct.",
            "energy": "C*dV/dt = source(theta,omega,V)-I_mcu-I_holder-V/Rleak; load_j=integral(Vbus*(I_mcu+I_holder)dt). Shared series-branch loss is diagnostic subset, not added twice.",
            "off": "Exact original BOLD execute_design route, no holder/read/clear load or state.",
            "dynamic": "Static relationships do not establish actual voltage coverage, identity recovery, energy closure or full service; unobserved evidence is null/UNKNOWN."},
        "source_refs": [SOURCE+".holding:EventHolding", SOURCE+".consumer:HoldingDoorProgram",
                        SOURCE+".consumer:_execute_enabled", SOURCE+".task:DESIGN_DOMAIN"]}


def design_facts(design, task=None):
    permission = task if task is not None else {"design_domain": DESIGN_DOMAIN, "components": COMPONENTS}
    validate_design(permission, design)
    enabled = design["holding_component"] != "off"
    reads = enabled and design["read_source"] == "holding_then_contact"
    persistent = design["persistent_queue"]
    facts = []

    def add(identifier, kind, subject, relation, obj, value, fields, ref):
        facts.append({"id": identifier, "kind": kind, "subject": subject, "relation": relation,
                      "object": obj, "value": value, "depends_on": fields,
                      "source_refs": [SOURCE+r if r.startswith(".") else r for r in ref.split(";")]})

    add("holder.production", "production", "holder", "produces", "holding_record",
        {"enabled": enabled, "voltage_domain_v": [PROFILE["voltage_min_v"], PROFILE["voltage_max_v"]],
         "input": "current_contact", "requires_mcu_power": False}, ["holding_component"], ".holding:prepare/advance")
    add("program.read", "consumption", "program.read", "reads", "holding_record",
        {"enabled": reads, "configured_source": design["read_source"], "order": "holder prefix before direct contact"},
        ["holding_component", "read_source"], ".consumer:HoldingDoorProgram.begin_step")
    add("pending.created", "handoff", "mcu_pending", "available_after", "read_commit",
        {"enabled": reads, "survives_mcu_reset": False}, ["holding_component", "read_source"], ".consumer:HoldingDoorProgram.advance")
    add("queue.handoff", "handoff", "mcu_queue", "available_after", "save_commit",
        {"destination": "nvm_queue" if persistent else "ram_queue", "survives_mcu_reset": persistent,
         "atomic": True, "dynamic_observation": None, "status": "UNKNOWN"},
        ["persistent_queue"], ".consumer:HoldingDoorProgram.advance;bfworld.agentlab.pqe20261022.door_program:DoorProgram.advance")
    add("receiver.handoff", "handoff", "receiver", "available_after", "ack_commit",
        {"receiver_acceptance_precedes_ack": True, "sequence_dedup": True,
         "survives_mcu_reset": True, "dynamic_observation": None, "status": "UNKNOWN"},
        ["persistent_queue", "retry_s", "tx_gate_v", "firmware_policy", "backoff_max_s", "tx_reserve_v"],
        ".consumer:HoldingDoorProgram.advance;bfworld.agentlab.pqe20261022.door_program:DoorProgram.advance")
    add("holder.clear", "handoff", "program.clear", "clear_trigger", "holding_slot_release",
        {"enabled": reads and design["clear_after"] != "never", "placement": design["clear_after"],
         "trigger": {"early": "read_commit", "save": "save_commit", "ack": "ack_commit", "never": None}[design["clear_after"]]},
        ["holding_component", "read_source", "clear_after"], ".consumer:HoldingDoorProgram._clear/advance")
    add("holder.reset", "reset", "holding_record", "survives_reset", "holder_voltage_loss",
        {"survives": False, "claim_survives": False, "mcu_reset_alone_clears": False},
        ["holding_component", "capacitance_f", "esr_ohm", "startup_v", "brownout_v", "mechanism"], ".holding:power_loss")
    add("program.identity", "reset", "sequence_identity", "identity_storage", "mcu_and_holder",
        {"mcu_committed_seq_survives_reset": persistent, "holder_claim_survives_mcu_only_reset": enabled,
         "holder_token_survives_holder_loss": False, "claim_created_after": "paid_read_commit",
         "observer_epoch_is_device_input": False}, ["persistent_queue", "holding_component", "read_source"], ".holding:read_commit;.consumer:HoldingDoorProgram.advance")
    add("holder.capacity", "capacity", "holding_record", "bounded_by", "holder_fifo",
        {"capacity": design["holding_capacity"], "overflow": design["holding_overflow"],
         "cleared_slots_reusable": True, "expiry_releases_slot": True},
        ["holding_component", "holding_capacity", "holding_overflow", "clear_after"], ".holding:advance/clear_commit")
    add("holder.retention", "timing", "holding_record", "expires_after", "powered_holder_time",
        {"seconds": PROFILE["retention_s"], "no_unpowered_clock": True, "voltage_loss_discards": True},
        ["holding_component", "capacitance_f", "esr_ohm", "mechanism"], ".holding:advance/power_loss")
    add("supply.connection", "load", "holder_and_program_operations", "connected_to", "shared_loaded_bus",
        {"implemented": True, "static_current_a": PROFILE["monitor_a"] if enabled else 0.,
         "execution_observed": None, "status": "UNKNOWN"},
        list(DESIGN_DOMAIN), ".consumer:_execute_enabled/_midpoint_step")
    add("dynamic.coverage", "dynamic", "current_design", "observed", "voltage_energy_identity_and_service",
        {"voltage_coverage": None, "energy_closure": None, "identity_recovery": None,
         "complete_service": None, "status": "UNKNOWN"}, list(DESIGN_DOMAIN), ".consumer:execute_design")
    loads = []
    for operation, a, duration in (("monitor", PROFILE["monitor_a"], None),
        ("capture", PROFILE["capture_a"], PROFILE["capture_s"]),
        ("read", PROFILE["read_a"], PROFILE["read_s"]),
        ("clear", PROFILE["clear_a"], PROFILE["clear_s"])):
        active = enabled and (operation not in ("read", "clear") or reads) and (operation != "clear" or design["clear_after"] != "never")
        loads.append({"component": "holder" if operation in ("monitor", "capture") else "mcu_holder_io",
            "operation": operation, "enabled": active, "current_a": a if active else 0., "duration_s": duration,
            "voltage_domain_v": [max(PROFILE["voltage_min_v"], design["brownout_v"]) if operation in ("read", "clear") else PROFILE["voltage_min_v"], PROFILE["voltage_max_v"]],
            "equation": "integral(Vbus*I_operation*dt); interruption still pays elapsed load",
            "depends_on": ["holding_component", "read_source", "clear_after", "capacitance_f", "esr_ohm", "startup_v", "brownout_v", "mechanism"],
            "source_refs": [SOURCE+".holding:PROFILE", SOURCE+".consumer:_execute_enabled"]})
    return {"schema": "codebt-design-facts-v1", "version": VERSION,
            "design_sha256": identity(design), "scope": {"task_id": task.get("task_id") if task else None,
                "static_only": True, "no_scientific_execution": True, "full_service": "UNKNOWN"},
            "facts": facts, "loads": loads}


PUBLIC_RELATION_VERSION = "codebt-public-record-relations-v2"


def public_record_relations(public):
    """Project only already-public observations; never read evaluator truth.

    Node IDs are source pointers, not extra device identities. A reused token
    is joined only while its publicly observed holder record remains live.
    Missing stages stay unknown; rereads do not create new captured records.
    """
    facts = public.get("facts", {}) if isinstance(public, dict) else {}
    available = isinstance(facts, dict)
    facts = facts if available else {}
    activity = facts.get("activity")
    activity = activity if isinstance(activity, list) else []
    events, records, holders, links, unknowns = [], [], [], [], []
    active_holders, latest_saved = {}, {}
    pending, last_read, mcu_resets = None, None, 0
    result_ref = public.get("result_sha256") if isinstance(public, dict) else None

    def event(action, row, pointer):
        item = {"id": pointer, "stage": action, "source_ref": pointer,
                "time_s": row.get("time_s"), "observed_mcu_resets": mcu_resets}
        if pointer.startswith("#/facts/receiver_records/"):
            from math import isfinite
            received_at = row.get("time_s")
            reset_times = [e.get("time_s") for e in activity
                           if isinstance(e, dict) and e.get("action") == "brownout"]
            valid_time = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
            known = valid_time(received_at) and all(valid_time(at) for at in reset_times)
            item["observed_mcu_resets"] = sum(at <= received_at for at in reset_times) if known else None
            item["mcu_reset_relation_status"] = "OBSERVED" if known else "UNKNOWN"
        # Explicit allowlist excludes observer_epoch, hidden truth and host labels.
        for key in ("seq", "direction", "token", "assigned_seq", "reason", "durable", "source", "placement"):
            if key in row:
                item[key] = deepcopy(row[key])
        if isinstance(row.get("record"), dict):
            item["record"] = {k: deepcopy(row["record"][k]) for k in
                              ("seq", "direction", "token", "assigned_seq") if k in row["record"]}
        events.append(item)
        return item

    def connect(first, second, relation, certainty="OBSERVED"):
        links.append({"from": first, "to": second, "relation": relation,
                      "status": certainty, "source_refs": [first, second]})

    def attach_saved(stage, row, ref):
        payload = row.get("record", row)
        key = (payload.get("seq"), payload.get("direction"))
        saved = latest_saved.get(key)
        if saved is None:
            unknowns.append({"stage_ref": ref, "relation": "preceding_save", "status": "UNKNOWN",
                             "reason": "No matching preceding public SAVE observation."})
        else:
            saved["stages"].setdefault(stage, []).append(ref)
            connect(saved["id"], ref, stage)

    stages = {"capture": "capture", "save_commit": "save", "wire_complete": "tx",
              "ack_commit": "ack", "holding_capture_commit": "holder_capture",
              "holding_read_commit": "read", "holding_clear_commit": "clear",
              "holding_expired": "expire", "holding_reset": "holder_reset",
              "brownout": "mcu_reset", "boot": "boot", "boot_complete": "boot_ready",
              "holding_read_invalidated": "read_invalidated",
              "holding_overflow_drop_new": "overflow_drop", "holding_overflow_overwrite": "overflow_overwrite"}
    for index, row in enumerate(activity):
        if not isinstance(row, dict) or row.get("action") not in stages:
            continue
        action = row["action"]
        ref = "#/facts/activity/"+str(index)
        event(stages[action], row, ref)
        payload = row.get("record", {}) if isinstance(row.get("record"), dict) else {}
        if action == "brownout":
            mcu_resets += 1
            pending, last_read = None, None
        elif action == "holding_reset":
            for held in active_holders.values():
                held["stages"].setdefault("holder_reset", []).append(ref)
            active_holders.clear()
            last_read = None
        elif action == "holding_capture_commit":
            held = {"id": ref, "token": payload.get("token"), "direction": payload.get("direction"),
                    "assigned_seq": payload.get("assigned_seq"), "record_key": {"assigned_seq": payload.get("assigned_seq"), "direction": payload.get("direction"), "status": "OBSERVED" if payload.get("assigned_seq") is not None else "UNKNOWN"}, "stages": {"holder_capture": [ref]},
                    "identity_scope": "Public capture occurrence; token is not a global identity."}
            holders.append(held)
            active_holders[payload.get("token")] = held
        elif action == "holding_read_commit":
            held = active_holders.get(payload.get("token"))
            last_read = (held, payload.get("assigned_seq"), payload.get("direction"), ref)
            if held is not None:
                held["assigned_seq"] = payload.get("assigned_seq")
                held["record_key"] = {"assigned_seq": payload.get("assigned_seq"), "direction": payload.get("direction"), "status": "OBSERVED" if payload.get("assigned_seq") is not None else "UNKNOWN"}
                held["stages"].setdefault("read", []).append(ref)
                connect(held["id"], ref, "paid_read_of_same_live_holder_record")
            else:
                unknowns.append({"stage_ref": ref, "relation": "holder_capture_origin", "status": "UNKNOWN"})
        elif action == "capture":
            pending = {"ref": ref, "direction": row.get("direction"), "held": None, "read_ref": None}
            if row.get("source") == "paid_holder_read" and last_read and last_read[2] == row.get("direction"):
                pending.update(held=last_read[0], read_ref=last_read[3], assigned_seq=last_read[1])
        elif action == "save_commit":
            key = (payload.get("seq"), payload.get("direction"))
            saved = {"id": ref, "seq": key[0], "direction": key[1], "durable": row.get("durable"),
                     "record_key": {"assigned_seq": key[0], "direction": key[1], "status": "OBSERVED" if key[0] is not None else "UNKNOWN"},
                     "observed_mcu_resets_at_save": mcu_resets, "stages": {"save": [ref]},
                     "identity_scope": "Public SAVE occurrence; numeric seq may be reused after reset."}
            if pending and pending["direction"] == key[1]:
                saved["stages"]["capture"] = [pending["ref"]]
                connect(pending["ref"], ref, "capture_to_save")
                held = pending["held"]
                if held is not None and pending.get("assigned_seq") == key[0]:
                    saved["holder_capture_ref"] = held["id"]
                    saved["stages"]["holder_capture"] = [held["id"]]
                    saved["stages"]["read"] = [pending["read_ref"]]
                    held["stages"].setdefault("save", []).append(ref)
                    connect(pending["read_ref"], ref, "read_to_save")
            else:
                unknowns.append({"stage_ref": ref, "relation": "capture_origin", "status": "UNKNOWN"})
            records.append(saved)
            latest_saved[key] = saved
            pending = None
        elif action in ("wire_complete", "ack_commit"):
            attach_saved(stages[action], row, ref)
        elif action in ("holding_clear_commit", "holding_expired", "holding_overflow_overwrite"):
            held = active_holders.pop(payload.get("token"), None)
            if held is not None:
                held["stages"].setdefault(stages[action], []).append(ref)
                connect(held["id"], ref, stages[action])
    # Receiver facts are already public; no hidden event match is imported.
    receiver = facts.get("receiver_records")
    if isinstance(receiver, list):
        for index, row in enumerate(receiver):
            if not isinstance(row, dict):
                continue
            ref = "#/facts/receiver_records/"+str(index)
            event("recv", row, ref)
            # Match the preceding SAVE by public time to avoid joining an old
            # receive to a later reused numeric sequence.
            candidates = [r for r in records if r["seq"] == row.get("seq") and r["direction"] == row.get("direction")
                          and activity[int(r["id"].rsplit("/", 1)[1])].get("time_s", float("inf")) <= row.get("time_s", -1)]
            if candidates:
                saved = candidates[-1]
                saved["stages"].setdefault("recv", []).append(ref)
                connect(saved["id"], ref, "gateway_accepted_independent_of_ack")
            else:
                unknowns.append({"stage_ref": ref, "relation": "preceding_save", "status": "UNKNOWN"})
    else:
        unknowns.append({"relation": "receiver_acceptance", "status": "UNKNOWN", "reason": "Missing public receiver_records."})
    if "activity" not in facts:
        unknowns.append({"relation": "record_stages", "status": "UNKNOWN", "reason": "Missing public activity; no inferred losses."})
    for saved in records:
        held = next((h for h in holders if h["id"] == saved.get("holder_capture_ref")), None)
        if held is not None:
            for stage in ("clear", "expire", "holder_reset"):
                if stage in held["stages"]:
                    saved["stages"][stage] = list(held["stages"][stage])
    return {"schema": PUBLIC_RELATION_VERSION, "result_ref": result_ref,
            "scope": {"public_input_only": True, "no_hidden_truth": True,
                      "no_observer_identity": True, "absence_is_not_loss": True,
                      "device_seq_is_not_globally_unique": True,
                      "execution_status": public.get("execution_status") if isinstance(public, dict) else None},
            "events": events, "records": records, "holder_records": holders,
            "relations": links, "unknowns": unknowns}
