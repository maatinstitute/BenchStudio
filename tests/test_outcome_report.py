import unittest

from benchstudio.analysis.outcome_report import (
    analyze_primary,
    clopper_pearson,
    discordance_interval,
    summarize_cells,
)


def cells(c_success=True, u_success=True):
    result = []
    for task_id in range(1, 7):
        for seed in (123, 456, 789, 1011, 1213):
            for parent in range(4):
                result.append(
                    {
                        "task_id": task_id,
                        "seed": seed,
                        "parent_id": f"task{task_id}-parent{parent}",
                        "arm": "C",
                        "comparator": "U",
                        "c_success": c_success,
                        "u_success": u_success,
                        "status": "complete",
                    }
                )
    return result


def planned_cells():
    return [
        {"task_id": task_id, "seed": seed, "parent_id": f"task{task_id}-parent{parent}"}
        for task_id in range(1, 7)
        for seed in (123, 456, 789, 1011, 1213)
        for parent in range(4)
    ]


class OutcomeReportTests(unittest.TestCase):
    def test_all_ties_leave_a_wide_nonzero_interval(self):
        interval = discordance_interval(0, 0, 4, alpha=0.05 / 60)
        self.assertLess(interval[0], 0)
        self.assertGreater(interval[1], 0)
        self.assertGreater(interval[1] - interval[0], 0.1)

    def test_all_wins_and_swapped_wins_have_opposite_bounds(self):
        wins = discordance_interval(4, 0, 4, alpha=0.05 / 60)
        losses = discordance_interval(0, 4, 4, alpha=0.05 / 60)
        self.assertGreater(wins[1], wins[0])
        self.assertLess(losses[0], losses[1])
        self.assertAlmostEqual(wins[0], -losses[1], places=12)

    def test_duplicate_parent_is_not_counted_as_an_independent_parent(self):
        duplicate = cells()[:]
        duplicate.append(dict(duplicate[0]))
        with self.assertRaisesRegex(ValueError, "duplicate parent"):
            analyze_primary(duplicate, planned=planned_cells())

    def test_complete_primary_reports_parent_and_seed_counts(self):
        result = analyze_primary(cells(), planned=planned_cells())
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["task_count"], 6)
        self.assertEqual(result["seed_count"], 5)
        self.assertEqual(result["parents"], 24)
        self.assertEqual(result["interval_method"], "simultaneous_clopper_pearson_discordance_v1")

    def test_missing_cells_remain_unknown(self):
        result = analyze_primary(cells()[:-4], planned=planned_cells())
        self.assertEqual(result["status"], "partial_missing")
        self.assertIsNone(result["interval"])
        self.assertGreater(result["missing_groups"], 0)

    def test_unbound_analysis_cannot_claim_a_complete_interval(self):
        result = analyze_primary(cells(), planned=[])
        self.assertEqual(result["status"], "partial_missing")
        self.assertIsNone(result["interval"])

    def test_missing_one_parent_is_not_a_complete_primary_interval(self):
        observed = cells()[:-1]
        result = analyze_primary(observed, planned=planned_cells())
        self.assertEqual(result["status"], "partial_missing")
        self.assertIsNone(result["interval"])

    def test_planned_seed_panel_and_domain_are_frozen(self):
        with self.assertRaisesRegex(ValueError, "seeds"):
            analyze_primary(cells(), planned=planned_cells(), seeds=(123, 123))
        bad_plan = planned_cells() + [{"task_id": 99, "seed": 123, "parent_id": "p"}]
        with self.assertRaisesRegex(ValueError, "task"):
            analyze_primary(cells(), planned=bad_plan)

    def test_missing_tie_cell_gets_finite_matrix_bounds(self):
        result = analyze_primary(cells()[:-1], planned=planned_cells())
        self.assertEqual(result["missingness_bounds"], [-1 / 120, 1 / 120])

    def test_planned_attempted_complete_and_missing_are_visible(self):
        planned = [{"cell_id": "a"}, {"cell_id": "b"}, {"cell_id": "c"}]
        receipts = [{"cell_id": "a", "status": "complete"}, {"cell_id": "b", "status": "excluded"}]
        result = summarize_cells(planned, receipts)
        self.assertEqual(result["planned"], 3)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["complete"], 1)
        self.assertEqual(result["excluded"], 1)
        self.assertEqual(result["missing"], 1)

    def test_clopper_pearson_endpoints_are_bounded(self):
        low, high = clopper_pearson(2, 4, alpha=0.05)
        self.assertGreaterEqual(low, 0)
        self.assertLessEqual(high, 1)
        self.assertLess(low, high)


if __name__ == "__main__":
    unittest.main()
