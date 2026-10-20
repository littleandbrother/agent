#!/usr/bin/env python3
"""Prepare or preflight ABC B inputs; never dispatch a model or scientific job."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "preflight"))
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--episode-root", required=True, type=Path)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    for key in ("source_root", "frozen_families"):
        path = Path(spec[key])
        spec[key] = str(path if path.is_absolute() else (args.spec.parent/path).resolve())
    # Reuse S0's existing phase3 checker without copying its source or environment.
    sys.path.insert(0, str(Path(spec["source_root"])/"packages/python/bfworld/src"))
    module_path = Path(__file__).resolve().parents[1]/"packages/python/bfworld/src/bfworld/agentlab/campaign20261019/abc_interfaces.py"
    name = "bfworld.agentlab.campaign20261019.abc_interfaces"
    loader = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(loader)
    sys.modules[name] = module
    loader.loader.exec_module(module)
    prepared = module.prepare_episode(spec, args.episode_root)
    if args.action == "prepare":
        result = prepared
    else:
        parser.error("preflight requires --request") if args.request is None else None
        handler = module.create_handler(args.episode_root, spec)
        handler({"action": "acquire"})
        result = handler({"action": "preflight", "request": json.loads(args.request.read_text())})
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if result.get("status") != "REJECTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
