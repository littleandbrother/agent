#!/usr/bin/env python3
from __future__ import annotations

import importlib.metadata
import json
import platform
import sys


EXPECTED = {
    "jsonschema": "4.23.0",
    "pyarrow": "22.0.0",
    "PyYAML": "6.0.2",
}


def main() -> int:
    observed = {name: importlib.metadata.version(name) for name in EXPECTED}
    problems = {
        name: {"expected": expected, "observed": observed[name]}
        for name, expected in EXPECTED.items()
        if observed[name] != expected
    }
    python_ok = sys.version_info[:2] == (3, 11)
    report = {
        "schema_version": "bfworld-environment-check-v1",
        "status": "passed" if python_ok and not problems else "failed",
        "python": platform.python_version(),
        "expected_python": "3.11.x",
        "dependencies": observed,
        "problems": problems,
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

