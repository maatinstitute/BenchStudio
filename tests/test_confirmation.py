import pytest

from benchstudio.campaigns import (
    SearchCandidate,
    compile_confirmation_plan,
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
