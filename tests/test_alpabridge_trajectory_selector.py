import pytest

from reva.integrations import (
    TrajectoryCandidate,
    TrajectoryReference,
    score_candidate,
    speed_scale,
    trajectory_region_score,
)


def _straight(lateral=0.0, longitudinal=0.0):
    return [(float(index + 1) + longitudinal, lateral) for index in range(20)]


def test_speed_scale_is_clipped_piecewise_linear():
    assert speed_scale(0.0) == 0.5
    assert speed_scale(1.4) == 0.5
    assert speed_scale(11.0) == 1.0
    assert speed_scale(15.0) == 1.0
    assert speed_scale(6.2) == pytest.approx(0.5 + 0.5 * (6.2 - 1.4) / (11.0 - 1.4))


def test_selection_regions_and_decay_match_source_contract():
    reference = _straight()
    score, inside = trajectory_region_score(_straight(lateral=1.7), reference, 91.0, 11.0, 19)
    assert inside and score == 91.0
    score, inside = trajectory_region_score(_straight(lateral=100.0), reference, 91.0, 11.0, 19)
    assert not inside and score == 4.0
    with pytest.raises(ValueError, match="unsupported"):
        trajectory_region_score(reference, reference, 80.0, 5.0, 7)


def test_three_and_five_second_regions_use_distinct_thresholds():
    reference = _straight()
    candidate = _straight()
    candidate[11] = (reference[11][0], 0.6)
    candidate[19] = (reference[19][0], 0.6)
    score_3s, inside_3s = trajectory_region_score(candidate, reference, 80.0, 1.4, 11)
    score_5s, inside_5s = trajectory_region_score(candidate, reference, 80.0, 1.4, 19)
    assert not inside_3s and score_3s < 80.0
    assert inside_5s and score_5s == 80.0


def test_candidate_scoring_selects_the_best_reference_at_both_horizons():
    candidate = TrajectoryCandidate("candidate", _straight(lateral=0.4))
    references = [
        TrajectoryReference("low", _straight(lateral=3.0), 70.0),
        TrajectoryReference("high", _straight(lateral=0.4), 95.0),
    ]
    score = score_candidate(candidate, references, 11.0)
    assert score.reference_3s_label == "high"
    assert score.reference_5s_label == "high"
    assert score.combined_score == 95.0


def test_short_trajectory_is_rejected():
    with pytest.raises(ValueError, match="requested selector index"):
        trajectory_region_score([(0.0, 0.0)], [(0.0, 0.0)], 80.0, 5.0, 11)
