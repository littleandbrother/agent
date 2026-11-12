"""Local physics only. No model client, experiment runner or permission layer."""
import argparse
import importlib

MODULES = dict(e1="feedback", e2="active", e3="structure", e4="stopping")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment", choices=[*MODULES, "all"], default="all")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    for name in MODULES if a.experiment == "all" else [a.experiment]:
        importlib.import_module(MODULES[name]).calibrate(workers=a.workers)
    from explain import build
    print(build())
