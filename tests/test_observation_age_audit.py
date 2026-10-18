"""Synthetic integrity tests; fixtures are not empirical experiment records."""

import copy
import unittest

from benchstudio.analysis.observation_age_audit import digest, validate_inputs


class InputAuditTests(unittest.TestCase):
    def rows(self):
        fields = {"camera": "a" * 64, "state": "b" * 64}
        return [
            dict(
                tick=t,
                input_refreshed=t % 5 == 0,
                supplied_observation_tick=t - t % 5,
                supplied_observation_age_ticks=t % 5,
                current_observation_sha256=digest(fields),
                supplied_observation_sha256=digest(fields),
                supplied_observation_field_sha256=copy.deepcopy(fields),
            )
            for t in range(10)
        ]

    def test_static_observations_are_legal(self):
        validate_inputs(self.rows(), 5)

    def test_fresh_control(self):
        rows = self.rows()
        for row in rows:
            row.update(
                input_refreshed=True,
                supplied_observation_tick=row["tick"],
                supplied_observation_age_ticks=0,
            )
        validate_inputs(rows, 1)

    def test_tampering_rejected(self):
        for key, value in [
            ("tick", 99),
            ("input_refreshed", True),
            ("supplied_observation_tick", 1),
            ("supplied_observation_age_ticks", 0),
            ("supplied_observation_sha256", "c" * 64),
            ("supplied_observation_field_sha256", {"camera": "d" * 64}),
        ]:
            with self.subTest(key=key):
                rows = self.rows()
                rows[1][key] = value
                with self.assertRaises(ValueError):
                    validate_inputs(rows, 5)

    def test_refresh_must_use_current(self):
        rows = self.rows()
        rows[5]["current_observation_sha256"] = "e" * 64
        with self.assertRaises(ValueError):
            validate_inputs(rows, 5)


if __name__ == "__main__":
    unittest.main()
