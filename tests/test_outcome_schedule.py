import copy
import tempfile
import unittest

from ival.campaigns.outcome_schedule import (
    _digest,
    _payload,
    build_schedule,
    read_schedule,
    validate_schedule,
    write_schedule,
)


def rows():
    result = []
    for task_id in (1, 2):
        for outcome in ("success", "failure"):
            for index in range(12):
                result.append(
                    {
                        "sample_id": f"t{task_id}-{outcome}-{index}",
                        "task_id": task_id,
                        "branch": "displaced",
                        "parent_id": f"parent-{index % 3}",
                        "trajectory_id": f"traj-{task_id}-{outcome}-{index}",
                        "task": f"task {task_id}",
                        "observation_path": "obs.npz",
                        "action_path": "actions.npy",
                        "outcome": outcome,
                        "action_start": index,
                        "valid_positions": 50,
                    }
                )
    return result


class OutcomeScheduleTests(unittest.TestCase):
    def test_robopad_source_golden_vector_is_byte_identical(self):
        """Keep the IVal port aligned with RoboPAD's frozen algorithm."""
        receipt = build_schedule(rows(), seed=123, updates=4)
        # Generated from RoboPAD experiments/outcome_schedule.py at the source
        # revision recorded in docs/source-attribution.md.  This is a parity
        # fixture, not a newly chosen expected result.
        self.assertEqual(
            receipt.schedule_sha256,
            "903284e9e3e1abbbc6cd40b169963214ea226f61749aac8977c04881a4c7e981",
        )
        self.assertEqual(
            [row["sample_id"] for row in receipt.rows_by_update[0]["M"]],
            [
                "t2-success-0",
                "t2-success-11",
                "t2-success-5",
                "t2-success-2",
                "t2-failure-0",
                "t2-failure-11",
                "t2-failure-5",
                "t2-failure-2",
            ],
        )

    def test_repeated_build_is_byte_identical(self):
        first = build_schedule(rows(), seed=123, updates=4)
        second = build_schedule(rows(), seed=123, updates=4)
        self.assertEqual(first.schedule_sha256, second.schedule_sha256)
        self.assertEqual(first.rows_by_update, second.rows_by_update)

    def test_m_u_c_share_ordered_rows_and_masks(self):
        receipt = build_schedule(rows(), seed=123, updates=4)
        for update in receipt.rows_by_update:
            self.assertEqual(update["M"], update["U"])
            self.assertEqual(update["M"], update["C"])
            self.assertEqual(update["M_masks"], update["U_masks"])
            self.assertEqual(update["M_masks"], update["C_masks"])

    def test_s_reuses_positive_slots_and_replaces_failure_slots(self):
        receipt = build_schedule(rows(), seed=123, updates=4)
        for update in receipt.rows_by_update:
            self.assertEqual(update["S"][:4], update["M"][:4])
            self.assertTrue(all(row["outcome"] == "success" for row in update["S"]))
            self.assertTrue(
                any(
                    row["sample_id"] != update["M"][i]["sample_id"]
                    for i, row in enumerate(update["S"][4:], start=4)
                )
            )

    def test_full_run_exposure_is_25600_positions(self):
        receipt = build_schedule(rows(), seed=123, updates=64)
        self.assertEqual(receipt.exposure["M"]["valid_positions"], 25600)
        self.assertEqual(receipt.exposure["C"]["windows"], 512)

    def test_small_two_class_strata_can_reuse_windows(self):
        small = [row for row in rows() if row["task_id"] == 1 and row["action_start"] < 4]
        receipt = build_schedule(small, seed=123, updates=1)
        self.assertEqual(len(receipt.rows_by_update[0]["M"]), 8)

    def test_empty_two_class_stratum_is_rejected(self):
        only_success = [
            row for row in rows() if row["outcome"] == "success" and row["task_id"] == 1
        ]
        with self.assertRaisesRegex(ValueError, "two-class"):
            build_schedule(only_success, seed=123, updates=1)

    def test_changed_order_is_rejected(self):
        receipt = build_schedule(rows(), seed=123, updates=2)
        changed = copy.deepcopy(receipt)
        changed.rows_by_update[0]["U"][0], changed.rows_by_update[0]["U"][1] = (
            changed.rows_by_update[0]["U"][1],
            changed.rows_by_update[0]["U"][0],
        )
        with self.assertRaisesRegex(ValueError, "ordered"):
            validate_schedule(changed)

    def test_non_50_mask_is_rejected(self):
        receipt = build_schedule(rows(), seed=123, updates=1)
        for arm in ("M_masks", "U_masks", "C_masks"):
            receipt.rows_by_update[0][arm][0] = [1] * 49
        with self.assertRaisesRegex(ValueError, "mask"):
            validate_schedule(receipt)

    def test_mutating_all_arms_is_caught_by_schedule_hash(self):
        receipt = build_schedule(rows(), seed=123, updates=1)
        receipt.rows_by_update[0]["M"][0]["action_start"] += 1
        receipt.rows_by_update[0]["U"][0]["action_start"] += 1
        receipt.rows_by_update[0]["C"][0]["action_start"] += 1
        with self.assertRaisesRegex(ValueError, "hash"):
            validate_schedule(receipt)

    def test_runtime_bindings_survive_schedule_freeze(self):
        receipt = build_schedule(rows(), seed=123, updates=1)
        row = receipt.rows_by_update[0]["C"][0]
        self.assertIn(row["task"], {"task 1", "task 2"})
        self.assertEqual(row["observation_path"], "obs.npz")
        self.assertEqual(row["action_path"], "actions.npy")

    def test_schedule_round_trip_preserves_hash(self):
        receipt = build_schedule(rows(), seed=123, updates=1)
        with tempfile.TemporaryDirectory() as directory:
            path = write_schedule(receipt, f"{directory}/schedule.json")
            loaded = read_schedule(path)
        self.assertEqual(loaded.schedule_sha256, receipt.schedule_sha256)
        self.assertEqual(loaded.rows_by_update, receipt.rows_by_update)

    def test_schedule_hash_and_update_count_are_required(self):
        receipt = build_schedule(rows(), seed=123, updates=1)
        receipt.schedule_sha256 = ""
        with self.assertRaisesRegex(ValueError, "hash"):
            validate_schedule(receipt)
        receipt = build_schedule(rows(), seed=123, updates=1)
        receipt.config["updates"] = 64
        with self.assertRaisesRegex(ValueError, "updates"):
            validate_schedule(receipt)

    def test_hierarchical_sampling_reaches_all_parents(self):
        receipt = build_schedule(rows(), seed=123, updates=64)
        selected = {row["parent_id"] for update in receipt.rows_by_update for row in update["M"]}
        self.assertEqual(selected, {"parent-0", "parent-1", "parent-2"})

    def test_required_one_class_stratum_is_reported_and_rejected(self):
        extra = [
            {
                "sample_id": "one-class",
                "task_id": 99,
                "branch": "nominal",
                "parent_id": "p",
                "trajectory_id": "t",
                "outcome": "success",
                "action_start": 0,
                "valid_positions": 50,
            }
        ]
        with self.assertRaisesRegex(ValueError, "required stratum"):
            build_schedule(
                rows() + extra,
                seed=123,
                updates=1,
                required_strata=[(1, "displaced"), (99, "nominal")],
            )

    def test_rehashed_schedule_cannot_hide_missing_masks_or_foreign_replacement(self):
        receipt = build_schedule(rows(), seed=123, updates=1)
        del receipt.rows_by_update[0]["C_masks"]
        receipt.schedule_sha256 = _digest(_payload(receipt))
        with self.assertRaisesRegex(ValueError, "mask"):
            validate_schedule(receipt)

        receipt = build_schedule(rows(), seed=123, updates=1)
        receipt.rows_by_update[0]["S"][4]["task_id"] = 999
        receipt.schedule_sha256 = _digest(_payload(receipt))
        with self.assertRaisesRegex(ValueError, "task/branch"):
            validate_schedule(receipt)

    def test_rehashed_schedule_rejects_invalid_action_start_and_missing_identity(self):
        receipt = build_schedule(rows(), seed=123, updates=1)
        receipt.rows_by_update[0]["M"][0]["action_start"] = -1
        receipt.schedule_sha256 = _digest(_payload(receipt))
        with self.assertRaisesRegex(ValueError, "action_start"):
            validate_schedule(receipt)

        receipt = build_schedule(rows(), seed=123, updates=1)
        del receipt.rows_by_update[0]["M"][0]["trajectory_id"]
        receipt.schedule_sha256 = _digest(_payload(receipt))
        with self.assertRaisesRegex(ValueError, "trajectory_id"):
            validate_schedule(receipt)


if __name__ == "__main__":
    unittest.main()
