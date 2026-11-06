"""examples/external_runtime/native_runtime_capture_py38.py.

The helper must run on the Python 3.8 OpenPI client interpreter, where `import benchstudio` fails.
Set BENCHSTUDIO_PYTHON38 to a Python 3.8 interpreter to run the 3.8 checks; they are skipped
otherwise (CI runs 3.10-3.12).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
HELPER = ROOT / "examples/external_runtime/native_runtime_capture_py38.py"
PY38 = os.environ.get("BENCHSTUDIO_PYTHON38")
SYNTHETIC_GL = {"vendor": "SYNTHETIC", "renderer": "SYNTHETIC", "version": "SYNTHETIC"}


def _helper():
    spec = importlib.util.spec_from_file_location("bs_capture_py38", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _files(tmp_path):
    files = {}
    for group in ("runner", "checkpoint", "assets", "normalization"):
        path = tmp_path / f"{group}.bin"
        path.write_bytes(group.encode())
        files[group] = {group: path}
    return files


def test_capture_is_write_once_and_labels_injected_renderer(tmp_path):
    helper = _helper()
    identity = helper.capture_and_write(
        tmp_path / "out",
        modules={"pytest": pytest},
        files=_files(tmp_path),
        read_renderer=lambda: dict(SYNTHETIC_GL),
    )
    capture = json.loads((tmp_path / "out/capture.json").read_text())
    assert (
        json.loads((tmp_path / "out/runtime.json").read_text()) == identity == capture["identity"]
    )
    assert capture["renderer_source"] == "injected"
    with pytest.raises(FileExistsError):
        helper.capture_and_write(
            tmp_path / "out",
            modules={"pytest": pytest},
            files=_files(tmp_path),
            read_renderer=lambda: dict(SYNTHETIC_GL),
        )


def test_expected_digest_is_enforced(tmp_path):
    helper = _helper()
    with pytest.raises(helper.CaptureRefused):
        helper.load_capture_module(expected_sha256="0" * 64)


def test_missing_file_group_is_refused(tmp_path):
    files = _files(tmp_path)
    del files["checkpoint"]
    with pytest.raises(ValueError):
        _helper().capture_and_write(
            tmp_path / "out",
            modules={"pytest": pytest},
            files=files,
            read_renderer=lambda: dict(SYNTHETIC_GL),
        )


PY38_SCRIPT = r"""
import json, sys, tempfile, pathlib, importlib.util, pip
root = pathlib.Path(sys.argv[1])
try:
    sys.path.insert(0, str(root / "src"))
    import benchstudio.integrations.native_evaluator_evidence  # noqa: F401
    package_import = "ok"
except TypeError as exc:
    package_import = "TypeError: " + str(exc)
finally:
    sys.path.pop(0)
helper = root / "examples" / "external_runtime" / "native_runtime_capture_py38.py"
spec = importlib.util.spec_from_file_location("h", str(helper))
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
tmp = pathlib.Path(tempfile.mkdtemp())
files = {}
for g in ("runner", "checkpoint", "assets", "normalization"):
    p = tmp / (g + ".bin"); p.write_bytes(g.encode()); files[g] = {g: p}
gl = {"vendor": "SYNTHETIC", "renderer": "SYNTHETIC", "version": "SYNTHETIC"}
identity = h.capture_and_write(tmp / "out", {"pip": pip}, files, read_renderer=lambda: dict(gl))
cap = json.loads((tmp / "out" / "capture.json").read_text())
result = {"python": cap["stack"]["python"], "keys": sorted(identity)}
result["package_import"] = package_import
print(json.dumps(result))
"""


@pytest.mark.skipif(not PY38, reason="set BENCHSTUDIO_PYTHON38 to a Python 3.8 interpreter")
def test_helper_runs_on_python38_where_package_import_fails():
    proc = subprocess.run(
        [PY38, "-I", "-c", PY38_SCRIPT, str(ROOT)], capture_output=True, text=True, check=True
    )
    result = json.loads(proc.stdout)
    assert result["python"].startswith("3.8.")
    assert result["keys"] == [
        "assets",
        "checkpoint",
        "normalization",
        "renderer",
        "runner",
        "simulator_stack",
    ]
    assert result["package_import"].startswith("TypeError")
