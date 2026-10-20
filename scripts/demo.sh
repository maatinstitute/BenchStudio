#!/usr/bin/env bash

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT=${1:-"$ROOT/runs/benchstudio-demo"}

if [[ -e "$OUTPUT" ]]; then
    echo "Refusing to overwrite existing demo output: $OUTPUT" >&2
    exit 2
fi

mkdir -p "$OUTPUT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "[1/4] Frozen campaign execution"
python -m benchstudio.cli \
  --campaign-spec "$ROOT/examples/campaigns/mock-worldepisode.json" \
  --plan-output "$OUTPUT/campaign-plan.json" \
  --execute-mock --workers 2 --audit \
  --output "$OUTPUT/campaign"

echo "[2/4] Robustness and recovery evidence"
python "$ROOT/examples/run_mock_robustness.py" --output "$OUTPUT/robustness"

echo "[3/4] Matched transfer-fidelity fixture"
python "$ROOT/examples/run_mock_transfer.py" --output "$OUTPUT/transfer"

echo "[4/4] RoboChallenge observe/action transport boundary"
python "$ROOT/examples/run_robochallenge_mock.py" >"$OUTPUT/robochallenge-report.json"
cat "$OUTPUT/robochallenge-report.json"

echo
echo "Demo complete. Evidence is in: $OUTPUT"
find "$OUTPUT" -maxdepth 2 -type f | sort
