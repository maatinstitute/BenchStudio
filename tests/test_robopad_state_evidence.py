import json

import numpy as np
import pytest

from reva.integrations.robopad_state_evidence import json_numpy


def test_simulator_scalar_and_array_metadata():
    source = {
        "mapping": {"qpos_address": [np.int32(9), np.int64(16)]},
        "contact": np.bool_(True),
        "pose": np.array([0.1, 0.2, 0.3]),
        "error": "original diagnostic error",
    }
    decoded = json.loads(json.dumps(source, default=json_numpy))
    assert decoded == {
        "mapping": {"qpos_address": [9, 16]},
        "contact": True,
        "pose": [0.1, 0.2, 0.3],
        "error": "original diagnostic error",
    }


def test_unknown_metadata_is_not_silently_stringified():
    with pytest.raises(TypeError, match="Unsupported report type"):
        json.dumps({"unknown": object()}, default=json_numpy)
