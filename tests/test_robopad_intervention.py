import numpy as np
import pytest

from benchstudio.conformance.robopad_intervention import (
    irrelevant_candidates,
    screen_supported_body,
)


def test_fixed_candidate_grid_preserves_unedited_state():
    anchor = np.arange(40, dtype=float) / 100
    original = anchor.copy()
    rows = irrelevant_candidates(
        anchor, nq=21, nv=18, target_qpos=7, distractor_qpos=14, distractor_dof=12
    )
    assert len(rows) == 32
    assert len({row["id"] for row in rows}) == 32
    for row in rows:
        state = row["state"]
        mask = np.ones(40, dtype=bool)
        mask[15:17] = False
        mask[34:40] = False
        np.testing.assert_array_equal(state[mask], anchor[mask])
        np.testing.assert_array_equal(state[34:40], np.zeros(6))
        assert np.isclose(np.linalg.norm(state[15:17] - anchor[8:10]), row["radius_m"])
    np.testing.assert_array_equal(anchor, original)
    rows[0]["state"][0] = 99
    assert rows[1]["state"][0] != 99


def test_candidate_address_validation_is_fail_closed():
    for kwargs in (
        {"target_qpos": 14, "distractor_qpos": 14, "distractor_dof": 12},
        {"target_qpos": 7, "distractor_qpos": 18, "distractor_dof": 12},
        {"target_qpos": 7, "distractor_qpos": 14, "distractor_dof": 17},
    ):
        with pytest.raises(ValueError):
            irrelevant_candidates(np.zeros(40), nq=21, nv=18, **kwargs)


def test_support_screen_enforces_contact_and_inset_limits():
    def screen(contacts, footprint=((-0.1, -0.1), (0.1, 0.1))):
        return screen_supported_body(
            footprint_xy=footprint,
            support_half_size=(0.5, 0.5),
            contacts=contacts,
            support_geom="floor",
        )

    assert screen([{"other_geom": "floor", "distance": -0.0005}])["physical_valid"]
    assert screen([{"other_geom": "floor", "distance": -0.001}])["physical_valid"]
    assert not screen([{"other_geom": "floor", "distance": -0.00101}])["physical_valid"]
    for contacts in ([], [{"other_geom": "floor", "distance": 0.0001}]):
        assert not screen(contacts)["physical_valid"]
    assert not screen(
        [{"other_geom": "floor", "distance": 0}, {"other_geom": "finger", "distance": 0}]
    )["physical_valid"]
    assert not screen([{"other_geom": "floor", "distance": 0}], footprint=((0.491, 0),))[
        "physical_valid"
    ]


def test_support_screen_rejects_invalid_contact_metadata():
    for contacts in (
        [{"other_geom": "floor", "distance": float("nan")}],
        [{"other_geom": "", "distance": 0}],
    ):
        with pytest.raises(ValueError):
            screen_supported_body(
                footprint_xy=((-0.1, -0.1), (0.1, 0.1)),
                support_half_size=(0.5, 0.5),
                contacts=contacts,
                support_geom="floor",
            )
