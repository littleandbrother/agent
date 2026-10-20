#!/usr/bin/env python3
"""Finite BF interface preparation, readback verification and offline replay."""
from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from bfworld.agentlab.campaign20261019 import bf_interfaces as bf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Export 64 inputs and E5 contract; no model or physical solves")
    prep.add_argument("--profile", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify", help="Read-only sealed artifact and parity audit")
    check.add_argument("--output", type=Path, required=True)
    participant = sub.add_parser("input", help="Audit one participant mount without any evaluator read")
    participant.add_argument("--trial-dir", type=Path, required=True)
    gate = sub.add_parser("gate", help="Fail-closed capability/storage admission")
    gate.add_argument("--profile", type=Path, required=True)
    gate.add_argument("--action", required=True)
    replay = sub.add_parser("replay", help="One trusted-side saved observation; no live Agent run")
    replay.add_argument("--profile", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--trial", required=True)
    replay.add_argument("--operation", choices=[x["operation"] for x in bf.TOOLS], required=True)
    replay.add_argument("--patch", type=json.loads)
    args = parser.parse_args()
    signal.alarm(120 if args.command == "prepare" else 60)
    try:
        if args.command == "prepare":
            result = bf.prepare(args.root, args.profile, args.output)
        elif args.command == "verify":
            bf.load_protocol(args.root)
            result = bf.verify(args.output)
        elif args.command == "gate":
            result = bf.resource_gate(args.root, args.profile, args.action)
        elif args.command == "input":
            result = bf.verify_trial(args.trial_dir)
        else:
            bf.resource_gate(args.root, args.profile, "replay")
            result = bf.replay_observation(args.output, args.trial, args.operation, args.patch)
    except (ValueError, KeyError, OSError, StopIteration) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
