#!/usr/bin/env python3
"""Pure JSON phase-two proposal validator. Does not run a Pi or scientific tool."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/python/bfworld/src"))
from bfworld.agentlab.campaign20261019 import phase2_methods as methods


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("schema", "validate", "classify", "impact", "reexecution"))
    args = parser.parse_args()
    try:
        if args.action == "schema":
            value = methods.tool_schema()
        else:
            raw = sys.stdin.buffer.read(65537)
            if len(raw) > 65536:
                raise ValueError("INPUT_BYTE_LIMIT")
            value = json.loads(raw)
            if args.action == "validate":
                value = methods.validate_method(value)
            elif args.action == "classify":
                value = {"artifact": methods.classify_change(value)}
            elif args.action == "impact":
                value = {"scope": methods.impact_scope(value)}
            else:
                if not isinstance(value, dict) or set(value) != {"change", "policy"}:
                    raise ValueError("CHANGE_AND_POLICY_REQUIRED")
                value = methods.validate_reexecution(value["change"], value["policy"])
        print(json.dumps({"ok": True, "value": value}, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
