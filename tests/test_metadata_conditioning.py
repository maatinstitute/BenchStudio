import unittest

from benchstudio.analysis.metadata_conditioning import (
    condition_prompt,
    format_metadata,
    validate_metadata,
)


class MetadataConditioningTests(unittest.TestCase):
    def test_normalizes_and_orders_fields(self):
        value = validate_metadata(
            {
                "outcome": "SUCCESS",
                "mistake": False,
                "recovery": "original_recovery",
                "quality": 5,
                "speed": 2000,
                "provenance": "base_rollout",
            }
        )
        self.assertEqual(value["recovery"], "original-recovery")
        self.assertEqual(
            format_metadata(value),
            "Metadata: outcome=success; quality=5; mistake=false; "
            "recovery=original-recovery; speed=2000; provenance=base-rollout",
        )

    def test_missing_annotations_are_explicit(self):
        prompt = condition_prompt("pick up the bowl", {"outcome": "unknown"})
        self.assertIn("outcome=unknown", prompt)
        self.assertIn("mistake=unknown", prompt)

    def test_none_preserves_ordinary_prompt(self):
        self.assertEqual(condition_prompt("  pick_up the bowl  "), "pick_up the bowl")

    def test_rejects_invalid_or_extra_fields(self):
        with self.assertRaises(ValueError):
            validate_metadata({"outcome": "success", "quality": 6})
        with self.assertRaises(ValueError):
            validate_metadata({"outcome": "success", "mistake": "maybe"})
        with self.assertRaises(ValueError):
            validate_metadata({"outcome": "success", "label": "leak"})


if __name__ == "__main__":
    unittest.main()
