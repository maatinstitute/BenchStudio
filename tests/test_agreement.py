import json
import unittest
from pathlib import Path

from reva.analysis.agreement import DIMENSIONS, compare, metrics, validate


def synthetic(identifier):
    p = json.loads(Path(__file__).with_name("blind_annotation.json").read_text())
    p["annotator"] = {
        "id": identifier,
        "kind": "model",
        "prior_label_exposure": "none",
        "completed_at": "SYNTHETIC TEST",
    }
    for i, r in enumerate(p["papers"]):
        for k in ("source_version", "comparison_id", "claim_locator", "boundary"):
            r[k] = "SYNTHETIC"
        for c in r["cells"].values():
            c.update(
                label="P" if i % 2 else "NA",
                source_locator="SYNTHETIC",
                evidence="SYNTHETIC",
                rationale="SYNTHETIC",
            )
    return p


class AgreementTests(unittest.TestCase):
    def test_known_kappa(self):
        # Balanced margins, 50% observed agreement, chance agreement 50%.
        self.assertEqual(metrics([("Q", "Q"), ("Q", "P"), ("P", "Q"), ("P", "P")])["kappa"], 0)
        self.assertEqual(metrics([("Q", "Q"), ("P", "P")])["kappa"], 1)
        self.assertIsNone(metrics([("Q", "Q")])["kappa"])
        self.assertIsNone(metrics([])["kappa"])

    def test_full_packet(self):
        r = compare(synthetic("A"), synthetic("B"))
        self.assertEqual(r["overall"]["n"], 128)
        self.assertEqual(r["overall"]["kappa"], 1)
        self.assertTrue(all(v["n"] == 16 for v in r["per_dimension"].values()))

    def test_reject_unresolved_and_scope_mismatch(self):
        p = synthetic("A")
        p["papers"][0]["cells"][DIMENSIONS[0]]["label"] = None
        with self.assertRaises(ValueError):
            validate(p)
        a, b = synthetic("A"), synthetic("B")
        b["papers"][0]["boundary"] = "OTHER"
        with self.assertRaises(ValueError):
            compare(a, b)

    def test_disagreement_and_missing_evidence(self):
        a, b = synthetic("A"), synthetic("B")
        b["papers"][0]["cells"][DIMENSIONS[0]]["label"] = "P"
        r = compare(a, b)
        self.assertEqual(len(r["disagreements"]), 1)
        self.assertEqual(r["overall"]["raw_agreement"], 127 / 128)
        b["papers"][0]["cells"][DIMENSIONS[0]]["evidence"] = None
        with self.assertRaises(ValueError):
            compare(a, b)

    def test_blind_template_has_no_labels_or_judgments(self):
        p = json.loads(Path(__file__).with_name("blind_annotation.json").read_text())
        self.assertEqual(len(p["papers"]), 16)
        for row in p["papers"]:
            self.assertEqual(set(row["cells"]), set(DIMENSIONS))
            self.assertTrue(all(v is None for c in row["cells"].values() for v in c.values()))
        with self.assertRaises(ValueError):
            validate(p)


if __name__ == "__main__":
    unittest.main()
