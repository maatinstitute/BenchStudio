#!/usr/bin/env bash

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT=${1:-"$ROOT/runs/benchstudio-demo"}
SERVE=${2:-""}
SIMULATORS=${BENCHSTUDIO_SIMULATORS:-${BENCHSTUDIO_SIMULATOR:-mujoco,genesis}}
URDF_STUDIO_ROOT=${URDF_STUDIO_ROOT:-"$(cd "$ROOT/.." && pwd)/urdf-studio"}

if [[ -e "$OUTPUT" ]]; then
    SUFFIX=$(date +%Y%m%d-%H%M%S)
    OUTPUT="${OUTPUT}-${SUFFIX}"
    echo "Requested output already exists; using: $OUTPUT"
fi

mkdir -p "$OUTPUT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "[1/5] Frozen campaign execution"
python -m benchstudio.cli \
  --campaign-spec "$ROOT/examples/campaigns/mock-worldepisode.json" \
  --plan-output "$OUTPUT/campaign-plan.json" \
  --execute-mock --workers 2 --audit \
  --output "$OUTPUT/campaign"

echo "[2/5] Robustness and recovery evidence"
python "$ROOT/examples/run_mock_robustness.py" --output "$OUTPUT/robustness"

echo "[3/5] Matched transfer-fidelity fixture"
python "$ROOT/examples/run_mock_transfer.py" --output "$OUTPUT/transfer"

echo "[4/5] RoboChallenge observe/action transport boundary"
python "$ROOT/examples/run_robochallenge_mock.py" >"$OUTPUT/robochallenge-report.json"
cat "$OUTPUT/robochallenge-report.json"

if [[ -d "$URDF_STUDIO_ROOT/backend" ]]; then
    echo "[5/5] URDF Studio SO-101 cube-lift evaluation ($SIMULATORS)"
    URDF_STUDIO_ROOT="$URDF_STUDIO_ROOT" \
        bash "$ROOT/scripts/demo_urdf_studio.sh" "$OUTPUT/urdf-studio" "$SIMULATORS"
else
    echo "[5/5] URDF Studio checkout not found; robot episode skipped"
    echo "      Set URDF_STUDIO_ROOT to enable the SO-101 cube-lift evaluation."
fi

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
