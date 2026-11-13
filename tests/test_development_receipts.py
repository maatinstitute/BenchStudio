import json
import tempfile
import unittest
from pathlib import Path

from ival.analysis.development_receipts import (
    build_development_receipt,
    read_development_receipt,
    validate_development_receipt,
    write_development_receipt,
)


def digest(letter):
    return letter * 64


def zero_receipt():
    return {
        "schema_version": "smolvla_development_receipt_v1",
        "status": "complete",
        "development_only": True,
        "science_eligible": False,
        "checkpoint_eligible": False,
        "kind": "zero_update",
        "updates": 0,
        "base_checkpoint_sha256": digest("a"),
        "output_sha256": digest("b"),
        "checkpoint_discarded": True,
        "parameter_delta_max": 0.0,
        "reload_preprocessing_match": True,
        "fixed_noise_action_match": True,
    }


class OutcomeDevelopmentTests(unittest.TestCase):
    def test_zero_update_receipt_is_explicitly_non_scientific(self):
        self.assertEqual(validate_development_receipt(zero_receipt())["updates"], 0)

    def test_one_update_requires_finite_gradient_and_mask_checks(self):
        receipt = zero_receipt() | {
            "kind": "one_update",
            "updates": 1,
            "finite_loss": True,
            "updated_parameter_count": 3,
            "mask_valid_positions": 50,
            "mask_reduction_verified": True,
        }
        del receipt["parameter_delta_max"]
        self.assertEqual(validate_development_receipt(receipt)["updates"], 1)

    def test_development_receipts_cannot_be_promoted_to_science(self):
        for field, value in (
            ("science_eligible", True),
            ("checkpoint_eligible", True),
            ("checkpoint_discarded", False),
        ):
            with self.subTest(field=field):
                receipt = zero_receipt()
                receipt[field] = value
                with self.assertRaisesRegex(ValueError, "development"):
                    validate_development_receipt(receipt)

    def test_invalid_update_and_zero_identity_fail_closed(self):
        receipt = zero_receipt()
        receipt["updates"] = 2
        with self.assertRaisesRegex(ValueError, "updates"):
            validate_development_receipt(receipt)
        receipt = zero_receipt()
        receipt["parameter_delta_max"] = 1.0
        with self.assertRaisesRegex(ValueError, "zero-update"):
            validate_development_receipt(receipt)

    def test_development_receipts_have_atomic_read_write_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "receipt.json"
            write_development_receipt(zero_receipt(), path)
            self.assertEqual(read_development_receipt(path), zero_receipt())
            mutated = json.loads(path.read_text())
            mutated["science_eligible"] = True
            path.write_text(json.dumps(mutated))
            with self.assertRaisesRegex(ValueError, "development"):
                read_development_receipt(path)

    def test_builder_constructs_only_non_scientific_receipts(self):
        receipt = build_development_receipt(
            "zero_update",
            base_checkpoint_sha256=digest("a"),
            output_sha256=digest("b"),
            metrics={
                "parameter_delta_max": 0.0,
                "reload_preprocessing_match": True,
                "fixed_noise_action_match": True,
            },
        )
        self.assertEqual(validate_development_receipt(receipt)["kind"], "zero_update")
        with self.assertRaisesRegex(ValueError, "reserved"):
            build_development_receipt(
                "one_update",
                base_checkpoint_sha256=digest("a"),
                output_sha256=digest("b"),
                metrics={
                    "science_eligible": True,
                    "finite_loss": True,
                    "updated_parameter_count": 1,
                    "mask_valid_positions": 50,
                    "mask_reduction_verified": True,
                },
            )


if __name__ == "__main__":
    unittest.main()
