import unittest

from benchstudio.analysis.outcome_eval import (
    boundary_outcome,
    first_attainment_step,
    inference_kwargs,
    prompt_mode_for_arm,
    validate_evaluation_branch,
    validate_replay_attainment,
)


class OutcomeEvalPromptTests(unittest.TestCase):
    def test_c_requests_success(self):
        self.assertEqual(prompt_mode_for_arm("C"), "desired_success")
        self.assertEqual(inference_kwargs("C"), {"prompt_mode": "desired_success"})

    def test_u_requests_unknown_metadata(self):
        self.assertEqual(prompt_mode_for_arm("U"), "all_metadata_unknown")

    def test_nonconditioned_arms_remain_task_only(self):
        for arm in ("B", "S", "M", "base", "control", "corrective"):
            with self.subTest(arm=arm):
                self.assertEqual(prompt_mode_for_arm(arm), "task_only")

    def test_unknown_arm_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "arm"):
            prompt_mode_for_arm("evaluation_result")

    def test_boundary_success_is_a_common_exclusion(self):
        self.assertEqual(
            boundary_outcome(True),
            {"status": "excluded_prepolicy_success", "success": None, "steps": 0},
        )
        self.assertIsNone(boundary_outcome(False))

    def test_first_attainment_stops_at_first_success(self):
        self.assertEqual(first_attainment_step([False, True, True]), 2)
        self.assertIsNone(first_attainment_step([False, False]))

    def test_replay_must_preserve_attainment_step(self):
        validate_replay_attainment(2, 2)
        with self.assertRaisesRegex(ValueError, "attainment"):
            validate_replay_attainment(2, 3)

    def test_branch_acceptance_requires_prespecified_screen_and_replay(self):
        prepared = {
            "supported": True,
            "pre_policy_success": False,
            "intervention": {"max_contact_penetration_m": 0.001},
        }
        branch = {
            "status": "complete",
            "success": False,
            "steps": 3,
            "first_attainment_step": None,
            "independent_replay": {
                "max_state_error": 0.0,
                "goal_matches": True,
                "observation_frames_checked": 4,
                "first_attainment_step": None,
            },
        }
        self.assertEqual(
            validate_evaluation_branch(branch, prepared, 0.002, "test"),
            {"success": False, "steps": 3, "excluded": False},
        )
        broken = dict(
            branch,
            independent_replay=dict(branch["independent_replay"], observation_frames_checked=3),
        )
        with self.assertRaisesRegex(ValueError, "Replay"):
            validate_evaluation_branch(broken, prepared, 0.002, "test")

    def test_success_attainment_step_must_match_replay(self):
        prepared = {
            "supported": True,
            "pre_policy_success": False,
            "intervention": {"max_contact_penetration_m": 0.001},
        }
        branch = {
            "status": "complete",
            "success": True,
            "steps": 3,
            "first_attainment_step": 2,
            "independent_replay": {
                "max_state_error": 0.0,
                "goal_matches": True,
                "observation_frames_checked": 4,
                "first_attainment_step": 2,
            },
        }
        self.assertFalse(validate_evaluation_branch(branch, prepared, 0.002, "test")["excluded"])
        broken = dict(
            branch, independent_replay=dict(branch["independent_replay"], first_attainment_step=3)
        )
        with self.assertRaisesRegex(ValueError, "Replay"):
            validate_evaluation_branch(broken, prepared, 0.002, "test")


if __name__ == "__main__":
    unittest.main()
