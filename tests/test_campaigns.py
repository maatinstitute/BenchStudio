from __future__ import annotations

import json

import pytest

from benchstudio.campaigns import (
    AttemptLedger,
    CampaignPlanner,
    Intervention,
    compile_counterfactual_plan,
    load_counterfactual_plan,
    load_frozen_campaign_plan,
    validate_counterfactual_plan,
)


def test_frozen_campaign_has_stable_complete_matrix(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1",
        scenario_id="pick",
        conditions=[{"budget": 2}, {"budget": 4}],
        seeds=[1, 2],
        repetitions=2,
    ).freeze()
    assert len(plan.attempts) == 8
    assert len({attempt.key.pair_id for attempt in plan.attempts}) == 2
    assert len({attempt.key.condition_id for attempt in plan.attempts}) == 2
    assert len(plan.plan_digest_sha256) == 64
    plan.write(tmp_path / "plan.json")
    assert (
        json.loads((tmp_path / "plan.json").read_text())["plan_digest_sha256"]
        == plan.plan_digest_sha256
    )


def test_frozen_campaign_plan_round_trips_through_independent_loader(tmp_path):
    plan = CampaignPlanner(
        run_id="round-trip", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    path = tmp_path / "plan.json"
    plan.write(path)
    assert load_frozen_campaign_plan(path) == plan


def test_frozen_campaign_plan_loader_rejects_digest_tampering(tmp_path):
    plan = CampaignPlanner(
        run_id="tampered", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    path = tmp_path / "plan.json"
    plan.write(path)
    payload = json.loads(path.read_text())
    payload["attempts"][0]["task_seed"] = 99
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="digest"):
        load_frozen_campaign_plan(path)


@pytest.mark.parametrize("field", ["run_id", "source_spec_sha256", "paired_schedule"])
def test_frozen_campaign_plan_digest_binds_full_envelope(tmp_path, field):
    plan = CampaignPlanner(
        run_id="full-envelope",
        scenario_id="task",
        conditions=[{"x": 1}],
        seeds=[1],
        source_spec_sha256="a" * 64,
    ).freeze()
    path = tmp_path / f"{field}.json"
    payload = plan.to_dict()
    if field == "run_id":
        payload[field] = "different-run"
    elif field == "source_spec_sha256":
        payload[field] = "b" * 64
    else:
        payload[field] = [{"attempt_id": "unexpected"}]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="digest|run_id"):
        load_frozen_campaign_plan(path)


def test_frozen_campaign_plan_loader_rejects_duplicate_or_mismatched_attempt_identity(tmp_path):
    plan = CampaignPlanner(
        run_id="identity-plan", scenario_id="task", conditions=[{"x": 1}], seeds=[1, 2]
    ).freeze()
    payload = plan.to_dict()
    payload["attempts"][1]["key"]["attempt_id"] = payload["attempts"][0]["key"]["attempt_id"]
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate attempt_id"):
        load_frozen_campaign_plan(path)

    payload = plan.to_dict()
    payload["attempts"][0]["key"]["run_id"] = "other-run"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="run_id"):
        load_frozen_campaign_plan(path)


def test_attempt_ledger_is_append_only_and_reports_missing(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1", scenario_id="pick", conditions=[{"budget": 2}], seeds=[1, 2]
    ).freeze()
    ledger = AttemptLedger(tmp_path / "attempts.jsonl", plan)
    first = plan.attempts[0].key
    ledger.append(first, {"status": "success"})
    assert ledger.missing_attempt_ids == [plan.attempts[1].key.attempt_id]
    with pytest.raises(ValueError, match="already recorded"):
        ledger.append(first, {"status": "success"})
    wrong = type(first)(
        first.run_id, first.scenario_id, "other", first.condition_id, first.attempt_id
    )
    with pytest.raises(ValueError, match="identity"):
        ledger.append(wrong, {"status": "success"})


