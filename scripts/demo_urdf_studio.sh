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
RECOVERY_STAGING=""
cleanup() {
    rm -rf "$STAGING"
    if [[ -n "$RECOVERY_STAGING" ]]; then
        rm -rf "$RECOVERY_STAGING"
    fi
}
trap cleanup EXIT
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
    "$STAGING" "${SIM_ARGS[@]}" --out "$OUTPUT"

if [[ "$HAS_MUJOCO" == true ]]; then
    RECOVERY_EPISODE_INDEX=${BENCHSTUDIO_RECOVERY_EPISODE_INDEX:-2}
    RECOVERY_MANIFEST="$OUTPUT/manifests/episode-$RECOVERY_EPISODE_INDEX.json"
    if [[ -f "$RECOVERY_MANIFEST" ]]; then
        RECOVERY_ROOT="$OUTPUT/recovery/episode-$RECOVERY_EPISODE_INDEX"
        FAILED_DIR="$RECOVERY_ROOT/attempt-0"
        RECOVERED_DIR="$RECOVERY_ROOT/attempt-1"
        RECOVERY_STAGING=$(mktemp -d /tmp/benchstudio-so101-recovery.XXXXXX)
        "$URDF_STUDIO_PYTHON" "$ROOT/scripts/build_recovery_fixture.py" prepare \
            --source "$OUTPUT/scenario" \
            --output "$RECOVERY_STAGING/scenario" \
            --max-steps 125
        mkdir -p "$RECOVERY_ROOT"
        cp "$RECOVERY_STAGING/scenario/recovery-intervention.json" \
            "$RECOVERY_ROOT/intervention.json"

        echo "[recovery] episode $RECOVERY_EPISODE_INDEX attempt 0: constrained horizon"
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" -m backend.scripts.scenario_episode_worker \
            --scenario "$RECOVERY_STAGING/scenario" \
            --sim mujoco \
            --episode-manifest "$RECOVERY_MANIFEST" \
            --out "$FAILED_DIR"

        echo "[recovery] episode $RECOVERY_EPISODE_INDEX attempt 1: protocol horizon restored"
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" -m backend.scripts.scenario_episode_worker \
            --scenario "$OUTPUT/scenario" \
            --sim mujoco \
            --episode-manifest "$RECOVERY_MANIFEST" \
            --out "$RECOVERED_DIR"

        cp "$RECOVERED_DIR/report.json" "$RECOVERED_DIR/trace.ndjson" \
            "$RECOVERED_DIR/decisions.ndjson" "$RECOVERED_DIR/episode.mp4" \
            "$OUTPUT/mujoco/episode-$RECOVERY_EPISODE_INDEX/"
    fi

    for MANIFEST in "$OUTPUT"/manifests/episode-*.json; do
        EPISODE_NAME=$(basename "$MANIFEST" .json)
        EPISODE_DIR="$OUTPUT/mujoco/$EPISODE_NAME"
        [[ -f "$EPISODE_DIR/report.json" ]] || continue
        ROBOT_VIDEO="$EPISODE_DIR/episode-robot.mp4"
        if MUJOCO_GL=egl PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" "$ROOT/scripts/render_urdf_studio_episode.py" \
            --scenario "$OUTPUT/scenario/scenario.yaml" \
            --manifest "$MANIFEST" \
            --trace "$EPISODE_DIR/trace.ndjson" \
            --output "$ROBOT_VIDEO"; then
            mv "$EPISODE_DIR/episode.mp4" "$EPISODE_DIR/episode-schematic.mp4"
            mv "$ROBOT_VIDEO" "$EPISODE_DIR/episode.mp4"
        else
            echo "Robot replay render unavailable for $EPISODE_NAME; keeping schematic video." >&2
        fi
    done

    if [[ -f "${RECOVERY_MANIFEST:-}" ]]; then
        for ATTEMPT_DIR in "$FAILED_DIR" "$RECOVERED_DIR"; do
            ATTEMPT_VIDEO="$ATTEMPT_DIR/episode-robot.mp4"
            if MUJOCO_GL=egl PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
                "$URDF_STUDIO_PYTHON" "$ROOT/scripts/render_urdf_studio_episode.py" \
                --scenario "$OUTPUT/scenario/scenario.yaml" \
                --manifest "$RECOVERY_MANIFEST" \
                --trace "$ATTEMPT_DIR/trace.ndjson" \
                --output "$ATTEMPT_VIDEO"; then
                mv "$ATTEMPT_DIR/episode.mp4" "$ATTEMPT_DIR/episode-schematic.mp4"
                mv "$ATTEMPT_VIDEO" "$ATTEMPT_DIR/episode.mp4"
            else
                echo "Robot replay render unavailable for $ATTEMPT_DIR; keeping schematic video." >&2
            fi
        done
        "$URDF_STUDIO_PYTHON" "$ROOT/scripts/build_recovery_fixture.py" bind \
            --output "$OUTPUT/recovery.json" \
            --episode-index "$RECOVERY_EPISODE_INDEX" \
            --manifest "$RECOVERY_MANIFEST" \
            --intervention "$RECOVERY_ROOT/intervention.json" \
            --failed-dir "$FAILED_DIR" \
            --recovered-dir "$RECOVERED_DIR" \
            --failed-policy "$RECOVERY_STAGING/scenario/waypoints.json" \
            --recovered-policy "$OUTPUT/scenario/waypoints.json"
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
