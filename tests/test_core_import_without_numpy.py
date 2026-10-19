from __future__ import annotations

import subprocess
import sys


def test_core_import_does_not_require_numpy():
    script = """
import importlib.abc
import sys

class BlockNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numpy' or fullname.startswith('numpy.'):
            raise ModuleNotFoundError('numpy intentionally blocked for smoke test')
        return None

sys.meta_path.insert(0, BlockNumpy())
import benchstudio
from benchstudio.analysis import parity
assert parity.PolicyParityReport(0, 0, ()).equivalent
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
