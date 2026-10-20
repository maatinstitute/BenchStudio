#!/usr/bin/env bash

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT=${1:-"$ROOT/runs/urdf-studio-so101-cube"}
SIMULATORS=${2:-mujoco}
URDF_STUDIO_ROOT=${URDF_STUDIO_ROOT:-"$(cd "$ROOT/.." && pwd)/urdf-studio"}
URDF_STUDIO_PYTHON=${URDF_STUDIO_PYTHON:-"$URDF_STUDIO_ROOT/.venv/bin/python"}

IFS=',' read -r -a SIMULATOR_LIST <<<"$SIMULATORS"
SIM_ARGS=()
HAS_MUJOCO=false
for simulator in "${SIMULATOR_LIST[@]}"; do
    case "$simulator" in
        mujoco) HAS_MUJOCO=true ;;
        genesis) ;;
        *) echo "Unsupported simulator: $simulator (choose mujoco or genesis)" >&2; exit 2 ;;
    esac
    SIM_ARGS+=(--sim "$simulator")
done

if [[ ! -d "$URDF_STUDIO_ROOT/backend" ]]; then
    echo "URDF Studio source was not found: $URDF_STUDIO_ROOT" >&2
    echo "Set URDF_STUDIO_ROOT to the upstream checkout." >&2
    exit 2
fi
if [[ ! -x "$URDF_STUDIO_PYTHON" ]]; then
    echo "URDF Studio Python was not found: $URDF_STUDIO_PYTHON" >&2
    exit 2
fi
if [[ -e "$OUTPUT" ]]; then
    OUTPUT="${OUTPUT}-$(date +%Y%m%d-%H%M%S)"
    echo "Requested output already exists; using: $OUTPUT"
fi

STAGING=$(mktemp -d /tmp/benchstudio-so101-cube.XXXXXX)
trap 'rm -rf "$STAGING"' EXIT
cp -R "$ROOT/examples/urdf_studio_so101_cube/." "$STAGING/"
cp -R "$URDF_STUDIO_ROOT/web/public/demo/assets" "$STAGING/assets"
"$URDF_STUDIO_PYTHON" "$ROOT/scripts/prepare_urdf_studio_robot.py" \
    "$URDF_STUDIO_ROOT/web/public/demo/robot.urdf" "$STAGING/robot.urdf"

echo "BenchStudio × URDF Studio"
echo "robot=SO-101 task=cube-lift simulators=$SIMULATORS"
echo "source=$URDF_STUDIO_ROOT"

cd "$URDF_STUDIO_ROOT"
PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    "$URDF_STUDIO_PYTHON" -m backend.scripts.scenario_run \
    "$STAGING" "${SIM_ARGS[@]}" --out "$OUTPUT" --episodes 1

if [[ "$HAS_MUJOCO" == true && -f "$OUTPUT/mujoco/episode-0/report.json" ]]; then
    EPISODE_DIR="$OUTPUT/mujoco/episode-0"
    ROBOT_VIDEO="$EPISODE_DIR/episode-robot.mp4"
    if MUJOCO_GL=egl PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        "$URDF_STUDIO_PYTHON" "$ROOT/scripts/render_urdf_studio_episode.py" \
        --scenario "$OUTPUT/scenario/scenario.yaml" \
        --manifest "$OUTPUT/manifests/episode-0.json" \
        --trace "$EPISODE_DIR/trace.ndjson" \
        --output "$ROBOT_VIDEO"; then
        mv "$EPISODE_DIR/episode.mp4" "$EPISODE_DIR/episode-schematic.mp4"
        mv "$ROBOT_VIDEO" "$EPISODE_DIR/episode.mp4"
    else
        echo "Robot replay render unavailable; keeping URDF Studio's schematic video." >&2
    fi
fi

PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    "$URDF_STUDIO_PYTHON" "$ROOT/scripts/build_simulator_debug_manifest.py" \
    --scenario "$OUTPUT/scenario" \
    --run "$OUTPUT/run.json" \
    --comparison "$OUTPUT/comparison.json" \
    --output "$OUTPUT/simulator-debug.json"

echo
echo "URDF Studio evaluation complete: $OUTPUT"
echo "Report: $OUTPUT/report.html"
