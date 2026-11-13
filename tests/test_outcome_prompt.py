import math
import unittest

from ival.analysis.metadata_conditioning import (
    condition_prompt,
    prompt_mode_metadata,
    validate_metadata,
)


class OutcomePromptTests(unittest.TestCase):
    def test_task_only_prompt_is_unchanged(self):
        self.assertEqual(prompt_mode_metadata("task_only"), None)
        self.assertEqual(
            condition_prompt("  open the drawer  ", prompt_mode_metadata("task_only")),
            "open the drawer",
        )

    def test_unknown_mode_is_explicit(self):
        metadata = prompt_mode_metadata("all_metadata_unknown")
        self.assertEqual(
            set(metadata), {"outcome", "quality", "mistake", "recovery", "speed", "provenance"}
        )
        self.assertTrue(all(value == "unknown" for value in metadata.values()))

    def test_training_outcome_and_desired_success_are_distinct(self):
        recorded = prompt_mode_metadata("recorded_outcome", recorded_outcome="failure")
        desired = prompt_mode_metadata("desired_success")
        self.assertEqual(recorded["outcome"], "failure")
        self.assertEqual(desired["outcome"], "success")
        self.assertNotEqual(recorded, desired)

    def test_rejects_nonfinite_and_boolean_numeric_scores(self):
        for value in (True, False, math.nan, math.inf, -math.inf, "fast"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_metadata({"outcome": "success", "quality": value})
        for value in (True, False, math.nan, math.inf, -math.inf, "very-fast"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_metadata({"outcome": "success", "speed": value})

    def test_rejects_unbounded_metadata_text(self):
        with self.assertRaises(ValueError):
            validate_metadata({"outcome": "success", "provenance": "x" * 257})

    def test_mode_cannot_take_evaluation_result(self):
        with self.assertRaises(ValueError):
            prompt_mode_metadata("evaluation_result", recorded_outcome="success")


if __name__ == "__main__":
    unittest.main()
