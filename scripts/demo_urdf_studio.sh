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
    "$URDF_STUDIO_ROOT/third_party/so-arm100/Simulation/SO101/so101_new_calib.urdf" \
    "$STAGING/robot.urdf"

echo "BenchStudio × URDF Studio"
echo "robot=SO-101 task=cube-lift simulators=$SIMULATORS"
echo "source=$URDF_STUDIO_ROOT"

cd "$URDF_STUDIO_ROOT"
PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    "$URDF_STUDIO_PYTHON" -m backend.scripts.scenario_run \
    "$STAGING" "${SIM_ARGS[@]}" --out "$OUTPUT"

if [[ "$HAS_MUJOCO" == true ]]; then
    for MANIFEST in "$OUTPUT"/manifests/episode-*.json; do
        EPISODE_NAME=$(basename "$MANIFEST" .json)
        EPISODE_DIR="$OUTPUT/mujoco/$EPISODE_NAME"
        [[ -f "$EPISODE_DIR/report.json" ]] || continue
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" "$ROOT/scripts/record_contact_telemetry.py" \
            --scenario "$OUTPUT/scenario/scenario.yaml" \
            --manifest "$MANIFEST" \
            --reference-report "$EPISODE_DIR/report.json" \
            --output "$EPISODE_DIR/contact-telemetry.ndjson" \
            --summary "$EPISODE_DIR/contact-telemetry-summary.json"
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" "$ROOT/scripts/analyze_contact_grasp.py" \
            --scenario "$OUTPUT/scenario/scenario.yaml" \
            --manifest "$MANIFEST" \
            --trace "$EPISODE_DIR/trace.ndjson" \
            --report "$EPISODE_DIR/report.json" \
            --contact-summary "$EPISODE_DIR/contact-telemetry-summary.json" \
            --output "$EPISODE_DIR/contact-analysis.json"
    done

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
            --approach-duration-s 2.4
        mkdir -p "$RECOVERY_ROOT"
        cp "$RECOVERY_STAGING/scenario/intervention.json" \
            "$RECOVERY_ROOT/intervention.json"

        echo "[intervention] episode $RECOVERY_EPISODE_INDEX attempt 0: baseline policy"
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" -m backend.scripts.scenario_episode_worker \
            --scenario "$OUTPUT/scenario" \
            --sim mujoco \
            --episode-manifest "$RECOVERY_MANIFEST" \
            --out "$FAILED_DIR"

        echo "[intervention] episode $RECOVERY_EPISODE_INDEX attempt 1: approach duration 2.4 s"
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" -m backend.scripts.scenario_episode_worker \
            --scenario "$RECOVERY_STAGING/scenario" \
            --sim mujoco \
            --episode-manifest "$RECOVERY_MANIFEST" \
            --out "$RECOVERED_DIR"

        for ATTEMPT_DIR in "$FAILED_DIR" "$RECOVERED_DIR"; do
            ATTEMPT_SCENARIO="$OUTPUT/scenario/scenario.yaml"
            if [[ "$ATTEMPT_DIR" == "$RECOVERED_DIR" ]]; then
                ATTEMPT_SCENARIO="$RECOVERY_STAGING/scenario/scenario.yaml"
            fi
            PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
                "$URDF_STUDIO_PYTHON" "$ROOT/scripts/record_contact_telemetry.py" \
                --scenario "$ATTEMPT_SCENARIO" \
                --manifest "$RECOVERY_MANIFEST" \
                --reference-report "$ATTEMPT_DIR/report.json" \
                --output "$ATTEMPT_DIR/contact-telemetry.ndjson" \
                --summary "$ATTEMPT_DIR/contact-telemetry-summary.json"
            PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
                "$URDF_STUDIO_PYTHON" "$ROOT/scripts/analyze_contact_grasp.py" \
                --scenario "$ATTEMPT_SCENARIO" \
                --manifest "$RECOVERY_MANIFEST" \
                --trace "$ATTEMPT_DIR/trace.ndjson" \
                --report "$ATTEMPT_DIR/report.json" \
                --contact-summary "$ATTEMPT_DIR/contact-telemetry-summary.json" \
                --output "$ATTEMPT_DIR/contact-analysis.json"
        done

        mkdir -p "$OUTPUT/pilot-scenarios"
        cp -R "$RECOVERY_STAGING/scenario" "$OUTPUT/pilot-scenarios/slow-approach"

    fi

    run_pilot_variant() {
        local CONDITION_ID=$1
        local LABEL=$2
        local EPISODE_INDEX=$3
        local TIME_SCALE=$4
        local SHOULDER_OFFSET=$5
        local MAX_STEPS=$6
        local VARIANT_SCENARIO="$OUTPUT/pilot-scenarios/$CONDITION_ID"
        local VARIANT_OUTPUT="$OUTPUT/pilot/$CONDITION_ID"
        local VARIANT_MANIFEST="$OUTPUT/manifests/episode-$EPISODE_INDEX.json"

        "$URDF_STUDIO_PYTHON" "$ROOT/scripts/build_pilot_variant.py" \
            --source "$OUTPUT/scenario" \
            --output "$VARIANT_SCENARIO" \
            --condition-id "$CONDITION_ID" \
            --label "$LABEL" \
            --time-scale "$TIME_SCALE" \
            --shoulder-pan-offset-rad "$SHOULDER_OFFSET" \
            --max-episode-steps "$MAX_STEPS"
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" -m backend.scripts.scenario_episode_worker \
            --scenario "$VARIANT_SCENARIO" \
            --sim mujoco \
            --episode-manifest "$VARIANT_MANIFEST" \
            --out "$VARIANT_OUTPUT"
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" "$ROOT/scripts/record_contact_telemetry.py" \
            --scenario "$VARIANT_SCENARIO/scenario.yaml" \
            --manifest "$VARIANT_MANIFEST" \
            --reference-report "$VARIANT_OUTPUT/report.json" \
            --output "$VARIANT_OUTPUT/contact-telemetry.ndjson" \
            --summary "$VARIANT_OUTPUT/contact-telemetry-summary.json"
        PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" "$ROOT/scripts/analyze_contact_grasp.py" \
            --scenario "$VARIANT_SCENARIO/scenario.yaml" \
            --manifest "$VARIANT_MANIFEST" \
            --trace "$VARIANT_OUTPUT/trace.ndjson" \
            --report "$VARIANT_OUTPUT/report.json" \
            --contact-summary "$VARIANT_OUTPUT/contact-telemetry-summary.json" \
            --output "$VARIANT_OUTPUT/contact-analysis.json"
        local VARIANT_VIDEO="$VARIANT_OUTPUT/episode-robot.mp4"
        if MUJOCO_GL=egl PYTHONPATH="$URDF_STUDIO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
            "$URDF_STUDIO_PYTHON" "$ROOT/scripts/render_urdf_studio_episode.py" \
            --scenario "$VARIANT_SCENARIO/scenario.yaml" \
            --manifest "$VARIANT_MANIFEST" \
            --trace "$VARIANT_OUTPUT/trace.ndjson" \
            --output "$VARIANT_VIDEO"; then
            mv "$VARIANT_OUTPUT/episode.mp4" "$VARIANT_OUTPUT/episode-schematic.mp4"
            mv "$VARIANT_VIDEO" "$VARIANT_OUTPUT/episode.mp4"
        fi
    }

    run_pilot_variant fast-approach "Fast approach" 1 0.65 0.0 250
    run_pilot_variant lateral-offset "Lateral offset" 3 1.25 0.22 325

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
            --failed-policy "$OUTPUT/scenario/waypoints.json" \
            --recovered-policy "$RECOVERY_STAGING/scenario/waypoints.json"
    fi

    "$URDF_STUDIO_PYTHON" "$ROOT/scripts/build_pilot_cohort.py" \
        --run-root "$OUTPUT" \
        --output "$OUTPUT/pilot-cohort.json"
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
