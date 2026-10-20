"""External necessary-bound check, independent of the public tool's formula.

This is a model-bound mathematical no-go, not measured hardware qualification.
It uses an intentionally weaker dark-duration lower bound and omits all event,
sample, write, boot and transmission energy. No candidate or model is called.
"""
from decimal import Decimal, localcontext
from pathlib import Path
import argparse
import hashlib
import json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    p = json.loads(args.protocol.read_text())
    app = Path(p["ar_tool_script"]).parents[1]
    contract_path = app / "configs/studies/phase1-20261020/ar/service-contract.v1.json"
    world_path = app / "packages/python/bfworld/src/bfworld/agentlab/campaign20261019/ar_service.py"
    for path in [contract_path, world_path]:
        if sha(path) != p["bound_files"][str(path)]:
            raise ValueError("FROZEN_INPUT_DRIFT")
    c = json.loads(contract_path.read_text())
    if c["world_id"] != "ar-service-program-v2":
        raise ValueError("UNREVIEWED_WORLD")
    cold, history = c["tasks"]["ar-cold"], c["tasks"]["ar-history-nvm"]
    d = cold["device"]
    D = lambda value: Decimal(str(value))
    with localcontext() as context:
        context.prec = 40
        off_min = D(c["legal_design_space"]["device"]["off_v"]["minimum"])
        max_v = D(d["cap_voltage_max_v"])
        if any(history["device"][key] != d[key] for key in ["sleep_power_w", "esr_ohm", "tx_peak_output_a", "output_v", "dropout_v"]):
            raise ValueError("CROSS_CASE_PHYSICS_MISMATCH")
        loaded_min = off_min - D(d["esr_ohm"]) * D(d["tx_peak_output_a"])
        if loaded_min < D(d["output_v"]) + D(d["dropout_v"]):
            raise ValueError("DROPOUT_RESTART_PROOF_NOT_APPLICABLE")
        deadline = D(cold["required_first_receive_s"])
        available = sum(max(D(0), min(deadline, D(segment["end_s"])) - D(segment["start_s"]))
            * max(D(0), D(segment["power_w"]) * D(d["harvest_efficiency"]) - D(d["off_power_w"]))
            for segment in cold["source_segments"] if D(segment["start_s"]) < deadline)
        cold_cap_max = 2 * available / off_min ** 2
        usable_per_f = (max_v ** 2 - off_min ** 2) / 2
        dark = max(D(segment["end_s"]) - D(segment["start_s"])
            for segment in history["source_segments"] if D(segment["power_w"]) == 0)
        # Permit a whole sampling interval at EACH edge plus two time steps.
        # This weakens the public tool's bound and avoids assuming edge samples.
        edge_slack = 2 * D(history["required_sample_period_s"]) + 2 * D(history["dt_s"])
        powered_lower_s = max(D(0), dark - edge_slack)
        sleep = D(d["sleep_power_w"])
        dark_cap_min = sleep * powered_lower_s / usable_per_f
        no_go = dark_cap_min > cold_cap_max
        net_cold = available / deadline
        optimistic = {
            "minimum_cold_deadline_s_for_dark_lower_bound": dark_cap_min * off_min ** 2 / (2 * net_cold),
            "maximum_dark_duration_s_for_cold_upper_bound": edge_slack + cold_cap_max * usable_per_f / sleep,
            "maximum_sleep_power_w_at_cold_upper_bound": cold_cap_max * usable_per_f / powered_lower_s,
        }
        numeric = {"cold_optimistic_available_j": available, "cold_capacitance_upper_bound_f": cold_cap_max,
            "dark_duration_s": dark, "edge_slack_s": edge_slack, "powered_duration_lower_bound_s": powered_lower_s,
            "sleep_only_energy_lower_bound_j": sleep * powered_lower_s,
            "usable_energy_per_f": usable_per_f, "dark_capacitance_lower_bound_f": dark_cap_min,
            "loaded_voltage_at_legal_off_min_v": loaded_min}
    receipt = {"schema_version": "bf-phase1-external-necessary-bound-v1",
        "status": "FIXED_SPACE_NO_GO" if no_go else "NOT_PROVEN", "protocol_sha256": sha(args.protocol),
        "contract_sha256": sha(contract_path), "world_sha256": sha(world_path), "checker_sha256": sha(Path(__file__)),
        "numeric_decimal": {key: str(value) for key, value in numeric.items()},
        "proof": ["Any cold receive requires charging above the legal ready voltage, which exceeds off_min. Omit boot, sampling and TX costs and grant every available source joule.",
            "At voltages above legal off_min the fixed ESR cannot trigger TX dropout. The executable grammar cannot request a power-off state.",
            "A background-threshold brownout leaves energy below off threshold; zero dark input cannot recharge to the strictly higher ready threshold. Sampling throughout the dark service therefore needs continuous power between its first and last required samples.",
            "Grant full charge at dark entry and a full sampling interval plus dt slack at both edges; charge only the fixed sleep power and ignore every other debit. The required capacitance still exceeds the cold upper bound."],
        "optimistic_human_tradeoff_limits_decimal": {key: str(value) for key, value in optimistic.items()},
        "tradeoff_scope": "Necessary optimistic limits only, not sufficient designs. Any relaxed service or changed physical power needs a new human-approved task and new qualification.",
        "physical_qualification": "UNKNOWN", "agent_method_benefit": "NOT_TESTED", "rsi": "NOT_TESTED",
        "new_simulations": 0, "paid_requests": 0, "native_dispatches": 0}
    with args.receipt.open("x") as output:
        json.dump(receipt, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"status": receipt["status"], "numeric": receipt["numeric_decimal"],
        "optimistic_tradeoffs": receipt["optimistic_human_tradeoff_limits_decimal"]}))


if __name__ == "__main__":
    main()
