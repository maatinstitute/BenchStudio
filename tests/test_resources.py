from benchstudio.analysis import ResourcePoint, pareto_frontier


def test_pareto_frontier_retains_success_latency_compute_tradeoffs():
    frontier = pareto_frontier(
        [
            ResourcePoint("cheap", 0.7, 10, 5),
            ResourcePoint("slow", 0.9, 20, 10),
            ResourcePoint("dominated", 0.6, 25, 15),
        ]
    )
    assert [point.condition_id for point in frontier] == ["cheap", "slow"]
