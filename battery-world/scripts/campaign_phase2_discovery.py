#!/usr/bin/env python3
"""Phase-two discovery schema, pure proposal checking and MOCK preparation."""
from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path

from bfworld.agentlab.campaign20261019 import phase2_discovery as discovery


def load(path: Path):
    if path.stat().st_size > discovery.MAX_SOURCE_BYTES:
        raise ValueError("INPUT_BYTE_LIMIT")
    return json.loads(path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("schema", help="Generic S0 operation parameters, no target fields or formula")
    validate = sub.add_parser("validate"); validate.add_argument("--proposal", type=Path, required=True)
    evaluate = sub.add_parser("evaluate", help="Local unqualified value only; no consumer or scientific execution")
    evaluate.add_argument("--proposal", type=Path, required=True); evaluate.add_argument("--source", type=Path, required=True)
    evaluate.add_argument("--field-units", type=Path)
    request = sub.add_parser("request", help="Check generic host request and conditional table")
    request.add_argument("--input", type=Path, required=True); request.add_argument("--legal-domain", type=Path)
    prep = sub.add_parser("prepare", help="Two explicit MOCK fixtures, no live episode")
    prep.add_argument("--profile", type=Path, required=True); prep.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); signal.alarm(60)
    try:
        if args.command == "schema": result = discovery.tool_schema()
        elif args.command == "validate": result = discovery.validate_proposal(load(args.proposal))
        elif args.command == "evaluate":
            result = discovery.evaluate_proposal(load(args.proposal), load(args.source),
                                                field_units=load(args.field_units) if args.field_units else None)
        elif args.command == "request":
            result = discovery.validate_request(load(args.input), legal_domain=load(args.legal_domain) if args.legal_domain else None)
        else: result = discovery.prepare_mock(args.root, args.profile, args.output)
    except (ValueError, OSError, KeyError, RecursionError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc),
                          "qualification": "EXTERNAL_REQUIRED", "real_consumer": "NOT_EXECUTED"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
