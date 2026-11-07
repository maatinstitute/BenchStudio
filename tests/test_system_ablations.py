from benchstudio.system_spec import Component, Connection, SystemSpec
from benchstudio.system_evidence import SystemRun, Trial, TrialKey
from benchstudio.system_comparison import compare_system_runs
from benchstudio.system_ablations import audit_ablation, audit_trial_coverage, review_ablation_evidence


def system(wm="v1", policy="p1", routing=False):
    connections = (Connection("world", "prediction", "agent", "world"),) if routing else ()
    return SystemSpec("robot", "r1", (
        Component("world", "world_model", "wm", wm, outputs=("prediction",)),
        Component("agent", "agent", "agent", "v1", inputs=("world",)),
        Component("policy", "vla", "smolvla", policy),
    ), connections)


def key(seed=1):
    return TrialKey("task", "v1", "scene", "nominal", seed, 0, "sim", "a"*64, "judge", "v1")


def run(system_spec, status="completed", success=True):
    row = Trial("trial1", key(), system_spec.digest, status, success,
                "official", True)
    return SystemRun("r", system_spec, (row,))


def test_single_component_revision_is_approved_structural_change():
    result = audit_ablation(system(), system(wm="v2"), allowed_components=("world",))
    assert result.structurally_isolated
    assert result.changed_components == ("world",)
    assert result.claim == "DECLARED_STRUCTURAL_ISOLATION_ONLY"


def test_hidden_policy_change_rejected_as_confound():
    result = audit_ablation(system(), system(wm="v2", policy="p2"),
                            allowed_components=("world",))
    assert not result.structurally_isolated
    assert "unapproved component change" in result.issues


def test_graph_wiring_and_metadata_changed_are_detected():
    assert not audit_ablation(system(), system(routing=True),
                             allowed_components=("world",)).structurally_isolated
    original = system()
    changed = SystemSpec(original.system_id, original.revision, original.components,
                         original.connections, metadata={"new":"camera"})
    result = audit_ablation(original, changed, allowed_components=("world",))
    assert result.metadata_changed and not result.structurally_isolated


def test_coverage_reports_failed_and_missing_separately():
    s = system()
    failed = run(s, status="execution_failed", success=None)
    cov = audit_trial_coverage(failed, {key(), key(2)})
    assert not cov.complete
    assert cov.valid_outcomes == 0
    assert len(cov.missing_keys) == len(cov.incomplete_keys) == 1


def test_ablation_readiness_not_causal_proof():
    before, after = system(), system(wm="v2")
    comparison = compare_system_runs(run(before), run(after))
    result = review_ablation_evidence(
        audit_ablation(before, after, allowed_components=("world",)),
        comparison, min_matched_pairs=1
    )
    assert result.status == "DECLARED_PREREQUISITES_MET"
    assert result.claim if hasattr(result, "claim") else True
    assert review_ablation_evidence(
        audit_ablation(before, after, allowed_components=("world",)),
        comparison, min_matched_pairs=20
    ).status == "INCONCLUSIVE"
