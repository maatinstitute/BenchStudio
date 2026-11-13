from __future__ import annotations

import copy
import itertools
import json

import pytest

from reva.campaigns import (
    CHECKPOINT_REVISION,
    CONDITIONS,
    DEFAULT_SCHEDULING_SEED,
    POLICY_SEEDS,
    STATE_IDS,
    SUITES,
    TASK_IDS,
    compile_refinement_campaign_plan,
    compile_refinement_source_plan,
    digest,
    load_refinement_source_plan,
    make_plan,
    write_plan,
)


def test_expected_count_and_full_factorial():
    plan = make_plan()
    assert plan["design"]["block_count"] == 80
    assert plan["design"]["planned_attempt_count"] == 320
    expected = set(itertools.product(SUITES, TASK_IDS, STATE_IDS, POLICY_SEEDS, CONDITIONS))
    actual = {
        (
            row["episode_identity"]["suite"],
            row["episode_identity"]["task_id"],
            row["episode_identity"]["initial_state_id"],
            row["episode_identity"]["policy_seed"],
            (row["h"], row["denoising_steps"]),
        )
        for row in plan["schedule"]
    }
    assert actual == expected


def test_refinement_source_golden_vector_is_byte_identical():
    """Keep the ReVa planner aligned with the source planner."""
    plan = make_plan()
    # Generated from Refinement/Refresh experiments/make_evaluation_plan.py at
    # the source revision recorded in docs/source-attribution.md.
    assert plan["scheduling"]["schedule_sha256"] == (
        "3e7959353447d2a02e1a7b42bfa1a756b7259a28f22d20df072ab3750917ad0b"
    )
    assert plan["schedule"][0]["planned_run_id"] == (
        "libero_10.task006.state013.seed2000.h1_d10"
    )
    assert plan["schedule"][-1]["planned_run_id"] == (
        "libero_object.task005.state014.seed2001.h5_d10"
    )


def test_contiguous_complete_blocks_and_native_reference():
    rows = make_plan()["schedule"]
    for start in range(0, len(rows), 4):
        block = rows[start : start + 4]
        assert {row["block_index"] for row in block} == {start // 4}
        assert len({row["block_id"] for row in block}) == 1
        assert {row["condition_index"] for row in block} == set(range(4))
        assert {(row["h"], row["denoising_steps"]) for row in block} == set(CONDITIONS)
        assert all(row["episode_identity"] == block[0]["episode_identity"] for row in block)
        assert sum(row["native_reference"] for row in block) == 1


def test_determinism_and_seed_changes_order_only():
    first = make_plan()
    assert first == make_plan()
    second = make_plan(DEFAULT_SCHEDULING_SEED + 1)
    assert first["schedule"] != second["schedule"]
    assert {row["planned_run_id"] for row in first["schedule"]} == {
        row["planned_run_id"] for row in second["schedule"]
    }


def test_digest_authenticates_canonical_schedule():
    plan = make_plan()
    assert plan["scheduling"]["schedule_sha256"] == digest(plan["schedule"])
    altered = copy.deepcopy(plan["schedule"])
    altered[0]["h"] = 999
    assert digest(altered) != plan["scheduling"]["schedule_sha256"]
    assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})


def test_unverified_status_and_seed_validation():
    plan = make_plan()
    assert plan["status"] == "requires_runtime_and_holdout_verification"
    assert plan["checkpoint"]["revision"] == CHECKPOINT_REVISION
    assert plan["checkpoint"]["runtime_file_hashes"] is None
    assert all(value == "unverified" for value in plan["external_gates"].values())
    assert plan["native_config"]["condition_id"] == "h1_d10"
    for seed in (True, 1.2, "123", None):
        with pytest.raises(ValueError):
            make_plan(seed)


def test_no_overwrite_without_force(tmp_path):
    target = tmp_path / "plan.json"
    first, second = make_plan(), make_plan(7)
    write_plan(target, first)
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        write_plan(target, second)
    assert target.read_bytes() == original
    write_plan(target, second, force=True)
    assert json.loads(target.read_text()) == second


def test_source_schedule_adapts_to_frozen_campaign_plan():
    plan = compile_refinement_campaign_plan(run_id="refinement-1")
    assert len(plan.attempts) == 320
    assert len(plan.paired_schedule) == 320
    assert plan.source_spec_sha256 == plan.attempts[0].metadata["source_schedule_sha256"]
    assert plan.attempts[0].key.attempt_id.endswith(plan.attempts[0].key.condition_id)


def test_source_plan_import_preserves_upstream_rows_and_binds_file(tmp_path):
    source_path = tmp_path / "upstream-plan.json"
    write_plan(source_path, make_plan())
    source, file_sha256 = load_refinement_source_plan(source_path)
    imported = compile_refinement_source_plan(source_path, run_id="imported-refinement")

    assert imported.run_id == "imported-refinement"
    assert imported.source_spec_sha256 == file_sha256
    assert list(imported.paired_schedule) == source["schedule"]
    assert imported.attempts[0].metadata["source_plan_file_sha256"] == file_sha256
    assert imported.attempts[0].metadata["source_planned_run_id"] == (
        source["schedule"][0]["planned_run_id"]
    )
    assert imported.protocol["checkpoint"] == source["checkpoint"]
    assert imported.protocol["native_config"] == source["native_config"]
    assert imported.protocol["execution_contract"] == source["execution_contract"]
    assert imported.protocol["external_gates"] == source["external_gates"]


def test_source_plan_import_rejects_schedule_mutation(tmp_path):
    source = make_plan()
    source["schedule"][0]["h"] = 99
    path = tmp_path / "mutated-plan.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="schedule digest mismatch"):
        compile_refinement_source_plan(path)


def test_source_plan_import_accepts_frozen_execution_protocol(tmp_path):
    source_path = tmp_path / "upstream-plan.json"
    write_plan(source_path, make_plan())
    protocol = {
        "M": {"adapter": "mock", "capabilities": {"supports_closed_loop": True}},
        "S": {
            "environments": [
                {
                    "id": "default",
                    "kind": "simulator",
                    "adapter": "external_command",
                    "adapter_config": {"command": ["fixture"]},
                }
            ]
        },
    }
    imported = compile_refinement_source_plan(
        source_path, run_id="protocol-bound", execution_protocol=protocol
    )
    assert imported.protocol["M"] == protocol["M"]
    assert imported.protocol["S"] == protocol["S"]
    assert imported.plan_digest_sha256 != compile_refinement_source_plan(
        source_path, run_id="protocol-bound"
    ).plan_digest_sha256
