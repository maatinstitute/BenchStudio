import numpy as np
import pytest

from reva.integrations.robopad_remaining import remaining_worlds, retain_frame


def test_remaining_world_scope_is_fixed_and_nonretryable():
    slots = []
    for task in range(3):
        for demo in range(2):
            for world in remaining_worlds(task, demo, 0):
                slots.extend((task, demo, world, role) for role in ("attempt", "replay"))
    assert len(slots) == 32
    assert len(set(slots)) == 32
    assert (0, 0, "H", "attempt") not in slots
    for args in ((True, 0, 0), (3, 0, 0), (0, 0, True), (0, 0, 1)):
        with pytest.raises(ValueError):
            remaining_worlds(*args)


def test_dense_and_terminal_frames_are_retained_exactly(tmp_path):
    directory = tmp_path / "results"
    directory.mkdir()
    for step in (55, 56, 57, 58, 69):
        original = {f"rgb_{index}": np.full((2, 2, 3), step + index, dtype=np.uint8) for index in range(2)}
        aligned = {f"rgb_{index}": np.full((2, 2, 3), step + index + 1, dtype=np.uint8) for index in range(2)}
        digest = retain_frame(directory, step, original, aligned)
        assert len(digest) == 64
        with np.load(directory / f"frame-{step:03d}.npz", allow_pickle=False) as arrays:
            np.testing.assert_array_equal(arrays["original_rgb_0"], original["rgb_0"])
            np.testing.assert_array_equal(arrays["physics_rgb_1"], aligned["rgb_1"])
