import json

from benchstudio.demo_dashboard import build_demo_dashboard


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_demo_dashboard_renders_artifact_values_and_urdf_studio_theme(tmp_path):
    evidence = tmp_path / "evidence"
    attempts = []
    ledger = []
    for index, condition in enumerate(("baseline", "low_refinement")):
        attempt_id = f"attempt-{index:06d}"
        attempts.append(
            {
                "key": {
                    "attempt_id": attempt_id,
                    "condition_id": condition,
                    "pair_id": "pair-01",
                },
                "metadata": {
                    "condition": {
                        "id": condition,
                        "denoising_steps": 10 if index == 0 else 2,
                    }
                },
            }
        )
        ledger.append(
            {
                "attempt_id": attempt_id,
                "status": "completed",
                "success_count": 1,
                "evidence_verified": True,
            }
        )

    _write_json(
        evidence / "campaign-plan.json",
        {
            "run_id": "pink-demo",
            "plan_digest_sha256": "abc123def456",
            "attempts": attempts,
        },
    )
    ledger_path = evidence / "campaign" / "attempt-results.jsonl"
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        "\n".join(json.dumps(row) for row in ledger) + "\n", encoding="utf-8"
    )
    _write_json(
        evidence / "robustness" / "counterfactual-summary.json",
        {
            "scheduled_branch_count": 2,
            "completed_branch_count": 2,
            "result_digest_sha256": "robust123",
        },
    )
    _write_json(
        evidence / "transfer" / "transfer-report.json",
        {
            "transfer_fidelity": {
                "simulation_success_rate": 1.0,
                "physical_success_rate": 0.5,
                "success_gap_physical_minus_simulation": -0.5,
                "matched_pairs": 2,
            }
        },
    )
    _write_json(
        evidence / "robochallenge-report.json", {"valid": True, "event_count": 2}
    )
    _write_json(
        evidence / "urdf-studio" / "run.json",
        {
            "schema": "scenario_run.v1",
            "scenario_id": "so101_cube_lift",
            "sims": ["mujoco"],
            "episodes": 4,
        },
    )
    _write_json(
        evidence / "urdf-studio" / "comparison.json",
        {
            "scenario_id": "so101_cube_lift",
            "summary": {"mujoco": {"episodes": 4, "completed": 4, "success_rate": 0.0}},
        },
    )
    _write_json(
        evidence / "urdf-studio" / "scenario" / "waypoints.json",
        {
            "waypoints": [
                {"label": "ready", "time_s": 0.0, "joints": {"gripper": 1.2}},
                {
                    "label": "close on contact",
                    "time_s": 3.0,
                    "joints": {"gripper": -0.15},
                },
                {"label": "lift", "time_s": 4.8, "joints": {"gripper": -0.15}},
            ]
        },
    )
    _write_json(
        evidence / "urdf-studio" / "simulator-debug.json",
        {
            "schema": "benchstudio.simulator_debug.v1",
            "shared_parameters": {
                "physics_timestep_s": 0.0002,
                "control_hz": 50.0,
                "checker_interval_steps": 5,
                "max_episode_steps": 400,
                "grasp_attach": "none",
                "attach_link": None,
                "episodes": 4,
            },
            "input_digests": {
                "scenario_sha256": "a" * 64,
                "robot_sha256": "b" * 64,
                "policy_sha256": "c" * 64,
            },
            "backends": {
                "mujoco": {
                    "status": "evaluated",
                    "package_version": "3.12.0",
                    "episodes": 4,
                    "completed": 4,
                    "success_rate": 0.0,
                    "mean_sim_time_s": 1.65,
                    "mean_wall_time_s": 0.55,
                    "errors": [],
                },
                "genesis": {
                    "status": "failed",
                    "episodes": 4,
                    "completed": 0,
                    "errors": ["genesis package is unavailable"],
                },
            },
        },
    )
    seeds = [17, 29, 43, 61]
    for episode_index, seed in enumerate(seeds):
        _write_json(
            evidence
            / "urdf-studio"
            / "mujoco"
            / f"episode-{episode_index}"
            / "report.json",
            {
                "success": False,
                "stop_reason": "max_steps",
                "grasp_attach_used": False,
                "sim_time_s": 1.5 + episode_index * 0.1,
                "wall_time_s": 0.4 + episode_index * 0.1,
                "steps": 75 + episode_index,
                "artifacts": {"trace_ndjson": {"record_count": 225}},
                "environment": {"packages": {"mujoco": "3.12.0"}},
            },
        )
        _write_json(
            evidence / "urdf-studio" / "manifests" / f"episode-{episode_index}.json",
            {
                "episode_index": episode_index,
                "seed": seed,
                "object_placements": {
                    "grasp_cube": {
                        "position_xyz": [0.270 + episode_index * 0.001, 0.007, 0.0225]
                    }
                },
            },
        )
        _write_json(
            evidence
            / "urdf-studio"
            / "mujoco"
            / f"episode-{episode_index}"
            / "contact-analysis.json",
            {
                "schema": "benchstudio.contact_grasp_analysis.v1",
                "episode_index": episode_index,
                "seed": seed,
                "backend": "mujoco",
                "success": False,
                "stop_reason": "max_steps",
                "failure_class": "transient_impact_ejected_object",
                "explanation": "The cube was abruptly displaced between 50 Hz evidence snapshots; bilateral retention never formed.",
                "contact_model": {
                    "mode": "physics_contact",
                    "grasp_attach_used": False,
                    "fixed_finger_geom": "robot/fixed_finger_contact_mesh",
                    "moving_finger_geom": "robot/moving_finger_contact_mesh",
                },
                "timeline": {
                    "close_command_ms": 3000,
                    "first_contact_ms": None,
                    "contact_frames": 0,
                    "bilateral_contact_frames": 0,
                },
                "motion": {
                    "horizontal_displacement_m": 0.16 + episode_index * 0.001,
                    "max_lift_m": 0.009,
                    "largest_frame_displacement_m": 0.028,
                    "largest_frame_displacement_t_ms": 2420,
                },
                "gripper": {"final_tracking_error_rad": 0.209},
                "physics_contact_telemetry": {
                    "capture": {
                        "kind": "deterministic_diagnostic_replay",
                        "physics_timestep_s": 0.0002,
                        "effective_sample_rate_hz": 5000.0,
                        "physics_steps_scanned": 40000,
                        "contact_records": 34,
                        "contact_physics_steps": 34,
                        "bilateral_contact_physics_steps": 0,
                        "all_robot_cube_contacts_retained": True,
                    },
                    "contact": {
                        "first_contact_s": 2.418,
                        "last_contact_s": 2.4246,
                        "peak_normal_force_n": 42.6,
                        "peak_tangential_force_n": 4.2,
                        "normal_impulse_ns": 0.0712,
                        "tangential_impulse_ns": 0.0081,
                        "maximum_penetration_m": 0.00031,
                    },
                    "equivalence": {"verified": True},
                },
                "limitations": [
                    "Contact reconstruction uses 50 Hz retained state snapshots; impacts shorter than 20 ms may occur between frames.",
                    "No contact force is claimed because the retained trace does not include solver impulses.",
                ],
            },
        )

    _write_json(
        evidence / "urdf-studio" / "recovery.json",
        {
            "schema": "benchstudio.robot_recovery.v1",
            "backend": "mujoco",
            "episode_index": 2,
            "seed": 43,
            "status": "lift_still_failed",
            "policy_changed": False,
            "policy_binding": {
                "failed_attempt_sha256": "e" * 64,
                "recovered_attempt_sha256": "f" * 64,
                "unchanged": False,
            },
            "intervention": {
                "kind": "slow_approach",
                "parameter": "policy.approach_duration_s",
                "baseline_value": 1.2,
                "intervention_value": 2.4,
                "unit": "s",
                "policy_changed": True,
            },
            "effect": {
                "peak_normal_force_n": {"baseline": 500.5, "intervention": 252.7},
                "horizontal_displacement_m": {"baseline": 0.0617, "intervention": 0.1370},
            },
            "attempts": [
                {
                    "attempt": 0,
                    "success": False,
                    "stop_reason": "max_steps",
                    "steps": 125,
                    "sim_time_s": 2.5,
                    "files": {
                        "episode.mp4": {
                            "path": "recovery/episode-2/attempt-0/episode.mp4"
                        }
                    },
                },
                {
                    "attempt": 1,
                    "success": False,
                    "stop_reason": "max_steps",
                    "steps": 400,
                    "sim_time_s": 8.0,
                    "files": {
                        "episode.mp4": {
                            "path": "recovery/episode-2/attempt-1/episode.mp4"
                        }
                    },
                },
            ],
        },
    )
    _write_json(
        evidence / "urdf-studio" / "study-manifest.json",
        {
            "schema": "benchstudio.study_manifest.v1",
            "study_id": "so101-cube-grasp-cross-sim-v1",
            "episode_count": 100,
            "manifest_sha256": "d" * 64,
            "episodes": [
                {
                    "episode_id": f"episode-{index:03d}",
                    "seed": index + 1000,
                    "policy_condition": "production_candidate",
                    "object_placements": {
                        "grasp_cube": {"position_xyz": [0.27, 0.0, 0.0225]}
                    },
                }
                for index in range(100)
            ],
        },
    )
    output = build_demo_dashboard(evidence, tmp_path / "site" / "index.html")
    workbench = output.read_text(encoding="utf-8")
    document = (tmp_path / "site" / "scientific-report.html").read_text(
        encoding="utf-8"
    )

    assert "BenchStudio — Evaluation Workbench" in workbench
    assert "100 EPISODES × 3 SIMULATORS" in workbench
    assert "Coverage matrix" in workbench
    assert workbench.count('class="coverage-row"') == 100
    assert workbench.count('class="coverage-cell') == 300
    assert "Paired intervention" not in workbench
    assert "Evidence records" not in workbench
    assert "STUDY STATUS" in workbench
    assert "BATCH BLOCKED" in workbench
    assert "Recorded backend" in workbench
    assert "Awaiting data" in workbench
    assert "PHYSICS CLOCK" in workbench
    assert "CONTROL CLOCK" in workbench
    assert "100 physics steps" in workbench
    assert "CHECKER CLOCK" in workbench
    assert "5 control ticks · 100 ms · 500 physics steps" in workbench
    assert 'data-view="report"' not in workbench
    assert 'id="view-report"' not in workbench
    assert 'href="scientific-report.html"' not in workbench
    assert 'id="inspect-video"' in workbench
    assert 'id="inspect-evidence"' in workbench
    assert 'id="inspect-report"' in workbench
    assert "SYNCHRONIZED VIEWPORTS" in workbench
    assert "AWAITING<br>DATA" in workbench
    assert "trajectory pending" in workbench
    assert "divergence —" in workbench
    assert "PLANNED PARAMETERS" in workbench
    assert "physics dt" in workbench
    assert "contact_source" in workbench
    assert "cube 0.270, 0.000, 0.022 m" in workbench
    assert 'id="inspect-empty"' in workbench
    assert "switchSimulator" in workbench
    assert "planned parameters shown below" in workbench

    assert "BenchStudio — Study control room" in document
    assert "Batch authorization" in document
    assert "Scientific verdict" not in document
    assert "EVIDENCE QUALIFIED" not in document
    assert "Transfer fidelity" not in document
    assert "VIEW MACHINE-READABLE SUMMARY" not in document
    assert "Inspect frozen plan" not in document
    assert "4/4 COMPLETED" not in document
    assert "Machine-readable" not in document
    assert 'font:14px/1.5 Inter,"Helvetica Neue",Arial,sans-serif' in document
    assert "--pink:#ff4fba" in document
    assert "radial-gradient" not in document
    assert "text-shadow" not in document
    assert "TARGET BATCH" in document
    assert ">100</b>" in document
    assert "PREFLIGHT EXECUTED" in document
    assert "BATCH WITHHELD" in document
    assert ">96</b>" in document
    assert "VERIFIED BACKEND" in document
    assert "Production batch blocked" in document
    assert "BLOCKED · TASK SUCCESS REQUIRED" in document
    assert "Authorize 100 episodes" in document
    assert "Approve 100 episodes" in document
    assert 'data-artifact="preflight_gate"' in document
    assert "EXPERIMENT SETUP" in document
    assert "SEEDING & PAIRING" in document
    assert "sha256(study_id, episode_index)" in document
    assert "RANDOMIZATION" in document
    assert "12 × 12 × 0 mm" in document
    assert "MuJoCo" in document
    assert "100-EPISODE EXECUTION MANIFEST" in document
    assert "Every batch slot is accounted for" in document
    assert "episode-000" in document
    assert "episode-099" in document
    assert document.count('class="manifest-row"') == 100
    assert 'data-artifact="study_manifest"' in document
    assert "TASK-SPECIFIC" in document
    assert "STUDY GOVERNANCE" in document
    assert "MUJOCO EVIDENCE" in document
    assert "no kinematic attach or weld" in document
    assert "constraint force" in document
    assert "PARAMETER PILOT · MUJOCO" in document
    assert "4 controlled conditions · 4 failures" in document
    assert "No population-level rate is reported" in document
    assert document.count("<video") == 1
    assert "CONTROLLED CONDITIONS · SELECT TO INSPECT" in document
    assert document.count('data-episode-position="') == 4
    assert 'id="pilot-video"' in document
    assert "urdf-studio/mujoco/episode-0/episode.mp4" in document
    assert "urdf-studio/mujoco/episode-1/episode.mp4" in document
    assert "urdf-studio/mujoco/episode-2/episode.mp4" in document
    assert "urdf-studio/mujoco/episode-3/episode.mp4" in document
    assert "Episode 01" in document
    assert "Episode 04" in document
    assert "SEED 17" in document
    assert "seed 61" in document
    assert 'data-artifact="study"' in document
    assert 'data-artifact="episode_0"' in document
    assert 'data-artifact="recovery"' in document
    assert "transient impact ejected object" in document
    assert "160.0 mm" in document
    assert "9.0 mm" in document
    assert "42.6 N" in document
    assert "PARAMETER EXPERIMENT" in document
    assert "Slower approach reduced impact, not failure" in document
    assert "1.2 → 2.4 s" in document
    assert "500.5 → 252.7 N" in document
    assert "61.7 → 137.0 mm" in document
    assert "Lift still failed" in document
    assert "Preflight evidence gates batch execution" in document
