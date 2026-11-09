"""Select two seen development conditions and two isolated tests before results."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil

A = Path(__file__).resolve().parent
ROOT = A.parents[4]
PLAN = A.parents[1]
CAN = ROOT / "workbench/bf-campaign-s0-20261019/battery-world"
PACKAGE = "BF-PQE-LC-SERVICE-LEARNING-20261024-001"


def read(p):
    return json.loads(Path(p).read_text())


def bind(p):
    p = Path(p)
    data = p.read_bytes()
    return {"path": str(p), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def main():
    free = shutil.disk_usage(ROOT).free
    assert free >= 11_000_000_000
    now = datetime.now(timezone.utc).isoformat()
    bold = PLAN / "bold-interventions"
    old = CAN / "studies/pqe20261022/e3lc"
    entries = [
        {"id": "development-bold-lc", "world": "LC-PV",
         "public": bind(bold / "a/host/lc-public.json"),
         "host_task": bind(bold / "a/host/lc-host-task.json"),
         "original_initial": str(bold / "s0/host/lc-initial"),
         "reason": "Required seen BOLD condition; sustained alternating light/shade, 12h darkness and interrupted recovery. Keep its full original service."},
        {"id": "development-e3lc", "world": "LC-PV",
         "public": bind(old / "shared/lcpv-task-public.json"),
         "host_task": bind(old / "lcpv-private/host-task.json"),
         "original_initial": str(old / "lcpv-private/initial"),
         "reason": "Existing qualified same-model 24h development condition selected before new outcomes; different optical/thermal/clock and recovery schedules, same strict service thresholds."},
    ]
    for entry in entries:
        pub = read(entry["public"]["path"])
        # The original learning flags are preserved as historical metadata.
        # Current work order explicitly authorizes these already-seen tasks.
        save(A / "public-tasks" / (entry["id"] + ".json"), {
            "schema": "lc-learning-public-development-task-v1", "package": PACKAGE,
            "training_allowed_in_current_package": True,
            "prior_phase_learning_flags_preserved": True, "public": pub,
            "original_public": entry["public"], "selection_reason": entry["reason"]})
        entry["training_public"] = bind(A / "public-tasks" / (entry["id"] + ".json"))
    save(A / "DEVELOPMENT-TASKS.json", {"at_utc": now, "package": PACKAGE,
         "selected_before_new_results": True, "entries": entries,
         "baseline": "Same original LC default flat Design in both conditions; not a winner selected from new outcomes."})

    rules = {"at_utc": now, "package": PACKAGE, "selection_before_new_results": True,
        "tests": {
            "DOOR": "Paused approaches: three opening/closing strokes separated by prescribed mid-angle no-motion dwell, short stable endpoint holds, three cold intervals. Always-available gateway isolates energy/record timing under interrupted motion. No subthreshold reversal pattern from BOLD is reused.",
            "LC": "New 25200..68400s darkness, alternating 20-minute irradiance and 45-minute uniform shadow blocks, gateway disconnect at12600 and uninterrupted recovery at68400; new thermal knots/lag/bias and oscillator error. Original full 24h service unchanged."},
        "initials": "DOOR uses the already public joint-source-supply BOLD design fixed now; LC uses original LC default. No private full solution/search or requirement that initial FAIL.",
        "privacy": "All new test definitions/results a/host only, A/S0 until formation/training/selection freeze. Never supply these to B or formation.",
        "replacement": False, "initial_full_cap_each": 1}
    save(A / "host/TASK-RULES.json", rules)
    door = deepcopy(read(bold / "a/host/door-task.json"))
    door.update(task_id="DOOR-LCLEARN-PAUSED-STROKE-20261024-v1",
                family_id="LCLEARN-ISOLATED-DOOR", exposure="Prospective private condition frozen before LC engineering and H training.",
                description="Every opening/closing in a 24h paused-stroke trajectory must be independently received within original2s; retain original force/energy/domain checks.")
    door["motion"] = []
    for start in (90.0, 410.0, 45100.0):
        t = start
        for lo, hi, duration, pause in ((0,42,.7,.45),(42,78,.7,.3),(78,90,.24,.2),
                                        (90,52,.75,.25),(52,12,.8,.35),(12,0,.24,0)):
            door["motion"].append({"start_s": t, "end_s": t+duration,
                                   "start_deg": lo, "end_deg": hi})
            t += duration + pause
    door["gateway_windows"] = [[0,86400]]
    design_source = bold / "a/engineering/03-joint-source-supply-t1/public-result.json"
    door["initial_design"] = deepcopy(read(design_source)["design"])
    door["material_sources"].pop("bold_lineage", None)
    door["material_sources"]["lclearn_rule"] = {"rules": rules["tests"]["DOOR"],
                                                "initial_design_source": bind(design_source)}
    save(A / "host/door-task.json", door)
    save(A / "host/door-public.json", {"task": door, "initial_design": door["initial_design"],
                                      "initial_problem": door["initial_problem"], "allowed_for_formation": False})

    lc = deepcopy(read(old / "lcpv-private/host-task.json"))
    public = deepcopy(read(old / "shared/lcpv-task-public.json"))
    instance = "LC-PV-LCLEARN-INTERMITTENT-20261024-v1"
    lc.update(instance_id=instance, allowed_for_learning=False,
              description="Strict temperature history under a new unstable-light/12h-darkness/disconnected-recovery schedule.")
    lc["service"].update(dark_interval_s=[25200,68400], recovery_at_s=68400,
                           recovery_old_history_deadline_s=68520,
                           history="All committed records retained; every pre-recovery unacknowledged record received by68520 in acquisition order without duplicate logical samples.",
                           new_sample_receive_scope="Samples acquired during available gateway windows; original10s acquisition-to-receive deadline.")
    lc["gateway_windows_s"] = [[0,12600],[68400,86400]]
    light, shade = [[25200,68400,0.0]], [[25200,68400,.8]]
    for start, end in ((0,25200),(68400,86400)):
        t, i = start, 0
        while t < end:
            light.append([t,min(t+1200,end),[.7,.32,.9,.4,.6][i%5]])
            t += 1200; i += 1
        t, i = start, 0
        while t < end:
            shade.append([t,min(t+2700,end),[.8,.35,1.0,.55][i%4]])
            t += 2700; i += 1
    lc["optical_environment"].update(irradiance_schedule_w_m2=sorted(light),
                                      uniform_shading_transmission=sorted(shade))
    lc["thermal_reference"].update(nominal_tau_s=28.0, nominal_bias_c=.1,
        air_truth_piecewise_linear_knots_s_c=[[0,5],[8400,5],[9300,8],[10500,8],[11400,5],
                                             [42000,5],[43200,8.5],[44700,8.5],[45900,5],[86400,5]])
    lc["clock_reference"]["nominal_rate_error_ppm"] = -18.0
    lc["generation_receipt"] = {"rule": rules["tests"]["LC"], "at_utc": now,
                                 "selected_before_engineering_and_training": True}
    lc["next_owner"] = "A runs one initial; S0 reuses it after both methods freeze. No replacement."
    pt = public["Task"]
    pt.update(task_id=instance, instance_id=instance, description=lc["description"],
              exposure="New complete private scenario, absent from development/formation/training.",
              service=deepcopy(lc["service"]), gateway_windows_s=deepcopy(lc["gateway_windows_s"]),
              optical_environment=deepcopy(lc["optical_environment"]),
              thermal_contract={k:v for k,v in lc["thermal_reference"].items() if k!='air_truth_piecewise_linear_knots_s_c'},
              clock_contract=deepcopy(lc["clock_reference"]))
    public["package"] = PACKAGE
    save(A / "host/lc-host-task.json", lc)
    save(A / "host/lc-public.json", public)
    save(A / "host/TASK-DEFINITION-FREEZE.json", {
        "schema": "lc-learning-private-definition-freeze-v1", "package": PACKAGE, "at_utc": now,
        "rules": bind(A / "host/TASK-RULES.json"), "door": bind(A / "host/door-task.json"),
        "door_public": bind(A / "host/door-public.json"), "lc": bind(A / "host/lc-host-task.json"),
        "lc_public": bind(A / "host/lc-public.json"), "initial_execution_owner": "campaign-a",
        "initial_status": "NOT_EXECUTED", "new_test_replacement": False,
        "definitions_before_new_engineering_or_training": True})
    save(A / "STORAGE-ENTRY.json", {"at_utc": now, "available_before_bytes": free,
        "estimated_peak_additional_bytes": 1_000_000_000, "required_available_bytes": 11_000_000_000,
        "A_retained_cap_bytes": 100_000_000, "package_retained_cap_bytes": 150_000_000,
        "output": str(A), "new_backups_environments_worktrees": 0})
    print(json.dumps({"development": bind(A / "DEVELOPMENT-TASKS.json"),
                      "private_definitions": bind(A / "host/TASK-DEFINITION-FREEZE.json"),
                      "full_calls": 0, "cheap_calls": 0}))


if __name__ == "__main__":
    main()
