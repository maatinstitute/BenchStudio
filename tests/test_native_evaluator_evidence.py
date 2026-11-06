import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from benchstudio.integrations.native_evaluator_evidence import (
    capture_native_runtime,
    native_frame_signature,
    replay_native_fixture,
)


def _frame(tick, *, pixels=0, stop=None):
    return {
        "state": {"tick": tick},
        "observation": {"image": [pixels], "position": [tick]},
        "native_success": False,
        "stop_reason": stop,
        "recorded_success": False if stop else None,
    }


class NativeEvaluatorEvidenceTests(unittest.TestCase):
    def test_capture_distinguishes_installed_and_imported_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "actual_module.py"
            source.write_text("# loaded code", encoding="utf-8")
            module = ModuleType("test_module")
            module.__file__ = str(source)
            module.__version__ = "2.0"
            files = {
                name: {"selected": source}
                for name in ("runner", "checkpoint", "assets", "normalization")
            }
            with patch("importlib.metadata.version", return_value="1.0"):
                capture = capture_native_runtime(
                    modules={"test-dist": module},
                    files=files,
                    read_renderer=lambda: {"vendor": "Mesa", "renderer": "llvmpipe", "version": "4"},
                )
                module.__version__ = "1.0"
                revised = capture_native_runtime(
                    modules={"test-dist": module},
                    files=files,
                    read_renderer=lambda: {"vendor": "Mesa", "renderer": "llvmpipe", "version": "4"},
                )
            self.assertEqual(capture["stack"]["modules"]["test-dist"]["imported_version"], "2.0")
            self.assertEqual(capture["stack"]["modules"]["test-dist"]["installed_version"], "1.0")
            self.assertNotEqual(
                capture["identity"]["simulator_stack"], revised["identity"]["simulator_stack"]
            )

    def test_exact_replay_exports_qualification_fixture(self):
        frames = [_frame(0), _frame(1, stop="horizon")]
        report = replay_native_fixture(
            fixture={"kind": "horizon_timeout"},
            actions=[[0.0]],
            expected=[native_frame_signature(frame) for frame in frames],
            restore=lambda: frames[0],
            step=lambda _: frames[1],
        )
        self.assertTrue(report["passed"])
        self.assertFalse(report["qualification_fixture"]["recorded_success"])
        self.assertEqual(report["qualification_fixture"]["samples"][-1]["step"], 1)

    def test_replay_locates_reset_and_post_action_mismatch(self):
        reference = [native_frame_signature(frame) for frame in (_frame(0), _frame(1))]
        for tick in (0, 1):
            with self.subTest(tick=tick):
                report = replay_native_fixture(
                    fixture={},
                    actions=[[0.0]],
                    expected=reference,
                    restore=lambda: _frame(0, pixels=int(tick == 0)),
                    step=lambda _: _frame(1, pixels=int(tick == 1)),
                )
                self.assertFalse(report["passed"])
                self.assertEqual(report["first_mismatch_step"], tick)
                self.assertEqual(report["differences"][0]["observation_fields"], ["image"])
                self.assertIsNone(report["qualification_fixture"])
