import json

import pytest

from benchstudio.campaigns import (
    ConfirmationEvaluation,
    SearchCandidate,
    audit_confirmation_results,
    compile_confirmation_plan,
    execute_confirmation_plan,
    load_confirmation_plan,
    validate_confirmation_plan,
)


def _candidate(candidate_id: str, source_seed: int = 1) -> SearchCandidate:
    return SearchCandidate(candidate_id, "pick", "state-1", "search-run", source_seed, "a" * 64)


def test_confirmation_plan_freezes_holdout_and_separates_search_seeds():
    plan = compile_confirmation_plan(
        run_id="confirm-run",
        source_search_digest_sha256="b" * 64,
        candidates=[_candidate("c1"), _candidate("c2", 2)],
        confirmation_seeds=[10, 11],
        holdout_candidate_ids=["c2"],
    )
    assert len(plan.cases) == 2
    assert {case.candidate_id for case in plan.cases} == {"c2"}
    assert validate_confirmation_plan(plan) == []


def test_confirmation_plan_round_trips_through_independent_loader(tmp_path):
    plan = compile_confirmation_plan(
        run_id="confirm-run",
        source_search_digest_sha256="b" * 64,
        candidates=[_candidate("c1")],
        confirmation_seeds=[10],
    )
    path = tmp_path / "confirmation-plan.json"
    plan.write(path)
    assert load_confirmation_plan(path) == plan


def test_confirmation_plan_loader_rejects_digest_tampering(tmp_path):
    plan = compile_confirmation_plan(
        run_id="confirm-run",
        source_search_digest_sha256="b" * 64,
        candidates=[_candidate("c1")],
        confirmation_seeds=[10],
    )
    path = tmp_path / "confirmation-plan.json"
    plan.write(path)
    payload = json.loads(path.read_text())
    payload["cases"][0]["confirmation_seed"] = 11
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="digest"):
        load_confirmation_plan(path)


def test_confirmation_plan_rejects_search_seed_reuse_and_unknown_holdout():
    with pytest.raises(ValueError, match="reuses search seed"):
        compile_confirmation_plan(
            run_id="run",
            source_search_digest_sha256="b" * 64,
            candidates=[_candidate("c1", 3)],
            confirmation_seeds=[3],
        )
    with pytest.raises(ValueError, match="unknown candidate"):
        compile_confirmation_plan(
            run_id="run",
            source_search_digest_sha256="b" * 64,
            candidates=[_candidate("c1")],
            confirmation_seeds=[3],
            holdout_candidate_ids=["missing"],
        )


@pytest.mark.parametrize("seed", [True, 10.0, "10"])
def test_confirmation_plan_rejects_non_integer_seeds(seed):
    with pytest.raises(ValueError, match="confirmation seed must be an integer"):
        compile_confirmation_plan(
            run_id="run",
            source_search_digest_sha256="b" * 64,
            candidates=[_candidate("c1")],
            confirmation_seeds=[seed],
        )


def test_confirmation_plan_loader_rejects_coerced_seed(tmp_path):
    plan = compile_confirmation_plan(
        run_id="confirm-run",
        source_search_digest_sha256="b" * 64,
        candidates=[_candidate("c1")],
        confirmation_seeds=[10],
    )
    path = tmp_path / "confirmation-plan.json"
    plan.write(path)
    payload = json.loads(path.read_text())
    payload["cases"][0]["confirmation_seed"] = "10"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="invalid confirmation case"):
        load_confirmation_plan(path)


def test_confirmation_execution_is_separate_and_persists_reproduction_evidence(tmp_path):
    plan = compile_confirmation_plan(
        run_id="confirm-run",
        source_search_digest_sha256="b" * 64,
        candidates=[_candidate("c1"), _candidate("c2", 2)],
        confirmation_seeds=[10, 11],
        holdout_candidate_ids=["c2"],
    )
    results = execute_confirmation_plan(
        plan,
        lambda case: ConfirmationEvaluation(
            failure_reproduced=case.confirmation_seed == 11,
            metadata={"seed": case.confirmation_seed},
        ),
        output=tmp_path / "confirmation-evidence",
    )
    assert len(results) == 2
    assert sum(result.failure_reproduced for result in results) == 1
    assert all(result.source_search_run_id == "search-run" for result in results)
    summary = json.loads(
        (tmp_path / "confirmation-evidence" / "confirmation-summary.json").read_text()
    )
    assert summary["source_search_digest_sha256"] == "b" * 64
    assert summary["failure_reproduced_count"] == 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "confirmation-evidence" / "confirmation-results.jsonl")
        .read_text()
        .splitlines()
    ]
    assert audit_confirmation_results(plan, rows).complete


def test_confirmation_result_audit_rejects_tampered_candidate_lineage():
    plan = compile_confirmation_plan(
        run_id="confirm-run",
        source_search_digest_sha256="b" * 64,
        candidates=[_candidate("c1")],
        confirmation_seeds=[10],
    )
    case = plan.cases[0]
    audit = audit_confirmation_results(
        plan,
        [
            {
                "case_id": case.case_id,
                "candidate_id": "wrong",
                "scenario_id": case.scenario_id,
                "initial_condition_id": case.initial_condition_id,
                "confirmation_seed": case.confirmation_seed,
                "source_search_run_id": case.source_search_run_id,
                "failure_reproduced": False,
            }
        ],
    )
    assert audit.complete is False
    assert any("candidate_id does not match frozen plan" in issue for issue in audit.lineage_issues)


def test_confirmation_result_audit_rejects_invalid_failure_evidence():
    plan = compile_confirmation_plan(
        run_id="confirm-run",
        source_search_digest_sha256="b" * 64,
        candidates=[_candidate("c1")],
        confirmation_seeds=[10],
    )
    case = plan.cases[0]
    audit = audit_confirmation_results(
        plan,
        [
            {
                "case_id": case.case_id,
                "candidate_id": case.candidate_id,
                "scenario_id": case.scenario_id,
                "initial_condition_id": case.initial_condition_id,
                "confirmation_seed": case.confirmation_seed,
                "source_search_run_id": case.source_search_run_id,
                "failure_reproduced": True,
                "failure_digest_sha256": "not-a-digest",
            }
        ],
    )
    assert audit.complete is False
    assert any("lowercase SHA-256" in issue for issue in audit.lineage_issues)


def test_confirmation_execution_rejects_digest_on_non_reproduction():
    plan = compile_confirmation_plan(
        run_id="confirm-run",
        source_search_digest_sha256="b" * 64,
        candidates=[_candidate("c1")],
        confirmation_seeds=[10],
    )
    with pytest.raises(ValueError, match="non-reproducing case"):
        execute_confirmation_plan(
            plan,
            lambda _: ConfirmationEvaluation(False, "a" * 64),
        )
