import hashlib
import io
import json
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from benchstudio.pipeline import ReplayPipeline
from benchstudio.robopad import RoboPADReplay, _FIELDS

try:
    import numpy as np
except ImportError:
    np = None


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _raw(step):
    return {field: np.asarray([step]) for field in _FIELDS}


def _campaign(root):
    key = "fixture"
    slot = next(
        slot for slot in range(1, 100)
        if int(hashlib.sha256(f"proposal1-v1:libero_spatial/task0/initial{slot}".encode())
               .hexdigest()[:8], 16) % 10 in (6, 7)
    )
    identity = f"libero_spatial/task0/initial{slot}"
    manifest = _json(root / "manifest.json", {
        "stage": "validation_transfer_v1",
        "episodes": [{
            "key": key, "episode_id": identity, "split": "validation", "suite": "libero_spatial",
            "task": 0, "initial_state": slot, "seed": 42, "bddl_sha256": "a" * 64,
        }],
    })
    pre = root / "prepared" / key
    post = root / "evaluations" / key / "base"
    pre.mkdir(parents=True)
    post.mkdir(parents=True)
    np.savez(pre / "shared.npz", prefix=np.array([[0]], dtype=np.float32),
             boundary_state=np.array([1.0]))
    np.save(post / "nominal_actions.npy", np.array([[1]], dtype=np.float32))
    np.save(post / "nominal_states.npy", np.array([[1.0], [2.0]]))
    _json(post / "nominal_observations.json", [
        {field: hashlib.sha256(value.tobytes()).hexdigest() for field, value in _raw(tick).items()}
        for tick in (1, 2)
    ])
    record = {"status": "complete", "manifest_sha256": _digest(manifest), "episode_id": identity}
    prepared = _json(pre / "record.json", {
        **record, "kind": "prepare", "artifact_sha256": {"shared.npz": _digest(pre / "shared.npz")},
    })
    _json(post / "record.json", {
        **record, "kind": "evaluate", "prepared_record_sha256": _digest(prepared),
        "artifact_sha256": {path.name: _digest(path) for path in post.iterdir()},
        "branches": {"nominal": {"status": "complete", "steps": 1,
                                 "success": True, "termination": "success"}},
    })
    return post


class _Runtime:
    def __init__(self):
        sim = SimpleNamespace(forward=lambda: None, get_state=lambda: np.array([float(self.tick)]))
        base = SimpleNamespace(sim=sim, _get_observations=lambda **_: _raw(self.tick))
        self.env = SimpleNamespace(env=base)

    def restore(self):
        self.tick = 0
        return {"stop_reason": None, "native_success": False}

    def step(self, action):
        assert action.dtype == np.float32
        self.tick += 1
        self.raw_observation = _raw(self.tick)
        return {"stop_reason": "goal" if self.tick == 2 else None,
                "native_success": self.tick == 2}

    def close(self):
        pass


class ReplayPipelineTests(unittest.TestCase):
    def test_rejects_traversal_before_opening_native_runtime(self):
        with TemporaryDirectory() as temporary:
            archive = Path(temporary) / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                member = tarfile.TarInfo("../escape")
                member.size = 1
                tar.addfile(member, io.BytesIO(b"x"))
            with self.assertRaisesRegex(ValueError, "unsafe archive entry"):
                ReplayPipeline.from_archive(archive).run()

    @unittest.skipIf(np is None, "archive fixture requires NumPy")
    def test_replays_original_evidence_from_archive(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "campaign"
            root.mkdir()
            _campaign(root)
            archive = Path(temporary) / "attempt.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(root, arcname="campaign")
            with patch.object(RoboPADReplay, "_runtime", side_effect=lambda *a, **kw: _Runtime()):
                result = ReplayPipeline.from_archive(archive).run()
            self.assertEqual(result.summary(), {
                "episode": "fixture", "passed": True, "first_difference": None,
                "difference_count": 0, "environment_checked": True,
            })

    @unittest.skipIf(np is None, "archive fixture requires NumPy")
    def test_rejects_changed_archive_artifact(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            post = _campaign(root)
            (post / "nominal_observations.json").write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
                ReplayPipeline.from_archive(root).check()
