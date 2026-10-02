"""Deterministic semantic golden episodes for the coupled-world successor.

These fixtures freeze meanings and truth tables, not the future v2 wire schema.
They deliberately keep RealityWorld separate from the Agent-editable
CandidateWorldModel.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from bfworld.kernel.canonical import canonical_hash, file_hash, write_canonical_json


class GoldenSemanticError(RuntimeError):
    """A golden episode violates its frozen semantic rules."""


EVENT_PRIORITY = {
    "continuous_integrated": 10,
    "pmic_transition": 20,
    "mcu_transition": 30,
    "application_event": 40,
    "mission_evaluated": 50,
}

A001_BUNDLE_HASH = "sha256:6fa761099b10c9b10060a3636380e5d83221cd95272ee6ac9efa96955ad97059"
FIXED_TIME = "2026-09-04T00:00:00Z"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GoldenSemanticError(message)


def _identified(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["content_hash"] = canonical_hash(result)
    return result


def _mission_contract() -> dict[str, Any]:
    return _identified(
        {
            "object_type": "MissionContract",
            "schema_version": "bfworld-semantic-mission-v0",
            "mission_id": "golden-coupled-mission-v0",
            "mutable_by_agent": False,
            "requirements": {
                "correct_diagnosis_required": True,
                "minimum_confidence": 0.7,
                "receiver_ack_required": True,
                "deadline_s": 1.2,
                "minimum_voltage_v": 1.8,
                "maximum_voltage_v": 3.6,
                "allowed_pmic_terminal_states": ["regulated", "protection"],
            },
            "resource_limits": {
                "flash_bytes": 65536,
                "sram_bytes": 16384,
                "operations_per_inference": 50000,
            },
            "required_evidence_claims": ["public-prediction-supported"],
        }
    )


def _reality_world(case: dict[str, Any]) -> dict[str, Any]:
    return _identified(
        {
            "object_type": "RealityWorld",
            "schema_version": "bfworld-semantic-reality-v0",
            "world_id": f"reality-{case['slug']}-v0",
            "mutable_by_agent": False,
            "sealed": True,
            "visibility": "fixture-authority",
            "mechanisms": case["reality_mechanisms"],
        }
    )


def _candidate_world(case: dict[str, Any]) -> dict[str, Any]:
    return _identified(
        {
            "object_type": "CandidateWorldModel",
            "schema_version": "bfworld-semantic-candidate-world-v0",
            "model_id": f"candidate-{case['slug']}-v0",
            "mutable_by_agent": True,
            "assumptions": case["candidate_assumptions"],
            "prediction_scope": case["prediction_scope"],
        }
    )


def _design(case: dict[str, Any]) -> dict[str, Any]:
    return _identified(
        {
            "object_type": "DesignArtifact",
            "schema_version": "bfworld-semantic-design-v0",
            "design_id": f"design-{case['slug']}-v0",
            "components": {
                "harvester": "rotary-charge-source-v0",
                "circuit": case["circuit"],
                "model": "tinyml-bearing-v0",
                "schedule": case["schedule"],
            },
            "resources": {
                "flash_bytes": 12000,
                "sram_bytes": 6000,
                "operations_per_inference": 34000,
            },
        }
    )


def _state(
    *,
    time_s: float,
    voltage_v: float,
    pmic: str,
    mcu: str,
    predicted_label: str | None,
    radio: str,
    mission: str,
) -> dict[str, Any]:
    return {
        "time_s": time_s,
        "omega_rpm": 120.0,
        "shaft_angle_rad": round(time_s * 4.0 * 3.141592653589793, 9),
        "harvester_charge_c": round(time_s * 0.0015, 9),
        "input_voltage_v": round(voltage_v + 0.15, 6),
        "pmic_state": pmic,
        "storage_voltage_v": voltage_v,
        "mcu_state": mcu,
        "sensor_buffer_samples": 1024 if time_s >= 0.8 else 0,
        "predicted_label": predicted_label,
        "radio_state": radio,
        "mission_state": mission,
    }


def _events(case: dict[str, Any]) -> list[dict[str, Any]]:
    terminal = case["terminal"]
    snapshots = [
        (
            0.0,
            "continuous_integrated",
            _state(
                time_s=0.0,
                voltage_v=2.4,
                pmic="off",
                mcu="off",
                predicted_label=None,
                radio="idle",
                mission="pending",
            ),
        ),
        (
            0.0,
            "pmic_transition",
            _state(
                time_s=0.0,
                voltage_v=2.4,
                pmic="regulated",
                mcu="off",
                predicted_label=None,
                radio="idle",
                mission="pending",
            ),
        ),
        (
            0.0,
            "mcu_transition",
            _state(
                time_s=0.0,
                voltage_v=2.4,
                pmic="regulated",
                mcu="sense",
                predicted_label=None,
                radio="idle",
                mission="pending",
            ),
        ),
        (
            0.0,
            "application_event",
            _state(
                time_s=0.0,
                voltage_v=2.4,
                pmic="regulated",
                mcu="sense",
                predicted_label=None,
                radio="idle",
                mission="request-open",
            ),
        ),
        (
            1.0,
            "continuous_integrated",
            _state(
                time_s=1.0,
                voltage_v=terminal["voltage_v"],
                pmic="regulated",
                mcu="infer",
                predicted_label=terminal["predicted_label"],
                radio="idle",
                mission="request-open",
            ),
        ),
        (
            1.0,
            "pmic_transition",
            _state(
                time_s=1.0,
                voltage_v=terminal["voltage_v"],
                pmic=terminal["pmic_state"],
                mcu="infer",
                predicted_label=terminal["predicted_label"],
                radio="idle",
                mission="request-open",
            ),
        ),
        (
            1.0,
            "mcu_transition",
            _state(
                time_s=1.0,
                voltage_v=terminal["voltage_v"],
                pmic=terminal["pmic_state"],
                mcu=terminal["mcu_state"],
                predicted_label=terminal["predicted_label"],
                radio=terminal["radio_state"],
                mission="request-open",
            ),
        ),
        (
            1.0,
            "application_event",
            _state(
                time_s=1.0,
                voltage_v=terminal["voltage_v"],
                pmic=terminal["pmic_state"],
                mcu=terminal["mcu_state"],
                predicted_label=terminal["predicted_label"],
                radio=terminal["radio_state"],
                mission="delivered" if terminal["ack_time_s"] is not None else "missed",
            ),
        ),
        (
            1.0,
            "mission_evaluated",
            _state(
                time_s=1.0,
                voltage_v=terminal["voltage_v"],
                pmic=terminal["pmic_state"],
                mcu=terminal["mcu_state"],
                predicted_label=terminal["predicted_label"],
                radio=terminal["radio_state"],
                mission=terminal["mission_state"],
            ),
        ),
    ]
    return [
        {
            "time_s": time_s,
            "priority": EVENT_PRIORITY[event_type],
            "event_type": event_type,
            "state": state,
        }
        for time_s, event_type, state in snapshots
    ]


def _mission_outcomes(
    mission: dict[str, Any],
    design: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any]:
    terminal = case["terminal"]
    requirements = mission["requirements"]
    request = case["request"]
    quality_valid = bool(
        request["predicted_label"] == request["fault_label"]
        and request["confidence"] >= requirements["minimum_confidence"]
    )
    delivered = request["ack_time_s"] is not None
    deadline_met = bool(delivered and request["ack_time_s"] <= request["deadline_s"])
    electrical_safe = bool(
        terminal["minimum_voltage_v"] >= requirements["minimum_voltage_v"]
        and terminal["maximum_voltage_v"] <= requirements["maximum_voltage_v"]
        and terminal["pmic_state"] in requirements["allowed_pmic_terminal_states"]
    )
    limits = mission["resource_limits"]
    resources = design["resources"]
    deployment_feasible = all(resources[key] <= limits[key] for key in limits)
    pmp = all((quality_valid, delivered, deadline_met, electrical_safe, deployment_feasible))
    ea = True
    submitted = True
    public_admission = bool(submitted and case["predicted"]["physical_mission_pass"] and ea)
    vms = bool(submitted and pmp and ea)
    return {
        "physical_mission_pass": {
            "quality_valid": quality_valid,
            "delivered": delivered,
            "deadline_met": deadline_met,
            "electrical_safe": electrical_safe,
            "deployment_feasible": deployment_feasible,
            "value": pmp,
        },
        "evidence_admissibility": {
            "identity_current": True,
            "scope_covered": True,
            "closure_complete": True,
            "independence_satisfied": True,
            "value": ea,
        },
        "submission": {
            "submitted": submitted,
            "terminal_reason": "submitted",
            "public_admission": public_admission,
        },
        "verified_mission_success": vms,
        "false_admission": bool(submitted and public_admission and not pmp),
        "valid_design_not_submitted": bool(pmp and ea and not submitted),
        "abstention": False,
        "no_submission_timeout": False,
    }


def _receipt(
    mission: dict[str, Any],
    candidate: dict[str, Any],
    design: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any]:
    return _identified(
        {
            "object_type": "EvidenceReceipt",
            "schema_version": "bfworld-semantic-receipt-v0",
            "subject_artifact_hash": design["content_hash"],
            "claim_id": "public-prediction-supported",
            "verifier_id": "golden-public-prediction-verifier-v0",
            "verifier_version": "0.1.0",
            # Public prediction evidence binds the participant-visible model,
            # never the sealed RealityWorld used for qualification truth.
            "provider_hash": candidate["content_hash"],
            "scenario_scope": {
                "episode_id": case["episode_id"],
                "rpm": 120.0,
                "fault_label": case["request"]["fault_label"],
                "model_id": design["components"]["model"],
                "circuit": design["components"]["circuit"],
            },
            "device_session_scope": "golden-fixture-device/session-0",
            "fidelity": "F0-deterministic-semantic",
            "assumption_set": case["candidate_assumptions"],
            "independence_group": "golden-public-prediction-group-v0",
            "observed_result": case["predicted"],
            "uncertainty": {"kind": "deterministic-fixture", "value": 0.0},
            "created_at": FIXED_TIME,
        }
    )


def _visual_bindings(episode_id: str) -> list[dict[str, Any]]:
    return [
        {
            "visual_property": "shaft.rotation_z",
            "source_channel": "environment.shaft_angle_rad",
            "transform": "identity",
            "unit": "rad",
            "source_kind": "observed",
            "fidelity": "F0-deterministic-semantic",
            "episode_id": episode_id,
        },
        {
            "visual_property": "capacitor.fill",
            "source_channel": "storage.storage_voltage_v",
            "transform": "clamp((v-1.8)/(3.6-1.8),0,1)",
            "unit": "V",
            "source_kind": "observed",
            "fidelity": "F0-deterministic-semantic",
            "episode_id": episode_id,
        },
        {
            "visual_property": "mcu.state",
            "source_channel": "mcu.mcu_state",
            "transform": "categorical",
            "unit": "state",
            "source_kind": "observed",
            "fidelity": "F0-deterministic-semantic",
            "episode_id": episode_id,
        },
        {
            "visual_property": "receiver.status",
            "source_channel": "radio.receiver_ack",
            "transform": "ack_time_to_status",
            "unit": "state",
            "source_kind": "observed",
            "fidelity": "F0-deterministic-semantic",
            "episode_id": episode_id,
        },
        {
            "visual_property": "mission_strip.pmp",
            "source_channel": "mission_outcomes.physical_mission_pass.value",
            "transform": "identity",
            "unit": "boolean",
            "source_kind": "qualified",
            "fidelity": "F0-deterministic-semantic",
            "episode_id": episode_id,
        },
        {
            "visual_property": "mission_strip.ea",
            "source_channel": "mission_outcomes.evidence_admissibility.value",
            "transform": "identity",
            "unit": "boolean",
            "source_kind": "qualified",
            "fidelity": "F0-deterministic-semantic",
            "episode_id": episode_id,
        },
        {
            "visual_property": "mission_strip.vms",
            "source_channel": "mission_outcomes.verified_mission_success",
            "transform": "identity",
            "unit": "boolean",
            "source_kind": "qualified",
            "fidelity": "F0-deterministic-semantic",
            "episode_id": episode_id,
        },
        {
            "visual_property": "study_atlas.status",
            "source_channel": "mission_outcomes.verified_mission_success",
            "transform": "true=PASS,false=FAIL",
            "unit": "state",
            "source_kind": "qualified",
            "fidelity": "F0-deterministic-semantic",
            "episode_id": episode_id,
        },
    ]


CASES: tuple[dict[str, Any], ...] = (
    {
        "episode_id": "G0-PASS",
        "slug": "g0-pass",
        "reality_mechanisms": ["load-dependent-harvesting", "safe-storage", "correct-information-ring"],
        "candidate_assumptions": ["dynamic-voltage-state", "correct-diagnosis-required"],
        "prediction_scope": ["energy", "voltage", "quality", "delivery"],
        "circuit": "rectifier-pmic-clamped-v0",
        "schedule": "state-aware-v0",
        "predicted": {"physical_mission_pass": True, "proxy_delivery_pass": True},
        "terminal": {
            "voltage_v": 2.6,
            "minimum_voltage_v": 2.2,
            "maximum_voltage_v": 3.2,
            "pmic_state": "regulated",
            "mcu_state": "tx",
            "predicted_label": "bearing-fault",
            "radio_state": "acked",
            "ack_time_s": 1.05,
            "mission_state": "success",
        },
        "request": {
            "request_id": "request-0",
            "window_start_s": 0.1,
            "window_end_s": 0.8,
            "rpm": 120.0,
            "fault_label": "bearing-fault",
            "model_id": "tinyml-bearing-v0",
            "predicted_label": "bearing-fault",
            "score": 0.91,
            "confidence": 0.91,
            "correct": True,
            "preprocessing_id": "bearing-window-int8-v0",
            "model_format": "int8-fixture",
            "tx_time_s": 1.0,
            "ack_time_s": 1.05,
            "deadline_s": 1.2,
        },
        "violation": None,
    },
    {
        "episode_id": "G1-OVERVOLTAGE",
        "slug": "g1-overvoltage",
        "reality_mechanisms": ["load-dependent-harvesting", "unclamped-storage", "correct-information-ring"],
        "candidate_assumptions": ["average-energy-closure", "voltage-envelope-omitted"],
        "prediction_scope": ["energy", "quality", "delivery"],
        "circuit": "rectifier-pmic-unclamped-v0",
        "schedule": "fixed-v0",
        "predicted": {"physical_mission_pass": True, "proxy_delivery_pass": True},
        "terminal": {
            "voltage_v": 3.8,
            "minimum_voltage_v": 2.2,
            "maximum_voltage_v": 3.8,
            "pmic_state": "protection",
            "mcu_state": "tx",
            "predicted_label": "bearing-fault",
            "radio_state": "acked",
            "ack_time_s": 1.05,
            "mission_state": "failed-electrical-safety",
        },
        "request": {
            "request_id": "request-0",
            "window_start_s": 0.1,
            "window_end_s": 0.8,
            "rpm": 120.0,
            "fault_label": "bearing-fault",
            "model_id": "tinyml-bearing-v0",
            "predicted_label": "bearing-fault",
            "score": 0.91,
            "confidence": 0.91,
            "correct": True,
            "preprocessing_id": "bearing-window-int8-v0",
            "model_format": "int8-fixture",
            "tx_time_s": 1.0,
            "ack_time_s": 1.05,
            "deadline_s": 1.2,
        },
        "violation": {
            "kind": "overvoltage",
            "time_s": 1.0,
            "observed": "storage_voltage_v=3.8 exceeds maximum_voltage_v=3.6",
            "dependency_path": ["harvester", "rectifier_pmic", "storage"],
            "candidate_explanations": ["excess transferred charge", "missing or insufficient clamp"],
            "confirmed_causal_factor": None,
        },
    },
    {
        "episode_id": "G2-BROWNOUT",
        "slug": "g2-brownout",
        "reality_mechanisms": ["same-total-energy-as-g0", "phase-shifted-harvest", "tx-current-burst"],
        "candidate_assumptions": ["average-energy-closure", "dynamic-state-omitted"],
        "prediction_scope": ["integrated-energy", "quality", "delivery"],
        "circuit": "rectifier-pmic-clamped-v0",
        "schedule": "fixed-tx-burst-v0",
        "predicted": {"physical_mission_pass": True, "proxy_delivery_pass": True},
        "terminal": {
            "voltage_v": 1.7,
            "minimum_voltage_v": 1.7,
            "maximum_voltage_v": 3.2,
            "pmic_state": "off",
            "mcu_state": "brownout",
            "predicted_label": "bearing-fault",
            "radio_state": "tx-aborted",
            "ack_time_s": None,
            "mission_state": "failed-brownout",
        },
        "request": {
            "request_id": "request-0",
            "window_start_s": 0.1,
            "window_end_s": 0.8,
            "rpm": 120.0,
            "fault_label": "bearing-fault",
            "model_id": "tinyml-bearing-v0",
            "predicted_label": "bearing-fault",
            "score": 0.91,
            "confidence": 0.91,
            "correct": True,
            "preprocessing_id": "bearing-window-int8-v0",
            "model_format": "int8-fixture",
            "tx_time_s": 1.0,
            "ack_time_s": None,
            "deadline_s": 1.2,
        },
        "violation": {
            "kind": "brownout",
            "time_s": 1.0,
            "observed": "storage_voltage_v=1.7 falls below minimum_voltage_v=1.8 during TX",
            "dependency_path": ["harvester", "storage", "mcu", "radio"],
            "candidate_explanations": ["harvest/load phase mismatch", "TX burst scheduled before recharge"],
            "confirmed_causal_factor": None,
        },
    },
    {
        "episode_id": "G3-WRONG-DIAGNOSIS",
        "slug": "g3-wrong-diagnosis",
        "reality_mechanisms": ["load-dependent-harvesting", "safe-storage", "fault-conditioned-information-ring"],
        "candidate_assumptions": ["delivery-proxy-is-sufficient", "quality-objective-omitted"],
        "prediction_scope": ["energy", "voltage", "delivery-proxy"],
        "circuit": "rectifier-pmic-clamped-v0",
        "schedule": "state-aware-v0",
        "predicted": {"physical_mission_pass": True, "proxy_delivery_pass": True},
        "terminal": {
            "voltage_v": 2.6,
            "minimum_voltage_v": 2.2,
            "maximum_voltage_v": 3.2,
            "pmic_state": "regulated",
            "mcu_state": "tx",
            "predicted_label": "normal",
            "radio_state": "acked",
            "ack_time_s": 1.05,
            "mission_state": "failed-quality",
        },
        "request": {
            "request_id": "request-0",
            "window_start_s": 0.1,
            "window_end_s": 0.8,
            "rpm": 120.0,
            "fault_label": "bearing-fault",
            "model_id": "tinyml-bearing-v0",
            "predicted_label": "normal",
            "score": 0.86,
            "confidence": 0.86,
            "correct": False,
            "preprocessing_id": "bearing-window-int8-v0",
            "model_format": "int8-fixture",
            "tx_time_s": 1.0,
            "ack_time_s": 1.05,
            "deadline_s": 1.2,
        },
        "violation": {
            "kind": "wrong-diagnosis",
            "time_s": 1.0,
            "observed": "receiver ACK arrived before deadline but predicted_label != fault_label",
            "dependency_path": ["sensor", "tinyml", "radio", "receiver", "mission"],
            "candidate_explanations": ["delivery-only proxy omitted diagnostic correctness"],
            "confirmed_causal_factor": None,
        },
    },
)


def _energy_ledger(case: dict[str, Any]) -> dict[str, Any]:
    # G0, G2, and G3 intentionally have the same integrated energy. G2 differs
    # only in temporal alignment and therefore falsifies average-energy closure.
    if case["episode_id"] == "G1-OVERVOLTAGE":
        components = {
            "storage_delta_mj": 0.5,
            "sense_mj": 0.7,
            "inference_mj": 2.0,
            "radio_mj": 1.8,
            "rectifier_loss_mj": 1.0,
            "pmic_loss_mj": 0.8,
            "leakage_mj": 0.3,
            "protection_dump_mj": 6.85,
        }
        harvester_mj = 14.0
    else:
        components = {
            "storage_delta_mj": 5.35,
            "sense_mj": 0.7,
            "inference_mj": 2.0,
            "radio_mj": 1.8,
            "rectifier_loss_mj": 1.0,
            "pmic_loss_mj": 0.8,
            "leakage_mj": 0.3,
            "protection_dump_mj": 0.0,
        }
        harvester_mj = 12.0
    residual_mj = round(harvester_mj - sum(components.values()), 9)
    return {
        "unit": "mJ",
        "harvester_output_mj": harvester_mj,
        **components,
        "residual_mj": residual_mj,
        "normalized_residual": round(abs(residual_mj) / harvester_mj, 12),
        "maximum_normalized_residual": 0.01,
    }


def build_golden_episodes() -> list[dict[str, Any]]:
    episodes = []
    for case in CASES:
        mission = _mission_contract()
        reality = _reality_world(case)
        candidate = _candidate_world(case)
        design = _design(case)
        outcomes = _mission_outcomes(mission, design, case)
        receipt = _receipt(mission, candidate, design, case)
        episode = {
            "schema_version": "bfworld-semantic-golden-episode-v0",
            "episode_id": case["episode_id"],
            "purpose": "semantic-fixture-not-formal-experiment",
            "authorities": {
                "mission_contract": mission,
                "reality_world": reality,
                "candidate_world_model": candidate,
                "design_artifact": design,
                "observation_broker": _identified(
                    {
                        "object_type": "ObservationBroker",
                        "schema_version": "bfworld-semantic-observation-broker-v0",
                        "only_reality_access": True,
                        "participant_hidden_access": False,
                        "public_observations": [
                            "terminal-voltage-trace",
                            "receiver-ack-trace",
                            "request-trace",
                        ],
                    }
                ),
            },
            "run_kinds": {
                "prediction_run": "CandidateWorldModel + DesignArtifact -> predicted_trace",
                "experiment_run": "RealityWorld + intervention -> observed_trace",
                "qualification_run": "sealed RealityWorld + submission -> qualification truth",
            },
            "event_ordering": [
                {"event_type": event_type, "priority": priority}
                for event_type, priority in EVENT_PRIORITY.items()
            ],
            "state_transition_table": _events(case),
            "prediction_vs_observation": {
                "predicted": case["predicted"],
                "observed": {
                    "physical_mission_pass": outcomes["physical_mission_pass"]["value"],
                    "minimum_voltage_v": case["terminal"]["minimum_voltage_v"],
                    "maximum_voltage_v": case["terminal"]["maximum_voltage_v"],
                    "receiver_ack": case["terminal"]["ack_time_s"] is not None,
                    "diagnosis_correct": outcomes["physical_mission_pass"]["quality_valid"],
                },
            },
            "request_trace": [case["request"]],
            "energy_ledger": _energy_ledger(case),
            "public_evidence_receipts": [receipt],
            "expected_evidence_state": "CURRENT",
            "mission_outcomes": outcomes,
            "failure_lens": {
                "observed_violation": case["violation"]["observed"] if case["violation"] else None,
                "structural_dependency_path": case["violation"]["dependency_path"] if case["violation"] else [],
                "candidate_explanations": case["violation"]["candidate_explanations"] if case["violation"] else [],
                "confirmed_causal_factor": case["violation"]["confirmed_causal_factor"] if case["violation"] else None,
                "confirmation_rule": "requires paired intervention or counterfactual evidence",
            },
            "expected_ui_projection": {
                "study_atlas_status": "PASS" if outcomes["verified_mission_success"] else "FAIL",
                "mission_strip": {
                    "pmp": outcomes["physical_mission_pass"]["value"],
                    "ea": outcomes["evidence_admissibility"]["value"],
                    "vms": outcomes["verified_mission_success"],
                    "fidelity": "F0-deterministic-semantic",
                },
                "visual_bindings": _visual_bindings(case["episode_id"]),
            },
        }
        episode["content_hash"] = canonical_hash(episode)
        validate_episode(episode)
        episodes.append(episode)
    return episodes


def _validate_identified(value: dict[str, Any], label: str) -> None:
    unsigned = dict(value)
    claimed = unsigned.pop("content_hash", None)
    _require(isinstance(claimed, str), f"{label} missing content hash")
    _require(canonical_hash(unsigned) == claimed, f"{label} content hash mismatch")


def validate_episode(episode: dict[str, Any]) -> dict[str, Any]:
    unsigned_episode = dict(episode)
    claimed_episode_hash = unsigned_episode.pop("content_hash", None)
    _require(canonical_hash(unsigned_episode) == claimed_episode_hash, "episode content hash mismatch")

    authorities = episode["authorities"]
    for key in (
        "mission_contract",
        "reality_world",
        "candidate_world_model",
        "design_artifact",
        "observation_broker",
    ):
        _validate_identified(authorities[key], key)
    _require(authorities["mission_contract"]["mutable_by_agent"] is False, "MissionContract is mutable")
    _require(authorities["reality_world"]["mutable_by_agent"] is False, "RealityWorld is mutable")
    _require(authorities["reality_world"]["sealed"] is True, "RealityWorld is not sealed")
    _require(authorities["candidate_world_model"]["mutable_by_agent"] is True, "CandidateWorldModel is not editable")
    _require(authorities["observation_broker"]["only_reality_access"] is True, "ObservationBroker authority broken")
    _require(authorities["observation_broker"]["participant_hidden_access"] is False, "participant hidden access enabled")

    order = {item["event_type"]: item["priority"] for item in episode["event_ordering"]}
    _require(order == EVENT_PRIORITY, "event priority table changed")
    events = episode["state_transition_table"]
    _require(events == sorted(events, key=lambda item: (item["time_s"], item["priority"])), "same-time event order invalid")
    for event in events:
        _require(order[event["event_type"]] == event["priority"], "event priority mismatch")
        state = event["state"]
        required_state = {
            "omega_rpm",
            "shaft_angle_rad",
            "harvester_charge_c",
            "input_voltage_v",
            "pmic_state",
            "storage_voltage_v",
            "mcu_state",
            "sensor_buffer_samples",
            "predicted_label",
            "radio_state",
            "mission_state",
        }
        _require(required_state <= state.keys(), "state vector field missing")

    ledger = episode["energy_ledger"]
    allocated = sum(
        float(ledger[key])
        for key in (
            "storage_delta_mj",
            "sense_mj",
            "inference_mj",
            "radio_mj",
            "rectifier_loss_mj",
            "pmic_loss_mj",
            "leakage_mj",
            "protection_dump_mj",
        )
    )
    residual = round(float(ledger["harvester_output_mj"]) - allocated, 9)
    _require(residual == ledger["residual_mj"], "energy ledger residual mismatch")
    normalized = round(abs(residual) / float(ledger["harvester_output_mj"]), 12)
    _require(normalized == ledger["normalized_residual"], "normalized energy residual mismatch")
    _require(normalized < ledger["maximum_normalized_residual"], "energy residual exceeds fixture gate")

    mission = authorities["mission_contract"]
    design = authorities["design_artifact"]
    request = episode["request_trace"][0]
    observed = episode["prediction_vs_observation"]["observed"]
    requirements = mission["requirements"]
    required_request = {
        "request_id",
        "window_start_s",
        "window_end_s",
        "rpm",
        "fault_label",
        "model_id",
        "preprocessing_id",
        "model_format",
        "predicted_label",
        "score",
        "confidence",
        "correct",
        "tx_time_s",
        "ack_time_s",
        "deadline_s",
    }
    _require(required_request <= request.keys(), "request-level information trace incomplete")
    _require(request["score"] == request["confidence"], "request score/confidence binding mismatch")
    _require(
        request["correct"] == (request["predicted_label"] == request["fault_label"]),
        "request correctness mismatch",
    )
    quality_valid = request["predicted_label"] == request["fault_label"] and request["confidence"] >= requirements["minimum_confidence"]
    delivered = bool(observed["receiver_ack"])
    deadline_met = bool(delivered and request["ack_time_s"] <= request["deadline_s"])
    electrical_safe = bool(
        observed["minimum_voltage_v"] >= requirements["minimum_voltage_v"]
        and observed["maximum_voltage_v"] <= requirements["maximum_voltage_v"]
        and events[-1]["state"]["pmic_state"] in requirements["allowed_pmic_terminal_states"]
    )
    deployment_feasible = all(
        design["resources"][key] <= mission["resource_limits"][key]
        for key in mission["resource_limits"]
    )
    pmp = all((quality_valid, delivered, deadline_met, electrical_safe, deployment_feasible))
    claimed_pmp = episode["mission_outcomes"]["physical_mission_pass"]
    _require(
        claimed_pmp
        == {
            "quality_valid": quality_valid,
            "delivered": delivered,
            "deadline_met": deadline_met,
            "electrical_safe": electrical_safe,
            "deployment_feasible": deployment_feasible,
            "value": pmp,
        },
        "PMP truth table mismatch",
    )

    receipts = episode["public_evidence_receipts"]
    _require(bool(receipts), "evidence closure empty")
    for receipt in receipts:
        _validate_identified(receipt, "evidence receipt")
        _require(receipt["subject_artifact_hash"] == design["content_hash"], "evidence subject identity stale")
        _require(
            receipt["provider_hash"] == authorities["candidate_world_model"]["content_hash"],
            "public receipt is not bound to CandidateWorldModel",
        )
        _require(bool(receipt["scenario_scope"]), "evidence scope missing")
        _require(bool(receipt["independence_group"]), "evidence independence group missing")
    claims = {receipt["claim_id"] for receipt in receipts}
    closure = set(mission["required_evidence_claims"]) <= claims
    ea = episode["mission_outcomes"]["evidence_admissibility"]
    _require(closure and ea["closure_complete"], "evidence closure mismatch")
    _require(all(ea[key] for key in ("identity_current", "scope_covered", "closure_complete", "independence_satisfied")), "EA component failed")
    _require(ea["value"] is True and episode["expected_evidence_state"] == "CURRENT", "EA state mismatch")

    submission = episode["mission_outcomes"]["submission"]
    predicted_pass = episode["prediction_vs_observation"]["predicted"]["physical_mission_pass"]
    public_admission = bool(submission["submitted"] and predicted_pass and ea["value"])
    _require(submission["public_admission"] == public_admission, "public admission mismatch")
    vms = bool(submission["submitted"] and pmp and ea["value"])
    _require(episode["mission_outcomes"]["verified_mission_success"] == vms, "VMS mismatch")
    _require(
        episode["mission_outcomes"]["false_admission"]
        == bool(submission["submitted"] and public_admission and not pmp),
        "false admission mismatch",
    )

    lens = episode["failure_lens"]
    _require(lens["confirmed_causal_factor"] is None, "golden fixture claims unconfirmed causality")
    _require("paired intervention" in lens["confirmation_rule"], "causal confirmation rule missing")
    bindings = episode["expected_ui_projection"]["visual_bindings"]
    _require(bool(bindings), "visual bindings missing")
    required_binding = {"visual_property", "source_channel", "transform", "unit", "source_kind", "fidelity", "episode_id"}
    for binding in bindings:
        _require(required_binding <= binding.keys(), "visual binding provenance incomplete")
        _require(binding["episode_id"] == episode["episode_id"], "visual binding episode mismatch")

    return {
        "episode_id": episode["episode_id"],
        "content_hash": claimed_episode_hash,
        "pmp": pmp,
        "ea": ea["value"],
        "vms": vms,
        "false_admission": episode["mission_outcomes"]["false_admission"],
        "energy_residual": normalized,
    }


def validate_suite(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate cross-episode truths that cannot be checked in isolation."""

    expected_ids = [case["episode_id"] for case in CASES]
    _require([episode["episode_id"] for episode in episodes] == expected_ids, "golden episode set changed")
    reports = [validate_episode(episode) for episode in episodes]
    by_id = {episode["episode_id"]: episode for episode in episodes}
    report_by_id = {report["episode_id"]: report for report in reports}

    _require(report_by_id["G0-PASS"]["pmp"] is True, "G0 must physically pass")
    _require(report_by_id["G0-PASS"]["vms"] is True, "G0 must achieve VMS")
    for episode_id in ("G1-OVERVOLTAGE", "G2-BROWNOUT", "G3-WRONG-DIAGNOSIS"):
        _require(report_by_id[episode_id]["pmp"] is False, f"{episode_id} must physically fail")
        _require(report_by_id[episode_id]["vms"] is False, f"{episode_id} must fail VMS")
        _require(report_by_id[episode_id]["false_admission"] is True, f"{episode_id} must expose false admission")

    pass_ledger = by_id["G0-PASS"]["energy_ledger"]
    brownout_ledger = by_id["G2-BROWNOUT"]["energy_ledger"]
    _require(
        pass_ledger["harvester_output_mj"] == brownout_ledger["harvester_output_mj"],
        "G0/G2 must have equal integrated harvested energy",
    )
    for component in ("sense_mj", "inference_mj", "radio_mj"):
        _require(pass_ledger[component] == brownout_ledger[component], f"G0/G2 {component} changed")
    _require(
        by_id["G2-BROWNOUT"]["mission_outcomes"]["physical_mission_pass"]["electrical_safe"] is False,
        "G2 must fail through electrical dynamics",
    )

    wrong = by_id["G3-WRONG-DIAGNOSIS"]["mission_outcomes"]["physical_mission_pass"]
    _require(wrong["delivered"] and wrong["deadline_met"] and wrong["electrical_safe"], "G3 controls changed")
    _require(wrong["quality_valid"] is False, "G3 must fail only diagnostic quality")
    overvoltage = by_id["G1-OVERVOLTAGE"]["mission_outcomes"]["physical_mission_pass"]
    _require(overvoltage["quality_valid"] and overvoltage["delivered"], "G1 controls changed")
    _require(overvoltage["electrical_safe"] is False, "G1 must fail electrical safety")

    return {
        "schema_version": "bfworld-semantic-golden-validation-v0",
        "status": "passed",
        "a001_bundle_hash": A001_BUNDLE_HASH,
        "episodes": reports,
        "gates": {
            "authority_separation": True,
            "pmp_ea_vms_recomputable": True,
            "same_time_event_order": True,
            "energy_conservation": True,
            "same_energy_twin_diverges": True,
            "request_level_information_ring": True,
            "visual_provenance_complete": True,
            "unconfirmed_causality_not_promoted": True,
        },
    }


def write_golden_suite(output: Path) -> dict[str, Any]:
    """Materialize the deterministic suite and its content-addressed manifest."""

    episodes = build_golden_episodes()
    validation = validate_suite(episodes)
    files = []
    for episode in episodes:
        relative = Path(episode["episode_id"].lower()) / "episode.json"
        path = output / relative
        write_canonical_json(path, episode)
        files.append(
            {
                "episode_id": episode["episode_id"],
                "path": relative.as_posix(),
                "episode_hash": episode["content_hash"],
                "file_hash": file_hash(path),
            }
        )
    manifest = {
        "schema_version": "bfworld-semantic-golden-manifest-v0",
        "feature_id": "B0-000-semantic-golden-episodes",
        "purpose": "executable-semantics-not-formal-experiment",
        "created_at": FIXED_TIME,
        "a001_bundle_hash": A001_BUNDLE_HASH,
        "files": files,
        "validation": validation,
    }
    manifest["content_hash"] = canonical_hash(manifest)
    write_canonical_json(output / "manifest.json", manifest)
    return manifest
