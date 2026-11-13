import pytest

from reva.analysis import clopper_pearson_interval, discordance_interval


def test_exact_paired_discordance_interval_is_bounded_and_nonzero():
    low, high = discordance_interval(0, 0, 4, alpha=0.05 / 60)
    assert low < 0 < high
    assert high - low > 0.1


def test_exact_interval_rejects_invalid_counts():
    with pytest.raises(ValueError):
        clopper_pearson_interval(3, 2)
    with pytest.raises(ValueError):
        discordance_interval(1, 1, 1)
