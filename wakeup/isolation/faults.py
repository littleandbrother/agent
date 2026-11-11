"""Three fixed fault instances; reuse measured facts, otherwise run the original ODE."""
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "deep"))
import semantic_alias as physical

FILE = HERE / "faults_qualification.json"
DATA = json.loads(FILE.read_text()) if FILE.exists() else {"records": {}, "and_corners": []}
LOAD_PULL = json.loads((HERE / "load_pull.json").read_text())
GROUPS = dict(main_length_mm="harvester", aux_length_mm="trigger", threshold_V="trigger", C_uF="storage", gate_V="storage")


def tasks():
    old = {t["id"]: t for t in physical.tasks()}
    result = []
    for ident, origin, factors in (
        ("T1a", "P2_unit_u", {"main_factor": .75}),
        ("T1b", "P2_unit_v", {"aux_factor": 1.4}),
        ("T2", "P2_unit_u", {"main_factor": .75, "aux_factor": 1.4}),
    ):
        t = copy.deepcopy(old[origin])
        t.update(id=ident, _physical=factors, groups=GROUPS.copy())
        if ident == "T2":
            t["spec"]["uncertainty"] = t["spec"]["uncertainty"].replace("one beam", "one or more beams")
        t["clean_spec"] = copy.deepcopy(t["spec"])
        t["clean_spec"]["controls"] = {
            "main_length_mm": "Nominal main energy-harvesting beam length, mm.",
            "aux_length_mm": "Nominal auxiliary beam length feeding the envelope detector, mm.",
            "C_uF": "Storage capacitance, microfarads; stores supply energy.",
            "gate_V": "Stored supply voltage required to start the MCU, V; not an envelope threshold.",
            "threshold_V": "Envelope voltage required to assert the wake comparator, V; not the supply voltage.",
            "brownout_V": "Fixed stored-supply brownout voltage: 1.8 V.",
        }
        result.append(t)
    t3 = copy.deepcopy(LOAD_PULL["task"])
    t3.update(groups=LOAD_PULL["groups"], clean_spec=copy.deepcopy(LOAD_PULL["clean_spec"]))
    t3["clean_spec"]["controls"] = result[0]["clean_spec"]["controls"].copy()
    result.append(t3)
    return result


def _key(t, x):
    return json.dumps([physical._design(t, x), physical.TASK], sort_keys=True)


def _put(t, x, terminal, views, source):
    key = _key(t, x)
    record = DATA["records"].setdefault(key, dict(task=t["id"], design=x.copy(), source=source))
    record["terminal"] = terminal
    record.update({k: v["metrics"] for k, v in views.items()})
    return record


def _seed():
    old = {t["id"]: t for t in physical.tasks()}
    q = HERE.parent / "deep" / "semantic_alias_qualification.json"
    for row in json.loads(q.read_text()):
        if row["id"] not in ("P2_unit_u", "P2_unit_v"):
            continue
        t = old[row["id"]]
        views = {k: row[k] for k in ("power", "trigger", "program") if k in row}
        _put(t, row["initial_input"], row["initial"], views, str(q))
        _put(t, row["witness_input"], row["witness"], {}, str(q))
        for run in row.get("diagnosis_reproduction", {}).get("runs", []):
            _put(t, run["design"], run["result"], run["measurements"], str(q) + "#diagnosis_reproduction")
    log = HERE.parent / "deep" / "agents.jsonl"
    with log.open() as stream:
        for line in stream:
            if '"kind": "observation"' not in line:
                continue
            row = json.loads(line)
            ident = row["job"].split("/")[0]
            if ident in ("P2_unit_u", "P2_unit_v") and row["design"] == old[ident]["initial"]:
                record = DATA["records"][_key(old[ident], row["design"])]
                record[row["observation"]] = row["result"]["metrics"]


def _save():
    FILE.write_text(json.dumps(DATA, indent=2) + "\n")


def evaluate(t, x):
    key = _key(t, x)
    reused = key in DATA["records"]
    if reused:
        record = DATA["records"][key]
    else:
        terminal = physical.evaluate(t, x)
        views = {k: physical.evaluate(t, x, observation=k) for k in ("power", "trigger", "program")}
        record = _put(t, x, terminal, views, "original semantic_alias.evaluate, full transient")
        _save()
    terminal = record["terminal"]
    unavailable = dict(available=False, reason="This exact old input retained its terminal result but not this diagnostic view.")
    return dict(pass_=terminal["pass_"], terminal=terminal["metrics"],
                **{k: record.get(k, unavailable) for k in ("power", "trigger", "program")},
                slack=terminal["slack"], cost=dict(full=0 if reused else terminal["cost"]["full"], numeric=0),
                fidelity=terminal["fidelity"], reused=reused, source=record["source"])


if not FILE.exists():
    _seed()
    _save()

for row in LOAD_PULL["qualification"]:
    _put(LOAD_PULL["task"], row["design"], row["result"], row["views"], str(HERE / "load_pull.json"))
_save()


if __name__ == "__main__":
    t = next(t for t in tasks() if t["id"] == "T2")
    for name, patch in (("both_bad", {}), ("main_only", dict(main_length_mm=40.)),
                        ("aux_only", dict(aux_length_mm=18 / 1.4)),
                        ("both_repaired", dict(main_length_mm=40., aux_length_mm=18 / 1.4))):
        x = t["initial"] | patch
        r = evaluate(t, x)
        DATA["and_corners"].append(dict(name=name, design=x, result=r))
        _save()
        print(name, json.dumps(r, ensure_ascii=False), flush=True)
