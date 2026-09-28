"""Battery World command line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from bfworld.agent.observation import public_observation
from bfworld.bundle.reader import RunBundleReader
from bfworld.kernel.canonical import canonical_bytes
from bfworld.verification.verifier import verify_bundle
from bfworld.application.rotary import run_rotary_mission


def _print(value: object) -> None:
    print(canonical_bytes(value).decode("utf-8"))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="bfworld")
    sub = result.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="execute the A Rotary-TENG vertical slice")
    run.add_argument("--mission", type=Path, required=True)
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--crash-after", choices=["baseline"])

    verify = sub.add_parser("verify", help="independently verify a RunBundle")
    verify.add_argument("--bundle", type=Path, required=True)
    replay = sub.add_parser("replay", help="replay and reproduce bundle identity")
    replay.add_argument("--bundle", type=Path, required=True)
    inspect = sub.add_parser("inspect", help="emit the A Agent-readable observation")
    inspect.add_argument("--bundle", type=Path, required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "run":
        _print(
            run_rotary_mission(
                args.mission,
                args.workspace,
                args.output,
                resume=args.resume,
                crash_after=args.crash_after,
            )
        )
        return 0
    if args.command in {"verify", "replay"}:
        _print(verify_bundle(args.bundle))
        return 0
    if args.command == "inspect":
        _print(public_observation(RunBundleReader(args.bundle)))
        return 0
    raise AssertionError(args.command)
