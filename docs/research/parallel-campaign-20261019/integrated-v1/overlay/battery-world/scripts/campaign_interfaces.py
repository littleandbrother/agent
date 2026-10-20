#!/usr/bin/env python3
"""Run or read-only verify the finite BFA-046 public development package."""
import argparse
import json
import signal
import sys
import traceback
from pathlib import Path

from bfworld.agentlab.campaign20261019.interfaces import load_protocol, run_suite, verify_run


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path,
                        default=root / "configs/studies/parallel-20261019/interfaces/protocol.json")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="A new absolute directory under the B runtime root")
    mode.add_argument("--verify", type=Path, help="Read-only verify an existing or relocated capsule")
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    signal.alarm(protocol["cost_cap"]["runner_wall_s"])
    try:
        if args.verify:
            print(json.dumps(verify_run(args.verify), sort_keys=True))
        else:
            if not args.output.is_absolute():
                parser.error("--output must be absolute")
            result = run_suite(args.protocol, args.output)
            print(json.dumps({"status": result["status"], "run_id": result["run_id"],
                              "output": str(args.output), "pairs": len(result["pairs"]),
                              "negative_controls": result["negative_controls"],
                              "costs": result["costs"]}, sort_keys=True))
    except Exception:
        # Retain infrastructure/scientific failure separately; never tune a frozen gate here.
        if args.output and args.output.is_dir() and not (args.output / "seal.json").exists():
            failure = args.output / "failure.txt"
            with failure.open("x") as stream:
                traceback.print_exc(file=stream)
        raise
    finally:
        signal.alarm(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
