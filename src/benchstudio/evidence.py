from __future__ import annotations

import hashlib
import json
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any


class NdjsonWriter:
    """Streaming NDJSON writer with the digest/count behavior used by rollouts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._digest = hashlib.sha256()
        self._count = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("wb")

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        self._handle.write(line)
        self._digest.update(line)
        self._count += 1

    def close(self) -> dict[str, Any]:
        self._handle.close()
        return {
            "uri": self.path.name,
            "digest_sha256": self._digest.hexdigest(),
            "record_count": self._count,
        }


def environment_fingerprint(backend_id: str | None = None) -> dict[str, Any]:
    """Capture reproducibility facts without embedding private paths or secrets."""
    package_names = ("mujoco", "genesis-world", "usd-core", "numpy", "scipy")
    result: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {},
    }
    for name in package_names:
        try:
            result["packages"][name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    if backend_id is not None:
        result["backend_id"] = backend_id
    return result
