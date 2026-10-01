#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -B -m unittest discover -s tests -v
python -B src/authoritative_world.py verify
