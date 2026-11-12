from __future__ import annotations

import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "examples" / "refinement_refresh" / "verify.py"


def _load_example():
    spec = importlib.util.spec_from_file_location("refinement_refresh_verify", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paper_example_reproduces_published_aggregate_and_pairing() -> None:
    report = _load_example().reproduce()
    assert report["canonical_attempts"] == 1120
    assert report["recorded_actions"] == 171805
    assert report["primary"]["selected_wins"] == 24
    assert report["primary"]["comparator_wins"] == 7
    assert report["primary"]["ties"] == 129
    assert math.isclose(report["primary"]["success_difference"], 0.10625, abs_tol=1e-12)
