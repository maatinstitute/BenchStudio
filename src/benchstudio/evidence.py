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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_artifact_manifest(root: Path, *, status: str) -> dict[str, Any]:
    """Bind produced run artifacts without creating a self-referential hash."""
    files = {}
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name != "artifact-manifest.json":
            files[path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    return {
        "schema": "benchstudio_artifact_manifest_v1",
        "status": status,
        "files": files,
    }


def write_manifest_trust_anchor(manifest_path: Path, anchor_path: Path) -> dict[str, Any]:
    """Write a digest outside the artifact directory for independent verification."""
    digest = sha256_file(manifest_path)
    anchor_path.write_text(f"sha256  {manifest_path.name}  {digest}\n", encoding="utf-8")
    return {"path": str(anchor_path), "sha256": digest}


def verify_artifact_manifest(
    root: Path,
    trust_anchor_path: Path | None = None,
    trusted_manifest_sha256: str | None = None,
    signature_path: Path | None = None,
    trusted_public_key: bytes | None = None,
) -> dict[str, Any]:
    """Verify bound files and, optionally, an independently supplied digest.

    The generated sibling anchor is useful for accidental tampering. A digest
    supplied by a separate store or verifier is the stronger trust reference
    and is checked independently when provided.
    """
    manifest_path = root / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches: list[dict[str, Any]] = []
    anchor = trust_anchor_path or root.parent / f"{root.name}.artifact-manifest.sha256"
    trust_anchor: dict[str, Any] = {
        "path": str(anchor),
        "checked": anchor.is_file(),
        "external_reference_supplied": trusted_manifest_sha256 is not None,
    }
    if not anchor.is_file():
        mismatches.append({"file": manifest_path.name, "reason": "trust_anchor_missing"})
    else:
        parts = anchor.read_text(encoding="utf-8").strip().split()
        expected_digest = parts[-1] if parts else ""
        actual_digest = sha256_file(manifest_path)
        trust_anchor.update({"expected_sha256": expected_digest, "actual_sha256": actual_digest})
        if expected_digest != actual_digest:
            mismatches.append({"file": manifest_path.name, "reason": "trust_anchor_mismatch"})
    if trusted_manifest_sha256 is not None:
        actual_digest = sha256_file(manifest_path)
        trust_anchor["trusted_manifest_sha256"] = trusted_manifest_sha256
        trust_anchor["actual_sha256"] = actual_digest
        if trusted_manifest_sha256 != actual_digest:
            mismatches.append(
                {"file": manifest_path.name, "reason": "external_trust_reference_mismatch"}
            )
    signature: dict[str, Any] | None = None
    if signature_path is not None or trusted_public_key is not None:
        resolved_signature_path = (
            signature_path or root.parent / f"{root.name}.artifact-manifest.sig"
        )
        if not resolved_signature_path.is_file():
            mismatches.append({"file": manifest_path.name, "reason": "signature_missing"})
            signature = {"valid": False, "reason": "signature_missing"}
        elif trusted_public_key is None:
            mismatches.append({"file": manifest_path.name, "reason": "public_key_missing"})
            signature = {"valid": False, "reason": "public_key_missing"}
        else:
            from .evidence_signing import verify_manifest_signature

            signature = verify_manifest_signature(
                manifest_path, resolved_signature_path, trusted_public_key
            )
            if not signature["valid"]:
                mismatches.append({"file": manifest_path.name, "reason": signature["reason"]})
    bound_names = set(manifest.get("files", {}))
    for name, expected in manifest.get("files", {}).items():
        path = root / name
        if not path.is_file():
            mismatches.append({"file": name, "reason": "missing"})
            continue
        actual = sha256_file(path)
        if actual != expected.get("sha256") or path.stat().st_size != expected.get("bytes"):
            mismatches.append({"file": name, "reason": "digest_or_size_mismatch"})
    for path in root.iterdir():
        if (
            path.is_file()
            and path.name != "artifact-manifest.json"
            and path.name not in bound_names
        ):
            mismatches.append({"file": path.name, "reason": "unbound_artifact"})
    return {
        "valid": not mismatches,
        "status": manifest.get("status"),
        "mismatches": mismatches,
        "trust_anchor": trust_anchor,
        "signature": signature,
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
