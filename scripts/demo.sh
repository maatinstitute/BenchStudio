#!/usr/bin/env bash

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT=${1:-"$ROOT/runs/benchstudio-demo"}
SERVE=${2:-""}

if [[ -e "$OUTPUT" ]]; then
    SUFFIX=$(date +%Y%m%d-%H%M%S)
    OUTPUT="${OUTPUT}-${SUFFIX}"
    echo "Requested output already exists; using: $OUTPUT"
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

python -m benchstudio.demo_dashboard \
  --input "$OUTPUT" \
  --output "$OUTPUT/index.html"

echo
echo "Demo complete. Evidence is in: $OUTPUT"
find "$OUTPUT" -maxdepth 2 -type f | sort

if [[ "$SERVE" == "--serve" ]]; then
    echo
    echo "Opening the visual control room at http://127.0.0.1:8765"
    echo "Press Ctrl-C to stop the demo server."
    cd "$OUTPUT"
    python -m http.server 8765 --bind 127.0.0.1
fi
