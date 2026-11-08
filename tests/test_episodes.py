from contextlib import contextmanager
import pytest
import benchstudio as bs


def test_reset_runs_before_each_episode_and_failure_prevents_body():
    state = [99]
    isolation = bs.EpisodeIsolation(reset=lambda system, case: system.clear())
    for case in ("a", "b"):
        with isolation.activate(state, case) as system:
            assert system == []
            system.append(4)
    def fail(*args):
        raise RuntimeError("reset failed")
    with pytest.raises(RuntimeError), bs.EpisodeIsolation(reset=fail).activate(state, "a"):
        pytest.fail("must not enter")


def test_factory_cleanup_on_episode_exception():
    events = []
    @contextmanager
    def factory(case):
        events.append(case)
        try:
            yield object()
        finally:
            events.append("closed")
    with pytest.raises(RuntimeError), bs.EpisodeIsolation(factory=factory).activate(None, "a"):
        raise RuntimeError("episode error")
    assert events == ["a", "closed"]


def test_trace_preserves_proposals_and_truncation_immutably():
    observation = {"tick": 1}
    proposed = [{"delta": 1}, {"delta": 2}]
    batch = bs.ActionBatch(observation, proposed, (0,))
    observation["tick"] = 5
    proposed.clear()
    assert batch.to_dict() == {"observation": {"tick": 1},
        "proposed": [{"delta": 1}, {"delta": 2}], "applied_indices": [0]}
    for indices in ((2,), (0, 0), (1, 0)):
        with pytest.raises(ValueError):
            bs.ActionBatch({}, (1, 2), indices)


def test_outcome_and_coverage_are_independent():
    outcome = bs.EpisodeOutcome(True, True, False)
    assert outcome.completed and outcome.goal_reached and not outcome.constraints_satisfied
    assert bs.EpisodeOutcome(True).constraints_satisfied is None
    assert bs.EpisodeCoverage(("a", "b"), ("a",)).missing == ("b",)
    with pytest.raises(ValueError):
        bs.EpisodeCoverage(("a",), ("b",))
    with pytest.raises(ValueError):
        bs.EpisodeIsolation()
