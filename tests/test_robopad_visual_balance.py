import numpy as np
import pytest

from reva.analysis.robopad_visual_balance import image_distance, match_candidates


def test_signed_rgb_distance_and_float_input_contract():
    black = np.zeros((2, 2, 3), dtype=np.uint8)
    white = np.full_like(black, 255)
    assert image_distance(black, white) == 1.0
    assert image_distance(white, black) == 1.0
    with pytest.raises(ValueError):
        image_distance(black.astype(float), white)
    a = np.zeros((1, 1, 3), dtype=np.float32)
    assert image_distance(a, np.full_like(a, 0.0001)) == pytest.approx(0.0001)
    with pytest.raises(ValueError):
        image_distance(a, np.full_like(a, -0.1))


def test_each_camera_must_balance_and_zero_change_cannot_qualify():
    relevant = [{"id": "r", "distance": [0.1, 0.2], "physical_valid": True}]
    irrelevant = [{"id": "i", "distance": [0.2, 0.1], "physical_valid": True}]
    result = match_candidates(relevant, irrelevant)
    assert result["match"] is None
    assert result["reason"] == "no_balanced_pair"
    zero = {"id": "z", "distance": [0, 0.1], "physical_valid": True}
    assert match_candidates([zero], [zero])["match"] is None
    with pytest.raises(ValueError):
        match_candidates(
            [{"id": "r", "distance": [float("nan"), 0.1], "physical_valid": True}],
            [irrelevant[0]],
        )


def test_balanced_pair_has_stable_tie_break_and_retains_rejections():
    relevant = [
        {"id": "r2", "distance": [0.1, 0.1], "physical_valid": True},
        {"id": "r1", "distance": [0.1, 0.1], "physical_valid": True},
    ]
    irrelevant = [
        {"id": "i", "distance": [0.105, 0.105], "physical_valid": True},
        {"id": "invalid", "distance": [0.1, 0.1], "physical_valid": False},
    ]
    result = match_candidates(relevant, irrelevant)
    assert result["match"]["relevant"] == "r1"
    assert result["match"]["irrelevant"] == "i"
    assert result["unmatched_relevant"] == ["r2"]
    assert result["invalid_irrelevant"] == ["invalid"]
    with pytest.raises(ValueError):
        match_candidates([relevant[0], relevant[0]], [irrelevant[0]])
    with pytest.raises(ValueError):
        match_candidates([{**relevant[0], "success": True}], [irrelevant[0]])
