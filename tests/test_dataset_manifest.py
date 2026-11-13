import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from reva.analysis.dataset_manifest import resolve_manifest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OutcomeDatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "obs.npz").write_bytes(b"observation-fixture")
        (self.root / "actions.npy").write_bytes(b"action-fixture")
        (self.root / "evidence.json").write_text('{"native_success": true}\n')

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, **changes):
        row = {
            "sample_id": "sample-1",
            "episode_id": "libero_spatial/task1/initial0",
            "task": "put the red mug in the drawer",
            "task_id": 1,
            "parent_id": "parent-1",
            "branch": "nominal",
            "trajectory_id": "traj-1",
            "observation_path": "obs.npz",
            "observation_sha256": digest(self.root / "obs.npz"),
            "observation_frame_index": 10,
            "action_path": "actions.npy",
            "action_sha256": digest(self.root / "actions.npy"),
            "action_trajectory_id": "traj-1",
            "action_start": 10,
            "action_shape": [100, 7],
            "action_finite": True,
            "outcome": "success",
            "outcome_evidence_path": "evidence.json",
            "outcome_evidence_sha256": digest(self.root / "evidence.json"),
            "split": "train",
            "ancestry": [],
            "handoff_boundaries": [],
        }
        row.update(changes)
        return row

    def write_manifest(self, rows, purpose="training"):
        path = self.root / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "outcome_dataset_v1",
                    "purpose": purpose,
                    "rows": rows,
                },
                indent=2,
            )
            + "\n"
        )
        return path

    def test_accepts_hash_bound_full_window(self):
        resolution = resolve_manifest(self.write_manifest([self.row()]))
        self.assertEqual(len(resolution.rows), 1)
        self.assertEqual(resolution.rows[0]["valid_positions"], 50)
        self.assertEqual(list(resolution.exclusions), [])

    def test_rejects_observation_hash_mismatch(self):
        with self.assertRaisesRegex(ValueError, "observation hash"):
            resolve_manifest(self.write_manifest([self.row(observation_sha256="0" * 64)]))

    def test_rejects_crossed_action_trajectory(self):
        with self.assertRaisesRegex(ValueError, "trajectory"):
            resolve_manifest(self.write_manifest([self.row(action_trajectory_id="other")]))

    def test_rejects_future_frame_observation(self):
        with self.assertRaisesRegex(ValueError, "pre-action"):
            resolve_manifest(
                self.write_manifest([self.row(observation_frame_index=11, action_start=10)])
            )

    def test_rejects_short_target_window(self):
        with self.assertRaisesRegex(ValueError, "50"):
            resolve_manifest(self.write_manifest([self.row(action_shape=[55, 7], action_start=10)]))

    def test_excludes_unknown_outcome_with_reason(self):
        resolution = resolve_manifest(
            self.write_manifest([self.row(outcome="unknown")]), purpose="inventory"
        )
        self.assertEqual(list(resolution.rows), [])
        self.assertEqual(resolution.exclusions[0]["reason"], "unknown_outcome")

    def test_rejects_unknown_outcome_for_training(self):
        with self.assertRaisesRegex(ValueError, "unknown outcome"):
            resolve_manifest(self.write_manifest([self.row(outcome="unknown")]))

    def test_rejects_foreign_split(self):
        with self.assertRaisesRegex(ValueError, "split"):
            resolve_manifest(self.write_manifest([self.row(split="test")]))

    def test_rejects_window_crossing_handoff(self):
        with self.assertRaisesRegex(ValueError, "handoff"):
            resolve_manifest(self.write_manifest([self.row(handoff_boundaries=[40])]))

    def test_rejects_missing_parent_lineage(self):
        row = self.row()
        del row["parent_id"]
        with self.assertRaisesRegex(ValueError, "parent_id"):
            resolve_manifest(self.write_manifest([row]))


if __name__ == "__main__":
    unittest.main()
