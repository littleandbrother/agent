#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -n "${BFWORLD_PYTHON:-}" ]]; then
  PYTHON_BIN="$BFWORLD_PYTHON"
elif [[ -x "$HOME/.local/share/bf-agent-runtime/product-cad/bin/python" ]]; then
  PYTHON_BIN="$HOME/.local/share/bf-agent-runtime/product-cad/bin/python"
elif [[ -x .venv/bin/python ]]; then
  PYTHON_BIN=.venv/bin/python
else
  PYTHON_BIN="${BFWORLD_PYTHON:-/usr/local/bin/python3}"
fi

export PYTHONPATH="$ROOT_DIR/packages/python/bfworld/src"

if [[ "${BFWORLD_VERIFY_PROFILE:-}" == "architecture-v2-ci" ]]; then
  export PYTHONPATH="$PYTHONPATH:$ROOT_DIR/tests/agentlab"
  "$PYTHON_BIN" -m unittest discover -s tests/agentlab -p 'test_repository*.py' -v
  "$PYTHON_BIN" docs/agentlab/architecture-v2/power-feedback-20261018/verify_saved.py
  exit
fi

if [[ "${BFWORLD_VERIFY_PROFILE:-}" == "power-feedback" ]]; then
  "$PYTHON_BIN" scripts/verify_power_feedback.py \
    --runtime "${BF_V2_RUNTIME:-$HOME/.local/share/bf-agent-architecture-v2}" \
    --output "${BF_FEEDBACK_EVIDENCE:?set the feedback evidence/cache directory}"
  exit
fi

if [[ "${BFWORLD_VERIFY_PROFILE:-}" == "architecture-v2-lab" ]]; then
  "$PYTHON_BIN" scripts/verify_lab_publication.py \
    --output "${BF_V2_EVIDENCE:?set a new verification output directory}"
  exit
fi

if [[ "${BFWORLD_VERIFY_PROFILE:-}" == "architecture-v2" ]]; then
  "$PYTHON_BIN" scripts/verify_v2_environment.py \
    --runtime "${BF_V2_RUNTIME:?set the isolated V2 runtime}" \
    --output "${BF_V2_EVIDENCE:?set a new verification output directory}"
  exit
fi

echo "=== Battery World environment ==="
"$PYTHON_BIN" scripts/check_environment.py

echo "=== Canonical A materialization and fresh reproduction ==="
"$PYTHON_BIN" scripts/validate_a.py

echo "=== B0 semantic golden episodes and byte-identical reproduction ==="
"$PYTHON_BIN" scripts/validate_golden_episodes.py --rebuild

echo "=== Evidence-gated project roadmap and progress ==="
"$PYTHON_BIN" scripts/validate_project_state.py
"$PYTHON_BIN" scripts/check_pilot_readiness.py
"$PYTHON_BIN" scripts/audit_campaign.py

echo "=== Python contract, boundary, integration, replay, chaos, semantic, and project tests ==="
"$PYTHON_BIN" scripts/build_deployments.py
"$PYTHON_BIN" scripts/build_learning_study.py
"$PYTHON_BIN" scripts/build_coupled.py
"$PYTHON_BIN" scripts/build_studio.py
"$PYTHON_BIN" -m unittest discover -s tests -v

echo "=== TypeScript SDK contract ==="
corepack pnpm run check:sdk

echo "=== World Studio types, source projection, and portable build ==="
"$PYTHON_BIN" scripts/validate_control.py
corepack pnpm run check:studio
corepack pnpm run build:studio
"$PYTHON_BIN" scripts/validate_studio.py

echo "=== Battery World repository verification complete ==="
