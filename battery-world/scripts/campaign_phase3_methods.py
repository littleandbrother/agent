#!/usr/bin/env python3
"""Read-only entry to the phase3 method contracts; no scientific execution."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/python/bfworld/src"))
from bfworld.agentlab.campaign20261019 import phase3_methods as methods


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("conditions", "comparisons", "event-contract", "budget"))
    parser.add_argument("--change-json", default='{"changed_artifact":"D"}')
    parser.add_argument("--condition", choices=methods.CONDITIONS, default="fixed_h")
    parser.add_argument("--usage-json", default='{"total_requests":0,"total_wall_s":0}')
    args = parser.parse_args()
    if args.command == "conditions":
        result = json.loads((ROOT / "configs/studies/phase3-20261020/methods/conditions.json").read_text())
    elif args.command == "comparisons":
        result = methods.comparison_registry(json.loads(args.change_json))
    elif args.command == "event-contract":
        result = methods.ordered_event_requirements()
    else:
        result = methods.remaining_budget(args.condition, **json.loads(args.usage_json))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