def test_attempt_ledger_rejects_reopening_with_a_different_plan(tmp_path):
    path = tmp_path / "attempts.jsonl"
    plan = CampaignPlanner(
        run_id="run-1", scenario_id="pick", conditions=[{"budget": 2}], seeds=[1]
    ).freeze()
    AttemptLedger(path, plan).append(plan.attempts[0].key, {"status": "success"})
    other = CampaignPlanner(
        run_id="run-1", scenario_id="pick", conditions=[{"budget": 4}], seeds=[1]
    ).freeze()
    with pytest.raises(ValueError, match="plan digest"):
        AttemptLedger(path, other)


def test_attempt_ledger_rejects_malformed_persisted_records(tmp_path):
    plan = CampaignPlanner(
        run_id="malformed-ledger", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    path = tmp_path / "attempts.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        AttemptLedger(path, plan)

    path.write_text(
        json.dumps(
            {
                "attempt_id": plan.attempts[0].key.attempt_id,
                "plan_digest_sha256": plan.plan_digest_sha256,
                "run_id": plan.run_id,
                "scenario_id": plan.attempts[0].key.scenario_id,
                "pair_id": plan.attempts[0].key.pair_id,
                "condition_id": plan.attempts[0].key.condition_id,
                "environment_id": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="identity fields"):
        AttemptLedger(path, plan)


def test_attempt_ledger_refreshes_between_workers_and_rejects_duplicate_commit(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1", scenario_id="pick", conditions=[{"budget": 2}], seeds=[1, 2]
    ).freeze()
    path = tmp_path / "attempts.jsonl"
    first_worker = AttemptLedger(path, plan)
    second_worker = AttemptLedger(path, plan)

    first_worker.append(plan.attempts[0].key, {"status": "success"})
    # The second ledger was constructed before the first commit. It must
    # refresh under the file lock instead of trusting its stale in-memory set.
    second_worker.append(plan.attempts[1].key, {"status": "success"})
    with pytest.raises(ValueError, match="already recorded"):
        second_worker.append(plan.attempts[0].key, {"status": "duplicate"})
    assert first_worker.missing_attempt_ids == []


def test_counterfactual_plan_binds_nominal_and_intervention_branches():
    nominal = CampaignPlanner(
        run_id="robustness", scenario_id="pick", conditions=[{"budget": 2}], seeds=[7, 8]
    ).freeze()
    plan = compile_counterfactual_plan(
        nominal,
        [Intervention("occlusion", 3, "partial_occlusion", {"fraction": 0.25})],
    )
    assert len(plan.pairs) == len(nominal.attempts)
    assert all(
        pair.nominal.pair_id == pair.intervention.pair_id
        and pair.nominal.branch == "nominal"
        and pair.intervention.branch == "intervention"
        for pair in plan.pairs
    )
    assert validate_counterfactual_plan(plan) == []
    assert len({pair.intervention.branch_attempt_id for pair in plan.pairs}) == len(plan.pairs)


def test_counterfactual_plan_round_trips_through_independent_loader(tmp_path):
    nominal = CampaignPlanner(
        run_id="round-trip-cf", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    plan = compile_counterfactual_plan(
        nominal, [Intervention("delay", 1, "sensor_delay", {"ms": 10})]
    )
    path = tmp_path / "counterfactual-plan.json"
    plan.write(path)
    assert load_counterfactual_plan(path) == plan


def test_counterfactual_plan_loader_rejects_digest_tampering(tmp_path):
    nominal = CampaignPlanner(
        run_id="tampered-cf", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    plan = compile_counterfactual_plan(
        nominal, [Intervention("delay", 1, "sensor_delay", {"ms": 10})]
    )
    path = tmp_path / "counterfactual-plan.json"
    plan.write(path)
    payload = json.loads(path.read_text())
    payload["pairs"][0]["intervention"]["intervention"]["parameters"]["ms"] = 20
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="digest"):
        load_counterfactual_plan(path)


def test_counterfactual_plan_rejects_reserved_or_duplicate_interventions():
    nominal = CampaignPlanner(
        run_id="robustness", scenario_id="pick", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    with pytest.raises(ValueError, match="reserved"):
        compile_counterfactual_plan(nominal, [Intervention("none", 0, "none", {})])
    intervention = Intervention("delay", 1, "sensor_delay", {"ms": 10})
    with pytest.raises(ValueError, match="unique"):
        compile_counterfactual_plan(nominal, [intervention, intervention])
