#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BASE="${BFWORLD_BOOTSTRAP_PYTHON:-/usr/local/bin/python3}"
"$PYTHON_BASE" -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check --requirement requirements.lock
.venv/bin/python -m pip install --disable-pip-version-check --no-deps --force-reinstall .
.venv/bin/python -c 'import bfworld'
corepack pnpm install --frozen-lockfile

echo "Battery World bootstrap complete. Run ./init.sh."
