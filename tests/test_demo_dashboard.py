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
            "summary": {"mujoco": {"episodes": 4, "completed": 4, "success_rate": 1.0}},
        },
    )
    _write_json(
        evidence / "urdf-studio" / "scenario" / "waypoints.json",
        {
            "waypoints": [
                {"label": "ready", "time_s": 0.0, "joints": {"gripper": 1.2}},
                {
                    "label": "close + attach",
                    "time_s": 3.0,
                    "joints": {"gripper": 0.15},
                    "attach": "grasp_cube",
                },
                {"label": "lift", "time_s": 4.8, "joints": {"gripper": 0.15}},
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
                "grasp_attach": "weld",
                "attach_link": "gripper_frame_link",
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
                    "success_rate": 1.0,
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
                "success": True,
                "grasp_attach_used": True,
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
        evidence / "urdf-studio" / "recovery.json",
        {
            "schema": "benchstudio.robot_recovery.v1",
            "backend": "mujoco",
            "episode_index": 2,
            "seed": 43,
            "status": "recovered",
            "policy_changed": False,
            "policy_binding": {
                "failed_attempt_sha256": "e" * 64,
                "recovered_attempt_sha256": "e" * 64,
                "unchanged": True,
            },
            "intervention": {
                "kind": "extend_episode_horizon",
                "parameter": "runtime.max_episode_steps",
                "failed_value": 125,
                "recovered_value": 400,
                "policy_changed": False,
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
                    "success": True,
                    "stop_reason": "success",
                    "steps": 235,
                    "sim_time_s": 4.7,
                    "files": {
                        "episode.mp4": {
                            "path": "recovery/episode-2/attempt-1/episode.mp4"
                        }
                    },
                },
            ],
        },
    )
    output = build_demo_dashboard(evidence, tmp_path / "site" / "index.html")
    document = output.read_text(encoding="utf-8")

    assert "BenchStudio — Evaluation report" in document
    assert "Eval Control Room" in document
    assert "Scientific verdict" not in document
    assert "EVIDENCE QUALIFIED" not in document
    assert "pink-demo" in document
    assert '"attempts.scheduled"</span>: <span class="json-number">2</span>' in document
    assert '"transport.valid"</span>: <span class="json-ok">true</span>' in document
    assert 'font-family:"Noto Sans", Arial, sans-serif' in document
    assert "--pink:#ff4fba" in document
    assert "radial-gradient" not in document
    assert "text-shadow" not in document
    assert "VIEW MACHINE-READABLE SUMMARY" in document
    assert 'data-artifact="plan"' in document
    assert 'href="campaign-plan.json"' not in document
    assert "SO-101 · Cube lift" in document
    assert "ROBOT EPISODES</span><b>4/4 COMPLETED" in document
    assert "FINAL RESULT</span><b>4/4 LIFT CHECKER PASS" in document
    assert "FIRST-PASS RATE</span><b>3/4" in document
    assert "RECOVERY</span><b>1/1 RECOVERED" in document
    assert "EXECUTIONS</span><b>5 TOTAL" in document
    assert "CONTACT GRASP</span><b>NOT EVALUATED" in document
    assert "This is not a contact-realistic grasp" in document
    assert "welded cube crossed the 0.10 m lift threshold" in document
    assert "varies the cube pose under frozen seeds" in document
    assert "Separate accounting fixture; not additional SO-101 videos." in document
    assert "Attempts completed</span><strong>2/2" in document
    assert "urdf-studio/mujoco/episode-0/episode.mp4" in document
    assert "urdf-studio/mujoco/episode-1/episode.mp4" in document
    assert "urdf-studio/mujoco/episode-2/episode.mp4" in document
    assert "urdf-studio/mujoco/episode-3/episode.mp4" in document
    assert "EPISODE 01" in document
    assert "EPISODE 04" in document
    assert "SEED 17" in document
    assert "SEED 61" in document
    assert 'value="mujoco" selected>MuJoCo · evaluated' in document
    assert 'value="genesis" disabled>Genesis · failed' in document
    assert "this report stays bound to the evaluated episode batch" in document
    assert 'data-artifact="robot_episodes"' in document
    assert 'data-artifact="robot_recovery"' in document
    assert 'data-artifact="robot_policy"' in document
    assert "Waypoint baseline · sha256" in document
    assert "ready 0.0s · close + attach 3.0s · lift 4.8s" in document
    assert "Simulator parameter matrix" in document
    assert "PHYSICS STEP" in document
    assert "genesis package is unavailable" in document
    assert "Lift checker pass rate" in document
    assert 'data-artifact="simulator_debug"' in document
    assert "Episode 03 · Linked attempts" in document
    assert "ATTEMPT 01 · FAILED" in document
    assert "MAX STEPS" in document
    assert "125 → 400" in document
    assert "policy unchanged · eeeeeeeeeeee" in document
    assert "ATTEMPT 02 · PASSED" in document
    assert "recovery/episode-2/attempt-0/episode.mp4" in document
    assert "recovery/episode-2/attempt-1/episode.mp4" in document
