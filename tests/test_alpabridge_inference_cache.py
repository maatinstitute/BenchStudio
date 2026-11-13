import math
from types import SimpleNamespace

import numpy as np
import pytest

from ival.integrations.alpabridge_inference_cache import (
    CachedInference,
    PoseReanchoredInferenceCache,
    cache_context,
    reanchor_trajectory,
)


def _pose(x, y, yaw):
    half = yaw / 2
    return SimpleNamespace(pose=SimpleNamespace(vec=SimpleNamespace(x=x, y=y), quat=SimpleNamespace(w=math.cos(half), x=0.0, y=0.0, z=math.sin(half))) )


def test_reanchor_round_trip_and_translation():
    cached = CachedInference(0, np.array([0.0, 0.0]), 0.0, np.array([[5.0, 0.0]]))
    np.testing.assert_allclose(reanchor_trajectory(cached, current_xy=np.array([2.0, 0.0]), current_yaw=0.0), [[3.0, 0.0]])
    np.testing.assert_allclose(reanchor_trajectory(cached, current_xy=np.array([0.0, 0.0]), current_yaw=math.pi / 2), [[0.0, -5.0]], atol=1e-10)


def test_cache_context_extracts_pose_and_disables_missing_context():
    value = SimpleNamespace(session_uuid="s", time_now_us=1_000_000, ego_pose_history=[_pose(3.0, 4.0, math.pi / 2)])
    session, timestamp, xy, yaw = cache_context(value)
    assert session == "s" and timestamp == 1_000_000
    np.testing.assert_allclose(xy, [3.0, 4.0])
    assert yaw == pytest.approx(math.pi / 2)
    assert cache_context(SimpleNamespace(session_uuid=None, time_now_us=0, ego_pose_history=[])) == (None, None, None, None)


def test_cache_reuses_within_interval_and_refreshes_after():
    cache = PoseReanchoredInferenceCache(0.5)
    calls = []

    def infer():
        calls.append(1)
        return np.array([[5.0, 0.0]])

    def inp(t, x):
        return SimpleNamespace(session_uuid="s", time_now_us=t, ego_pose_history=[_pose(x, 0.0, 0.0)])

    assert cache.get(inp(0, 0.0), infer)[1] is False
    assert cache.get(inp(200_000, 1.0), infer)[1] is True
    assert cache.get(inp(600_000, 2.0), infer)[1] is False
    assert len(calls) == 2
    cache.forget("s")
    assert "s" not in cache._cache
