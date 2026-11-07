import pytest
from benchstudio.system_spec import Component, SystemSpec
from benchstudio.system_evidence import Trial, TrialKey, SystemRun
from benchstudio.system_comparison import compare_system_runs


def system(revision):
    return SystemSpec("wm-agent", revision, (
        Component("wm", "world_model", "wm", revision),
        Component("actor", "vla", "policy", "p1"),
    ))


def key(seed=1, protocol="a"*64):
    return TrialKey("grasp", "v1", "scene", "nominal", seed, 0, "sim-v1",
                    protocol, "checker", "r1")


def run(label, outcomes, metric_name="mse"):
    s = system(label)
    rows = []
    for seed, (status, success, mse) in enumerate(outcomes, 1):
        rows.append(Trial(f"t-{seed}", key(seed), s.digest, status, success,
                          "declared", True, {metric_name: mse} if mse is not None else {}))
    return SystemRun(label, s, tuple(rows))


def test_paired_system_comparison_and_world_model_prediction_metric():
    a = run("v1", [("completed", False, .5), ("completed", True, .4)])
    b = run("v2", [("completed", True, .3), ("completed", True, .2)])
    result = compare_system_runs(a, b, metrics=("mse",))
    assert result.matched_conditions == 2
    assert result.valid_binary_pairs == 2
    assert result.paired_success.success_gap_b_minus_a == .5
    assert result.numeric_deltas[0].mean_b_minus_a == pytest.approx(-.2)
    assert result.interpretation.startswith("DESCRIPTIVE")


def test_execution_failure_and_missing_unit_not_scored_false():
    a = run("a", [("completed", True, .3), ("completed", True, .1)])
    b = run("b", [("execution_failed", None, None)])
    result = compare_system_runs(a, b, metrics=("mse",))
    assert result.valid_binary_pairs == 0
    assert result.incomplete_pairs == 1
    assert len(result.unmatched_b) == 1
    assert result.paired_success.success_gap_b_minus_a is None
    assert result.numeric_deltas[0].matched == 0


def test_protocol_changed_means_not_paired():
    a = run("a", [("completed", True, .1)])
    s = system("b")
    wrong = Trial("t1", key(protocol="b"*64), s.digest, "completed", False,
                  "official", True, {})
    result = compare_system_runs(a, SystemRun("b", s, (wrong,)))
    assert result.matched_conditions == 0
    assert len(result.unmatched_a) == len(result.unmatched_b) == 1


def test_metric_name_selection_validation():
    a = run("a", [("completed", True, .1)])
    with pytest.raises(ValueError, match="duplicate"):
        compare_system_runs(a, a, metrics=("mse", "mse"))


def test_continuous_only_world_models_have_numeric_comparison_without_success():
    a = run("a", [("completed", None, .5)])
    b = run("b", [("completed", None, .2)])
    comparison = compare_system_runs(a, b, metrics=("mse",))
    assert comparison.valid_binary_pairs == 0
    assert comparison.numeric_deltas[0].mean_b_minus_a == pytest.approx(-.3)
