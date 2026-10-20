"""Build a self-contained visual dashboard from BenchStudio demo evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    return rows


def _short(value: Any, length: int = 12) -> str:
    text = str(value or "unavailable")
    return html.escape(text[:length])


def _percent(value: Any) -> int:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0
    return max(0, min(100, round(float(value) * 100)))


def build_demo_dashboard(input_dir: Path, output_path: Path) -> Path:
    """Render the demo evidence directory as a standalone HTML control room."""
    root = Path(input_dir)
    plan = _load_json(root / "campaign-plan.json")
    ledger = _load_jsonl(root / "campaign" / "attempt-results.jsonl")
    robustness = _load_json(root / "robustness" / "counterfactual-summary.json")
    transfer = _load_json(root / "transfer" / "transfer-report.json")
    robochallenge = _load_json(root / "robochallenge-report.json")

    robot_run: dict[str, Any] = {}
    robot_report: dict[str, Any] = {}
    robot_episodes: list[dict[str, Any]] = []
    robot_comparison: dict[str, Any] = {}
    robot_policy: dict[str, Any] = {}
    robot_recovery: dict[str, Any] = {}
    simulator_debug: dict[str, Any] = {}
    robot_policy_digest = "not loaded"
    robot_policy_timeline = "No policy artifact loaded"
    robot_root = root / "urdf-studio"
    selected_simulator = "mujoco"
    if (robot_root / "run.json").is_file():
        robot_run = _load_json(robot_root / "run.json")
        simulator_names = robot_run.get("sims", [])
        if isinstance(simulator_names, list) and simulator_names:
            selected_simulator = str(simulator_names[0])
        comparison_path = robot_root / "comparison.json"
        policy_path = robot_root / "scenario" / "waypoints.json"
        simulator_debug_path = robot_root / "simulator-debug.json"
        recovery_path = robot_root / "recovery.json"
        episode_count = int(robot_run.get("episodes", 0) or 0)
        for episode_index in range(episode_count):
            report_path = (
                robot_root
                / selected_simulator
                / f"episode-{episode_index}"
                / "report.json"
            )
            manifest_path = robot_root / "manifests" / f"episode-{episode_index}.json"
            contact_analysis_path = report_path.parent / "contact-analysis.json"
            if not report_path.is_file():
                continue
            episode = {
                "episode_index": episode_index,
                "report": _load_json(report_path),
                "manifest": _load_json(manifest_path) if manifest_path.is_file() else {},
                "contact_analysis": (
                    _load_json(contact_analysis_path)
                    if contact_analysis_path.is_file()
                    else {}
                ),
            }
            robot_episodes.append(episode)
        if robot_episodes:
            robot_report = robot_episodes[0]["report"]
        if comparison_path.is_file():
            robot_comparison = _load_json(comparison_path)
        if policy_path.is_file():
            robot_policy = _load_json(policy_path)
            robot_policy_digest = hashlib.sha256(policy_path.read_bytes()).hexdigest()
            raw_waypoints = robot_policy.get("waypoints", [])
            if isinstance(raw_waypoints, list):
                events = []
                for waypoint in raw_waypoints:
                    if not isinstance(waypoint, dict):
                        continue
                    label = str(waypoint.get("label", "waypoint"))
                    time_s = float(waypoint.get("time_s", 0.0) or 0.0)
                    events.append(f"{label} {time_s:.1f}s")
                if events:
                    robot_policy_timeline = " · ".join(events)
        if simulator_debug_path.is_file():
            simulator_debug = _load_json(simulator_debug_path)
        if recovery_path.is_file():
            robot_recovery = _load_json(recovery_path)

    attempts = plan.get("attempts", [])
    completed = sum(row.get("status") == "completed" for row in ledger)
    failed = sum(row.get("status") != "completed" for row in ledger)
    evidence_verified = sum(row.get("evidence_verified") is True for row in ledger)
    scheduled = len(attempts)
    missing = max(0, scheduled - len(ledger))
    evidence_rate = round(100 * evidence_verified / scheduled) if scheduled else 0

    transfer_fidelity = transfer.get("transfer_fidelity", {})
    simulation_rate = _percent(transfer_fidelity.get("simulation_success_rate"))
    boundary_rate = _percent(transfer_fidelity.get("physical_success_rate"))
    gap = round(
        float(transfer_fidelity.get("success_gap_physical_minus_simulation", 0)) * 100
    )
    matched_pairs = int(transfer_fidelity.get("matched_pairs", 0) or 0)
    branches = int(robustness.get("scheduled_branch_count", 0) or 0)
    complete_branches = int(robustness.get("completed_branch_count", 0) or 0)

    conditions: dict[str, dict[str, Any]] = {}
    pair_ids: list[str] = []
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict):
            continue
        key = attempt.get("key", {})
        metadata = attempt.get("metadata", {})
        condition = metadata.get("condition", {}) if isinstance(metadata, dict) else {}
        if isinstance(key, dict) and isinstance(condition, dict):
            conditions[str(key.get("condition_id"))] = condition
            pair_id = str(key.get("pair_id"))
            if pair_id not in pair_ids:
                pair_ids.append(pair_id)

    ledger_by_attempt = {str(row.get("attempt_id")): row for row in ledger}
    matrix_cells = []
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict):
            continue
        key = attempt.get("key", {})
        metadata = attempt.get("metadata", {})
        if not isinstance(key, dict) or not isinstance(metadata, dict):
            continue
        condition = metadata.get("condition", {})
        row = ledger_by_attempt.get(str(key.get("attempt_id")), {})
        matrix_cells.append(
            {
                "pair": str(key.get("pair_id")),
                "condition": str(condition.get("id", key.get("condition_id")))
                if isinstance(condition, dict)
                else str(key.get("condition_id")),
                "steps": condition.get("denoising_steps")
                if isinstance(condition, dict)
                else None,
                "success": row.get("success_count") == 1,
                "verified": row.get("evidence_verified") is True,
            }
        )

    contact_analyses = [
        episode.get("contact_analysis", {})
        for episode in robot_episodes
        if isinstance(episode.get("contact_analysis"), dict)
        and episode.get("contact_analysis")
    ]
    matrix_json = json.dumps(matrix_cells, separators=(",", ":")).replace("</", "<\\/")
    artifact_json = json.dumps(
        {
            "plan": plan,
            "ledger": ledger,
            "transfer": transfer,
            "robustness": robustness,
            "transport": robochallenge,
            "robot_run": robot_run,
            "robot_episodes": robot_episodes,
            "contact_analyses": contact_analyses,
            "robot_comparison": robot_comparison,
            "robot_policy": robot_policy,
            "robot_recovery": robot_recovery,
            "simulator_debug": simulator_debug,
        },
        separators=(",", ":"),
    ).replace("</", "<\\/")
    run_id = html.escape(str(plan.get("run_id", "BenchStudio demo")))
    plan_digest = _short(plan.get("plan_digest_sha256"), 16)
    transport_valid = robochallenge.get("valid") is True
    transport_events = int(robochallenge.get("event_count", 0) or 0)
    robot_episode_count = int(robot_run.get("episodes", 0) or 0)
    robot_summary = robot_comparison.get("summary", {})
    robot_backend_summary = (
        robot_summary.get(selected_simulator, {}) if isinstance(robot_summary, dict) else {}
    )
    robot_completed_episodes = (
        int(robot_backend_summary.get("completed", 0) or 0)
        if isinstance(robot_backend_summary, dict)
        else 0
    )
    robot_reports = [
        episode["report"]
        for episode in robot_episodes
        if isinstance(episode.get("report"), dict)
    ]
    robot_lift_passes = sum(report.get("success") is True for report in robot_reports)
    recovery_status = str(robot_recovery.get("status", "not_run"))
    recovery_episode_index = int(robot_recovery.get("episode_index", -1) or -1)
    recovery_attempts = robot_recovery.get("attempts", [])
    if not isinstance(recovery_attempts, list):
        recovery_attempts = []
    recovered_episode_count = 1 if recovery_status == "recovered" else 0
    robot_first_passes = robot_lift_passes
    robot_execution_count = robot_episode_count + len(recovery_attempts)
    robot_grasp_attach_used = any(
        report.get("grasp_attach_used") is True for report in robot_reports
    )
    robot_contact_evaluated = bool(contact_analyses) and all(
        isinstance(analysis.get("contact_model"), dict)
        and analysis["contact_model"].get("mode") == "physics_contact"
        and analysis["contact_model"].get("grasp_attach_used") is False
        for analysis in contact_analyses
    )
    contact_pass_count = sum(analysis.get("success") is True for analysis in contact_analyses)
    contact_failure_count = len(contact_analyses) - contact_pass_count
    robot_sim_time = (
        sum(float(report.get("sim_time_s", 0.0) or 0.0) for report in robot_reports)
        / len(robot_reports)
        if robot_reports
        else 0.0
    )
    robot_wall_time = (
        sum(float(report.get("wall_time_s", 0.0) or 0.0) for report in robot_reports)
        / len(robot_reports)
        if robot_reports
        else 0.0
    )
    robot_steps = sum(int(report.get("steps", 0) or 0) for report in robot_reports)
    robot_trace_records = 0
    for report in robot_reports:
        artifacts = report.get("artifacts", {})
        trace = artifacts.get("trace_ndjson", {}) if isinstance(artifacts, dict) else {}
        if isinstance(trace, dict):
            robot_trace_records += int(trace.get("record_count", 0) or 0)
    robot_environment = robot_report.get("environment", {})
    robot_packages = robot_environment.get("packages", {}) if isinstance(robot_environment, dict) else {}
    simulator_display_names = {"mujoco": "MuJoCo", "genesis": "Genesis"}
    simulator_name = simulator_display_names.get(
        selected_simulator, selected_simulator.replace("_", " ").title()
    )
    simulator_version = (
        str(robot_packages.get(selected_simulator, "not reported"))
        if isinstance(robot_packages, dict)
        else "not reported"
    )
    simulator_debug_backends = simulator_debug.get("backends", {})
    simulator_options_parts = []
    for simulator, display_name in simulator_display_names.items():
        debug_backend = (
            simulator_debug_backends.get(simulator, {})
            if isinstance(simulator_debug_backends, dict)
            else {}
        )
        status = str(debug_backend.get("status", "not_run")) if isinstance(debug_backend, dict) else "not_run"
        status_label = "run required" if status == "not_run" else status
        simulator_options_parts.append(
            f'<option value="{simulator}" '
            f'{"selected" if simulator == selected_simulator else "disabled"}>'
            f'{display_name} · {html.escape(status_label)}</option>'
        )
    simulator_options = "".join(simulator_options_parts)
    if robot_episodes:
        episode_cards = []
        for position, episode in enumerate(robot_episodes):
            episode_index = int(episode.get("episode_index", position))
            report = episode.get("report", {})
            manifest = episode.get("manifest", {})
            contact_analysis = episode.get("contact_analysis", {})
            placements = manifest.get("object_placements", {}) if isinstance(manifest, dict) else {}
            cube = placements.get("grasp_cube", {}) if isinstance(placements, dict) else {}
            cube_position = cube.get("position_xyz", []) if isinstance(cube, dict) else []
            cube_xy = "unreported"
            if isinstance(cube_position, list) and len(cube_position) >= 2:
                cube_xy = f"x {float(cube_position[0]):.3f} · y {float(cube_position[1]):+.3f} m"
            seed = manifest.get("seed", "—") if isinstance(manifest, dict) else "—"
            passed = report.get("success") is True if isinstance(report, dict) else False
            recovered = recovery_status == "recovered" and episode_index == recovery_episode_index
            failure_class = (
                str(contact_analysis.get("failure_class", "checker failure"))
                if isinstance(contact_analysis, dict)
                else "checker failure"
            )
            sim_time = float(report.get("sim_time_s", 0.0) or 0.0) if isinstance(report, dict) else 0.0
            autoplay = " autoplay" if position == 0 else ""
            episode_cards.append(
                '<article class="episode-card">'
                f'<video controls{autoplay} muted loop playsinline preload="metadata" '
                f'aria-label="SO-101 cube-lift episode {episode_index + 1}">'
                f'<source src="urdf-studio/{html.escape(selected_simulator)}/episode-{episode_index}/episode.mp4" '
                'type="video/mp4"></video>'
                '<div class="episode-meta">'
                f'<div><span>EPISODE {episode_index + 1:02d}</span><b>{"RECOVERED" if recovered else ("LIFT PASS" if passed else "CHECKER FAIL")}</b></div>'
                f'<div><span>SEED {html.escape(str(seed))}</span><small>{html.escape(cube_xy if passed else failure_class.replace("_", " "))}</small></div>'
                f'<time>{sim_time:.2f} s</time>'
                '</div></article>'
            )
        episode_media = f'<div class="episode-grid">{"".join(episode_cards)}</div>'
    else:
        episode_media = (
            '<div class="episode-empty">NO ROBOT EPISODE LOADED<br>'
            'Run scripts/demo_urdf_studio.sh first.</div>'
        )

    failure_analysis_panel = ""
    if contact_analyses:
        primary_analysis = next(
            (analysis for analysis in contact_analyses if analysis.get("success") is not True),
            contact_analyses[0],
        )
        primary_motion = primary_analysis.get("motion", {})
        primary_timeline = primary_analysis.get("timeline", {})
        primary_gripper = primary_analysis.get("gripper", {})
        primary_telemetry = primary_analysis.get("physics_contact_telemetry", {})
        if not isinstance(primary_motion, dict):
            primary_motion = {}
        if not isinstance(primary_timeline, dict):
            primary_timeline = {}
        if not isinstance(primary_gripper, dict):
            primary_gripper = {}
        if not isinstance(primary_telemetry, dict):
            primary_telemetry = {}
        primary_telemetry_capture = primary_telemetry.get("capture", {})
        primary_telemetry_contact = primary_telemetry.get("contact", {})
        primary_telemetry_equivalence = primary_telemetry.get("equivalence", {})
        primary_telemetry_capture = primary_telemetry_capture if isinstance(primary_telemetry_capture, dict) else {}
        primary_telemetry_contact = primary_telemetry_contact if isinstance(primary_telemetry_contact, dict) else {}
        primary_telemetry_equivalence = primary_telemetry_equivalence if isinstance(primary_telemetry_equivalence, dict) else {}

        failure_rows = []
        for position, analysis in enumerate(contact_analyses):
            motion = analysis.get("motion", {})
            timeline = analysis.get("timeline", {})
            gripper = analysis.get("gripper", {})
            telemetry = analysis.get("physics_contact_telemetry", {})
            motion = motion if isinstance(motion, dict) else {}
            timeline = timeline if isinstance(timeline, dict) else {}
            gripper = gripper if isinstance(gripper, dict) else {}
            telemetry = telemetry if isinstance(telemetry, dict) else {}
            telemetry_contact = telemetry.get("contact", {})
            telemetry_contact = telemetry_contact if isinstance(telemetry_contact, dict) else {}
            event_ms = timeline.get("first_contact_ms")
            event_kind = "contact"
            if event_ms is None:
                event_ms = motion.get("largest_frame_displacement_t_ms")
                event_kind = "impact window"
            event_text = "not retained" if event_ms is None else f"{float(event_ms) / 1000:.2f} s {event_kind}"
            displacement_mm = float(motion.get("horizontal_displacement_m", 0.0) or 0.0) * 1000
            max_lift_mm = float(motion.get("max_lift_m", 0.0) or 0.0) * 1000
            bilateral_frames = int(timeline.get("bilateral_contact_frames", 0) or 0)
            tracking_error = gripper.get("final_tracking_error_rad")
            tracking_text = "—" if tracking_error is None else f"{float(tracking_error):.3f} rad"
            peak_force = telemetry_contact.get("peak_normal_force_n")
            force_text = "—" if peak_force is None else f"{float(peak_force):.1f} N"
            failure_class = str(analysis.get("failure_class") or "passed").replace("_", " ")
            failure_rows.append(
                '<div class="failure-row">'
                f'<div><b>EP {int(analysis.get("episode_index", position)) + 1:02d}</b><span>seed {html.escape(str(analysis.get("seed", "—")))}</span></div>'
                f'<div><b>{html.escape(failure_class)}</b><span>{html.escape(event_text)}</span></div>'
                f'<div><b>{displacement_mm:.1f} mm</b><span>cube displacement</span></div>'
                f'<div><b>{max_lift_mm:.1f} mm</b><span>maximum lift</span></div>'
                f'<div><b>{bilateral_frames}</b><span>bilateral frames</span></div>'
                f'<div><b>{html.escape(force_text)}</b><span>peak normal force</span></div>'
                f'<div><b>{html.escape(tracking_text)}</b><span>closure error</span></div>'
                '</div>'
            )

        primary_event_ms = primary_timeline.get("first_contact_ms")
        if primary_event_ms is None:
            primary_event_ms = primary_motion.get("largest_frame_displacement_t_ms")
        primary_event = "not retained" if primary_event_ms is None else f"{float(primary_event_ms) / 1000:.2f} s"
        primary_displacement = float(primary_motion.get("horizontal_displacement_m", 0.0) or 0.0) * 1000
        primary_lift = float(primary_motion.get("max_lift_m", 0.0) or 0.0) * 1000
        primary_bilateral = int(primary_timeline.get("bilateral_contact_frames", 0) or 0)
        primary_tracking = primary_gripper.get("final_tracking_error_rad")
        primary_tracking_text = "—" if primary_tracking is None else f"{float(primary_tracking):.3f} rad"
        primary_peak_force = primary_telemetry_contact.get("peak_normal_force_n")
        primary_force_text = "—" if primary_peak_force is None else f"{float(primary_peak_force):.1f} N"
        primary_impulse = primary_telemetry_contact.get("normal_impulse_ns")
        primary_impulse_text = "—" if primary_impulse is None else f"{float(primary_impulse):.4f} N·s"
        primary_penetration = primary_telemetry_contact.get("maximum_penetration_m")
        primary_penetration_text = "—" if primary_penetration is None else f"{float(primary_penetration) * 1000:.2f} mm"
        sample_rate = primary_telemetry_capture.get("effective_sample_rate_hz")
        sample_rate_text = "50 Hz fallback" if sample_rate is None else f"{float(sample_rate) / 1000:.1f} kHz"
        equivalence_text = "VERIFIED" if primary_telemetry_equivalence.get("verified") is True else "NOT VERIFIED"
        primary_class = str(primary_analysis.get("failure_class") or "successful_contact_grasp").replace("_", " ")
        failure_analysis_panel = f'''
      <section class="failure-analysis" aria-label="Contact grasp failure analysis">
        <div class="failure-head"><div><div class="section-label">Root-cause analysis</div><h2>{contact_failure_count}/{len(contact_analyses)} grasps failed</h2><p class="section-copy">{html.escape(str(primary_analysis.get("explanation", "No explanation retained.")))}</p></div><span class="failure-badge">{html.escape(primary_class.upper())}</span></div>
        <div class="failure-kpis">
          <div><span>FAILURE WINDOW</span><b>{html.escape(primary_event)}</b></div>
          <div><span>CUBE DISPLACEMENT</span><b>{primary_displacement:.1f} mm</b></div>
          <div><span>MAXIMUM LIFT</span><b>{primary_lift:.1f} mm</b></div>
          <div><span>BILATERAL RETENTION</span><b>{primary_bilateral} frames</b></div>
          <div><span>CLOSURE ERROR</span><b>{html.escape(primary_tracking_text)}</b></div>
          <div><span>PEAK NORMAL FORCE</span><b>{html.escape(primary_force_text)}</b></div>
          <div><span>NORMAL IMPULSE</span><b>{html.escape(primary_impulse_text)}</b></div>
          <div><span>MAX PENETRATION</span><b>{html.escape(primary_penetration_text)}</b></div>
          <div><span>CONTACT CAPTURE</span><b>{html.escape(sample_rate_text)} · {equivalence_text}</b></div>
        </div>
        <div class="failure-table-head"><div>EPISODE</div><div>DIAGNOSIS / EVENT</div><div>DISPLACEMENT</div><div>LIFT</div><div>RETENTION</div><div>FORCE</div><div>TRACKING</div></div>
        {''.join(failure_rows)}
        <div class="failure-foot"><p>Evidence boundary: robot–cube contacts are retained at every {html.escape(sample_rate_text)} physics step with geom pairs, positions, contact frames, penetration, friction, solver force/torque, cube velocity, joint state, targets, and actuator forces. Solver evidence is accepted only when the replay matches the evaluated run; it is not a calibrated hardware-force measurement.</p><button class="artifact-button" data-artifact="contact_analyses">Inspect failure evidence</button></div>
      </section>'''

    recovery_panel = ""
    if recovery_status in {"recovered", "lift_still_failed"} and len(recovery_attempts) >= 2:
        failed_attempt = recovery_attempts[0] if isinstance(recovery_attempts[0], dict) else {}
        recovered_attempt = recovery_attempts[1] if isinstance(recovery_attempts[1], dict) else {}
        failed_files = failed_attempt.get("files", {}) if isinstance(failed_attempt, dict) else {}
        recovered_files = recovered_attempt.get("files", {}) if isinstance(recovered_attempt, dict) else {}
        failed_video = failed_files.get("episode.mp4", {}) if isinstance(failed_files, dict) else {}
        recovered_video = recovered_files.get("episode.mp4", {}) if isinstance(recovered_files, dict) else {}
        failed_video_path = str(failed_video.get("path", "")) if isinstance(failed_video, dict) else ""
        recovered_video_path = str(recovered_video.get("path", "")) if isinstance(recovered_video, dict) else ""
        intervention = robot_recovery.get("intervention", {})
        policy_binding = robot_recovery.get("policy_binding", {})
        baseline_policy_sha = str(policy_binding.get("failed_attempt_sha256", "unbound"))[:8] if isinstance(policy_binding, dict) else "unbound"
        intervention_policy_sha = str(policy_binding.get("recovered_attempt_sha256", "unbound"))[:8] if isinstance(policy_binding, dict) else "unbound"
        baseline_value = intervention.get("baseline_value", "—") if isinstance(intervention, dict) else "—"
        intervention_value = intervention.get("intervention_value", "—") if isinstance(intervention, dict) else "—"
        intervention_unit = intervention.get("unit", "") if isinstance(intervention, dict) else ""
        recovery_succeeded = recovered_attempt.get("success") is True
        recovery_state_label = "LIFT RECOVERED" if recovery_succeeded else "LIFT STILL FAILED"
        recovery_result_label = "LIFT CHECKER PASS" if recovery_succeeded else str(
            recovered_attempt.get("stop_reason", "checker fail")
        ).replace("_", " ").upper()
        intervention_effect = robot_recovery.get("effect", {})
        intervention_effect = intervention_effect if isinstance(intervention_effect, dict) else {}
        force_effect = intervention_effect.get("peak_normal_force_n", {})
        displacement_effect = intervention_effect.get("horizontal_displacement_m", {})
        force_effect = force_effect if isinstance(force_effect, dict) else {}
        displacement_effect = displacement_effect if isinstance(displacement_effect, dict) else {}
        baseline_force = force_effect.get("baseline")
        changed_force = force_effect.get("intervention")
        baseline_displacement = displacement_effect.get("baseline")
        changed_displacement = displacement_effect.get("intervention")
        force_comparison = "—" if baseline_force is None or changed_force is None else f"{float(baseline_force):.1f} → {float(changed_force):.1f} N peak"
        displacement_comparison = "—" if baseline_displacement is None or changed_displacement is None else f"{float(baseline_displacement) * 1000:.1f} → {float(changed_displacement) * 1000:.1f} mm displacement"
        recovery_panel = f'''
      <section class="recovery-panel" aria-label="Causal intervention evidence">
        <div class="recovery-head"><div><div class="section-label">Causal intervention</div><h2>Episode {recovery_episode_index + 1:02d} · Baseline vs slower approach</h2><p class="section-copy">Same seed, cube pose, simulator, checker, and geometry. The intervention changes only approach duration to test whether lower approach velocity reduces the pre-close collision.</p></div><span class="recovery-state {'passed' if recovery_succeeded else 'failed'}">{recovery_state_label}</span></div>
        <div class="recovery-flow">
          <article class="recovery-attempt failed"><video controls muted playsinline preload="metadata"><source src="urdf-studio/{html.escape(failed_video_path)}" type="video/mp4"></video><div><span>ATTEMPT 01 · BASELINE</span><b>{html.escape(str(failed_attempt.get("stop_reason", "failed")).replace("_", " ").upper())}</b><small>{failed_attempt.get("steps", "—")} steps · {float(failed_attempt.get("sim_time_s", 0.0) or 0.0):.2f} s</small></div></article>
          <div class="recovery-change"><span>APPROACH DURATION</span><strong>{html.escape(str(baseline_value))} → {html.escape(str(intervention_value))} {html.escape(str(intervention_unit))}</strong><small>single policy parameter<br>{html.escape(baseline_policy_sha)} → {html.escape(intervention_policy_sha)}</small></div>
          <article class="recovery-attempt {'passed' if recovery_succeeded else 'failed'}"><video controls muted playsinline preload="metadata"><source src="urdf-studio/{html.escape(recovered_video_path)}" type="video/mp4"></video><div><span>ATTEMPT 02 · INTERVENTION</span><b>{html.escape(recovery_result_label)}</b><small>{recovered_attempt.get("steps", "—")} steps · {float(recovered_attempt.get("sim_time_s", 0.0) or 0.0):.2f} s</small></div></article>
        </div>
        <div class="recovery-foot"><span>SEED {html.escape(str(robot_recovery.get("seed", "—")))}</span><span>{html.escape(force_comparison)}</span><span>{html.escape(displacement_comparison)}</span><button class="artifact-button" data-artifact="robot_recovery">Inspect intervention evidence</button></div>
      </section>'''

    debug_backends = simulator_debug.get("backends", {})
    debug_shared = simulator_debug.get("shared_parameters", {})
    debug_digests = simulator_debug.get("input_digests", {})

    def backend_value(backend_id: str, key: str, default: str = "—") -> str:
        backend = debug_backends.get(backend_id, {}) if isinstance(debug_backends, dict) else {}
        if not isinstance(backend, dict):
            return default
        value = backend.get(key)
        if value is None:
            return default
        return str(value)

    def rate_value(backend_id: str) -> str:
        raw = backend_value(backend_id, "success_rate")
        if raw == "—":
            return raw
        return f"{float(raw) * 100:.0f}%"

    def seconds_value(backend_id: str, key: str) -> str:
        raw = backend_value(backend_id, key)
        if raw == "—":
            return raw
        return f"{float(raw):.2f} s"

    def backend_error(backend_id: str) -> str:
        backend = debug_backends.get(backend_id, {}) if isinstance(debug_backends, dict) else {}
        errors = backend.get("errors", []) if isinstance(backend, dict) else []
        if isinstance(errors, list) and errors:
            return str(errors[0]).splitlines()[-1][:120]
        return "none"

    debug_rows = [
        ("Run status", "shared inputs", backend_value("mujoco", "status"), backend_value("genesis", "status")),
        ("Engine package", "—", backend_value("mujoco", "package_version", "available"), backend_value("genesis", "package_version", "unavailable")),
        ("Episodes", str(debug_shared.get("episodes", "—")), f'{backend_value("mujoco", "completed")}/{backend_value("mujoco", "episodes")}', f'{backend_value("genesis", "completed")}/{backend_value("genesis", "episodes")}'),
        ("Lift checker pass rate", "same checker", rate_value("mujoco"), rate_value("genesis")),
        ("Mean sim time", "same timeout", seconds_value("mujoco", "mean_sim_time_s"), seconds_value("genesis", "mean_sim_time_s")),
        ("Mean wall time", "host measured", seconds_value("mujoco", "mean_wall_time_s"), seconds_value("genesis", "mean_wall_time_s")),
        ("Backend error", "—", backend_error("mujoco"), backend_error("genesis")),
    ]
    debug_rows_html = "".join(
        "<div class=\"debug-row\">"
        + "".join(f"<div>{html.escape(value)}</div>" for value in row)
        + "</div>"
        for row in debug_rows
    )
    shared_parameters = [
        ("PHYSICS STEP", f'{debug_shared.get("physics_timestep_s", "—")} s'),
        ("CONTROL", f'{debug_shared.get("control_hz", "—")} Hz'),
        ("CHECKER", f'every {debug_shared.get("checker_interval_steps", "—")} steps'),
        ("MAX STEPS", str(debug_shared.get("max_episode_steps", "—"))),
        (
            "ATTACH",
            "disabled"
            if debug_shared.get("grasp_attach") == "none"
            else f'{debug_shared.get("grasp_attach", "—")} → {debug_shared.get("attach_link") or "—"}',
        ),
    ]
    shared_parameters_html = "".join(
        f'<div><span>{label}</span><b>{html.escape(value)}</b></div>'
        for label, value in shared_parameters
    )
    input_bindings_html = " · ".join(
        f'{name.removesuffix("_sha256")} {str(value)[:10]}'
        for name, value in debug_digests.items()
    ) if isinstance(debug_digests, dict) else "not loaded"

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#191919">
  <title>BenchStudio — Evaluation report</title>
  <style>
    :root {{ color-scheme: dark; --bg:#191919; --surface:#1f1f1f; --raised:#252525; --line:#353535; --text:#f4f4f4; --muted:#9c9c9c; --pink:#ff4fba; --ok:#afd6c4; --warn:#d8b27d; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Noto Sans", Arial, sans-serif; font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased; }}
    .mono, .tag, .metric-label, .matrix-label, code, summary {{ font-family:"Noto Sans Mono", monospace; }}
    .shell {{ width:min(1160px, calc(100% - 40px)); margin:auto; padding:22px 0 56px; }}
    header {{ display:flex; justify-content:space-between; align-items:center; padding:0 0 18px; border-bottom:1px solid var(--line); }}
    .brand {{ display:flex; align-items:center; gap:10px; font-size:15px; font-weight:600; }}
    .mark {{ width:14px; height:14px; border-radius:4px; background:var(--pink); }}
    .brand span:last-child {{ color:var(--muted); font-weight:400; }}
    .tag {{ color:#cfcfcf; border:1px solid var(--line); border-radius:5px; padding:5px 8px; font-size:10px; letter-spacing:.04em; }}
    .run-context {{ display:grid; grid-template-columns:1.5fr 1fr 1fr; border:1px solid var(--line); border-radius:10px; overflow:hidden; margin:18px 0; }}
    .run-context div {{ padding:14px 18px; background:var(--surface); border-right:1px solid var(--line); min-width:0; }} .run-context div:last-child {{ border:0; }}
    .run-context span {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; letter-spacing:.08em; }}
    .run-context b {{ display:block; margin-top:7px; overflow:hidden; text-overflow:ellipsis; color:#c8c8c8; font:500 11px/1.4 "Noto Sans Mono",monospace; white-space:nowrap; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; }}
    .campaign-scope {{ display:flex; justify-content:space-between; align-items:end; gap:20px; margin:22px 2px 9px; }}
    .campaign-scope p {{ margin:0; color:#777; font-size:10px; }}
    .metric {{ padding:18px 20px; background:var(--surface); border-right:1px solid var(--line); }}
    .metric:last-child {{ border-right:0; }}
    .metric-label {{ display:block; color:var(--muted); font-size:9px; letter-spacing:.08em; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:8px; font-size:27px; line-height:1; letter-spacing:-.035em; font-weight:500; }}
    .robot-run {{ display:grid; grid-template-columns:1.35fr .65fr; border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; background:var(--surface); }}
    .sim-debug {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; background:var(--surface); }}
    .sim-debug-head {{ display:flex; justify-content:space-between; gap:24px; padding:24px; border-bottom:1px solid var(--line); }}
    .sim-debug-head h2 {{ margin-bottom:4px; }}
    .shared-params {{ display:grid; grid-template-columns:repeat(5,1fr); border-bottom:1px solid var(--line); }}
    .shared-params div {{ padding:14px 16px; border-right:1px solid var(--line); }} .shared-params div:last-child {{ border:0; }}
    .shared-params span {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; }} .shared-params b {{ display:block; margin-top:7px; color:#ccc; font:500 10px/1.4 "Noto Sans Mono",monospace; }}
    .debug-row {{ display:grid; grid-template-columns:1.05fr .9fr 1fr 1fr; border-bottom:1px solid var(--line); }} .debug-row:last-child {{ border:0; }}
    .debug-row div {{ min-width:0; padding:11px 14px; border-right:1px solid var(--line); color:#aaa; font:10px/1.45 "Noto Sans Mono",monospace; overflow-wrap:anywhere; }} .debug-row div:last-child {{ border:0; }}
    .debug-row.header div {{ color:#ddd; background:var(--raised); font-weight:600; }}
    .debug-bindings {{ padding:12px 16px; border-top:1px solid var(--line); color:#777; font:9px/1.5 "Noto Sans Mono",monospace; }}
    .episode-view {{ min-height:390px; background:#111; border-right:1px solid var(--line); }}
    .episode-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:1px; width:100%; height:100%; background:var(--line); }}
    .episode-card {{ min-width:0; background:#111; }}
    .episode-card video {{ display:block; width:100%; aspect-ratio:16/9; object-fit:contain; background:#0b0b0b; }}
    .episode-meta {{ display:grid; grid-template-columns:1fr 1.2fr auto; gap:10px; align-items:center; padding:10px 12px; border-top:1px solid #292929; }}
    .episode-meta span,.episode-meta small {{ display:block; color:#777; font:8px/1.4 "Noto Sans Mono",monospace; }}
    .episode-meta b {{ display:block; margin-top:3px; color:var(--ok); font:500 10px/1.3 "Noto Sans Mono",monospace; }}
    .episode-meta time {{ color:#aaa; font:9px/1 "Noto Sans Mono",monospace; white-space:nowrap; }}
    .episode-empty {{ color:#777; font:11px/1.6 "Noto Sans Mono",monospace; text-align:center; padding:40px; }}
    .run-config {{ padding:24px; }}
    .run-config h2 {{ margin-bottom:22px; }}
    .field {{ margin-bottom:16px; }} .field label {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; letter-spacing:.08em; margin-bottom:7px; }}
    .field-help {{ display:block; margin-top:7px; color:#777; font-size:10px; line-height:1.45; }}
    .field select,.field-output {{ width:100%; border:1px solid var(--line); border-radius:6px; background:var(--raised); color:#ddd; padding:9px 10px; font:11px/1.3 "Noto Sans Mono",monospace; }}
    .policy-timeline {{ margin:-8px 0 16px; color:#999; font:10px/1.6 "Noto Sans Mono",monospace; }}
    .run-result {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:22px; }}
    .run-result div {{ padding:12px; border:1px solid var(--line); border-radius:6px; background:var(--raised); }}
    .run-result span {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; }} .run-result b {{ display:block; margin-top:7px; font-size:13px; font-weight:500; }}
    .truth-note {{ margin:16px 0 0; padding-top:14px; border-top:1px solid var(--line); color:var(--muted); font-size:11px; line-height:1.55; }}
    .failure-analysis {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; background:var(--surface); }}
    .failure-head {{ display:flex; justify-content:space-between; align-items:start; gap:24px; padding:24px; border-bottom:1px solid var(--line); }}
    .failure-head h2 {{ margin-bottom:5px; }}
    .failure-badge {{ max-width:230px; color:var(--warn); border:1px solid #66533d; border-radius:5px; padding:7px 9px; font:9px/1.35 "Noto Sans Mono",monospace; letter-spacing:.05em; text-align:right; }}
    .failure-kpis {{ display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid var(--line); }}
    .failure-kpis div {{ padding:16px; border-right:1px solid var(--line); }} .failure-kpis div:last-child {{ border:0; }}
    .failure-kpis span,.failure-table-head div {{ display:block; color:#777; font:9px/1.35 "Noto Sans Mono",monospace; }}
    .failure-kpis b {{ display:block; margin-top:8px; color:#ddd; font:500 16px/1.2 "Noto Sans Mono",monospace; }}
    .failure-table-head,.failure-row {{ display:grid; grid-template-columns:.5fr 1.65fr repeat(5,.8fr); }}
    .failure-table-head {{ background:var(--raised); border-bottom:1px solid var(--line); }}
    .failure-table-head div,.failure-row > div {{ min-width:0; padding:10px 12px; border-right:1px solid var(--line); }} .failure-table-head div:last-child,.failure-row > div:last-child {{ border:0; }}
    .failure-row {{ border-bottom:1px solid var(--line); }}
    .failure-row b,.failure-row span {{ display:block; overflow-wrap:anywhere; }}
    .failure-row b {{ color:#bbb; font:500 10px/1.45 "Noto Sans Mono",monospace; }} .failure-row span {{ margin-top:3px; color:#747474; font:9px/1.4 "Noto Sans Mono",monospace; }}
    .failure-row > div:nth-child(2) b {{ color:var(--warn); }}
    .failure-foot {{ display:flex; align-items:center; justify-content:space-between; gap:24px; padding:13px 16px; }} .failure-foot p {{ max-width:820px; margin:0; color:#858585; font-size:10px; line-height:1.5; }}
    .recovery-panel {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; background:var(--surface); }}
    .recovery-head {{ display:flex; justify-content:space-between; align-items:start; gap:20px; padding:22px 24px; border-bottom:1px solid var(--line); }}
    .recovery-head h2 {{ margin-bottom:4px; }}
    .recovery-state {{ border-radius:5px; padding:6px 9px; font:9px/1 "Noto Sans Mono",monospace; letter-spacing:.06em; }} .recovery-state.passed {{ color:var(--ok); border:1px solid #466056; }} .recovery-state.failed {{ color:var(--warn); border:1px solid #66533d; }}
    .recovery-flow {{ display:grid; grid-template-columns:1fr 170px 1fr; align-items:stretch; background:#111; }}
    .recovery-attempt {{ min-width:0; }}
    .recovery-attempt video {{ display:block; width:100%; aspect-ratio:16/9; object-fit:contain; background:#090909; }}
    .recovery-attempt > div {{ padding:12px 14px; border-top:1px solid var(--line); }}
    .recovery-attempt span,.recovery-attempt small,.recovery-change span,.recovery-change small {{ display:block; color:#777; font:9px/1.45 "Noto Sans Mono",monospace; }}
    .recovery-attempt b {{ display:block; margin:5px 0 3px; font:500 12px/1.3 "Noto Sans Mono",monospace; }}
    .recovery-attempt.failed b {{ color:var(--warn); }} .recovery-attempt.passed b {{ color:var(--ok); }}
    .recovery-change {{ display:grid; place-content:center; text-align:center; padding:20px; border-left:1px solid var(--line); border-right:1px solid var(--line); background:#171717; }}
    .recovery-change strong {{ display:block; margin:12px 0 9px; color:#ddd; font:500 24px/1 "Noto Sans Mono",monospace; }}
    .recovery-foot {{ display:flex; align-items:center; flex-wrap:wrap; gap:22px; padding:12px 16px; border-top:1px solid var(--line); color:#888; font:9px/1.4 "Noto Sans Mono",monospace; }}
    .recovery-foot button {{ margin-left:auto; }}
    .story {{ display:grid; grid-template-columns:1.4fr .8fr; border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; background:var(--surface); }}
    .transfer {{ padding:28px; border-right:1px solid var(--line); }}
    .section-label {{ color:var(--muted); font:500 10px/1.2 "Noto Sans Mono", monospace; letter-spacing:.08em; text-transform:uppercase; }}
    h2 {{ margin:10px 0 6px; font-size:22px; letter-spacing:-.025em; font-weight:500; }}
    .section-copy {{ color:var(--muted); margin:0; font-size:13px; }}
    .gap {{ margin:34px 0 28px; font-size:clamp(64px,10vw,112px); line-height:.82; letter-spacing:-.07em; font-weight:500; }}
    .gap span {{ color:var(--muted); font-size:16px; letter-spacing:0; margin-left:8px; }}
    .bars {{ display:grid; gap:14px; }}
    .bar {{ display:grid; grid-template-columns:135px 1fr 42px; align-items:center; gap:14px; }}
    .bar label {{ color:#bcbcbc; font-size:12px; }}
    .track {{ height:7px; border-radius:9px; background:#303030; overflow:hidden; }}
    .fill {{ height:100%; background:var(--pink); }}
    .fill.boundary {{ background:#666; }}
    .bar b {{ font:500 11px/1 "Noto Sans Mono", monospace; text-align:right; }}
    .claim {{ padding:28px; display:flex; flex-direction:column; }}
    .claim h2 {{ margin-bottom:24px; }}
    .decision {{ padding:15px 0; border-top:1px solid var(--line); }}
    .decision:first-of-type {{ border-top:0; padding-top:0; }}
    .decision b {{ display:block; font-size:13px; font-weight:500; }}
    .decision span {{ display:block; color:var(--muted); font-size:12px; margin-top:4px; }}
    .supported b::before {{ content:"✓"; color:var(--ok); margin-right:8px; }}
    .unsupported b::before {{ content:"—"; color:var(--warn); margin-right:8px; }}
    .panel {{ padding:26px 28px; border:1px solid var(--line); border-radius:10px; background:var(--surface); margin-bottom:18px; }}
    .panel-head {{ display:flex; justify-content:space-between; gap:20px; align-items:start; margin-bottom:22px; }}
    .panel-head h2 {{ margin-top:0; }}
    .matrix {{ display:grid; gap:6px; }}
    .matrix-row {{ display:grid; grid-template-columns:120px repeat(2,minmax(0,1fr)); gap:6px; }}
    .matrix-label {{ color:#858585; font-size:9px; letter-spacing:.05em; display:flex; align-items:center; }}
    .matrix-cell {{ min-height:64px; padding:12px; border:1px solid var(--line); border-radius:7px; background:var(--raised); display:flex; justify-content:space-between; align-items:end; }}
    .matrix-cell strong {{ font-size:12px; font-weight:500; }} .matrix-cell small {{ color:#888; font-size:10px; }}
    .check {{ color:var(--ok); }}
    .evidence {{ display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); border-radius:8px; overflow:hidden; margin-top:20px; }}
    .evidence div {{ padding:15px; background:var(--raised); border-right:1px solid var(--line); }} .evidence div:last-child {{ border:0; }}
    .evidence span {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; }}
    .evidence b {{ display:block; margin:9px 0 4px; font-size:12px; font-weight:500; }} .evidence small {{ color:#858585; font:9px/1.4 "Noto Sans Mono",monospace; }}
    .links {{ display:flex; flex-wrap:wrap; gap:18px; margin-top:18px; }}
    .artifact-button {{ appearance:none; border:0; border-bottom:1px solid #555; background:none; color:#aaa; padding:3px 0; font:11px/1.4 "Noto Sans",Arial,sans-serif; cursor:pointer; }} .artifact-button:hover {{ color:#fff; border-color:var(--pink); }}
    details {{ border:1px solid var(--line); border-radius:10px; background:var(--surface); margin-bottom:18px; }}
    summary {{ cursor:pointer; padding:17px 20px; color:#aaa; font-size:10px; letter-spacing:.04em; }}
    .json-panel {{ margin:0 20px 20px; padding:17px; border:1px solid var(--line); border-radius:7px; background:#171717; overflow:auto; }}
    .json-panel code {{ color:#c8c8c8; font-size:11px; line-height:1.8; white-space:pre; }}
    .json-key {{ color:#d98ab9; }} .json-string {{ color:#b8aec4; }} .json-number {{ color:#a5bdc5; }} .json-ok {{ color:var(--ok); }}
    dialog {{ width:min(820px,calc(100% - 32px)); max-height:82vh; padding:0; color:var(--text); background:var(--surface); border:1px solid #444; border-radius:10px; }}
    dialog::backdrop {{ background:rgba(0,0,0,.72); }}
    .dialog-head {{ display:flex; justify-content:space-between; align-items:center; padding:16px 18px; border-bottom:1px solid var(--line); }}
    .dialog-head strong {{ font-size:13px; font-weight:500; }} .dialog-head span {{ display:block; color:var(--muted); font:9px/1.4 "Noto Sans Mono",monospace; margin-top:3px; }}
    .close {{ appearance:none; border:1px solid var(--line); border-radius:5px; background:var(--raised); color:#bbb; padding:6px 9px; cursor:pointer; }}
    #artifact-content {{ margin:0; padding:20px; overflow:auto; color:#c8c8c8; font:11px/1.7 "Noto Sans Mono",monospace; white-space:pre-wrap; word-break:break-word; }}
    footer {{ display:flex; justify-content:space-between; gap:20px; color:#707070; border-top:1px solid var(--line); padding-top:18px; font-size:10px; }}
    @media(max-width:800px) {{ .robot-run,.story {{ grid-template-columns:1fr; }} .episode-view,.transfer {{ border-right:0; border-bottom:1px solid var(--line); }} .recovery-flow {{ grid-template-columns:1fr; }} .recovery-change {{ border:0; border-top:1px solid var(--line); border-bottom:1px solid var(--line); }} .metrics {{ grid-template-columns:1fr 1fr; }} .metric:nth-child(2) {{ border-right:0; }} .metric:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }} .evidence {{ grid-template-columns:1fr 1fr; }} .evidence div:nth-child(2) {{ border-right:0; }} .evidence div:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }} .shared-params {{ grid-template-columns:1fr 1fr; }} .debug-row {{ grid-template-columns:90px repeat(3,minmax(120px,1fr)); }} .sim-debug {{ overflow-x:auto; }} .failure-kpis {{ grid-template-columns:repeat(2,1fr); }} .failure-table-head {{ display:none; }} .failure-row {{ grid-template-columns:repeat(3,1fr); }} .failure-head,.failure-foot {{ align-items:start; flex-direction:column; }} }}
    @media(max-width:560px) {{ .shell {{ width:calc(100% - 24px); }} .run-context {{ grid-template-columns:1fr; }} .run-context div {{ border-right:0; border-bottom:1px solid var(--line); }} .episode-grid {{ grid-template-columns:1fr; }} .matrix-row {{ grid-template-columns:76px repeat(2,1fr); }} .bar {{ grid-template-columns:100px 1fr 36px; }} footer {{ flex-direction:column; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <header><div class="brand"><span class="mark"></span>BenchStudio <span>/ Eval Control Room</span></div><span class="mono" style="color:#777;font-size:10px">CAMPAIGN FIXTURE · {scheduled} ATTEMPTS · {matched_pairs} TRANSFER PAIRS</span></header>

    <main>
      <section class="run-context" aria-label="Run identity">
        <div><span>RUN</span><b>{run_id}</b></div>
        <div><span>MODE</span><b>CONTROLLED COMPARISON</b></div>
        <div><span>PLAN</span><b>{plan_digest}</b></div>
      </section>

      <section class="robot-run" aria-label="URDF Studio robot evaluation">
        <div class="episode-view">{episode_media}</div>
        <aside class="run-config">
          <div class="section-label">URDF Studio execution</div>
          <h2>SO-101 · Cube lift</h2>
          <div class="field"><label for="simulator-select">SIMULATOR</label><select id="simulator-select" aria-describedby="simulator-help">{simulator_options}</select><small id="simulator-help" class="field-help">Choose the backend before the run; this report stays bound to the evaluated episode batch.</small></div>
          <div class="field"><label>ROBOT SOURCE</label><div class="field-output">URDF Studio / SO-101</div></div>
          <div class="field"><label>POLICY</label><div class="field-output">Waypoint baseline · sha256 {html.escape(robot_policy_digest[:12])}</div></div>
          <div class="policy-timeline">{html.escape(robot_policy_timeline)}</div>
          <div class="run-result">
            <div><span>FINAL RESULT</span><b>{robot_lift_passes}/{robot_episode_count} LIFT CHECKER PASS</b></div>
            <div><span>CONTACT GRASP</span><b>{'PHYSICS EVALUATED' if robot_contact_evaluated else ('KINEMATIC ATTACH' if robot_grasp_attach_used else 'NOT EVALUATED')}</b></div>
            <div><span>ROBOT EPISODES</span><b>{robot_completed_episodes}/{robot_episode_count} {'COMPLETED' if robot_completed_episodes else 'NOT RUN'}</b></div>
            <div><span>FIRST-PASS RATE</span><b>{robot_first_passes}/{robot_episode_count}</b></div>
            <div><span>INTERVENTION</span><b>{'1 EVALUATED' if recovery_attempts else 'NOT RUN'}</b></div>
            <div><span>EXECUTIONS</span><b>{robot_execution_count} TOTAL</b></div>
          </div>
          <p class="truth-note">{html.escape(simulator_name)} {html.escape(simulator_version)} · mean wall time {robot_wall_time:.2f} s. The batch varies the cube pose under frozen seeds and one frozen policy. Exact finger-mesh collisions participate in MuJoCo contact; no attach or weld event is permitted. Physics-step diagnostic replay retains solver force/torque, impulse, penetration, cube velocity, and controller state and is accepted only after deterministic equivalence verification.</p>
          <div class="links"><button class="artifact-button" data-artifact="robot_policy">Inspect policy</button><button class="artifact-button" data-artifact="robot_episodes">Inspect episode evidence</button><button class="artifact-button" data-artifact="robot_comparison">Inspect comparison</button></div>
        </aside>
      </section>

      {failure_analysis_panel}

      {recovery_panel}

      <section class="sim-debug" aria-label="Simulator parameter debugger">
        <div class="sim-debug-head"><div><div class="section-label">Cross-simulator debugging</div><h2>Simulator parameter matrix</h2><p class="section-copy">Shared inputs stay frozen; backend status and outcomes remain visibly separate.</p></div><button class="artifact-button" data-artifact="simulator_debug">Inspect debug manifest</button></div>
        <div class="shared-params">{shared_parameters_html}</div>
        <div class="debug-row header"><div>PARAMETER</div><div>SHARED CONTRACT</div><div>MUJOCO</div><div>GENESIS</div></div>
        {debug_rows_html}
        <div class="debug-bindings">INPUT BINDINGS · {html.escape(input_bindings_html)}</div>
      </section>

      <div class="campaign-scope"><div class="section-label">Frozen campaign fixture</div><p>Separate accounting fixture; not additional SO-101 videos.</p></div>
      <section class="metrics" aria-label="Campaign integrity">
        <div class="metric"><span class="metric-label">Attempts scheduled</span><strong>{scheduled}</strong></div>
        <div class="metric"><span class="metric-label">Attempts completed</span><strong>{completed}/{scheduled}</strong></div>
        <div class="metric"><span class="metric-label">Attempt evidence verified</span><strong>{evidence_rate}%</strong></div>
        <div class="metric"><span class="metric-label">Attempt outcomes missing</span><strong>{missing}</strong></div>
      </section>

      <section class="story">
        <article class="transfer">
          <div class="section-label">Primary result</div>
          <h2>Transfer fidelity</h2>
          <p class="section-copy">Matched outcomes across the simulation and boundary fixtures.</p>
          <div class="gap">{gap:+d}<span>percentage points</span></div>
          <div class="bars">
            <div class="bar"><label>Simulation fixture</label><div class="track"><div class="fill" style="width:{simulation_rate}%"></div></div><b>{simulation_rate}%</b></div>
            <div class="bar"><label>Boundary fixture</label><div class="track"><div class="fill boundary" style="width:{boundary_rate}%"></div></div><b>{boundary_rate}%</b></div>
          </div>
        </article>
        <aside class="claim">
          <div class="section-label">Claim boundary</div>
          <h2>What the evidence permits</h2>
          <div class="decision supported"><b>Campaign integrity</b><span>All frozen attempts are terminal and accounted for.</span></div>
          <div class="decision supported"><b>Evidence integrity</b><span>Every committed result passed local verification.</span></div>
          <div class="decision supported"><b>Contact-grasp execution</b><span>Evaluated with collision response and no attachment shortcut.</span></div>
          <div class="decision supported"><b>Simulator contact diagnostics</b><span>Physics-step solver forces, impulses, penetration, and controller state are retained with replay equivalence checks.</span></div>
          <div class="decision unsupported"><b>Hardware force calibration</b><span>Not established; MuJoCo solver forces are not physical sensor measurements.</span></div>
          <div class="decision unsupported"><b>Real-world transfer</b><span>Not supported by this deterministic fixture.</span></div>
          <div class="decision unsupported"><b>Model quality</b><span>No model-performance claim is made.</span></div>
        </aside>
      </section>

      <section class="panel">
        <div class="panel-head"><div><div class="section-label">Experiment design</div><h2>Paired attempts</h2><p class="section-copy">The same initial states were evaluated under both inference budgets.</p></div><span class="tag">2 × 2</span></div>
        <div id="matrix" class="matrix" aria-label="Paired attempt matrix"></div>
      </section>

      <section class="panel">
        <div class="section-label">Reproducibility</div><h2>Evidence chain</h2>
        <div class="evidence">
          <div><span>01</span><b>Frozen plan</b><small>{plan_digest}</small></div>
          <div><span>02</span><b>Attempt ledger</b><small>{len(ledger)} terminal rows</small></div>
          <div><span>03</span><b>Counterfactual branches</b><small>{complete_branches}/{branches} complete</small></div>
          <div><span>04</span><b>Transport audit</b><small>{transport_events} events · {'valid' if transport_valid else 'invalid'}</small></div>
        </div>
        <div class="links"><button class="artifact-button" data-artifact="plan">Inspect frozen plan</button><button class="artifact-button" data-artifact="ledger">Inspect attempt ledger</button><button class="artifact-button" data-artifact="transfer">Inspect transfer report</button><button class="artifact-button" data-artifact="robustness">Inspect robustness report</button><button class="artifact-button" data-artifact="transport">Inspect transport audit</button></div>
      </section>

      <details>
        <summary>VIEW MACHINE-READABLE SUMMARY</summary>
        <div class="json-panel"><code>{{
  <span class="json-key">"campaign.status"</span>: <span class="json-string">"complete"</span>,
  <span class="json-key">"attempts.scheduled"</span>: <span class="json-number">{scheduled}</span>,
  <span class="json-key">"attempts.committed"</span>: <span class="json-number">{completed}</span>,
  <span class="json-key">"evidence.verified"</span>: <span class="json-number">{evidence_verified}</span>,
  <span class="json-key">"transport.valid"</span>: <span class="json-ok">{str(transport_valid).lower()}</span>,
  <span class="json-key">"claim.verdict"</span>: <span class="json-string">"qualified"</span>
}}</code></div>
      </details>
    </main>

    <footer><span>BenchStudio · independent evaluation infrastructure for embodied AI</span><span>Model-agnostic · benchmark-agnostic · evidence-first</span></footer>
  </div>
  <dialog id="artifact-dialog" aria-labelledby="artifact-title">
    <div class="dialog-head"><div><strong id="artifact-title">Evidence artifact</strong><span>READ-ONLY · GENERATED FROM THIS RUN</span></div><button class="close" type="button" aria-label="Close evidence inspector">Close</button></div>
    <pre id="artifact-content"></pre>
  </dialog>
  <script>
    const cells = {matrix_json};
    const artifacts = {artifact_json};
    const artifactTitles = {{plan:'Frozen campaign plan',ledger:'Attempt ledger',transfer:'Transfer fidelity report',robustness:'Counterfactual robustness report',transport:'RoboChallenge transport audit',robot_policy:'SO-101 waypoint policy',robot_episodes:'SO-101 episode batch evidence',contact_analyses:'Contact-grasp failure analyses',robot_recovery:'SO-101 causal intervention evidence',robot_comparison:'URDF Studio comparison report',simulator_debug:'Simulator debug manifest'}};
    const pairs = [...new Set(cells.map(c => c.pair))];
    const conditions = [...new Set(cells.map(c => c.condition))];
    const matrix = document.getElementById('matrix');
    const head = document.createElement('div'); head.className = 'matrix-row';
    head.innerHTML = '<div class="matrix-label">INITIAL STATE</div>' + conditions.map(c => `<div class="matrix-label">${{c.replaceAll('_',' ').toUpperCase()}}</div>`).join(''); matrix.appendChild(head);
    pairs.forEach((pair, index) => {{ const row = document.createElement('div'); row.className = 'matrix-row'; row.innerHTML = `<div class="matrix-label">PAIR ${{String(index + 1).padStart(2,'0')}}</div>` + conditions.map(condition => {{ const cell = cells.find(c => c.pair === pair && c.condition === condition); return `<div class="matrix-cell"><div><strong>${{cell?.steps ?? '—'}} denoise steps</strong><br><small>${{cell?.verified ? 'verified' : 'unverified'}}</small></div><span class="check">${{cell?.success ? '✓' : '—'}}</span></div>`; }}).join(''); matrix.appendChild(row); }});
    const dialog = document.getElementById('artifact-dialog');
    document.querySelectorAll('[data-artifact]').forEach(button => button.addEventListener('click', () => {{ const key=button.dataset.artifact; document.getElementById('artifact-title').textContent=artifactTitles[key]; document.getElementById('artifact-content').textContent=JSON.stringify(artifacts[key],null,2); dialog.showModal(); }}));
    dialog.querySelector('.close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {{ if(event.target===dialog) dialog.close(); }});
  </script>
</body>
</html>
"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Demo evidence directory")
    parser.add_argument("--output", type=Path, required=True, help="Output HTML path")
    args = parser.parse_args()
    path = build_demo_dashboard(args.input, args.output)
    print(f"dashboard={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
