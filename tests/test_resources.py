import pytest

from ival.analysis import ResourceBudget, ResourcePoint, audit_resources, pareto_frontier


def test_pareto_frontier_retains_success_latency_compute_tradeoffs():
    frontier = pareto_frontier(
        [
            ResourcePoint("cheap", 0.7, 10, 5),
            ResourcePoint("slow", 0.9, 20, 10),
            ResourcePoint("dominated", 0.6, 25, 15),
        ]
    )
    assert [point.condition_id for point in frontier] == ["cheap", "slow"]


def test_campaign_resource_limits_audit_measured_gpu_bytes_and_queries():
    audit = audit_resources(
        calls=4,
        wall_time_ms=900,
        compute_time_ms=200,
        gpu_hours=0.25,
        output_bytes=120,
        policy_queries=4,
        budget=ResourceBudget(
            max_gpu_hours=0.5,
            max_bytes=128,
            max_policy_queries=4,
            per_cell_timeout_seconds=1.0,
        ),
    )
    assert audit.valid


def test_campaign_resource_limits_fail_closed_when_measurements_are_missing():
    audit = audit_resources(
        calls=1,
        wall_time_ms=1,
        compute_time_ms=1,
        budget=ResourceBudget(max_gpu_hours=0.1, max_bytes=10),
    )
    assert audit.valid is False
    assert audit.violations == ("gpu_hours_unavailable", "output_bytes_unavailable")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_bytes": True},
        {"max_policy_queries": 1.5},
        {"retry_limit": -1},
        {"max_gpu_hours": float("nan")},
    ],
)
def test_campaign_resource_limits_reject_invalid_frozen_values(kwargs):
    with pytest.raises(ValueError):
        ResourceBudget(**kwargs)
