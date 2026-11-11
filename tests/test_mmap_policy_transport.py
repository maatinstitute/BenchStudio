"""Cross-process mmap bridge smoke; no checkpoint or physics dependency."""
import sys

import pytest

np = pytest.importorskip("numpy")

from benchstudio.contracts import Observation
from benchstudio.external_policy import PersistentExternalCommandPolicy


_CHILD = '''import json, os, sys
from benchstudio.local_tensors import open_local_tensors
for line in sys.stdin:
    req = json.loads(line)
    op = req["operation"]
    if op == "reset":
        print(json.dumps({"status": "reset"}), flush=True)
    elif op == "predict":
        root = os.environ["BENCHSTUDIO_LOCAL_TENSOR_ROOT"]
        with open_local_tensors(req["observation"]["payload"], root=root) as image_payload:
            pixels = image_payload["images"]["front"]
            response = {
                "actions": [[float(pixels.mean())]],
                "metadata": {
                    "shape": list(pixels.shape),
                    "device": os.getenv("BENCHSTUDIO_LEROBOT_DEVICE"),
                },
            }
        print(json.dumps(response), flush=True)
    elif op == "close":
        print(json.dumps({"status": "closed"}), flush=True)
        break
'''


def test_mmap_external_policy_predicts_from_real_array():
    policy = PersistentExternalCommandPolicy(
        [sys.executable, "-c", _CHILD],
        tensor_transport="mmap",
        device="cpu",
        timeout_s=10,
    )
    try:
        policy.reset(seed=12)
        image = np.arange(6 * 7 * 3, dtype=np.uint8).reshape(6, 7, 3)
        result = policy.predict(
            Observation(sequence=0, sim_time_s=0, payload={"images": {"front": image}}),
            denoising_steps=1,
        )
        assert result.actions[0][0] == pytest.approx(float(image.mean()))
        assert result.metadata == {"shape": [6, 7, 3], "device": "cpu"}
        assert list(policy._local_tensors.root.iterdir()) == []
    finally:
        root = policy._local_tensors.root
        policy.close()
    assert not root.exists()


def test_mmap_does_not_silently_accept_invalid_device():
    with pytest.raises(ValueError, match="device"):
        PersistentExternalCommandPolicy([sys.executable, "-c", _CHILD], device="cuda")


def test_mmap_rejects_conflicting_device_environment():
    with pytest.raises(ValueError, match="conflicts"):
        PersistentExternalCommandPolicy(
            [sys.executable, "-c", _CHILD],
            device="cpu",
            environment={"BENCHSTUDIO_LEROBOT_DEVICE": "cuda:0"},
        )
