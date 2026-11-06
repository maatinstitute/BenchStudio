"""Runtime capture for a Python 3.8 native evaluator process. Stdlib only; 3.8-compatible.

`import benchstudio` fails on Python 3.8: the package declares requires-python >=3.10, and
`benchstudio/measurement.py` subscripts `collections.abc.Callable` at import time. This helper
therefore reads `src/benchstudio/integrations/native_evaluator_evidence.py` once, records the sha256
of those bytes, executes the same bytes as a standalone module, and calls its unmodified
`capture_native_runtime`. No capture logic is copied here.

Use it INSIDE the evaluator process, after its dependencies are imported and its renderer is current
(docs/refinement-v3-qualification.md, "Capturing runtime and replay evidence in the native
process"):

    import importlib.util
    helper_path = "<BenchStudio>/examples/external_runtime/native_runtime_capture_py38.py"
    spec = importlib.util.spec_from_file_location("bs_capture", helper_path)
    ...
    capture_and_write(output_dir, modules={"libero": libero, ...}, files=RUNTIME_FILE_GROUPS)

It writes `capture.json` and `runtime.json` (exactly the identity mapping) into a new directory and
never overwrites. `capture.json` adds `capture_module_sha256` and `renderer_source`
("active_opengl_identity" or "injected"), so a validator can refuse a capture made with another
module version or with an injected renderer (`scripts/validate_refinement_evidence.py runtime`).

What the identity establishes, per native_evaluator_evidence.py: the listed files had these bytes
at capture; the named modules were imported with these versions and this `__file__` content (for
a package, its `__init__.py` only); the GL strings of the current context. It does not establish
that a listed file was executed, what the rest of a package contains, which interpreter binary ran
(its path is recorded, not hashed), or anything about a second process.
"""

import hashlib
import json
import os
import types
from pathlib import Path

DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "benchstudio"
    / "integrations"
    / "native_evaluator_evidence.py"
)


class CaptureRefused(RuntimeError):
    pass


def load_capture_module(source=DEFAULT_SOURCE, expected_sha256=None):
    """Read once, hash those bytes, execute the same bytes. No .pyc, no second read."""
    path = Path(source)
    if not path.is_file():
        raise CaptureRefused("capture module not found: {}".format(path))
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise CaptureRefused("capture module {} is not the expected version".format(digest))
    module = types.ModuleType("_benchstudio_native_evaluator_evidence")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    module.__source_sha256__ = digest
    return module


def capture_and_write(
    output_dir, modules, files, read_renderer=None, source=DEFAULT_SOURCE, expected_sha256=None
):
    """modules: {distribution: imported module}; files: {group: {logical_name: path}}.

    read_renderer defaults to the module's active_opengl_identity, which needs a live GL context.
    An injected reader is recorded as renderer_source="injected" and is not runtime evidence.
    """
    module = load_capture_module(source, expected_sha256)
    kwargs = {
        "modules": modules,
        "files": {
            group: {name: Path(p) for name, p in entries.items()}
            for group, entries in files.items()
        },
    }
    if read_renderer is not None:
        kwargs["read_renderer"] = read_renderer
    capture = module.capture_native_runtime(**kwargs)
    capture["capture_module_sha256"] = module.__source_sha256__
    capture["renderer_source"] = "active_opengl_identity" if read_renderer is None else "injected"
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    for name, document in (("capture.json", capture), ("runtime.json", capture["identity"])):
        target = output / name
        with open(str(target), "x", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
        os.chmod(str(target), 0o444)
    return capture["identity"]
