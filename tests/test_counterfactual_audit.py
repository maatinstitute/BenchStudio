from __future__ import annotations

from benchstudio.analysis import audit_counterfactual_outcomes
from benchstudio.campaigns import CampaignPlanner, Intervention, compile_counterfactual_plan


def _plan():
    nominal = CampaignPlanner(
        run_id="robustness", scenario_id="task", conditions=[{"x": 1}], seeds=[7]
    ).freeze()
    return compile_counterfactual_plan(
        nominal, [Intervention("delay", 2, "sensor_delay", {"ms": 10})]
    )


def test_counterfactual_outcome_audit_requires_frozen_branch_lineage():
    plan = _plan()
    pair = plan.pairs[0]
    records = [
        {
            "branch_attempt_id": pair.nominal.branch_attempt_id,
            "pair_id": pair.nominal.pair_id,
            "branch": "nominal",
            "transition_index": 2,
            "intervention_id": "none",
        },
        {
            "branch_attempt_id": pair.intervention.branch_attempt_id,
            "pair_id": pair.intervention.pair_id,
            "branch": "intervention",
            "transition_index": 2,
            "intervention_id": "delay",
        },
    ]
    audit = audit_counterfactual_outcomes(plan, records)
    assert audit.complete is True
    assert audit.to_dict()["scheduled_branches"] == 2


def test_counterfactual_outcome_audit_preserves_missing_and_mismatched_branches():
    plan = _plan()
    pair = plan.pairs[0]
    audit = audit_counterfactual_outcomes(
        plan,
        [
            {
                "branch_attempt_id": pair.intervention.branch_attempt_id,
                "pair_id": "wrong-pair",
                "branch": "intervention",
                "transition_index": 1,
                "intervention_id": "wrong",
            }
        ],
    )
    assert audit.complete is False
    assert pair.nominal.branch_attempt_id in audit.missing_branch_attempt_ids
    assert len(audit.lineage_issues) == 3
